"""The single redaction point (DESIGN.md:312-318, §8 required case #2).

**Every assertion in this file is written so a FAILURE cannot print the
secret it was checking for.** The obvious form,

    assert FAKE_SC not in line

fails by printing both operands, so the test that exists to prove a
credential never reaches a log record publishes it into CI's output the
moment it goes red - and it goes red exactly when a credential *is*
leaking, which is the worst possible moment. Every check below therefore
computes a bool first and asserts on the bool, so the failure output is
`assert not True`.

**Nothing here is a real credential.** These are the shapes, not the
values.
"""

from __future__ import annotations

import ast
import logging
import pathlib
import subprocess
import sys
from collections.abc import Iterator

import httpx2
import pytest
from pydantic import SecretStr

from fast_mcp_jobvite.services.jobvite_client import JobviteClient
from fast_mcp_jobvite.utils import redaction
from fast_mcp_jobvite.utils.redaction import (
    HTTPX_LOGGER_NAME,
    NON_SENSITIVE_ARGUMENT_KEYS,
    REDACTED,
    SECRET_HEADERS,
    SECRET_QUERY_PARAMS,
    RedactingLogFilter,
    install_log_redaction,
    redact_arguments,
    redact_headers,
    redact_text,
    redact_url,
)

from .conftest import REPO_ROOT

#: Obvious non-values. `CONTRIBUTING.md:133-135` forbids a real tenant
#: id, client name or credential anywhere in the repository, tests
#: included.
FAKE_API = "FAKE-API-KEY-0000"
FAKE_SC = "FAKE-SC-SECRET-1111"
FAKE_COMPANY = "FAKE-COMPANY-2222"

JOB_FEED_URL = (
    "https://api.jobvite.com/api/v2/jobFeed"
    f"?api={FAKE_API}&sc={FAKE_SC}&companyId={FAKE_COMPANY}&page=2"
)


def _leaks(haystack: str, *needles: str) -> bool:
    """True if any secret survived.

    Returns a bool so a failure prints no secret.
    """
    return any(needle in haystack for needle in needles)


# ----------------------------------------------------------------------
# redact_url - the absence, and its paired positive
# ----------------------------------------------------------------------


def test_the_whole_jobFeed_url_loses_every_credential_parameter() -> None:
    out = redact_url(JOB_FEED_URL)
    leaked = _leaks(out, FAKE_API, FAKE_SC, FAKE_COMPANY)
    assert not leaked, "a credential query parameter survived redact_url"


def test_redact_url_is_not_vacuous_it_returns_a_usable_url() -> None:
    """The paired positive for the absence above.

    A `redact_url` that returned `""`, or that dropped the query string
    entirely, would pass the absence test and destroy the debugging
    value the design keeps. This arm pins what must SURVIVE.
    """
    out = redact_url(JOB_FEED_URL)
    assert out.startswith("https://api.jobvite.com/api/v2/jobFeed?")
    assert "page=2" in out
    assert out.count(REDACTED) == 3
    # The parameter NAMES survive: which credentials were on the URL is
    # not itself a secret, and losing them makes the redacted URL
    # unreadable.
    for name in ("api=", "sc=", "companyId="):
        assert name in out


def test_parameter_order_is_preserved() -> None:
    out = redact_url(JOB_FEED_URL)
    names = [pair.split("=")[0] for pair in out.split("?", 1)[1].split("&")]
    assert names == ["api", "sc", "companyId", "page"]


def test_uppercase_parameter_names_are_still_redacted() -> None:
    """A case-sensitive redactor fails open on a hand-made URL."""
    out = redact_url(f"https://example.invalid/jobFeed?SC={FAKE_SC}&API={FAKE_API}")
    leaked = _leaks(out, FAKE_SC, FAKE_API)
    assert not leaked, "an upper-cased credential parameter survived redact_url"


def test_a_url_with_no_query_is_returned_unchanged() -> None:
    url = "https://api.jobvite.com/api/v2/candidate"
    assert redact_url(url) == url


