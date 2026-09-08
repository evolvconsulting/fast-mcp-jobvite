"""The dual-era approval guard for the one write (DESIGN.md:1122-1203).

**WHAT THIS MODULE ESTABLISHES, STATED EXACTLY.** It establishes that
*the server requires an approval response from the host and refuses to
write without one*. It does **not** establish that a human approved
anything, and nothing here may ever be read as saying so: a host may
auto-respond to an elicitation with no person present - Claude Code
documents a hook that does exactly this - and the MCP specification
places human-in-the-loop on the host, not on the server. That is
**C4-S1**, a **High residual** which is **not mitigable server-side**
(DESIGN.md:1852, ADR-0009). The honest claim is the one in the first
sentence and there is no stronger one available.

**TWO MECHANISMS, EXACTLY COMPLEMENTARY, AND A SINGLE-MECHANISM GUARD IS
BROKEN ON ONE ERA WHICHEVER IT PICKS** (DESIGN.md:1153-1159, executed at
`FASTMCP-SPIKE-4.md:2118-2143`):

| Era | MRTR | `ctx.elicit()` |
|---|---|---|
| sessionless `2026-07-28` | works, with a client handler | raises |
| handshake `2025-11-25` | raises on EVERY arm, approve too | works |

Read *works* as **era AND handler**, not as a property of the era. On
either era a client that supplies no elicitation handler cannot approve,
and the two failures surface **differently**: sessionless raises
`MCPError: Elicitation not supported`, handshake returns
`is_error=True` with a masked message (`FASTMCP-SPIKE-4.md:2153-2165`).
Both fail closed. **A test asserting an error SHAPE therefore passes on
one era and fails on the other**, which is why §8's case asserts the row
count instead.

**THE DISCRIMINATOR IS `protocol_version`, AND THE TWO OBVIOUS
ALTERNATIVES ARE MEASURED TRAPS.** `ctx.transport` is **identical on
both eras**, and `session_id` is **populated on both**, despite one era
being called sessionless (`FASTMCP-SPIKE-4.md:2066-2074`). Neither can
discriminate. A test pins `protocol_version` as the discriminator so a
later refactor cannot quietly swap it for one of the two things that
look like it and are not.

**Two values in that claim are transport-dependent, and saying so is
the point (R7-L3).** `transport` is `'streamable-http'` on both eras
over real streamable-HTTP, which is what `FASTMCP-SPIKE-4.md` measured;
in-process - the transport this repository's whole suite runs on - it is
`None` on both. **Identical either way, so the trap is real on both
transports**, but the literal `'streamable-http'` is a value no test
here can observe, and this paragraph named it as though it could.

`session_id` needs the same care in the other direction: the REAL ones
are per-session UUIDs and **differ** on every connection, measured
in-process as `728ce0eb-...` against `960c1569-...`. It is "populated on
both" that makes it useless as an era discriminator, never that it is
equal on both - a session_id-keyed guard would fail loudly rather than
quietly. `_FakeContext` gives both eras the SAME session_id, which is a
convenience of the fake and not an observation about the framework.

**AN UNIDENTIFIABLE ERA REFUSES.** The discriminator is correct for the
two eras that have been measured; a third case exists - the version
absent, or an era nobody has seen - and DESIGN.md:1199-1203 rules that
it must not degrade quietly. There is no weaker fallback to reach for
now that the confirmation token is cut (§7.6), so the rule is explicit:
**refuse, and log the observed value**, so an operator learns approval
could not be established from a log line rather than from a candidate's
inbox.

**THE GUARD CHECKS THE ACTION AND THE VALUE, AND THE CONJUNCTION IS NOT
OPTIONAL** (DESIGN.md:1148-1151). An *accepted* elicitation carrying
`approve: false` is still an acceptance, so
`action == "accept" and content.get("approve") is True` is the whole
test and either half alone admits a refusal as an approval.

**WHAT THIS MODULE CANNOT PROTECT, so it is not over-trusted.**
A tool cannot swallow the era guard - returning an `InputRequiredResult`
merely constructs an object, and the era check fires in FastMCP's
result-serialization layer *after* the tool has returned, outside any
scope a `try/except` in the tool controls (DESIGN.md:1171-1179). That
protects the **first leg only**. A tool that reaches its second leg and
mis-validates the answer is on its own, which is what the conjunction
above exists for.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Mapping
from typing import Any, Final

import mcp_types
from fastmcp import Context
from fastmcp.server.elicitation import AcceptedElicitation
from fastmcp.tools.base import InputRequiredToolResult
from loguru import logger
from pydantic import ConfigDict

from fast_mcp_jobvite.utils.constraints import InboundModel

#: The sessionless era, and the tuple FastMCP's own guard compares
#: against (`FASTMCP-SPIKE-4.md:2085`). MRTR is available here and
#: `ctx.elicit()` raises.
#: This module's own claim to a coverage role from DESIGN.md:1443-1445,
#: read by `docs/reviews/check-coverage-floors.py`. The design names the
#: roles and not the paths, and the claim lives HERE rather than in a
#: role-to-module map in the checker, which would be a hand-kept list
#: beside its container. The checker asserts the two sets are EQUAL.
COVERAGE_ROLE: Final = "approval"

MODERN_PROTOCOL_VERSIONS: Final[tuple[str, ...]] = ("2026-07-28",)

#: The handshake era. `ctx.elicit()` is available here and MRTR raises
#: on **every** arm including approve (DESIGN.md:1158-1159).
#:
#: **THIS TUPLE IS DELIBERATELY NOT "everything that is not modern".**
#: DESIGN.md:1199-1203 requires an unrecognised version to REFUSE rather
#: than fall through to whichever branch happens to be last, and an
#: `else` would silently hand a future era to `ctx.elicit()` on the
#: strength of never having been measured.
HANDSHAKE_PROTOCOL_VERSIONS: Final[tuple[str, ...]] = ("2025-11-25",)


class ApprovalAnswer(InboundModel):
    """The one field an approval response carries.

    **BOTH ERAS ASK FOR EXACTLY THIS SHAPE**, and that is deliberate. A
    `ctx.elicit(..., response_type=bool)` on the handshake era would
    render a *scalar* schema whose single property is called `value`,
    while the MRTR leg asks for `approve` - so one host handler could
    not answer both, and the two paths would differ in the one place a
    reader assumes they agree. Naming the field once, here, makes the
    payload era-independent and leaves the era deciding only which
    mechanism carries it.
    """

    #: **`strict=True`, and R8-H2 is why it is not optional here.**
    #: Without it pydantic coerces before `result.data.approve is True`
    #: can run, so `"true"`, `1`, `"yes"`, `"on"` and `"TRUE"` all
    #: became `True` on the elicitation leg while the MRTR leg - which
    #: reads the raw dict and applies `is True` to the wire value -
    #: refused every one of them. Measured, both legs, real functions:
    #:
    #:     wire value    MRTR leg    ELICITATION
    #:     True          True        True           <- the control
    #:     "true"        False       True           <- DISAGREED
    #:     1             False       True           <- DISAGREED
    #:     "yes"         False       True           <- DISAGREED
    #:
    #: The comment on the elicitation leg says "THE SAME CONJUNCTION AS
    #: THE MRTR LEG" and it sat exactly at the divergence. A host
    #: answering `{"approve": "yes"}` authorised a `create_candidate`
    #: write on one era and was refused on the other - and that tool
    #: emails a living person.
    #:
    #: Every one of the six tool input models already sets this. This
    #: model did not, because no sweep reaches it: it lives outside
    #: `tools/`, which is R8-H1.
    #:
    #: **AND `InboundModel` IS THE REST OF R8-H1.** This class
    #: declared two thirds of SS2.1 - `extra="forbid"` and
    #: `strict=True` - and not the third, the four structural limits,
    #: because the sweep asserting all three reached only `tools/`. It
    #: now reaches here (`tests/test_arguments_sweep.py`, route C), and
    #: this base is what that arm asks for.
    #:
    #: **It changes no outcome today and that is the argument for it,
    #: not against it.** With one `bool` field under `strict=True` and
    #: extra keys forbidden, every payload the limits would refuse is
    #: already refused for a different reason - which is exactly the
    #: "fail-closed by accident" `NestedProbe` was written about, and
    #: it evaporates the first time this model grows a `dict` or a
    #: `list` field. No contract moves: SS2.1's limits are stated for
    #: an argument payload, and applying them to a response this
    #: server asked its host for adds a refusal, never an acceptance.
    model_config = ConfigDict(extra="forbid", strict=True)

    approve: bool


#: The elicitation schema, derived from the model above rather than
#: written out beside it - two hand-kept copies of one shape is how the
#: MRTR leg and the `ctx.elicit()` leg come to ask for different things.
APPROVAL_SCHEMA: Final[dict[str, Any]] = ApprovalAnswer.model_json_schema()

#: The key the MRTR leg files its request under and reads its answer
#: back from. One name, used in both directions, because a mismatch
#: between them would read as "no answer arrived" and fail closed
#: silently on the one path that is supposed to succeed.
APPROVAL_REQUEST_KEY: Final = "approval"


class ApprovalMechanism(enum.StrEnum):
    """Which approval path produced the response (ADR-0021).

    **The set is CLOSED**, for the reason `error-contract.md`'s registry
    is closed (DESIGN.md:761-762): a value emitted into an audit record
    is a contract, and an open string invites a fourth spelling of the
    first three. ADR-0021 defines exactly these three and §8's
    audit-event case asserts the emitted value is one of them.

    **THE SESSIONLESS MEMBER IS `MRTR`, AND IT WAS `SAMPLING` UNTIL
    ADR-0028.** The path is Multi Round-Trip Requests -
    `InputRequiredResult` plus `ctx.input_responses` - and is not
    sampling in the MCP sense at all; this server has no MCP sampling
    path to name. ADR-0021's context paragraph described §7.5 as
    *"elicitation on one era, sampling with `ctx.input_responses` on
    the other"*, which is where the wrong noun entered, and the
    vocabulary it closed then had no slot for MRTR. U10 emitted the
    contract's value and raised the mismatch rather than inventing a
    fourth string the audit reader had never been told about.
    ADR-0028 renamed the member and kept the set closed at three, so
    the value and the mechanism now agree. The set did not grow.
    """

    #: `ctx.elicit()` answered - the handshake era's path.
    ELICITATION = "elicitation"
    #: The MRTR second leg answered - the sessionless era's path.
    #: Renamed from `SAMPLING` by ADR-0028; see the class docstring.
    MRTR = "mrtr"
    #: No approval path could run at all: no client handler, or an era
    #: this server does not recognise. Always a refusal.
    NO_HANDLER = "no_handler"


class ApprovalState(enum.StrEnum):
    """What the approval response said.

    **ADR-0021 explicitly did NOT settle this vocabulary** - it recorded
    `approval_state`'s own contents as a second gap in the same
    paragraph and declined to fold it in, because one ADR resolving two
    things is how the half nobody was looking at ships unreviewed
    (ADR-0017, `U2-REPORT.md` D1). U10 chose the values below and
    reported them rather than presenting them as settled. **ADR-0033
    then settled them**: the set is CLOSED, the design names it, and a
    fifth value is an ADR.

    **`PENDING` and `UNAVAILABLE` must not be collapsed.** One is an
    abandoned conversation and the other a conversation that never
    started, and collapsing them makes an abandoned approval
    indistinguishable from an unconfigured host in the only record
    either leaves.

    The prose above names no count on purpose. A number here is a second
    statement of a set the members below already are, and it goes stale
    on the change that adds one.
    """

    #: `action == "accept"` **and** `approve is True`. The only value
    #: under which a row is created.
    APPROVED = "approved"
    #: The MRTR first leg has been returned and no answer exists yet.
    #: **No row is created under this value**, and an approval abandoned
    #: here is C4-D1: the call hangs with no server-side bound, so this
    #: is the last audit record such an invocation ever produces.
    PENDING = "pending"
    #: A response arrived and did not authorise the write: a decline, or
    #: an acceptance carrying `approve: false`.
    REFUSED = "refused"
    #: No response could be obtained. Pairs with `NO_HANDLER`.
    UNAVAILABLE = "unavailable"


@dataclasses.dataclass(frozen=True)
class ApprovalPending:
    """The MRTR first leg: hand this back to the caller unchanged.

    The tool returns it; FastMCP serialises it into an
    `elicitation/create` request and the client retries the original
    call with `inputResponses` attached. **No row is created on this
    leg.**
    """

    result: InputRequiredToolResult
    #: Which path is being opened. Always the MRTR one - the handshake
    #: era's `ctx.elicit()` completes within a single leg and never
    #: produces a pending result - and it is carried rather than assumed
    #: at the call site so the audit record on this leg reads the same
    #: field as the audit record on the next one.
    mechanism: ApprovalMechanism = ApprovalMechanism.MRTR


@dataclasses.dataclass(frozen=True)
class ApprovalDecision:
    """A settled answer, and everything the audit event needs.

    Attributes:
        approved: Whether the write may proceed. **`True` means an
            approval response was received from the host**, never that a
            person saw it (C4-S1).
        mechanism: Which path answered.
        state: What that answer said.
        protocol_version: The version observed on the request context,
            recorded so a refusal names what it saw.
    """

    approved: bool
    mechanism: ApprovalMechanism
    state: ApprovalState
    protocol_version: str | None


def observed_protocol_version(ctx: Context) -> str | None:
    """Read the discriminator, and only the discriminator.

    **`ctx.transport` and `session_id` are measured traps** and are not
    consulted here or anywhere else: the first is identical on both eras
    and the second is populated on both
    (`FASTMCP-SPIKE-4.md:2066-2074`).

    Args:
        ctx: The invocation context.

    Returns:
        The negotiated protocol version, or `None` when there is no
        request context or it carries no version.
    """
    request_context = ctx.request_context
    if request_context is None:
        return None
    version = getattr(request_context, "protocol_version", None)
    return version if isinstance(version, str) else None


def _answer_for(answers: object, key: str) -> object:
    """Read one answer out of `ctx.input_responses`.

    **THE CONTAINER TYPE IS NOT THE SPIKE'S AND THIS IS MEASURED, NOT
    DEFENSIVE.** `FASTMCP-SPIKE-4.md:2103` reads it as
    `answers.root.get(...)` - a pydantic `RootModel` - and at the
    `fastmcp` version this repository pins (ADR-0001) it arrives as a
    plain mapping, so the spike's line raises
    `AttributeError: 'dict' object has no attribute 'root'`. Both forms
    are accepted here because the spike is the executed evidence for the
    mechanism and the installed library is the executed evidence for the
    shape, and a helper that reads only one of them turns a library bump
    into a write that fails closed for a reason nobody can see.

    Args:
        answers: Whatever `ctx.input_responses` returned.
        key: The name the request was filed under.

    Returns:
        The response object, or `None` when the key is absent. **`None`
        fails the conjunction below and therefore refuses**, which is
        the direction that cannot email anyone.
    """
    container = getattr(answers, "root", answers)
    if isinstance(container, Mapping):
        return container.get(key)
    return None


def _approved_by_conjunction(response: object) -> bool:
    """`action == "accept" AND content["approve"] is True`.

    Both halves, always. An accepted elicitation carrying
    `approve: false` is still an acceptance, and an action check alone
    would admit it (DESIGN.md:1148-1151).

    `is True` rather than a truth test: a JSON `"true"`, a `1` or a
    non-empty dict are all truthy and none of them is the boolean the
    schema asked for.

    Args:
        response: The elicitation response object from the MRTR second
            leg.

    Returns:
        Whether this response authorises the write.
    """
    if getattr(response, "action", None) != "accept":
        return False
    content = getattr(response, "content", None) or {}
    if not isinstance(content, dict):
        return False
    return content.get("approve") is True


def build_approval_message(
    *,
    candidate: str,
    job: str,
    send_email: bool,
) -> str:
    """The text the approval request carries.

    **IT MUST NAME THE EMAIL AND NOT ONLY THE RECORD**, and this is the
    one place the strongest gate can be satisfied honestly and still
    produce the outcome it exists to prevent (DESIGN.md:1134-1143). An
    approver shown *"create candidate Jane Doe"* approves a database row
    and thereby authorises **an email to Jane Doe that nobody
    mentioned**. `ai/agent-guardrails.md:70-73` lists *"outbound message
    to a third party"* among the destructive actions that must pause for
    approval, so the email is separately a gated action and an approval
    that never mentioned it has not been obtained for it.

    Args:
        candidate: How the candidate is identified to the approver.
        job: The target job's `jobEId`, or a marker when none was given.
        send_email: Whether Jobvite will be asked to mail the candidate.

    Returns:
        The message, naming all three.
    """
    email_clause = (
        "AND JOBVITE WILL EMAIL THIS PERSON (send_email=true)"
        if send_email
        else "no email will be sent (send_email=false)"
    )
    return (
        f"Create candidate {candidate} in the live Jobvite ATS, "
        f"applying to job {job}, {email_clause}. "
        f"This creates a real record and cannot be undone."
    )


def pending_approval(message: str, request_state: str) -> ApprovalPending:
    """Build the MRTR first-leg result.

    Args:
        message: `build_approval_message`'s text.
        request_state: Opaque state echoed back on the retry, so the
            second leg can see which call it is answering.

    Returns:
        The pending result for the tool to return unchanged.
    """
    request = mcp_types.ElicitRequest(
        method="elicitation/create",
        params=mcp_types.ElicitRequestFormParams(
            mode="form",
            message=message,
            requested_schema=APPROVAL_SCHEMA,
        ),
    )
    return ApprovalPending(
        result=InputRequiredToolResult(
            mcp_types.InputRequiredResult(
                result_type="input_required",
                input_requests={APPROVAL_REQUEST_KEY: request},
                request_state=request_state,
            )
        )
    )


async def resolve_approval(
    ctx: Context,
    *,
    message: str,
    request_state: str,
) -> ApprovalPending | ApprovalDecision:
    """Obtain an approval response, on whichever era this call arrived.

    Three outcomes and no fourth:

    - `ApprovalPending` - the MRTR first leg. Return it unchanged; **no
      row is created**.
    - `ApprovalDecision(approved=True, ...)` - **an approval response
      was received from the host.** Not a person; see the module
      docstring and C4-S1.
    - `ApprovalDecision(approved=False, ...)` - refuse. Every path that
      is not an explicit approval lands here, including an era this
      server cannot identify.

    Args:
        ctx: The invocation context. Its `protocol_version` is the
            discriminator and nothing else is consulted.
        message: The approval text, which must already name the email.
        request_state: Opaque state for the MRTR retry.

    Returns:
        The pending first leg, or the settled decision.
    """
    version = observed_protocol_version(ctx)

    if version in MODERN_PROTOCOL_VERSIONS:
        answers = ctx.input_responses
        if answers is None:
            # FIRST LEG. `ctx.input_responses` is `None` here and
            # populated on the retry - and `hasattr` cannot tell the two
            # apart, because it is a CLASS-LEVEL property and is
            # therefore `True` on every era, always
            # (`FASTMCP-SPIKE-4.md:1988-1995`). The era check above is
            # what separates them; this only separates the legs.
            return pending_approval(message, request_state)
        response = _answer_for(answers, APPROVAL_REQUEST_KEY)
        approved = _approved_by_conjunction(response)
        return ApprovalDecision(
            approved=approved,
            mechanism=ApprovalMechanism.MRTR,
            state=ApprovalState.APPROVED if approved else ApprovalState.REFUSED,
            protocol_version=version,
        )

    if version in HANDSHAKE_PROTOCOL_VERSIONS:
        result = await ctx.elicit(message, response_type=ApprovalAnswer)
        # THE SAME CONJUNCTION AS THE MRTR LEG, in the shape this
        # mechanism returns it: `AcceptedElicitation` IS the accept
        # action, and `.approve is True` is the value half. A
        # `isinstance` check alone would admit an acceptance carrying
        # `approve: false`, which is the arm people drop
        # (DESIGN.md:1148-1151).
        approved = (
            isinstance(result, AcceptedElicitation)
            and isinstance(result.data, ApprovalAnswer)
            and result.data.approve is True
        )
        return ApprovalDecision(
            approved=approved,
            mechanism=ApprovalMechanism.ELICITATION,
            state=ApprovalState.APPROVED if approved else ApprovalState.REFUSED,
            protocol_version=version,
        )

    # THE THIRD CASE. DESIGN.md:1199-1203: the version is absent, or is
    # an era nobody has measured. Refuse, and LOG THE OBSERVED VALUE, so
    # an operator learns that approval could not be established from a
    # log line rather than from a candidate's inbox.
    logger.warning(
        "create_candidate refused: the protocol era could not be identified",
        observed_protocol_version=version,
        recognised_protocol_versions=sorted(
            MODERN_PROTOCOL_VERSIONS + HANDSHAKE_PROTOCOL_VERSIONS
        ),
    )
    return ApprovalDecision(
        approved=False,
        mechanism=ApprovalMechanism.NO_HANDLER,
        state=ApprovalState.UNAVAILABLE,
        protocol_version=version,
    )
