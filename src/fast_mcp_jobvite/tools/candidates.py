"""`search_candidates` and `get_candidate` (DESIGN.md:137).

**TWO TOOLS, NOT ONE, AND THE REASON IS STRUCTURAL.** Output
cardinality differs - `get_candidate` returns one record and
`search_candidates` a page - and under `strict=True` one tool cannot
have two return schemas. A single tool returning "a page that sometimes
holds one" would make every caller unwrap a list to reach a record it
asked for by id.

**`create_candidate` IS THE THIRD TOOL AND IT SHARES THIS FILE.** The
two reads above may never call a non-GET method; the write does, and it
is gated behind an explicit deploy-time opt-in **and** a per-invocation
approval guard (`approval.py`, DESIGN.md:207-237).

**THIS IS THE ONLY TOOL WHOSE FAILURE MODE EMAILS A LIVING PERSON.**
Everything else in this file returns wrong data. `create_candidate`
creates a real record in a real ATS with no sandbox, and with
`send_email` true it mails a human being. Two consequences run through
every line of it:

- **A retried write emails a SECOND live human.** The exclusion is in
  `services/jobvite_client.py`'s `RETRYABLE_METHODS`, which admits
  `GET` and `HEAD` only, so a `POST` cannot be retried **by
  construction** rather than by configuration (DESIGN.md:362). There is
  no setting that turns it back on and none may be added.
- **An authorised write can still be made twice** - a model retrying
  after a timeout, or a caller approving twice. That is **C4-D2**, and
  the idempotency-key remedy the standard names **cannot be built**:
  nothing establishes that Jobvite accepts a dedupe key on this endpoint
  (DESIGN.md:245-258). A `409` is surfaced as `/problems/conflict` with
  the duplicate named in `detail` - **detection, not prevention** - and
  even that shape is `[INFERRED]` rather than observed.

**What the guard establishes, exactly:** the server requires an approval
response from the host and refuses to write without one. **Never that a
human approved.** C4-S1 is a High residual, not mitigable server-side
(DESIGN.md:1852, ADR-0009).

**This is the candidate PII data class** (DESIGN.md:137), which is the
step up from `tools/jobs.py`. It is the first tool surface where §6.1's
fencing fires, where §6.2's EEO exclusion is load-bearing, and where
DESIGN.md:780-782's "candidate PII reaches the audit *path* by
construction" is literally true - the argument to `get_candidate` IS a
candidate identifier.

**ORDER OF OPERATIONS, and it is not interchangeable:**

1. `fence_payload` walks the RAW Jobvite record against the generated
   path registry. Unknown paths are dropped, `""` is unified with null,
   admitted free text is fenced, and an unknown non-string is dropped
   rather than stringified (§8 #20).
2. `to_candidate` maps the surviving keys onto the allow-listed model,
   normalising the date asymmetry.

Doing it the other way round would fence values that had already lost
their path, which is the only thing that tells `candidates[].title`
from `candidates[].application.job.title`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, Final

from fastmcp import Context, FastMCP
from fastmcp.tools.base import InputRequiredToolResult, ToolResult
from pydantic import BaseModel, ConfigDict, Field

from ..approval import (
    ApprovalPending,
    ApprovalState,
    build_approval_message,
    resolve_approval,
)
from ..audit import (
    AuditPhase,
    Transport,
    attach_audit_warnings,
    audit_scope,
    emit,
)
from ..config import CREATE_CANDIDATE, GET_CANDIDATE, SEARCH_CANDIDATES, Settings
from ..errors import (
    ApprovalRefusedError,
    DuplicateCandidateError,
    JobviteUpstreamError,
    problem_from_exception,
)
from ..models.candidate import (
    CANDIDATES_ENVELOPE_KEY,
    TOTAL_ENVELOPE_KEY,
    Candidate,
    CandidateApplication,
    CandidateJob,
    CandidateResume,
    CandidateSearchResult,
)
from ..models.fencing import Fenced, FencingDecision, fencing_paths
from ..services.jobvite_client import JobviteClient
from ..utils.constraints import InboundModel, JobviteIdentifier, SafeText
from ..utils.normalise import epoch_ms_to_date, none_to_blank, read_identifier
from ..utils.redaction import fence_payload

#: The namespaced `_meta` key `request_id` travels to the caller under
#: (DESIGN.md:684-687). **The same literal `tools/jobs.py` declares**,
#: and it is duplicated rather than imported on purpose: importing one
#: tool module from another to share a protocol constant would couple
#: two units' registration order for a string. A test pins the two
#: equal, which is the check that actually catches a drift.
REQUEST_ID_META_KEY: Final = "com.evolvconsulting.fast-mcp-jobvite/requestId"

#: The v2 route both tools call (`JOBVITE-CONTRACT.md:225-236`).
#: **Routing is case-sensitive and inconsistent on this API**
#: (`JOBVITE-API.md:384`), so the casing is hard-coded and never
#: derived.
CANDIDATES_PATH: Final = "/candidate"

#: Jobvite's query parameter for one candidate
#: (`JOBVITE-CONTRACT.md:229`). `[INFERRED]`, and named here rather
#: than inline so a test can assert the value that reaches the wire.
CANDIDATE_ID_PARAM: Final = "candidateId"

#: **Every route this module asks the client for.** Enumerated so a
#: test can assert the two sets are EQUAL rather than merely
#: overlapping - a list written beside the call site is blind to the
#: route nobody added to it.
CLIENT_ROUTES: Final = (CANDIDATES_PATH,)

#: The fencing decisions for one candidate record, GENERATED from the
#: output models (DESIGN.md:202-205) and keyed by **path in Jobvite's
#: own key space**, exactly as DESIGN.md:822's own example
#: `candidates[].application.job.title` is.
#:
#: The two envelope entries are added explicitly because they are not
#: fields of `Candidate`: the walk starts at one record.
CANDIDATE_FENCING_PATHS: Final[dict[str, Fenced]] = {
    CANDIDATES_ENVELOPE_KEY: Fenced(
        FencingDecision.NOT_FREE_TEXT,
        CANDIDATES_ENVELOPE_KEY,
        "envelope container; each element decides separately",
    ),
    TOTAL_ENVELOPE_KEY: Fenced(
        FencingDecision.NOT_FREE_TEXT,
        TOTAL_ENVELOPE_KEY,
        "integer from the envelope",
    ),
    **fencing_paths(Candidate, f"{CANDIDATES_ENVELOPE_KEY}[]"),
}


class SearchCandidatesInput(InboundModel):
    """Arguments for `search_candidates`.

    **DELIBERATELY EMPTY, AND THE EMPTINESS IS EVIDENCE-BOUND.**
    `JOBVITE-CONTRACT.md:225-236` documents nine request parameters and
    **every one of them is `[INFERRED]` or `[ASSUMED]`** - none is
    observed. `start` and `count` are U6's. Of the rest:

    - `datestart`/`dateend` are the parameters `tools/jobs.py` refused
      to offer, and they are `[INFERRED]` here for the same reason they
      were `[ASSUMED]` there - the analogy runs from this route to that
      one, not the other way.
    - `wflowstate` is `[ASSUMED]`: two clients left it as an
      unimplemented TODO, so it is v1 continuity and **not observed
      working on v2**.

    **Jobvite silently ignores a parameter it does not recognise**, so
    offering a guessed filter returns an UNFILTERED page while the
    caller believes it was filtered - a wrong answer that explains
    itself. That is the failure `SearchJobsInput` withheld its date
    filter to avoid, and the argument is identical here. Checklist rows
    6 and 13.4 are what settle the names.
    """

    model_config = ConfigDict(extra="forbid", strict=True)


class GetCandidateInput(InboundModel):
    """Arguments for `get_candidate`.

    `candidateId` is `[INFERRED]` like everything else on this route,
    and it is offered anyway because it is the only one whose ABSENCE
    would leave the tool unable to do the thing it is named for. The
    difference from a guessed filter is the failure mode: a wrong
    filter name returns an unfiltered page that looks filtered, while a
    wrong id parameter returns a page the tool can see is not one
    record.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    candidate_id: Annotated[
        JobviteIdentifier,
        Field(description="The candidate's Jobvite `eId`."),
    ]


