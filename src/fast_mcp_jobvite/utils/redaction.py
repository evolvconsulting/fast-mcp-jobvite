"""Secret redaction - the single enforcement point (DESIGN.md:312-318).

**This module holds the SECRET half only.** DESIGN.md:293 gives
`utils/redaction.py` two jobs, "log redaction; untrusted-content
fencing", and `IMPLEMENTATION-PLAN.md:1497` assigns the fencing half to
U8. Nothing here fences.

**Why one place.** DESIGN.md:312-318 classifies the v1 `GET /v1/jobFeed`
URL as sensitive - it structurally requires `api`, `sc` and `companyId`
as query parameters, so unlike every other Jobvite call the credential
is *in the URL* - and states the rule as "never logged whole, never in
an exception message, `sc=` redacted before any log line. Enforced in
one place, `utils/redaction.py`, with a test that fails if a secret can
reach a log record." A second redactor elsewhere is the defect this
sentence exists to prevent, because the two drift and the one that
drifts is the one nobody reads.

**Three parameters are redacted, not one.** DESIGN.md:315-316
names `api`, `sc` and `companyId` as the three the URL
structurally carries, and DESIGN.md:332-333 makes `companyId` a
credential class of its own ("the job feed's separate `companyId`
credential"). §8's required case names
`sc=` because that is the one an implementer is most likely to reach
for; redacting only it would satisfy the case and leave two credentials
in the log line, so the case is the floor here and not the
specification.

**Arguments are redacted by allow-list, and the direction is
deliberate.** DESIGN.md:1897 rates C7-I1 - candidate PII written to logs
in the clear - **Critical**, and `ai/tool-calling.md:171-172` requires
the audit event to carry "validated arguments (PII redacted)". A
deny-list of known PII key names fails *open*: the argument nobody
thought of is emitted in the clear, which is the failure mode
DESIGN.md:1886 (C6-I2) already rejects for output fields in favour of
"path-keyed allow-list fails closed: an unlisted field is dropped until
someone adds it deliberately". The same reasoning applies with more
force on the audit path, because `create_candidate`'s arguments **are**
the candidate. So an argument whose key is not on
`NON_SENSITIVE_ARGUMENT_KEYS` has its value replaced by a type marker,
and the audit record still shows *which* arguments were supplied and of
what shape - which is what makes the event auditable - without showing
any of their content.
"""

from __future__ import annotations

import logging
import re
import threading
import urllib.parse
from collections.abc import Mapping, Sequence
from typing import Any, Final

# PRIVATE ON PURPOSE, and the failure mode is loud (ADR-0026). The
# logger NAME is not public API; ADR-0026 forbids the string literal,
# so the symbol is imported instead. If httpx2 moves it this raises
# ImportError at import time - a red gate, never a silent unredacted
# log - which is why the private path is accepted rather than guarded.
from httpx2._client import logger as _httpx2_logger  # noqa: SLF001

from ..models.fencing import (
    LIST_MARKER,
    PATH_SEPARATOR,
    Fenced,
    FencingDecision,
)
from .normalise import blank_to_none

#: The value shape a validated tool argument can take. Recursive,
#: because `create_candidate`'s payload is nested and a redactor typed
#: only at the top level would be typed for the case that does not
#: matter. `Any` is not available: `ANN401` is on (`pyproject.toml`,
#: ruff `ANN`), and it would also switch mypy off exactly where the
#: fail-closed walk needs checking.
type JsonValue = (
    str | int | float | bool | None | Mapping[str, JsonValue] | Sequence[JsonValue]
)

#: What replaces a redacted scalar. A fixed sentinel rather than a
#: length-preserving mask: a mask that preserves length leaks the
#: length, and a credential's length is a real hint.
REDACTED: Final = "[REDACTED]"

