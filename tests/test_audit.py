"""U3: the audit event, §8 cases #2, #4, #5, #17, and the policy.

**Three of the four §8 cases this file carries are ABSENCE claims, and
each is paired with a positive in the SAME construction** - not merely
somewhere else in the file. DESIGN.md:1361-1364 states the rule for
#4/#5 and this file extends it to #2 and #17:

- **#4 is the positive for #5.** The PII absence is asserted against the
  record #4 proves exists, never against an empty stream.
- **#2's positive is the plan's** (IMPLEMENTATION-PLAN.md:697-705, Q6):
  the same call must emit a record carrying the request's non-secret
  attributes, and the `sc=` value must be absent *from that record*.
  Against a misconfigured logger emitting nothing, the absence alone
  passes and proves nothing. #4 does not supply this pairing - #4 proves
  the *audit event* exists, and #2 is about the loguru stream.
- **#17 needs both arms** (DESIGN.md:1416-1420): a field always absent
  and a field always synthesised each pass a single-arm test, and the
  second is the failure that matters.

**Secret-safe failure output.** As in `test_redaction.py`, every absence
check computes a bool first and asserts on the bool, so a red test
prints `assert not True` rather than the credential it just caught
leaking.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import traceback
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from loguru import logger

from fast_mcp_jobvite import audit
from fast_mcp_jobvite.audit import (
    ATTRIBUTION_UNAVAILABLE,
    AUDIT_EVENT_NAME,
    AuditPhase,
    AuditWriteError,
    Transport,
    attach_audit_warnings,
    audit_scope,
    emit,
    parse_trace_context,
    resolve_request_id,
)
from fast_mcp_jobvite.utils.correlation import request_id_var

FAKE_API = "FAKE-API-KEY-0000"
FAKE_SC = "FAKE-SC-SECRET-1111"
FAKE_COMPANY = "FAKE-COMPANY-2222"

JOB_FEED_URL = (
    "https://api.jobvite.com/api/v2/jobFeed"
    f"?api={FAKE_API}&sc={FAKE_SC}&companyId={FAKE_COMPANY}"
)

#: A candidate, as `create_candidate`'s arguments would carry one.
CANDIDATE_ARGS: dict[str, Any] = {
    "job_id": "job-42",
    "candidate": {
        "firstName": "Ada",
        "lastName": "Lovelace",
        "email": "ada@example.invalid",
        "coverLetter": "I have been working with difference engines.",
    },
}

TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
SPAN_ID = "00f067aa0ba902b7"


@pytest.fixture
def audit_records() -> Iterator[list[dict[str, Any]]]:
    """Capture the real loguru stream this server writes to.

    A capturing sink and not a fake logger: §8 #2's pairing is worth
    nothing if the "log stream" it proves non-empty is one the test
    invented.
    """
    captured: list[dict[str, Any]] = []

    def sink(message: Any) -> None:
        captured.append(dict(message.record))

    sink_id = logger.add(sink, level="DEBUG")
    try:
        yield captured
    finally:
        logger.remove(sink_id)


def _serialise(record: dict[str, Any]) -> str:
    """Flatten a captured record to text.

    A leak anywhere in it is then caught.
    """
    return json.dumps(record, default=repr)


def _leaks(haystack: str, *needles: str) -> bool:
    """True if any secret survived.

    A bool, so a failure prints no secret.
    """
    return any(needle in haystack for needle in needles)


def _emit_one(**kwargs: Any) -> None:
    """Run one complete invocation through the scope and emit it."""
    phase = kwargs.pop("phase", AuditPhase.READ)
    with audit_scope(**kwargs) as event:
        emit(event, phase)


# ----------------------------------------------------------------------
# §8 #4 - the audit event is emitted and carries its mandated fields.
# POSITIVE ON PURPOSE (DESIGN.md:1361-1363).
# ----------------------------------------------------------------------


def test_case4_the_audit_event_is_emitted_at_all(
    audit_records: list[dict[str, Any]],
) -> None:
    _emit_one(tool_name="get_candidate", transport=Transport.HTTP)
    assert len(audit_records) == 1, "no audit record reached the log stream"
    assert audit_records[0]["message"] == AUDIT_EVENT_NAME


def test_case4_the_event_carries_every_mandated_field(
    audit_records: list[dict[str, Any]],
) -> None:
    """Every field the standard names, verbatim.

    `ai/tool-calling.md:171-173`: tool name, redacted arguments, result
    status, latency, correlation id - plus DESIGN.md:1357-1359's
    transport and the resolved client id.
    """
    _emit_one(
        tool_name="get_candidate",
        transport=Transport.HTTP,
        arguments={"candidate_id": "cand-7"},
        client_id="client-abc",
    )
    extra = audit_records[0]["extra"]
    assert extra["tool_name"] == "get_candidate"
    assert extra["result_status"] == "success"
    assert extra["transport"] == "http"
    assert extra["client_id"] == "client-abc"
    assert extra["arguments"] == {"candidate_id": "cand-7"}
    assert isinstance(extra["latency_ms"], float)
    assert uuid.UUID(extra["request_id"]).version == 4


def test_case4_the_field_names_are_wire_shaped_snake_case() -> None:
    """`ai/tool-calling.md:178-179`: the three required fields.

    `tool_name`, `request_id`, `result_status`.
    """
    with audit_scope("get_candidate", Transport.HTTP) as event:
        record = event.to_record()
    for name in ("tool_name", "request_id", "result_status", "latency_ms"):
        assert name in record
    for name in record:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", name), f"{name} is not snake_case"


def test_case4_the_write_records_approval_state_and_its_mechanism(
    audit_records: list[dict[str, Any]],
) -> None:
    """DESIGN.md:1359: `approval_state` WITH the mechanism (§5.3).

    Asserted on the write.
    """
    with audit_scope("create_candidate", Transport.HTTP) as event:
        event.approval_state = "accepted"
        event.approval_mechanism = "elicitation"
        emit(event, AuditPhase.AFTER_WRITE)
    extra = audit_records[0]["extra"]
    assert extra["approval_state"] == "accepted"
    assert extra["approval_mechanism"] == "elicitation"


# ----------------------------------------------------------------------
# §8 #5 - candidate PII never reaches a log or audit record.
# ABSENCE, asserted against the record #4 above proves exists.
# ----------------------------------------------------------------------


def test_case5_candidate_pii_never_reaches_the_audit_record(
    audit_records: list[dict[str, Any]],
) -> None:
    _emit_one(
        tool_name="create_candidate",
        transport=Transport.HTTP,
        arguments=CANDIDATE_ARGS,
        phase=AuditPhase.AFTER_WRITE,
    )
    # The PAIRED POSITIVE, in this same test and on this same record:
    # the stream is non-empty and the record is the one we just caused.
    assert len(audit_records) == 1, "the absence below would pass against silence"
    serialised = _serialise(audit_records[0])
    assert audit_records[0]["extra"]["tool_name"] == "create_candidate"
    assert audit_records[0]["extra"]["arguments"]["job_id"] == "job-42"

    leaked = _leaks(
        serialised,
        "Ada",
        "Lovelace",
        "ada@example.invalid",
        "difference engines",
    )
    assert not leaked, "candidate PII reached the audit record"


def test_case5_the_event_object_itself_never_holds_the_raw_arguments() -> None:
    """Redaction happens on the way IN, not on the way out.

    An event that held the raw arguments and redacted them inside
    `to_record` would pass every assertion above and still print the
    candidate from a traceback, a `repr` or a debugger - all three of
    which read the object.
    """
    with audit_scope(
        "create_candidate", Transport.HTTP, arguments=CANDIDATE_ARGS
    ) as event:
        leaked = _leaks(repr(event), "Ada", "Lovelace", "ada@example.invalid")
    assert not leaked, "the AuditEvent object holds unredacted candidate PII"


# ----------------------------------------------------------------------
# §8 #2 - a secret never reaches a log record, including the whole
# jobFeed URL. ABSENCE, paired with a positive on the SAME record (Q6).
# ----------------------------------------------------------------------


def test_case2_the_sc_value_is_absent_from_a_record_proven_non_empty(
    audit_records: list[dict[str, Any]],
) -> None:
    _emit_one(
        tool_name="get_job_feed",
        transport=Transport.HTTP,
        arguments={"feed_url": JOB_FEED_URL},
        client_id="client-abc",
    )

    # THE PAIRED POSITIVE. Against a misconfigured logger emitting
    # nothing, the absence below passes and proves nothing, so the
    # stream is proven non-empty and proven to carry THIS request's
    # non-secret attributes first.
    assert len(audit_records) == 1, "the log stream was empty; the absence is vacuous"
    extra = audit_records[0]["extra"]
    assert extra["tool_name"] == "get_job_feed"
    assert extra["transport"] == "http"
    assert extra["client_id"] == "client-abc"
    assert uuid.UUID(extra["request_id"]).version == 4

    # THE ABSENCE, on that same record.
    leaked = _leaks(_serialise(audit_records[0]), FAKE_SC, FAKE_API, FAKE_COMPANY)
    assert not leaked, "a jobFeed credential reached the audit log record"


def test_case2_the_whole_url_is_covered_not_just_the_sc_parameter(
    audit_records: list[dict[str, Any]],
) -> None:
    """DESIGN.md:312-318 classifies the URL as sensitive.

    Not one parameter of it.
    """
    _emit_one(
        tool_name="get_job_feed",
        transport=Transport.HTTP,
        arguments={"feed_url": JOB_FEED_URL},
    )
    assert len(audit_records) == 1
    leaked = _leaks(_serialise(audit_records[0]), JOB_FEED_URL)
    assert not leaked, "the whole jobFeed URL reached the audit log record"


def test_case2_a_stderr_failure_report_carries_no_credential(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failure channel is a log record, and formats an exception.

    DESIGN.md:315-318 says never in an exception message. `httpx` puts
    the request URL into the text of the exceptions it raises, so an
    audit-write failure that formats one is exactly where the URL would
    otherwise escape.
    """
    monkeypatch.setattr(audit, "logger", _ExplodingLogger(f"timeout on {JOB_FEED_URL}"))
    with audit_scope("get_job_feed", Transport.HTTP) as event:
        emit(event, AuditPhase.READ)
    err = capsys.readouterr().err
    assert err.strip(), "nothing was written to stderr; the absence would be vacuous"
    leaked = _leaks(err, FAKE_SC, FAKE_API, FAKE_COMPANY)
    assert not leaked, "a credential reached the stderr failure report"