#: The status Jobvite is `[INFERRED]` to return on a duplicate create
#: (`JOBVITE-CONTRACT.md:260`, DESIGN.md:1471-1474). Named so the
#: mapping to `/problems/conflict` is one comparison against one
#: constant rather than a magic number beside a status test.
#: This module's own claim to a coverage role from DESIGN.md:1443-1445,
#: read by `docs/reviews/check-coverage-floors.py`. The design names the
#: roles and not the paths, and the claim lives HERE rather than in a
#: role-to-module map in the checker, which would be a hand-kept list
#: beside its container. The checker asserts the two sets are EQUAL.
COVERAGE_ROLE: Final = "the write"

DUPLICATE_CANDIDATE_STATUS: Final = 409

#: The `201` envelope's outer key (`JOBVITE-CONTRACT.md:575-583`).
#: **The write response spells the identifier `EId` where every read
#: spells it `eId`** - §9 hazard 1, Jobvite's asymmetry and not ours -
#: so both ids below are read through `read_identifier`, which accepts
#: either spelling. A test pins the asymmetry so a later tidy-up cannot
#: turn it into a bug.
CREATE_APPLICATION_KEY: Final = "application"
CREATE_CANDIDATE_KEY: Final = "candidate"


class CreateCandidateInput(InboundModel):
    """Arguments for `create_candidate`.

    **THIS MODEL CARRIES CANDIDATE PII BY CONSTRUCTION** - name, email
    and phone are what it is for (DESIGN.md:1786). Every string is
    `SafeText`, which bounds the length and rejects control characters
    and bidi overrides before dispatch (§2.1, B25).

    **`send_email` DEFAULTS TO `false`, and the default is the whole
    point** (DESIGN.md:239): it mails a live human, so the dangerous
    value is never the one reached by omission. It is also an argument
    like any other and is disclosed in the approval request by name
    (DESIGN.md:1134-1143).
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    first_name: Annotated[
        SafeText,
        Field(description="The candidate's given name."),
    ]
    last_name: Annotated[
        SafeText,
        Field(description="The candidate's family name."),
    ]
    email: Annotated[
        SafeText,
        Field(description="The candidate's email address."),
    ]
    job_eid: Annotated[
        JobviteIdentifier,
        Field(description="The `eId` of the job this application attaches to."),
    ]
    # THE DEFAULT IS DECLARED ONCE, AS THE ASSIGNMENT, AND THIS IS A
    # MEASURED CORRECTION. These three fields carried `Field(default=X)`
    # AND a trailing `= X`; pydantic takes the assignment, so the
    # `Field` copy was inert. U10's M9 mutation flipped the inert one to
    # `True` and the send_email default test passed against it - a
    # surviving row on the one field in this server that decides whether
    # a live person is emailed. Two declarations of one default is the
    # two-lists defect at the width of a single field.
    mobile: Annotated[
        SafeText | None,
        Field(description="The candidate's mobile number."),
    ] = None
    source: Annotated[
        SafeText | None,
        Field(description="Free-text name of the application source."),
    ] = None
    send_email: Annotated[
        bool,
        Field(
            description=(
                "Ask Jobvite to EMAIL THIS PERSON. Defaults to false. "
                "Setting it true sends mail to a real human being."
            ),
        ),
    ] = False


class CreateCandidateResult(BaseModel):
    """What the caller gets back from an approved write.

    Deliberately small: the two identifiers Jobvite minted, and nothing
    echoed back. Echoing the submitted PII would put candidate data in a
    second place for no gain, and the caller already has it.

    `warnings` is **always present, never omitted**. The schema is
    built in serialisation mode with `extra="forbid"`, so a key absent
    from the schema is rejected by the client's own validator - and the
    post-write audit-failure branch has to be able to add one
    (DESIGN.md:794-800). A field that only sometimes exists would make
    that branch the one shape the schema refuses.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    candidate_eid: str | None = None
    application_eid: str | None = None
    warnings: list[str] = Field(default_factory=list)


