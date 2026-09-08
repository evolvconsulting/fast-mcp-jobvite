"""The audit event, and where `request_id` originates (§5.3).

`ai/agent-guardrails.md:40` mandates audit logging of every tool
invocation and `ai/tool-calling.md:171-173` names the fields. **We emit
this ourselves rather than assuming middleware provides it**
(DESIGN.md:649-653): `StructuredLoggingMiddleware` runs with
`include_payloads=False`, which emits *no* arguments where the mandated
field is *redacted* arguments, so the framework's default is wrong for
this project in the one way that matters.

**`request_id` originates here** (DESIGN.md:655-657). MCP has no
`X-Request-ID` middleware and no ambient request id, so this module
mints a UUIDv4 per tool invocation and it is the same value that reaches
the problem object's `request_id` and its `instance` URN.

**The id is minted and bound in ONE statement** (DESIGN.md:664-666),
which is literally true of the single line in `audit_scope`:

    with request_id_scope(resolve_request_id(inbound_request_id)) as
    request_id:

`resolve_request_id` mints, `request_id_scope` binds, and the `finally`
that resets the var lives in `utils/correlation.py` in shipped code
rather than being restated at each call site.

**Attribution is not the same question as identity**
(DESIGN.md:766-778). Two identities are in play and the design is
explicit that only one is knowable: *who approved* is unknowable
(ADR-0009), while *which client invoked the tool* is knowable **on
HTTP**, where §4.4 already derives it through `get_client_id` to
rate-limit on it. On stdio there is no token and therefore no client
identity, so the event carries `caller_attribution` naming the reason,
and **never the literal `"global"`** - an implementer who wires
`get_client_id` on stdio, receives `"global"` and believes attribution
exists leaves the gap open behind a value that looks like an answer.

**`trace_id` and `span_id` are recorded when present, omitted when
absent, and never synthesised** (DESIGN.md:728-729,
`ai/tool-calling.md:176-177`). A locally minted id in a field named for
the host's trace joins nothing while looking like it does, which is
worse than an empty field.
"""

from __future__ import annotations

import dataclasses
import enum
import re
import sys
import time
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Final

from loguru import logger

from .utils.correlation import request_id_scope, request_id_var
from .utils.redaction import JsonValue, redact_arguments, redact_text

#: The message every audit record carries, so the audit stream is
#: greppable as one thing. The mandated fields travel as structured
#: `extra`, not inside this string: `ai/tool-calling.md:178-179`
#: requires wire-shaped snake_case fields, and a message you have to
#: parse is not a field.
AUDIT_EVENT_NAME: Final = "tool_invocation"

#: What `caller_attribution` says on stdio (DESIGN.md:771-776).
#:
#: **This string must never be `"global"` and must never contain it.**
#: `"global"` is what `get_client_id` returns on stdio, and recording it
#: would assert an identity that does not exist. §8's stdio arm asserts
#: this marker and asserts the absence of that literal, which is the
#: implementer error the row exists to prevent.
ATTRIBUTION_UNAVAILABLE: Final = "unavailable:stdio-has-no-caller-token"

#: `RESULT_STATUS_*` - the `result_status` field of
#: `ai/tool-calling.md:171-172`.
RESULT_STATUS_SUCCESS: Final = "success"
RESULT_STATUS_ERROR: Final = "error"

#: A UUIDv4 in canonical form: version nibble `4`, variant nibble
#: `8`/`9`/`a`/`b`.
#:
#: Inbound `X-Request-ID` is validated against this before use
#: (DESIGN.md:657-659, threat C7-T1 at DESIGN.md:1895). An unvalidated
#: inbound id is a log-forging vector: a value carrying a newline writes
#: a second, attacker-authored line into the audit stream.
_UUID4_RE: Final = re.compile(
    r"\A[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z",
    re.IGNORECASE,
)

#: W3C `traceparent`: `version-trace_id-span_id-flags`.
#:
#: The all-zero trace id and the all-zero span id are invalid per the
#: W3C Trace Context recommendation, and both are rejected here.
#: Accepting them would put a field in the event that looks like a join
#: and is not one, which is exactly what DESIGN.md:728-729 forbids.
_TRACEPARENT_RE: Final = re.compile(
    r"\A00-(?!0{32})([0-9a-f]{32})-(?!0{16})([0-9a-f]{16})-[0-9a-f]{2}\Z"
)


class Transport(enum.StrEnum):
    """The transport the invocation arrived on (DESIGN.md:771-773)."""

    STDIO = "stdio"
    HTTP = "http"