# ----------------------------------------------------------------------
# §8 #17 - trace context, BOTH arms (DESIGN.md:1416-1420).
# ----------------------------------------------------------------------


def test_case17_arm1_trace_context_is_recorded_when_the_caller_supplies_it(
    audit_records: list[dict[str, Any]],
) -> None:
    _emit_one(
        tool_name="get_candidate",
        transport=Transport.HTTP,
        meta={"traceparent": TRACEPARENT},
    )
    extra = audit_records[0]["extra"]
    # The values come FROM the header. Asserting only "a 32-hex string
    # is present" would pass against a synthesised id, which is the
    # failure DESIGN.md:1418-1420 says is the one that matters.
    assert extra["trace_id"] == TRACE_ID
    assert extra["span_id"] == SPAN_ID


def test_case17_arm2_trace_context_is_ABSENT_when_the_caller_supplies_none(
    audit_records: list[dict[str, Any]],
) -> None:
    _emit_one(tool_name="get_candidate", transport=Transport.HTTP, meta=None)
    extra = audit_records[0]["extra"]
    # The paired positive: the record exists and carries its other
    # fields, so this absence is not the absence of a record.
    assert extra["tool_name"] == "get_candidate"
    assert "trace_id" not in extra, "trace_id was synthesised with no inbound header"
    assert "span_id" not in extra, "span_id was synthesised with no inbound header"