def test_a_url_carrying_no_secret_is_untouched() -> None:
    """Positive control: the redactor does not mangle innocent URLs.

    DESIGN.md:1451-1452 - a guard that refuses everything is not a
    guard.
    """
    url = "https://api.jobvite.com/api/v2/jobs?count=50&start=0"
    assert redact_url(url) == url


# ----------------------------------------------------------------------
# redact_text - the exception-message arm (DESIGN.md:315-318)
# ----------------------------------------------------------------------


def test_a_url_embedded_in_an_exception_message_is_redacted() -> None:
    message = (
        f"ReadTimeout: timed out requesting {JOB_FEED_URL} after 10s; "
        "retrying attempt 2"
    )
    out = redact_text(message)
    leaked = _leaks(out, FAKE_API, FAKE_SC, FAKE_COMPANY)
    assert not leaked, "a credential survived redaction of an exception message"


def test_redact_text_keeps_the_rest_of_the_message_intact() -> None:
    """Paired positive: the message is still the message.

    A `redact_text` that returned `"[REDACTED]"` for the whole string
    would pass the absence arm above and destroy every log line in the
    server.
    """
    message = (
        f"ReadTimeout: timed out requesting {JOB_FEED_URL} after 10s; "
        "retrying attempt 2"
    )
    out = redact_text(message)
    assert out.startswith("ReadTimeout: timed out requesting https://")
    assert out.endswith("after 10s; retrying attempt 2")


@pytest.mark.parametrize("closer", ["'", '"', ")", ",", ".", "),", '".'])
def test_redact_text_keeps_the_punctuation_that_closed_the_url(closer: str) -> None:
    """R2-nit-3: the closing delimiter was eaten with the secret.

    `redact_text` splits on whitespace, so a URL quoted or parenthesised
    in a message arrives as ONE token with the closing character stuck
    to the last query value. `redact_url` then replaced that whole value
    - closing character included - and the message came back
    `...&sc=[REDACTED] then stop.`, an unbalanced quote and a missing
    comma.

    It never un-redacted anything, which is why it is a nit. It matters
    for the reason `redaction.py:104-108` gives about preserving
    parameter order: a redacted line that is not a faithful rendering of
    the original is one people stop trusting, and a truncated URL in an
    incident is read as truncation rather than as redaction.
    """
    message = f"see {JOB_FEED_URL}{closer} then stop"
    out = redact_text(message)
    leaked = _leaks(out, FAKE_API, FAKE_SC, FAKE_COMPANY)
    assert not leaked, "a credential survived redaction"
    assert out == f"see {redact_url(JOB_FEED_URL)}{closer} then stop"


@pytest.mark.parametrize("tail", [".", ")", ",", "'"])
def test_punctuation_INSIDE_the_secret_is_still_redacted(tail: str) -> None:
    """The other side of the fix, and the one it could get wrong.

    Stripping trailing punctuation before redacting must not leave a
    value that genuinely ENDS in one partly in the clear. The whole
    secret is gone either way; what survives is a single character that
    is indistinguishable from the delimiter case above and carries
    nothing.
    """
    secret = f"{FAKE_SC}{tail}"
    out = redact_text(f"see https://api.jobvite.com/x?sc={secret} then stop")
    leaked = _leaks(out, FAKE_SC)
    assert not leaked, "the secret survived because its own tail was stripped off"


def test_redact_text_preserves_newlines_so_a_traceback_survives() -> None:
    message = f"line one\n  {JOB_FEED_URL}\nline three"
    out = redact_text(message)
    assert out.startswith("line one\n  https://")
    assert out.endswith("\nline three")
    assert out.count("\n") == 2


# ----------------------------------------------------------------------
# redact_headers - the v2 credential headers (DESIGN.md:312)
# ----------------------------------------------------------------------