#: A URL carrying credentials in its USERINFO -
#: `scheme://user:password@host`.
#:
#: Round 2 found this surviving: `redact_text` only inspected tokens
#: containing both `?` and `=`, so a proxy URL - which has neither -
#: passed through whole and reached the caller's problem `detail`.
#: Measured before the fix:
#: `https://user:hunter2@proxy.internal:8080/path` came back unchanged.
#:
#: `://` before the `@` is what separates this from an email address,
#: which must not be touched: `someone@example.com` has no scheme and no
#: colon-password.
_USERINFO: Final = re.compile(
    r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*://)(?P<user>[^/@\s:]+):(?P<pw>[^/@\s]*)@"
)

#: Query parameters on the `jobFeed` URL that carry a credential
#: (DESIGN.md:312-318). Compared case-insensitively, because a URL a
#: human assembled will not always match Jobvite's casing and a redactor
#: that misses `SC=` has failed open.
SECRET_QUERY_PARAMS: Final[frozenset[str]] = frozenset({"api", "sc", "companyid"})

#: Request headers that carry a v2 credential (DESIGN.md:312).
#: Lower-cased; callers must lower-case the key before lookup.
SECRET_HEADERS: Final[frozenset[str]] = frozenset({"x-jvi-api", "x-jvi-sc"})

#: Argument keys whose values may appear in an audit record in the
#: clear.
#:
#: **Fail-closed: anything absent from this set is redacted.** Every
#: member is here because its value is structurally an identifier, a
#: bound, a page cursor, **or a closed-domain flag whose shape IS its
#: value** - rather than anything a candidate typed or that identifies
#: one. A tool added later contributes its arguments to the audit event
#: redacted, and stays that way until someone adds the key here
#: deliberately - which is the point.
#:
#: **The fourth clause was added with `send_email` and is not a
#: loosening.** For every other argument here, recording the SHAPE is
#: enough to make the event auditable. For a `bool` the shape is the
#: whole domain, so `[REDACTED:bool]` answers nothing: the record cannot
#: distinguish a write that emailed a live person from one that did not.
#: A flag qualifies only when its domain is closed AND enumerating it
#: discloses nothing about a candidate - which is why `query`, also a
#: single value, is still absent below.
#:
#: `query` is deliberately ABSENT. A `search_candidates` query is free
#: text a caller composed, and the obvious thing to search for is a
#: person's name.
NON_SENSITIVE_ARGUMENT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "candidate_id",
        "job_id",
        "requisition_id",
        "workflow_state",
        "limit",
        "start",
        "count",
        "page",
        "eId",
        # ADMITTED BY THE FOURTH CLAUSE ABOVE, AND IT IS THE ONE
        # ARGUMENT HERE WITH A THREAT ROW OF ITS OWN. DESIGN.md:1816
        # C1-T1 names flipping `send_email` to `true` a HIGH threat and
        # DESIGN.md:242 makes its `false` default a safety property.
        # Redacted to `[REDACTED:bool]` the audit event - the artefact a
        # compliance reader consults after the fact - could not answer
        # "did this write email a live person?", which is the single
        # question that row exists to make answerable.
        #
        # AND THE DESIGN ALREADY REQUIRES THE VALUE TO BE DISCLOSED.
        # DESIGN.md:1142-1143: the elicitation payload "names the
        # candidate, the target job, and **whether `send_email` is
        # true**, in those terms" - so the value is shown to the
        # approver at the moment of approval. A value the design
        # mandates showing to the approver cannot coherently be a secret
        # in the record of what was approved.
        #
        # **There is no tension with DESIGN.md:1145-1146, and reading
        # half of it manufactured one.** That line says `send_email` "is
        # also an
        # argument like any other AND IS SUBJECT TO §2.1's SCHEMA RULES;
        # it defaults to `false` (§2.2)". It is scoped to schema and
        # defaulting - it says this field gets no special treatment from
        # the INPUT MODEL, and says nothing about the audit surface. A
        # citation trimmed at the comma reads as a conflict with C1-T1
        # and there is none; that misreading was carried into a review,
        # a task and this comment before anyone quoted the sentence
        # whole.
        #
        # NOT A LICENCE TO WIDEN. The next flag proposed for this list
        # gets both questions asked out loud, and "it is a bool" is not
        # on its own an answer: `approve` is also a bool and belongs
        # nowhere near here.
        "send_email",
        # `companyId` WAS HERE AND IS A CREDENTIAL. R2-H5.
        #
        # This file already classified it as one: SECRET_QUERY_PARAMS
        # holds `companyid`, so the identical value was REDACTED in a
        # URL and published IN THE CLEAR as a tool argument - two lists
        # eighty lines apart in one module, disagreeing. The docstring
        # above says so outright: DESIGN.md:333, "the job feed's
        # separate `companyId` credential", and :1692 classifies it
        # Restricted.
        #
        # Removing it costs nothing today: no tool takes `companyId` as
        # an argument, and JOBVITE_COMPANY_ID is configuration, never a
        # caller-supplied value. U12's `get_job_feed` reads it from
        # settings, so it must NOT be re-admitted here when that lands.
        # U5's `search_jobs` argument, admitted DELIBERATELY by the rule
        # above: its value is a Jobvite `eId`, structurally the same
        # identifier as `eId` and `job_id`, which are already here.
        #
        # THE NAME IS GENERIC AND THAT IS THE RISK, written down rather
        # than left for someone to rediscover. This set is keyed by
        # argument NAME across every tool, so admitting `ids` admits it
        # for any future tool using that word. It is tolerable only
        # while the rule above holds - "structurally an identifier, a
        # bound or a page cursor". A later tool whose `ids` means
        # anything else MUST RENAME ITS ARGUMENT rather than lean on
        # this entry, and the reviewer's job is to notice.
        #
        # Not a new class: `candidate_id` is already admitted, so a
        # candidate identifier is already deemed loggable here.
        "ids",
    }
)


