"""The dual-era approval guard and `create_candidate`, end to end.

**THE ROW COUNTER AND THE APPROVED-WRITE CONTROL ARE THE FIRST TWO
THINGS HERE, AND BOTH PREDATE `approval.py`.**
`IMPLEMENTATION-PLAN.md` §U10 says why, and it is not a style
preference: four refusal arms below all assert *the row count did not
move*, and every one of them passes perfectly against a
`create_candidate` that is broken and never writes at all - the
guard-that-refuses-everything of DESIGN.md:1451-1452.
`FASTMCP-SPIKE-4.md:1431` is the spike recording exactly that failure
against itself: a first run refused all six arms, looked like a perfect
security result, and was a token-parsing bug.

So `_JobviteRows` counts rows on the server side of a
`httpx2.MockTransport`, exactly as the spike ran it, and
`test_positive_control_*` asserts an APPROVED write moves that counter
**by exactly one, on both eras**. Nothing else in this file means
anything without them.

**WHAT THIS FILE MAY NEVER ASSERT, AND THE RULE IS ABSOLUTE.** It
asserts that the server requires an approval response from the host and
refuses to write without one. It never asserts, implies or names a
human: a host may auto-respond with no person present, which is C4-S1,
a **High residual** that is **not mitigable server-side**
(DESIGN.md:1852, ADR-0009).

A suite passing only against synthetic fixtures proves the client is
self-consistent, not that it speaks Jobvite (DESIGN.md:1339-1341). The
`201` body here is
`docs/research/fixtures/candidate_create_success.json` and it is
synthetic - `JOBVITE-CONTRACT.md:260` marks the whole write
contract `[INFERRED]`, and checklist row 10 is what replaces it.
"""

from __future__ import annotations

import json
import pathlib
import re
from collections.abc import Callable, Iterator
from typing import Any

import httpx2
import pytest
from fastmcp import Client
from loguru import logger
from pydantic import SecretStr

from fast_mcp_jobvite.audit import AUDIT_EVENT_NAME
from fast_mcp_jobvite.config import CREATE_CANDIDATE, Settings
from fast_mcp_jobvite.server import build_server
from fast_mcp_jobvite.services.jobvite_client import JobviteClient
from fast_mcp_jobvite.tools.candidates import (
    CANDIDATES_PATH,
    REQUEST_ID_META_KEY,
    CreateCandidateResult,
    build_create_result,
)

from .conftest import FIXTURES_DIR

#: The two eras, by the name the client's own `mode` argument takes.
#: `auto` negotiates the sessionless `2026-07-28`; `legacy` pins the
#: handshake `2025-11-25` (`FASTMCP-SPIKE-4.md:2066-2068`).
SESSIONLESS_MODE = "auto"
HANDSHAKE_MODE = "legacy"
BOTH_ERAS = (SESSIONLESS_MODE, HANDSHAKE_MODE)

CREATE_SUCCESS = "candidate_create_success.json"

VALID_ARGS: dict[str, Any] = {
    "first_name": "Testcandidate",
    "last_name": "Omega",
    "email": "testcandidate.omega@example.invalid",
    "job_eid": "TESTJOB1",
}


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


def settings(**overrides: Any) -> Settings:
    """Build validated-shaped settings for a write-enabled server.

    Both gates are satisfied here on purpose: `JOBVITE_ENABLE_WRITES`
    **and** the name in `JOBVITE_TOOLS` (DESIGN.md:998). The cases that
    withhold one of them do so explicitly.
    """
    base: dict[str, Any] = {
        "tools": CREATE_CANDIDATE,
        "enable_writes": True,
        "api_key": SecretStr("test-api-key"),
        "api_secret": SecretStr("test-api-secret"),
    }
    base.update(overrides)
    return Settings(**base)


# ======================================================================
# THE SERVER-SIDE ROW COUNTER. WRITTEN FIRST, BEFORE `approval.py`
# EXISTED, BECAUSE EVERY REFUSAL ARM BELOW IS AN ASSERTION ABOUT IT.
# ======================================================================


class _JobviteRows:
    """A fake Jobvite that counts the rows it was asked to create.

    **This is the control the whole file rests on**, and it is the
    construction `FASTMCP-SPIKE-4.md:2118-2143` ran: a counter on the
    server side of the transport, read before and after each arm.

    It counts the **request that reached the wire**, not a call the tool
    made to itself, which is the difference between measuring the write
    and measuring our own bookkeeping. A non-`POST` on this route is a
    hard failure rather than a quiet 200: this fake exists to notice a
    write, and a read arriving here means the tool did something other
    than the thing under test.
    """

    def __init__(self, *, status: int = 201, body: bytes | None = None) -> None:
        self.status = status
        self.body = fixture_bytes(CREATE_SUCCESS) if body is None else body
        #: One entry per POST that reached the transport. `len()` is the
        #: row count; the bodies are kept so an arm can assert what was
        #: actually sent.
        self.rows: list[dict[str, Any]] = []
        self.requests: list[httpx2.Request] = []

    @property
    def count(self) -> int:
        """The number of candidate rows created so far."""
        return len(self.rows)

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if request.method != "POST":
            msg = f"the fake ATS was asked for {request.method}, not a write"
            raise AssertionError(msg)
        self.rows.append(json.loads(request.content or b"{}"))
        return httpx2.Response(self.status, content=self.body)

    def factory(self) -> Callable[[], JobviteClient]:
        def make() -> JobviteClient:
            return JobviteClient(
                api_key=SecretStr("test-api-key"),
                api_secret=SecretStr("test-api-secret"),
                transport=httpx2.MockTransport(self.handler),
            )

        return make


async def approve_everything(
    message: str,
    response_type: type | None,
    params: Any,  # noqa: ANN401 - the framework's own params union
    context: Any,  # noqa: ANN401 - the SDK's client request context
) -> dict[str, Any]:
    """An elicitation handler that answers `approve: true`.

    **It is a HOST auto-responder and nothing else.** That is exactly
    C4-S1's shape - a host may answer with no person present - and it is
    why no assertion in this file says a human approved anything.
    """
    return {"approve": True}


async def deny_everything(
    message: str,
    response_type: type | None,
    params: Any,  # noqa: ANN401 - the framework's own params union
    context: Any,  # noqa: ANN401 - the SDK's client request context
) -> Any:  # noqa: ANN401 - an ElicitResult, typed by the framework
    """An elicitation handler that DECLINES."""
    from fastmcp.client.elicitation import ElicitResult

    return ElicitResult(action="decline", content=None)


async def accept_but_refuse(
    message: str,
    response_type: type | None,
    params: Any,  # noqa: ANN401 - the framework's own params union
    context: Any,  # noqa: ANN401 - the SDK's client request context
) -> Any:  # noqa: ANN401 - an ElicitResult, typed by the framework
    """`action == "accept"` carrying `approve: false`.

    **The arm people drop.** An accepted elicitation carrying
    `approve: false` is still an acceptance, which is why
    DESIGN.md:1148-1151 makes the guard a conjunction rather than an
    action check.
    """
    from fastmcp.client.elicitation import ElicitResult

    return ElicitResult(action="accept", content={"approve": False})


@pytest.fixture
def audit_records() -> Iterator[list[dict[str, Any]]]:
    """Capture the real loguru stream this server writes to."""
    captured: list[dict[str, Any]] = []

    def sink(message: Any) -> None:  # noqa: ANN401 - loguru's own message type
        captured.append(dict(message.record))

    sink_id = logger.add(sink, level="DEBUG")
    try:
        yield captured
    finally:
        logger.remove(sink_id)