def test_the_v2_credential_headers_are_redacted() -> None:
    out = redact_headers(
        {"x-jvi-api": FAKE_API, "X-JVI-SC": FAKE_SC, "accept": "application/json"}
    )
    leaked = _leaks("".join(out.values()), FAKE_API, FAKE_SC)
    assert not leaked, "a v2 credential header survived redact_headers"


def test_redact_headers_keeps_non_secret_headers_and_does_not_mutate() -> None:
    original = {"x-jvi-api": FAKE_API, "accept": "application/json"}
    out = redact_headers(original)
    assert out["accept"] == "application/json"
    assert original["x-jvi-api"] == FAKE_API, "redact_headers mutated the live request"


# ----------------------------------------------------------------------
# redact_arguments - fail-closed by allow-list
# ----------------------------------------------------------------------


def test_an_unlisted_argument_key_is_redacted() -> None:
    """Fail closed.

    The argument nobody thought of is the one that leaks.
    """
    out = redact_arguments({"firstName": "Ada", "email": "ada@example.invalid"})
    leaked = _leaks(repr(out), "Ada", "ada@example.invalid")
    assert not leaked, "an unlisted argument value survived redact_arguments"


def test_a_key_added_by_a_later_tool_is_redacted_without_anyone_updating_this() -> None:
    """The property that makes the allow-list direction worth its cost.

    A deny-list would emit this in the clear; the fail-closed set
    redacts it until someone adds the key deliberately.
    """
    out = redact_arguments({"someFieldInventedInU10": "a resume body"})
    leaked = _leaks(repr(out), "a resume body")
    assert not leaked, "a newly invented argument key was emitted in the clear"


def test_allow_listed_keys_survive_so_the_event_is_still_auditable() -> None:
    """Paired positive.

    A `redact_arguments` that redacted EVERYTHING would pass both
    absence arms above and make the audit event useless - it would
    record that a call happened and nothing about which one.
    """
    out = redact_arguments({"candidate_id": "cand-123", "limit": 50})
    assert out == {"candidate_id": "cand-123", "limit": 50}


def test_the_redacted_marker_names_the_type_but_not_the_value() -> None:
    out = redact_arguments({"coverLetter": "please hire me", "age": 31})
    assert out == {"coverLetter": "[REDACTED:str]", "age": "[REDACTED:int]"}


def test_a_candidate_one_level_down_is_not_emitted() -> None:
    out = redact_arguments(
        {"candidate": {"firstName": "Ada", "contact": {"email": "a@example.invalid"}}}
    )
    leaked = _leaks(repr(out), "Ada", "a@example.invalid")
    assert not leaked, "PII nested inside an argument survived redact_arguments"


def test_a_container_under_an_unlisted_key_is_redacted_WHOLE() -> None:
    """The allow-list is path-keyed, not leaf-keyed.

    **Found by the mutation harness, not by reading.** `M14` removed the
    container walk and the suite stayed green, which meant the walk was
    not doing what the test above believed. It was descending into a
    container whose OWN key nothing had allowed, and then emitting any
    leaf that happened to carry an allow-listed name - so `job_id`
    escaped from inside a blob called `secretBlob`.

    DESIGN.md:1886 describes C6-I2's mechanism as a **path-keyed**
    allow-list for this reason: membership is a property of the path,
    not of the leaf name in isolation.
    """
    out = redact_arguments({"secretBlob": {"job_id": "job-42", "email": "a@b.invalid"}})
    assert out == {"secretBlob": "[REDACTED:dict]"}
    leaked = _leaks(repr(out), "job-42", "a@b.invalid")
    assert not leaked, "a leaf escaped from inside an unlisted container"


def test_a_list_under_an_unlisted_key_is_redacted_WHOLE() -> None:
    out = redact_arguments({"candidates": [{"lastName": "Lovelace"}]})
    assert out == {"candidates": "[REDACTED:list]"}
    leaked = _leaks(repr(out), "Lovelace")
    assert not leaked, "PII inside a list argument survived redact_arguments"