def build_create_body(params: CreateCandidateInput) -> dict[str, Any]:
    """Build the `POST /api/v2/candidate` body.

    `JOBVITE-CONTRACT.md:269-300`. Every field on that route is
    `[INFERRED]`; checklist row 10 is the one write in a customer-agreed
    window that replaces the inference with an observation.

    **`none_to_blank` is the REQUEST direction of the `""`/null
    unification** (§9 hazard 4): Jobvite's own fields use `""` where a
    null belongs, so a body we send uses the vendor's spelling rather
    than ours.

    Args:
        params: The validated arguments.

    Returns:
        The JSON body, nested exactly as the contract records it.
    """
    return {
        "candidate": {
            "firstName": params.first_name,
            "lastName": params.last_name,
            "email": params.email,
            "mobile": none_to_blank(params.mobile),
            # THE FLAG THAT EMAILS A LIVING PERSON. It is forwarded as
            # the caller sent it and is never defaulted here - the
            # default lives on the input model, where the schema shows
            # it to the caller, and a second default in this function
            # would be a place for the two to disagree.
            "sendEmail": params.send_email,
            "application": {
                "jobEId": params.job_eid,
                "sourceType": "CareerSite",
                "source": none_to_blank(params.source),
            },
        }
    }


def build_create_result(payload: dict[str, Any]) -> CreateCandidateResult:
    """Read the two minted identifiers out of the `201` envelope.

    **THE CASING ASYMMETRY IS PINNED HERE** (§9 hazard 1): the write
    response spells them `EId`, every read spells them `eId`, and
    `read_identifier` accepts both. That is Jobvite's inconsistency, not
    ours, and a normalisation that "tidied" it would break this route.

    A missing id yields `None` rather than an invented error: the `201`
    body is `[INFERRED]` throughout, and guessing a shape for a response
    nobody has observed is how a wrong answer acquires an explanation.

    Args:
        payload: The decoded create response.

    Returns:
        The two identifiers, each `None` when the body carried neither
        spelling of it.
    """
    application = payload.get(CREATE_APPLICATION_KEY)
    if not isinstance(application, dict):
        return CreateCandidateResult()
    candidate = application.get(CREATE_CANDIDATE_KEY)
    return CreateCandidateResult(
        application_eid=read_identifier(application),
        candidate_eid=(
            read_identifier(candidate) if isinstance(candidate, dict) else None
        ),
    )