def test_case17_the_fields_are_omitted_not_emitted_as_none() -> None:
    """A field always present passes a single-arm test."""
    with audit_scope("get_candidate", Transport.HTTP) as event:
        record = event.to_record()
    assert "trace_id" not in record
    assert "span_id" not in record


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "not-a-traceparent",
        "00-0000000000000000000000000000000-00f067aa0ba902b7-01",  # short trace id
        "00-00000000000000000000000000000000-00f067aa0ba902b7-01",  # all-zero trace
        "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01",  # all-zero span
        "99-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",  # bad version
    ],
)
def test_case17_a_malformed_traceparent_yields_nothing_rather_than_a_guess(
    bad: str,
) -> None:
    assert parse_trace_context({"traceparent": bad}) is None


def test_case17_a_valid_traceparent_parses_the_positive_control() -> None:
    """Without this, the cases above pass against `return None`."""
    assert parse_trace_context({"traceparent": TRACEPARENT}) == (TRACE_ID, SPAN_ID)


# ----------------------------------------------------------------------
# The stdio attribution marker (DESIGN.md:771-776).
# ----------------------------------------------------------------------


def test_stdio_records_the_attribution_marker(
    audit_records: list[dict[str, Any]],
) -> None:
    _emit_one(tool_name="get_candidate", transport=Transport.STDIO)
    extra = audit_records[0]["extra"]
    assert extra["transport"] == "stdio"
    assert extra["caller_attribution"] == ATTRIBUTION_UNAVAILABLE