def test_a_container_under_an_ALLOW_LISTED_key_is_still_walked() -> None:
    """The paired positive for the two absences above.

    A `redact_arguments` that replaced EVERY container with a marker
    would pass both, and would stop the walk being reachable at all -
    which is how a fix for an over-permissive rule quietly becomes dead
    code.
    """
    out = redact_arguments({"job_id": ["job-1", "job-2"]})
    assert out == {"job_id": ["job-1", "job-2"]}


def test_the_allow_list_does_not_contain_query() -> None:
    """`search_candidates`'s query is free text.

    And a name is what you search for.
    """
    assert "query" not in NON_SENSITIVE_ARGUMENT_KEYS


def test_redact_arguments_does_not_mutate_its_input() -> None:
    original = {"firstName": "Ada"}
    redact_arguments(original)
    assert original == {"firstName": "Ada"}


# Userinfo credentials, which the query-parameter arm cannot reach.
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "https://user:hunter2@proxy.internal:8080/path",
        "proxy error: http://svc:hunter2@10.0.0.1:3128 refused",
        "ProxyError connecting via socks5://me:hunter2@127.0.0.1:1080",
    ],
)
def test_redact_text_redacts_a_userinfo_password(message: str) -> None:
    """`scheme://user:password@host` - the `?`/`=` arm never saw it.

    **This was a surviving mutation.** `redact_text` only passed a token
    to `redact_url` when it contained BOTH `?` and `=`, and a proxy URL
    has neither - so it went through whole. An httpx proxy
    misconfiguration puts exactly that string into an exception message,
    and that message reaches the caller's problem `detail`.

    Measured before the fix:
    `https://user:hunter2@proxy.internal:8080/path` came back
    byte-identical.
    """
    out = redact_text(message)
    assert "hunter2" not in out, f"the userinfo password survived: {out}"
    assert REDACTED in out, f"nothing was redacted at all: {out}"


def test_redact_text_keeps_the_username_which_is_the_diagnosis() -> None:
    """The password is the secret; the user aids readability.

    The same split this project applies to a failing assertion, where
    the variable NAME is printed and its value is not.
    """
    out = redact_text("https://svcaccount:hunter2@proxy.internal/x")
    assert "svcaccount" in out, f"the username was destroyed with the password: {out}"
    assert "hunter2" not in out


@pytest.mark.parametrize(
    "message",
    [
        "mail someone@example.com about it",
        "contact first.last@jobvite.com",
        "no url here at all",
        "a bare host:port like proxy.internal:8080",
    ],
)
def test_redact_text_leaves_a_non_credential_at_sign_alone(message: str) -> None:
    """The false-positive arm: why the pattern requires a scheme.

    An email address has an `@` and no `://`, so a looser pattern would
    redact correspondence and ordinary prose. Without this arm the fix
    above could be "redact everything containing an at-sign", which
    passes every assertion in the test above while destroying the
    messages it is meant to keep readable.
    """
    assert redact_text(message) == message


# The walk matches the DECLARED type, not `list` (round 2's M-7).
# ----------------------------------------------------------------------


def test_a_tuple_is_walked_like_a_list() -> None:
    """`JsonValue` declares `Sequence`; the walk tested `list`.

    **A tuple is a `Sequence` and therefore in contract**, so it fell
    through to `return arguments` unredacted at the top level. Measured
    before the fix: `redact_arguments(({"email": "a@b.c"},))` returned
    the address untouched while the identical list redacted it. A
    pydantic field typed `tuple[...]` is all it takes to reach this.

    The nested case was safe only by accident - a tuple under an
    UNLISTED key hits `_redacted_value` and becomes `[REDACTED:tuple]` -
    so the leak needed an allow-listed key or the top level.
    """
    assert redact_arguments(({"email": "a@b.c"},)) == [{"email": "[REDACTED:str]"}]


