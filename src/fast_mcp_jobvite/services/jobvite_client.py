"""The Jobvite client: auth and error detection (DESIGN.md:308-352).

**The load-bearing behaviour in this codebase is `evaluate_response`
below, and everything else in this module exists to feed it.**
DESIGN.md:344-345 states the invariant this module is built around:

    a response is successful only if the body carries no
    `status.code >= 400` **and** the HTTP status is below 400. Both,
    every call.

The trap it defends against is recorded, not hypothetical
(`JOBVITE-CONTRACT.md` §3.1): `api.jobvite.com` answers a rejected
credential with **HTTP 200** and a body of
`{"status":{"code":401,"messages":["Invalid api/secret..."]}}`. A client
branching on `response.status_code` reads that as success, looks for a
`candidates` key, does not find one, and reports **zero candidates for a
credential that was refused**. A wrong zero that explains itself is the
hardest kind to notice, which is why this is C5-S1, the only Critical on
the client.

**The two arms are written as two independent statements on purpose.**
Either one alone passes a plausible-looking test suite:

* Drop the envelope arm and the recorded 200-with-401-body fixture is
  reported as a success.
* Drop the HTTP arm and a transport-level failure carrying a body that
  has no `status` block at all is reported as a success.

`DESIGN.md:344-345` says *both, every call*, so both are here and each
has a case of its own that dies when it is removed.

**Decoding cannot assume JSON and cannot dispatch on content type
either** (DESIGN.md:347-349). Three error encodings are handled on the
routes we call - a JSON status envelope, plain text with **no
`Content-Type` header at all**, and a Tomcat HTML page.
`JOBVITE-CONTRACT.md` §3.3 records that the v1 `jobFeed` 401 sends no
`Content-Type`, which is what rules content-type sniffing out as the
dispatch.

**HR-XML is a hardened fallback, not a handled case**
(DESIGN.md:349-352). It appears on `/v1/candidate`, which we do not
call. If XML ever arrives it is parsed with `defusedxml` and treated as
an **error body** - never as a success - because entity expansion on
attacker-reachable input is not a risk worth taking for a route that
should never respond to us.

**Credentials.** v2 travels as the headers `x-jvi-api` and `x-jvi-sc`,
and **a URL containing a secret is never constructed**
(DESIGN.md:312-313), even though Jobvite's own published sample code
does exactly that. `GET /v1/jobFeed` is the one structural exception: it
requires `api`, `sc` and `companyId` as query parameters, so its URL is
classified sensitive and never reaches a log line whole. Redaction is
not reimplemented here - `utils/redaction.py` is the single enforcement
point DESIGN.md:312-318 requires, and this module calls it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic
from types import TracebackType
from typing import Any, Final, NoReturn, Protocol, Self

import httpx2
from circuitbreaker import CircuitBreaker, CircuitBreakerError
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring as defused_fromstring
from loguru import logger
from tenacity import AsyncRetrying, RetryCallState, stop_after_attempt, stop_after_delay
from tenacity.stop import stop_base
from tenacity.wait import wait_exponential_jitter

from ..errors import JobviteUnavailableError, JobviteUpstreamError
from ..utils.correlation import request_id_var
from ..utils.redaction import (
    install_log_redaction as _install_log_redaction,
)
from ..utils.redaction import redact_headers, redact_text, redact_url

# ----------------------------------------------------------------------
# Transport constants. `JOBVITE-CONTRACT.md` §2 records both base URLs
# as [RECORDED]; note the v1 base is `/v1`, NOT `/api/v1`.
# ----------------------------------------------------------------------
V2_BASE_URL: Final = "https://api.jobvite.com/api/v2"
V1_BASE_URL: Final = "https://api.jobvite.com/v1"

#: The v2 credential headers (DESIGN.md:312). `utils/redaction.py`
#: holds the same two names in `SECRET_HEADERS`; a test pins the two
#: lists together so a rename here cannot leave the redactor watching a
#: header that no longer exists.
API_KEY_HEADER: Final = "x-jvi-api"
# noqa on the next line: S105 flags the NAME of a header, not a
# credential. The value never appears in this file; it arrives as a
# SecretValue at construction.
API_SECRET_HEADER: Final = "x-jvi-sc"  # noqa: S105

#: The one route that structurally requires credentials in the query
#: string (DESIGN.md:315-318, `JOBVITE-CONTRACT.md` §2.1 rule 2).
JOBFEED_PATH: Final = "/jobFeed"

#: The threshold in `status.code >= 400` and `http_status < 400`
#: (DESIGN.md:344-345). Named rather than inlined twice, so the two arms
#: cannot drift apart under a later edit.
ERROR_STATUS_THRESHOLD: Final = 400

#: How much of an undecodable body may appear in an exception `detail`.
#: Jobvite's Tomcat HTML page is small, but nothing guarantees the next
#: one is, and this string reaches a log line. Truncation is a bound on
#: the blast radius, not a substitute for `redact_text`, which is
#: applied as well.
MAX_BODY_EXCERPT_CHARS: Final = 500

# ----------------------------------------------------------------------
# The `detail` a transport failure reaches the API consumer with.
# ENUMERATED, never formatted from the exception.
#
# `backend/error-handling.md` is `priority: required` and says at :383
# "Never leak raw exception messages from third-party libraries to API
# consumers" and at :493 "never pass `str(exc)` from third-party
# libraries". This module used to build `JobviteUnavailableError`'s
# detail as `redact_text(f"{type(exc).__name__}: {exc}")`, and that
# detail reaches the caller unchanged through `problem_from_exception`
# -> `build_problem`.
#
# **`redact_text` does not discharge the clause.** It bounds the
# credential classes it knows about - `api`, `sc`, `companyId`, userinfo
# passwords. An httpx2 exception string also carries `_ssl.c` line
# numbers, local socket paths and resolver detail, none of which are
# credential-shaped and all of which are third-party internals arriving
# at a consumer.
#
# **What the design actually requires is preserved**: DESIGN.md:368-372
# says an open breaker and an outage share
# `/problems/service-unavailable` 503 and "what distinguishes them is
# `detail`, which says whether Jobvite failed or whether we have stopped
# calling it". Three stable strings say exactly that, and a caller can
# still branch on them. The breaker's own counterpart string is U7's to
# add when the breaker exists; writing it here would be a constant with
# no producer.
#
# The exception text itself is not lost - it goes to the log line below,
# which is its correct destination.
# ----------------------------------------------------------------------
UNAVAILABLE_TIMEOUT_DETAIL: Final = (
    "Jobvite did not respond before the configured timeout elapsed. "
    "This is an upstream failure, not an open circuit breaker."
)
UNAVAILABLE_TRANSPORT_DETAIL: Final = (
    "Jobvite could not be reached. "
    "This is an upstream failure, not an open circuit breaker."
)
UNAVAILABLE_REQUEST_DETAIL: Final = (
    "The request to Jobvite could not be issued. "
    "This is a client-side transport failure, not an open circuit breaker."
)


def _unavailable_detail(exc: Exception) -> str:
    """Map a transport exception onto its enumerated `detail`.

    Dispatch is on the exception CLASS and the return values are
    constants, so nothing a third-party library wrote into the
    exception's text can reach the value this returns. That is the
    property `backend/error-handling.md:383` and `:493` ask for, and it
    is a property of the function rather than of a redactor applied
    afterwards.

    Args:
        exc: The transport exception caught around the request.

    Returns:
        One of the three module-level `UNAVAILABLE_*_DETAIL` constants.
    """
    if isinstance(exc, httpx2.TimeoutException):
        return UNAVAILABLE_TIMEOUT_DETAIL
    if isinstance(exc, httpx2.TransportError):
        # Every network-layer failure httpx2 raises: connect, read,
        # write, pool, protocol and proxy errors all subclass this.
        return UNAVAILABLE_TRANSPORT_DETAIL
    # `InvalidURL`, `CookieConflict` and `StreamError` sit outside the
    # `HTTPError` hierarchy entirely - see the `except` clause below.
    # Jobvite was never called on this path, so saying "could not be
    # reached" would be a false statement about the upstream service.
    return UNAVAILABLE_REQUEST_DETAIL


class SecretValue(Protocol):
    """The one method this module needs from a secret holder.

    **Structural rather than nominal, and that is deliberate.**
    DESIGN.md:335-336 requires credentials to be `SecretStr` throughout,
    resolved with `.get_secret_value()` only when building a request -
    and `SecretStr` is pydantic's. `pydantic` is present in the resolve
    only as a transitive of `fastmcp`, and U4's dependency slot is
    granted for `httpx2` and `defusedxml` and nothing else, so importing
    it here would either add an undeclared direct import or spend a slot
    that was not granted.

    A `Protocol` satisfies the design's actual requirement - the value
    is opaque until something deliberately unwraps it - and pydantic's
    `SecretStr` satisfies this Protocol structurally, so U1's
    configuration can hand one straight in with no adapter. See
    U4-IMPL-REPORT.md.
    """

    def get_secret_value(self) -> str:
        """Return the wrapped secret."""
        ...


# ======================================================================
# THE INVARIANT (DESIGN.md:344-345). Everything below this block is
# plumbing.
# ======================================================================


def evaluate_response(http_status: int, body: bytes) -> dict[str, Any]:
    """Apply the error-detection rule to one response, and decode it.

    **The invariant (DESIGN.md:344-345): a response is successful only
    if the body carries no `status.code >= 400` AND the HTTP status is
    below 400. Both, every call.**

    Args:
        http_status: The HTTP status line's code. **Not authoritative on
            its own** - see the module docstring and
            `JOBVITE-CONTRACT.md` §3.1.
        body: The raw response bytes. Raw rather than a parsed object,
            because the decision of whether this is even JSON is part of
            the rule.

    Returns:
        The decoded JSON body, when and only when both arms of the
        invariant hold.

    Raises:
        JobviteUpstreamError: On either arm of the invariant failing,
            and on a body that cannot be decoded as a JSON object at all
            - which includes the plain-text, HTML and XML encodings, all
            of which are errors.
    """
    payload = _decode_json_object(http_status, body)

    # ARM 1 - the body's own status envelope. This is the arm the
    # recorded 200-with-401-body fixture exercises, and the reason the
    # HTTP status is not consulted first: at that point the HTTP status
    # is 200 and says nothing.
    envelope_code = _envelope_status_code(payload)
    if envelope_code is not None and envelope_code >= ERROR_STATUS_THRESHOLD:
        raise JobviteUpstreamError(envelope_code, _envelope_message(payload))

    # ARM 2 - the HTTP status, applied INDEPENDENTLY rather than as an
    # `elif`. A body with no `status` block at all, or with a code under
    # 400, arriving on a 5xx must still fail. `JOBVITE-CONTRACT.md` §3.2
    # records that a status block with a code under 400 has never been
    # observed, so this arm is what covers the shape we cannot rule out.
    if http_status >= ERROR_STATUS_THRESHOLD:
        raise JobviteUpstreamError(http_status, _envelope_message(payload))

    return payload


def _envelope_status_code(payload: Mapping[str, Any]) -> int | None:
    """Return `status.code` if the body carries one, else `None`.

    `None` and a code under 400 are different answers and are kept
    apart: `JOBVITE-CONTRACT.md` §3.2 records that no success body has
    ever been observed, so whether a success carries a `status` block at
    all is unknown (checklist row §13.1). Both are tolerated, and
    neither is treated as an error by this function.
    """
    status = payload.get("status")
    if not isinstance(status, Mapping):
        return None
    code = status.get("code")
    # `bool` is an `int` in Python, and `{"code": true}` is not a status
    # code.
    if isinstance(code, bool) or not isinstance(code, int):
        return None
    return code


def _envelope_message(payload: Mapping[str, Any]) -> str:
    """Join Jobvite's own `status.messages` into one line for `detail`.

    Jobvite's message is preserved rather than discarded -
    DESIGN.md:592-594 puts it in `detail` - but it never reaches the
    problem object's `status`, which comes from the registry
    (`errors.py`).
    """
    status = payload.get("status")
    if not isinstance(status, Mapping):
        return "no message"
    messages = status.get("messages")
    if isinstance(messages, str):
        return redact_text(messages)
    if isinstance(messages, list) and messages:
        return redact_text("; ".join(str(m) for m in messages))
    return "no message"


def _decode_json_object(http_status: int, body: bytes) -> dict[str, Any]:
    """Decode the body as a JSON object, or raise the right typed error.

    **This is the "cannot assume JSON, cannot dispatch on content type"
    half** (DESIGN.md:347-349). Dispatch is on the bytes themselves,
    because the v1 `jobFeed` 401 sends no `Content-Type` header at all
    (`JOBVITE-CONTRACT.md` §3.3), so a content-type dispatch has nothing
    to read on exactly the route that needs it most.

    Every non-JSON encoding is an ERROR. That is not an assumption: v2
    speaks JSON on success, so plain text, HTML and XML are all failure
    shapes, and the two synthetic malformed fixtures must fail loudly
    here rather than degrade to an empty result.
    """
    text = body.decode("utf-8", errors="replace").strip()

    if text.startswith("<"):
        # Markup: the Tomcat HTML page, or HR-XML. Neither is ever a
        # success.
        _raise_from_markup(http_status, text)

    try:
        payload = json.loads(text)
    except ValueError:
        # Plain text with no Content-Type - the recorded v1 `jobFeed`
        # 401 - and the synthetic malformed bodies. FAIL LOUDLY:
        # returning `{}` here is precisely the "wrong zero" this module
        # exists to prevent.
        raise JobviteUpstreamError(
            _upstream_status_or_none(http_status), _excerpt(text)
        ) from None

    if not isinstance(payload, dict):
        # Valid JSON that is not an object: `null`, a bare list, a
        # number. No Jobvite route is documented to return one, and
        # `payload["status"]` would raise a TypeError several frames
        # away from the cause.
        raise JobviteUpstreamError(
            _upstream_status_or_none(http_status),
            f"expected a JSON object, got {type(payload).__name__}",
        )

    return payload


def _raise_from_markup(http_status: int, text: str) -> NoReturn:
    """Treat any markup body as an error, parsing XML with `defusedxml`.

    **HR-XML is a hardened fallback, not a handled case**
    (DESIGN.md:349-352). It appears on `/v1/candidate`, which we do not
    call. So this function's job is not to support XML - it is to make
    sure that if XML ever does arrive, the parse that touches it cannot
    be turned into a denial of service by entity expansion, and that
    whatever comes out is reported as a failure.

    `defusedxml` raising is a SUCCESSFUL outcome for us: it means the
    document carried a DTD, an external entity or an entity bomb, and we
    declined to expand it. Either way the caller gets a
    `JobviteUpstreamError`; the only difference is how much detail we
    can honestly put in it.
    """
    detail = _excerpt(text)
    try:
        root = defused_fromstring(text)
    except (DefusedXmlException, SyntaxError):
        # Not well-formed XML (the Tomcat HTML page), or defused_etree
        # refused it (a DTD or an entity bomb). Both are errors and
        # neither is parsed further. The body excerpt is redacted and
        # truncated, never trusted.
        raise JobviteUpstreamError(
            _upstream_status_or_none(http_status), detail
        ) from None

    # Well-formed XML. Pull the HR-XML `<Error code="N">` shape if it is
    # there; anything else still ends as an error, just with a vaguer
    # detail.
    error = root.find(".//Error")
    if error is not None:
        code = error.get("code")
        message = (error.text or "").strip() or detail
        raise JobviteUpstreamError(
            int(code) if code is not None and code.isdigit() else None,
            redact_text(message),
        )
    raise JobviteUpstreamError(_upstream_status_or_none(http_status), detail)


def _upstream_status_or_none(http_status: int) -> int | None:
    """Report the HTTP status only when it actually indicates a failure.

    `JobviteUpstreamError(None, ...)` renders as "Jobvite returned
    status none", which is the honest thing to say about a body that
    failed to decode on an HTTP 200: Jobvite reported no failing status
    anywhere, and claiming it returned 200 as though 200 were the error
    would invert the meaning of the field.
    """
    return http_status if http_status >= ERROR_STATUS_THRESHOLD else None


def _excerpt(text: str) -> str:
    """Bound and redact a body before it reaches a message or log.

    Both halves matter. `redact_text` is `utils/redaction.py`'s
    exception-message arm (DESIGN.md:315-318): an error body can quote
    back the request URL, and on the `jobFeed` route that URL carries
    `sc=`. Truncation bounds a body we do not control.
    """
    redacted = redact_text(text)
    if len(redacted) <= MAX_BODY_EXCERPT_CHARS:
        return redacted
    return redacted[:MAX_BODY_EXCERPT_CHARS] + "... [truncated]"


# ======================================================================
# U6 - PAGING. Base-agnostic offset scanning around `request` below.
#
# THE WHOLE MECHANISM IS ONE CHARACTER (DESIGN.md:494-503): every scan
# starts at `start=0`. A 0-based server returns record zero; a 1-based
# server returns the same first page it would have returned anyway.
# Starting at 1 is the only choice that can silently lose a record.
#
# WHAT IS OBSERVED, and it is narrower than the design's own first
# sentence. DESIGN.md:490 says `start` is 1-based *per Jobvite's own v1
# documentation, which is the only statement from the vendor*. That is
# a VENDOR CLAIM. The observation is `JOBVITE-API.md:399`: `start=0` is
# accepted and returns records, in one genuine `200`. That falsifies
# "1-based and strict" and separates nothing else - "0-based" and
# "1-based with clamping" both remain live, and `start=0` is safe under
# both, which is the point of being base-agnostic.
#
# WHY DE-DUPLICATION IS NOT THE SAFETY MECHANISM (DESIGN.md:504-507).
# The seen set defends against OVER-reading only. Under the
# 1-based-with-clamping hypothesis `start=0` is clamped to 1, so
# advancing by `count` re-reads one boundary record per page and the
# seen set drops it. It CANNOT recover a record that was never
# returned, "which is exactly why the fix is starting at 0 rather than
# de-duplicating harder". Moving the start to 1 and trusting the seen
# set loses record zero on a 0-based server, silently, forever.
#
# WHY THE ADVANCE IS `+= count` FROM 0 AND NOT FROM A DECLARED BASE. It
# is gap-free under both surviving hypotheses:
#   0-based:            page 1 = records 0..count-1, next start = count
#   1-based + clamping: page 1 = records 1..count,   next start = count
#                       -> record `count` arrives twice, the seen set
#                          drops one copy, and NO record is skipped.
# Advancing from a declared base of 1 would skip record `count` on a
# 0-based server, which is the loss this whole section exists to avoid.
# ======================================================================

#: The v2 transport page cap (DESIGN.md:473). **Not observed.** No call
#: in our evidence requested more than 5 records, so whether 500 is a
#: real server limit is unknown; it is the design's figure, and this
#: constant is where a measurement would land.
V2_PAGE_CAP: Final = 500

#: The `/v1/jobFeed` transport page cap (DESIGN.md:473). Unobserved for
#: the same reason as `V2_PAGE_CAP`.
JOBFEED_PAGE_CAP: Final = 1000

#: `JOBVITE_MAX_RESULTS`, the CONFIGURED half of
#: `min(transport_cap, configured_result_cap)` (DESIGN.md:473-475,
#: DESIGN.md:1653-1656). 50 agrees with the `showing 50 of 1,240`
#: string a caller already reads, which makes it internally consistent
#: and NOT a measurement of anything.
DEFAULT_MAX_RESULTS: Final = 50

#: THE SCAN'S RECORD CEILING, and it is in RECORDS rather than in pages
#: DELIBERATELY - ADR-0024, **Accepted 2026-08-29**, whose ruling
#: settles exactly this point (R5-H2).
#:
#: **The ADR's own text proposes a `MAX_PAGES` and, two sections
#: later, requires that any bound be "sane at both 50 and 500 records
#: per page". Those cannot both hold, and the ruling corrects the ADR
#: in favour of records.** A `MAX_PAGES = 10_000` admits 500,000
#: records at the 50-record page size and 5,000,000 at the 500-record
#: one - a tenfold difference in the resource actually at risk,
#: decided by a knob the ceiling cannot see. A ceiling in RECORDS is
#: sane at both page sizes by construction, because records are what
#: memory is spent on.
#: `scripts/probe-scan-bounds.py` measures both halves of that: equal
#: records held at the two page sizes, a tenfold difference in requests.
#:
#: **It is NOT `total` and does not read `total`** (DESIGN.md:525-526),
#: so the clause that "`total` is reported and never trusted as a loop
#: condition" is intact. It is a constant of ours.
#:
#: 100,000 IS A CHOICE AND NOT A MEASUREMENT, and the two arguments
#: that would make it look like one are both WRONG here - the rescued
#: draft of this comment made both, and they are corrected rather than
#: repeated:
#:
#: * **Not "above the largest scan the outbound budget could
#:   complete".** The budget bounds WALL CLOCK, and the probe measured
#:   a scan issuing 2,001 requests inside a TWO-SECOND budget without
#:   it firing once.
#:   The budget does not bound the request count at all, which is the
#:   ADR's load-bearing point; it cannot be what sizes this.
#: * **Not "5.5 hours at 6/min".** `JOBVITE_OUTBOUND_RATE_LIMIT`
#:   (DESIGN.md:1657-1662) is a documented default whose self-throttle
#:   is NOT IMPLEMENTED (task #43 measured its absence). Sizing a
#:   ceiling against machinery that does not exist is sizing it
#:   against nothing.
#:
#: What it IS sized against is the resource: DESIGN.md:513 records the
#: largest real one as `showing 50 of 1,240`, so 100,000 is roughly
#: eighty times the biggest scan this project has ever named, and no
#: legitimate scan comes near it. What it COSTS when it does fire is
#: bounded and stated at both page sizes the ADR requires: **2,000
#: requests at 50 records per page, 200 at 500**, and 100,000 records
#: held in memory in either case. That last figure is the ceiling's real
#: subject - the failure it prevents is the process dying, not the
#: request count, which the zero-progress break already covers on the
#: only shape that can produce it cheaply.
MAX_SCAN_RECORDS: Final = 100_000

#: Where every scan starts (DESIGN.md:494). Named rather than inlined
#: so a future edit is a visible one-line diff with this comment
#: attached, instead of a `0` quietly becoming a `1` inside a call.
SCAN_START: Final = 0

#: The envelope key carrying the full result-set size.
#: `JOBVITE-API.md:398`: `total` is the size of the whole result set,
#: not of the page - a call requesting 5 reported a `total` in the
#: hundreds of thousands. It is REPORTED and never a loop condition
#: (DESIGN.md:525-526).
TOTAL_KEY: Final = "total"

#: The default per-record identifier. `eId` is an opaque 8-character
#: id, which is why completeness is a COUNT against `total` and not a
#: search for a hole (DESIGN.md:508-511).
DEFAULT_ID_KEY: Final = "eId"


class ScanResult:
    """One scan's records, and what a caller must not re-derive.

    Carried as an object rather than a bare list because three of these
    fields are the difference between a capped answer and an anomaly,
    and a caller handed only `items` has to guess which it is holding.
    """

    __slots__ = (
        "capped",
        "duplicates_dropped",
        "exhaustive",
        "incomplete",
        "items",
        "pages",
        "total",
        "unidentified",
    )

    def __init__(
        self,
        *,
        items: list[dict[str, Any]],
        total: int | None,
        pages: int,
        duplicates_dropped: int,
        unidentified: int,
        capped: bool,
        exhaustive: bool,
        incomplete: bool,
    ) -> None:
        """Record one scan.

        Args:
            items: The de-duplicated records, in arrival order.
            total: The envelope's `total`, reported and never trusted
                as a loop condition (DESIGN.md:525-526). `None` when
                no page carried one.
            pages: How many requests the scan issued.
            duplicates_dropped: Records the seen set rejected. Under
                the clamping hypothesis this is about one per page
                after the first, so a non-zero value is normal rather
                than alarming.
            unidentified: Records carrying no id. They are KEPT and
                never de-duplicated: collapsing them onto a single
                `None` key would delete real records, which is the
                over-reading defence causing the under-read it exists
                to prevent.
            capped: The scan stopped because it reached its limit.
            exhaustive: The caller requested no limit.
            incomplete: The completeness check fired. Only ever `True`
                on an exhaustive scan (DESIGN.md:508-516).
        """
        self.items = items
        self.total = total
        self.pages = pages
        self.duplicates_dropped = duplicates_dropped
        self.unidentified = unidentified
        self.capped = capped
        self.exhaustive = exhaustive
        self.incomplete = incomplete


# ======================================================================
# The client. One request entry point, feeding the invariant above.
# ======================================================================


# ======================================================================
# U7 - RESILIENCE (DESIGN.md:354-370, :373-375, :617).
#
# THE COMPOSITION ORDER IS FIXED AND IT IS NOT A PREFERENCE.
# `backend/resilience.md:216-222` states it innermost to outermost:
#
#     timeout (innermost) -> retry -> circuit breaker (outermost)
#
# and gives the reason the order matters: "the breaker wraps the retried
# call, so retries count toward the breaker and a tripped breaker
# short-circuits BEFORE any retry budget is spent. Never let a retry
# loop sit outside the breaker - that lets retry storms defeat the
# breaker and keep hammering a down upstream." `_attempt` below is the
# timeout, `_attempt_with_retry` is the retry, and `_through_breaker`
# wraps both.
#
# THE TOTAL OUTBOUND BUDGET EXISTS BECAUSE THE CLAUSE IT DISCHARGES HAS
# NO REFERENT HERE. `backend/resilience.md:74-76` requires timeouts
# "shorter than the inbound request's own deadline". DESIGN.md:386-390
# records that MCP gives us no inbound deadline to be shorter than -
# there is no HTTP request worker to hang and no caller-supplied
# timeout - so DESIGN.md:392-394 supplies the deadline the transport
# does not: "a total outbound budget, configured, that bounds all
# attempts for one tool invocation, so a slow Jobvite surfaces as a
# typed 503 rather than an unbounded wait".
#
# **`config.py`'s `outbound_rate_limit` is NOT this and cannot be made
# into it.** A rate limit is requests per minute; a budget is a time
# bound on one invocation. Six requests per minute is satisfied
# perfectly by one request that never returns.
# ======================================================================

#: `JOBVITE_OUTBOUND_BUDGET_SECONDS`. The total wall-clock bound on ALL
#: outbound attempts for one tool invocation (DESIGN.md:392-394).
#:
#: **60 is a choice, not a measurement**, and it is recorded as one for
#: the same reason DESIGN.md:1657-1662 records the 6/min rate limit as a
#: guess. No Jobvite response-time distribution has ever been observed
#: on this project, so there is nothing to derive a percentile from. It
#: is sized to be comfortably longer than one 30-second read timeout
#: plus a retry, and short enough that an MCP host does not appear hung.
DEFAULT_OUTBOUND_BUDGET_SECONDS: Final = 60.0

#: The per-phase timeouts (DESIGN.md:358, and
#: `backend/resilience.md:67-70`).
#: **Explicit and per-phase: no SDK default and no single scalar.**
#: httpx2's own default is a 5-second scalar, which is a resilience
#: decision made by a library rather than by us.
DEFAULT_CONNECT_TIMEOUT: Final = 5.0
DEFAULT_READ_TIMEOUT: Final = 30.0
DEFAULT_WRITE_TIMEOUT: Final = 30.0
DEFAULT_POOL_TIMEOUT: Final = 5.0

#: The attempt cap, the other half of `backend/resilience.md:88-90`'s
#: "cap BOTH the maximum attempt count AND the total elapsed time". The
#: elapsed-time half is the outbound budget above, so the two `stop`
#: conditions are OR-ed.
#:
#: **NOT CONFIGURABLE, and this comment used to name an environment
#: variable that does not exist.** It cannot name it again even to say
#: so - the checker matches literals, so an explanation that quotes the
#: invented name reproduces the finding it is explaining. Measured: the
#: first version of this comment left the checker at four findings.
#:
#: The frozen design names no variable
#: for it - unlike the budget at DESIGN.md:392-394, which says
#: "configured" and now is. Naming a variable is the design's call:
#: §U9 records a whole unit that was UNBUILDABLE because three
#: variables had no names, and a reviewer's guesses were correctly not
#: adopted on that basis. Inventing one in a comment is that defect
#: from the other side - a knob an operator can set and nothing reads.
#: Making it configurable is an ADR, not an edit.
DEFAULT_RETRY_MAX_ATTEMPTS: Final = 4

#: Backoff, exponential WITH jitter (`backend/resilience.md:79-82`):
#: "fixed-interval or jitter-free retries synchronize clients into a
#: thundering herd that amplifies the outage".
DEFAULT_RETRY_INITIAL_BACKOFF: Final = 0.2
DEFAULT_RETRY_MAX_BACKOFF: Final = 5.0

#: The figures in `backend/resilience.md:180-181`'s worked example,
#: taken as-is because nothing about Jobvite's availability has been
#: observed that would justify moving them.
#:
#: **NOT CONFIGURABLE.** These two constants each carried an invented
#: environment-variable name in this comment, neither of which exists
#: and neither of which the frozen design names. The names are not
#: repeated here, for the reason given on the retry cap above: an
#: invented variable is a knob that does nothing, and quoting it keeps
#: it findable as though it were real.
DEFAULT_BREAKER_FAILURE_THRESHOLD: Final = 5
DEFAULT_BREAKER_RECOVERY_SECONDS: Final = 30.0

#: Jobvite's rate-limit status. **Never observed** (DESIGN.md:373-382):
#: "no 429 has ever been observed and no rate-limit header is returned,
#: so this path is written defensively and is unexercised" - against
#: Jobvite. It IS exercised by this project's tests.
RATE_LIMITED_STATUS: Final = 429

#: The floor for a server-side failure. `ERROR_STATUS_THRESHOLD` (400)
#: is the invariant's floor and a DIFFERENT quantity: everything at or
#: above 400 is an error, and only what is at or above 500 is OURS to
#: retry. `backend/resilience.md:92-94`: "4xx validation, auth, and
#: permission errors are not retryable and must surface immediately".
SERVER_ERROR_STATUS_FLOOR: Final = 500

#: The methods a retry may re-issue. **THIS IS HOW `create_candidate` IS
#: EXCLUDED FROM RETRY BY CONSTRUCTION** (DESIGN.md:362-365), and the
#: word "construction" is load-bearing: there is no setting that adds
#: `POST` to this set, no tool-name allow-list to keep in step with
#: `tools/`, and a tool added tomorrow that writes is excluded the
#: moment it is written rather than the moment somebody remembers to
#: list it. A hand-kept list of exempt tool names would be blind to the
#: tool nobody added to it.
#:
#: DESIGN.md:362-365 records the measurement this prevents: **one call,
#: four rows created**, when FastMCP's `RetryMiddleware` retried a write
#: that had already succeeded. That is why the case for this asserts a
#: ROW COUNT at the transport rather than reading a configuration value.
RETRYABLE_METHODS: Final = frozenset({"GET", "HEAD"})

#: The `retry_after` hint on an open breaker (DESIGN.md:368-370). It is
#: the breaker's own remaining open window, so it is computed rather
#: than constant - see `_breaker_retry_after`.
UNAVAILABLE_BREAKER_DETAIL: Final = (
    "We have stopped calling Jobvite because it has been failing. "
    "This is an open circuit breaker, not an upstream failure in flight."
)
#: This module's own claim to a coverage role from DESIGN.md:1443-1445,
#: read by `docs/reviews/check-coverage-floors.py`. The design names the
#: roles and not the paths, and the claim lives HERE rather than in a
#: role-to-module map in the checker, which would be a hand-kept list
#: beside its container. The checker asserts the two sets are EQUAL.
COVERAGE_ROLE: Final = "the Jobvite client"

UNAVAILABLE_BUDGET_DETAIL: Final = (
    "The total outbound time budget for this invocation was exhausted "
    "before Jobvite answered. This is a bound we applied, not an open "
    "circuit breaker."
)
UNAVAILABLE_RATE_LIMITED_DETAIL: Final = (
    "Jobvite rate-limited this request and it did not recover within the "
    "retry budget. This is an upstream failure, not an open circuit breaker."
)

#: THE BUDGET'S CARRIER, and it is a `ContextVar` for the same reason
#: `request_id_var` is (DESIGN.md:668-672): `asyncio` runs invocations
#: concurrently on one thread, and a module global would let two
#: invocations share one deadline - the first to start would bound the
#: second, and the corruption would be silent because every call still
#: gets *a* deadline.
#:
#: It holds a `monotonic()` deadline rather than a duration, so it stays
#: correct across the arbitrary number of `request` calls one scan
#: makes. `monotonic` rather than wall clock: a budget must not move
#: when NTP does.
outbound_deadline_var: ContextVar[float | None] = ContextVar(
    "outbound_deadline_var", default=None
)


@contextmanager
def outbound_budget_scope(
    seconds: float = DEFAULT_OUTBOUND_BUDGET_SECONDS,
) -> Iterator[float]:
    """Bound every outbound attempt in this scope to `seconds` total.

    **This is what DESIGN.md:392-394 promises and what nothing in `src/`
    implemented until now.** One scope per tool invocation: the deadline
    it sets is shared by every `request` beneath it, including the many
    a `scan` makes, which is the difference between a budget and a
    per-call timeout.

    **An already-open scope is NOT restarted.** A nested scope keeps the
    outer deadline, because an inner scope that reset the clock would
    turn one invocation's budget into a per-page budget and the bound
    would be `pages x seconds` - unbounded in exactly the direction this
    exists to bound. The `finally` resets the token so a deadline cannot
    leak into the next invocation on a reused worker task, which is the
    leak `correlation.request_id_scope` documents for the id.

    Args:
        seconds: The total budget. `JOBVITE_OUTBOUND_BUDGET_SECONDS`.

    Yields:
        The `monotonic()` deadline in force for this scope - the outer
        one if a scope was already open.
    """
    existing = outbound_deadline_var.get()
    deadline = existing if existing is not None else monotonic() + seconds
    token = outbound_deadline_var.set(deadline)
    try:
        yield deadline
    finally:
        outbound_deadline_var.reset(token)


def outbound_budget_remaining() -> float | None:
    """Seconds left in the current budget, or `None` if none is open.

    Returns:
        The remaining seconds, which may be zero or negative when the
        budget is spent, or `None` when no scope is open. `None` and a
        remaining `0.0` are kept apart deliberately: "no budget" and "no
        budget left" are opposite conditions and collapsing them would
        make an unscoped call look exhausted.
    """
    deadline = outbound_deadline_var.get()
    if deadline is None:
        return None
    return deadline - monotonic()


class JobviteRetryLaterError(JobviteUnavailableError):
    """A 503 that carries RFC 9457's `retry_after` extension member.

    **No new type URI is minted** (DESIGN.md:367-370): `kind` is
    inherited, so an open breaker, an exhausted budget and a 429 all
    still answer `/problems/service-unavailable` at 503. What
    distinguishes them is `detail`, exactly as the design requires. This
    subclass exists only to carry the hint, which `errors.build_problem`
    already accepts as an extension member and which nothing previously
    produced.

    **`counts_toward_breaker` is a property of the CAUSE, not of the
    status.** A 429 is Jobvite telling us it is unwell and counts. An
    exhausted budget is a bound WE applied and must not: a slow call we
    abandoned says nothing about Jobvite's health that its own timeout
    has not already said, and counting it would let one slow invocation
    trip a breaker for every other caller.
    """

    def __init__(
        self,
        detail: str,
        *,
        retry_after: float | None = None,
        counts_toward_breaker: bool = False,
    ) -> None:
        """Record the hint and whether this failure is an outage signal.

        Args:
            detail: The occurrence-specific explanation, which is what
                distinguishes this 503 from the other two.
            retry_after: Seconds the caller should wait, when we have a
                defensible number. `None` when we do not - an invented
                hint is worse than none.
            counts_toward_breaker: Whether the breaker should count this
                as a failure.
        """
        super().__init__(detail)
        self.retry_after = retry_after
        self.counts_toward_breaker = counts_toward_breaker


class _RetryableUpstream(Exception):  # noqa: N818 - private, never surfaces
    """A 5xx or 429, wrapped so `tenacity` can select on it alone.

    **Module-private, with exactly TWO exits, both in
    `_attempt_with_retry`.** `_attempt` raises it whatever the method;
    the non-retrying branch converts it immediately and the retrying
    branch converts it the moment retries are exhausted. Those are the
    only two conversion sites, and they are named rather than counted by
    a grep, because every grep short enough to write here also matches
    this sentence - which is the tautological-control shape R6-M2 found
    one file over.

    The sentence this replaces said only that it "never reaches a
    caller", and it did: there was one converter, not two, so a POST
    meeting a 5xx raised this class out of `request()` and the caller
    was told `/problems/internal-error` 500. R6-H2 measured it.

    It exists because the retry predicate has to separate a 5xx from a
    4xx, and both arrive as `JobviteUpstreamError` - which is correct
    for the caller and useless as a selector.
    """

    def __init__(self, cause: JobviteUpstreamError, retry_after: float | None) -> None:
        """Wrap the public error and Jobvite's own `Retry-After`.

        Args:
            cause: The typed error this becomes if retries run out.
            retry_after: The parsed `Retry-After` value, if any.
        """
        super().__init__(str(cause))
        self.cause = cause
        self.retry_after = retry_after

    def public_error(self) -> JobviteUpstreamError | JobviteRetryLaterError:
        """Convert to what the caller is allowed to see.

        **THE NON-429 BRANCH CARRIES THE HINT TOO** (ADR-0030, R11-H1).
        It used to `return self.cause` untouched, so a 5xx arriving
        with a `Retry-After` we could not afford surfaced as a 502 with
        the hint discarded - the shape the ADR is titled after. The
        value assigned is `self.retry_after`, which is
        `_retry_after_seconds(response.headers)` and nothing else: only
        what Jobvite actually sent, never a number we worked out. When
        Jobvite sent none it stays `None`, which means *we were not
        told* and not *do not retry*.

        Returns:
            A `JobviteRetryLaterError` (503) for a 429, honouring
            `Retry-After` - DESIGN.md:373-382 says a 429 is "retried and
            then mapped to 503, honouring `Retry-After` when present" -
            and the original `JobviteUpstreamError` (502) otherwise,
            now carrying the same hint when the upstream sent one.
        """
        if self.cause.upstream_status == RATE_LIMITED_STATUS:
            return JobviteRetryLaterError(
                UNAVAILABLE_RATE_LIMITED_DETAIL,
                retry_after=self.retry_after,
                counts_toward_breaker=True,
            )
        self.cause.retry_after = self.retry_after
        return self.cause


def _is_retryable_status(status: int | None) -> bool:
    """Whether an upstream status is ours to retry.

    Args:
        status: The status Jobvite reported, from the HTTP line or from
            its own JSON envelope. `None` means it reported none.

    Returns:
        `True` for a 429 or any 5xx. **`None` is `False`**: a body that
        failed to decode on an HTTP 200 is not a transient condition and
        re-issuing the call would return the same undecodable body.
    """
    if status is None:
        return False
    return status >= SERVER_ERROR_STATUS_FLOOR or status == RATE_LIMITED_STATUS


def _retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    """Parse `Retry-After`, seconds form only.

    `backend/resilience.md:95-97` requires honouring it. Only the
    delta-seconds form is parsed: the HTTP-date form would need a clock
    comparison against a server whose clock we have never observed, and
    a wrong date silently becomes a wrong wait.

    **A zero is FLOORED, not trusted and not rejected.** `0` is `>= 0`,
    so it used to be returned verbatim and `_wait_for_retry` took it in
    preference to the jittered schedule - every retry then fired with no
    delay at all, which is `backend/resilience.md:79-82`'s stated
    failure ("fixed-interval or jitter-free retries synchronize clients
    into a thundering herd that amplifies the outage") produced on
    demand by a header value the UPSTREAM controls. Flooring honours
    the back-pressure without letting it switch jitter off.

    Args:
        headers: The response headers.

    Returns:
        The delay in seconds, never below
        `DEFAULT_RETRY_INITIAL_BACKOFF`, or `None` if the header is
        absent, not a number, or negative.
    """
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        value = float(raw.strip())
    except ValueError:
        return None
    return max(value, DEFAULT_RETRY_INITIAL_BACKOFF) if value >= 0 else None


class _RetryAfterExceedsBudget(stop_base):
    """A `tenacity` stop: the upstream asks for longer than we have.

    **THE CLAMP ALONE BOUGHT AN ATTEMPT `_attempt` REFUSES** (R6-M1).
    `min(900, remaining)` **is** `remaining`, so honouring a
    `Retry-After` larger than the budget slept the budget to zero and
    the attempt it paid for was then rejected by `_attempt`'s own
    `remaining <= 0` check before the transport saw it. Measured at
    1.00s of a 1.0s budget by
    `docs/reviews/probe-r6-wait-burns-budget.py`, and it holds at any
    budget because the clamp always yields exactly `remaining`.

    **A stop, not a shorter sleep, and this too was measured.** The
    first fix returned `0.0` from `_wait_for_retry` on the reasoning
    that `stop_after_delay` would then fire on the next loop. It does
    not: `stop_after_delay` fires on ELAPSED time, so a zero wait
    advances the clock by nothing and the loop instead burns the whole
    attempt cap back to back - hammering an upstream that had just
    asked us to wait fifteen minutes, which is the opposite of
    `backend/resilience.md:95-97`. Stopping here ends the call after the
    attempt that carried the header, with no further request, and the
    conversion in `_attempt_with_retry` surfaces the 429's own
    `Retry-After` to the caller.

    **A `stop_base` subclass rather than a bare function** because
    `stop_base.__or__` is what composes the three arms, and `|` on a
    plain callable is not that operator.
    """

    def __call__(self, retry_state: RetryCallState) -> bool:
        """Whether to stop before taking a wait we cannot afford.

        Args:
            retry_state: `tenacity`'s state for the failed attempt.

        Returns:
            `True` when the last attempt carried a `Retry-After` we
            cannot afford. `False` when there is no header, or no
            budget scope - the other two stop arms still apply.
        """
        outcome = retry_state.outcome
        exc = outcome.exception() if outcome is not None else None
        if not isinstance(exc, _RetryableUpstream) or exc.retry_after is None:
            return False
        remaining = outbound_budget_remaining()
        return remaining is not None and exc.retry_after >= remaining


#: The singleton of the arm above. One instance: it holds no state.
_retry_after_exceeds_budget: Final = _RetryAfterExceedsBudget()


def _is_outage(_exc_type: type[BaseException], exc: BaseException) -> bool:
    """The breaker's predicate. **4xx MUST NOT trip it** (§8 #23).

    DESIGN.md:366-367: "one circuit breaker for Jobvite. 4xx must not
    trip it - a bad candidate id is the caller's problem, not a health
    signal." `backend/resilience.md:161-163` says the same and adds that
    this "mirrors the retry predicate above", which is why this function
    and `_is_retryable_status` agree on which statuses are outages.

    Args:
        _exc_type: The exception class, per `circuitbreaker`'s predicate
            signature. Unused: the instance carries everything needed
            and dispatching on the class alone cannot see a status.
        exc: The exception that left the wrapped call.

    Returns:
        `True` when this failure is evidence that Jobvite is unwell.
    """
    if isinstance(exc, JobviteRetryLaterError):
        return exc.counts_toward_breaker
    if isinstance(exc, JobviteUnavailableError):
        # Every transport failure: connect, read, write, pool, protocol.
        return True
    if isinstance(exc, JobviteUpstreamError):
        return _is_retryable_status(exc.upstream_status)
    return False


#: **ONE breaker for Jobvite** (DESIGN.md:366, B37,
#: `backend/resilience.md:156-159`: "one breaker per dependency ...
#: never a single global breaker"). Jobvite is this server's only
#: outbound dependency, so one module-level instance IS one per; a
#: second dependency would get its own rather than share this.
#:
#: **Module level rather than per client instance, deliberately.** The
#: breaker's job is to record what the DEPENDENCY has been doing, and a
#: per-instance breaker would forget everything each time a client was
#: rebuilt - which is once per invocation in the shapes `tools/` uses.
#: `backend/resilience.md:196-200` records the corresponding limit: the
#: state is in-process and per-replica, so on N replicas each observes
#: the threshold independently.
_JOBVITE_BREAKER: Final = CircuitBreaker(
    failure_threshold=DEFAULT_BREAKER_FAILURE_THRESHOLD,
    recovery_timeout=DEFAULT_BREAKER_RECOVERY_SECONDS,
    expected_exception=_is_outage,
    name="jobvite",
)

#: The last breaker state a transition line was written for. A
#: transition is a CHANGE, so reporting one needs the previous value,
#: and `circuitbreaker` exposes state but no transition hook.
_breaker_reported_state: str = _JOBVITE_BREAKER.state


def reset_breaker_for_test() -> None:
    """Return the module breaker to closed - **tests only**.

    The breaker is module state on purpose (see `_JOBVITE_BREAKER`), and
    module state that survives between tests makes case order
    load-bearing: one case tripping it would fail the next for a reason
    that has nothing to do with the next case. Shipped code never calls
    this - an operator wanting a closed breaker restarts the process.
    """
    global _breaker_reported_state  # noqa: PLW0603 - the state IS module-level
    _JOBVITE_BREAKER.reset()
    _breaker_reported_state = _JOBVITE_BREAKER.state


def _breaker_retry_after() -> float | None:
    """The breaker's remaining open window, as a `retry_after` hint.

    Returns:
        Seconds until the breaker will admit a probe, or `None` when it
        is not open. `circuitbreaker` returns an already-rounded int.
    """
    remaining = _JOBVITE_BREAKER.open_remaining
    return float(remaining) if remaining > 0 else None


def _report_breaker_state() -> None:
    """Log a breaker transition **if one happened**, on the call path.

    **This function IS the reason `circuitbreaker` had to evaluate
    expiry on the call path** (DESIGN.md:677). It reads
    `_JOBVITE_BREAKER.state`, which for an expired open window is a
    DERIVED read computed in this frame - so the `open->half_open` line
    is written by the invocation's own task, with its `request_id_var`
    bound. A library that flipped the state from a background timer
    would have written that line from a task with no id, logging `None`
    and failing §8 #13. `scripts/probe-breaker-call-path.py` is the
    measurement that settled this, and it is run as a test.

    The line carries the direction, the triggering counter and
    `request_id`, which is what `backend/resilience.md:224-226` and
    DESIGN.md:674-677 require. **It carries no URL**, for the same
    reason a retry line does not: the v1 `jobFeed` URL is itself a
    secret.
    """
    global _breaker_reported_state  # noqa: PLW0603 - the state IS module-level
    current = _JOBVITE_BREAKER.state
    if current == _breaker_reported_state:
        return
    logger.warning(
        "jobvite breaker transition",
        transition=f"{_breaker_reported_state}->{current}",
        failure_count=_JOBVITE_BREAKER.failure_count,
        request_id=request_id_var.get(),
    )
    _breaker_reported_state = current


#: Exponential backoff WITH jitter (`backend/resilience.md:79-82`).
#: Module level so `_wait_for_retry` composes it with `Retry-After`
#: rather than rebuilding it per attempt - `wait_exponential_jitter`
#: derives its delay from the attempt number on the state it is handed,
#: so one instance is correct for every call.
_JITTERED_BACKOFF: Final = wait_exponential_jitter(
    initial=DEFAULT_RETRY_INITIAL_BACKOFF, max=DEFAULT_RETRY_MAX_BACKOFF
)


def _should_retry(state: RetryCallState) -> bool:
    """`tenacity`'s predicate: re-issue this attempt, or surface it?

    **Never a blanket `except Exception`**
    (`backend/resilience.md:92-94`). Three things retry and nothing
    else does:

    * `_RetryableUpstream` - a 429 or a 5xx, already classified by
      `_attempt` where the response was still in scope;
    * `JobviteUnavailableError` - every transport failure httpx2 raises,
      which is DESIGN.md:359-361's "connection errors, timeouts";
    * and **not** `JobviteRetryLaterError`, which is the subclass this
      module raises for an open breaker and an exhausted budget. Both
      are fail-fast signals we produced ourselves.
      `backend/resilience.md:170-172` states the breaker half directly:
      "do NOT let `tenacity` retry a `CircuitBreakerError` - it is a
      fail-fast signal, not a transient error."

    A `JobviteUpstreamError` that reaches here is a 4xx or an
    undecodable body and surfaces immediately.

    Args:
        state: `tenacity`'s call state for the attempt just finished.

    Returns:
        `True` to retry.
    """
    if state.outcome is None or not state.outcome.failed:
        return False
    exc = state.outcome.exception()
    if isinstance(exc, JobviteRetryLaterError):
        return False
    return isinstance(exc, _RetryableUpstream | JobviteUnavailableError)


def _log_retry_attempt(state: RetryCallState) -> None:
    """Log one retry at WARNING, carrying `request_id` and **no URL**.

    `backend/resilience.md:224-226`: "log every retry attempt (at
    WARNING) ... each carrying the `request_id` correlation field. Never
    retry or trip silently." DESIGN.md:674-676 adds the fields: the
    attempt number, the elapsed delay and the exception type.

    **THE ABSENT FIELD IS THE LOAD-BEARING ONE.** No URL and no route
    appear here, because the v1 `jobFeed` URL carries `sc=` in its query
    string and is itself a secret (DESIGN.md:315-318, :618-620): "a
    retry line is exactly where an unredacted URL would otherwise reach
    a log". The exception is reduced to its CLASS NAME rather than its
    text for the same reason - httpx2 puts the request URL inside the
    message of the exceptions it raises.

    `request_id` is read from `request_id_var` rather than passed,
    because `tenacity` calls this hook, not our call site
    (DESIGN.md:661-663). It is a per-Task ContextVar, so two invocations
    retrying concurrently each read their own - which is §8 #13, and
    why that case runs two invocations in parallel rather than one.

    Args:
        state: `tenacity`'s call state for the attempt just finished.
    """
    exc = state.outcome.exception() if state.outcome is not None else None
    logger.warning(
        "jobvite retry",
        attempt=state.attempt_number,
        elapsed=round(state.seconds_since_start or 0.0, 3),
        error_type=type(exc).__name__ if exc is not None else "none",
        request_id=request_id_var.get(),
    )


class JobviteClient:
    """An `httpx2` client for Jobvite, with one request entry point.

    **`request` is the single method that issues one call, applies the
    invariant and returns a decoded body or raises the typed error**
    (`IMPLEMENTATION-PLAN.md:773-777`). Paging around it is U6's; U4
    owns the one-call path. Without this method U4 would be an
    auth-and-error module with no caller.

    ADR-0007 chose `httpx2`: `fastmcp 4.0.3` does not install `httpx`
    at all, and `httpx2` ships `MockTransport` in the box, which is what
    lets the credential-free test strategy add no third-party mocking
    library.
    """

    def __init__(
        self,
        *,
        api_key: SecretValue,
        api_secret: SecretValue,
        company_id: SecretValue | None = None,
        transport: httpx2.AsyncBaseTransport | None = None,
        timeout: httpx2.Timeout | None = None,
        max_results: int = DEFAULT_MAX_RESULTS,
        start_base_overrides: Mapping[str, int] | None = None,
        outbound_budget_seconds: float = DEFAULT_OUTBOUND_BUDGET_SECONDS,
        retry_max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS,
        install_log_redaction: bool = True,
    ) -> None:
        """Build the client.

        Args:
            api_key: The v2 `x-jvi-api` credential, and the v1 `api`
                parameter.
            api_secret: The v2 `x-jvi-sc` credential, and the v1 `sc`
                parameter.
            company_id: The job feed's separate credential
                (DESIGN.md:332-333). Required only for `jobFeed`, so it
                is optional here and the failure for a missing one is
                raised at the call.
            transport: Substituted in tests with `httpx2.MockTransport`
                (DESIGN.md:1440-1441, ADR-0007). `None` in production.
            timeout: Explicit and per-phase (DESIGN.md:358). **No SDK
                default and no single scalar**: `httpx2`'s own default
                is a 5-second scalar, which is a resilience decision
                made by a library rather than by us. The full
                retry/breaker ordering of DESIGN.md:354-370 is U7's;
                this is the timeout half, which cannot wait for it
                because the default it would otherwise inherit is
                silent.
            max_results: `JOBVITE_MAX_RESULTS`, the CONFIGURED half of
                `min(transport_cap, configured_result_cap)`
                (DESIGN.md:473-475). U5 applies the same figure
                in-tool in `tools/jobs.py` and owns the
                `showing N of total` string; this half bounds what
                leaves the transport, and neither unit owns all of it.
            start_base_overrides: `JOBVITE_PAGINATION_START_BASE`,
                **per resource and not global** (DESIGN.md:517-519),
                keyed by the same `path` a scan is given. Absent, every
                resource starts at `SCAN_START`. This exists for
                someone who has ESTABLISHED the base against a live
                tenant; it is not a place to write down the vendor's
                claim, because a declared 1 here loses record zero on a
                0-based server.
            outbound_budget_seconds: `JOBVITE_OUTBOUND_BUDGET_SECONDS`,
                the total wall-clock bound on ALL attempts for one tool
                invocation (DESIGN.md:392-394). Applied by `scan`, and
                by a bare `request` that finds no scope already open -
                see `outbound_budget_scope`.
            install_log_redaction: ADR-0026, option 1. Install the
                redaction filter on `httpx2`'s stdlib logger, so an
                EMBEDDER who never runs
                `__main__.configure_logging()` does not receive the
                `jobFeed` URL - `api`, `sc` and `companyId` - in the
                clear. **Defaults to installing**: a credential leak
                is a worse default than a surprising side effect, and
                an embedder who wants their logging untouched passes
                `False` here, which makes the exposure a choice they
                made rather than one they did not know about.

                **A constructor argument and NEVER a `Settings`
                field.** ADR-0025 is about a setting nothing reads;
                a second one is not the answer.
            retry_max_attempts: The attempt half of
                `backend/resilience.md:88-90`'s "cap BOTH the maximum
                attempt count AND the total elapsed time". The elapsed
                half is the budget above. A constructor argument only -
                NOT settable from the environment; see the constant's
                own note.
        """
        if install_log_redaction:
            # IDEMPOTENT by construction - see the function. This runs
            # once per invocation from three call sites, so an
            # unguarded `addFilter` here would stack one filter per
            # tool call for the life of the process.
            _install_log_redaction()
        self._api_key = api_key
        self._api_secret = api_secret
        self._company_id = company_id
        self._max_results = max_results
        self._start_base_overrides = dict(start_base_overrides or {})
        self._outbound_budget_seconds = outbound_budget_seconds
        self._retry_max_attempts = retry_max_attempts
        # KEPT ON THE INSTANCE so an attempt can be narrowed to what
        # remains of the outbound budget. `httpx2.Timeout` exposes the
        # four phases as attributes but rebuilding from the values we
        # were given is what lets `_attempt_timeout` clamp them without
        # depending on that shape.
        self._timeout = timeout or httpx2.Timeout(
            connect=DEFAULT_CONNECT_TIMEOUT,
            read=DEFAULT_READ_TIMEOUT,
            write=DEFAULT_WRITE_TIMEOUT,
            pool=DEFAULT_POOL_TIMEOUT,
        )
        self._client = httpx2.AsyncClient(
            transport=transport,
            timeout=self._timeout,
            # PINNED, not inherited. httpx2 2.12.0 happens to default
            # this False, so before this line the safety came from a
            # transitive default and nothing else - a review added
            # `follow_redirects=True` and all 294 tests stayed green.
            #
            # A 30x would forward `x-jvi-api` and `x-jvi-sc` to whatever
            # host the `Location` header names, and on the v1 jobFeed
            # route the credentials travel in the QUERY STRING, so a
            # redirect would hand them to a third party in a URL that
            # also lands in that host's access log.
            #
            # server.py states this project's own rule for exactly this
            # class: "a security-relevant default is exactly the kind of
            # thing that must be stated in our own source so a diff
            # shows it moving". It was applied to `mask_error_details`
            # and not here.
            follow_redirects=False,
        )

    async def __aenter__(self) -> Self:
        """Enter the client's context, closing the pool on exit."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the underlying transport."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying `httpx2` client."""
        await self._client.aclose()

    # -- authentication
    # -----------------------------------------------------

    def v2_headers(self) -> dict[str, str]:
        """Build the v2 request headers (DESIGN.md:312).

        `.get_secret_value()` is called **here and only here** for v2,
        which is DESIGN.md:335-336's "resolved only when building a
        request".

        Returns:
            The two credential headers plus `Accept`.
        """
        return {
            API_KEY_HEADER: self._api_key.get_secret_value(),
            API_SECRET_HEADER: self._api_secret.get_secret_value(),
            "Accept": "application/json",
        }

    def jobfeed_params(self) -> dict[str, str]:
        """Build the v1 `jobFeed` params - **the one exception**.

        DESIGN.md:315-318: this route structurally requires `api`, `sc`
        and `companyId` as query parameters, which is why its URL is
        classified sensitive. Every other route puts the credential in a
        header and DESIGN.md:312-313 forbids building a URL that
        contains one.

        Returns:
            The three credential parameters.

        Raises:
            RuntimeError: If no `company_id` was configured. Raised
                rather than sending the call without it, because Jobvite
                would answer a missing `companyId` with the same 401
                body as a bad credential and the operator would go
                looking for the wrong fault.

                **The TYPE is R2-L-4 and it was open until U7.** This
                used to raise `JobviteUpstreamError(None, ...)`, which
                `errors.py` maps to `/problems/external-service-error`
                **502** and renders as *"Jobvite returned status none:
                ..."*. Jobvite returned nothing; the call was never
                made. Telling a caller the upstream failed when the
                deployment is misconfigured is the same inversion
                DESIGN.md:553-560 corrects for Jobvite's own 401.

                `errors.py` has no configuration row and
                DESIGN.md:561-562 forbids minting a slug, so an
                exception outside the
                hierarchy is the honest answer: ADR-0017 routes it to
                `/problems/internal-error` **500** with the class name
                and not the message. **The review's own suggested fix
                said `about:blank`, and that text predates ADR-0017** -
                the slug moved, the diagnosis did not.
        """
        if self._company_id is None:
            msg = (
                "the jobFeed route requires a companyId credential and none is "
                "configured"
            )
            raise RuntimeError(msg)
        return {
            "api": self._api_key.get_secret_value(),
            "sc": self._api_secret.get_secret_value(),
            "companyId": self._company_id.get_secret_value(),
        }

    # -- the one request entry point
    # ---------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
        jobfeed: bool = False,
    ) -> dict[str, Any]:
        """Issue ONE call, apply the invariant, return the body.

        **The single request entry point.** One call, no paging - paging
        around this method is U6's (`IMPLEMENTATION-PLAN.md:775`).

        Args:
            method: The HTTP method.
            path: The path below the base URL, e.g. `/candidate`.
            params: Non-credential query parameters.
            json_body: A JSON request body, for POST routes.
            jobfeed: Select the v1 `jobFeed` route and its
                query-parameter authentication. **A `bool` rather than a
                free-form base URL**: the sensitive-URL path has to be
                one enumerated branch that a test can point at, not a
                value a caller can pass in.

        Returns:
            The decoded body, when both arms of the invariant hold.

        Raises:
            JobviteUpstreamError: On either arm of the invariant, or an
                undecodable body.
            JobviteUnavailableError: If Jobvite could not be reached at
                all, if the breaker is open, or if the outbound budget
                was exhausted. The three are one problem type and are
                told apart by `detail` (DESIGN.md:367-370).
        """
        if jobfeed:
            url = f"{V1_BASE_URL}{path}"
            headers = {"Accept": "application/json"}
            query = {**dict(params or {}), **self.jobfeed_params()}
        else:
            url = f"{V2_BASE_URL}{path}"
            headers = self.v2_headers()
            query = dict(params or {})

        # The ONLY log line on this path, and it names the route rather
        # than the URL. DESIGN.md:315-318 forbids the jobFeed URL
        # reaching a log whole, and `redact_url` is applied on top
        # rather than instead: the path is already credential-free for
        # v2, so this is belt and braces on the one route where a
        # mistake is unrecoverable.
        logger.debug(
            "jobvite request",
            method=method,
            route=redact_url(f"{V1_BASE_URL if jobfeed else V2_BASE_URL}{path}"),
        )

        # THE BUDGET, and the `if` is the whole of what makes it a
        # budget rather than a per-call timeout. A `scan` has already
        # opened the scope, so all 25 of its requests share ONE
        # deadline; a bare `request` opens its own so that a caller who
        # forgot still gets a bound rather than an unbounded wait.
        with outbound_budget_scope(self._outbound_budget_seconds):
            # THE BREAKER IS OUTERMOST and the retry sits INSIDE it
            # (`backend/resilience.md:216-222`). Reversing the two lets
            # a retry storm keep hammering an upstream the breaker has
            # already given up on.
            return await self._through_breaker(
                method,
                url,
                params=query,
                headers=headers,
                json_body=json_body,
                jobfeed=jobfeed,
                path=path,
            )

    async def _through_breaker(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str],
        headers: Mapping[str, str],
        json_body: Mapping[str, Any] | None,
        jobfeed: bool,
        path: str,
    ) -> dict[str, Any]:
        """The outermost layer: fail fast when Jobvite is known-down.

        Args:
            method: The HTTP method.
            url: The fully-built URL. Never logged.
            params: The query parameters, credentials included on the
                `jobFeed` route.
            headers: The request headers, credentials included on v2.
            json_body: The JSON body, for POST routes.
            jobfeed: Whether this is the v1 route, for the log line.
            path: The route below the base URL, for the log line.

        Returns:
            The decoded body.

        Raises:
            JobviteRetryLaterError: When the breaker is open. It is
                raised **before** the body executes, which is
                `backend/resilience.md:165-170`'s "surface it as a fast,
                typed error rather than letting calls queue against a
                known-down upstream".
        """
        # READ THE STATE FIRST. For an expired open window this read is
        # what computes the `open->half_open` transition, in this task,
        # with this invocation's `request_id_var` bound - see
        # `_report_breaker_state`.
        _report_breaker_state()
        if _JOBVITE_BREAKER.opened:
            raise JobviteRetryLaterError(
                UNAVAILABLE_BREAKER_DETAIL,
                retry_after=_breaker_retry_after(),
                counts_toward_breaker=False,
            )
        try:
            # THE CALL RUNS OUTSIDE THE BREAKER'S CONTEXT AND ITS
            # OUTCOME IS REPORTED AFTERWARDS. `CircuitBreaker.__exit__`
            # (`circuitbreaker.py:113-120`) has exactly two outcomes: an
            # exception its predicate ACCEPTS counts, and everything
            # else - a clean exit AND an exception the predicate
            # DECLINES - calls `reset()`, which sets `_failure_count =
            # 0` and `_state = CLOSED`.
            #
            # So wrapping the call in `with _JOBVITE_BREAKER:` cannot
            # express "this failure is not evidence": it can only say
            # "this call succeeded". Measured at 4 -> 0 by
            # `docs/reviews/probe-r6-breaker-reset.py`, with a 4 -> 5
            # control on a real outage. A 4xx, an exhausted budget and a
            # 429 that does not count each HEALED the breaker, so
            # traffic that mixes 4xx with outages could hold it closed
            # forever.
            #
            # NOT TRIPPING IT AND HEALING IT ARE DIFFERENT BEHAVIOURS
            # and DESIGN.md:366-367 asks for the first. Three outcomes
            # are needed and the context manager offers two, so the
            # third - NEUTRAL - is expressed by never entering it.
            result = await self._attempt_with_retry(
                method,
                url,
                params=params,
                headers=headers,
                json_body=json_body,
                jobfeed=jobfeed,
                path=path,
            )
        except CircuitBreakerError:
            # Defensive: the `opened` check above short-circuits first,
            # so reaching here would mean the breaker tripped between
            # the two statements. It is mapped rather than allowed to
            # escape, because `CircuitBreakerError` is not in
            # `errors.py`'s hierarchy and would surface as a 500.
            raise JobviteRetryLaterError(
                UNAVAILABLE_BREAKER_DETAIL,
                retry_after=_breaker_retry_after(),
                counts_toward_breaker=False,
            ) from None
        except Exception as exc:
            # `_is_outage` REMAINS THE SINGLE AUTHORITY on which
            # failures are signals; what changed is what a declined one
            # now costs. A declined failure never reaches the breaker at
            # all, so the counter it had is the counter it keeps, and a
            # breaker in `half_open` stays there rather than being
            # closed by a call that never reached Jobvite.
            #
            # `except Exception`, not `BaseException`: a
            # `CancelledError` is the caller going away and says nothing
            # about Jobvite, so it too must leave the breaker untouched
            # - which it does by not being caught here.
            if not _is_outage(type(exc), exc):
                raise
            # ACCEPTED: re-raised INSIDE the context so `__exit__` sees
            # it and counts it, which is the one thing the context
            # manager does that we want.
            with _JOBVITE_BREAKER:
                raise
        else:
            # A SUCCESS, and the only thing that may reset the counter.
            # An empty body is the honest spelling of "report a
            # success": `__exit__(None, None, None)` is exactly
            # `reset()`.
            with _JOBVITE_BREAKER:
                pass
            return result
        finally:
            # The `closed->open` and `half_open->closed` lines. Written
            # here rather than inside `__exit__`: `circuitbreaker`
            # exposes no transition hook - what it does expose is state
            # that is correct to read at any point on the call path.
            _report_breaker_state()

    async def _attempt_with_retry(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str],
        headers: Mapping[str, str],
        json_body: Mapping[str, Any] | None,
        jobfeed: bool,
        path: str,
    ) -> dict[str, Any]:
        """The middle layer: re-issue transient failures, or do not.

        **`create_candidate` is excluded here, BY CONSTRUCTION**
        (DESIGN.md:362-365). The `if` below dispatches on the HTTP
        METHOD, so a `POST` cannot be retried by any configuration,
        and the exclusion covers a write tool written next year that
        nobody remembered to add to a list. DESIGN.md:365 records what
        this prevents, measured: **one call, four rows created**.

        Args:
            method: The HTTP method. The retry decision reads this.
            url: The fully-built URL. Never logged.
            params: The query parameters.
            headers: The request headers.
            json_body: The JSON body, for POST routes.
            jobfeed: Whether this is the v1 route, for the log line.
            path: The route below the base URL, for the log line.

        Returns:
            The decoded body.

        Raises:
            JobviteUpstreamError: A 4xx immediately; a 5xx once the
                retry budget is spent.
            JobviteUnavailableError: A transport failure once the retry
                budget is spent, or an exhausted outbound budget.
        """
        if method.upper() not in RETRYABLE_METHODS:
            # ONE await, and no loop exists on this branch to run a
            # second one. That is the construction.
            #
            # THE CONVERSION IS HERE BECAUSE `_attempt` WRAPS A
            # RETRYABLE STATUS WHATEVER THE METHOD (see `:_attempt`'s
            # `raise _RetryableUpstream`), and this branch is the other
            # place that wrapper has to come off. Without it a POST
            # meeting a 5xx or a 429 raised the module-private type
            # straight out of `request()`, ADR-0017 routed it to
            # `/problems/internal-error` **500**, and the detail read
            # `An unexpected _RetryableUpstream occurred.` - the wrong
            # status, and a private class name reaching an API consumer,
            # which `backend/error-handling.md:383` forbids. Measured by
            # `docs/reviews/probe-r6-post-escape.py`.
            try:
                return await self._attempt(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    json_body=json_body,
                    jobfeed=jobfeed,
                    path=path,
                )
            except _RetryableUpstream as exc:
                raise exc.public_error() from None

        remaining = outbound_budget_remaining()
        # BOTH caps, OR-ed (`backend/resilience.md:88-90`).
        # `stop_after_delay` measures from the first attempt, so it is
        # given what is left of the invocation's budget rather than a
        # constant of its own - otherwise a retry loop on the last page
        # of a scan could outlive the budget every other layer respects.
        stop = (
            stop_after_attempt(self._retry_max_attempts)
            | stop_after_delay(max(remaining or 0.0, 0.0))
            # THE THIRD ARM (R6-M1). The other two fire on a count and
            # on elapsed time; neither can see a wait we have not taken
            # yet, and a `Retry-After` we cannot afford is exactly that.
            | _retry_after_exceeds_budget
        )
        retrying = AsyncRetrying(
            retry=_should_retry,
            wait=self._wait_for_retry,
            stop=stop,
            before_sleep=_log_retry_attempt,
            reraise=True,
        )
        try:
            return await retrying(
                self._attempt,
                method,
                url,
                params=params,
                headers=headers,
                json_body=json_body,
                jobfeed=jobfeed,
                path=path,
            )
        except (_RetryableUpstream, JobviteUnavailableError) as exc:
            # THE BUDGET IS THE AUTHORITY ON WHY WE STOPPED, and this
            # `if` is the difference between the design's promise and a
            # near miss. `stop_after_delay` fires when the budget is
            # spent, `reraise=True` then re-raises the LAST attempt's
            # error, and that error describes the attempt rather than
            # the reason: a slow upstream that answered 503 twice would
            # surface as `/problems/external-service-error` **502**
            # while DESIGN.md:392-394 promises "a typed 503".
            #
            # **This was found by the test, not by reading the code.**
            # The first version of this method had no such branch and
            # `test_a_slow_upstream_becomes_a_typed_503...` failed
            # against it with `Jobvite returned status 503` - a
            # perfectly true statement about the last attempt and the
            # wrong answer to "why did this call end".
            remaining = outbound_budget_remaining()
            if remaining is not None and remaining <= 0:
                raise JobviteRetryLaterError(
                    UNAVAILABLE_BUDGET_DETAIL,
                    retry_after=None,
                    counts_toward_breaker=False,
                ) from None
            if isinstance(exc, _RetryableUpstream):
                raise exc.public_error() from None
            raise

    def _wait_for_retry(self, state: RetryCallState) -> float:
        """How long to sleep before the next attempt.

        **`Retry-After` beats the local schedule** when Jobvite sent one
        (`backend/resilience.md:95-97`: "respect the server's
        back-pressure rather than the local backoff schedule when the
        header is present"), and the value is CLAMPED to what remains of
        the outbound budget - an upstream asking for 900 seconds must
        not be able to make us wait past a bound we promised the caller.

        Args:
            state: `tenacity`'s call state for the attempt that failed.

        Returns:
            Seconds to sleep. Exponential with jitter by default;
            jitter-free retries synchronise clients into a thundering
            herd that amplifies the outage.
        """
        exc = state.outcome.exception() if state.outcome is not None else None
        remaining = outbound_budget_remaining()
        if isinstance(exc, _RetryableUpstream) and exc.retry_after is not None:
            wait = exc.retry_after
        else:
            wait = _JITTERED_BACKOFF(state)
        if remaining is not None:
            wait = min(wait, max(remaining, 0.0))
        return wait

    def _attempt_timeout(self, remaining: float | None) -> httpx2.Timeout:
        """The per-phase timeout for one attempt, clamped to the budget.

        **Per-phase and explicit** (DESIGN.md:358): four separate
        numbers, never httpx2's 5-second scalar default. The clamp is
        what stops a single read timeout from outliving the invocation's
        total budget, which is the whole point of DESIGN.md:392-394.

        Args:
            remaining: Seconds left in the outbound budget, or `None`
                when no scope is open.

        Returns:
            The timeout to apply to this attempt.
        """
        if remaining is None:
            return self._timeout
        bound = max(remaining, 0.0)
        return httpx2.Timeout(
            connect=min(self._timeout.connect or DEFAULT_CONNECT_TIMEOUT, bound),
            read=min(self._timeout.read or DEFAULT_READ_TIMEOUT, bound),
            write=min(self._timeout.write or DEFAULT_WRITE_TIMEOUT, bound),
            pool=min(self._timeout.pool or DEFAULT_POOL_TIMEOUT, bound),
        )

    async def _attempt(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, str],
        headers: Mapping[str, str],
        json_body: Mapping[str, Any] | None,
        jobfeed: bool,
        path: str,
    ) -> dict[str, Any]:
        """The innermost layer: ONE bounded call, and the invariant.

        Args:
            method: The HTTP method.
            url: The fully-built URL. Never logged - `path` is.
            params: The query parameters.
            headers: The request headers.
            json_body: The JSON body.
            jobfeed: Whether this is the v1 route, for the log line.
            path: The route below the base URL, for the log line.

        Returns:
            The decoded body, when both arms of the invariant hold.

        Raises:
            JobviteRetryLaterError: If the outbound budget is already
                spent. Checked BEFORE the call, so an exhausted budget
                cannot buy one more full read timeout.
            _RetryableUpstream: On a 429 or a 5xx. Module-private; the
                retry layer converts it before anything else sees it.
            JobviteUpstreamError: On a 4xx or an undecodable body.
            JobviteUnavailableError: On a transport failure.
        """
        remaining = outbound_budget_remaining()
        if remaining is not None and remaining <= 0:
            raise JobviteRetryLaterError(
                UNAVAILABLE_BUDGET_DETAIL,
                retry_after=None,
                counts_toward_breaker=False,
            )

        try:
            response = await self._client.request(
                method,
                url,
                params=dict(params),
                headers=dict(headers),
                json=dict(json_body) if json_body is not None else None,
                # PER-ATTEMPT, and narrowed to what is left of the
                # invocation's budget. The client-level timeout is
                # already explicit and per-phase; this is the layer that
                # keeps the LAST attempt inside the total bound.
                timeout=self._attempt_timeout(remaining),
            )
        except (
            httpx2.HTTPError,
            # NOT SUBCLASSES OF HTTPError, measured at httpx2 2.12.0
            # rather than assumed: `InvalidURL`, `CookieConflict` and
            # `StreamError` sit outside that hierarchy entirely.
            # `except httpx2.HTTPError` reads like "any transport
            # failure" and is not.
            #
            # An InvalidURL is reachable the moment a later unit
            # interpolates a `path` - U5 and U12 both do - and it would
            # escape this block WITHOUT passing through `redact_text`
            # and without becoming a typed error, so the module's own
            # documented contract ("Raises: JobviteUnavailableError: If
            # Jobvite could not be reached at all") would be false.
            # errors.py contains it at the boundary today, so there is
            # no leak; the defect is the contract, not a live escape.
            httpx2.InvalidURL,
            httpx2.CookieConflict,
            httpx2.StreamError,
        ) as exc:
            # THE LOG IS WHERE THE EXCEPTION TEXT GOES, and the consumer
            # gets an enumerated reason instead
            # (`backend/error-handling.md:383`, `:493`, and the block
            # above `_unavailable_detail`). "Log errors with sufficient
            # context server-side" is the same standard's :494.
            #
            # `httpx` puts the request URL into the text of the
            # exceptions it raises, so on the jobFeed route `str(exc)`
            # carries `sc=`. `redact_text` is the arm of
            # utils/redaction.py that exists for exactly this
            # (DESIGN.md:315-318); without it a timeout on the feed
            # publishes the credential into whatever formats the
            # exception.
            #
            # `redact_headers` is applied because on the v2 branch
            # `headers` IS `v2_headers()` - the resolved `x-jvi-api` and
            # `x-jvi-sc` values, in the clear, in a local variable
            # (DESIGN.md:312). This is the call site that function was
            # written for; before this line it had none, and a header
            # dict was one `logger.debug(headers=headers)` away from the
            # log stream with nothing to stop it.
            #
            # The exception is passed as REDACTED TEXT, not as an
            # exception object: `logger.exception` would put it in
            # `record["exception"]`, which the sink's filter does not
            # reach - see `__main__.py`.
            logger.warning(
                "jobvite transport failure",
                method=method,
                route=redact_url(f"{V1_BASE_URL if jobfeed else V2_BASE_URL}{path}"),
                headers=redact_headers(dict(headers)),
                error=redact_text(f"{type(exc).__name__}: {exc}"),
            )
            raise JobviteUnavailableError(_unavailable_detail(exc)) from None
        finally:
            # NO COOKIE JAR (`JOBVITE-CONTRACT.md` §2.3). Jobvite sets
            # four `AWSALBAPP-*` cookies whose values are all the
            # literal string `_remove_`, and the API is
            # credential-authenticated per request: there is no session
            # to carry.
            #
            # **This is not httpx2's default and was measured, not
            # assumed.** A bare `AsyncClient` stores those cookies and
            # sends them back on the next request; the probe that
            # established it is reproduced as a test. Clearing in
            # `finally` rather than after a success means a call that
            # raised cannot leave a jar behind either.
            self._client.cookies.clear()

        try:
            return evaluate_response(response.status_code, response.content)
        except JobviteUpstreamError as exc:
            # THE RETRY PREDICATE'S ONE DECISION, and it is made here
            # rather than in `tenacity` because this is the only frame
            # that still has the RESPONSE - and `Retry-After` lives on
            # the response, not on the exception.
            #
            # **A 4xx falls straight through**, unwrapped, which is what
            # makes `backend/resilience.md:92-94` ("4xx validation, auth
            # and permission errors are not retryable and must surface
            # immediately") a property of the code rather than of a
            # configured exception list.
            #
            # The status is read from the EXCEPTION, not from
            # `response.status_code`: `evaluate_response`'s first arm is
            # the body's own envelope, and the recorded fixture that
            # arm exists for is an HTTP **200** carrying a 401. Reading
            # the HTTP line here would classify a 200-with-503-envelope
            # as non-retryable and a 200-with-401-envelope as whatever
            # the line said.
            if _is_retryable_status(exc.upstream_status):
                raise _RetryableUpstream(
                    exc, _retry_after_seconds(response.headers)
                ) from None
            raise

    # -- paging (U6)
    # ------------------------------------------------------

    def transport_cap(self, *, jobfeed: bool = False) -> int:
        """The transport page cap for a route (DESIGN.md:473).

        Args:
            jobfeed: Select the `/v1/jobFeed` route's cap.

        Returns:
            1000 on `/v1/jobFeed`, 500 on v2. **Neither is observed**;
            both are the design's figures.
        """
        return JOBFEED_PAGE_CAP if jobfeed else V2_PAGE_CAP

    def result_cap(self, *, jobfeed: bool = False) -> int:
        """`min(transport_cap, configured_result_cap)`.

        **THE TRANSPORT HALF OF ONE BEHAVIOUR SPLIT ACROSS TWO FILES**
        (DESIGN.md:473-475). U5's `tools/jobs.py` applies
        `JOBVITE_MAX_RESULTS` to a page and owns the caller-facing
        `showing N of total` string; this is the `min()` that composes
        the two caps, and it is deliberately not a second copy of U5's
        reporting. Neither unit owns all of it.

        Args:
            jobfeed: Select the `/v1/jobFeed` route's transport cap.

        Returns:
            The smaller of the route's transport cap and the
            configured result cap.
        """
        return min(self.transport_cap(jobfeed=jobfeed), self._max_results)

    def scan_start(self, path: str) -> int:
        """The FIRST `start` of a scan of `path` (DESIGN.md:494-503).

        `SCAN_START` unless an operator has overridden this resource.
        The override is per resource and not global
        (DESIGN.md:517-519), and it exists for someone who has
        established the base against a live tenant. **The vendor's
        1-based claim is not written here as a default**: a declared 1
        never requests record zero, so on a 0-based server it loses
        that record on every scan and nothing reports it.

        Args:
            path: The resource path, the same value `scan` is given.

        Returns:
            The offset the scan's first request will carry.
        """
        return self._start_base_overrides.get(path, SCAN_START)

    async def scan(
        self,
        path: str,
        *,
        items_key: str,
        params: Mapping[str, str] | None = None,
        jobfeed: bool = False,
        id_key: str = DEFAULT_ID_KEY,
        limit: int | None = None,
    ) -> ScanResult:
        """Page a resource, base-agnostically (DESIGN.md:494-526).

        Args:
            path: The path below the base URL, e.g. `/job`.
            items_key: The envelope key holding the page's records.
            params: Non-credential, non-paging query parameters.
            jobfeed: Select the v1 `jobFeed` route.
            id_key: The per-record identifier the seen set reads.
            limit: The caller's cap, clamped to `result_cap`. **`None`
                means an EXHAUSTIVE scan**, and it is the only input
                that arms the completeness check.

        Returns:
            The scan, with its counts.

        Raises:
            JobviteUpstreamError: From `request`, unchanged.
            JobviteUnavailableError: From `request`, unchanged.
        """
        # ONE RULE FOR THE PAGE SIZE, and it is DESIGN.md:473-475's
        # `min(transport_cap, configured_result_cap)` with no branch on
        # top of it. An exhaustive scan pages at the same size and just
        # keeps going; a caller's `limit` only ever narrows it further.
        # A separate "exhaustive scans use the raw transport cap" rule
        # would CONTRADICT the policy §4.5 states; it is not a vacuum
        # this would fill. ADR-0025's Q1 said the design stated no
        # policy and was WITHDRAWN for it. Changing this is an ADR
        # amending §4.5, never a branch invented here - and such a
        # branch is untestable without a knob invented to test it.
        exhaustive = limit is None
        cap = self.result_cap(jobfeed=jobfeed)
        effective_limit = cap if exhaustive else min(limit or 0, cap)
        count = cap if exhaustive else max(effective_limit, 1)

        # THE BUDGET IS OPENED HERE, AROUND THE WHOLE SCAN, and that is
        # the difference between a budget and a timeout
        # (DESIGN.md:392-394: "bounds all attempts for ONE TOOL
        # INVOCATION"). An exhaustive scan of a 1,240-record resource
        # makes 25 requests; each `request` below finds this scope
        # already open and shares its deadline rather than starting a
        # fresh one, so 25 requests cannot cost 25 budgets.
        #
        # A caller that has already opened a scope keeps it - see
        # `outbound_budget_scope` - so wrapping a scan inside a tool's
        # own invocation scope narrows nothing.
        with outbound_budget_scope(self._outbound_budget_seconds):
            return await self._scan_pages(
                path,
                params=params,
                items_key=items_key,
                id_key=id_key,
                jobfeed=jobfeed,
                exhaustive=exhaustive,
                effective_limit=effective_limit,
                count=count,
            )

    async def _scan_pages(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None,
        items_key: str,
        id_key: str,
        jobfeed: bool,
        exhaustive: bool,
        effective_limit: int,
        count: int,
    ) -> ScanResult:
        """The paging loop itself, inside one outbound budget scope.

        Split out of `scan` so the budget scope is a single statement
        wrapping the whole loop rather than a `try/finally` threaded
        through it. U6 wrote the loop; U7 moved it and changed nothing
        inside it.

        Args:
            path: The resource path.
            params: Non-credential query parameters.
            items_key: The envelope key holding the page's records.
            id_key: The per-record identifier the seen set reads.
            jobfeed: Select the v1 route.
            exhaustive: Whether the caller asked for everything.
            effective_limit: The cap this scan stops at.
            count: The page size requested on the wire.

        Returns:
            The scan's records and what a caller must not re-derive.
        """
        start = self.scan_start(path)
        base_params = dict(params or {})
        seen: set[Any] = set()
        items: list[dict[str, Any]] = []
        total: int | None = None
        pages = 0
        duplicates = 0
        unidentified = 0
        short_page = False
        capped = False
        #: ADR-0024's two bounds. Kept apart from `short_page` because
        #: neither IS one - a scan that stopped on either did not reach
        #: the end of the resource, and `_check_completeness` must not
        #: read them as though it had.
        stalled = False
        ceiling_hit = False

        while True:
            payload = await self.request(
                "GET",
                path,
                params={**base_params, "start": str(start), "count": str(count)},
                jobfeed=jobfeed,
            )
            pages += 1
            reported = payload.get(TOTAL_KEY)
            # `not isinstance(reported, bool)` IS LOAD-BEARING, not
            # defensive noise: `isinstance(True, int)` is True in
            # Python, so an envelope carrying `"total": true` would
            # land a `bool` in `ScanResult.total` (R5-N1, measured).
            # `True` then compares equal to `unique == 1`, so a
            # one-record scan declares itself COMPLETE against a
            # `total` that is not a number.
            if isinstance(reported, int) and not isinstance(reported, bool):
                total = reported
            raw = payload.get(items_key)
            page: list[dict[str, Any]] = (
                [item for item in raw if isinstance(item, dict)]
                if isinstance(raw, list)
                else []
            )

            # PROGRESS IS MEASURED BEFORE THE PAGE IS CONSUMED, and
            # `unidentified` is counted alongside `seen` because an
            # id-less record IS a record the caller receives - a page of
            # them is progress, not stalling (DESIGN.md:504-507).
            progress_before = len(seen) + unidentified

            for item in page:
                ident = item.get(id_key)
                if ident is None:
                    # KEPT, and never de-duplicated. Every id-less
                    # record would collapse onto one `None` key, so a
                    # seen set that swallowed them would DELETE
                    # records - the over-reading defence causing the
                    # under-read it exists to prevent
                    # (DESIGN.md:504-507).
                    unidentified += 1
                    items.append(item)
                    continue
                if ident in seen:
                    duplicates += 1
                    continue
                seen.add(ident)
                items.append(item)

            # THE ONLY TERMINATION THAT READS THE SERVER
            # (DESIGN.md:525-526). `len(page) < count`, on the RAW page
            # and not on the de-duplicated total: a fully duplicate
            # full-length page is not a short page, and stopping on it
            # would end a scan early on the clamping hypothesis.
            # `total` is reported and is never a loop condition.
            if len(page) < count:
                short_page = True
                break

            if not exhaustive and len(items) >= effective_limit:
                capped = True
                break

            # ====================================================
            # THE ZERO-PROGRESS BREAK (ADR-0024 mechanism 1, Accepted;
            # R5-H2).
            #
            # Reached only on a FULL page, because the short-page exit
            # is above it. So it fires exactly when the server answered
            # a complete page that added NOTHING. On healthy paging that
            # cannot happen: a full page of records the caller has not
            # seen is progress by definition, and a page that is
            # genuinely the last one is short.
            #
            # THIS IS THE ONE THAT TERMINATES THE LOOP rather than
            # capping it. R5 measured the unfixed shape and aborted its
            # own probe at 200 requests. `scripts/probe-scan-bounds.py`
            # re-measured the same shape on `5eb64b0`, against a client
            # that HAS the outbound budget, and had to abort at 2,000 -
            # including on a run with a two-SECOND budget, because the
            # budget bounds wall clock and a `MockTransport` answers
            # thousands of requests inside it. That is the evidence for
            # ADR-0024's "the budget is a mitigation, not a fix", and it
            # is stronger than the ADR states: the budget did not fire
            # at all. With the break in place the same arm issues TWO
            # requests.
            #
            # `incomplete` rather than an exception, because the records
            # already collected are REAL. A caller holding 50 records
            # and `incomplete=True` is better served than one holding a
            # 503 and nothing, which is what the budget would eventually
            # have handed it.
            # ====================================================
            if len(seen) + unidentified == progress_before:
                stalled = True
                logger.warning(
                    "jobvite scan: a full page added no records; the server "
                    "is not advancing",
                    route=redact_url(f"{V2_BASE_URL}{path}"),
                    pages=pages,
                    records=len(items),
                    request_id=request_id_var.get(),
                )
                break

            # ====================================================
            # THE RECORD CEILING (ADR-0024 mechanism 2, as CORRECTED
            # by the ADR's own ruling to count records rather than
            # pages - see MAX_SCAN_RECORDS).
            #
            # NEITHER MECHANISM SUBSTITUTES FOR THE OTHER, and the probe
            # shows why instead of the ADR asserting it. A server that
            # IGNORES `start` repeats one page: its record count never
            # grows, and the break above catches it. A server that
            # HONOURS `start` and never runs out returns a full page of
            # NEW records every time: the zero-progress break can never
            # fire, and the only thing at risk is memory. R5's fake
            # produces the first shape only, which is why the second
            # needed a probe of its own.
            # ====================================================
            if len(items) >= MAX_SCAN_RECORDS:
                ceiling_hit = True
                logger.warning(
                    "jobvite scan: the record ceiling was reached without a short page",
                    route=redact_url(f"{V2_BASE_URL}{path}"),
                    pages=pages,
                    records=len(items),
                    ceiling=MAX_SCAN_RECORDS,
                    request_id=request_id_var.get(),
                )
                break

            start += count

        if not exhaustive and len(items) > effective_limit:
            capped = True
            items = items[:effective_limit]

        # EITHER BOUND MAKES THE RESULT INCOMPLETE ON ITS OWN, and the
        # `or` is what makes that true regardless of `total`.
        # `_check_completeness` is armed only by a SHORT PAGE and only
        # when the envelope carried an integer `total` - both correct
        # for
        # what it checks, and both reasons it cannot see these two. A
        # scan
        # that stopped because the server stopped advancing is
        # incomplete
        # whether or not `total` was reported at all.
        incomplete = (
            self._check_completeness(
                path=path,
                exhaustive=exhaustive,
                short_page=short_page,
                unique=len(seen) + unidentified,
                total=total,
            )
            or stalled
            or ceiling_hit
        )

        return ScanResult(
            items=items,
            total=total,
            pages=pages,
            duplicates_dropped=duplicates,
            unidentified=unidentified,
            capped=capped,
            exhaustive=exhaustive,
            incomplete=incomplete,
        )

    def _check_completeness(
        self,
        *,
        path: str,
        exhaustive: bool,
        short_page: bool,
        unique: int,
        total: int | None,
    ) -> bool:
        """Completeness vs `total`, ARMED ONLY BY AN EXHAUSTIVE SCAN.

        DESIGN.md:508-516. The check has two required halves and the
        second is the one that gets left out:

        * it fires when a scan that requested EVERYTHING terminated on
          a short page and returned fewer unique records than `total`;
        * **it must NOT fire on a capped call.** A capped result is a
          mismatch BY DESIGN - `showing 50 of 1,240` is §7.7's own
          worked example - and DESIGN.md:513 says wiring the check to
          every call "would fire the alarm on the default path and
          train everyone to ignore it".

        Comparing a COUNT is the whole mechanism, because `eId` is
        opaque and you cannot find a hole in a set of opaque ids
        (DESIGN.md:508-511).

        Args:
            path: The resource, for the log line.
            exhaustive: The caller requested no limit.
            short_page: The scan terminated on a short page.
            unique: Unique records returned.
            total: The envelope's reported `total`, if any.

        Returns:
            Whether the anomaly was logged.
        """
        if not exhaustive or not short_page or not isinstance(total, int):
            return False
        if unique == total:
            return False

        # THE TWO DIRECTIONS ARE DIFFERENT FINDINGS AND WERE LOGGED
        # AS ONE (R5-M2). `unique != total` fires on both, and this
        # method's own docstring says the check is for a scan that
        # returned **fewer** records than `total` - which is what
        # DESIGN.md:508-516 describes and all it contemplates.
        #
        # The over-count direction is REACHABLE and was reached: a
        # wrong `id_key` sends every record down the `unidentified`
        # branch, kept and never de-duplicated, giving `unique=10`
        # against `total=9`. That was logged as "jobvite scan
        # incomplete" - an OVER-read reported as an under-read, the
        # same wolf with the wrong name on it. DESIGN.md:513 is
        # explicit about what crying wolf costs.
        if unique > total:
            logger.warning(
                "jobvite scan returned MORE unique records than total",
                route=redact_url(f"{V2_BASE_URL}{path}"),
                unique=unique,
                reported_total=total,
            )
            return True

        logger.warning(
            "jobvite scan incomplete",
            route=redact_url(f"{V2_BASE_URL}{path}"),
            unique=unique,
            reported_total=total,
        )
        return True