def audit_events(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every `tool_invocation` record's structured fields, in order."""
    return [dict(r["extra"]) for r in records if r["message"] == AUDIT_EVENT_NAME]


# ======================================================================
# 1. THE POSITIVE CONTROL. WRITTEN FIRST, ON BOTH ERAS.
#    IMPLEMENTATION-PLAN.md §U10, DESIGN.md:1451-1452.
# ======================================================================


@pytest.mark.parametrize("mode", BOTH_ERAS)
async def test_positive_control_an_approved_write_moves_the_row_counter_by_one(
    mode: str,
) -> None:
    """An APPROVED write creates exactly one row, on both eras.

    **This is the case the whole unit is ordered around.** Four refusal
    arms below assert that the row counter did not move, and every one
    of them passes against a `create_candidate` that never writes at
    all. This case is what makes them mean something, so it asserts the
    opposite: the counter moves, by exactly one, and the identifiers
    Jobvite minted reach the caller.

    **It says nothing about a human.** The handler is a host
    auto-responder (C4-S1).
    """
    ats = _JobviteRows()
    server = build_server(settings(), client_factory=ats.factory())

    assert ats.count == 0, "the counter is not at zero before the write"

    async with Client(
        server, mode=mode, elicitation_handler=approve_everything
    ) as client:
        result = await client.call_tool(CREATE_CANDIDATE, {"params": VALID_ARGS})

    assert result.is_error is False, result.content
    assert ats.count == 1, (
        f"expected exactly one row on {mode}; the counter went 0 -> {ats.count}"
    )

    content = result.structured_content
    assert content is not None
    assert content["candidate_eid"] == "TESTCND9"
    assert content["application_eid"] == "TESTAPP9"


# ======================================================================
# 2. THE ERA DISCRIMINATOR. IT IS `protocol_version` AND IT IS NOT
#    `ctx.transport` OR `session_id` - BOTH MEASURED TRAPS.
#    FASTMCP-SPIKE-4.md:2066-2074.
# ======================================================================


class _FakeRequestContext:
    """A request context carrying all three candidate discriminators.

    **The two traps are POPULATED HERE ON PURPOSE**: `transport` is the
    DEPLOYED value on both eras and `session_id` is a real string on
    both. An implementation that read either of them would sail through
    the arms below, because both look exactly as they do on a working
    call.

    **`'streamable-http'` is the deployed value, not a measured one
    (R7-L3), and it is kept deliberately.** Over real streamable-HTTP
    both eras report it, which is what `FASTMCP-SPIKE-4.md:2066-2074`
    measured. In-process - the transport this whole suite runs on - the
    real `ctx.transport` is `None` on both. The fake states the
    deployment it is standing in for rather than the harness it runs
    under; what matters to the trap is that the two eras AGREE, and they
    agree either way. `test_the_traps_agree_on_the_real_context` pins
    the in-process observation so the two cannot drift apart unnoticed.
    """

    def __init__(self, protocol_version: str | None) -> None:
        if protocol_version is not None:
            self.protocol_version = protocol_version
        self.transport = "streamable-http"
        self.session_id = "3bd41cb2-0000-0000-0000-000000000000"
        self.meta = None


class _FakeContext:
    """The minimum `resolve_approval` reads, and nothing else."""

    def __init__(
        self,
        protocol_version: str | None,
        input_responses: Any = None,
    ) -> None:
        self.request_context = _FakeRequestContext(protocol_version)
        self.input_responses = input_responses
        self.transport = "streamable-http"
        self.session_id = "3bd41cb2-0000-0000-0000-000000000000"

    async def elicit(self, message: str, response_type: Any) -> Any:  # noqa: ANN401
        from fastmcp.server.elicitation import AcceptedElicitation

        self.elicited = message
        return AcceptedElicitation(data=response_type(approve=True))


class _Answer:
    """One MRTR response, in the shape the second leg reads."""

    def __init__(self, action: str, content: Any) -> None:  # noqa: ANN401
        self.action = action
        self.content = content


# E501: the name is one character over once `async` is prefixed, and it
# is a HARNESS ANCHOR - `scripts/check-u10-write-controls.sh:192` names
# this test verbatim, so shortening it to satisfy the line length would
# silently unhook the row that proves this case can fail.
async def test_the_discriminator_is_protocol_version_and_not_transport_or_session_id() -> (  # noqa: E501
    None
):
    """The three candidates, separated - by CALLING the guard.

    **R7-L1: this case did not do what its name says.** Its body called
    only `observed_protocol_version`, a four-line `getattr` helper, and
    never reached `resolve_approval` at all. Its two "trap" assertions
    compared `sessionless.transport` with `handshake.transport` and the
    same for `session_id` - two `_FakeContext` objects this test
    constructs itself, from the same hardcoded literals. They asserted
    that a literal equals itself, and swapping the discriminator for
    `transport` would not change either literal, so the refactor the
    docstring claimed to stop would have passed.

    It is now driven through `resolve_approval`, the function it names:

    1. Two contexts differing ONLY in `protocol_version` must resolve to
       DIFFERENT mechanisms - `MRTR` on the sessionless era,
       `ELICITATION` on the handshake era. A guard keyed on `transport`
       or `session_id` cannot produce two answers here, because those
       are identical on both.
    2. **The negative control, for what must NOT matter**: make
       `transport` and `session_id` differ between the two contexts and
       assert the mechanisms are UNCHANGED. Without this, a guard that
       read `transport` and happened to agree on this pair would still
       pass step 1.

    The branch is not uncovered either way - R7's M2 mutation of the era
    check is killed by two other cases - which is why this was a nit.
    But a test whose name is a claim its body never exercises is a
    recorded defect on this project, and the name is the part a later
    reader trusts.
    """
    from fast_mcp_jobvite.approval import (
        APPROVAL_REQUEST_KEY,
        ApprovalDecision,
        ApprovalMechanism,
        resolve_approval,
    )

    async def mechanism_of(ctx: Any) -> ApprovalMechanism:
        decision = await resolve_approval(
            ctx, message="approve?", request_state="state"
        )
        assert isinstance(decision, ApprovalDecision), (
            f"the era resolved to {type(decision).__name__}, not a decision; "
            "this case cannot compare mechanisms"
        )
        return decision.mechanism

    # The sessionless era needs its MRTR answers present, or it returns
    # the pending FIRST leg instead of a settled decision.
    answers = {APPROVAL_REQUEST_KEY: _Answer("accept", {"approve": True})}

    sessionless = _FakeContext("2026-07-28", input_responses=answers)
    handshake = _FakeContext("2025-11-25")

    # The two traps really are identical here, which is what makes the
    # discrimination below attributable to the version alone.
    assert sessionless.transport == handshake.transport
    assert sessionless.session_id == handshake.session_id

    assert await mechanism_of(sessionless) == ApprovalMechanism.MRTR
    assert await mechanism_of(handshake) == ApprovalMechanism.ELICITATION

    # NEGATIVE CONTROL. Make both traps DIFFER and require the same two
    # mechanisms: whatever the guard reads, it is not these.
    varied_sessionless = _FakeContext("2026-07-28", input_responses=answers)
    varied_sessionless.transport = "stdio"
    varied_sessionless.session_id = "11111111-1111-4111-8111-111111111111"
    varied_handshake = _FakeContext("2025-11-25")
    varied_handshake.transport = "sse"
    varied_handshake.session_id = "22222222-2222-4222-8222-222222222222"

    assert varied_sessionless.transport != varied_handshake.transport
    assert varied_sessionless.session_id != varied_handshake.session_id

    assert await mechanism_of(varied_sessionless) == ApprovalMechanism.MRTR
    assert await mechanism_of(varied_handshake) == ApprovalMechanism.ELICITATION


async def test_the_traps_agree_on_the_real_context() -> None:
    """R7-L3: the fakes above assert values this suite cannot produce.

    `_FakeRequestContext` and `_FakeContext` set `transport` to
    `'streamable-http'` and give both eras the SAME `session_id`. Over
    real streamable-HTTP the first is right; in-process, which is what
    everything here runs on, it is `None`. And real `session_id`s are
    per-session UUIDs that DIFFER on every connection - the fakes make
    them equal, which is a convenience of the fake and was being read as
    an observation about the framework.

    **The claim that matters survives either way, and this pins it:**
    `transport` is EQUAL across the two eras, so it cannot discriminate.
    `session_id` is POPULATED on both - that is what makes it a trap,
    never that it is equal. Nothing else in this file measures the real
    `Context`, so without this case the framework could change what
    either returns and only the fakes would still agree.
    """
    from fastmcp import Client as ProbeClient
    from fastmcp import FastMCP
    from fastmcp.server.dependencies import get_context

    probe = FastMCP("l3-probe")

    @probe.tool
    async def observe() -> dict[str, str]:
        ctx = get_context()
        return {
            "transport": repr(getattr(ctx, "transport", None)),
            "session_id": repr(getattr(ctx, "session_id", None)),
            "protocol_version": repr(
                getattr(ctx.request_context, "protocol_version", None)
            ),
        }

    seen: dict[str, dict[str, str]] = {}
    for mode in (SESSIONLESS_MODE, HANDSHAKE_MODE):
        async with ProbeClient(probe, mode=mode) as client:
            seen[mode] = (await client.call_tool("observe", {})).data

    # POSITIVE CONTROL: the two eras really were distinguished, or the
    # agreement below is agreement between two identical calls.
    assert (
        seen[SESSIONLESS_MODE]["protocol_version"]
        != seen[HANDSHAKE_MODE]["protocol_version"]
    ), seen

    assert seen[SESSIONLESS_MODE]["transport"] == seen[HANDSHAKE_MODE]["transport"], (
        f"transport now DIFFERS across eras, so it is no longer a trap: {seen}"
    )

    for mode in (SESSIONLESS_MODE, HANDSHAKE_MODE):
        assert seen[mode]["session_id"] != repr(None), (
            f"session_id is unpopulated on {mode}; the docstrings calling it "
            f"a trap because it is populated on both are now wrong: {seen}"
        )


async def test_an_unidentifiable_era_refuses_and_logs_the_observed_value(
    audit_records: list[dict[str, Any]],
) -> None:
    """A version in neither tuple refuses. DESIGN.md:1199-1203.

    **There is no fallback to fall through to** now that the
    confirmation token is cut, so an era nobody has measured must not
    degrade quietly into whichever branch happens to be last. The
    observed value is logged so an operator learns approval could not be
    established from a log line rather than from a candidate's inbox.
    """
    from fast_mcp_jobvite.approval import (
        ApprovalDecision,
        ApprovalMechanism,
        ApprovalState,
        resolve_approval,
    )

    ctx = _FakeContext("2099-01-01")
    decision = await resolve_approval(ctx, message="m", request_state="s")  # type: ignore[arg-type]

    assert isinstance(decision, ApprovalDecision)
    assert decision.approved is False
    assert decision.mechanism is ApprovalMechanism.NO_HANDLER
    assert decision.state is ApprovalState.UNAVAILABLE

    refusals = [
        r
        for r in audit_records
        if r["extra"].get("observed_protocol_version") == "2099-01-01"
    ]
    assert refusals, "the refusal did not log the version it observed"


async def test_an_absent_protocol_version_refuses() -> None:
    """The other half of the third case: the attribute is not there."""
    from fast_mcp_jobvite.approval import ApprovalDecision, resolve_approval

    decision = await resolve_approval(
        _FakeContext(None),  # type: ignore[arg-type]
        message="m",
        request_state="s",
    )
    assert isinstance(decision, ApprovalDecision)
    assert decision.approved is False
    assert decision.protocol_version is None


async def test_positive_control_a_recognised_era_approves() -> None:
    """The pairing for the two refusals above.

    **It belongs to the era test and not to §8 #22 or #25**, which is
    why `IMPLEMENTATION-PLAN.md` §U10 lists it as its own arm: without
    it, "an unrecognised era refuses" and "an absent version refuses"
    both pass against a guard that refuses every era there is.
    """
    from fast_mcp_jobvite.approval import (
        ApprovalDecision,
        ApprovalMechanism,
        resolve_approval,
    )

    decision = await resolve_approval(
        _FakeContext("2025-11-25"),  # type: ignore[arg-type]
        message="m",
        request_state="s",
    )
    assert isinstance(decision, ApprovalDecision)
    assert decision.approved is True
    assert decision.mechanism is ApprovalMechanism.ELICITATION


# ======================================================================
# 3. §8 #22 - FOUR ARMS. THE SECOND IS THE ONE PEOPLE DROP.
# ======================================================================


@pytest.mark.parametrize("mode", BOTH_ERAS)
async def test_case22_a_denied_approval_refuses_and_no_row_is_created(
    mode: str,
) -> None:
    """Arm 1: deny refuses, on both eras."""
    ats = _JobviteRows()
    server = build_server(settings(), client_factory=ats.factory())

    async with Client(server, mode=mode, elicitation_handler=deny_everything) as client:
        result = await client.call_tool(
            CREATE_CANDIDATE, {"params": VALID_ARGS}, raise_on_error=False
        )

    assert result.is_error is True
    assert ats.count == 0, "a denied approval created a row"


@pytest.mark.parametrize("mode", BOTH_ERAS)
async def test_case22_an_acceptance_carrying_approve_false_refuses(mode: str) -> None:
    """Arm 2, **the arm people drop**.

    `action == "accept"` with `approve: false` is still an acceptance.
    An action-only check admits it and writes, which is why
    DESIGN.md:1148-1151 makes the guard a conjunction.
    """
    ats = _JobviteRows()
    server = build_server(settings(), client_factory=ats.factory())

    async with Client(
        server, mode=mode, elicitation_handler=accept_but_refuse
    ) as client:
        result = await client.call_tool(
            CREATE_CANDIDATE, {"params": VALID_ARGS}, raise_on_error=False
        )

    assert result.is_error is True
    assert ats.count == 0, "an acceptance carrying approve:false created a row"


async def test_case22_the_second_leg_actually_consumes_ctx_input_responses() -> None:
    """Arm 4: the MRTR second leg reads the answer it was given.

    Driven at the guard rather than through the client, because that is
    the only place the two legs are separable: leg one sees
    `ctx.input_responses is None` and returns a pending result **without
    writing**; leg two sees the populated container and decides. A guard
    that ignored the answer would return the same verdict for both of
    the second-leg calls below.
    """
    from fast_mcp_jobvite.approval import (
        APPROVAL_REQUEST_KEY,
        ApprovalDecision,
        ApprovalMechanism,
        ApprovalPending,
        resolve_approval,
    )

    first_leg = await resolve_approval(
        _FakeContext("2026-07-28", input_responses=None),  # type: ignore[arg-type]
        message="m",
        request_state="s",
    )
    assert isinstance(first_leg, ApprovalPending)

    approved = await resolve_approval(
        _FakeContext(  # type: ignore[arg-type]
            "2026-07-28",
            input_responses={
                APPROVAL_REQUEST_KEY: _Answer("accept", {"approve": True})
            },
        ),
        message="m",
        request_state="s",
    )
    assert isinstance(approved, ApprovalDecision)
    assert approved.approved is True
    assert approved.mechanism is ApprovalMechanism.MRTR

    # THE SAME CALL, A DIFFERENT ANSWER. If the verdict did not come
    # from `ctx.input_responses`, these two would agree.
    refused = await resolve_approval(
        _FakeContext(  # type: ignore[arg-type]
            "2026-07-28",
            input_responses={
                APPROVAL_REQUEST_KEY: _Answer("accept", {"approve": False})
            },
        ),
        message="m",
        request_state="s",
    )
    assert isinstance(refused, ApprovalDecision)
    assert refused.approved is False


async def test_case22_an_answer_filed_under_another_key_refuses() -> None:
    """A populated container with no answer for us fails closed."""
    from fast_mcp_jobvite.approval import ApprovalDecision, resolve_approval

    decision = await resolve_approval(
        _FakeContext(  # type: ignore[arg-type]
            "2026-07-28",
            input_responses={"something-else": _Answer("accept", {"approve": True})},
        ),
        message="m",
        request_state="s",
    )
    assert isinstance(decision, ApprovalDecision)
    assert decision.approved is False


# ======================================================================
# 4. §8 #25 - NO HANDLER, BOTH ERAS.
#
#    **THIS CASE ASSERTS THE ROW COUNT AND NOT THE ERROR SHAPE.** The
#    no-handler arm RAISES `MCPError` on sessionless and RETURNS
#    `is_error=True` on handshake (FASTMCP-SPIKE-4.md:2153-2165), so
#    `pytest.raises(MCPError)` passes on one era and fails on the other,
#    and `assert result.is_error` does the reverse. The invariant that
#    actually matters is the same on both: nothing was written.
# ======================================================================


@pytest.mark.parametrize("mode", BOTH_ERAS)
async def test_case25_no_client_handler_fails_closed_on_both_eras(mode: str) -> None:
    """No handler, no approval, no row - whatever shape the error takes.

    The two eras surface this differently and **neither shape is
    asserted here on purpose**. Both are caught, and the assertion is
    that the server-side row counter did not move.
    """
    ats = _JobviteRows()
    server = build_server(settings(), client_factory=ats.factory())
    shape = await _no_handler_shape(server, mode)

    # THE REFUSAL HAPPENED IN ONE OF THE TWO KNOWN SHAPES. Asserting
    # membership rather than a specific shape is what makes one case
    # cover both eras; asserting that SOMETHING refused is what stops
    # this passing against a call that silently succeeded.
    assert shape in {"raised", "is_error"}, shape
    assert ats.count == 0, f"a call with no elicitation handler wrote a row on {mode}"


async def _no_handler_shape(server: Any, mode: str) -> str:  # noqa: ANN401
    """Drive one no-handler call and name the shape it produced.

    Returns:
        `"raised"`, `"is_error"`, or `"succeeded"`.
    """
    async with Client(server, mode=mode) as client:
        try:
            result = await client.call_tool(
                CREATE_CANDIDATE, {"params": VALID_ARGS}, raise_on_error=False
            )
        except Exception:  # noqa: BLE001 - the sessionless era RAISES here
            return "raised"
    return "is_error" if result.is_error else "succeeded"


async def test_case25_the_two_eras_refuse_in_DIFFERENT_shapes() -> None:
    """The asymmetry the case above is written around, pinned.

    **This is NOT §8 #25** - it is the measurement #25's wording
    depends on. `FASTMCP-SPIKE-4.md:2153-2165` records that sessionless
    raises `MCPError` and handshake returns `is_error=True`, and that is
    the whole reason #25 asserts the row count instead of an error
    shape. If the two ever agree, #25's justification has moved and
    somebody should be told - by a red test, not by a paragraph nobody
    re-reads.
    """
    shapes = {}
    for mode in BOTH_ERAS:
        ats = _JobviteRows()
        server = build_server(settings(), client_factory=ats.factory())
        shapes[mode] = await _no_handler_shape(server, mode)
        assert ats.count == 0

    assert shapes[SESSIONLESS_MODE] == "raised", shapes
    assert shapes[HANDSHAKE_MODE] == "is_error", shapes
    assert shapes[SESSIONLESS_MODE] != shapes[HANDSHAKE_MODE]


# ======================================================================
# 5. §8 #16 - `request_id` ON THE WIRE, ON THE WRITE'S TWO ARMS.
#
#    **ASSERTED ON THE WIRE RESULT, NEVER ON THE `ToolResult` THE TOOL
#    RETURNED.** DESIGN.md:1408-1411: asserting the object would pass
#    while the wire carried nothing.
# ======================================================================


@pytest.mark.parametrize("mode", BOTH_ERAS)
async def test_case16_a_successful_write_carries_request_id_on_the_wire(
    mode: str,
    audit_records: list[dict[str, Any]],
) -> None:
    """The success arm, matched against the audit event's own id."""
    ats = _JobviteRows()
    server = build_server(settings(), client_factory=ats.factory())

    async with Client(
        server, mode=mode, elicitation_handler=approve_everything
    ) as client:
        result = await client.call_tool(CREATE_CANDIDATE, {"params": VALID_ARGS})

    assert ats.count == 1
    wire_id = (result.meta or {}).get(REQUEST_ID_META_KEY)
    assert wire_id, "no request_id reached the wire on a successful write"

    events = audit_events(audit_records)
    assert events, "the write emitted no audit event"
    assert wire_id in {event["request_id"] for event in events}

    # THE STRUCTURED CONTENT STILL VALIDATES. An undeclared top-level
    # key is rejected by the output validator, which is why the id
    # travels in `_meta` and not in the payload.
    assert result.structured_content is not None
    CreateCandidateResult.model_validate(result.structured_content)


async def test_case16_the_audit_failure_warning_branch_carries_request_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The post-write audit-failure arm. DESIGN.md:794-800.

    **SUCCESS WITH A WARNING, NEVER AN ERROR.** A post-write audit
    failure returned as a problem object would tell the caller the
    operation failed when it did not, and the caller's reasonable answer
    to that is to retry - which creates a second record and may email
    the candidate a second time. Preventing exactly that is why this
    branch exists, so its shape is asserted here and not only its id.

    The sink is broken on its SECOND use, which is the post-write
    emission: the first is `BEFORE_SIDE_EFFECT`, whose failure must
    instead fail the call.
    """
    calls = {"n": 0}

    class _Sink:
        def info(self, message: str) -> None:
            calls["n"] += 1
            if calls["n"] >= 2:
                msg = "the audit sink is gone"
                raise RuntimeError(msg)

    class _BrokenLogger:
        def bind(self, **record: Any) -> _Sink:  # noqa: ANN401
            return _Sink()

    # PATCHED BY DOTTED PATH, not by `setattr(audit.logger, ...)`.
    # `logger` is re-exported rather than declared by `audit`, and mypy
    # refuses the attribute form - correctly, because a module that does
    # not export a name is a module whose name can move.
    monkeypatch.setattr("fast_mcp_jobvite.audit.logger", _BrokenLogger())

    ats = _JobviteRows()
    server = build_server(settings(), client_factory=ats.factory())
    async with Client(
        server, mode=HANDSHAKE_MODE, elicitation_handler=approve_everything
    ) as client:
        result = await client.call_tool(
            CREATE_CANDIDATE, {"params": VALID_ARGS}, raise_on_error=False
        )

    assert ats.count == 1, "the write did not happen, so this branch is vacuous"
    assert calls["n"] >= 2, (
        f"the broken sink was used {calls['n']} times; the post-write emission "
        f"never happened and this branch was never entered"
    )
    assert result.is_error is False, "a post-write audit failure became an ERROR"
    assert (result.meta or {}).get(REQUEST_ID_META_KEY)
    content = result.structured_content
    assert content is not None
    assert content["warnings"], "the audit failure produced no warning for the caller"
    assert "Do not retry" in content["warnings"][0]


# ======================================================================
# 6. C4-R1 - `approval_state` AND THE MECHANISM THAT PRODUCED IT ARE IN
#    THE AUDIT EVENT. ADR-0021 defines the closed vocabulary.
# ======================================================================


@pytest.mark.parametrize(
    ("mode", "expected_mechanism"),
    [(SESSIONLESS_MODE, "mrtr"), (HANDSHAKE_MODE, "elicitation")],
)
async def test_c4r1_the_audit_event_records_approval_state_and_its_mechanism(
    mode: str,
    expected_mechanism: str,
    audit_records: list[dict[str, Any]],
) -> None:
    """Both fields, on both eras, from the closed set.

    **The mechanism differs by era and that is the point of recording
    it**: `elicitation` on handshake, the MRTR path on sessionless. A
    field that read the same on both would say nothing about which path
    answered, which is what ADR-0021 exists to make recordable.
    """
    from fast_mcp_jobvite.approval import ApprovalMechanism

    ats = _JobviteRows()
    server = build_server(settings(), client_factory=ats.factory())
    async with Client(
        server, mode=mode, elicitation_handler=approve_everything
    ) as client:
        await client.call_tool(CREATE_CANDIDATE, {"params": VALID_ARGS})

    assert ats.count == 1
    events = audit_events(audit_records)
    approved = [e for e in events if e.get("approval_state") == "approved"]
    assert approved, f"no audit event recorded an approval; got {events}"

    for event in approved:
        assert event["approval_mechanism"] == expected_mechanism
        # THE SET IS CLOSED (ADR-0021). An open string invites a fourth
        # spelling of the first three.
        assert event["approval_mechanism"] in {m.value for m in ApprovalMechanism}


async def test_c4r1_a_refusal_is_audited_too_and_names_the_mechanism(
    audit_records: list[dict[str, Any]],
) -> None:
    """A refused write leaves a record. The absence would be R2-H1."""
    ats = _JobviteRows()
    server = build_server(settings(), client_factory=ats.factory())
    async with Client(
        server, mode=HANDSHAKE_MODE, elicitation_handler=deny_everything
    ) as client:
        await client.call_tool(
            CREATE_CANDIDATE, {"params": VALID_ARGS}, raise_on_error=False
        )

    assert ats.count == 0
    events = audit_events(audit_records)
    refusals = [e for e in events if e.get("approval_state") == "refused"]
    assert refusals, f"a refused write left no audit record; got {events}"
    assert refusals[0]["approval_mechanism"] == "elicitation"
    assert refusals[0]["result_status"] == "error"


async def test_the_audit_arguments_carry_no_candidate_pii_in_the_clear(
    audit_records: list[dict[str, Any]],
) -> None:
    """C6-* : the write's arguments ARE candidate PII by construction.

    Asserted against the audit event the case above proves exists, not
    against an empty stream (DESIGN.md:1354-1362).

    **R7-L2: this checked ONE of four values, and only `arguments`.** It
    asserted `VALID_ARGS["email"]` absent and said nothing about
    `first_name`, `last_name` or `job_eid` - all submitted, the first
    two PII in their own right. It also serialised only
    `e["arguments"]`, where U8's sibling
    (`tests/test_tools_candidates.py:943`) serialises the WHOLE event.
    The behaviour was correct - R7 probed all four - so this was a
    partial check that happened to be pointed at a leak-free field.

    Now every value in `VALID_ARGS` is checked, and against the whole
    event: a redactor covering `arguments` while leaking the same value
    into another structured field would have passed the old form, and a
    JSON sink publishes every field.
    """
    ats = _JobviteRows()
    server = build_server(settings(), client_factory=ats.factory())
    async with Client(
        server, mode=HANDSHAKE_MODE, elicitation_handler=approve_everything
    ) as client:
        await client.call_tool(CREATE_CANDIDATE, {"params": VALID_ARGS})

    events = audit_events(audit_records)
    assert events, "the stream is empty; this absence would be vacuous"
    serialised = json.dumps(events, default=str)
    for name, value in VALID_ARGS.items():
        assert value not in serialised, (name, serialised)


# ======================================================================
# 7. THE TWO DEPLOY-TIME GATES (DESIGN.md:996-1000). BOTH DIRECTIONS.
# ======================================================================


async def test_the_write_is_not_registered_without_the_writes_flag() -> None:
    """Named in `JOBVITE_TOOLS`, flag off: no write tool exists."""
    server = build_server(
        settings(enable_writes=False), client_factory=_JobviteRows().factory()
    )
    async with Client(server) as client:
        names = {tool.name for tool in await client.list_tools()}
    assert CREATE_CANDIDATE not in names, names


async def test_the_write_is_not_registered_when_it_is_not_named() -> None:
    """Flag on, not named: still no write tool.

    DESIGN.md:996-1000 states the conjunction in BOTH directions, and a
    single-direction test passes against an implementation that dropped
    one of them.
    """
    server = build_server(
        settings(
            tools=None,
            enable_writes=True,
            # `JOBVITE_TOOLS` unset means every READ tool, and
            # `get_job_feed` refuses to register without the v1
            # credential class. Supplying it here keeps this case about
            # the write's second gate rather than about the feed's
            # credentials.
            feed_key=SecretStr("test-feed-key"),
            feed_secret=SecretStr("test-feed-secret"),
            company_id=SecretStr("test-company-id"),
        ),
        client_factory=_JobviteRows().factory(),
    )
    async with Client(server) as client:
        names = {tool.name for tool in await client.list_tools()}
    assert CREATE_CANDIDATE not in names, names
    # The READS are still registered; withholding the write is not
    # withholding the server.
    assert names, "both gates off registered nothing at all"


async def test_positive_control_both_gates_satisfied_registers_the_write() -> None:
    """The pairing: with both gates met, the tool IS there."""
    server = build_server(settings(), client_factory=_JobviteRows().factory())
    async with Client(server) as client:
        names = {tool.name for tool in await client.list_tools()}
    assert CREATE_CANDIDATE in names, names


async def test_the_write_declares_all_three_annotations() -> None:
    """`destructiveHint`/`idempotentHint`/`readOnlyHint`.

    `readOnlyHint` is asserted FALSE rather than merely absent: an
    absent hint and a false one are not the same claim, and this is the
    one tool where the difference reaches a live person.
    """
    server = build_server(settings(), client_factory=_JobviteRows().factory())
    async with Client(server) as client:
        tool = next(t for t in await client.list_tools() if t.name == CREATE_CANDIDATE)
    annotations = tool.annotations
    assert annotations is not None
    assert annotations.destructiveHint is True
    assert annotations.idempotentHint is False
    assert annotations.readOnlyHint is False


# ======================================================================
# 8. THE ELICITATION PAYLOAD NAMES THE CANDIDATE, THE JOB, AND WHETHER
#    `send_email` IS TRUE (DESIGN.md:1134-1143).
#
#    **THIS IS THE ONE PLACE THE STRONGEST GATE CAN BE SATISFIED
#    HONESTLY AND STILL PRODUCE THE OUTCOME IT EXISTS TO PREVENT.** An
#    approver shown "create candidate Jane Doe" approves a database row
#    and thereby authorises an email to Jane Doe that nobody mentioned.
#    `ai/agent-guardrails.md:70-73` lists an outbound message to a third
#    party as destructive in its own right, so the email is separately a
#    gated action.
# ======================================================================


def test_the_approval_message_names_the_candidate_the_job_and_the_email() -> None:
    """All three, in the true-`send_email` direction."""
    from fast_mcp_jobvite.approval import build_approval_message

    message = build_approval_message(
        candidate="Testcandidate Omega", job="TESTJOB1", send_email=True
    )
    assert "Testcandidate Omega" in message
    assert "TESTJOB1" in message
    assert "send_email=true" in message
    assert "EMAIL" in message.upper()


def test_the_approval_message_says_so_when_no_email_will_be_sent() -> None:
    """Both arms are required, and this is the second.

    A message that always mentions email and one that never does each
    pass a single-arm test, and the second is the failure that matters:
    a caller told "no email will be sent" on a call that sends one has
    been misinformed by the control itself.
    """
    from fast_mcp_jobvite.approval import build_approval_message

    message = build_approval_message(
        candidate="Testcandidate Omega", job="TESTJOB1", send_email=False
    )
    assert "send_email=false" in message
    assert "send_email=true" not in message


async def test_the_approval_message_reaches_the_host_with_the_email_named() -> None:
    """End to end: the text the host actually receives.

    The two cases above test the builder. This one tests that its output
    is what travels, because a builder nothing calls is a string
    function with a good docstring.
    """
    seen: list[str] = []

    async def recording_handler(
        message: str,
        response_type: type | None,
        params: Any,  # noqa: ANN401 - the framework's own params union
        context: Any,  # noqa: ANN401 - the SDK's client request context
    ) -> dict[str, Any]:
        seen.append(message)
        return {"approve": True}

    ats = _JobviteRows()
    server = build_server(settings(), client_factory=ats.factory())
    async with Client(
        server, mode=HANDSHAKE_MODE, elicitation_handler=recording_handler
    ) as client:
        await client.call_tool(
            CREATE_CANDIDATE, {"params": {**VALID_ARGS, "send_email": True}}
        )

    assert ats.count == 1
    assert seen, "no approval request reached the host"
    assert "send_email=true" in seen[0]
    assert VALID_ARGS["job_eid"] in seen[0]
    assert "Testcandidate" in seen[0]


# ======================================================================
# 9. `send_email` DEFAULTS TO FALSE (DESIGN.md:239). THE DANGEROUS VALUE
#    IS NEVER THE ONE REACHED BY OMISSION.
# ======================================================================


async def test_send_email_defaults_to_false_on_the_wire() -> None:
    """Omitted by the caller, `false` in the body Jobvite receives."""
    ats = _JobviteRows()
    server = build_server(settings(), client_factory=ats.factory())
    async with Client(
        server, mode=HANDSHAKE_MODE, elicitation_handler=approve_everything
    ) as client:
        await client.call_tool(CREATE_CANDIDATE, {"params": VALID_ARGS})

    assert ats.count == 1
    assert ats.rows[0]["candidate"]["sendEmail"] is False


async def test_send_email_true_is_forwarded_and_not_quietly_dropped() -> None:
    """The paired direction.

    Without it, "the default is false" passes against a tool that hard-
    codes `false` and ignores the argument - which would be safe and
    would also make the disclosure in the approval request a lie.
    """
    ats = _JobviteRows()
    server = build_server(settings(), client_factory=ats.factory())
    async with Client(
        server, mode=HANDSHAKE_MODE, elicitation_handler=approve_everything
    ) as client:
        await client.call_tool(
            CREATE_CANDIDATE, {"params": {**VALID_ARGS, "send_email": True}}
        )

    assert ats.rows[0]["candidate"]["sendEmail"] is True


@pytest.mark.parametrize("send_email", [True, False])
async def test_the_audit_event_records_send_email_as_its_value(
    audit_records: list[dict[str, Any]],
    send_email: bool,
) -> None:
    """R7-M4: the audit event must answer "did this email a person?".

    `send_email` was in `NON_SENSITIVE_ARGUMENT_KEYS`' complement, so
    the audit event recorded it as `[REDACTED:bool]`. For every other
    argument recording the SHAPE is what makes the event auditable
    (`utils/redaction.py`'s own docstring). **For a `bool` the shape is
    the whole domain**, so the record could not distinguish a write that
    emailed a live person from one that did not.

    `DESIGN.md:1816` C1-T1 names flipping this field to `true` a
    **High** threat and `DESIGN.md:242` makes its `false` default a
    safety property. The audit event is the artefact a compliance reader
    consults after the fact, and it was the one place that question had
    to be answerable and was not.

    **BOTH directions, because R7 measured it unpinned in both.** Adding
    the key broke nothing - and no test asserted it was redacted either,
    so the previous behaviour was held in place by nothing at all. A
    single-value arm here would pass against a tool that hard-codes
    whichever value it was written with.
    """
    ats = _JobviteRows()
    server = build_server(settings(), client_factory=ats.factory())
    async with Client(
        server, mode=HANDSHAKE_MODE, elicitation_handler=approve_everything
    ) as client:
        await client.call_tool(
            CREATE_CANDIDATE,
            {"params": {**VALID_ARGS, "send_email": send_email}},
        )

    events = audit_events(audit_records)
    assert events, "the invocation emitted no audit event; this would be vacuous"
    recorded = events[-1]["arguments"]["send_email"]
    assert recorded is send_email, (
        f"the audit event records send_email as {recorded!r}, not {send_email!r}; "
        "C1-T1 cannot be answered from this record"
    )

    # The pairing: admitting this key must not admit the PII beside it.
    for pii_key in ("first_name", "last_name", "email"):
        assert events[-1]["arguments"][pii_key] == "[REDACTED:str]", (
            f"{pii_key} is no longer redacted in the audit event"
        )


async def test_the_body_reaches_the_wire_under_jobvites_own_keys() -> None:
    """`JOBVITE-CONTRACT.md:269-300`, nesting included."""
    ats = _JobviteRows()
    server = build_server(settings(), client_factory=ats.factory())
    async with Client(
        server, mode=HANDSHAKE_MODE, elicitation_handler=approve_everything
    ) as client:
        await client.call_tool(CREATE_CANDIDATE, {"params": VALID_ARGS})

    candidate = ats.rows[0]["candidate"]
    assert candidate["firstName"] == VALID_ARGS["first_name"]
    assert candidate["lastName"] == VALID_ARGS["last_name"]
    assert candidate["email"] == VALID_ARGS["email"]
    assert candidate["application"]["jobEId"] == VALID_ARGS["job_eid"]
    # THE REQUEST DIRECTION OF THE ""/null UNIFICATION (§9 hazard 4):
    # Jobvite's own fields use `""` where a null belongs, so a body we
    # SEND uses the vendor's spelling.
    assert candidate["mobile"] == ""
    assert candidate["application"]["source"] == ""
    assert ats.requests[0].method == "POST"
    assert ats.requests[0].url.path.endswith(CANDIDATES_PATH)


# ======================================================================
# 10. THE `eId`/`EId` CASING ASYMMETRY, PINNED (§9 hazard 1).
#     The WRITE response spells it `EId`; every READ spells it `eId`.
#     It is Jobvite's inconsistency and a well-meaning normalisation
#     would turn it into a bug.
# ======================================================================


def test_the_write_response_capital_eid_is_read() -> None:
    """The `201` body's spelling, from the contract's own example."""
    result = build_create_result(
        {"application": {"EId": "TESTAPP9", "candidate": {"EId": "TESTCND9"}}}
    )
    assert result.application_eid == "TESTAPP9"
    assert result.candidate_eid == "TESTCND9"


def test_the_read_spelling_is_accepted_on_the_write_route_too() -> None:
    """The other half of the asymmetry.

    One reader serves both spellings, so a tenant that answers the write
    with the read casing is not a silent `None`.
    """
    result = build_create_result(
        {"application": {"eId": "TESTAPP9", "candidate": {"eId": "TESTCND9"}}}
    )
    assert result.application_eid == "TESTAPP9"
    assert result.candidate_eid == "TESTCND9"


def test_an_envelope_carrying_neither_spelling_yields_none_not_an_error() -> None:
    """The `201` shape is `[INFERRED]` throughout.

    Guessing a shape for a response nobody has observed is how a wrong
    answer acquires an explanation, so an absent id is `None`.
    """
    assert build_create_result({}).candidate_eid is None
    assert build_create_result({"application": "not a dict"}).application_eid is None


# ======================================================================
# 11. C4-D2 - A `409` IS `/problems/conflict` WITH THE DUPLICATE NAMED
#     IN `detail`. **DETECTION, NOT PREVENTION** (DESIGN.md:1471-1474).
# ======================================================================


async def test_a_409_surfaces_as_problems_conflict_naming_the_duplicate() -> None:
    """The one thing we can do about C4-D2, and its exact limit.

    None of §2.2's gates stops an AUTHORISED write being made twice.
    This surfaces the duplicate rather than preventing it, and even the
    `409` shape is `[INFERRED]` rather than observed.
    """
    ats = _JobviteRows(
        status=409,
        body=b'{"status": {"code": 409, "messages": ["Candidate already exists"]}}',
    )
    server = build_server(settings(), client_factory=ats.factory())
    async with Client(
        server, mode=HANDSHAKE_MODE, elicitation_handler=approve_everything
    ) as client:
        result = await client.call_tool(
            CREATE_CANDIDATE, {"params": VALID_ARGS}, raise_on_error=False
        )

    assert result.is_error is True
    problem = result.structured_content
    assert problem is not None
    assert problem["type"] == "/problems/conflict"
    assert problem["status"] == 409
    assert "already exists" in problem["detail"]
    # THE `detail` MUST TELL THE CALLER NOT TO RETRY, because a retry is
    # what creates the second record and the second email.
    assert "not retried" in problem["detail"].lower()


async def test_a_non_409_upstream_failure_is_not_dressed_up_as_a_conflict() -> None:
    """The paired direction.

    `conflict_or_original` returning a conflict for everything would
    make the case above pass while telling every caller their candidate
    was a duplicate.
    """
    ats = _JobviteRows(
        status=500,
        body=b'{"status": {"code": 500, "messages": ["Server exploded"]}}',
    )
    server = build_server(settings(), client_factory=ats.factory())
    async with Client(
        server, mode=HANDSHAKE_MODE, elicitation_handler=approve_everything
    ) as client:
        result = await client.call_tool(
            CREATE_CANDIDATE, {"params": VALID_ARGS}, raise_on_error=False
        )

    problem = result.structured_content
    assert problem is not None
    assert problem["type"] != "/problems/conflict"


# ======================================================================
# 12. THE WRITE IS NEVER RETRIED (§4.3, DESIGN.md:1430).
#     **BY CONSTRUCTION**: `RETRYABLE_METHODS` admits GET and HEAD only,
#     so no configuration and no tool-name allow-list can turn it back
#     on. Without this case the caller-replay ceiling (C4-D2, B108) is
#     untested, and it is the one property that makes it honest.
# ======================================================================


async def test_an_approved_write_that_times_out_is_attempted_exactly_once(
    audit_records: list[dict[str, Any]],
) -> None:
    """A retried write emails a SECOND human - and the row it leaves.

    **The second claim is the more serious of the two this case makes.**
    This is `create_candidate`, the WRITE, on the one path where the
    write may or may not have landed: `AFTER_WRITE`'s policy never
    raises and never fails the call, so the audit row is the ONLY
    surviving evidence anyone has afterwards that the attempt did not
    succeed. Deleting `event.result_status = "error"` records a failed
    or ambiguous create as a success and left the whole suite green
    (task #97's container probe,
    `docs/reviews/probe-audit-row-container.sh`).

    Coverage cannot see it. `tools/candidates.py` reads 100.00% line
    AND 100.00% branch; this arm is EXECUTED by this case and by the
    409 and 500 cases above, all three of which assert the
    caller-visible half and none of which read the row.
    """
    attempts: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        attempts.append(request)
        raise httpx2.ConnectTimeout("timed out", request=request)

    def factory() -> Callable[[], JobviteClient]:
        def make() -> JobviteClient:
            return JobviteClient(
                api_key=SecretStr("test-api-key"),
                api_secret=SecretStr("test-api-secret"),
                transport=httpx2.MockTransport(handler),
            )

        return make

    server = build_server(settings(), client_factory=factory())
    async with Client(
        server, mode=HANDSHAKE_MODE, elicitation_handler=approve_everything
    ) as client:
        result = await client.call_tool(
            CREATE_CANDIDATE, {"params": VALID_ARGS}, raise_on_error=False
        )

    assert result.is_error is True
    assert len(attempts) == 1, (
        f"the write was attempted {len(attempts)} times; a retried write "
        f"creates a second record and may email a second live human"
    )

    # THE WRITE EMITS TWICE, and which row carries the verdict is the
    # whole of the claim. `BEFORE_SIDE_EFFECT` is written before the
    # POST is attempted (NO AUDIT, NO WRITE) and is CORRECTLY
    # `success` - nothing had failed yet. Only the `AFTER_WRITE` row
    # can record the outcome, so an assertion aimed at `events[0]`
    # would read the pre-write row, pass on the amputated code and
    # test nothing.
    events = audit_events(audit_records)
    assert len(events) == 2, (
        f"expected the BEFORE_SIDE_EFFECT and AFTER_WRITE rows, got {events}"
    )
    assert events[0]["result_status"] == "success", (
        "the pre-write row is written before the POST is attempted and "
        "records no outcome; if it reads 'error' the verdict has moved and "
        "the row below is no longer the one that carries it"
    )
    assert events[-1]["result_status"] == "error", (
        "the audit row recorded a write that may or may not have landed as "
        "anything other than an error, so the only surviving evidence of the "
        "failure is wrong"
    )


def test_the_write_method_is_not_in_the_retryable_set() -> None:
    """The exclusion read at its source, not inferred from a run.

    The arm above measures the behaviour; this one pins the *mechanism*
    the design calls "by construction", so a change that made POST
    retryable is visible even if the timing arm were ever weakened.
    """
    from fast_mcp_jobvite.services.jobvite_client import RETRYABLE_METHODS

    assert "POST" not in RETRYABLE_METHODS
    assert RETRYABLE_METHODS == frozenset({"GET", "HEAD"})


# ======================================================================
# 13. THE WORDING RULE, ENFORCED BY A TEST RATHER THAN BY REVIEW.
#     C4-S1 is a High residual and is NOT mitigable server-side.
# ======================================================================


#: The phrasings this unit may never assert (C4-S1).
#:
#: **ASSEMBLED FROM FRAGMENTS, NOT WRITTEN OUT**, so the intact phrase
#: never appears in this file. Spelling them literally made the scanner
#: below report its OWN pattern list and its own function names as
#: claims - a checker that cannot be run over the file it lives in is a
#: checker with a hole exactly where its author was standing.
#: **The bare nouns, and the articled forms are DERIVED from them**, so
#: that adding a claimant is one edit rather than three that can
#: disagree. R7 evaded the original three with `a recruiter` - a
#: claimant no more exotic than the ones already listed, in a repository
#: about recruiting.
_BARE_CLAIMANTS = (
    "human",
    "person",
    "reviewer",
    "recruiter",
    "user",
    "operator",
    "someone",
)
_CLAIMANTS = _BARE_CLAIMANTS + tuple(
    f"{'an' if who[0] in 'aeiou' else 'a'} {who}"
    for who in _BARE_CLAIMANTS
    if who != "someone"
)

#: The verbs that assert the act. `approved` alone let `authorised this
#: write` through, which is the same claim in a synonym.
_VERBS = ("approved", "authorised", "authorized", "signed off")

#: The phrasings this unit may never assert, in all three shapes the
#: claim takes: subject-verb, the passive `by`, and the hyphenated
#: adjective form, which neither of the other two matches.
#:
#: **Assembled, never spelt** - and the widening proved why within
#: minutes of being written. A first draft of this very comment wrote
#: the hyphenated example out in full as an illustration, and the
#: scanner reported the comment. That is the header's warning arriving
#: on schedule: the checker with a hole where its author was standing.
_HUMAN_CLAIMS = (
    tuple(f"{who} {verb}" for who in _CLAIMANTS for verb in _VERBS)
    + tuple(f"{verb} by {who}" for who in _CLAIMANTS for verb in _VERBS)
    + tuple(
        f"{who}-{verb}" for who in _BARE_CLAIMANTS for verb in _VERBS if " " not in verb
    )
)

#: A denial reads as a claim to a substring search, so an occurrence is
#: read together with the text before it.
#:
#: **`"nothing"` was missing and ADR-0031 tripped on it.** Its sentence
#: reads "nothing proves a human approved anything" - a denial, flagged
#: as a claim, by a document written to make exactly that disclaimer.
#: Found when this widened list met that ADR in a merge; neither existed
#: when the other was written.
#:
#: **THE TWO LISTS FAIL IN OPPOSITE DIRECTIONS AND ARE MAINTAINED
#: DIFFERENTLY FOR THAT REASON.** A missing NEGATOR is a false ALARM: a
#: denial gets flagged, someone reads it, and the cost is a minute. A
#: missing CLAIMANT is a false NEGATIVE: a real claim that a human
#: approved passes silently, which is the one thing this project has
#: decided it may never say. So the claimant side is enumerated and
#: aggressively widened (R7-H3), while this side stays a hand-kept list
#: - there is no container to enumerate for English negation, and
#: failing toward flagging is the safe direction.
#:
#: Adding a negator DOES widen a shadow, which is why negators are
#: scoped to the claim's own clause below. The evasions this addition
#: could enable are carried as DATA in the test cases, never spelled in
#: this comment - prose that quotes a forbidden claim is a forbidden
#: claim to a scanner, and this file is one the scanner reads.
_NEGATORS = ("not ", "never", "cannot", "no person", "no human", "n't", "nothing")

#: Where a negator stops applying: the end of the claim's own clause.
#:
#: **This used to be a 160-character window, and R7 measured what that
#: cost.** A negator anywhere in the preceding 160 characters suppressed
#: the hit, whatever it was negating, so the forbidden claim spelt
#: exactly as `_HUMAN_CLAIMS[0]` spells it went unreported whenever any
#: unrelated denial happened to sit nearby - 6 of 6 crafted evasions,
#: and 24-40% of the four scanned files sat inside such a shadow. **The
#: tripwire was blindest exactly where the prose denies the most**,
#: which is the prose the rule exists to require.
#:
#: A comma is deliberately NOT a boundary: *"we never claim X, only
#: that a response came back"* is one clause and the negator governs
#: all of it.
# The COMMA is here because adding `"nothing"` to `_NEGATORS` opened an
# evasion without it: a negator and a claim separated only by a comma
# were ONE clause, so the negator suppressed a real claim. Measured -
# that case was FLAGGED before the negator was added and CLEAN after,
# a regression the addition caused and this boundary closes. The case
# itself lives in the parametrised evasions, not here.
#
# It costs a false alarm on a denial that puts its negator before a
# comma, and that is the direction to fail: see `_NEGATORS` on why the
# two lists are maintained differently.
_CLAUSE_BOUNDARY = re.compile(r"[.;:!?,]")


def _unnegated_claims(text: str) -> list[str]:
    """Every claim of human approval NOT inside a denial of one.

    **A bare substring search cannot do this job, and the first version
    of it proved so**: it fired on this unit's own sentence saying the
    guard does not establish that anything of the sort happened, which
    is the sentence the rule exists to require.

    Markdown emphasis is stripped and whitespace collapsed before
    anything is matched. The second version searched the raw text and
    reported a denial as a claim, because the negator it was looking for
    was spelt with asterisks around it and a line break sat inside the
    phrase. **A scanner that reads formatting as content finds claims
    nobody made.**

    **This is a TRIPWIRE, not a proof.** It errs toward flagging: a
    denial phrased with its negator in an EARLIER clause than the claim
    is reported, and the fix is to tighten the sentence rather than to
    widen the scope. It cannot see a claim made in words it does not
    know, which is why review still applies.

    **The negator must govern the claim's own clause**, not merely sit
    somewhere near it. R7 measured the earlier 160-character window
    missing 6 of 6 crafted evasions - including the forbidden claim
    spelt exactly as this file spells it, suppressed by an unrelated
    denial in the previous sentence - with a quarter to two-fifths of
    every scanned file inside such a shadow. See `_CLAUSE_BOUNDARY`.

    Args:
        text: The lower-cased source of one owned file.

    Returns:
        One excerpt per unnegated claim.
    """
    flat = re.sub(r"\s+", " ", text.replace("*", ""))
    found = []
    for phrase in _HUMAN_CLAIMS:
        offset = flat.find(phrase)
        while offset != -1:
            boundaries = [m.end() for m in _CLAUSE_BOUNDARY.finditer(flat, 0, offset)]
            before = flat[(boundaries[-1] if boundaries else 0) : offset]
            if not any(negator in before for negator in _NEGATORS):
                found.append(flat[max(0, offset - 60) : offset + len(phrase)])
            offset = flat.find(phrase, offset + 1)
    return found


def test_the_wording_rule_holds_across_every_file_this_unit_owns(
    repo_root: pathlib.Path,
) -> None:
    """Nothing this unit wrote may assert that a person was involved.

    **A review catches this once; a test catches it on every commit.**
    The honest claim is *"the server requires an approval response from
    the host and refuses to write without one"*. A host may auto-respond
    with no person present (C4-S1, ADR-0009), so the stronger phrasing
    is one this design cannot support - and it would be written into a
    record a compliance reader later treats as authoritative.

    **This file is one of the files it scans**, which is why the
    patterns above are assembled rather than spelt.

    **The scope is three CONTAINERS plus this file, not a list of
    paths.** It was four typed paths, and R7 found two files the claim
    could be written into that nobody had added: `errors.py`, which
    holds `ApprovalRefusedError`, and ADR-0028, which is precisely the
    kind of document the docstring above calls one *"a compliance
    reader later treats as authoritative"*. Enumerating the directories
    closes both, and closes the next file nobody thinks to add.

    **Repo-wide was measured and rejected**, not assumed too broad.
    Scanning all 243 tracked `.py`/`.md` files reports 18 hits, every
    one of them benign: `README.md`, this repository's own review and
    brief documents, and `FASTMCP-SPIKE-4.md` all quote the forbidden
    phrasing in order to forbid it. The rule governs documents that
    ASSERT how this system behaves, not documents that discuss the
    rule, so `docs/reviews`, `docs/briefs` and `docs/research` are out
    of scope by measurement.
    """
    owned = sorted(
        {
            *(repo_root / "src" / "fast_mcp_jobvite").rglob("*.py"),
            *(repo_root / "docs" / "adr").glob("*.md"),
            *(repo_root / "docs" / "worklogs").glob("*.md"),
            repo_root / "tests" / "test_approval_write.py",
        }
    )

    # A glob at a path that stopped resolving returns an empty list and
    # this whole case would pass having read nothing - the wrong-zero
    # this project has recorded three times. The floor is well under
    # the 83 files the three containers hold today, so it fires on a
    # broken glob without going red on ordinary deletions.
    assert len(owned) >= 40, f"only {len(owned)} files scanned; a glob is not resolving"

    # POSITIVE CONTROL on the derivation: the two files R7 found missing
    # from the typed list must be inside what the containers produce.
    for required in (
        repo_root / "src" / "fast_mcp_jobvite" / "errors.py",
        repo_root
        / "docs"
        / "adr"
        / "0028-approval-mechanism-names-a-path-this-design-does-not-use.md",
    ):
        assert required in owned, f"the derivation does not reach {required}"

    for path in owned:
        assert path.exists(), f"the path does not resolve: {path}"
        text = path.read_text().lower()
        assert text.strip(), f"{path.name} is empty; this absence would be vacuous"
        claims = _unnegated_claims(text)
        assert not claims, f"{path.name} asserts human approval: {claims}"


def test_positive_control_the_wording_tripwire_can_actually_fire() -> None:
    """The pairing for the case above.

    An absence assertion over a search that matches nothing passes
    perfectly, and this unit's whole ordering exists because of that
    failure mode. So the tripwire is shown catching an assertion, and
    shown NOT catching the two denials that broke its first two
    versions.

    **The six evasions R7 measured are arms here, and they are the
    ratchet.** Without them the scanner can be reverted to its
    160-character window and its three-claimant list, and every one of
    these claims goes silently unreported again with the suite green.
    Each phrase is assembled from `_CLAIMANTS` and `_VERBS` rather than
    spelt, because this file is one of the files the rule scans.
    """
    claim = f"a human {_VERBS[0]}"

    # It fires on the bare claim, subject-verb and passive shapes both.
    assert _unnegated_claims(f"the write proceeded because {claim} it")
    assert _unnegated_claims(f"the record was {_VERBS[0]} by a human before sending")

    # It does NOT fire on the two denials that broke its first two
    # versions - the negator governs the claim's own clause.
    assert not _unnegated_claims(f"this does **not** establish that {claim} anything")
    assert not _unnegated_claims(
        f"we never claim {claim} it, only that a response came back"
    )

    # R7's six evasions. The first three are the serious ones: the
    # forbidden claim spelt exactly as this file spells it, formerly
    # suppressed by an unrelated denial within 160 characters.
    evasions = (
        f"the elicitation handler is not optional here. {claim} this write.",
        f"we never cache a tool that mints one-time state. {claim} this write.",
        f"the host doesn't buffer anything. {claim} this write.",
        f"a recruiter {_VERBS[0]} this write.",
        f"a human {_VERBS[1]} this write.",
        f"this write was human-{_VERBS[0]}.",
    )
    for evasion in evasions:
        assert _unnegated_claims(evasion), f"evasion not caught: {evasion}"


async def test_case22_a_declined_answer_carrying_approve_true_refuses() -> None:
    """The ACTION half of the conjunction, on the MRTR leg.

    **This case exists because a mutation survived without it.** U10's
    M6 deletes the action check, and every arm of
    `test_case22_the_second_leg_actually_consumes_ctx_input_responses`
    sends `action="accept"` - so the deletion changed nothing any of
    them could see. `DESIGN.md:1148-1151` requires BOTH halves and this
    is the one nothing exercised.
    """
    from fast_mcp_jobvite.approval import (
        APPROVAL_REQUEST_KEY,
        ApprovalDecision,
        resolve_approval,
    )

    decision = await resolve_approval(
        _FakeContext(  # type: ignore[arg-type]
            "2026-07-28",
            input_responses={
                APPROVAL_REQUEST_KEY: _Answer("decline", {"approve": True})
            },
        ),
        message="m",
        request_state="s",
    )
    assert isinstance(decision, ApprovalDecision)
    assert decision.approved is False, "a DECLINED response authorised the write"


# ======================================================================
# 9. THE THREE UNREAD BRANCHES OF THE APPROVAL PATH (#94).
#
#    ADR-0010 puts approval on the critical-path floor at 95% line and
#    90% branch. Approval measured 78.57% BRANCH against that floor
#    while its line coverage read 96% - the miss was entirely on the
#    half nobody looks at.
#
#    All three arms below run in the SAME direction: a shape the server
#    cannot read must refuse. Each is paired with a positive control,
#    because "refuses an unreadable shape" is satisfied by a function
#    that refuses everything, and that function approves nothing and is
#    not the fix (DESIGN.md:1451-1452).
# ======================================================================


async def test_a_context_with_no_request_context_refuses() -> None:
    """`ctx.request_context is None` must fail closed, not read on.

    `observed_protocol_version` returns `None` for it, which lands in
    the third case: neither era is identified, so nothing authorises
    the write. This is the arm where the discriminator cannot be read
    AT ALL, as distinct from
    `test_an_absent_protocol_version_refuses`, where the context exists
    and carries no version.

    **The assertion is the whole decision, not just `approved`.** A
    refusal recorded as `MRTR`/`REFUSED` would be a different
    claim - that a mechanism was consulted and said no - and ADR-0033
    publishes this vocabulary, so the mechanism and the state are part
    of the contract rather than diagnostics.
    """
    from fast_mcp_jobvite.approval import (
        ApprovalDecision,
        ApprovalMechanism,
        ApprovalState,
        resolve_approval,
    )

    ctx = _FakeContext("2026-07-28")
    # The arm under test. Set after construction so the rest of the
    # fake - including the two measured traps - is untouched.
    ctx.request_context = None  # type: ignore[assignment]

    decision = await resolve_approval(ctx, message="m", request_state="s")  # type: ignore[arg-type]

    assert isinstance(decision, ApprovalDecision)
    assert decision.approved is False
    assert decision.mechanism is ApprovalMechanism.NO_HANDLER
    assert decision.state is ApprovalState.UNAVAILABLE
    assert decision.protocol_version is None


async def test_an_input_responses_container_of_an_unreadable_shape_refuses() -> None:
    """`_answer_for`'s third arm: neither a mapping nor a `RootModel`.

    The helper accepts two container shapes on purpose - the spike
    measured `answers.root` and the pinned library hands over a plain
    dict - and the version after next could hand over a third. **The
    arm that matters is what happens then**, and it must be a refusal,
    because the alternative is a write authorised out of a container
    the server could not read.

    A list is used rather than an invented type: it is what a host
    serialising its responses positionally would plausibly send, it has
    no `root`, and it is not a `Mapping`.

    The positive control is the same era with a readable container, so
    this case cannot pass against a helper that returns `None` for
    everything.
    """
    from fast_mcp_jobvite.approval import (
        APPROVAL_REQUEST_KEY,
        ApprovalDecision,
        ApprovalMechanism,
        ApprovalState,
        resolve_approval,
    )

    unreadable = await resolve_approval(
        _FakeContext(  # type: ignore[arg-type]
            "2026-07-28",
            input_responses=[_Answer("accept", {"approve": True})],
        ),
        message="m",
        request_state="s",
    )
    assert isinstance(unreadable, ApprovalDecision)
    assert unreadable.approved is False, (
        "an approval was read out of a container shape the server does not "
        "understand, which authorises a write on an unparsed response"
    )
    # The era WAS identified, so this is a refusal by the MRTR
    # mechanism and not the no-handler case above.
    assert unreadable.mechanism is ApprovalMechanism.MRTR
    assert unreadable.state is ApprovalState.REFUSED

    readable = await resolve_approval(
        _FakeContext(  # type: ignore[arg-type]
            "2026-07-28",
            input_responses={
                APPROVAL_REQUEST_KEY: _Answer("accept", {"approve": True})
            },
        ),
        message="m",
        request_state="s",
    )
    assert isinstance(readable, ApprovalDecision)
    assert readable.approved is True, (
        "the positive control did not approve, so the refusal above proves "
        "nothing - a helper refusing every container would satisfy it"
    )


async def test_an_accepted_response_whose_content_is_not_a_dict_refuses() -> None:
    """`_approved_by_conjunction`'s shape guard, which is not defensive.

    `content = getattr(response, "content", None) or {}` admits
    whatever the host sent, and the value half of the conjunction is a
    `.get` on it. A response carrying `content` as a JSON *string* - a
    host that serialised the object one layer too many - would raise
    `AttributeError` inside the write path without this guard, and an
    exception on the approval leg is not a refusal: it is an error
    whose handling lives somewhere else entirely.

    **The action half is `accept` here on purpose.** With `action` set
    to anything else the first half of the conjunction refuses and this
    arm is never reached, so a case that varied both would prove the
    wrong thing.

    The positive control is the dict form of the same content, which is
    what separates this from a guard that refuses every acceptance.
    """
    from fast_mcp_jobvite.approval import (
        APPROVAL_REQUEST_KEY,
        ApprovalDecision,
        ApprovalState,
        resolve_approval,
    )

    async def decide(content: object) -> ApprovalDecision:
        decision = await resolve_approval(
            _FakeContext(  # type: ignore[arg-type]
                "2026-07-28",
                input_responses={APPROVAL_REQUEST_KEY: _Answer("accept", content)},
            ),
            message="m",
            request_state="s",
        )
        assert isinstance(decision, ApprovalDecision)
        return decision

    serialised = await decide('{"approve": true}')
    assert serialised.approved is False, (
        "a JSON string was read as an approval, so a host that serialised "
        "its content one layer too many authorises the write"
    )
    assert serialised.state is ApprovalState.REFUSED

    genuine = await decide({"approve": True})
    assert genuine.approved is True, (
        "the positive control did not approve, so the refusal above is "
        "satisfied by a conjunction that refuses every acceptance"
    )