def test_a_string_is_not_walked_character_by_character() -> None:
    """The guard on the fix, without which it is worse than the defect.

    `str` and `bytes` are `Sequence`s too. Matching `Sequence` without
    excluding them turns every string argument into a list of
    one-character strings, which would pass a "the tuple is redacted"
    assertion while corrupting every ordinary value the audit event
    carries.
    """
    assert redact_arguments("plain string") == "plain string"
    assert redact_arguments(b"raw") == b"raw"
    assert redact_arguments({"note": "hello"}) == {"note": "[REDACTED:str]"}


def test_a_credential_is_not_non_sensitive_on_one_path_and_secret_on_another() -> None:
    """R2-H5: `companyId` was in BOTH lists, and they disagreed.

    `SECRET_QUERY_PARAMS` redacted it in a URL while
    `NON_SENSITIVE_ARGUMENT_KEYS` published it in the clear as a tool
    argument - two lists eighty lines apart in one module, disagreeing
    about one credential. It survived two review rounds because nothing
    compared them.

    This asserts the general property rather than the one instance, so a
    future key admitted to both is caught the same way. Compared
    case-insensitively: the query set is lower-cased by convention and
    the argument set is not, which is part of how the two stayed out of
    each other's sight.
    """
    argument_keys = {key.lower() for key in NON_SENSITIVE_ARGUMENT_KEYS}
    secret_params = {key.lower() for key in SECRET_QUERY_PARAMS}
    secret_headers = {key.lower() for key in SECRET_HEADERS}

    both = argument_keys & (secret_params | secret_headers)
    assert not both, (
        f"these keys are declared BOTH non-sensitive as arguments and secret "
        f"elsewhere in this module: {sorted(both)}. One of the two is wrong, "
        "and the value is published in the clear on whichever path admits it."
    )


def test_company_id_is_redacted_as_an_argument() -> None:
    """The specific case, kept beside the general one deliberately.

    The property test above passes if BOTH lists lose the key. This one
    fails unless `companyId` is genuinely treated as a credential, so
    "fixing" the property test by deleting the entry from
    `SECRET_QUERY_PARAMS` would go red here.
    """
    assert redact_arguments({"companyId": "ACME123"}) == {"companyId": "[REDACTED:str]"}
    assert "ACME123" not in redact_url(
        "https://api.jobvite.com/v1/jobFeed?api=k&sc=s&companyId=ACME123"
    )


# ----------------------------------------------------------------------
# ADR-0026: the EMBEDDER's half. `JobviteClient.__init__` installs the
# filter, and the install is IDEMPOTENT.
#
# **The shipped server was never exposed.** `configure_logging()` runs
# at `__main__` module scope on every shipped path. These cases are
# about a process that never imports it.
# ----------------------------------------------------------------------


@pytest.fixture
def httpx_logger() -> Iterator[logging.Logger]:
    """`httpx2`'s logger, left as it was found.

    **The filter list is PROCESS GLOBAL, and it arrives here already
    populated.** Measured: these four cases passed run alone and FAILED
    in the full suite, because every other module that constructs a
    `JobviteClient` - `test_jobvite_client`, `test_tools_job_feed`,
    `test_resilience` - installs the filter as a side effect and it
    outlives them. So the fixture CLEARS ours on the way in as well as
    restoring the process's own list on the way out; snapshotting alone
    would leave each case reading whatever ran before it.

    The restore puts back exactly what was there, ours included, so
    this fixture cannot itself become the reason a later case sees no
    filter.
    """
    logger = logging.getLogger(HTTPX_LOGGER_NAME)
    before = list(logger.filters)
    logger.filters = [f for f in before if not isinstance(f, RedactingLogFilter)]
    try:
        yield logger
    finally:
        logger.filters = before


def _ours(logger: logging.Logger) -> list[logging.Filter]:
    """OUR filters on a logger, counted by type.

    By type rather than by `len(logger.filters)`: a filter somebody
    else installed is not our leak, and a raw length would blame us for
    it.
    """
    return [f for f in logger.filters if isinstance(f, RedactingLogFilter)]