def conflict_or_original(exc: Exception) -> Exception:
    """Turn Jobvite's `409` into `/problems/conflict` (DESIGN.md:1471).

    **Detection, not prevention, and the difference is the point.**
    None of §2.2's gates stops an *authorised* write being made twice;
    what this does is name the duplicate in `detail` so a caller can see
    what happened instead of reading a generic upstream failure. The
    `409` shape itself is `[INFERRED]` and never observed, so even the
    detection rests on a hypothesis until a credential exists (C4-D2).

    Args:
        exc: Whatever the client raised.

    Returns:
        A `DuplicateCandidateError` when Jobvite reported the duplicate
        status, otherwise the original exception unchanged.
    """
    if (
        isinstance(exc, JobviteUpstreamError)
        and exc.upstream_status == DUPLICATE_CANDIDATE_STATUS
    ):
        return DuplicateCandidateError(
            f"Jobvite reported this candidate already exists and refused the "
            f"duplicate ({exc.upstream_message}). The write was NOT retried; "
            f"retrying it would create a second record and may email the "
            f"candidate a second time."
        )
    return exc


def to_candidate(raw: dict[str, Any]) -> Candidate:
    """Fence, then map one Jobvite record onto the allow-listed model.

    **The allow-list is applied by naming each key**, not by handing
    Jobvite's object to pydantic and trusting `extra="forbid"` to
    reject it. The two differ in the direction that matters:
    `extra="forbid"` would make a NEW Jobvite field an error and take
    the whole call down, while DESIGN.md:192-195 requires it to be
    **dropped**. Failing closed here means dropping the field, not
    failing the tool.

    Args:
        raw: One element of the `candidates` array, straight off the
            wire and not yet fenced.

    Returns:
        The admitted, fenced, normalised subset.
    """
    fenced = fence_payload(raw, CANDIDATE_FENCING_PATHS, f"{CANDIDATES_ENVELOPE_KEY}[]")
    application = fenced.get("application")
    return Candidate(
        eid=fenced.get("eId"),
        first_name=fenced.get("firstName"),
        last_name=fenced.get("lastName"),
        email=fenced.get("email"),
        home_phone=fenced.get("homePhone"),
        work_phone=fenced.get("workPhone"),
        city=fenced.get("city"),
        state=fenced.get("state"),
        country=fenced.get("country"),
        title=fenced.get("title"),
        work_status=fenced.get("workStatus"),
        application=(
            _to_application(application) if isinstance(application, dict) else None
        ),
    )