def test_stdio_never_records_the_literal_global(
    audit_records: list[dict[str, Any]],
) -> None:
    """The implementer error the row exists to prevent.

    `get_client_id` returns `"global"` on stdio. Recording it would
    assert an identity that does not exist, behind a value that looks
    like an answer - so the client id passed in is DISCARDED on this
    transport rather than trusted not to be supplied.
    """
    _emit_one(tool_name="get_candidate", transport=Transport.STDIO, client_id="global")
    record = audit_records[0]
    assert record["extra"]["caller_attribution"] == ATTRIBUTION_UNAVAILABLE
    assert "client_id" not in record["extra"]
    assert "global" not in _serialise(record)
    assert "global" not in ATTRIBUTION_UNAVAILABLE


def test_http_records_the_client_id_and_no_marker(
    audit_records: list[dict[str, Any]],
) -> None:
    """The paired positive: attribution IS recorded when knowable."""
    _emit_one(
        tool_name="get_candidate", transport=Transport.HTTP, client_id="client-abc"
    )
    extra = audit_records[0]["extra"]
    assert extra["client_id"] == "client-abc"
    assert "caller_attribution" not in extra


# ----------------------------------------------------------------------
# The audit-write-failure policy, three arms (DESIGN.md:784-800).
# ----------------------------------------------------------------------


class _ExplodingLogger:
    """A logger whose write always fails.

    Mirrors the real call signature.

    `bind(**fields).info(message)` is exactly how `audit.emit` uses
    loguru, so a change to that call site breaks this fake rather than
    silently bypassing it.
    """

    def __init__(self, message: str = "disk full") -> None:
        self.message = message

    def bind(self, **_fields: object) -> _ExplodingLogger:
        raise OSError(self.message)

    def info(self, _message: str) -> None:  # pragma: no cover - never reached
        raise AssertionError("bind should have raised first")


@pytest.fixture
def broken_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit, "logger", _ExplodingLogger())


def test_arm1_before_the_side_effect_the_call_fails(
    broken_audit: None,
) -> None:
    with audit_scope("create_candidate", Transport.HTTP) as event:
        with pytest.raises(AuditWriteError):
            emit(event, AuditPhase.BEFORE_SIDE_EFFECT)


#: A redactable credential, in the shape `redact_text` is built for: a
#: `jobFeed` URL whose `sc=` parameter is the secret. The sink failure
#: this file simulates carries the URL in its exception message, which
#: is exactly how one reaches `_on_audit_write_failure`.
_LEAKY_SINK_MESSAGE = (
    "connect failed for https://api.jobvite.com/v1/jobFeed"
    "?companyId=c&api=a&sc=SUPERSECRETSC after 3 tries"
)
_SINK_SENTINEL = "SUPERSECRETSC"