def _client(**kwargs: object) -> JobviteClient:
    """One client over a transport that answers everything."""
    return JobviteClient(
        api_key=SecretStr(FAKE_API),
        api_secret=SecretStr(FAKE_SC),
        company_id=SecretStr(FAKE_COMPANY),
        transport=httpx2.MockTransport(lambda _r: httpx2.Response(200, json={})),
        **kwargs,  # type: ignore[arg-type]
    )


def test_the_logger_guarded_is_the_one_the_library_actually_logs_through(
    httpx_logger: logging.Logger,
) -> None:
    """`httpx2`, not `httpx` (ADR-0007), asserted against the library.

    **A filter installed on the wrong logger is accepted by `logging`
    without complaint, never fires, and leaves the leak exactly as
    measured.** Every arm of every other case here would still pass:
    they would install on a logger nothing writes to, observe one
    filter on it, and observe no credentials in a stream that never
    carried any. This is the one case that reads the library rather
    than our own constant.

    **THE FIRST ASSERTION IS NOW A TAUTOLOGY, AND THAT IS THE POINT**
    (R11-M1). `HTTPX_LOGGER_NAME` used to be the literal `"httpx2"`,
    and this line was the only thing standing between a typo and a
    silently dead filter. ADR-0026 requires the name DERIVED from the
    imported module rather than retyped - *"the package is vendored as
    `httpx2` and a future rename would silently detach the filter
    again"* - and now it is, so both sides are the same object's name
    by construction.

    It is kept, with a **source-level** assertion beside it, because
    the regression it now guards against - someone retyping the
    literal - cannot be caught at runtime at all. **My first attempt
    was `HTTPX_LOGGER_NAME is _httpx2_logger.name`, and it SURVIVED
    the amputation**: CPython interns short identifier-shaped string
    literals, so `"httpx2" is logger.name` is `True` and the identity
    check passes against exactly the code it was written to refuse. A
    guard whose subject is what the SOURCE says has to read the
    source. The BEHAVIOURAL claim - that a credential-bearing record
    comes out redacted - is the inverted probe's, which is what
    ADR-0026 says the assertion has to be.
    """
    assert HTTPX_LOGGER_NAME == httpx2._client.logger.name  # noqa: SLF001

    module = ast.parse(pathlib.Path(redaction.__file__).read_text(encoding="utf-8"))
    assigned = [
        node.value
        for node in ast.walk(module)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "HTTPX_LOGGER_NAME"
        and node.value is not None
    ]
    assert len(assigned) == 1, (
        f"found {len(assigned)} annotated assignments to HTTPX_LOGGER_NAME; "
        "the search is broken and a green here would mean nothing"
    )
    assert isinstance(assigned[0], ast.Attribute), (
        "HTTPX_LOGGER_NAME is assigned "
        f"{type(assigned[0]).__name__}, not an attribute of the imported "
        "module. It has been retyped as a literal, which ADR-0026 forbids: "
        "a literal detaches silently when the package is renamed, and no "
        "runtime comparison can see the difference because CPython interns "
        "the literal to the same object."
    )


async def test_building_many_clients_leaves_exactly_one_redaction_filter(
    httpx_logger: logging.Logger,
) -> None:
    """ADR-0026's ruling: the install must be IDEMPOTENT.

    **"The filter is installed" is not the property.** That passes on
    the FIRST construction and says nothing about the twentieth.
    `JobviteClient` is built once per invocation - `jobvite_client.py`
    says so where it explains why the breaker is module-level - from
    three call sites, so an unguarded `addFilter` in `__init__` stacks
    one filter per tool call for the life of a long-running server, and
    every record on that logger then walks a list that grows without
    bound. A slow leak inside the change written to stop a leak.

    A test that built two or three clients would not see it, which is
    exactly why this one builds twenty.

    **The `== 1` is paired with a growing control below**, because a
    counter that reads the wrong logger also returns a constant.
    """
    assert not _ours(httpx_logger), "a filter of ours was already installed"
    for _ in range(20):
        client = _client()
        await client.aclose()
    assert len(_ours(httpx_logger)) == 1