def redact_url(url: str) -> str:
    """Redact every credential-bearing query parameter in a URL.

    The `jobFeed` URL is the reason this exists (DESIGN.md:312-318), but
    the function is not restricted to it: a URL is passed in and every
    parameter in `SECRET_QUERY_PARAMS` comes back redacted, whatever the
    host. Restricting it to a recognised `jobFeed` host would fail open
    on a staging host, a tenant-specific host, or a URL assembled
    slightly differently.

    Parameter ORDER and every non-secret parameter are preserved, so a
    redacted URL is still useful for debugging - which is what stops
    someone logging the raw one instead.

    Args:
        url: The URL to redact. May be a fragment, a full URL, or a
            string that is not a URL at all; a string with no query part
            is returned unchanged.

    Returns:
        The URL with each secret parameter's value replaced by
        `REDACTED`.
    """
    split = urllib.parse.urlsplit(url)
    if not split.query:
        return url
    pairs = urllib.parse.parse_qsl(split.query, keep_blank_values=True)
    if not any(key.lower() in SECRET_QUERY_PARAMS for key, _ in pairs):
        # Returned byte-identical rather than reassembled. `urlencode`
        # would re-encode every innocent value, so a URL with nothing to
        # redact would still come back altered - and a redactor that
        # rewrites what it had no reason to touch is one nobody trusts
        # to be transparent.
        return url
    redacted = [
        (key, REDACTED if key.lower() in SECRET_QUERY_PARAMS else value)
        for key, value in pairs
    ]
    # `safe="[]"` keeps the sentinel literal. Without it `urlencode`
    # percent- encodes the brackets to `%5BREDACTED%5D`, and every
    # downstream grep for `[REDACTED]` - in a test, in a log search, in
    # an incident - misses it.
    query = urllib.parse.urlencode(redacted, safe="[]")
    return urllib.parse.urlunsplit(split._replace(query=query))


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Redact the v2 credential headers (DESIGN.md:312).

    Args:
        headers: Request headers. Keys are matched case-insensitively.

    Returns:
        A new mapping with `x-jvi-api` and `x-jvi-sc` values replaced.
        The original is not mutated, because a redactor that mutates its
        input redacts the request that is about to be sent.
    """
    return {
        key: (REDACTED if key.lower() in SECRET_HEADERS else value)
        for key, value in headers.items()
    }


#: Characters that close a URL in prose rather than belonging to it.
#: `redact_text` splits on whitespace, so these arrive attached to the
#: last query value (R2-nit-3).
_TRAILING_PUNCTUATION: Final[str] = "'\"),.;"


def redact_text(text: str) -> str:
    """Redact any credential-bearing URL embedded in free text.

    This is the arm that covers an **exception message**
    (DESIGN.md:315-318). `httpx` puts the request URL into the text of
    the exceptions it raises, so a `jobFeed` timeout carries `sc=` in
    `str(exc)` and any handler that formats the exception into a log
    line publishes the credential. Redacting only at the URL-argument
    boundary would miss exactly that path.

    Args:
        text: Arbitrary text that may contain a URL.

    It also redacts **userinfo** - `scheme://user:password@host` - which
    the query-parameter arm cannot reach, because such a URL carries
    neither `?` nor `=`. An httpx proxy misconfiguration puts exactly
    that into an exception message. The username is kept: the password
    is the secret and the user is the diagnosis, the same split this
    project applies to a failing assertion.

    Returns:
        The text with every embedded URL's secret parameters and
        userinfo password redacted.
    """
    out: list[str] = []
    for token in _split_keeping_whitespace(text):
        if "?" in token and "=" in token:
            # R2-nit-3. A URL quoted, parenthesised or ended with a full
            # stop arrives as ONE whitespace-delimited token with the
            # closing character stuck to the last query VALUE, so
            # `redact_url` replaced the delimiter along with the secret
            # and the message came back with an unbalanced quote. Split
            # the trailing run off, redact, and put it back.
            #
            # A value that genuinely ends in one of these loses that one
            # character to the outside of the redaction; the whole
            # secret is still replaced, and one punctuation mark carries
            # nothing, which is the cheaper of the two errors.
            core = token.rstrip(_TRAILING_PUNCTUATION)
            out.append(redact_url(core) + token[len(core) :])
        else:
            out.append(token)
    # Userinfo is a SECOND credential shape in the same text, and it is
    # not reached by the query-parameter arm above: a proxy URL has no
    # `?` and no `=`, so it never entered `redact_url` at all. Applied
    # to the joined text rather than per token so a URL split across the
    # whitespace splitter is still caught.
    return _USERINFO.sub(
        lambda m: f"{m.group('scheme')}{m.group('user')}:{REDACTED}@", "".join(out)
    )


def redact_arguments(arguments: JsonValue) -> JsonValue:
    """Redact a tool's validated arguments for the audit event.

    Fail-closed by allow-list, for the reason in the module docstring.
    Nested containers are walked, because `create_candidate`'s payload
    is nested and a top-level-only redactor would emit the whole
    candidate one level down.

    A redacted scalar becomes `"[REDACTED:<type>]"` rather than a bare
    sentinel. The type is not sensitive, and keeping it is what makes
    the audit event answer "was a résumé body supplied on this call" -
    which is an auditing question - without answering "what did it say".

    Args:
        arguments: The validated arguments, or any value nested inside
            them.

    Returns:
        A redacted copy. The input is never mutated.
    """
    if isinstance(arguments, Mapping):
        return {
            key: (
                redact_arguments(value)
                if key in NON_SENSITIVE_ARGUMENT_KEYS
                else _redacted_value(value)
            )
            for key, value in arguments.items()
        }
    # `Sequence`, not `list`, because that is what `JsonValue` DECLARES.
    # The walk tested `list`, so a tuple - which is a `Sequence` and
    # therefore in contract - fell through to `return arguments`
    # UNREDACTED at the top level. Measured:
    # `redact_arguments(({"email": "a@b.c"},))` returned the address
    # untouched while the list form redacted it. A pydantic field typed
    # `tuple[...]` is all it takes.
    #
    # `str` and `bytes` are Sequences too and must NOT be walked
    # character by character; they are handled above as scalars.
    if isinstance(arguments, Sequence) and not isinstance(arguments, str | bytes):
        return [redact_arguments(item) for item in arguments]
    return arguments


def _redacted_value(value: JsonValue) -> str:
    """Replace one value with a marker naming only its type.

    **Containers are redacted whole, not descended into**, and that is
    the path-aware half of the allow-list. An earlier revision descended
    into any container regardless of its key, which meant an
    allow-listed key nested under an UNLISTED one was emitted in the
    clear:

        {"secretBlob": {"job_id": "...", "email": "..."}}
          -> {"secretBlob": {"job_id": "...", "email":
          "[REDACTED:str]"}}

    The `job_id` survived because `job_id` is allow-listed, even though
    nothing had allowed `secretBlob`. DESIGN.md:1886 calls C6-I2's
    mechanism a **path-keyed** allow-list for exactly this reason:
    membership has to be judged on the path, not on the leaf name in
    isolation.

    Found by the mutation harness rather than by reading - `M14`
    survived, which said the mutation was not a leak, which said the
    walk it removed was doing something other than what the test
    believed.
    """
    return f"[REDACTED:{type(value).__name__}]"


def _split_keeping_whitespace(text: str) -> list[str]:
    """Split on whitespace, keeping separators so text reassembles.

    `str.split()` discards the whitespace it split on, so rejoining with
    a single space would silently rewrite a log line's formatting -
    including a multi-line traceback, which is exactly the text this
    function is asked to redact.
    """
    tokens: list[str] = []
    current: list[str] = []
    for char in text:
        if char.isspace():
            if current:
                tokens.append("".join(current))
                current = []
            tokens.append(char)
        else:
            current.append(char)
    if current:
        tokens.append("".join(current))
    return tokens


class RedactingLogFilter(logging.Filter):
    """Redact a stdlib log record in place, and never drop it.

    **The embedder's half of DESIGN.md:312-318** (ADR-0026). Our own
    process gets redaction from `__main__.configure_logging()`, which
    installs a loguru sink and a record filter. An embedder that
    imports `server.build_server` - or, as ADR-0026's probe does,
    constructs `JobviteClient` directly - never runs it, and `httpx2`
    logs `HTTP Request: GET <url>` through the STANDARD LIBRARY logger,
    which on the `jobFeed` route structurally carries `api`, `sc` and
    `companyId`.

    So this is a `logging.Filter`, not a second redactor: it calls
    `redact_text`, the same function both loguru depths call, and
    "enforced in one place" still holds - one redactor, now three
    depths.

    **The MESSAGE is rewritten, not the arguments.** `record.msg` and
    `record.args` are formatted together by `getMessage()`, and the
    credential can sit in either - `httpx2` puts the URL in an
    argument. Formatting once here and clearing `args` redacts both
    without having to know which. It costs the lazy `%`-formatting a
    handler below might have skipped; a record that reached a filter is
    one somebody has already decided to emit.

    **Returns `True` always.** Dropping the record would turn a leak
    into silence, which is the other way to lose a log line - the same
    call `__main__._redact_message` makes, for the same reason.

    **WHAT IT DOES NOT REACH: `record.exc_info`.** A stdlib filter sees
    `msg` and `args`; a traceback is rendered by the FORMATTER, later,
    from `exc_info`, and no filter can redact it. `__main__` needs two
    depths for exactly this reason - a serialised exception carries the
    URL.

    **Measured, so the residue is bounded rather than feared.** Across
    the whole installed `httpx2` package, subdirectories included:

        getLogger(  -> 1   (_client.py:110, "httpx2")
        logger.*(   -> 2   (_client.py:1085 and :1923, both .info)
        exc_info=   -> 0   on any logging call

    So **httpx2 never attaches an exception to a record**, and the two
    calls it does make are `.info` with the URL in `args`, which is what
    this filter is built for. The one `getLogger` also settles the wider
    question: a filter on `httpx2` covers every logger this package
    creates, not merely the one somebody noticed.

    The real residual is narrower than "exceptions are unguarded": an
    EMBEDDER formatting a traceback on THEIR OWN logger was never within
    reach of a filter installed on `httpx2`, and could not be. That is
    what `configure_logging()` is for on the shipped path.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact one record's formatted message. Never drops one."""
        record.msg = redact_text(record.getMessage())
        record.args = None
        return True


#: The logger `httpx2` emits its request lines on.
#:
#: **DERIVED FROM THE IMPORTED MODULE, NEVER RETYPED** - ADR-0026's
#: second consequence, in its own words: *"The implementation must
#: derive the logger name from the imported module, not retype it. The
#: package is vendored as `httpx2` and a future rename would silently
#: detach the filter again."* This line was `Final = "httpx2"` until
#: R11-M1, which is the literal the ADR forbids, and it survived
#: review because the design had been edited to say it was derived.
#:
#: **`httpx2`, not `httpx`** (ADR-0007), and the distinction is not
#: cosmetic here: a filter installed on `httpx` is accepted by
#: `logging` without complaint, never fires, and leaves the leak
#: exactly as measured - a fix that lands on the wrong artefact.
#: Reading the library's own logger object is what makes that
#: unspellable rather than merely tested for.
HTTPX_LOGGER_NAME: Final[str] = _httpx2_logger.name

#: Serialises the check-then-add below. Two threads constructing a
#: client at once would otherwise both read a filter-less logger and
#: both append, which is the unbounded growth the idempotence exists to
#: prevent, merely rarer and harder to reproduce.
_INSTALL_LOCK: Final = threading.Lock()


def install_log_redaction(logger_name: str = HTTPX_LOGGER_NAME) -> bool:
    """Install `RedactingLogFilter` on one logger, at most once.

    **IDEMPOTENT, and that is the whole point of the function**
    (ADR-0026's ruling). `JobviteClient` is constructed once per
    invocation - `jobvite_client.py` says so where it explains why the
    breaker is module-level and not per-instance - so a bare
    `addFilter` in `__init__` stacks one filter per tool call, forever,
    and every record on that logger then walks a list that grows
    without bound. That is a slow leak inside the change written to
    stop a leak, and a test that builds a handful of clients and exits
    cannot see it.

    Args:
        logger_name: The logger to guard. Defaults to `httpx2`'s.

    Returns:
        `True` if this call installed the filter, `False` if one of
        ours was already there. The return value is what makes the
        idempotence observable without reaching into `logger.filters`.
    """
    logger = logging.getLogger(logger_name)
    with _INSTALL_LOCK:
        if any(isinstance(f, RedactingLogFilter) for f in logger.filters):
            return False
        logger.addFilter(RedactingLogFilter())
        return True


# ======================================================================
# THE FENCING HALF (U8). DESIGN.md:293 gives this module two jobs -
# "log redaction; untrusted-content fencing" - and the second one is
# below. U3 owns everything above and nothing here restructures it.
#
# **Containment is not fencing** (DESIGN.md:197-200 and
# `models/fencing.py`). Allow-listing decides WHETHER a field leaves;
# fencing decides HOW an admitted field is presented to a model. A
# field can be correctly admitted and still carry an injection payload.
#
# **The allow-list is PATH-KEYED WITH WILDCARDS, NOT NAME-KEYED**
# (DESIGN.md:820-822), and the design says why in its own words:
# "Name-keying collides: `title` and `eId` each appear at multiple
# depths in our own fixtures, and `customField[]` is open-ended. Keys
# are paths like `candidates[].application.job.title`."
#
# **Fencing is defined for STRINGS ONLY** (DESIGN.md:824-825). An
# unknown non-string field is DROPPED, not stringified - "stringifying
# invents a representation and collides with `strict=True` output
# models".
# ======================================================================

#: The opening delimiter wrapping attacker-authored content.
#:
#: **The tokens are XML-ish and named for their provenance**, which is
#: what `ai/prompt-injection.md` asks a fence to communicate: the model
#: is told what the block IS, not merely that a block exists. They are
#: also what `candidate_list_injection.json` attacks, so the fixture and
#: the implementation cannot drift apart silently - the red-team case
#: reads these constants.
FENCE_OPEN: Final = "<jobvite_candidate_data>"

#: The closing delimiter. Content containing this is what
#: DESIGN.md:817-818 means by "content cannot close its own fence".
FENCE_CLOSE: Final = "</jobvite_candidate_data>"

#: Every delimiter token stripped from content before it is wrapped.
#:
#: **Matched CASE-INSENSITIVELY**, and that is not decoration. A
#: stripper keyed on the exact literal passes
#: `candidate_list_injection.json` - whose payload is lowercase - and
#: misses `</JOBVITE_CANDIDATE_DATA>`, which an XML-ish reader
#: downstream may well treat as the same tag. The seed fixture is the
#: SEED and `IMPLEMENTATION-PLAN.md` §U8 says outright it is not
#: sufficient on its own.
_FENCE_TOKENS: Final = re.compile(
    "|".join(re.escape(token) for token in (FENCE_OPEN, FENCE_CLOSE)),
    re.IGNORECASE,
)

#: What a stripped delimiter leaves behind. Not an empty string: a
#: silent deletion makes the fenced body read as though the attacker
#: never wrote anything, and a reviewer reading a résumé cannot tell
#: tampering from the candidate's own prose. The marker says a token
#: was here and was removed.
FENCE_STRIPPED: Final = "[stripped]"

#: The wildcard segment. `customField[]` is open-ended
#: (DESIGN.md:821), so its members cannot be enumerated and a registry
#: that tried would be a hand-kept list beside a container it cannot
#: see the whole of.
PATH_WILDCARD: Final = "*"


def fence_text(text: str) -> str:
    """Wrap attacker-authored content so it cannot close its own fence.

    DESIGN.md:817-818: "Every such field is fenced before it reaches a
    tool result, and delimiter tokens occurring inside the content are
    stripped so content cannot close its own fence."

    **Strip first, then wrap.** The other order wraps the payload and
    then strips the wrapper's own tokens along with the attacker's,
    producing a fence with no delimiters at all - a refusal that looks
    like a pass.

    **Fencing does not censor.** An instruction inside the content
    survives verbatim; what it loses is the ability to escape the
    frame. Deleting the instruction instead would make the guard
    unfalsifiable, because a stripper that empties every résumé passes
    every red-team case and every positive control fails.

    Args:
        text: Content a candidate typed.

    Returns:
        The content between one opening and one closing delimiter, with
        every delimiter token inside it replaced by `FENCE_STRIPPED`.
    """
    stripped = _FENCE_TOKENS.sub(FENCE_STRIPPED, text)
    return f"{FENCE_OPEN}\n{stripped}\n{FENCE_CLOSE}"


def _path_matches(path: str, registered: str) -> bool:
    """Compare two paths segment by segment, honouring wildcards.

    Args:
        path: The concrete path built during the walk.
        registered: A registry key, which may hold `*` segments.

    Returns:
        Whether the concrete path is the registered one.
    """
    actual = path.split(PATH_SEPARATOR)
    expected = registered.split(PATH_SEPARATOR)
    if len(actual) != len(expected):
        return False
    return all(
        want in (PATH_WILDCARD, have)
        for have, want in zip(actual, expected, strict=True)
    )


def _lookup(path: str, registry: Mapping[str, Fenced]) -> Fenced | None:
    """Resolve one path against the registry.

    Exact match first, then wildcard. **Exact wins**, so a concrete
    entry is never shadowed by a `*` that happens to also match - which
    is the failure that would make an explicit decision unreachable.

    Args:
        path: The concrete path.
        registry: Path -> `Fenced`.

    Returns:
        The decision, or `None` when the path is unregistered.
    """
    if path in registry:
        return registry[path]
    for registered, decision in registry.items():
        if PATH_WILDCARD in registered and _path_matches(path, registered):
            return decision
    return None


def fence_payload(
    payload: Mapping[str, Any],
    registry: Mapping[str, Fenced],
    prefix: str = "",
) -> dict[str, Any]:
    """Walk a raw Jobvite body and apply the path-keyed decisions.

    **Three outcomes per field, and the third is §8 #20:**

    - the path decides `FENCE` and the value is a `str` -> fenced;
    - the path decides `NOT_FREE_TEXT` -> passed through;
    - **anything else -> DROPPED.** That covers an unregistered path
      (the path-keyed allow-list failing closed, DESIGN.md:1886) *and*
      a `FENCE` decision arriving as a non-string, which cannot be
      fenced and must not be stringified.

    **Dropped means the key is ABSENT from the result**, not present
    carrying a rendered value. §8 #20 asserts the drop rather than the
    type precisely because a stringifying implementation satisfies
    every type assertion perfectly.

    Args:
        payload: One decoded Jobvite object.
        registry: Generated path -> `Fenced`, from `models/fencing.py`.
        prefix: The path accumulated so far. `""` at the top level.

    Returns:
        A new mapping. **The input is never mutated** - a fencer that
        edited its argument in place would fence the payload the audit
        path is about to read.
    """
    out: dict[str, Any] = {}
    for key, value in payload.items():
        path = f"{prefix}{PATH_SEPARATOR}{key}" if prefix else key
        if isinstance(value, Mapping):
            # A container's own decision says its VALUE is not free
            # text; its children answer separately, which is what
            # `models/fencing.py` records for every container field.
            if _lookup(path, registry) is None:
                continue
            out[key] = fence_payload(value, registry, path)
            continue
        if isinstance(value, list):
            if _lookup(path, registry) is None:
                continue
            out[key] = _fence_list(value, registry, f"{path}{LIST_MARKER}")
            continue
        decision = _lookup(path, registry)
        if decision is None:
            # UNREGISTERED. Dropped until someone admits it
            # deliberately - the direction DESIGN.md:1886 requires and
            # the one a deny-list gets backwards.
            continue
        # §9 HAZARD 4 IS APPLIED HERE, AND THE POSITION IS THE POINT.
        # Jobvite uses `""` where a null belongs and both mean absent
        # (DESIGN.md:1465-1466). Unifying AFTER fencing would turn `""`
        # into a fenced empty string - a present value carrying nothing
        # - and the absence the unification exists to express would be
        # gone. So it happens before the decision is applied, in one
        # place, on the whole payload.
        value = blank_to_none(value)
        if value is None:
            # An absence. Dropped, so the model's own `None` default is
            # what the caller sees, rather than an explicit null the
            # allow-list never decided to emit.
            continue
        if decision.decision is FencingDecision.FENCE:
            if not isinstance(value, str):
                # §8 #20. Fencing is defined for strings only, so this
                # field cannot be fenced - and stringifying it invents a
                # representation. Dropped.
                continue
            out[key] = fence_text(value)
            continue
        out[key] = value
    return out


def _fence_list(
    items: Sequence[Any], registry: Mapping[str, Fenced], path: str
) -> list[Any]:
    """Fence one list, element by element, at the `[]` path.

    **A scalar element is subject to the same three outcomes as a
    field**, including the drop: a list of unregistered scalars comes
    back empty rather than passed through, because a container's own
    decision says nothing about its members (`models/fencing.py`).

    Args:
        items: The decoded list.
        registry: Path -> `Fenced`.
        path: The ELEMENT path, already carrying `LIST_MARKER`.

    Returns:
        A new list holding only the elements a decision admitted.
    """
    decision = _lookup(path, registry)
    out: list[Any] = []
    for item in items:
        if isinstance(item, Mapping):
            out.append(fence_payload(item, registry, path))
            continue
        if decision is None:
            continue
        if decision.decision is FencingDecision.FENCE:
            # Strings only (DESIGN.md:824-825); a non-string element is
            # dropped rather than stringified, exactly as a field is.
            if isinstance(item, str):
                out.append(fence_text(item))
            continue
        out.append(item)
    return out