class AuditPhase(enum.StrEnum):
    """Which branch of the audit-write-failure policy applies.

    DESIGN.md:784-800.

    The phase is a property of *when the audit write is attempted*, not
    of the tool, which is why a write tool passes `BEFORE_SIDE_EFFECT`
    for its first emission and `AFTER_WRITE` for its second.
    """

    #: Before the side effect. An audit failure fails the call: no
    #: audit, no write.
    BEFORE_SIDE_EFFECT = "before_side_effect"
    #: A read tool. An audit failure logs to stderr and the call
    #: continues, because losing the tool is worse than losing one audit
    #: line.
    READ = "read"
    #: After a successful write. An audit failure returns success with a
    #: warning, never an error - an error makes the model retry, and a
    #: retry emails a second live human.
    AFTER_WRITE = "after_write"


class AuditWriteError(RuntimeError):
    """The audit write failed before a side effect, so the call fails.

    Deliberately **not** a `FastMcpJobviteError`: it is not one of the
    registry conditions at `error-contract.md:96-108`, and the tool
    boundary converts it through `problem_from_exception`'s
    `about:blank` path (ADR-0017) rather than through a slug this
    project would then owe forever (DESIGN.md:561-562).
    """


@dataclasses.dataclass
class AuditEvent:
    """One tool invocation's audit record.

    Field names are wire-shaped snake_case because
    `ai/tool-calling.md:178-179` requires it: `tool_name`, `request_id`,
    `result_status`.
    """

    tool_name: str
    request_id: str
    transport: Transport
    #: Already redacted. The type is `JsonValue` and not "the raw
    #: arguments" on purpose: passing raw arguments here and redacting
    #: inside `to_record` would put an unredacted copy on the event
    #: object, which is the value a debugger, a traceback or a `repr`
    #: would print.
    arguments: JsonValue = None
    client_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    result_status: str = RESULT_STATUS_SUCCESS
    approval_state: str | None = None
    approval_mechanism: str | None = None
    #: Monotonic start, set by `audit_scope`. `perf_counter` and not
    #: `time.time`: a clock adjustment mid-invocation would otherwise
    #: produce a negative latency.
    started_at: float = dataclasses.field(default_factory=time.perf_counter)

    @property
    def caller_attribution(self) -> str | None:
        """The stdio attribution marker, or `None` on HTTP.

        On HTTP the attribution IS `client_id`, so a marker beside it
        would be two answers to one question.
        """
        return ATTRIBUTION_UNAVAILABLE if self.transport is Transport.STDIO else None

    def to_record(self) -> dict[str, JsonValue]:
        """Build the structured record.

        **Optional fields are OMITTED, never emitted as `None`.** A
        `trace_id` of `None` is a field that is always present, and §8's
        trace case exists because a field that is always there passes a
        single-arm test (DESIGN.md:1416-1420).
        """
        record: dict[str, JsonValue] = {
            "tool_name": self.tool_name,
            "request_id": self.request_id,
            "arguments": self.arguments,
            "result_status": self.result_status,
            "latency_ms": self.latency_ms(),
            "transport": str(self.transport),
        }
        optional: dict[str, JsonValue] = {
            "client_id": self.client_id,
            "caller_attribution": self.caller_attribution,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "approval_state": self.approval_state,
            "approval_mechanism": self.approval_mechanism,
        }
        record.update({key: v for key, v in optional.items() if v is not None})
        return record

    def latency_ms(self) -> float:
        """Milliseconds since `audit_scope` opened."""
        return (time.perf_counter() - self.started_at) * 1000.0