def test_the_filter_count_can_read_growth_at_all(
    httpx_logger: logging.Logger,
) -> None:
    """The positive control for the case above.

    `== 1` is satisfied perfectly by an instrument that can only ever
    return 1 - one that reads a logger nothing installs onto, or whose
    isinstance check matches nothing. Appending by hand makes the list
    grow on purpose, so the assertion above is known to be a reading of
    a live list.
    """
    for _ in range(20):
        httpx_logger.addFilter(RedactingLogFilter())
    assert len(_ours(httpx_logger)) == 20


async def test_the_opt_out_is_honoured_and_installs_nothing(
    httpx_logger: logging.Logger,
) -> None:
    """ADR-0026: an embedder may decline the side effect.

    A library mutating a host's global logging configuration from a
    constructor is something an embedder is entitled to object to. The
    default installs because a credential leak is the worse default;
    the keyword is what makes the exposure a choice they made.

    **A constructor argument and never a `Settings` field** (ADR-0025).
    """
    client = _client(install_log_redaction=False)
    await client.aclose()
    assert not _ours(httpx_logger)


def test_install_log_redaction_reports_whether_it_installed(
    httpx_logger: logging.Logger,
) -> None:
    """The second call must be a no-op, and must SAY it was one.

    The return value is what makes idempotence observable without
    reaching into `logger.filters`, and it is the value the constructor
    ignores - so it is asserted here rather than nowhere.
    """
    assert install_log_redaction() is True
    assert install_log_redaction() is False
    assert len(_ours(httpx_logger)) == 1


def test_the_filter_redacts_a_credential_carried_in_a_records_ARGS() -> None:
    """The shape `httpx2` emits, not the shape easiest to test.

    `httpx2` calls `logger.info("HTTP Request: %s %s ...", method, url,
    ...)`, so the URL is in `record.args` and `record.msg` is a format
    string carrying no credential at all. A filter that redacted only
    `record.msg` would pass an `assert REDACTED in record.msg` written
    against a pre-formatted message and leak every real record.
    """
    record = logging.LogRecord(
        name=HTTPX_LOGGER_NAME,
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="HTTP Request: %s %s",
        args=("GET", JOB_FEED_URL),
        exc_info=None,
    )
    assert RedactingLogFilter().filter(record) is True
    assert not _leaks(record.getMessage(), FAKE_API, FAKE_SC, FAKE_COMPANY)
    assert REDACTED in record.getMessage()


def test_the_embedder_leak_probe_still_reproduces_its_measurements() -> None:
    """`docs/reviews/probe-u12-f2-embedder-leak.py`, run not cited.

    **The probe is the artefact behind ADR-0026's claim, and prose
    about a measurement decays into a claim about one.** It ran
    UNWIRED while it demonstrated the defect, because gating on it
    would have gated on the bug staying; now that it asserts the fix it
    gates, the way `probe-scan-bounds.py` and the breaker probes do.

    **A SUBPROCESS, and not for tidiness.** The probe's precondition is
    that `fast_mcp_jobvite.__main__` has never been imported - if it
    has, `configure_logging()` has run and the probe measures the
    SHIPPED path instead of an embedder's, which is the one thing it is
    not for. It aborts with exit 2 rather than passing, but in-process
    it would abort every time: this suite imports plenty. A fresh
    interpreter is the only place the experiment is valid.
    """
    probe = REPO_ROOT / "docs" / "reviews" / "probe-u12-f2-embedder-leak.py"
    assert probe.is_file(), f"the probe is missing at {probe}"
    result = subprocess.run(  # noqa: S603 - a committed script, no shell
        [sys.executable, str(probe)],
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