def test_arm1_the_raise_does_not_carry_the_unredacted_exception_along(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R2-M-1: `redact_text` cleans the message, `__context__` does not.

    `_on_audit_write_failure` redacts the detail it formats, and then
    raised **from inside an `except` block**, so Python attached the raw
    `OSError` as `__context__` and every formatted traceback printed the
    credential the line above had just removed. `from None` is the whole
    fix; these assertions are what would have noticed.

    Asserted on **bools**, per this module's secret-safe convention: a
    red run must not print the credential it caught leaking.
    """
    monkeypatch.setattr(audit, "logger", _ExplodingLogger(_LEAKY_SINK_MESSAGE))
    with audit_scope("create_candidate", Transport.HTTP) as event:
        with pytest.raises(AuditWriteError) as excinfo:
            emit(event, AuditPhase.BEFORE_SIDE_EFFECT)

    raised = excinfo.value
    # POSITIVE CONTROL for the whole arm: the secret really was in the
    # sink's exception, so an absence below is redaction working rather
    # than a probe that never carried anything.
    assert _SINK_SENTINEL in _LEAKY_SINK_MESSAGE
    # Bools computed FIRST, per this module's secret-safe convention:
    # passing the haystack into the assert prints it on failure, which
    # is the credential these arms exist to catch.
    message_leaks = _leaks(str(raised), _SINK_SENTINEL)
    assert not message_leaks, "the message itself leaks"
    # THE LEAK PATH FIRST, because it is the assertion that has to be
    # able to fail: R2-M-1's own reproduction table read
    # "full traceback: leaks True".
    formatted = "".join(
        traceback.format_exception(type(raised), raised, raised.__traceback__)
    )
    traceback_leaks = _leaks(formatted, _SINK_SENTINEL)
    assert not traceback_leaks, "the raw exception text reached a formatted traceback"
    # And the mechanism that closes it. `from None` sets
    # `__suppress_context__`; it does NOT clear `__context__`, which is
    # still reachable on the object - so the verdict's suggested
    # `assert excinfo.value.__context__ is None` fails against the
    # correct fix. Measured here before it was believed.
    assert raised.__suppress_context__, "the context is not suppressed"


def test_arm2_on_a_read_it_logs_to_stderr_and_continues(
    broken_audit: None, capsys: pytest.CaptureFixture[str]
) -> None:
    with audit_scope("get_candidate", Transport.HTTP) as event:
        warnings = emit(event, AuditPhase.READ)
    assert warnings == [], "a read must not surface a warning to the caller"
    assert "audit write failed" in capsys.readouterr().err


def test_arm3_after_a_successful_write_it_returns_a_warning_not_an_error(
    broken_audit: None, capsys: pytest.CaptureFixture[str]
) -> None:
    with audit_scope("create_candidate", Transport.HTTP) as event:
        warnings = emit(event, AuditPhase.AFTER_WRITE)
    assert len(warnings) == 1
    assert "audit" in warnings[0].lower()
    # The warning goes to stderr TOO, not only to the caller
    # (DESIGN.md:790-791).
    assert "audit write failed" in capsys.readouterr().err


def test_arm3_the_warning_tells_the_caller_not_to_retry(broken_audit: None) -> None:
    """The whole reason this branch exists.

    DESIGN.md:788-790 and DESIGN.md:796-800.

    A retry emails a second live human, so a warning that does not say
    so invites the exact harm the branch was written to prevent.
    """
    with audit_scope("create_candidate", Transport.HTTP) as event:
        warnings = emit(event, AuditPhase.AFTER_WRITE)
    assert "not retry" in warnings[0].lower()


def test_arm3_the_result_is_success_with_a_warnings_array_not_a_problem_object(
    broken_audit: None,
) -> None:
    """The shape, which DESIGN.md:794-800 specifies deliberately.

    "Success with a warning" is not a shape, so the design states one.
    """
    with audit_scope("create_candidate", Transport.HTTP) as event:
        warnings = emit(event, AuditPhase.AFTER_WRITE)
    payload = attach_audit_warnings({"candidate_id": "cand-9"}, warnings)
    assert payload["candidate_id"] == "cand-9"
    assert isinstance(payload["warnings"], list)
    # Not a problem object: none of the seven required members is
    # present.
    for member in ("type", "title", "status", "detail", "instance", "timestamp"):
        assert member not in payload


def test_a_successful_audit_adds_no_warnings_key_at_all(
    audit_records: list[dict[str, Any]],
) -> None:
    """The paired positive for the shape above."""
    with audit_scope("create_candidate", Transport.HTTP) as event:
        warnings = emit(event, AuditPhase.AFTER_WRITE)
    assert warnings == []
    assert len(audit_records) == 1
    assert attach_audit_warnings({"candidate_id": "cand-9"}, warnings) == {
        "candidate_id": "cand-9"
    }


def test_attach_audit_warnings_does_not_mutate_its_input() -> None:
    original: dict[str, Any] = {"candidate_id": "cand-9"}
    attach_audit_warnings(original, ["a warning"])
    assert original == {"candidate_id": "cand-9"}


# ----------------------------------------------------------------------
# request_id: minted here, bound in the same statement, reset on the way
# out.
# ----------------------------------------------------------------------


def test_the_scope_binds_request_id_var_to_the_id_it_minted() -> None:
    with audit_scope("get_candidate", Transport.HTTP) as event:
        assert request_id_var.get() == event.request_id


def test_the_scope_resets_request_id_var_on_the_way_out() -> None:
    """The absence, paired with the positive above.

    Built in the same construction.
    """
    with audit_scope("get_candidate", Transport.HTTP):
        pass
    assert request_id_var.get() is None


def test_the_scope_resets_request_id_var_even_when_the_body_raises() -> None:
    with pytest.raises(ValueError, match="boom"):
        with audit_scope("get_candidate", Transport.HTTP):
            raise ValueError("boom")
    assert request_id_var.get() is None


def test_audit_scope_calls_request_id_scope_rather_than_setting_the_var_itself() -> (
    None
):
    """N1's resolution, asserted rather than described.

    `utils/correlation.py`'s `request_id_scope` was called by nothing.
    U3 calls it, and this test is what stops a later edit quietly
    replacing it with a bare `request_id_var.set()` and losing the
    `finally`.

    **Read through the AST, not with a substring search over the file.**
    The first version of this test did the latter, and the amputation
    harness caught it: `A7` deleted the call outright and this assertion
    still passed, because the module DOCSTRING quotes that exact line as
    the proof that the mint and the bind are one statement. The test was
    asserting that the documentation existed. An AST walk sees code and
    cannot see prose.
    """
    tree = ast.parse(pathlib.Path(audit.__file__).read_text(encoding="utf-8"))
    scope_fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "audit_scope"
    )
    entered = [
        item.context_expr.func.id
        for node in ast.walk(scope_fn)
        if isinstance(node, ast.With)
        for item in node.items
        if isinstance(item.context_expr, ast.Call)
        and isinstance(item.context_expr.func, ast.Name)
    ]
    assert "request_id_scope" in entered, (
        "audit_scope no longer enters request_id_scope; the finally that resets "
        "the var lives there and nowhere else"
    )
    direct_sets = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "set"
        and isinstance(node.value, ast.Name)
        and node.value.id == "request_id_var"
    ]
    assert not direct_sets, "audit.py sets request_id_var directly, bypassing the scope"


@pytest.mark.parametrize(
    "inbound",
    [
        "11111111-1111-4111-8111-111111111111",
        # THE ROW THAT MAKES THIS TEST ABLE TO FAIL. R2's nit-4: the
        # literal above is all digits and hyphens, so `.lower()` is the
        # identity on it and deleting the call from
        # `resolve_request_id` left the whole suite green. Only a
        # literal carrying a LETTER in upper case can tell "echoed" from
        # "echoed lower-cased" apart.
        "A1B2C3D4-1111-4111-8111-11111111CDEF",
    ],
)
def test_a_valid_inbound_uuid4_is_echoed_unchanged(inbound: str) -> None:
    """The caller's id comes back byte for byte, case included.

    `_UUID4_RE` is `IGNORECASE`, so case was never a validity question,
    and an operator joining a log line to a caller's record does it by
    exact string match. Canonicalising a value we were asked to echo
    breaks that join for no stated requirement.
    """
    assert resolve_request_id(inbound) == inbound


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "",
        "not-a-uuid",
        "11111111-1111-4111-8111-111111111111\ninjected=audit_bypass",
        # A BARE trailing newline. NOT a duplicate of the row
        # above: Python's `$` matches immediately before a
        # trailing newline and `\Z` does not, so relaxing the
        # anchor by one character reopens C7-T1 - and the row
        # above cannot see it, because the text after ITS
        # newline breaks the match either way. Measured: with
        # `$` for `\Z` this module passed 43/43 while
        # resolve_request_id echoed the value back.
        "11111111-1111-4111-8111-111111111111\n",
        "11111111-1111-1111-8111-111111111111",  # v1, not v4
        "11111111-1111-4111-c111-111111111111",  # bad variant nibble
    ],
)
def test_an_invalid_inbound_request_id_is_replaced_rather_than_used(
    bad: str | None,
) -> None:
    """C7-T1: a newline in the inbound id forges a log entry.

    DESIGN.md:1895.
    """
    resolved = resolve_request_id(bad)
    assert resolved != bad
    assert uuid.UUID(resolved).version == 4


def test_two_invocations_get_different_ids() -> None:
    """A module global would give both the same id, silently."""
    with audit_scope("get_candidate", Transport.HTTP) as first:
        pass
    with audit_scope("get_candidate", Transport.HTTP) as second:
        pass
    assert first.request_id != second.request_id


def test_every_event_field_reaches_the_record() -> None:
    """R3-L3: `to_record`'s field list is a second enumeration.

    `AuditEvent` is a dataclass, so its fields are the container.
    `to_record` names them again in two dict literals, and a field added
    to the dataclass and not to the literals is simply ABSENT from every
    audit record - silently. The record still validates, still parses,
    still looks well formed, and the missing field is one nobody asked
    for by name until an incident.

    This is the same shape as R3-L1 (`TOOL_REQUIREMENTS` beside
    `KNOWN_TOOLS`) and the same one `fix-audit-logging` cited when it
    chose `serialize=True` over an `{extra}` format string: a hand-kept
    list beside the thing it is supposed to describe. Nothing enumerated
    the container - `dataclasses.fields` appeared nowhere in the suite.

    `started_at` is excluded deliberately: it is the input to
    `latency_ms()`, not a wire field.
    """
    import dataclasses

    with audit_scope("search_jobs", Transport.HTTP, client_id="c") as event:
        # Every optional field set to something non-None. `to_record`
        # drops None values, so an event built with defaults would let
        # this pass while the literals omitted half the container.
        event.trace_id = "a" * 32
        event.span_id = "b" * 16
        event.approval_state = "not_applicable"
        event.approval_mechanism = "none"
        event.result_status = "success"
        emitted = set(event.to_record())

    declared = {f.name for f in dataclasses.fields(event)} - {"started_at"}
    missing = declared - emitted
    assert not missing, (
        f"these AuditEvent fields never reach the audit record: {sorted(missing)}. "
        "Add them to to_record, or say in a comment why they are not wire fields."
    )


def test_the_field_check_is_not_vacuous() -> None:
    """The control for the test above.

    If `dataclasses.fields` returned nothing, or the event carried no
    optional values, the assertion would pass over an empty set and
    prove nothing. Both counts are pinned here rather than in the test
    itself, so a change that empties either one fails HERE with a clear
    reason instead of quietly weakening the check next door.
    """
    import dataclasses

    with audit_scope("search_jobs", Transport.HTTP) as event:
        declared = {f.name for f in dataclasses.fields(event)}
        assert len(declared) > 5, (
            f"AuditEvent declares only {len(declared)} fields; the field "
            "check next door would be nearly vacuous"
        )
        assert "started_at" in declared, (
            "started_at is excluded by name in the check next door; if it "
            "no longer exists, that exclusion is silently doing nothing"
        )