def resolve_request_id(inbound_request_id: str | None = None) -> str:
    """Return the inbound `request_id`, or mint a fresh UUIDv4.

    An inbound `X-Request-ID` is **echoed only if it is a valid UUIDv4**
    (DESIGN.md:657-659). Anything else is discarded silently and
    replaced, rather than rejected: a malformed correlation header is
    not a reason to fail a tool call, and C7-T1 (DESIGN.md:1895) asks
    for the value to be "validated as a UUIDv4 before use and replaced
    if invalid".

    **A valid inbound id is echoed BYTE FOR BYTE, case included.** This
    used to `.lower()` it, and R2's nit-4 recorded that nothing held
    either behaviour: the only test used an all-digit literal, which is
    invisible to `.lower()`, so the mutation survived the whole suite.
    Echoing unchanged is the behaviour chosen: `_UUID4_RE` is already
    `IGNORECASE` so case was never a validity question, and the point of
    echoing a correlation id is that an operator can join on it by exact
    string match across two systems. A canonicalisation the caller did
    not ask for breaks that join and is not required by anything -
    `error-contract.md:83-85` imposes no case.

    Args:
        inbound_request_id: The caller's `X-Request-ID`, where the HTTP
            transport supplied one. `None` on stdio, which has no
            headers.

    Returns:
        The caller's id unchanged when it is a valid UUIDv4, otherwise a
        freshly minted one.
    """
    if inbound_request_id is not None and _UUID4_RE.match(inbound_request_id):
        return inbound_request_id

    # U9-F1. FALL BACK TO AN ALREADY-BOUND id BEFORE MINTING ONE.
    # The HTTP transport validates the caller's `X-Request-ID` and binds
    # it into `request_id_var` before a tool runs. Every `audit_scope`
    # call site then called this with no argument, so a FRESH id was
    # minted INSIDE the scope the middleware had already bound: the
    # caller's id was validated, bound, and discarded, and the value
    # stamped into `_meta` was one we invented. Measured end to end -
    # sent `0e1f2a3b-...`, got `db66f3bc-...`.
    #
    # FIXED HERE RATHER THAN AT EACH CALL SITE, deliberately. All three
    # sites omitted the argument - `search_jobs` and both candidate
    # tools - so a per-site fix is three edits today and a fourth for
    # the next tool, which is a hand-kept obligation beside a container
    # and the defect this repository has recorded eight times. The rule
    # belongs where the id is resolved.
    #
    # On stdio there is no header and the var is unset, so this returns
    # `None` and a fresh id is minted, which is the behaviour §7.4
    # requires there.
    bound = request_id_var.get()
    if bound is not None:
        return bound
    return str(uuid.uuid4())


def parse_trace_context(meta: Mapping[str, object] | None) -> tuple[str, str] | None:
    """Extract W3C trace context from the request `_meta`, or `None`.

    Read from `ctx.request_context.meta` directly rather than through
    FastMCP's span plumbing (DESIGN.md:724-726): `telemetry_mode()` may
    be `"off"`, in which case FastMCP's extractor returns the ambient
    context unchanged while the wire `_meta` still carries the header.

    **Returns `None` rather than a synthesised pair** when the header is
    missing or malformed (DESIGN.md:728-729).

    Args:
        meta: The request `_meta` mapping, or `None` when the caller
            sent none.

    Returns:
        `(trace_id, span_id)`, or `None` when no valid `traceparent` is
        present.
    """
    if not meta:
        return None
    raw = meta.get("traceparent")
    if not isinstance(raw, str):
        return None
    match = _TRACEPARENT_RE.match(raw.strip())
    if match is None:
        return None
    return match.group(1), match.group(2)


@contextmanager
def audit_scope(
    tool_name: str,
    transport: Transport,
    *,
    arguments: JsonValue = None,
    client_id: str | None = None,
    inbound_request_id: str | None = None,
    meta: Mapping[str, object] | None = None,
) -> Iterator[AuditEvent]:
    """Mint the `request_id`, bind it, and time the invocation.

    **This does not emit.** A write tool audits twice - once before the
    side effect and once after it - under two different branches of the
    failure policy (DESIGN.md:784-800), so the caller decides when and
    with which `AuditPhase`. A scope that emitted on exit would collapse
    those two branches into one and silently delete the branch the
    design says matters.

    Args:
        tool_name: The tool as registered.
        transport: The transport this invocation arrived on.
        arguments: The validated arguments. Redacted here, once, on the
            way in (DESIGN.md:312-318); the event never holds the raw
            values.
        client_id: `get_client_id`'s value on HTTP. **Ignored on
            stdio**, where it would be the literal `"global"` and would
            assert an identity that does not exist (DESIGN.md:771-776).
        inbound_request_id: The caller's `X-Request-ID`, if any.
        meta: The request `_meta`, read for `traceparent`.

    Yields:
        The `AuditEvent`, for the caller to complete and emit.
    """
    # DESIGN.md:664-666: minted and bound in the same statement.
    with request_id_scope(resolve_request_id(inbound_request_id)) as request_id:
        trace = parse_trace_context(meta)
        yield AuditEvent(
            tool_name=tool_name,
            request_id=request_id,
            transport=transport,
            arguments=redact_arguments(arguments),
            client_id=client_id if transport is Transport.HTTP else None,
            trace_id=None if trace is None else trace[0],
            span_id=None if trace is None else trace[1],
        )