def _to_application(raw: dict[str, Any]) -> CandidateApplication:
    """Map the already-fenced application object.

    Args:
        raw: The fenced `application` object.

    Returns:
        The admitted subset, with both dates normalised.
    """
    resume = raw.get("resume")
    job = raw.get("job")
    return CandidateApplication(
        eid=raw.get("eId"),
        workflow_state=raw.get("workflowState"),
        disposition=raw.get("disposition"),
        source=raw.get("source"),
        source_type=raw.get("sourceType"),
        # §9 HAZARD 2, NORMALISED HERE AND NOWHERE ELSE. `_int_or_none`
        # rather than a bare cast: a Jobvite field that arrives as a
        # string would otherwise raise inside a read tool, and a read
        # is recoverable.
        sent_date=epoch_ms_to_date(_int_or_none(raw.get("sentDate"))),
        last_updated_date=epoch_ms_to_date(_int_or_none(raw.get("lastUpdatedDate"))),
        resume=(
            CandidateResume(format=resume.get("format"), content=resume.get("content"))
            if isinstance(resume, dict)
            else None
        ),
        job=(
            CandidateJob(
                eid=job.get("eId"),
                title=job.get("title"),
                department=job.get("department"),
                location=job.get("location"),
            )
            if isinstance(job, dict)
            else None
        ),
    )


def _int_or_none(value: object) -> int | None:
    """Accept only a real integer timestamp.

    `bool` is excluded explicitly: it is a subclass of `int`, and
    `epoch_ms_to_date(True)` would return `1970-01-01` for a flag.

    Args:
        value: Whatever the envelope carried.

    Returns:
        The integer, or `None` for anything else.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def build_result(payload: dict[str, Any], max_results: int) -> CandidateSearchResult:
    """Apply the in-tool result cap to one page (DESIGN.md:508-516).

    **Reports rather than truncates.** A capped result is a mismatch
    against `total` by design, so the cap is surfaced in `summary` and
    is explicitly not an anomaly to be logged.

    **`total` comes from the envelope, never from `len(items)`**
    (DESIGN.md:525-540, and `JOBVITE-API.md:398` measured it: 5
    requested, a total in the hundreds of thousands returned). Counting
    the page instead would make `showing N of N` true on every call and
    delete the only signal that a page was capped.

    Args:
        payload: The decoded Jobvite envelope.
        max_results: `JOBVITE_MAX_RESULTS`.

    Returns:
        The capped page, with the cap reported.
    """
    items = payload.get(CANDIDATES_ENVELOPE_KEY) or []
    candidates = [
        to_candidate(item) for item in items[:max_results] if isinstance(item, dict)
    ]
    raw_total = payload.get(TOTAL_ENVELOPE_KEY)
    total = raw_total if isinstance(raw_total, int) else len(items)
    return CandidateSearchResult(candidates=candidates, total=total)


def register(
    server: FastMCP[Any],
    settings: Settings,
    *,
    client_factory: Callable[[], JobviteClient] | None = None,
) -> None:
    """Register the candidate read tools, each if it is enabled.

    **The gate is `settings.enabled_tools` and it is checked per tool**
    (DESIGN.md:990-1007): registration is the deploy-time control, and a
    tool that registers and then refuses is a tool a client can still
    see. The two tools are gated independently because they are two
    tools.

    Args:
        server: The instance to register on.
        settings: Settings that have already passed
            `validate_settings`.
        client_factory: Builds the `JobviteClient` for one invocation.
            Substituted in tests to inject `httpx2.MockTransport`
            (DESIGN.md:1440-1441).
    """
    wanted = {
        SEARCH_CANDIDATES,
        GET_CANDIDATE,
        CREATE_CANDIDATE,
    } & settings.enabled_tools
    if not wanted:
        return

    transport = Transport(settings.mcp_transport)

    # Resolved ONCE, at registration, and refused loudly if absent.
    # `validate_settings` has already refused a configuration enabling
    # these without credentials, so reaching here with `None` is a
    # programming error rather than a user's input.
    if settings.api_key is None or settings.api_secret is None:
        msg = (
            f"{sorted(wanted)} enabled but credentials are unset; "
            f"validate_settings should have refused this configuration"
        )
        raise ValueError(msg)
    api_key = settings.api_key
    api_secret = settings.api_secret

    def _client() -> JobviteClient:
        if client_factory is not None:
            return client_factory()
        # `max_results`, `company_id` and `start_base_overrides` are
        # all passed for the reason `tools/jobs.py` records at length:
        # the factory's argument list should describe the SETTINGS, not
        # the current caller. Omitting `max_results` was U6's F1 and
        # omitting `start_base_overrides` was R5-M1 - the same defect
        # twice, in one argument list.
        return JobviteClient(
            api_key=api_key,
            api_secret=api_secret,
            company_id=settings.company_id,
            max_results=settings.max_results,
            outbound_budget_seconds=settings.outbound_budget_seconds,
            start_base_overrides=(
                None
                if settings.pagination_start_base is None
                else dict.fromkeys(CLIENT_ROUTES, settings.pagination_start_base)
            ),
        )

    def _meta_of(ctx: Context) -> Any:  # noqa: ANN401 - the framework's own type
        """Read the wire `_meta`, by NAMED attribute access (R4-L2).

        `getattr(..., "meta", None)` turns a future library rename into
        a silent drop of the trace context from every audit event, at
        exit 0. Reading `.meta` by name makes a rename an
        `AttributeError` at the call site.

        Args:
            ctx: The invocation context.

        Returns:
            The request `_meta` mapping, or `None`.
        """
        request_context = ctx.request_context
        return request_context.meta if request_context is not None else None

    if SEARCH_CANDIDATES in wanted:

        @server.tool(
            name=SEARCH_CANDIDATES,
            # `mode="serialization"`, never the default: pydantic's
            # `mode="validation"` omits computed fields, so `showing`
            # and `summary` would be absent from the advertised schema
            # while every result carried them - and `extra="forbid"`
            # renders as `additionalProperties: false`, so the client's
            # own validator then rejects our success payload.
            output_schema=CandidateSearchResult.model_json_schema(mode="serialization"),
            annotations={"readOnlyHint": True},
        )
        async def search_candidates(
            params: SearchCandidatesInput,
            ctx: Context,
        ) -> ToolResult:
            """Search Jobvite candidates.

            Returns one page of candidates, capped at the server's
            configured result limit and reporting `showing N of total`
            rather than truncating silently. Candidate free text is
            fenced and EEO fields are never returned.
            """
            with audit_scope(
                SEARCH_CANDIDATES,
                transport,
                arguments=params.model_dump(mode="json"),
                meta=_meta_of(ctx),
            ) as event:
                try:
                    async with _client() as client:
                        payload = await client.request("GET", CANDIDATES_PATH)
                    result = build_result(payload, settings.max_results)
                except Exception as exc:  # noqa: BLE001 - every failure is a problem
                    event.result_status = "error"
                    emit(event, AuditPhase.READ)
                    return ToolResult(
                        structured_content=problem_from_exception(
                            exc, event.request_id
                        ),
                        meta={REQUEST_ID_META_KEY: event.request_id},
                        is_error=True,
                    )
                emit(event, AuditPhase.READ)
                return ToolResult(
                    structured_content=result.model_dump(mode="json"),
                    meta={REQUEST_ID_META_KEY: event.request_id},
                )

    if GET_CANDIDATE in wanted:

        @server.tool(
            name=GET_CANDIDATE,
            output_schema=Candidate.model_json_schema(mode="serialization"),
            annotations={"readOnlyHint": True},
        )
        async def get_candidate(
            params: GetCandidateInput,
            ctx: Context,
        ) -> ToolResult:
            """Fetch one Jobvite candidate by `eId`.

            Returns a single record, not a page. Candidate free text is
            fenced and EEO fields are never returned.
            """
            with audit_scope(
                GET_CANDIDATE,
                transport,
                arguments=params.model_dump(mode="json"),
                meta=_meta_of(ctx),
            ) as event:
                try:
                    async with _client() as client:
                        payload = await client.request(
                            "GET",
                            CANDIDATES_PATH,
                            params={CANDIDATE_ID_PARAM: params.candidate_id},
                        )
                    record = _one_record(payload)
                except Exception as exc:  # noqa: BLE001 - every failure is a problem
                    event.result_status = "error"
                    emit(event, AuditPhase.READ)
                    return ToolResult(
                        structured_content=problem_from_exception(
                            exc, event.request_id
                        ),
                        meta={REQUEST_ID_META_KEY: event.request_id},
                        is_error=True,
                    )
                emit(event, AuditPhase.READ)
                return ToolResult(
                    structured_content=record.model_dump(mode="json"),
                    meta={REQUEST_ID_META_KEY: event.request_id},
                )

    if CREATE_CANDIDATE in wanted:

        @server.tool(
            name=CREATE_CANDIDATE,
            output_schema=CreateCandidateResult.model_json_schema(mode="serialization"),
            # THE THREE ANNOTATIONS ARE A CONTRACT, NOT DECORATION. A
            # host reads them to decide how loudly to ask.
            # `readOnlyHint`
            # is stated FALSE rather than omitted: an absent hint and a
            # false one are not the same claim, and this is the one tool
            # in the server where the difference reaches a live person.
            annotations={
                "destructiveHint": True,
                "idempotentHint": False,
                "readOnlyHint": False,
            },
        )
        async def create_candidate(
            params: CreateCandidateInput,
            ctx: Context,
        ) -> ToolResult | InputRequiredToolResult:
            """Create a candidate in the live Jobvite ATS.

            **Requires an approval response from the host and refuses to
            write without one.** The approval request names the
            candidate, the target job and whether `send_email` is true,
            because an outbound message to a third party is separately a
            gated action.

            **This creates a real record and cannot be undone**, and
            with `send_email` true Jobvite mails the candidate. It is
            never retried: a retried write would create a second record
            and may email the candidate a second time.
            """
            with audit_scope(
                CREATE_CANDIDATE,
                transport,
                arguments=params.model_dump(mode="json"),
                meta=_meta_of(ctx),
            ) as event:
                decision = await resolve_approval(
                    ctx,
                    message=build_approval_message(
                        candidate=f"{params.first_name} {params.last_name}",
                        job=params.job_eid,
                        send_email=params.send_email,
                    ),
                    # NO PII IN THE STATE. It travels to the client and
                    # back and is not covered by the argument redaction
                    # `audit_scope` applies on the way in.
                    request_state=f"{CREATE_CANDIDATE}:{params.job_eid}",
                )

                if isinstance(decision, ApprovalPending):
                    # THE MRTR FIRST LEG. No side effect is attempted,
                    # and the phase is still `BEFORE_SIDE_EFFECT`: if
                    # the audit write fails here the call fails, which
                    # is the direction that cannot email anyone.
                    event.approval_state = ApprovalState.PENDING
                    event.approval_mechanism = decision.mechanism
                    emit(event, AuditPhase.BEFORE_SIDE_EFFECT)
                    return decision.result

                event.approval_state = decision.state
                event.approval_mechanism = decision.mechanism

                if not decision.approved:
                    # EVERY REFUSAL PATH LANDS HERE: a decline, an
                    # acceptance carrying `approve: false`, and an era
                    # this server cannot identify. No client call is
                    # made, so no row can be created.
                    event.result_status = "error"
                    emit(event, AuditPhase.BEFORE_SIDE_EFFECT)
                    return ToolResult(
                        structured_content=problem_from_exception(
                            ApprovalRefusedError(
                                "The host did not return an approval for this "
                                "write, so nothing was created."
                            ),
                            event.request_id,
                        ),
                        meta={REQUEST_ID_META_KEY: event.request_id},
                        is_error=True,
                    )

                # NO AUDIT, NO WRITE (DESIGN.md:784-785). This emission
                # is BEFORE the POST and its failure raises
                # `AuditWriteError`, which leaves the ATS untouched.
                emit(event, AuditPhase.BEFORE_SIDE_EFFECT)

                try:
                    async with _client() as client:
                        payload = await client.request(
                            "POST",
                            CANDIDATES_PATH,
                            json_body=build_create_body(params),
                        )
                    result = build_create_result(payload)
                except Exception as exc:  # noqa: BLE001 - every failure is a problem
                    event.result_status = "error"
                    # `AFTER_WRITE`'s POLICY, deliberately, on a path
                    # where the write may or may not have landed: it
                    # never raises and never fails the call, because a
                    # timeout after a successful create is
                    # indistinguishable from a refused one and an error
                    # that makes the model retry emails a second live
                    # human. **Its RETURN VALUE is discarded here** -
                    # that string says the write succeeded, which is not
                    # known on this path. The stderr line it also writes
                    # is generic and is correct.
                    emit(event, AuditPhase.AFTER_WRITE)
                    return ToolResult(
                        structured_content=problem_from_exception(
                            conflict_or_original(exc), event.request_id
                        ),
                        meta={REQUEST_ID_META_KEY: event.request_id},
                        is_error=True,
                    )

                # SUCCESS WITH A WARNING, NEVER AN ERROR
                # (DESIGN.md:794-800). A post-write audit failure
                # returned as a problem object would tell the caller the
                # operation failed when it did not, and the caller's
                # reasonable answer is to retry.
                warnings = emit(event, AuditPhase.AFTER_WRITE)
                return ToolResult(
                    structured_content=attach_audit_warnings(
                        result.model_dump(mode="json"), warnings
                    ),
                    meta={REQUEST_ID_META_KEY: event.request_id},
                )


def _one_record(payload: dict[str, Any]) -> Candidate:
    """Take the single record out of a candidate-list envelope.

    **The route answers with a PAGE even when asked for one record**
    (`JOBVITE-CONTRACT.md:229`: `candidateId` is a query parameter on
    the list route, not a sub-path). So this tool reads the first
    element rather than pretending the envelope is different.

    **`JOBVITE-CONTRACT.md:161` records that the record-level
    "not found" shape is UNKNOWN** - an empty array, a 404 body, or
    something else. An empty array therefore yields an empty
    `Candidate` rather than an invented error type: guessing a shape
    for a response nobody has observed is how a wrong answer acquires
    an explanation. Checklist row §13.4 settles it.

    Args:
        payload: The decoded envelope.

    Returns:
        The first candidate, or an empty one.
    """
    items = payload.get(CANDIDATES_ENVELOPE_KEY) or []
    for item in items:
        if isinstance(item, dict):
            return to_candidate(item)
    return Candidate()