def emit(event: AuditEvent, phase: AuditPhase) -> list[str]:
    """Write the audit event, applying the failure policy.

    DESIGN.md:784-800.

    Args:
        event: The completed event.
        phase: Which branch applies if the write fails.

    Returns:
        Warnings for the caller's `warnings` array. Empty unless a
        post-write audit failed.

    Raises:
        AuditWriteError: The write failed at `BEFORE_SIDE_EFFECT`, so
            the call must fail before the side effect happens.
    """
    try:
        logger.bind(**event.to_record()).info(AUDIT_EVENT_NAME)
    except Exception as exc:  # noqa: BLE001 - the policy is defined over ANY failure
        return _on_audit_write_failure(exc, event, phase)
    return []


def _on_audit_write_failure(
    exc: Exception, event: AuditEvent, phase: AuditPhase
) -> list[str]:
    """The three branches, in the order DESIGN.md:785-791 gives."""
    detail = redact_text(f"{type(exc).__name__}: {exc}")
    if phase is AuditPhase.BEFORE_SIDE_EFFECT:
        # Fail the call. No audit, no write.
        #
        # `from None` is NOT cosmetic (R2-M-1). This raise happens
        # inside `emit`'s `except`, so without it Python attaches the
        # sink's own exception as `__context__` - and that exception is
        # the UNREDACTED one whose text `detail` above has just
        # redacted. Every formatted traceback would then carry the
        # credential beside the cleaned message. The raw exception is
        # not lost: `detail` names its type and its redacted text.
        raise AuditWriteError(
            f"audit write failed before the side effect of {event.tool_name}; "
            f"the call was not performed ({detail})"
        ) from None
    # Both surviving branches report to STDERR, never to the audit
    # stream that just failed (DESIGN.md:790-791): routing the report
    # down the channel whose failure it reports is how the record of the
    # failure is lost too.
    _warn_on_stderr(
        f"audit write failed ({phase}) for {event.tool_name} "
        f"request_id={event.request_id}: {detail}"
    )
    if phase is AuditPhase.AFTER_WRITE:
        return [
            f"The {event.tool_name} write succeeded but its audit record was "
            f"not written (request_id={event.request_id}). Do not retry: the "
            f"write has already been performed."
        ]
    # AuditPhase.READ: log to stderr and continue. A read is recoverable
    # and losing the tool is worse than losing one audit line.
    return []


def _warn_on_stderr(message: str) -> None:
    """Write one line to stderr, best effort.

    `sys.stderr.write` and not `print`: ruff's `T20` is on for `src/`
    (`pyproject.toml`, `architecture/observability.md:642`), and
    `print` would be the wrong call anyway - it is the audit stream's
    failure channel, not output.

    **The write is best effort, and this is a policy requirement rather
    than defensiveness.** Since `__main__.configure_logging` puts the
    one log sink on stderr, the commonest cause of an audit-write
    failure - a full disk, a closed pipe - is a cause that fails the
    stderr write too. If that OSError escaped, the `READ` branch would
    fail a read tool and the `AFTER_WRITE` branch would raise instead of
    returning its warning, and DESIGN.md:785-791 says neither may
    happen: losing the tool is worse than losing one audit line, and an
    error after a successful write makes the model retry and email a
    second live candidate. There is no further channel to report the
    failure of the failure channel on, so it is swallowed here and
    nowhere else - `BEFORE_SIDE_EFFECT` never reaches this function.
    """
    try:
        sys.stderr.write(f"{message}\n")
    except OSError:
        return


def attach_audit_warnings(
    structured_content: dict[str, JsonValue], warnings: list[str]
) -> dict[str, JsonValue]:
    """Add the `warnings` array to a SUCCESS result's content.

    DESIGN.md:794-800 specifies this shape because "success with a
    warning" is not one: the normal success result, `is_error=False`,
    with a `warnings` array in its structured content naming the audit
    failure - **not a problem object**. §5.1 makes problem objects the
    channel for expected *failures*, and this is not one, because the
    write succeeded. Returning a problem object here would tell the
    caller the operation failed when it did not, and the caller's
    reasonable answer to that is to retry, which emails a second live
    candidate. Preventing exactly that is why this branch exists.

    Args:
        structured_content: The tool's normal success payload.
        warnings: `emit`'s return value. An empty list leaves the
            payload untouched, so callers need no conditional.

    Returns:
        A new payload. The input is not mutated.
    """
    if not warnings:
        return dict(structured_content)
    return {**structured_content, "warnings": list(warnings)}
