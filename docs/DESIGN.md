# fast-mcp-jobvite - Design

Status: **FROZEN, revision 6.** Frozen 2026-08-28 03:04 PM CDT.

**Only a numbered ADR in `docs/adr/` may change this document from here.** ADR-0012 onward carries a
`Type:` field, because an ADR does two different jobs here and after the freeze the difference
decides whether the change was permitted (§13).

**What the freeze does and does not certify.** It certifies that a review round returned 0 Critical,
0 High and 0 Medium; that §11's must-mitigate table is empty; and that every conditional dismissal
in the standards register was re-tested and recorded standing or tripped. It does **not** certify
that this document is correct. Three carried risks are recorded rather than resolved:

- **§8's SIGTERM case is the one required case whose deletion the gate provably cannot see**, and it
  guards a defect verified 3-of-3 in the wild. It is the most expensive case in §8 to write and
  dropping it would cost nothing anyone notices. It is carried as a named line item with an owner on
  the implementation plan, because this document cannot carry it.
- **The last review's own findings were applied without being independently re-reviewed.** Reviewing
  the application of a round's findings is infinite regress, so it was stopped deliberately; one of
  those fixes was a choice between two options the reviewer left open, not a dictated edit.
- **Five defects were found by attempting to build, none by reading** - a README that did not exist,
  a CI pipeline that did not exist, and three settings specified in prose with no name. Prose review
  reached 0C/0H/0M while a unit sat unbuildable. **The next defect of that class is reachable only by
  implementation, and freezing is how this document stops pretending otherwise.**

Review history, which is a record rather than a status anyone must keep in sync:

| Round | Result |
|---|---|
| `DESIGN-R1.md` | 0c / 2h / 1m |
| `DESIGN-R2.md` | 0c / 3h / 1m |
| `DESIGN-R3.md` | 0c / 5h / 6m, threat model VALIDATED WITH CHANGES |
| `DESIGN-R4.md` | 0c / 6h / 11m, **recommended against freezing** |
| `CONFORMANCE-B1-B106.md` | 42 satisfied / 22 partial / 37 unaddressed |
| `CONFORMANCE-DESIGN-ARTIFACT.md` | threat model mandated and missing; caching standard had gone live |
| `SPIKE-CLAIM-AUDIT.md` | 55 claims: 39 supported, 8 overstated, 3 unsupported, 2 not found, 4 stale |

**The freeze rule, stated as a rule rather than as an accomplished fact:** this document freezes
when a review round returns 0C/0H/0M against it **and** §11's must-mitigate table is empty, and
**after that** only a numbered ADR in `docs/adr/` may change it.

**The second condition is not redundant, and omitting it was a defect a review caught.** 0C/0H/0M
is a statement about the *review*; the must-mitigate table is a statement about the *design*. They
came apart in practice: rounds returned few findings while the table still held High rows whose
remedies were edits to this very document, and `threat-modeling.md:86` requires inherent Critical
and High mitigated **before implementation proceeds**. Freezing in that state would have frozen a
document instructing against its own next step, and put its own stated remedies behind the ADR
process that exists to protect a *settled* design. An earlier revision also stated the second half
in the present tense while four rounds were still finding defects, which read as though the freeze
had already happened.

Last updated: 2026-08-28 03:04 PM CDT.

Evidence: `docs/research/JOBVITE-API.md`, `JOBVITE-CONTRACT.md`, `FASTMCP.md`,
`FASTMCP-SPIKE-4.md`, `STANDARDS.md`, `COMPLIANCE-SPEC.md`. Decisions: `docs/DECISIONS.md`.

**What is and is not verified in this document**, stated precisely because a blanket compliance
claim is exactly the kind of self-certification that has already been wrong once on this project:

- **Every claim about FastMCP or the MCP protocol is executed.** Each rests on a spike in
  `FASTMCP-SPIKE-4.md` against `fastmcp==4.0.0b4`, or on a clause quoted at its `file:line`.
- **Every claim about Jobvite's error transport is recorded.** Byte-exact captures.
- **No claim about a Jobvite success response is verified**, because none has ever been observed.
- **Two mechanisms designed here have never been executed**: the capability-drift diff (§10),
  marked at its point of use and carried in §11's Residual Risks, and the **circuit breaker**
  (§4.3), which sits beside a *measured* retry finding and has no supporting execution of its own.
  The test for this list is not "is it built" - almost nothing here is - but "does it sit among
  executed results and borrow their credibility". §12 states the same pair on that criterion; an
  earlier revision of this line said *one* and disagreed with it. The runtime `start`-base probe
  an earlier revision named beside it **does not exist** - it was cut (§4.5) in favour of
  base-agnostic paging, whose one load-bearing property, that `start=0` is accepted and returns
  records, is observed in the one genuine `200` (`JOBVITE-API.md:399`).

A reviewer should treat "verified" in this document as meaning one of the first two, and should
challenge any sentence that reads as verified without belonging to them.

---

## 1. What this is

An MCP server exposing Jobvite, an applicant tracking system, as tools a model can call. It runs
over stdio for local clients and over Streamable HTTP when hosted.

It is not an SDK, a sync engine, or a cache. **It caches no Jobvite response** (§7.7). The only
state outliving a call is an HTTP connection pool and the framework rate limiter's in-process token
buckets - neither of which holds candidate data.

**In-process state is per-connection on stdio**, generally and not just for any one mechanism:
stdio spawns a fresh server process per connection, so anything held in memory resets between
connections. Nothing in this design depends on cross-call memory, which is why that is a footnote
rather than a hazard - but it is the reason any future design that wants such memory cannot get it
from a module-level variable.

**Single-process is load-bearing**, not incidental: ADR-0002's rate-limiting argument assumes one
process. Running this multi-worker breaks it silently: each worker gets its own buckets, so the
effective limit multiplies by the worker count while every log line still reports the configured
number. **That is the standard's own objection, not our extrapolation** -
`backend/rate-limiting.md:94-97` forbids in-memory limiters *"because they desynchronize across
replicas"*, and gives the worked case: *"a 4-replica deployment with in-memory limits gives each
client 4× the intended quota."* Workers substitute for replicas exactly. Stated here because it is the kind of assumption
someone violates by deploying normally.

### 1.1 The constraint that shapes everything

Jobvite publishes no public API documentation. `developer.jobvite.com` has never existed - the
Wayback Machine holds zero snapshots, and a third-party client citing it fabricated the citation.
The support site is login-gated. No OpenAPI document exists. There is no sandbox:
`api-stg.jobvite.com` fails DNS. **Nobody building this holds a Jobvite credential.**

**One** genuine Jobvite `200` exists in our evidence: a third-party VCR cassette recorded against a
live tenant (`JOBVITE-API.md` §6.1). It is the project's strongest success-shape evidence and it
already answers what a success envelope looks like. Its body cannot be copied here - it was
captured with a live credential and contains real candidate data including EEO fields - so it is
used as a **structural** reference only (§8). Every other success shape remains a hypothesis.

Three consequences run through the design:

1. **Scope is limited to what is evidenced.** Of 17 live v2 resources, five operations have a
   usable contract. The rest are route names that answer 401 when they exist and 404 when they do
   not. We ship tools for the five and none for the twelve.
2. **Every success-path response shape is a hypothesis.** The design must fail loudly when a
   hypothesis is wrong rather than degrade into a plausible empty result.
3. **Response handling is defensive by default.** We do not assert schemas we have never seen.

---

## 2. Tool surface

Five tools. `ai/agent-guardrails.md:47-49` requires a minimal allow-list because an unused tool is
attack surface, and the evidence permits no more. (`ai/tool-calling.md:54` uses the same phrase
about loose parameter types, which is a different obligation - §2.1.)

| Tool | Jobvite operation | Kind | Data class |
|---|---|---|---|
| `search_candidates` | `GET /api/v2/candidate` | read | candidate PII |
| `get_candidate` | `GET /api/v2/candidate?candidateId=` | read | candidate PII |
| `search_jobs` | `GET /api/v2/job` | read | public job data |
| `get_job_feed` | `GET /v1/jobFeed` | read | public job data, **separate credential** |
| `create_candidate` | `POST /api/v2/candidate` | **write, destructive** | candidate PII |

`search_candidates` and `get_candidate` are separate tools because **their output cardinality
differs**: `?candidateId=` returns one record, the paged form returns a page. Under
`strict=True` one tool cannot have two return schemas. (The earlier justification - "tighter
schemas" - was the weaker argument.)

**`POST /api/v2/task` is excluded.** It requires an RSA key exchange with Jobvite as a human
onboarding step, uses AES-256-ECB, and its decrypted success shape is unknown. Highest cost,
lowest value, nothing depends on it.

### 2.1 Tool schemas

Every tool takes a typed Pydantic model, never a free-form dict. `strict=True`, extra keys
forbidden, explicit `max_length` on every string, regex on every identifier. Outputs are
snake_case regardless of Jobvite's casing.

**Four structural limits bound an inbound argument payload**, taken as the defaults from
`backend/input-validation.md:220-226` and enforced before dispatch, with `:391-392` requiring body
size at the middleware and depth limiting on recursive structures:

| Constraint | Limit |
|---|---|
| Max nesting depth | 5 levels |
| Max list items | 1,000 |
| Max dict keys | 100 |
| Max total request body size | 1 MiB |

**These are a different axis from §4.5's page caps**, and conflating them is the mistake worth
naming: 500 and 1000 there are *outbound transport* limits on what we ask Jobvite for, and bound
nothing about what a caller sends us. `customField[]` is open-ended (§6.1) and is exactly the shape
these limits exist to bound.

**Input is rejected on control characters and encoding before dispatch**, which `max_length` does
not cover and the output allow-list cannot: `ai/prompt-injection.md:124-125` requires
*"input size/encoding limits before dispatch; reject control characters and oversized payloads"*.
A candidate name carrying a NUL or a bidi override is a well-formed short string, so every
length-and-regex check passes it. The allow-list is an **output** filter and §6.1's fencing is
applied on the way back out, so neither reaches an inbound argument on its way to Jobvite. Strings
are validated as UTF-8 and rejected if they carry C0/C1 control characters other than tab, newline
and carriage return, or Unicode bidirectional overrides.

**What a caller receives when one of these limits fires, stated here because this section said the
wrong thing and §5.1 said the right one four hundred lines away.** Every check above lives in the
input models, so every one of them runs **before the tool body** and is raised by the framework.
By §5.1's own executed reasoning - a problem object is safe precisely because it is *returned*
rather than *raised* - **nothing here can return one.** An earlier revision of this paragraph said
*"Rejection is a `400` problem object per §5.1"*, which was wrong twice over: no problem object
reaches the caller on this path at all, and had one done so its status would be **422**, not 400,
per the registry mapping in §5.1. These rejections are §5.1's third exception rather than an
exception to it. **The rule still fails closed**, which is the whole of what B25 and B30 require,
and §8 tests each limit with a positive control showing an ordinary argument still passes.

**Outputs are allow-listed models, not passthrough.** A field Jobvite returns that is not on the
model does not reach the caller, and it fails closed: a new Jobvite field is dropped until someone
admits it deliberately. That is **containment**, and it satisfies the special-category-data position
(§6.2).

**Containment is not injection-fencing.** They are different controls with different failure modes,
and an earlier revision claimed one mechanism covered both. Allow-listing decides *whether a field
leaves*; fencing decides *how an admitted field is presented to a model* (§6.1). A field can be
correctly admitted and still carry an injection payload.

**The two lists live in different key spaces** - models are snake_case, fencing paths are
camelCase Jobvite paths - so **the fencing paths are generated from the output models** rather than
maintained beside them, and a test fails when any model field has no fencing decision. Two
hand-maintained lists that must correspond is a defect waiting for the first schema change.

### 2.2 `create_candidate` is guarded two ways

It is the only write, it creates real records in a real ATS, its side effect is an email to a
live human, and there is no sandbox.

**The governing clause is `ai/agent-guardrails.md:70-73`**, and this section exists to discharge it:

> *"**Default-deny destructive operations.** Any irreversible or high-blast-radius action (delete,
> financial transaction, **outbound message to a third party**, infra change, mass update) MUST
> pause for human approval before execution. Fail closed: no approver, no action."*

Three things in it are load-bearing here and are easy to miss. It names **outbound message to a
third party** as destructive in its own right, which is why §7.5's approval must disclose the email
and not only the record - the email is not a side effect of the gated action, it *is* one of the
gated actions. It says **MUST pause before execution**, which is a per-invocation obligation that a
deploy-time flag alone cannot meet. And it says **fail closed: no approver, no action**, which is
the rule every refusal path below is measured against.

**Two gates, deliberately not three:**

1. **Deploy-time.** Not registered unless `JOBVITE_ENABLE_WRITES=true`. Enforced server-side; a
   client cannot bypass it. Conceptually the weakest control and the only unconditionally
   enforceable one, which is exactly why it is kept.
2. **Per-invocation approval** via the dual-era guard (§7.5). Fails closed on every measured path.

**A confirmation-token mechanism was designed, spiked, and then cut.** It would have been a third
gate on paper and was not one in fact: **neither it nor elicitation can distinguish a human from an
agent**, so an autonomous caller defeats the token by calling preview and then create. Stacking two
controls with the same blind spot does not close the gap, it makes it feel closed. The two gates
kept are **orthogonal** - one server-side and client-independent, one per-invocation - and
orthogonal weak controls compose where duplicate ones do not.

It also had a measured defect on our default transport: stdio spawns a fresh server process per
connection, so an in-process token store is per-connection there.

Also: `send_email` defaults to `false`, and the tool is never retried (§4.3). Neither gate
establishes that a human was involved - see §7.5 on what we may honestly claim.

**The other replay path, and the ceiling on what we can do about it (B108).**
`backend/resilience.md:146-151` permits a write to be retried only when an **idempotency key** lets
the downstream dedupe the replay. We take the other branch of that clause: the server never
auto-retries `create_candidate`, by construction (§4.3). What that does not reach is a **caller**
re-issuing the write - a model retrying after a timeout, or a human approving twice - which is
C4-D2. **We evaluated the remedy the clause names and cannot build it.** Nothing in the research
corpus establishes that Jobvite accepts a dedupe key on candidate creation: `POST /api/v2/candidate`'s
documented body carries no such field, no idempotency header appears in any source we hold, and the
nearest thing Jobvite exposes - `importDuplicates` on the Engage Contact Import API - is a policy
toggle on a different endpoint of a different product, not a client-supplied key, and cannot tell a
replay from a genuine second submission. Jobvite publishes no API documentation and offers no
sandbox, so this cannot be settled before a credential exists (§12, item 1). **We therefore state
the ceiling rather than claim a control**, on the same footing as the read-only-key requirement in
§7.2: the residual duplicate is accepted, it is C4-D2, and it is carried in Residual Risks.

**Two things this disposal deliberately does not claim.** It does not claim the `409` prevents the
duplicate - if Jobvite really conflicts on a repeat, the downstream dedupes and C4-D2's *"detection,
not prevention"* would be an understatement, but that behaviour is `[INFERRED]` everywhere it
appears and checklist row 10 is what settles it. And it does not claim nothing could be built: a
server-side seen-set is possible independent of Jobvite - §4.5 already uses that pattern for
pagination - and it was considered and not taken, because it needs durable state with a TTL and a
defined restart behaviour to guard a Medium whose remedy would then itself be unverified. **This
disposal expires** the day a credential or Jobvite documentation shows a dedupe key exists on this
endpoint, at which point the clause becomes a live obligation on the client.

Annotations: `destructiveHint: true`, `idempotentHint: false`, `readOnlyHint: false`. The other
four are `readOnlyHint: true`. **Annotations are advisory only** - verified: one non-test
reference exists in the entire framework, a field-name alias table, and nothing acts on them. We
set them because a well-behaved host may prompt on them. **The design never counts them as a
control.**

---

## 3. Module layout

```
src/fast_mcp_jobvite/
  __main__.py                 entry; transport selection; signal handling; logging before imports
  server.py                   FastMCP instance, middleware stack, lifespan
  config.py                   pydantic-settings; SecretStr; fails fast on missing config
  errors.py                   exception hierarchy + RFC 9457 problem construction
  audit.py                    the per-invocation audit event (§5.3)
  approval.py                 the dual-era approval guard (§7.5)
  services/jobvite_client.py  httpx2: auth, the error rule, pagination, resilience
  tools/candidates.py         search_candidates, get_candidate, create_candidate; their input models
  tools/jobs.py               search_jobs, get_job_feed; their input models
  models/                     allow-listed OUTPUT models, one per tool; no input model lives here
  utils/correlation.py        request_id_var, the per-invocation correlation ContextVar (§5.3)
  utils/redaction.py          log redaction; untrusted-content fencing
  utils/normalise.py          casing, dates, empty-string/null unification
  utils/constraints.py        the shared inbound constraint types every input model reuses:
                              control-character and bidi rejection, and the depth/list/dict-key
                              limits (§2.1)
```

Every input model imports its constraints from `utils/constraints.py`. No input model defines its
own (ADR-0012).

No cache module, no bulk module, no custom logging module. Framework middleware and `loguru`
cover the first and third; the second is speculation.

---

## 4. The Jobvite client

### 4.1 Authentication, and three credential classes

v2 credentials travel as headers, `x-jvi-api` and `x-jvi-sc`. **A URL containing a secret is never
constructed**, even though Jobvite's own published sample code does exactly that.

`GET /v1/jobFeed` is the exception: it structurally requires `api`, `sc` and `companyId` as query
parameters. Its URL is classified sensitive - never logged whole, never in an exception message,
`sc=` redacted before any log line. Enforced in one place, `utils/redaction.py`, with a test that
fails if a secret can reach a log record.

**The guarantee is carried by `JobviteClient`, not by the server entry point (ADR-0026).** Redacting
at our own sink covers every producer in a process whose handlers we own and nothing in a process
whose handlers belong to someone else, so an embedder that constructs `JobviteClient` directly has
no sink of ours at all. The object that holds the credential therefore installs the filter on the
`httpx2` logger from its constructor, defaulting to installing, with an **opt-out constructor
keyword and never a `Settings` field**. Two constraints are load-bearing. **The install is
idempotent**: a client is constructed once per invocation, so a filter appended per construction
would stack one per tool call forever, which is a leak inside the code path added to prevent one.
**The logger name is derived from the imported module rather than retyped**: the package is vendored
as `httpx2`, and a filter installed on `httpx` attaches to a logger this library never writes to,
where it would refuse nothing and every test of it would pass.

**This gives three credential/data classes, which is also the token-scoping axis (§7.2):**
candidate PII, public job data, and the job feed's separate `companyId` credential.

Credentials are `SecretStr` throughout, resolved with `.get_secret_value()` only when building a
request.

### 4.2 The error-detection rule

**The load-bearing behaviour in this codebase.** `api.jobvite.com` returns `HTTP 200` with a body
of `{"status":{"code":401,...}}`. A client branching on HTTP status reads that as success, finds
no `candidates` key, and reports zero candidates for a rejected credential.

**Invariant:** a response is successful only if the body carries no `status.code >= 400` **and**
the HTTP status is below 400. Both, every call.

The parser cannot assume JSON and cannot dispatch on content type either. **Three error encodings
are handled** on the routes we call: a JSON status envelope, plain text with no `Content-Type`
header at all, and a Tomcat HTML page. **HR-XML is a hardened fallback, not a handled case** - it
appears on `/v1/candidate`, which we do not call. If XML ever arrives it is parsed with
`defusedxml` and treated as an error body; entity expansion on attacker-reachable input is not a
risk worth taking for a route that should never respond to us.

### 4.3 Resilience

Ordered timeout, then retry, then circuit breaker.

- **Timeouts explicit and per-phase.** No SDK default, no single scalar.
- **Retries live inside this module**, via `tenacity` with jitter, and only for connection errors,
  timeouts and 5xx. The retry budget is bounded by **a server-side ceiling we choose**, not by the
  inbound request's deadline, because there is no inbound deadline here - see the note below.
- **`create_candidate` is excluded from retry by construction**, not by configuration. This is
  forced: `RetryMiddleware` cannot be scoped to exclude a tool, and narrowing `retry_exceptions`
  does not help because FastMCP wraps tool exceptions as `ToolError(...) from original` and the
  retry check unwraps one level of `__cause__`. Measured: one call, **four rows created**.
- **One circuit breaker for Jobvite. 4xx must not trip it** - a bad candidate id is the caller's
  problem, not a health signal.
- **An open breaker is distinguishable from an outage without inventing a type.** Both use
  `/problems/service-unavailable` at 503, per the registry; what distinguishes them is `detail`,
  which says whether Jobvite failed or whether we have stopped calling it, plus a `retry_after`
  hint. An earlier revision minted two slugs for this. The distinction is real and worth making;
  a new contract-bearing type URI is not the way to make it.
- **Jobvite's `429`, if it exists, is retried and then mapped to 503**, honouring `Retry-After`
  when present. No 429 has ever been observed and no rate-limit header is returned (§4.4), so this
  path is written defensively and is unexercised.
- **A `Retry-After` the upstream volunteered is passed on, on whatever problem shape results**
  (ADR-0030). `retry_after` is an optional RFC 9457 extension member, not a registry row and not a
  new type URI, so §5.1's seven mandated members are unchanged and this is not an eighth. Its
  absence means *we were not told*, never *do not retry*, and callers must tolerate it being absent,
  which is the common case (§4.4: no rate-limit header is returned). Only a value the upstream
  actually sent is passed on this way; the open breaker's hint above is computed from our own
  remaining window and is ours to compute precisely because it describes our own state.

**`backend/resilience.md:74-76` has no referent on this transport, and saying so is the honest form of
compliance with it.** The clause reads *"Timeouts MUST be **shorter than the inbound request's own
deadline** so a slow dependency surfaces as a fast, typed error rather than a hung request
worker."* **MCP gives us no inbound deadline to be shorter than.** There is no HTTP request worker
to hang and no caller-supplied timeout the server can read, so a phrase like "budget inside the
inbound timeout" - which this section used to carry - names a bound that does not exist and reads
as compliance while establishing nothing.

What the clause is *for* still applies, so we satisfy the intent by supplying the deadline the
transport does not: **a total outbound budget, configured, that bounds all attempts for one tool
invocation**, so a slow Jobvite surfaces as a typed 503 rather than an unbounded wait.

**Where this does not reach, stated because the clause's own failure mode occurs here for a
different reason.** §7.5 records that an abandoned approval **hangs the call** with no server-side
bound, because the elicitation handler runs in the client's process. That is a hung call of exactly
the kind `:74-76` exists to prevent, and no outbound budget touches it - it is not waiting on a
dependency. It is C4-D1, it is in Residual Risks, and it is disclosed to integrators. The outbound
budget bounds Jobvite; nothing bounds a client that never answers.

### 4.4 Rate limiting

Jobvite returns **no rate-limit headers of any kind**. Nothing to parse, nothing to feed a
backoff calculation, so throttling is client-side and configuration-driven.

**Inbound** throttling uses **FastMCP's own `RateLimitingMiddleware`** - the framework's, not one
we wrote - with four constraints established by execution:

- **`get_client_id` is mandatory.** The default keys every caller to the literal string
  `"global"` despite the docstring implying per-client. One noisy integrator would throttle
  everyone.
- **Burst is sized `desired_calls + 2` per session**, where the `+ 2` is measured against
  FastMCP's own client and is not a protocol constant. It counts every MCP request, not just tool
  calls. Measured: burst 3 yields 1 tool call, 5 yields 3, 10 yields 8; independently, burst 6
  yields 4 on both protocol eras. **The `2` is that client's connect sequence** - `server/discover`
  plus `tools/list` - not a property of the limiter or of MCP. A client whose connect sequence is
  heavier (one that also lists resources or prompts, both of which `server/discover` advertises)
  burns more, and `desired + 2` then **under-provisions and refuses real tool calls**. That is the
  failure direction worth stating: over-provisioning a thinner client is harmless, under-provisioning
  is not. No client but FastMCP's has been measured.
  On stdio the toll is paid per connection rather than per process lifetime, because stdio spawns a
  fresh server process - and therefore a fresh bucket - for every connection (§1).
- **Limits are startup-only.** Mutating them has no effect; only `limiters.clear()` applies new
  values, **and that resets every client's quota**, making a config reload a quota amnesty and
  repeated reloads a trivial bypass.
- **A trip raises `MCPError`, not an `is_error` result**, so a rate-limit refusal does **not**
  carry an RFC 9457 problem object. §5 states this rather than claiming uniformity it does not
  have.

On stdio there is no token and thus no `client_id`, but there is exactly one caller, so the
global bucket is correct there. **That is reasoning, not a measurement** - every limiter arm was run
in-memory or over HTTP, and the limiter has never been exercised on stdio. It follows from stdio's
one-process-per-connection behaviour rather than from an executed result.

**Every one of those measurements was sequential and single-client**, and all of them used FastMCP's
own client. Bucket behaviour under simultaneous callers - the case that actually matters in
production - is unverified, and `limiters.clear()` was never tested under load. ADR-0002 records
that as a limitation rather than implying coverage we do not have.

**Outbound, we throttle ourselves against Jobvite's only documented operating envelope**, which is
prose rather than a number: call it on an as-needed basis, and anything more frequent than once a
day must be filtered. That is the sole guidance Jobvite gives. So the client carries a configurable
outbound rate limit with a conservative default, and the README must state the envelope once one exists (§10.1), because a user
syncing hourly is outside what the vendor documents and should know it.

**That outbound throttle IS NOT IMPLEMENTED. The two rules below constrain whoever builds it; they do not
describe what runs today** (ADR-0025). `JOBVITE_OUTBOUND_RATE_LIMIT` is declared, typed, defaulted,
documented in `.env.example` and covered by config tests, and **no code reads it** - which is the defect
ADR-0025 was raised over. This section states the shape the implementation must take so that the unit
which builds it does not choose that shape silently.

- **The throttle is PER-PROCESS**, scoped like §4.3's circuit breaker and for the same reason: it exists
  to protect Jobvite from us, and Jobvite sees our process, not our scans. A per-scan throttle lets N
  concurrent scans each spend the full allowance, so the rate arriving at Jobvite is N times the limit
  and the limit means nothing. Two mechanisms with one purpose must not hold opposite ideas of what
  they are protecting.
- **Time spent waiting on the throttle SPENDS §4.3's outbound budget.** A bound that excludes the term
  dominating the wait is not a bound, and a caller does not care whether we were waiting on Jobvite or
  waiting on ourselves.

**Those two rules compose with §4.5's paging, and that composition is the implementer's to check.**
ADR-0025 works the arithmetic through on this design's own worked example and is where it is recorded.
Whoever implements the throttle must either size the defaults so the composition holds, or raise it as
an ADR against §4.5 - not settle it silently, which is the outcome ADR-0025 exists to prevent.

The mandated Redis token bucket is not used: the standard's rationale is replica
desynchronisation, and a single-process server has no replicas. **ADR-0002.**

### 4.5 Pagination, and detecting the `start` base at runtime

Offset-based, `start` and `count`. Page cap **500** on v2, **1000** on `/v1/jobFeed`. These are
the *transport* limits. The *result* limit returned to a model is separate and configurable
(§7.7); the two are related by `min(transport_cap, configured_result_cap)`.

**The `start` base is genuinely unresolved** - three third-party clients disagree; the only
statement from Jobvite is its own v1 documentation, which is 1-based. If we are wrong we silently
skip the first record of every page.

**An earlier revision proposed a runtime probe and its logic was inverted.** It read "identical
first ids means the server clamps and either base is safe". That is backwards: identical ids mean
the server is **1-based and clamped 0 to 1**, and clamping protects only page one - a 0-based
caller then re-reads the boundary record on **every subsequent page**. The probe also contradicted
§9 hazard 5: with no stable sort, two requests can return different first ids for reasons having
nothing to do with the base, so the "different ids" branch was unsound in exactly the direction
that looks like successful detection. It cached an indeterminate verdict (a tenant with one
candidate always probes "identical") and applied one verdict across resources whose bases differ.

**What we do instead, and it needs no probe.** `start` is **1-based**, per Jobvite's own v1
documentation, which is the only statement from the vendor. Correctness does not rest on that being
right, because paging is made **base-agnostic**:

- **Every scan starts at `start=0`.** This is the whole mechanism and it is one character. A
  0-based server returns record zero; a 1-based server returns the same first page it would have
  returned anyway. **What is observed, and all that needs to be:** `start=0` is accepted and returns
  records, in the one genuine Jobvite `200` in our evidence (`JOBVITE-API.md:399`). That falsifies
  "1-based and strict", which is the only hypothesis under which `start=0` could have failed.
  **It does not establish that a 1-based server clamps 0 to 1** - the same source says so in its own
  sentence, and the two remaining hypotheses (0-based, or 1-based-with-clamping) are exactly the
  pair it cannot separate. We do not need to separate them: `start=0` is safe under both, which is
  the whole point of being base-agnostic. Starting at 1 is the only choice that can silently lose a
  record, because on a 0-based server record zero is never requested.
- Returned ids are checked against a per-scan seen set, so a clamped or overlapping page **drops
  duplicates**. Note what this does and does not do: **de-duplication defends against over-reading
  only.** It cannot recover a record that was never returned, which is exactly why the fix is
  starting at 0 rather than de-duplicating harder.
- **Completeness is checked against `total`, and ONLY on an exhaustive scan.** An earlier revision
  said a gap would be "detected and logged", which had no mechanism - `eId` is an opaque
  8-character identifier and you cannot find a hole in a set of opaque ids. Comparing the unique-id
  count to the reported `total` is a real check, but **it is only meaningful when the caller asked
  for everything.** A capped call is a mismatch by design: §7.7's own worked example is
  `showing 50 of 1,240`. Wiring the check to every call would fire the alarm on the default path
  and train everyone to ignore it. So the check runs when a scan terminates on a short page having
  requested no limit, and a capped result reports `showing N of total` instead, which is not an
  anomaly and is not logged as one.
- The base is per-resource, not global. `/v1/jobFeed` is `[OFFICIAL]` 1-based; the v2 resources are
  `[INFERRED]`. They are configured separately.
- `JOBVITE_PAGINATION_START_BASE` overrides per resource for anyone who has established the truth.
- Checklist row 2 still settles it definitively the day a credential exists.

De-duplicating on the way out is cheaper than detecting the base, and unlike a probe it cannot be
fooled by an unstable sort.

Paging terminates on a short page (`len(items) < count`), never on `total`. `total` is reported
and never trusted as a loop condition.

**That rule names the condition paging must not use and names none it must, which leaves an
exhaustive scan correct and unbounded at the same time: a server that ignores `start` and answers a
full page every time is paged forever. Two bounds close it and neither substitutes for the other
(ADR-0024).** A **zero-progress break** - a full page that adds nothing to the seen set and nothing
to the unidentified count - terminates the loop and marks the scan incomplete; it cannot fire on
healthy paging, because a full page that adds no records means the server is not advancing. A
**record ceiling** not derived from `total` bounds a server that advances but never shortens,
likewise marking the scan incomplete. **The ceiling counts RECORDS and not pages**, because the page
cap above is 500 on v2 and 1000 on `/v1/jobFeed` and a page ceiling is a different number of records
at each; the bound has to be sane at every page size this section permits. Neither bound reads
`total`, so the rule above is intact.

---

## 5. Errors, logging, and correlation

### 5.1 The error contract

Failures return `ToolResult(structured_content=<problem>, is_error=True)` carrying a complete RFC
9457 problem object: `type`, `title`, `status`, `detail`, `instance`, `request_id`, `timestamp`.
No `success: true/false` envelope exists anywhere in this repository.

`type` is a relative `/problems/<slug>`. `instance` is
`urn:fast-mcp-jobvite:invocation:<request_id>`.

**`type` and `status` come from the registry at `error-contract.md:96-108`, not from Jobvite.** An
earlier revision passed the upstream status through and minted `/problems/jobvite-*` slugs of its
own. Both were wrong:

- **Passing Jobvite's status through is a user-facing bug, not only a compliance one.** A Jobvite
  `401` reaching the caller as `401` tells them *their* credentials failed, when what failed is the
  credential *this server* holds. The registry's answer is `/problems/external-service-error`,
  **502**, *"Upstream service failure"* - which is what actually happened.
- **`:210` makes a published `type` URI a contract**, so inventing slugs is a promise we would owe
  forever. The registry already has a type for every condition we produce.

| Condition | Type | Status |
|---|---|---|
| Any Jobvite failure, including its 4xx | `/problems/external-service-error` | 502 |
| Jobvite unreachable, breaker open, timeout | `/problems/service-unavailable` | 503 |
| Argument or schema validation | `/problems/validation-error` | 422 |
| Candidate or job id not found | `/problems/resource-not-found` | 404 |
| Duplicate candidate on create | `/problems/conflict` | 409 |
| Caller's token lacks the scope | `/problems/forbidden` | 403 |
| An approval was required and none was returned | `/problems/forbidden` | 403 |
| Anything unmapped, including an unhandled exception in a tool body | `/problems/internal-error`, *"Internal Server Error"* | 500 |

**`/problems/forbidden` names two conditions and mints no second slug for the pair** (ADR-0031). A
scope denial and a refused approval are both "this write was not authorised"; `detail` says which,
and the precedent is the one §4.3 already sets for the two 503 shapes, where an open breaker and an
outage share a type and are distinguished in `detail`. Minting `/problems/approval-refused` would be
a published `type` URI, which the bullet above makes a promise this project owes forever, and the
alternative the "anything unmapped" row would otherwise select is `/problems/internal-error` -
telling a caller this server is broken when a refusal is the control working as designed.

**`about:blank` keeps its actual scope** and no other: an unmapped **HTTP status received from
Jobvite**, where we genuinely have no type for what the upstream returned
(`error-contract.md:115`, RFC 9457 §4.2.1 - an external reference, and the filename is on this line
so `check-cross-references.py` reads it as one). It is not the answer for an unhandled exception in
our own tool body, which the
registry already names `/problems/internal-error`. Every problem object therefore carries a
`status`, without exception, which is what makes the seven-member requirement above checkable
(ADR-0017).

Jobvite's own status and message are **not discarded** - they go in `detail` and in the audit
event, where they help whoever is debugging, rather than in `status`, where they mislead whoever is
calling. Validation is **422**, per the registry, not 400.

**Problem objects are the primary channel for expected conditions** - unknown candidate id,
rejected credential, validation failure. Verified across five arms: because they are *returned*
rather than *raised*, they are untouched by `ErrorHandlingMiddleware`, by `transform_errors`, and
by `mask_error_details`. They are the only error shape no configuration can distort. Raising is
reserved for the genuinely exceptional.

**Three honest exceptions to uniformity**, stated rather than glossed. The third is the most
common and was the last to be admitted:
- A rate-limit refusal raises `MCPError` and carries no problem object (§4.4). **ADR-0002 covers
  this**, because `rate-limiting.md:361-362` separately requires a 429 to use a problem detail, and
  substituting the limiter does not dispose of that clause.
- An abandoned approval never resolves at all (§7.5).
- **No pre-dispatch argument rejection carries a problem object.** FastMCP validates arguments
  **before the tool body runs**, so by this section's own reasoning - problem objects are safe
  because they are *returned* rather than *raised* - nothing can return one. The rejection is
  raised by the framework. This is the failure path callers hit most often, so implying uniformity
  here would be the most misleading place to do it. The rejection still fails closed and is
  unit-tested, which is what B12 and B23 actually require.

  **This exception covers all three of §2.1's inbound controls, not just the schema.** A schema
  violation, a control-character or encoding rejection, and a structural-limit rejection are one
  path with one shape: they all live in the input models, they all run before the body, and none of
  them can return anything. Stating it as *"an argument-schema violation"* was narrower than the
  truth and let §2.1 claim a `400` problem object for the other two without contradicting anything
  a reader would notice.

  **Consequence for the table above, recorded rather than left to be discovered.** Its
  `/problems/validation-error` **422** row is therefore **unreachable on the pre-dispatch path**.
  It is not dead: it is what a validation failure detected *inside* the tool body uses - a
  semantically invalid argument combination, or a validation error Jobvite itself returns. The row
  stays, and it is worth knowing which half of validation it actually serves, because a slug that
  looks like it covers all validation and covers only some of it is the kind of thing that gets
  cited in a compliance claim.

### 5.2 `problem+json` and the transport

`error-contract.md:44` requires the media type `application/problem+json` on all error responses.
An MCP tool error travels inside a 200 OK JSON-RPC body whose content type the transport fixes.
**That clause is violated in the letter and no implementation can satisfy it: ADR-0003.**

The ADR rests on transport-level auth rejections, which are genuine HTTP responses and do carry
`problem+json`. **There is no health endpoint** - an earlier draft claimed one as mitigation and
none is specified anywhere in this design. Note the consequence honestly: transport-level
rejections exist only on the opt-in HTTP transport, **so on the default stdio transport
`problem+json` is honoured nowhere at all.**

### 5.3 Audit logging and `request_id`

`ai/agent-guardrails.md:40` mandates audit logging of every tool invocation;
`ai/tool-calling.md:171-173` names the fields: tool name, validated arguments with PII redacted,
result status, latency, correlation id.

**We emit this ourselves in `audit.py`, and do not assume middleware provides it.** Three of the
eight framework middlewares exercised shipped a default wrong for this project, so "the framework
probably logs it" is not a basis for a compliance claim. `StructuredLoggingMiddleware` runs with
`include_payloads=False` - for this server those payloads are candidate PII - which means it emits
*no* arguments, not *redacted* arguments. The mandated field is redacted arguments, so we produce
them.

**`request_id` originates here.** MCP has no `X-Request-ID` middleware and no ambient request id.
`audit.py` mints a UUIDv4 per tool invocation, and it is the same value that appears in the
problem object's `request_id` and inside its `instance` URN. Where the HTTP transport receives an
inbound `X-Request-ID`, it is validated as a UUIDv4 before use - unvalidated inbound ids are a
log-forging vector - and echoed.

**`request_id_var` carries it to code that never sees the invocation (B40).** The retry and
circuit-breaker hooks are called *by the resilience library*, not by our call site, so there is no
parameter to thread the id through and no argument we control at the point the log line is written.
`utils/correlation.py` holds a single `ContextVar[str | None]` named `request_id_var`. **That name is not our choice: `ai/tool-calling.md:173-175` mandates the canonical triple verbatim** - header `X-Request-ID`, log field `request_id`, ContextVar `request_id_var` - so this discharges the clause rather than merely resembling it. `audit.py`
sets it in the same statement that mints the id, before the first outbound attempt, and resets it in
a `finally` so an id cannot leak into the next invocation on a reused worker task.

A ContextVar rather than a module global, because `asyncio` runs invocations concurrently on one
thread and a module global would interleave: two candidates fetched in parallel would each log the
other's id about half the time, and the corruption is silent - every line still carries a
well-formed UUID. That is the failure this mechanism exists to prevent, and it is why the §8 case
below asserts under concurrency rather than on a single call.

**Retries and breaker transitions are logged, each carrying `request_id` (B39).**
`backend/resilience.md:224-226` requires both. Every retry attempt logs the attempt number, the
elapsed delay and the exception type; every breaker transition logs the direction
(`closed->open`, `open->half_open`, `half_open->closed`) and the counter that triggered it. **The breaker must evaluate transitions on the call path, not from a background timer.** A ContextVar is per-Task: a half-open expiry fired by a timer task has no `request_id_var` set and would log `None`, failing the §8 case. Several Python breaker libraries do exactly that. **B47 does name one - `circuitbreaker ^2` is a blessed library and B37 says to use it - and an earlier revision of this paragraph said no library was selected, which mischaracterised the obligation and turned a one-library test into an open-ended survey.** What is actually open is whether `circuitbreaker ^2` evaluates half-open expiry on the call path or from a timer, which is one experiment against the blessed candidate. So this is a constraint on that choice rather than an observation about one. **If no library satisfies it, an inline breaker in `services/jobvite_client.py` is the sanctioned fallback** - a counter, a state and a timestamp checked on entry. Adopting a library and then constraining its scheduler is the worse trade, because the constraint would live in our code while the behaviour lived in theirs. Stated here so the answer is not decided by whoever happens to implement it. Neither
line carries the URL, because the v1 `jobFeed` URL is itself a secret (§4.1) and a retry line is
exactly where an unredacted URL would otherwise reach a log.

**`request_id` reaches the caller on every result, in `_meta` (B42).** `request-middleware.md:144`
requires the id echoed on **every response, success and error**. The error half is the problem
object's own `request_id` member, which `error-contract.md` specifies and which stays. The success
half goes in the result's `_meta`, under the namespaced key
`com.evolvconsulting.fast-mcp-jobvite/requestId` - `io.modelcontextprotocol/*` is reserved, and the
spec's own `SERVER_INFO_META_KEY` is the precedent: server-stamped, and documented as display and
debugging only, never behaviour or security, which is exactly this value's class.

**Not a field on the output models, and the reason is executed rather than reasoned.** §2.1's models
set `additionalProperties: false`, and `ClientSession.validate_tool_result` validates
`structured_content` against the cached output schema unconditionally - the same unconditional
validation that broke `ResponseLimitingMiddleware` (§7.7). An undeclared top-level `request_id` in
structured content is **rejected**: *"Additional properties are not allowed ('request_id' was
unexpected)"*. Declaring it on every model would work, and is rejected for a different reason: it
would put transport plumbing inside the model-facing payload, drag it through §6.1's fencing paths
and §7.7's size budget, and make it part of five tools' data contracts. `_meta` is the protocol's
own channel for this, and the validator never inspects it.

**One way to set `meta` and have it silently discarded, which is worth knowing before it is
debugged.** `ToolResult.to_mcp_result()` short-circuits on `_raw_mcp_result` before it looks at
`meta` (`fastmcp/tools/base.py:176-177`), and `from_mcp_result` stashes exactly that when it wraps
an upstream `CallToolResult` (`:168`). **Setting `.meta` on a wrapped result is therefore dropped
with no error and no warning** - the id simply never appears. Our tools construct their results
rather than wrapping an upstream one, so this should not arise; it is recorded because the failure
is silent, and because it is why §8's case asserts the id **on the wire result rather than on the
`ToolResult` object** - the latter assertion would pass while the wire carried nothing.

**A caller reads it as a normal field on the result** - `result.meta["com.evolvconsulting.fast-mcp-jobvite/requestId"]`
on the raw SDK, and the same through FastMCP, which copies `meta` through. **The README must
document the key**, because a caller cannot guess it, and an id a caller cannot reach discharges
nothing. One consequence to know: `ToolResult.to_mcp_result()` branches on
`if self.meta is not None or self.is_error`, so setting `meta` makes every result return as a full
`CallToolResult` rather than the bare content/tuple form. That is a shape change, not a behaviour
change, and it is stated here because it is invisible at the call site.

**The audit event also records the inbound trace context, beside `request_id` and never merged with
it.** `ai/tool-calling.md:176-177` requires the LLM trace/span id so a tool call ties back to its
turn, and says explicitly that trace ids are separate from `request_id`. **This is reachable on the
pinned stack today**: `mcp` injects W3C trace context into every outgoing request's `_meta` per
SEP-414 (`mcp/shared/jsonrpc_dispatcher.py:390`, whose own comment notes `_meta` stays on the wire
even with a no-op tracer), `opentelemetry-api` is a hard dependency of `mcp 2.1.1` so nothing new is
added to §10's pins, and FastMCP already extracts it server-side
(`fastmcp/server/telemetry.py:95`) through a public helper (`fastmcp/telemetry.py:263`, exported at
`:308`). We read `ctx.request_context.meta` directly rather than depending on FastMCP's span
plumbing, because `telemetry_mode()` may be `"off"`, in which case the extractor returns the ambient
context unchanged while the wire `_meta` still carries the header.

`trace_id` and `span_id` are **recorded when present, omitted when absent, and never synthesised**:
a locally-minted id in a field named for the host's trace joins nothing while looking like it does.
**Whether a given host injects at all is unverified** - the same limitation §7.5 records for the
host survey - so this is written to the wire contract, not to a measured client.

**What this does not do:** on stdio the id correlates lines *within* one invocation and nothing
more, because there is no inbound id and no caller identity to join against (§4.4). It is a
within-invocation correlation key, not a distributed trace id, and a reader who assumes otherwise
will over-trust it.

**The audit event includes `approval_state`.** `agent-guardrails.md:121-123` names it explicitly,
and `create_candidate` is gated two ways and emails a live human - without it, the only record
that a gated write was authorised would not exist. `:79` also requires recording **who** approved,
which §7.5 establishes we can never know: the host may auto-respond with no human present. We
record what we can prove - that an approval response was received and what it said - and
**ADR-0009** records that identity is unsatisfiable **for the approver specifically, and not for
the caller.**

**`approval_state` is drawn from a closed set of four** (ADR-0033): `approved` - a response arrived
and authorised the write; `refused` - a response arrived and did not, so a human said no; `pending` -
the request went out and no answer has come, so no write has happened and may never; `unavailable` -
no handler existed to ask, so nobody was asked. **`pending` and `unavailable` are the pair most
likely to be collapsed and must not be**: one is an abandoned conversation, the other a conversation
that never started, and collapsing them makes an abandoned approval indistinguishable from an
unconfigured host in the only record either leaves. The set is closed for the same reason
`approval_mechanism`'s is - a value emitted into an audit record is a contract - and a fifth value
is an ADR.

**The audit event also records which approval path produced the response**, in a field named
`approval_mechanism`, drawn from a closed set: `elicitation`, `mrtr`, `no_handler` - the three
paths §7.5 establishes. **The sessionless member is named `mrtr` and not `sampling`** (ADR-0028):
that path is Multi Round-Trip Requests - `InputRequiredResult` plus `ctx.input_responses` - and is
not sampling in the MCP sense at all, so the vocabulary named a mechanism this server has no path
to. The set is closed for the reason `error-contract.md`'s registry is closed:
a value emitted into an audit record is a contract, and an open string invites a fourth spelling of
the first three. The value names a protocol path and carries no PII. **This is *how* the answer
arrived, not *who* gave it** - ADR-0009's boundary is untouched (ADR-0021).

That distinction is load-bearing and is the kind an ADR silently swallows. Two different identities
are in play: *who approved* is unknowable, because a host may auto-respond with no human present;
*which client invoked the tool* is knowable **on the HTTP transport**, where §4.4 already derives it
through `get_client_id` in order to rate-limit on it. **That value is recorded in the audit event.**

**On stdio there is no client identity to record**, because there is no token - §4.4 says so, and
this section must not contradict it. The audit event records the transport and, on stdio, states
that caller attribution is unavailable rather than emitting the literal `"global"` and implying an
identity. An implementer who wires `get_client_id` on stdio, receives `"global"`, and closes this
finding believing attribution exists would leave the gap open behind a value that looks like an
answer.
An ADR read as "identity in the audit log is unsatisfiable" would close a gap it never considered,
in a document about to be frozen.

**Candidate PII reaches the audit *path* by construction** - the arguments to redact are the candidate's own fields - **and what is emitted carries none of it in the clear**, because the approval request describes the
candidate about to be written. `approval_state` therefore falls inside §4.1's single redaction point
rather than beside it, and the audit stream carries the same handling class as the log stream.

**Audit-write failure has a stated policy, and the third case is the one that matters:**
- **Before the side effect:** fail the call. No audit, no write.
- **On a read tool:** log to stderr and continue. A read is recoverable and losing the tool is
  worse than losing one audit line.
- **After a successful write:** return **success with a warning**, never an error. If a post-write
  audit failure surfaced as an error, the model would retry, and **a second live human would be
  emailed.** The audit hole is the lesser harm. **The warning goes to stderr, not to the audit stream that
  just failed** - routing it down the channel whose failure it reports is how the record of the
  failure is lost too.

  **What the caller receives, specified because "success with a warning" is not a shape:** the
  normal success result, `is_error=False`, with a `warnings` array in its structured content naming
  the audit failure. **Not a problem object.** §5.1 makes problem objects the primary channel for
  expected *failures*, and this is not one - the write succeeded. Returning a problem object would
  say the operation failed when it did not, and the caller's reasonable response to that is to
  retry, which emails a second live candidate. Preventing exactly that is why this branch exists,
  so its result shape must not reintroduce it.

`mask_error_details=True` is set explicitly at construction; FastMCP defaults it to `False`,
which sends the full text of any unhandled exception to the client. **Masking is client-facing
only**: the full traceback still reaches the server log, so a credential is never interpolated
into an exception message and the log stream is treated as sensitive.

---

## 6. Untrusted and sensitive content

### 6.1 Candidate free text is attacker-authored

Résumé bodies, cover letters, notes and any free-text field a candidate typed are **input from
people outside the operator's organisation, fed directly to a model**. That is exactly the threat
`ai/prompt-injection.md` addresses.

Every such field is fenced before it reaches a tool result, and delimiter tokens occurring inside
the content are stripped so content cannot close its own fence.

**The allow-list is path-keyed with wildcards, not name-keyed.** Name-keying collides: `title` and
`eId` each appear at multiple depths in our own fixtures, and `customField[]` is open-ended. Keys
are paths like `candidates[].application.job.title`.

**Fencing is defined for strings only.** An unknown non-string field is **dropped**, not
stringified - stringifying invents a representation and collides with `strict=True` output models.

Red-team cases live in the main suite and are merge-gating.

### 6.2 Special-category data

Our own fixtures show `gender`, `race` and `veteranStatus` in candidate responses. These are EEO
fields, they are special-category personal data, and left alone they would flow straight to a
model.

**A previous revision justified this by saying the GDPR standard is `priority: optional`. That was
false and checkable.** `architecture/gdpr-data-rights.md:9` reads `priority: required`; corpus-wide
the only `optional` files are twelve README indexes, and no substantive standard is optional. The
research it came from made a *scope* argument, correctly, and the compression into a priority claim
was mine.

**The correct argument is scope.** That standard's obligations attach to systems that **store**
personal data - DSAR policies per table, erasure dispositions, a `gdpr_erasures` table. This server
stores nothing and Jobvite is the controller's system of record, so the DSAR and
right-to-be-forgotten machinery does not reach us. **ADR-0008 makes that argument, not the priority
one.**

**What does bind, and is not waived:** `:119-129`, records of processing under Article 30, is
field-level and names downstream processors. Routing candidate PII to a model is exactly that, so
`docs/data-inventory.md` records the categories handled, the purpose, and the recipients. And the
residue that always binds is no-PII-in-logs, since a log file is the one place a stateless server
can accidentally become a store of personal data.

On the fields themselves: **they are not in any output model and therefore never leave the
server.** The allow-listed output models of §2.1 are the mechanism, and
they generalise - the point is not "drop three fields" but "nothing reaches the model that was not
deliberately admitted."

---

## 7. Server, transport, configuration

### 7.1 Transport

**stdio by default**, HTTP opt-in via `JOBVITE_MCP_TRANSPORT=http`. HTTP binds
**`JOBVITE_MCP_HOST`, default `127.0.0.1`**, on **`JOBVITE_MCP_PORT`, default `8000`**, with
`allowed_hosts`/`allowed_origins` set whenever the bind address is not loopback.

**Both are named here because an earlier revision said "unless told otherwise" and named nothing
that does the telling.** That is the same SHAPE as B15 - a setting specified in prose with no name - though B15 itself is the result-size obligation and does not cover these. Found the same way, by someone trying to
build against it and discovering the unit could not be started, let alone bound off-loopback to
exercise the TLS refusal §8 tests.

**Off-loopback requires TLS, and the server refuses to start without it.** A non-loopback bind
carries a bearer token and candidate PII over the wire; `allowed_hosts` and `allowed_origins`
address a different threat entirely and do nothing about plaintext. So binding a non-loopback
address without `JOBVITE_TLS_TERMINATED_BY_PROXY=true` is a startup failure, not a warning.

**This server terminates no TLS of its own.** There is no certificate configuration and none is
planned: a terminating proxy in front is the only off-loopback shape this design supports, which is
what `.env.example` offers and the only thing the refusal can actually check. An earlier revision of
this paragraph offered *"or certificates configured here"* as a second arm and named nothing that
configures one - **B15's defect for a third time, four lines below the paragraph added to fix it**,
because that edit swept the sentence it was changing rather than the section.

`JOBVITE_TLS_TERMINATED_BY_PROXY` is deliberately an **operator assertion the server cannot
verify**, rather than a check of `X-Forwarded-Proto`. Trusting that header would look more rigorous
and be strictly worse: it is spoofable by anyone who can reach the port, so the server would be
authenticating the attacker's own claim about the attacker's connection. **An assertion that fails
loudly when absent beats a check that appears to verify and does not.** Outbound to Jobvite is HTTPS
with `httpx2`'s default verification, and verification is never disabled.

**Sessionless `2026-07-28` is the default era**, with the handshake era served simultaneously -
verified on one server, one port. Two deployment consequences:
- Any reverse proxy, load balancer or WAF must pass `mcp-method`, `mcp-name` and
  `MCP-Protocol-Version` through untouched. A proxy stripping unknown headers breaks the server in
  a way that looks like our bug.
- `server/discover` advertises only `2026-07-28` even though handshake-era clients are served.

### 7.2 Authentication and scopes

HTTP auth uses `StaticTokenVerifier` built at startup from **`JOBVITE_HTTP_TOKENS`**, a JSON object
mapping each bearer token to the scopes it holds - `{"<token>": ["candidates:read", "jobs:read",
"feed:read"]}`. It is **secret-class**: unset by default, absent from `.env.example`'s filled values
like every other credential, and redacted wherever configuration is echoed. Unset with
`JOBVITE_MCP_TRANSPORT=http` is a startup failure, not an open server - the same fail-fast posture
§7.3 applies to every required variable.

**Scopes follow the three data classes of §4.1**: candidate PII, public job data, and the job feed. That axis survives
regardless of the tool set; the earlier axis - "a read-only token never sees the write tool" -
collapsed whenever the write was out of scope.

**`require_scopes` removes an unauthorised tool from `tools/list` entirely**, and a direct call
returns "Unknown tool", not a permission error. Good behaviour, confusing failure mode; the README
documents it or every support conversation starts in the wrong place.

**stdio is unauthenticated by design.** Anything able to spawn the process can call its tools; the
trust boundary is the operating system's, not this server's. That is the correct model for a local
subprocess, and it is stated rather than left implicit. It also means `create_candidate` on stdio
rests on the deploy-time flag plus approval, not on scopes.

**No ambient authority, and why a model-supplied id is not an instance of it here (B107).**
`ai/agent-guardrails.md:54-56` requires that a tool never act on behalf of an arbitrary user, and
`ai/tool-calling.md:108-111` requires tools to re-validate authorization off the request principal,
**never off a value the model supplied**. Both clauses were uncited by every instrument this project
has until an audit went looking for them, so this paragraph exists to dispose of them in the open
rather than to leave a reader inferring it.

**The demand is substantially met on the HTTP transport.** `require_scopes` enforces off the bearer
token's scopes - the request principal - and a scope the caller does not hold removes the tool from
`tools/list` entirely. No model-supplied value participates in that decision.

**What is not implemented is row-level scoping, and the reason is the deployment model rather than
an oversight.** `get_candidate(candidate_id)` does resolve a record from a value the model supplied,
with no per-record authorization check. That is not ambient authority **because there is no
caller-scoped record set to enforce**: a deployment holds one Jobvite API key and one `companyId`,
so every caller who can reach the server is already authorised for exactly the same records. A
row-level check would have nothing to discriminate on, and adding one would assert a boundary that
does not exist.

**Stated as a property of our deployment model, not of Jobvite.** One key and one company id per
deployment is how we configure it (§7.3). It is **not** a claim about Jobvite's permission model,
which we have never seen - the same limit §7.2 records for read-only keys, and over-reading a vendor
property is a mistake this document has already had to correct twice.

**The ceiling, which is the part that expires.** **If Jobvite ever exposes per-user or multi-tenant
scoping, or a deployment is ever configured with more than one company id, this disposal is void and
both clauses become live obligations**. The second limb is observable in `JOBVITE_COMPANY_ID` by anyone reading a deployment. **The first was observable by nobody as first written** - it named no document, no checklist row and no moment at which anyone looks - so `CREDENTIAL-CHECKLIST.md` row 0 now asks Jobvite about the permission model as well as about read-only keys, and that row is where this limb is settled - `get_candidate` would then need an authorization check
against the request principal before returning a record. Without that trigger written down, this
paragraph rots silently on the day the assumption changes, which is precisely how the conditional
dismissal of `backend/idempotency.md` went unnoticed (§13's freeze procedure).


**The outbound Jobvite credential is a separate question from inbound scopes, and it is the one the
narrowest-credential rule actually asks about (B21).** Everything above governs what a *caller* may
ask this server to do. None of it constrains what *this server* may do to Jobvite: the API key in
`JOBVITE_API_KEY` carries whatever rights Jobvite issued it, so a deployment running with
`JOBVITE_ENABLE_WRITES=false` still holds a credential that can create candidates. Our two write
gates stop *this server* from using that power; they do nothing about anyone who reads the
environment of the process.

**Operator requirement: where writes are disabled, the Jobvite key must be a read-only key.** This
is stated **today** in `docs/CREDENTIAL-CHECKLIST.md`, whose row 0 records the question to Jobvite
and its answer either way, and **the README must carry it in the deployment section when the
implementation produces one** (§10.1). The tense matters and an earlier revision got it wrong: it
asserted the README stated this while §10.1, most of a document away, deliberately withholds the README
because describing an unbuilt system is a false claim in the present tense. The checklist is the
document the first key request actually passes through, and before implementation it is the only
point at which this instruction can be acted on at all. It is
**an instruction to a human, not a control this server can enforce**, for two reasons that should
not be blurred together:

- The server cannot verify it. There is no Jobvite endpoint that reports a key's own permissions, so
  a read-only key and a write-capable key are indistinguishable to us until a write is attempted -
  and attempting one to find out is exactly the destructive probe §1.1 forbids.
- **Whether Jobvite issues read-only keys at all is unknown to us.** Keys come from a human at
  Customer Success and the permission model is undocumented in what we hold. `CREDENTIAL-CHECKLIST.md`
  carries this as a question to ask when the first key is requested. **If the answer is no, this
  requirement is unsatisfiable and the residual risk stands** - which is the honest outcome to
  record, and better than a checklist row that quietly goes unticked.

The threat-model row is therefore mitigated **as an operator instruction with a stated ceiling**,
not as an enforceable control. A reader who takes it as enforced would over-credit the deployment.

### 7.3 Configuration

`pydantic-settings` owns required-config validation. `fastmcp.json` **cannot** express a required
environment variable: with one unset the server starts normally and the tool receives the literal
string `${JOBVITE_API_KEY}`, surfacing later as a confusing Jobvite 401. A missing credential must
fail at boot, naming the variable. `server.json` declares variables for registry consumers;
pydantic-settings enforces them.

**Configuration is scoped to the tools actually enabled**, and the enable surface is defined here
rather than presupposed. `JOBVITE_TOOLS` is a comma-separated allow-list of tool names; unset means
all **read** tools and never the write.

**The two variables are ANDed, and the answer is stated in both directions** because the converse
alone is what an earlier revision gave:
- `create_candidate` is registered **only if** `JOBVITE_ENABLE_WRITES=true` **and** it is named in
  `JOBVITE_TOOLS`.
- So `JOBVITE_ENABLE_WRITES=true` with `JOBVITE_TOOLS` unset does **not** register it. Enabling
  writes is deliberately two steps, and the obvious single step is the one that does nothing.
- Naming it in `JOBVITE_TOOLS` without the flag does not register it either.

**An unrecognised name in `JOBVITE_TOOLS` is a startup failure**, not a silent skip, matching this
section's fail-fast posture. A typo that silently disables a tool is exactly the shape of the
`--strict-markers` problem §8 describes: a green start-up having done less than the operator asked.
§8 states that configuration and carries a required case asserting it, so this is a cross-reference
that resolves; for one revision it named a control §8 did not contain.

Fail-fast validates what each *enabled* tool requires, never the union - a deployment using only
candidate search must not be forced to invent a `companyId` it has no use for:

| Tool | Requires |
|---|---|
| `search_candidates`, `get_candidate` | `JOBVITE_API_KEY`, `JOBVITE_API_SECRET` |
| `search_jobs` | `JOBVITE_API_KEY`, `JOBVITE_API_SECRET` |
| `get_job_feed` | `JOBVITE_FEED_KEY`, `JOBVITE_FEED_SECRET`, `JOBVITE_COMPANY_ID` |
| `create_candidate` | the v2 pair, plus `JOBVITE_ENABLE_WRITES=true` |
| *the `http` transport* | `JOBVITE_HTTP_TOKENS`, and `JOBVITE_TLS_TERMINATED_BY_PROXY=true` when the bind address is not loopback |

**The last row is keyed on the transport rather than on a tool**, which is why it is set apart. Every
other row answers "this tool is enabled, so these must be set"; the http row answers "this transport
is selected". §7.2 leans on this table for its claim that an unset `JOBVITE_HTTP_TOKENS` is a
startup failure, and until the row existed that cross-reference pointed at a table with no place to
put it - a tool-keyed table cannot express a transport-conditional requirement, and the sentence
resolved to nothing.

`server.json` declares every variable for registry consumers; pydantic-settings enforces only the
subset the enabled tools and the selected transport need.

### 7.4 Lifespan and shutdown

`from fastmcp.server.lifespan import lifespan` with `|` composition; startup in order, teardown in
strict reverse, verified.

**Lifespan teardown does not run under SIGTERM** - only SIGINT. Verified 3 of 3 with process
identity checks, and reproduced on the previous major, so it is longstanding rather than a 4.0
regression. Docker, Kubernetes and Cloud Run all stop containers with SIGTERM. Filed upstream as
[#4927](https://github.com/PrefectHQ/fastmcp/issues/4927).

**The obvious mitigation is actively dangerous and we do not use it.** An earlier draft proposed
`signal.signal(SIGTERM, signal.getsignal(SIGINT))`. Both doubts the review raised were correct, and
executing it found a third problem worse than either:

- **`getsignal(SIGINT)` returns whatever is installed at that moment.** A backgrounded process
  inherits `SIGINT = SIG_IGN`, so the one-liner installs **"ignore SIGTERM"** - the opposite of the
  intent. In a container that means the process does not stop on `docker stop` and is SIGKILLed
  after the grace period, **guaranteeing no teardown at all.** Its behaviour depends on ambient
  state that differs between a shell job, a foreground terminal, and PID 1.
- **Uvicorn does overwrite both handlers** during `run()`, confirmed from inside a live server. So
  the one-liner is a no-op while the server runs. Teardown happened anyway only because uvicorn's
  `capture_signals` *restores* the original handlers and *re-raises* the captured signal. **We
  would have been depending on a uvicorn implementation detail while believing we handled SIGTERM.**
- **On stdio there is no uvicorn at all**, and teardown runs but **the process does not die** - a
  non-daemon AnyIO worker thread blocks interpreter shutdown, so even an explicit `sys.exit(0)`
  never completes.

**The verified implementation** installs an explicit handler rather than copying SIGINT's, and
forces exit after teardown:

```python
def _install_shutdown_handler() -> None:
    # Do NOT use signal.getsignal(SIGINT): it returns whatever is installed at that
    # moment, which is SIG_IGN for a backgrounded process - installing "ignore SIGTERM".
    def _term(signum, frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, _term)

# in main():
status = 0
try:
    mcp.run(...)
except KeyboardInterrupt:
    logger.info("shutting down")
except BaseException:
    logger.exception("the server terminated abnormally")
    status = 70          # EX_SOFTWARE
    raise
finally:
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(status)   # a non-daemon AnyIO thread blocks sys.exit() on stdio
```

Teardown completes before `os._exit`, so skipping atexit handlers costs nothing we rely on.

**The status is the one the run earned, not a constant.** `finally` runs on every exit from the
`try`, not only on the `KeyboardInterrupt` path this section is about, so `os._exit(0)` would report
a bound port, a misconfiguration or an escaping cancellation as a clean stop, and every supervisor
that reads an exit status - Docker restart policies, Kubernetes `restartPolicy`, systemd
`Restart=on-failure` - would believe it. `os._exit` still runs unconditionally, so the stdio hang
below is still closed and nothing about the SIGTERM mitigation changes; only the constant moves.
The `raise` never reaches a caller, because the `finally` forces the exit first: it is there so the
traceback is not swallowed if the `finally` is ever removed, and the logging call is what actually
records the failure. **This must be tested by the side effect** - a case that forces `mcp.run` to
fail for a real reason and reads the process's exit status - not by asserting `70` against a
synthetic exception (ADR-0018).

**Two limits on the word "verified" here, stated because the mitigation this replaced was also
called verified and was not.** First, **the two halves were executed separately**: the explicit
handler was run on HTTP without `os._exit`, and `os._exit` was run on stdio. The composed snippet
above has never been run end to end on HTTP. Second, **PID 1 was never simulated.** Every arm used
`kill -TERM` on Linux; a container adds an init process and a grace period, and PID 1 changes
default signal dispositions - which is the exact ambient-state sensitivity that made the previous
one-liner install "ignore SIGTERM". The explicit handler should be immune, because unlike the
one-liner it never reads ambient state, but that is reasoning and not a measurement. The test below
closes both gaps on the first CI run, which is why it is a requirement rather than a suggestion.

**The test must assert both halves, on both transports:** that the teardown marker was written
**and** that the process exited within the grace period, signalling the interpreter PID resolved
via `/proc/<pid>/cmdline` rather than a wrapper. The HTTP path passes on teardown alone; **only
stdio catches the exit failure**, which is precisely why a single-transport test would have shipped
this bug.

**The rule that survives regardless of the mitigation, and it belongs at the lifespan definition
in `server.py` rather than in a review:** even when teardown runs, it runs *after* connections are
gone. **Nothing that must complete before connections close may live in a lifespan teardown.**
Today nothing depends on teardown - the only resource is a connection pool the OS reclaims - which
means the constraint is free now and will be violated by the first person who adds a metrics flush
or an audit-log write. §5.3's audit event makes that more likely, not less.

### 7.5 Human approval (MRTR)

Server-initiated elicitation is unavailable on the sessionless era by design. **The sanctioned
replacement is Multi Round-Trip Requests**: the tool returns an `InputRequiredResult` carrying an
`elicitation/create` request, and the client retries the original call with `inputResponses`
attached. Verified end to end on our default era: approve writes, deny refuses with the row count
unchanged, no client handler fails closed.

Implementation: the tool inspects `ctx.input_responses` - `None` on the first leg, populated on
the retry. Accessors are `ctx.input_responses` and `ctx.request_state` on `Context`, **not** on
`request_context`.

**The approval request must state what is actually being authorised, including the email.** This is
the one place the strongest gate can be satisfied honestly and still produce the outcome it exists
to prevent: an approver shown "create candidate Jane Doe" approves a database row, and thereby
authorises **an email to Jane Doe** that nobody mentioned. **The standard settles this rather than
leaving it to our judgement**: `ai/agent-guardrails.md:70-73` lists *"outbound message to a third
party"* among the destructive actions that must pause for approval, alongside deletes and financial
transactions (§2.2). The email is therefore not an incidental consequence of an approved write - it
is separately a gated action, so an approval that never mentioned it has not been obtained for it.
The elicitation payload accordingly names the candidate, the target job, and **whether `send_email`
is true**, in those terms.

`send_email` is also an argument like any other and is subject to §2.1's schema rules; it defaults
to `false` (§2.2) so the dangerous value is never the one reached by omission.

**The guard must check the action AND the value:**
`action == "accept" and content.get("approve") is True`. An *accepted* elicitation carrying
`approve: false` is still an acceptance. This conjunction is not optional and has its own test
with a deny arm and an accept-carrying-false arm.

**The two mechanisms are exactly complementary, and a single-mechanism guard is broken on one era
whichever it picks.** Executed on both:

| Era | MRTR | `ctx.elicit()` |
|---|---|---|
| sessionless `2026-07-28` | works, with a client handler | raises |
| handshake `2025-11-25` | **raises, every arm including approve** | works, with a client handler |

**Read "works" as `era AND handler`, not as an era property.** Availability has two axes and this
table shows one. On either era, a client that supplies no elicitation handler cannot approve: the
sessionless arm raises `MCPError: Elicitation not supported` and the handshake arm returns
`is_error=True`. Both fail closed, and §8 requires the test to assert the row count rather than the
error shape precisely because the two shapes differ. The era decides *which mechanism*; the client
decides *whether either can run at all*.

FastMCP's own error names the remedy: the multi-round-trip result type "only exists at MCP
2026-07-28 ... Use `ctx.elicit()` for server-initiated input on handshake-era connections."

**A tool cannot swallow the era guard, and this is structural rather than behavioural.** Returning
an `InputRequiredResult` merely constructs and returns an object; it does not raise. The era check
fires in **FastMCP's result-serialization layer, after the tool has already returned**, so the
exception is not raised in a scope the tool controls. A `try/except Exception` wrapped around the
tool's own approval request therefore cannot catch it and proceed to the write. This was established
by constructing the failure deliberately: a variant that swallows its own approval exception and
writes anyway was run on both eras with no client handler, and wrote nothing on all four arms.
That is a stronger property than a loud error a careless caller could still catch, and it is why
§2.2's gates do not need a fourth. **Its limit, stated so it is not over-trusted:** it protects the
*first* leg only. A tool that reaches its second leg and mis-validates the answer is on its own,
which is exactly what the `action == "accept" and value is True` conjunction above exists for.

**A default stdio install lands on the handshake era**, which is why a sessionless-only guard would
have shipped broken. **This one claim is documentation-sourced, not executed:** Claude Code's own
docs state that it negotiates `2026-07-28` for HTTP servers automatically but asks stdio servers
only when `MCP_PROTOCOL_NEGOTIATION` is set to `auto`. We have not driven Claude Code against this
server, and the survey it comes from is documentation research. **The guard does not rest on it** -
§20.2's execution shows MRTR raising on handshake regardless of who negotiates what, so both arms
are required either way. What the host survey supplies is the reason to care, not the reason to
branch.

**The discriminator is `ctx.request_context.protocol_version`**, compared against the same
`('2026-07-28',)` tuple FastMCP's own guard uses. Two plausible alternatives were measured and both
are traps: `ctx.transport` is **identical** on both eras (`'streamable-http'`), and `session_id` is
**populated on both** despite one era being called sessionless. `ctx._is_modern_protocol()` works
but is private.

**An unrecognised protocol version refuses the write.** The discriminator is correct for the two
eras that have been measured; a third case exists - `protocol_version` absent, or a future era
nobody has seen - and it must not degrade quietly. There is no weaker fallback to fall through to
now that the confirmation token is cut (§7.6), so the rule is explicit: **if the era cannot be
identified, `create_candidate` refuses and logs the refusal with the observed value.** An operator
learns that approval could not be established from a log line, not from a candidate's inbox.

**An earlier revision branched on whether `ctx.input_responses` exists. That branch was inert** -
`input_responses` and `request_state` are class-level properties, so `hasattr` is True on every era,
and `is not None` is already spent telling the first leg from the retry. It looked like handling,
which is why nobody looked further. The premise underneath it had never been measured on the
handshake era at all.

**What we may honestly claim.** A host can auto-respond to elicitation without showing anyone a
dialog. The MCP specification places human-in-the-loop confirmation on the host, not the server.
So the claim is *"the server requires an approval response from the host and refuses to write
without one"* - **never** *"a human approved this."*

**Liveness, for the README:** the write is safe on every refusal path including abandonment, with
`rows=0` independently confirmed. But an abandoned approval **hangs the call**, and a client-side
timeout does not bound it, because the elicitation handler runs in the client's own process. "The
write silently never completes" is a confusing failure mode and integrators are told about it.

### 7.6 Why there is no confirmation token

Cut, after being designed and spiked. It is recorded here rather than deleted silently because the
mechanism is the obvious thing to propose and the reasons against it are not obvious.

It worked: HMAC-bound to the payload, so a token minted for candidate A did not authorise writing
candidate B; forged, replayed, argument-mismatched and expired tokens each refused with distinct
messages. It was cut anyway because **it enforces confirmation, not human confirmation** - the same
blind spot as elicitation - so it was a second copy of a control we already had rather than an
additional one. Its costs were real: a caching footgun (a cached preview re-issues a spent token
and disables the write for the cache TTL, on a tool annotated `readOnlyHint=True`), an in-process
store that is per-connection on stdio and unshared across workers, and two extra tools on a server
whose value is being small.

**What survives is the audit half.** The approval request and response are recorded in the audit
event (§5.3), which was the token's only durable benefit, without a second tool pair.

### 7.7 Middleware

Adopted, each constructed with explicit arguments: `Timing`, `StructuredLogging` with
`include_payloads=False`, and `RateLimiting` with `get_client_id`.

**A fourth is adopted rather than disabled: `DereferenceRefs`** (ADR-0032). It is not constructed
here - `FastMCP.__init__` appends it whenever `dereference_schemas` is true, which is its default -
so it arrived framework-injected and ran unassessed by this section. Turning it off would buy
nothing measurable and would trade a real forward-compatibility property for cosmetic agreement with
a document that was simply incomplete: **fix the document, which was wrong, not the stack, which is
fine.** It rewrites published tool schemas by inlining `$ref`, and never request or response
payloads.

**`StructuredLogging` and `Timing`, plus §5.3's `audit.py`, make three log producers per invocation,
against a clause that says one**, and the deviation is now on the record rather than left as an arithmetic difference
between two sections. `request-middleware.md:145` reads *"4. **One log per request**: The
middleware emits exactly one structured log entry per request."* We keep three, because
`include_payloads=False` emits *no* arguments while B17 mandates **redacted** ones, so `audit.py`
is forced rather than chosen. **ADR-0011**, which also records what the deviation costs.

**`ResponseCachingMiddleware` is NOT adopted, and this reverses an earlier revision.** Three facts
from this design decide it: the cacheable responses are candidate PII (§2); §7.2's three scopes
exist precisely so different callers see different data; and §4.4 **measured** that this
framework's sibling middleware defaults every caller to the literal string `"global"` while its
docstring implies per-client. If the cache keys without client identity, a candidate-PII-scoped
result can be served to a public-job-data token, defeating §7.2 entirely through one middleware line.

**What `architecture/caching.md` contributes, at its actual strength**, because an earlier revision
cited it as a requirement and it is not one: the file contains no `MUST` anywhere. Its strongest
statement is `:841`, *"Cache user-specific data without proper namespacing"*, listed as a **Don't** -
which is the clause that bears on us, since a candidate record is user-specific data. `:628`'s
*Cache Key Namespacing* section shows the canonical shape, a tenant-scoped key built from the tenant
id, and `:833` advises namespacing *"when needed"*. So the standard supplies a prohibition, a
pattern, and an advisory tick. **The binding force here is ours, not the standard's:** §2's PII
classification and §7.2's three scopes are what make un-namespaced caching unacceptable in this
server, and `caching.md:841` agrees rather than compels.

We have not executed its key derivation, and the honest position is that we do not need to: **the
only benefit is latency against an upstream nobody has ever successfully called.** Dropping it
removes the scope-crossing risk and the spent-token hazard (§7.6) in one edit. If a cache is ever
wanted, its key derivation must be established by execution the way §4.4 established the limiter's,
and a test with two differently-scoped tokens must prove isolation before it ships.

Not used: `ResponseLimiting` (broken - the *client* raises on any tool with an output schema, at `mcp/client/session.py:1144-1145`, after the middleware truncates and drops the structured content it was validating; the middleware itself does not raise, and locating the raise there sends a reader to the wrong source. Filed as
[#4926](https://github.com/PrefectHQ/fastmcp/issues/4926)), `ErrorHandling` (its default converts
a caller's input problem into a raised server fault), `Retry` (§4.3), `Ping` (inert on our era).

**Standing rule, and it outlives the mechanism that produced it: never cache a tool that mints
one-time state.** A nonce, an idempotency key, an upload URL, a short-lived handle - a cached
response re-issues the *same* one, so the first use spends it and every subsequent caller receives
something already dead, for the whole TTL. **The trap is that such a tool is naturally annotated
`readOnlyHint=True`**, which is exactly the signal someone reaches for when deciding what is safe
to cache. **Derived, not measured** - and the distinction is kept because this rule is written to
outlive its mechanism, so a wrong provenance on it would become permanent. It composes two executed
results: caching demonstrably serves a stored response to a later identical call, and a spent
confirmation token was demonstrably refused on replay. Nobody ran a caching middleware in front of
the token preview before that mechanism was cut (§7.6). The composition is sound; the rule
is kept because the next tool of this shape will not announce itself.

**Design rule, earned rather than assumed: on this framework a middleware's default is not a safe
starting point.** Four of the eight exercised were unusable or needed their defaults overridden.
No middleware is adopted on the strength of its documentation, and each one's arguments are
justified here.

**Result size is bounded inside each tool**, not by middleware: a page is capped and the result
says `showing 50 of 1,240`. That is more useful to a model than a truncated JSON blob. The cap is
configuration, not a constant.

---

## 8. Testing

The default suite runs with no network and no credentials, and CI has **zero skips** - a skip
counts as a failure, so credential-dependent tests are excluded by *selection*, not marked
`skipif`.

**Selection means a marker, and a marker means `--strict-markers`, which is the configuration this
strategy rests on.** `backend/testing.md:67` puts `"--strict-markers"` in `addopts` and `:71-75`
declares the marker list; `:59` sets `asyncio_mode = "auto"` and `:82` sets `branch = true`. All
four are adopted verbatim, and the first is not housekeeping here. **Without it, a typo in the
exclusion marker's name selects nothing and the run goes green having tested less than it
claimed** - the live suite excluded by accident rather than by design, on a project whose entire
test strategy is "exclude the credentialed arm deliberately". `--strict-markers` turns that typo
into a collection error instead. §7.3's fail-fast posture on an unrecognised `JOBVITE_TOOLS` name is
the same rule applied to configuration, and it cites this paragraph.

`markers` declares the credential-dependent marker explicitly, so the name the exclusion selects on
and the name the tests carry are checked against one declared list rather than against each other.

**The live suite must be collected even though it is not run.** A suite that is excluded and never
collected rots silently: an import error or a renamed fixture in it is invisible until the day
someone finally has a credential. CI runs `--collect-only` against it and fails on a collection
error.

**Fixtures are in three tiers, and the split is load-bearing:**
- **Recorded** - byte-exact captures of real Jobvite error transport. Assert verbatim.
- **Structural** - the one genuine `200` (§1.1). Its body cannot ship, since it holds real
  candidate data, so we assert its *shape*: envelope keys, types, nesting, and whether a success
  body carries a `status` block. That last point already answers what was an open question.
- **Synthetic** - every other success body. Hypotheses in JSON.

**A suite passing only against synthetic fixtures proves the client is self-consistent, not that
it speaks Jobvite.** That sentence is in the test module's own docstring so nobody mistakes green
for verified. `docs/CREDENTIAL-CHECKLIST.md` converts each synthetic fixture to a recorded one
when a key lands; rows 1-4 are blocking.

Required cases, each failing if its defence is removed:
- the 200-with-401-body trap;
- **the log stream carries records for an invocation that produced them** - required by **C5-I1**
  (§4.1, §5.3), whose mitigation is redaction at one enforcement point and which is untestable
  against a stream nothing proves non-empty. The positive pairing for the case below, on the same
  construction the audit pair uses: an absence passes trivially against a server that emits no log
  record at all, so the two are paired and neither can be satisfied by silence;
- **a secret never reaching a log record, including the `jobFeed` URL** - asserted against the log
  stream the case above proves non-empty, not against silence (ADR-0013);
- **`.gitignore` covers the credential patterns and `.env.example` carries no real value** - asserted
  against the committed files, since the row this covers is about what reaches the repository rather
  than what reaches a log, and reusing the log-redaction case above would have been a test whose name
  did not match what it exercises;
- **the audit event is emitted and carries its mandated fields** - tool name, redacted arguments,
  result status, latency, `request_id`, the resolved client id on the HTTP transport and an
  explicit attribution-unavailable marker on stdio, and on the write `approval_state` together with
  the mechanism that produced it - `approval_mechanism`, present and one of `elicitation`,
  `mrtr`, `no_handler` (§5.3). **This case is positive on purpose.** The PII case below
  asserts an absence, and an absence passes trivially against a server that emits no audit event at
  all; the two are paired so that neither can be satisfied by silence;
- **candidate PII never reaching a log or audit record** - a distinct case from the secret test
  above, because §5.3 spends a paragraph distinguishing them and the threat model rates it
  Critical. Asserted against the audit event the case above proves exists, not against an empty
  stream;
- **EEO fields never appearing in any tool result**, asserted against the output models rather than
  by inspection, since §6.2 rates that Critical and an allow-list is only as good as its test;
- **an argument-schema violation failing closed**, which B12 and B23 require and which §5.1 claims
  is satisfied - the claim is only true once this test exists;
- **a control character or bidi override in a string argument rejected before dispatch**, with a
  positive control showing an ordinary name still passes. This is a distinct case from the schema
  test above, because the payload it catches is a valid short string that every `max_length` and
  regex check admits (B25, §2.1);
- **an argument payload exceeding a structural limit rejected** - one arm per limit: nesting past
  five levels, a list past 1,000 items, a dict past 100 keys, and a body past 1 MiB (B30, §2.1);
- **an off-loopback bind without TLS refuses to start** - no certificates configured here and
  `JOBVITE_TLS_TERMINATED_BY_PROXY` not declared, and the server exits naming the reason rather
  than warning and continuing (§7.1). Three High rows rest on this refusal and none of them rested
  on a test before;
- **the manifest pins `mcp` and the frozen resolve has no lock drift** - `mcp` present with an `==`
  pin in `pyproject.toml`, and the frozen resolve (`uv lock --check`, the same lock CI installs
  with `uv sync --frozen`) succeeding without amending `uv.lock` (§10). Credential-free and
  runnable in CI. The `fastmcp inspect` capability-drift diff is a CI gate rather than a case in
  this suite, and it is unexecuted (§10);
- **an undeclared pytest marker fails collection rather than selecting nothing** - the
  `--strict-markers` guarantee the exclusion strategy above rests on, asserted by invoking pytest
  against a file marked with a name absent from `markers` and requiring a non-zero exit. Its
  positive control is the declared marker still selecting its tests. **This case exists because
  §7.3 cites it**, and for one revision it cited a control §8 did not contain;
- **every retry and breaker-transition log line carries the invocation's own `request_id`, asserted
  under concurrency** - two invocations driven in parallel, each forced to retry, and each line
  matched to the invocation that produced it (B39, B40, §5.3). A single-call version of this test
  passes against a module global, which is the bug `request_id_var` exists to prevent, so the
  concurrent arm is the case and the single call is not sufficient. The same case asserts no URL
  appears in a retry line, since the `jobFeed` URL is itself a secret;
- **the read-only-key requirement is present in `CREDENTIAL-CHECKLIST.md`, and in the README's
  deployment section once a README exists** - asserted against the committed files, with the README
  arm **gated on the file's presence rather than skipped**, because a skip is a green that tested
  nothing (B21, §7.2). This tests that the
  instruction exists and is discoverable, which is **all that is testable** - the server cannot
  verify a key's permissions, and the row it covers is mitigated as an operator instruction rather
  than as a control. A test asserting anything stronger would misrepresent what the design achieves;
- **an expired advisory-ignore entry fails the audit gate** - an entry past its recorded expiry
  date is rejected rather than honoured, with a positive control showing an unexpired entry is
  honoured (B72, §10). This is the case that stops a time-boxed ignore becoming a permanent one,
  which is the only failure mode of the triage policy that arrives silently;
- **`request_id` is present on every result, success and error** - asserted on a successful read,
  a successful write, the audit-failure warning branch, and an error, each matched against the
  audit event's own id. The success arms assert it in `_meta` under the namespaced key and assert
  the structured content still validates against the output model, since an undeclared top-level
  key is rejected by the validator. **Each arm asserts the id on the WIRE result, not on the
  `ToolResult` the tool returned** - see §5.3's note on `_raw_mcp_result`: asserting the object
  would pass while the wire carried nothing (B42, §5.3);
- **trace context is recorded when the caller supplies it and absent when it does not** - two arms,
  one with a `traceparent` in the request `_meta` and one without. **Both arms are required**: a
  field that is always absent and a field that is always synthesised each pass a single-arm test,
  and the second is the failure that matters, because a minted id in a field named for the host's
  trace looks like a join and is not one (`ai/tool-calling.md:176-177`, §5.3);
- **lifespan teardown runs on SIGTERM, on both transports** - the process exits without the
  handler leaking the resource the lifespan opened, asserted by observing the teardown side effect
  rather than the exit code, since a process that dies uncleanly can still exit 0. **This case
  exists because §7.4 stated the requirement and nothing could fail if it were dropped**: it was
  not a §8 bullet. **Being one is not by itself enough, and this document twice claimed otherwise before the claim was measured.** The gate resolves §11 rows to §8 cases and not the reverse, so deleting this case leaves it at exit 0 - verified, against a control where deleting a case a row DOES name is caught. GATE-2 requires every case to cite a B-number or a section, which catches a case stripped to a bare unattributed line. **It does not check that the citation names an OWNER**, and this bullet is self-immunising: its own references to §8 and §11 - the retraction prose explaining the gate's limits - satisfy the check, so deleting §7.4 and §12 item 5 from here would still pass. Measured, not reasoned. **And it does not make deletion visible.** This is the third time this passage has overstated what protects it; the protection is that §7.4, §12 item 5 and this bullet reference each other, which is weaker than a §11 row and is now stated as weak rather than as a gate. Only a §11 row naming a case does that, and no threat row models a resource leak on shutdown - so this case's protection is that §7.4, §12 item 5 and this bullet all point at each other, and that is weaker than a row and is recorded as such. Three
  of this document's stated verification gaps close only on it (the upstream defect at
  `#4927`, the `os._exit` workaround, and the uvicorn implementation detail §12 item 5 records);
- untrusted-content fencing, including content that tries to close its own fence;
- an unknown non-string field being dropped rather than stringified;
- **`create_candidate` not retrying on timeout** - §2.2 and §4.3 both rest on the write being excluded from retry by construction, and B19 and B108's disposal are discharged by it. Without this case, the one property that makes the caller-replay ceiling honest is untested;
- approval: deny refuses, accept-carrying-false refuses, no-handler fails closed, and the second
  leg actually consumes `ctx.input_responses`;
- **a 4xx not tripping the circuit breaker** - §4.3 states it and `backend/resilience.md:166-168` (B37) requires it: a bad candidate id is the caller's error, not an outage, and a breaker that counts it takes the server down on a caller's typo;
- **the `eId`/`EId` casing asymmetry pinned**, so a later refactor cannot tidy it into a bug - §4.2 records the asymmetry as Jobvite's, not ours, and it is the kind of wart a well-meaning normalisation removes;
- **approval on BOTH eras**, because the no-handler arm surfaces differently on each: sessionless
  raises `MCPError`, handshake returns `is_error=True` with a masked message. A test asserting
  `pytest.raises(MCPError)` passes on one era and fails on the other. **The test asserts the
  invariant that matters - the row count did not change - not the error shape.**

Transport substitution uses `httpx2`'s built-in `MockTransport`. No third-party mocking library is
required, which matters because a credential-free test strategy cannot afford to depend on one.

Coverage: 80% floor overall, 85% tool modules, 90% the Jobvite client, **95% on `utils/` - the
standard's own Utilities target, kept rather than remapped** - and 95% line with 90% branch on
critical paths (auth, argument rejection, the error rule, approval, the write).

`utils/redaction.py` holds secret redaction and untrusted-content fencing, which are two of the
required cases above and both rated Critical in §11. An earlier remap left it at the floor while
giving the client 90%, which inverted the risk. See ADR-0010.

**A guard that refuses everything is not a guard, and its refusals prove nothing.** Every
refusal-path test is paired with a positive control showing the happy path still succeeds.

---

## 9. Known contract hazards

Jobvite's, not ours, each needing explicit handling:

1. **Casing asymmetry.** Reads return `eId`; the create response returns `EId`. Normalised at the
   boundary, pinned by a test.
2. **Date asymmetry.** Requests take `yyyy-MM-dd` strings; responses return epoch milliseconds.
3. **Three names for one concept.** v2 jobs key on `requisitions`, the v1 feed on `jobs`, the
   create response nests under `application`.
4. **Empty strings where nulls belong.** Phone fields use `""`. Treated identically at the
   boundary.
5. **No stable sort.** No sort parameter is documented, so a long paged scan over a mutating set
   may duplicate or skip. Bounded date windows are preferred to full-catalogue walks.
6. **Duplicate creates return `409`, and none of §2.2's gates prevent one.** Both gates stop
   an *unauthorised* write; none stops an *authorised* write being made twice - a model calling the
   tool again after a timeout, or a user approving twice. The `409` shape is `[INFERRED]` and never
   observed. So `create_candidate` surfaces a `409` as `/problems/conflict`
   with the duplicate named in `detail`, rather than as a generic failure, and never retries (§4.3). This is a real residual risk, not a
   solved one: we can report a duplicate, not prevent it.
7. **Route-level 404s.** `404 "Invalid URL Cannot find API."` means the route does not exist, not
   that a record was not found. The record-level not-found shape is unknown.

---

## 10. Repository and delivery

Canonical at `evolvconsulting/fast-mcp-jobvite`, mirrored to `Aztec03hub/fast-mcp-jobvite`.
Apache-2.0, `Copyright 2026 evolv Consulting`, with a NOTICE.

Python `>=3.12`. `fastmcp==4.0.3`, the GA line, targeting the sessionless `2026-07-28` spec as
deliberate early adopters: the pin was the beta `4.0.0b4` until ADR-0036 (2026-09-08), five days
after 4.0.0 shipped, and the spec target did not move. **`mcp` is pinned explicitly**, not just
`fastmcp`: the `ResponseLimiting`
regression arrived through the transitive SDK with zero change to the code that broke, which is
the characteristic failure mode of early adoption on a freshly major-bumped dependency.

Packaging, the pin core verbatim, because every line is load-bearing. The block was written as
three pins: the spike verified a two-pin recipe (`fastmcp` and `fastmcp-slim`, the beta and its
transitive prerelease, which `prerelease = "explicit"` refuses unless named), this block added
`mcp`, and the three-pin form was resolved on its own before being written here (`uv lock` exit 0,
72 packages, `pydantic` at a **stable** 2.13.4). **ADR-0036 removed the `fastmcp-slim` line when
the pin moved to the GA `4.0.3`**: a GA pin resolves its transitive unnamed, measured in five `uv
lock` arms with a positive and a negative control (the negative, the beta without its transitive,
still fails to resolve), and the lock moved exactly two packages, `fastmcp` and `fastmcp-slim`,
holding 121 packages either side with `mcp` 2.1.1, `mcp-types` 2.1.1, `httpx2` 2.12.0,
`starlette` 1.6.0, `pydantic` 2.13.5 and no `httpx`. Adding a hard `==` pin inside a
`prerelease = "explicit"` resolve is the change most likely to fail to resolve, which is why every
form of this block was run rather than assumed:

```toml
dependencies = [
  "fastmcp==4.0.3",          # the GA line; ADR-0036 moved it off the 4.0.0b4 beta
  "mcp==2.1.1",              # the transitive SDK that broke a middleware with no code change
]

[tool.uv]
prerelease = "explicit"
```

**A previous revision claimed in prose that `mcp` was pinned and then omitted it from this block**,
which was presented as verbatim. Anyone implementing that block exactly would have reproduced the
regression class the paragraph exists to prevent.

**The lockfile is the actual cure and it was missing.** This section argues that a transitive bump
broke code with zero change to that code, then pinned three packages by hand - which diagnoses the
disease and does not prescribe the remedy. `uv.lock` is committed, CI runs `uv sync --frozen`, and
the SBOM is generated from that frozen resolve. An SBOM produced from an unfrozen resolve documents
a build nobody shipped.

`prerelease = "explicit"` is kept at the GA pin (ADR-0036), and the reason changed with the pin.
Under the beta it was load-bearing in the other direction: `--prerelease=allow` is global in uv
and pulled in a beta pydantic, and `explicit` alone failed to resolve because `fastmcp-slim`
arrived transitively as a prerelease, so naming it directly was what resolved pydantic to stable.
At `4.0.3` nothing in the tree is a prerelease, the setting is inert, and it stays as the guard
that refuses a future transitive prerelease nobody named instead of accepting one silently.

**HTTP client is `httpx2`, the same one FastMCP ships: ADR-0007.** One HTTP stack in the image,
not two.

An earlier revision chose `httpx` on the belief that httpx2 was "a fork with a much smaller
ecosystem" whose mocking support was unproven. **That characterisation came from the runtime spike,
was repeated without checking, and was wrong in every part.** Checked against PyPI and the
repository, and recorded in **ADR-0007** - note that the spike still carries the original
characterisation, so it is the ADR and not `FASTMCP-SPIKE-4.md` that supports what follows:

- `httpx2` is authored by **Tom Christie, httpx's own author**, and published under the
  **pydantic** organisation. Its README states plainly that *"With HTTPX itself seeing limited
  activity recently, Pydantic is picking up stewardship under the HTTPX2 name so that users have a
  reliably maintained path forward - including timely security updates."*
- It is **the maintained continuation**, not a competitor. Releases through 2.12.0 in August 2026;
  `httpx` itself has shipped only `1.0.devN` prereleases.
- It ships `httpx2/_transports/mock.py`. **`MockTransport` is built in**, so the entire premise -
  that our credential-free test strategy would rest on unproven mocking - was false. We need no
  third-party mocking library at all.

Choosing `httpx` would have meant two HTTP stacks and two TLS surfaces in one image, a dependency
with limited activity in the critical path, and a silent hazard we would have invented ourselves:
`except httpx.HTTPError` can never catch a FastMCP-raised exception. Adopting httpx2 removes that
hazard rather than guarding it, so the module-confinement rule and its AST test in §8 are dropped
as unnecessary.

**No CI pipeline exists yet, and every "CI runs" sentence in this document is a specification of
what the pipeline must do, not a report of what it does.** `.github/workflows/` currently holds one
file, `mirror.yml`, which pushes to the mirror remote and nothing else. This is stated once, here,
because the present tense elsewhere would otherwise read as a claim about a pipeline that has never
run. **This covers every sentence in this document that describes CI in the present tense** -
*"CI runs"*, *"CI also runs"*, *"CI has"*, *"CI installs"*, *"CI exercises"* - and not only the one
phrasing. An earlier version of this paragraph named a single string form, which is a selector, and
the cheapest way to satisfy a selector is to leave every non-matching sentence alone - the same false-tense defect §7.2 already had to correct about the README, and it survived
seven review rounds and a machine gate in this section. **Standing the pipeline up is the first unit
of implementation, and until it exists these gates are run by hand.**

CI must run `python3 docs/reviews/check-coupling.py docs/DESIGN.md`, which enforces §11's internal
properties against §8 - row ids, STRIDE category coverage, ratings computed from likelihood and
impact, disposition legality, and the closing tables - together with a positive-control harness and
a subject-free mutation sweep (`check-coupling-sweep.py`) that both prove the checks can fail.

**Described rather than counted, deliberately.** An earlier version of this sentence said "six
properties" and "eight positive controls". Both numbers were wrong when written and went wronger as
the gate grew, which is the same stale-count defect the reviews kept finding elsewhere in this
document. A count is a claim that decays on every change; a description does not.

A checker that has only ever passed is the same failure as the sentence it replaced, which is why
the sweep can be pointed at a reverted gate and made to report holes.

CI must also run: lint, format, types, tests, plus `pip-audit`, CodeQL, TruffleHog with full history depth, SBOM
in both formats, and a `pip-licenses` allow-list gate. `fastmcp inspect` output is emitted and
**diffed between builds**, so capability drift arriving through a dependency bump is visible in
review rather than at runtime. **UNVERIFIED:** that this actually catches the drift it is meant to
catch is reasoning, not an executed result - the `ResponseLimiting` regression is the case it is
modelled on, and nobody has replayed that bump against this check.

**Advisory triage, because `pip-audit` fails on any advisory and we chose a beta stack (B72).**
`pip-audit` has no severity threshold: one advisory anywhere in the transitive tree turns a required
check red and blocks every merge, including merges that fix it. On a normal stack that is rare
enough to handle ad hoc. **We pinned `fastmcp==4.0.0b4`, a transitive prerelease, and `mcp==2.1.1`
deliberately, so we should expect this and owe it a sanctioned response** - because the unsanctioned
one is a blanket ignore, which is precisely the silent suppression the clause forbids, and which
nobody removes once added.

The policy, in the order it must be applied:

1. **Determine reachability first.** Does our code reach the vulnerable path? An advisory in a
   transitive package we never call is a different object from one in our request path, and the
   distinction must be recorded, not assumed. The SBOM identifies the dependent; reachability is a
   human judgement written down, not a tool output.
2. **If reachable: fix or stop.** Bump, patch, or remove the dependency. If none is possible, the
   affected tool is disabled via `JOBVITE_TOOLS` and the README says so. There is no third option
   and no "accept and continue" for a reachable advisory in credential-handling code.
3. **If not reachable: a time-boxed, single-advisory ignore**, recorded in
   `pyproject.toml` with the advisory id, the date, the reason it is unreachable, and **an expiry
   date no more than 30 days out**. **`scripts/check_advisories.py` is the owner, and it is a
   required CI step:** it reads that table, emits the `--ignore-vuln` flags `pip-audit` actually
   takes - the tool has no expiry concept and no `pyproject.toml` ignore section of its own - and
   exits non-zero on any expired entry, so the ignore cannot outlive its justification by drifting.
   **The table is the single source for both the flags and the expiry.** Hand-maintaining the CLI
   flags beside the table would be the two-lists defect §2.1 and §10.1 design around elsewhere, and
   an earlier revision of this step said only *"CI fails on an expired entry"* - passive, naming no
   owner, which is the construction that hides a missing mechanism.
4. **Never a blanket ignore, and never a raised threshold.** Both convert a signal into silence for
   every future advisory, not just this one.

**What this policy costs, stated rather than hidden:** step 1 is human judgement on every advisory,
and this project has one maintainer. The 30-day expiry is what stops that judgement being made once
and inherited forever, and it is the part most likely to be felt as friction and quietly lengthened.

### 10.1 Documentation deliverables

`documentation/readme-standard.md` mandates fourteen README sections in a fixed order, and the
conformance sweep found eleven consecutive documentation obligations unaddressed. **The README is
not written yet, deliberately**: it would have to assert a Quickstart that reaches "a working
state", live CI badges, and a test command, for software that does not exist. A README describing
an unbuilt system is a false claim in the present tense, and this project has already been bitten
by a document asserting its own compliance.

What the design fixes instead is **what the README must contain when the implementation produces
it**, so the obligation is discharged by specification rather than by fabrication:

- **All fourteen sections, headings matching exactly**, because automated checks locate them by
  heading text.
- **The Configuration table lists every environment variable the component reads**, with secrets
  referenced by name only. A variable added later updates the table in the same PR.

  **`.env.example` is the single enumeration and the table is checked against it**, rather than
  both being maintained by hand. This is §2.1's argument about fencing paths applied to
  configuration: two hand-kept lists that must correspond is a defect waiting for the first change,
  and here there would be three, since §7.3's requirements table is a fourth statement of the same
  set. `.env.example` is the one that must be complete, because it is the file an operator copies.

  **An earlier revision enumerated the set in this bullet and said "the four credential
  variables". There are five** - `JOBVITE_API_KEY`, `JOBVITE_API_SECRET`, `JOBVITE_FEED_KEY`,
  `JOBVITE_FEED_SECRET`, `JOBVITE_COMPANY_ID` - as §7.3's own table says and `.env.example` now
  shows. `JOBVITE_COMPANY_ID` is the job feed's separate credential, which §4.1 counts as a
  credential class of its own. `readme-standard.md:66` requires **every** variable, so a miscount
  in the sentence discharging the obligation produces precisely the incomplete table the clause
  forbids. Removing the hand-kept list is the fix; restating it correctly would only reset the
  clock.

  **The variables that had no name have one now** - `JOBVITE_MAX_RESULTS` and
  `JOBVITE_OUTBOUND_RATE_LIMIT` below, and `JOBVITE_MCP_HOST`, `JOBVITE_MCP_PORT` and
  `JOBVITE_HTTP_TOKENS` in §7.1 and §7.2. Leaving any of them unnamed made `.env.example` incomplete
  by construction and blocked the units that read them (B15). **The first two were found by a
  conformance sweep and the last three by someone trying to start the server**, which is why the
  thing that closes this is a sweep over the whole variable set rather than over the sentence being
  edited. An earlier version of this bullet said *"the two variables"* and went stale on the very
  next change - in the bullet whose subject is that a hand-kept list goes stale on the first change.

  - **`JOBVITE_MAX_RESULTS`**, default **50** - §7.7's in-tool result cap. 50 is not arbitrary: it
    is the number §4.5 and §11's C3-I1 already use in the caller-facing string `showing 50 of
    1,240`, and picking anything else would have made two parts of this document disagree about a
    figure a caller reads.
  - **`JOBVITE_OUTBOUND_RATE_LIMIT`**, requests per minute, default **6** - §4.4's self-throttle.
    Jobvite documents no numeric limit at all; its only stated envelope is prose, *call it on an
    as-needed basis, and anything more frequent than once a day must be filtered*. **6/min is
    therefore a conservative guess and not a vendor figure**, chosen to keep an interactive session
    usable while sitting far under any plausible limit, and it is recorded as a guess so nobody
    later cites it as documented. Checklist row 9 is what replaces it with an observation.
  - **`JOBVITE_OUTBOUND_BUDGET_SECONDS`**, seconds - §4.3's total outbound budget, the deadline the
    transport does not supply (ADR-0027). §4.3 requires that budget to be **configured**, and naming
    it here is what makes that requirement true; until it was named, a section of this document
    demanded a variable no other section admitted existed. Like the throttle above, its default is a
    choice made with nothing observed about Jobvite's latency to support it, and it is recorded as
    such rather than as a measured figure.

  These are now in `.env.example`, which closes B15's blocking half. What remains open is whether
  their defaults are *right*, which no amount of specification settles and only a live tenant can.
- **An `mcp-name:` string, added before the first PyPI upload and not after.** PyPI ownership
  verification for the MCP registry reads it out of the README, which becomes the package
  description, so retrofitting it costs a version bump. Cheap now, annoying later, and free if we
  never register.

**Six behaviours must be documented because each one produces a confusing support conversation
otherwise**, and every one was discovered by execution rather than anticipated:

1. **An under-scoped client gets "Unknown tool", not a permission error.** `require_scopes` removes
   the tool from `tools/list` entirely. Good behaviour, opaque symptom.
2. **The write tool requires a host that can elicit.** With the confirmation token cut (§7.6),
   there is no fallback: on a host that can elicit on neither era, `create_candidate` refuses.
   Correct, and surprising if undocumented.
3. **An abandoned approval hangs the call**, and a client-side timeout does not bound it, because
   the handler runs in the client's own process. The write stays safe; the call does not return.
4. **A reverse proxy must pass `mcp-method`, `mcp-name` and `MCP-Protocol-Version` through
   untouched.** A proxy stripping unknown headers breaks the server in a way that looks like our
   bug.
5. **Jobvite's documented operating envelope** - as-needed, and filtered beyond once a day - with
   the note that anything more frequent is outside what the vendor documents.
6. **The write path has never been executed against live Jobvite.** That caveat is removed only
   when `CREDENTIAL-CHECKLIST.md` rows 1-4 close, and not before.

**One standard behaviour is deferred rather than unmeetable, and an earlier draft got this wrong
in both directions.** It claimed Quickstart-CI parity was impossible and proposed a README that
marks the final step as requiring a credential. Both halves were wrong:

- `readme-standard.md:67` requires the Quickstart commands to be exercised by CI on every merge.
  **That is meetable**, by the credential-free path the same paragraph already described - install,
  start the server, list tools. The obligation was excused on a misreading, not a constraint.
- `readme-standard.md:83` lists *"Quickstart steps that require credentials, VPN access, or
  undocumented prerequisites"* under Anti-patterns. **The standard forbids the exact remedy the
  draft proposed.**

**So the Quickstart is credential-free in full, and CI exercises all of it.** Anything needing a
Jobvite credential belongs in Configuration and Usage, which is where the standard expects it. That
satisfies both clauses and is a better README.

**A CI status badge still cannot be live until CI exists**, since `:70` forbids a static badge that
does not reflect reality. That one is genuinely deferred until the implementation lands, not
excused.

**Two commit-time gates, both exceeding the standard deliberately:**
- Secret scanning pre-commit, not only in CI. On a public remote a pushed secret is compromised
  the instant it lands.
- **A committed-file-type gate.** A CONFIDENTIAL PDF has no high-entropy token and matches no
  credential regex, so it passes every secret scanner cleanly - the control we had named as
  preventing that incident could never have caught it. Allowlist-first, extension denylist,
  magic-number sniffing, NUL-byte backstop, fail-closed, overrides only via an allowlist entry in
  the same commit so the exception is reviewable in the diff.
  **Its limit, stated so it is not over-trusted:** it stops a *file* of the wrong type entering the
  repository. It does nothing about confidential prose pasted into Markdown, which is the incident
  we actually had. Review and `JOBVITE-API.md` §0.2 cover that.

---

## 11. Threat model

Required by `architecture/threat-modeling.md`, which is `applicable_to: all` and `priority:
required`. Four of the six triggers at `:120-127` fire: this handles PII, it changes authentication
and authorization, it exposes endpoints to external clients, and it is a third-party integration.
`:143` requires it authored **before implementation begins**, which is why it is here rather than
deferred.

**Four conventions, stated because the template leaves them open and the thresholds are meaningless
without them.**

1. **Every row carries a unique id**, `C<component>-<STRIDE letter><n>`. The number is always
   present, even where a component and category pair holds a single row, so adding a second row
   later never renames the first. Every closing table and every cross-reference addresses rows by
   that id and by nothing else. An earlier revision left six ids colliding - `C1-S`, `C4-D`,
   `C4-E`, `C6-I`, `C7-I` and `C8-E` each named two different rows - while the closing tables keyed
   on them and disambiguated by prose or not at all.
2. **The Risk column is INHERENT risk** - before the control named in the same row's Mitigation
   column. `:86` requires Critical and High to be mitigated before implementation proceeds. Read
   post-mitigation that rule could never fire, since a rated row already carries its mitigation.
   Read pre-mitigation it does real work: it names which threats may not be left to the
   implementer's judgement. Post-mitigation exposure lives in Residual Risks.
3. **Ratings are computed from the matrix at `:78-82`, not chosen.** Likelihood and Impact are
   judged against `:62-74`; the Risk cell is whatever the matrix yields. Machine-checked: every
   rated row agrees with it.
4. **Every component is evaluated against all six STRIDE categories**, per `:35`. Where a category
   carries no credible threat the row says so and gives the reason. A category is never dropped
   silently.

**The `Test` column is the coupling, and a script checks it rather than a reader.** Every row names
either the §8 case that fails if the mitigation is removed, or an explicit disposition:
`unmitigated`, `accepted`, `residual`, `no credible threat`, or `not required` for a row below the
Critical and High threshold. `docs/reviews/check-coupling.py` reads this section and §8 and fails
if a mitigated Critical or High row names no §8 case, if a named case is absent from §8's required
list, if two rows share an id, if a component is missing a STRIDE category, or if a closing table
names an id the analysis does not define.

**The universally quantified sentence that used to stand here is retired, deliberately.** It read
*"every mitigated Critical or High row below has a required test in §8"*. It was asserted three
times and was false all three times - most recently in the same edit that added a mitigated High
with no test at all, and it needed an escape clause that appeared 184 lines below the claim. A
claim about coverage is worth exactly the check that was run against it, so the claim is now a
column and the check is a script.

### Assets

| Asset | Sensitivity | Location |
|---|---|---|
| Candidate personal data (names, emails, phone numbers, résumés, cover letters, interview notes) | Restricted | Jobvite responses in transit; tool results; `models/`; **`create_candidate`'s input model in `tools/candidates.py`, which carries name, email and phone by construction**; logs if redaction fails |
| Special-category EEO data (`gender`, `race`, `veteranStatus`) | Restricted | Jobvite responses only. Excluded from every output model (§6.2), so never leaves the server |
| Jobvite v2 API credential (`x-jvi-api`, `x-jvi-sc`) | Restricted | Environment; `config.py` as `SecretStr`; request headers |
| Jobvite job-feed credential (`api`, `sc`, `companyId`) | Restricted | Environment; the `/v1/jobFeed` query string, which is why that URL is classified sensitive (§4.1) |
| MCP client bearer tokens | Restricted | Environment at startup; `StaticTokenVerifier` (§7.2) |
| The capability to create a candidate in a live ATS | Restricted | `create_candidate`. Side effect is an email to a live human and there is no sandbox (§2.2) |
| Public job data | Public | `search_jobs`, `get_job_feed` results |
| Server log stream | Confidential | Local log sink. Carries redacted arguments plus full tracebacks (§5.3) |
| Service availability | Internal | The process itself |

### Trust Boundaries

| Boundary | From | To | Controls |
|---|---|---|---|
| B1. Local process spawn (stdio) | Any OS process able to spawn the server | Server, full tool set | None at the server. The OS process boundary is the control, by design (§7.2). `create_candidate` here rests on the deploy-time flag plus approval, not scopes |
| B2. Network client (Streamable HTTP) | Remote or local MCP client | Server, scoped tool set | `StaticTokenVerifier` bearer token; `require_scopes` per data class; `allowed_hosts` / `allowed_origins` off-loopback; **TLS required off-loopback or the server refuses to start** (§7.1, §7.2) |
| B3. Server to Jobvite | Server | `api.jobvite.com` | `x-jvi-api` / `x-jvi-sc` headers, never in a URL; HTTPS with `httpx2` default verification, never disabled (§4.1, §7.1) |
| B4. Jobvite content to the model | Attacker-authored candidate free text | The calling model's context | Path-keyed allow-listed output models, fencing paths generated from those models, delimiter-token stripping (§6.1) |
| B5. Server to log sink | Server internals, including credentials and PII | Log stream and anything reading it | Single-point redaction in `utils/redaction.py` with a failing test; `include_payloads=False`; `mask_error_details=True` client-side only (§4.1, §5.3) |
| B6. Maintainer workstation to public remote | Local working tree, including credentials, vendor documents and client detail | Two public GitHub repositories | Pre-commit secret scanning **and** a committed-file-type gate (§10); `.gitignore`; review. **This is the only boundary on which an incident has actually occurred here** - a CONFIDENTIAL vendor PDF reached both public remotes and a history rewrite alone did not evict it |
| B7. Operator to configuration | Whoever sets environment variables | Server capability set, including whether writes exist and whether TLS is asserted | `pydantic-settings` fail-fast at boot; `JOBVITE_ENABLE_WRITES` and TLS enforcement both server-side (§7.1, §7.3, §2.2) |

### STRIDE Analysis

**C1. Transport and session** (`__main__.py`, `server.py`, `StaticTokenVerifier`, scopes)

| ID | Threat | L | I | Risk | Mitigation | Test |
|---|---|---|---|---|---|---|
| C1-S1 | Bearer token observed on a non-loopback bind and replayed | M | H | **High** | Off-loopback requires TLS or a declared terminating proxy; absence is a startup failure, not a warning (§7.1). Mitigated | §8: an off-loopback bind without TLS refuses to start |
| C1-S2 | Any local process able to spawn the server calls any tool over stdio | L | H | Medium | Accepted. The OS process boundary is the trust boundary (§7.2), stated rather than left implicit | accepted (B1) |
| C1-T1 | Request or response modified in flight on a plaintext non-loopback bind, for example flipping `send_email` to `true` | M | H | **High** | Same control as C1-S1 (§7.1). Mitigated | §8: an off-loopback bind without TLS refuses to start |
| C1-R1 | A write cannot be attributed to a caller: `audit.py` mints a `request_id` per invocation (§5.3) and caller identity must be recorded beside it, which `get_client_id` already derives for rate limiting (§4.4) | H | M | **High** | **Mitigated in §5.3**, and the remedy is qualified by transport rather than stated flat: the audit event records the resolved client id on the HTTP transport, and on stdio records that caller attribution is unavailable rather than emitting the literal `"global"`. An implementer who wires `get_client_id` on stdio, receives `"global"` and closes this row would leave the gap open behind a value that looks like an answer | §8: the audit event is emitted and carries its mandated fields |
| C1-I1 | Candidate PII readable in transit on a plaintext non-loopback bind | M | H | **High** | Same control as C1-S1 (§7.1). Mitigated | §8: an off-loopback bind without TLS refuses to start |
| C1-D1 | Connection or request flooding on the HTTP transport | M | M | Medium | `RateLimitingMiddleware` with a mandatory `get_client_id`, sized per session (§4.4) Mitigated. | not required (Medium) |
| C1-E1 | A token provisioned with the wrong scope set reaches candidate PII it should not | L | H | Medium | `require_scopes` on the three data classes (§7.2). Consider validating configured scope sets at startup Mitigated. | not required (Medium) |

**C2. Middleware stack** (§7.7: `Timing`, `StructuredLogging`, `RateLimiting`, `DereferenceRefs`)

| ID | Threat | L | I | Risk | Mitigation | Test |
|---|---|---|---|---|---|---|
| C2-S1 | No credible threat. No adopted middleware establishes identity | - | - | - | Identity is established at C1 | no credible threat |
| C2-T1 | No credible threat. No adopted middleware mutates request or response payloads | - | - | - | Payload shaping happens in the tools and in `models/`, which is C3 and C6 | no credible threat |
| C2-T2 | `DereferenceRefsMiddleware` rewrites published tool schemas, inlining `$ref` before they reach a caller (ADR-0032) | L | L | Low | It rewrites **schemas** and never request or response payloads, so it cannot carry caller data anywhere; it runs downstream of `RequestIdMiddleware`, so anything it emits is correlated; it has no configuration we set and no credential. Adopted rather than disabled (§7.7). A tripwire exists on the MODEL side - `tests/test_server.py`'s `test_no_input_model_produces_a_ref_for_the_middleware_to_inline` - and fires when a model starts nesting. Mitigated | not required (Low) |
| C2-R1 | `StructuredLoggingMiddleware` runs with `include_payloads=False` and so emits no arguments, leaving invocations unreconstructable | H | M | **High** | `audit.py` emits redacted arguments itself rather than assuming middleware provides them (§5.3). Mitigated | §8: the audit event is emitted and carries its mandated fields |
| C2-I1 | `include_payloads` flipped to `True`, sending raw candidate PII to the framework log | L | H | Medium | Constructed with explicit arguments; the value is stated in §7.7 and its rationale in §5.3. Mitigated by review, not by a control | not required (Medium) |
| C2-D1 | A configuration reload calls `limiters.clear()`, resetting every client's quota; repeated reloads are a trivial bypass (§4.4) | L | M | Low | Accepted. Requires operator access. Carried to Residual Risks | residual |
| C2-E1 | No credible threat. No adopted middleware grants capability | - | - | - | Capability is granted by registration (§7.3) and by scopes (§7.2), which is C8 and C1 | no credible threat |

*`ResponseCaching` is not adopted (§7.7), so the scope-crossing disclosure and the spent-token
hazard it carried are both out of the model rather than mitigated within it.*

**C3. Tool argument layer** (input models, `strict=True`)

| ID | Threat | L | I | Risk | Mitigation | Test |
|---|---|---|---|---|---|---|
| C3-S1 | No credible threat at this layer. Identity is established at C1 | - | - | - | The argument layer sees an already-authenticated caller | no credible threat |
| C3-T1 | Control characters or alternate encodings in a string argument pass unexamined into a Jobvite query (B25) | M | M | Medium | **Mitigated in §2.1:** strings are validated as UTF-8 and rejected before dispatch if they carry C0/C1 control characters other than tab, newline and carriage return, or Unicode bidi overrides. `max_length` and the output allow-list do not reach this - a NUL-bearing name is a well-formed short string, and the allow-list is an output filter | §8: a control character or bidi override in a string argument rejected before dispatch |
| C3-R1 | No credible threat beyond C1-R1. Arguments are recorded redacted by `audit.py` (§5.3) | - | - | - | Covered by C1-R1 | no credible threat |
| C3-I1 | An over-broad search argument returns more candidate records than the caller needs | M | M | Medium | Result cap enforced in-tool, reported as `showing 50 of 1,240` (§7.7). **The default is now named and shipped** - `JOBVITE_MAX_RESULTS=50` in `.env.example` (§12) - and what remains open is whether 50 is the right value, which only a live tenant settles (B15) | unmitigated (B15) |
| C3-D1 | A deeply nested or very large argument payload consumes parse time and memory (B30) | M | M | Medium | **Mitigated in §2.1:** the four limits from `input-validation.md:220-226` - nesting depth 5, list items 1,000, dict keys 100, body 1 MiB - enforced before dispatch. §4.5's page caps are outbound transport limits and bound nothing a caller sends | §8: an argument payload exceeding a structural limit rejected |
| C3-E1 | A schema violation reaches the tool body | L | H | Medium | `strict=True`, extra keys forbidden, validation before dispatch (§2.1). The rejection path's error shape is stated in §5.1 and the failure-closed case is required in §8, which is what closed B12. Mitigated | §8: an argument-schema violation failing closed |

**C4. Approval subsystem** (`approval.py`, MRTR elicitation on sessionless, `ctx.elicit()` on handshake)

| ID | Threat | L | I | Risk | Mitigation | Test |
|---|---|---|---|---|---|---|
| C4-S1 | A host auto-responds to the elicitation with no human present, so an approval represents no person | H | M | **High** | **Not mitigable server-side**, and no action item can discharge it. The MCP specification places human-in-the-loop on the host. §7.5 limits the claim to *"the server requires an approval response from the host"*. Carried to Residual Risks | residual |
| C4-T1 | An approval answer is tampered with or replayed to authorise a different write | L | H | Medium | The answer is bound to the invocation by the protocol rather than by a token we mint: the retry carries `inputResponses` for that request, and there is no long-lived artifact to replay. The confirmation token that would have needed a TTL was cut (§7.6) Mitigated. | not required (Medium) |
| C4-R1 | The approval decision is not among the audited fields, so there is no record that a gated write was authorised. `agent-guardrails.md:122` requires it (B17) | H | M | **High** | **Mitigated in §5.3:** the audit event includes `approval_state` and the mechanism that produced it. `agent-guardrails.md:79` separately requires recording *who* approved, which is unsatisfiable here and is scoped out by ADR-0009 for the approver only | §8: the audit event is emitted and carries its mandated fields |
| C4-I1 | **The approval request describes the candidate about to be written, so the audit stream holds candidate PII by construction** - the exposure the cut token would have carried moved here rather than disappearing (§5.3) | M | M | Medium | `approval_state` falls inside §4.1's single redaction point rather than beside it, and the audit stream carries the same handling class as the log stream Mitigated. | §8: candidate PII never reaching a log or audit record |
| C4-D1 | An abandoned approval hangs the call. A client-side timeout does not bound it because the handler runs in the client's process (§7.5) | M | M | Medium | No server-side bound is possible. Disclosed to integrators. Carried to Residual Risks | residual |
| C4-D2 | An authorised write is made twice - a model retrying after a timeout, or a human approving twice - creating a duplicate candidate and a second email to a live person | M | M | Medium | Never retried (§4.3); a `409` is surfaced as `/problems/conflict` with the duplicate named in `detail`. **The clause naming a remedy for this path (B108) is disposed of in §2.2: the remedy is an idempotency key, and nothing establishes that Jobvite accepts one, so the ceiling is stated rather than a control claimed. Detection, not prevention**, and the `409` shape is inferred rather than observed. Carried to Residual Risks | residual |
| C4-E1 | An accepted elicitation carrying `approve: false` treated as approval | M | H | **High** | The guard checks action **and** value: `action == "accept" and content.get("approve") is True`, with a deny arm and an accept-carrying-false arm in the required tests (§7.5, §8). Mitigated | §8: accept-carrying-false refuses |
| C4-E2 | Era misdetection downgrades or bypasses the control - `protocol_version` absent, or a future era value nobody has seen | L | H | Medium | The discriminator is measured rather than inferred (§7.5), which removed the inert-`hasattr` failure. **An unidentifiable era now refuses the write and logs the observed value**; with the token cut there is no weaker path to fall through to, so the failure mode is refusal rather than silent downgrade. Mitigated | §8: approval on BOTH eras |

**Note on C4 and duplicate writes.** §9 hazard 6 records that none of §2.2's gates prevents an
*authorised* write being made twice, and that hazard was absent from this table in an earlier
revision - a residual risk named in one section and unmodelled in the section whose job is
modelling residual risk. It is C4-D2 above, and it is in Residual Risks below. An earlier revision
asserted that placement in the same edit that failed to make it.

**C5. Jobvite client** (`services/jobvite_client.py`)

| ID | Threat | L | I | Risk | Mitigation | Test |
|---|---|---|---|---|---|---|
| C5-S1 | A rejected credential returns `HTTP 200` with a `{"status":{"code":401}}` body and is read as success, reporting zero candidates for an unauthenticated caller (§4.2) | H | H | **Critical** | The invariant: successful only if the body carries no `status.code >= 400` **and** the HTTP status is below 400, both, every call. Mitigated | §8: the 200-with-401-body trap |
| C5-T1 | Response substituted or modified in transit to Jobvite | L | H | Medium | HTTPS with `httpx2` default verification, never disabled (§7.1). Mitigated | not required (Medium) |
| C5-R1 | Retries and circuit-breaker transitions are not logged, so upstream behaviour cannot be reconstructed. `backend/resilience.md:224-226` requires both, each carrying the `request_id` correlation field (B39) | H | M | **High** | **Mitigated in §5.3.** `request_id_var`, a ContextVar set where the id is minted and reset in a `finally`, carries it to the retry and breaker hooks, which the resilience library calls with no argument we control. Every retry and transition is logged with it, and without the URL, since the v1 feed URL is itself a secret | §8: every retry and breaker-transition log line carries the invocation's own `request_id`, asserted under concurrency |
| C5-I1 | The `/v1/jobFeed` URL structurally carries `sc=` as a query parameter and could reach a log line or an exception message | M | H | **High** | Classified sensitive, never logged whole, `sc=` redacted at one enforcement point (§4.1). Mitigated | §8: a secret never reaching a log record, including the `jobFeed` URL |
| C5-D1 | Retry amplification against an already-degraded Jobvite | M | M | Medium | Retry budget bounded by a configured server-side outbound ceiling, jitter, one breaker per dependency, 4xx excluded from tripping it (§4.3). The ceiling is ours because MCP supplies no inbound deadline to derive one from, which §4.3 now states rather than implying otherwise. Mitigated | not required (Medium) |
| C5-E1 | The Jobvite credential is write-capable in a deployment where `JOBVITE_ENABLE_WRITES=false`, so the narrowest-credential rule is not met (B21) | M | H | **High** | **Mitigated in §7.2 as an operator instruction with a stated ceiling, not as an enforceable control.** Where writes are disabled a read-only key is required, stated today in `docs/CREDENTIAL-CHECKLIST.md` row 0, and required of the README's deployment section once a README exists (§7.2, §10.1). The server cannot verify a key's rights - no Jobvite endpoint reports them - and whether Jobvite issues read-only keys at all is unknown, so if the answer is no the residual stands and is recorded rather than ticked | §8: the read-only-key requirement is present in `CREDENTIAL-CHECKLIST.md`, and in the README's deployment section once a README exists |

**C6. Output pipeline** (`models/`, `utils/normalise.py`, fencing)

| ID | Threat | L | I | Risk | Mitigation | Test |
|---|---|---|---|---|---|---|
| C6-S1 | Candidate free text forges a channel break and impersonates system instructions to the calling model | H | H | **Critical** | Explicit fencing of every free-text field, fencing paths generated from the output models so the two cannot drift, delimiter tokens stripped so content cannot close its own fence (§6.1). Mitigated, with residual | §8: untrusted-content fencing, including content that tries to close its own fence |
| C6-T1 | An unknown non-string field is stringified, inventing a representation and colliding with `strict=True` output models | M | L | Low | Unknown non-string fields are dropped, not stringified (§6.1). Mitigated | §8: an unknown non-string field being dropped rather than stringified |
| C6-R1 | No credible threat. This component produces no auditable decision | - | - | - | It transforms a response that C5 already fetched and C1/C4 already authorised | no credible threat |
| C6-I1 | Special-category EEO fields (`gender`, `race`, `veteranStatus`) flow to the model | H | H | **Critical** | Not present in any output model, so they never leave the server (§6.2, ADR-0008). Mitigated | §8: EEO fields never appearing in any tool result |
| C6-I2 | A newly added Jobvite field leaks to the model without review | M | M | Medium | Path-keyed allow-list fails closed: an unlisted field is dropped until someone adds it deliberately (§2.1). Mitigated | not required (Medium) |
| C6-D1 | An unbounded Jobvite page returned to the model as a context and cost blowout | M | M | Medium | Result size bounded inside each tool, cap is configuration (§7.7). **The default is now named and shipped** - `JOBVITE_MAX_RESULTS=50` in `.env.example` (§12) - and what remains open is whether 50 is the right value, which only a live tenant settles (B15) | unmitigated (B15) |
| C6-E1 | No credible threat. This component grants no capability | - | - | - | It produces data, never a capability; the tool set is fixed at registration (§7.3) | no credible threat |

**C7. Audit and logging** (`audit.py`, `utils/redaction.py`, `loguru`)

| ID | Threat | L | I | Risk | Mitigation | Test |
|---|---|---|---|---|---|---|
| C7-S1 | No credible threat. This component establishes no identity | - | - | - | It records the identity C1 established | no credible threat |
| C7-T1 | A caller-supplied `X-Request-ID` carrying newlines forges log entries, or an over-long value bloats the log | M | M | Medium | Validated as a UUIDv4 before use and replaced if invalid (§5.3, B41). Mitigated | not required (Medium) |
| C7-R1 | No credible threat of its own. Repudiation of a tool call is C1-R1; repudiation of an approval is C4-R1 | - | - | - | Covered by C1-R1 and C4-R1 | no credible threat |
| C7-I1 | Candidate PII written to logs in the clear | H | H | **Critical** | `audit.py` emits redacted arguments deliberately rather than accepting `include_payloads=False`'s no-arguments default; single-point redaction (§4.1, §5.3, B88). Mitigated | §8: candidate PII never reaching a log or audit record |
| C7-I2 | Full tracebacks reach the server log. §5.3 says *"the log stream is treated as sensitive"*, which asserts a boundary without naming a control: no retention, access-control or destination is specified | M | M | Medium | State where the log goes, who can read it, and how long it is kept. Carried to Residual Risks | residual |
| C7-D1 | A hostile caller inflates log volume to exhaust disk | M | L | Low | Rate limiting bounds request volume (§4.4) Mitigated. | not required (Low) |
| C7-E1 | **No credible threat. Logging grants no capability** - `audit.py` and `utils/redaction.py` write records and return none of them to a caller, so there is nothing here to elevate into | - | - | - | Exposure of the log stream is C7-I1 and C7-I2, not elevation | no credible threat |

**C8. Configuration and secrets** (`config.py`, environment, repository)

| ID | Threat | L | I | Risk | Mitigation | Test |
|---|---|---|---|---|---|---|
| C8-S1 | No credible threat. Configuration establishes no identity | - | - | - | It supplies the material C1 authenticates with | no credible threat |
| C8-T1 | Environment or `.env` modified by a local actor to redirect credentials or enable writes | L | H | Medium | OS file permissions. Outside the server's control, stated for completeness | accepted |
| C8-R1 | No record of configuration changes, including `JOBVITE_ENABLE_WRITES` being flipped or TLS being declared as proxy-terminated | M | M | Medium | Log the enabled tool set, the write flag and the TLS posture once at startup. **Not currently specified** | unmitigated |
| C8-I1 | A real credential or a `.env` reaches the public repository. This repository has already had confidential material reach a public remote once | H | H | **Critical** | **Mitigated:** pre-commit secret scanning and a committed-file-type gate, both exceeding the standard (§10); `.gitignore` is committed and ignores `.env`, `*.key` and vendored source documents, and is named as a control on boundary B6. `.gitignore` now covers `*.pem` and `secrets/`, and `.env.example` is committed with every secret-class variable empty - `JOBVITE_API_KEY`, `JOBVITE_API_SECRET`, `JOBVITE_FEED_KEY`, `JOBVITE_FEED_SECRET`, `JOBVITE_COMPANY_ID`, `JOBVITE_HTTP_TOKENS` (B90, B91 closed) | §8: `.gitignore` covers the credential patterns and `.env.example` carries no real value |
| C8-D1 | A required variable is unset and the server starts anyway, surfacing later as a confusing Jobvite 401 | M | L | Low | `pydantic-settings` fails at boot naming the variable, scoped to the tools actually enabled (§7.3). Mitigated | not required (Low) |
| C8-E1 | `JOBVITE_ENABLE_WRITES` enabled unintentionally, exposing `create_candidate` | L | H | Medium | Enforced server-side, and the write still requires per-invocation approval, which the flag alone cannot satisfy (§2.2). Two orthogonal gates rather than three duplicate ones (§7.6). Mitigated in depth | not required (Medium) |
| C8-E2 | `JOBVITE_TLS_TERMINATED_BY_PROXY=true` asserted where no proxy terminates TLS, returning the deployment to plaintext with no warning | L | H | Medium | Accepted. The server cannot verify what sits in front of it, and the alternative (trusting `X-Forwarded-Proto`) is spoofable by anyone who can reach the port. An operator assertion is the correct shape. Carried to Residual Risks | residual |

**C9. Supply chain** (`pyproject.toml`, `uv.lock`, CI, the beta framework)

| ID | Threat | L | I | Risk | Mitigation | Test |
|---|---|---|---|---|---|---|
| C9-S1 | A dependency name is typo-squatted or a package is substituted at resolve time | L | H | Medium | Committed `uv.lock` with hashes; `uv sync --frozen`; every dependency named explicitly (§10) Mitigated. | not required (Medium) |
| C9-T1 | **A transitive dependency changes behaviour with no change to our code or to the code that breaks.** This is a realised threat here, not a hypothetical: an `mcp` major bump removed the behaviour a merged upstream fix depended on, and broke a middleware whose own source never changed (§10, §7.7) | H | M | **High** | `mcp` pinned explicitly, not only `fastmcp`; `uv.lock` committed and CI runs `uv sync --frozen` (§10). Mitigated by the pins and the frozen resolve. The third leg, `fastmcp inspect` output diffed between builds so capability drift appears in review, is **designed and unexecuted** (§10, which carries the `UNVERIFIED:` marker) and is carried to Residual Risks | §8: the manifest pins `mcp` and the frozen resolve has no lock drift |
| C9-R1 | A shipped artifact cannot be traced to the resolve that produced it | M | M | Medium | SBOM generated from the frozen resolve rather than a fresh one, in both CycloneDX and SPDX (§10) Mitigated. | not required (Medium) |
| C9-I1 | A dependency exfiltrates credentials or candidate data at runtime | L | H | Medium | `pip-audit` on every PR; licence allow-list gate; no dependency added without review. **Residual and unmitigable in general** - we run third-party code in the same process as the credentials. Carried to Residual Risks | residual |
| C9-D1 | A required CI gate goes red on a transitive advisory with no sanctioned response, blocking all merges | H | L | Medium | **Mitigated in §10.** A four-step triage policy: establish reachability first; if reachable, fix or disable the tool; if not, a single-advisory ignore carrying the id, the reason and an expiry no more than 30 days out; never a blanket ignore or a raised threshold. CI fails on an expired entry so the ignore cannot outlive its justification | §8: an expired advisory-ignore entry fails the audit gate |
| C9-E1 | A build-time dependency executes arbitrary code during install | L | H | Medium | `uv` with a frozen lock and hash verification; no `setup.py` execution in our own build (hatchling) Mitigated. | not required (Medium) |

### Threshold disposition

`threat-modeling.md:86-88`. Inherent Critical and High rows, and what each needs.

**The selection rule, stated because an earlier revision's was wrong.** A row lands in the
must-mitigate list when it is inherent Critical or High, unmitigated, **and a server-side remedy
exists that an action item can name**. A row that is inherent Critical or High, unmitigated, and
has **no available server-side remedy** cannot be discharged by an action item at all; it is
accepted with a documented rationale and carried to Residual Risks instead. **C4-S1 is the one such
row.** C5-E1 also sits in Residual Risks with no server-side remedy, and is **not** a counterexample:
the rule selects on *unmitigated*, and C5-E1 is mitigated - as an operator instruction with a stated
ceiling (§7.2), which is why its exposure is carried at High rather than reduced. That distinction
rests on one unrepeated adjective, so it is spelled out here rather than left to the reader. The earlier rule read simply "unmitigated, inherent Critical or High", which selects C4-S1
and then silently omitted it, so the rule did not describe the table it introduced.

**Must mitigate before implementation proceeds:**

| Row | Threat | Action | Ref |
|---|---|---|---|
| *(none)* | Both rows are closed by this revision: C5-R1 in §5.3, C5-E1 in §7.2 | - | B39, B40, B21 |

**This table is the count. No sentence in this section states a total for it.**

That rule exists because the total was stated in prose three times and was wrong all three times -
at *"Seven"*, then *"Three"* after C8-I1 came off, then *"Two"* after revision 5 emptied the table
entirely. Each correction was itself carried forward wrongly, and the third survived a review round
whose freeze condition is *"the must-mitigate table is empty"*: a reader checking that condition in
the section the rule points them at would have read **"Two"** above an empty table. A count in prose
beside the table it counts is a second source of truth that nothing keeps in step, and shown
arithmetic makes it worse, because it lends the authority of a calculation to a number nobody
rechecked.

**Removal ledger.** Whoever changes the table above adds a row here in the same edit.

| Came off | Rows | Why |
|---|---|---|
| TLS refusal specified (§7.1) | C1-S1, C1-T1, C1-I1 | An off-loopback bind without TLS now refuses to start |
| `ResponseCaching` dropped (§7.7) | the cache-disclosure row | Removed from the model entirely rather than mitigated |
| Already-performed remedies recognised | C1-R1, C4-R1 | Both were listed as blockers while §5.3 already stated the remedy |
| `.gitignore` and `.env.example` committed | C8-I1 | Mitigated with a §8 case (B90, B91) |
| Revision 5 (this one) | C5-R1, C5-E1 | §5.3's `request_id_var` and retry/breaker logging; §7.2's read-only-key requirement |

**The original total is not reconstructible, and no total should be derived from the ledger
either.** Two records exist and they disagree: the retired prose asserted **seven**, while the
ledger above names **nine** removed rows over a table that is now empty. Neither can be trusted over
the other - the prose did not reconcile with itself, naming four removals from *"seven"* and
concluding *"five"*, and the ledger was assembled after the fact from what the document still
recorded rather than from a contemporaneous count. **Do not derive a total by summing the ledger.**
It is a record of what came off, not evidence of what was there.

**C9-T1 was added to the model after the last count and never joined the list**, because its pins
and frozen resolve are specified in §10 and covered by a §8 case; the unexecuted part, the
capability-drift diff, is a residual risk rather than an implementation blocker.

**Mitigate before production release** (inherent Medium, unmitigated): C3-I1 and C6-D1 the
result cap whose default is shipped but unvalidated against a live tenant (B15), C7-I2 log-stream handling, and C8-R1 configuration-change logging.

**Three rows have LEFT that list and are not members of it:** C3-T1 (B25), C3-D1 (B30) and C9-D1
(B72). §2.1 specifies the control-character and encoding rejection and the four structural limits,
and §10 carries the advisory-triage policy, each with a §8 case. They are named separately because
an earlier revision joined them to the list above with *"and"*, so departed rows scanned as members
and the sentence appeared to name seven where the list holds four.

**Separately, and on the other list**, C5-R1 (B39, B40) and C5-E1 (B21) have left the must-mitigate
table above, which is what empties it: §5.3 supplies the `request_id_var` mechanism and the retry
and breaker logging, and §7.2 the read-only-key requirement. Those two are **High**, and were never
on this Medium list; an earlier revision named all three departures in one sentence, which read as a
single group and asserted a relationship that does not exist. **C5-E1 left it on weaker terms than the other two and the difference matters:** its
remedy is an instruction to an operator that this server cannot verify and that Jobvite may not
even be able to satisfy, so what closed is our obligation to state and test the requirement, not
the underlying exposure.

**Already mitigated at Critical or High**, listed so the mitigations are recognised as load-bearing
and not quietly removed later: C5-S1 the 200-with-401 trap, C6-S1 indirect prompt injection, C6-I1
EEO exclusion, C7-I1 PII in logs, C4-E1 accept-carrying-false, C5-I1 the jobFeed URL, C1-S1, C1-T1
and C1-I1 the TLS requirement, C2-R1 the audit event existing at all, C1-R1 caller attribution,
C4-R1 the approval decision, C9-T1 the pinned and frozen resolve, C8-I1 the credential and
`.env` exposure the repository has already suffered once, C5-R1 the correlated retry and
breaker logging, and C5-E1 the read-only-key requirement. **Each names its §8 case in
the `Test` column above, and `check-coupling.py` fails if any of them stops doing so.** This list
is derived from the table rather than maintained beside it; the script checks that it matches.

### Residual Risks

| Risk | Rating | Rationale for Acceptance |
|---|---|---|
| A host may auto-respond to elicitation with no human present, so an approval attests to a host response and not to a person (C4-S1) | High | Not mitigable by a tool provider. The MCP specification places human-in-the-loop on the host. §7.5 states the honest claim and never asserts human approval. The one control that operates without host cooperation is the deploy-time flag; the confirmation token an earlier revision named beside it was cut (§7.6) and is not defence in depth for anything |
| Fencing reduces but cannot eliminate indirect prompt injection from candidate free text (C6-S1) | Medium | Fencing plus delimiter stripping plus an allow-listed output model is the strongest available server-side control. The remaining exposure is the calling model's susceptibility, which is the host's boundary. Red-team cases are merge-gating (§6.1, §8) |
| An abandoned approval hangs the call with no server-side bound (C4-D1) | Medium | The elicitation handler runs in the client's process, so no server-side timeout reaches it. The write is safe on every refusal path including abandonment, with `rows=0` confirmed. Disclosed to integrators |
| An authorised write can be made twice, creating a duplicate candidate and a second email to a live person (C4-D2) | Medium | Detection, not prevention: the write is never retried (§4.3) and a `409` surfaces as `/problems/conflict` with the duplicate named in `detail`. The `409` shape is inferred rather than observed, so even the detection rests on a hypothesis until a credential exists **The remedy the standard names was evaluated and is unavailable to us**: `backend/resilience.md:146-151` permits a retried write only behind an idempotency key, and nothing establishes that Jobvite accepts one on this endpoint. §2.2 records that ceiling and the condition that expires it (B108). |
| `JOBVITE_TLS_TERMINATED_BY_PROXY=true` is an operator assertion the server cannot verify (C8-E2) | Medium | The server cannot see what terminates TLS in front of it. The alternative, trusting `X-Forwarded-Proto`, is spoofable by anyone who can reach the port and would be a worse control. An unverifiable assertion that fails loudly when absent beats a verifiable-looking one that lies |
| A configuration reload is a quota amnesty and repeated reloads bypass rate limiting (C2-D1) | Low | Requires operator access, already inside the trust boundary. Framework limitation: only `limiters.clear()` applies new values |
| The log stream carries redacted arguments and full tracebacks with no specified retention or access control (C7-I2) | Medium | Accepted only until C7-I2's action is taken. If the log destination is a developer's local disk this is minor; if it is shipped anywhere it is not, and nothing currently says which |
| The Jobvite credential is write-capable where writes are disabled (C5-E1) | High | **No server-side remedy exists.** No Jobvite endpoint reports a key's own permissions, so the server cannot verify the key it was given, and establishing it by attempting a write is the destructive probe §1.1 forbids. §7.2 requires a read-only key where writes are disabled, but that is an instruction to an operator: what it discharges is our obligation to state and test the requirement, not the exposure. **It is also unknown whether Jobvite issues read-only keys at all** - the permission model is undocumented in what we hold and `CREDENTIAL-CHECKLIST.md` carries it as a question for the day a key is first requested. If the answer is no, this exposure is undiminished by anything in this design. Rated at its inherent High rather than reduced, because no control here lowers it |
| We run third-party code in the same process as the Jobvite credential, on a deliberately beta stack (C9-I1) | Medium | Unmitigable in general by anyone who takes a dependency. `pip-audit`, the licence gate and the frozen resolve narrow the window; they do not close it. The rating rests on a Low likelihood judgement that a beta framework and a transitive prerelease make contestable, which is recorded rather than settled |
| The capability-drift diff is designed and has never been executed (C9-T1) | Medium | It is modelled on the `ResponseLimiting` regression and nobody has replayed that bump against it, so its ability to catch the thing it exists to catch is reasoning rather than a result. §10 carries the `UNVERIFIED:` marker at the point of use. The pins and the frozen resolve, which are executable and tested, carry C9-T1's mitigation on their own |
| `problem+json` is honoured nowhere on the default stdio transport (§5.2) | Low | ADR-0003. A media type carries no security property here; the seven RFC 9457 members are present in the payload regardless |
| No success response from Jobvite has ever been observed, so every success-path shape is a hypothesis (§1.1) | Medium | Accepted deliberately and structurally: fail loudly rather than degrade to a plausible empty result; synthetic fixtures are labelled as hypotheses in the test module's own docstring; `CREDENTIAL-CHECKLIST.md` converts them when a key lands |

---

## 12. Open questions

1. **A Jobvite credential.** Converts every synthetic fixture to a recorded one. Blocking for any
   claim that this is verified against Jobvite.
2. **The `start` base.** Still unresolved as a fact about Jobvite. Correctness no longer depends on
   it: paging is base-agnostic and every scan starts at `start=0` (§4.5). Checklist row 2 settles
   it the day a credential exists.
3. **The record-level not-found shape.** Unknown.
4. **Whether Claude Desktop supports elicitation.** No first-party statement found; secondary
   sources conflict and are not relied upon.
5. **Shutdown depends on a uvicorn implementation detail** (§7.4). Our handler works because
   uvicorn restores and re-raises; that is behaviour uvicorn does not guarantee. Recorded as a
   known dependency rather than left as an assumption, and the shutdown test would catch a
   regression.

6. **Whether a given host injects W3C trace context at all.** §5.3 records `trace_id` and
   `span_id` when the inbound `_meta` carries a `traceparent`. The SDK injects on the send path and
   FastMCP extracts server-side, but no host was surveyed, so how often the field is populated in
   practice is unknown - the same limitation §7.5 already records for elicitation support.

Items 1 to 4 and 6 are external unknowns about Jobvite or about a host. **Item 5 is not** - it is a
dependency on a uvicorn implementation detail, which is a claim about our own stack, recorded here
because it is the kind of assumption that goes unstated.

**What this list is not.** It is not an inventory of everything unexecuted in this design, and an
earlier revision closed with a sentence claiming it was - which is the blanket self-certification
this document's own front matter warns against. **Most of what is specified here has never been
run**, because none of it is built yet: the retry policy and the circuit breaker (§4.3), the
de-duplication seen-set and the completeness check (§4.5), the generated fencing paths (§2.1), the
redaction enforcement point (§4.1). Those are unbuilt implementation, not open questions, and §8
is where each acquires a test. Two items are different in kind, because they are reasoned claims
sitting inside sections whose neighbouring results *were* executed, and so borrow credibility
nobody granted them: the **capability-drift diff**, marked `UNVERIFIED:` at its point of use (§10)
and carried in §11's Residual Risks; and the **circuit breaker**, which appears in §4.3 beside a
measured retry finding and has no supporting execution anywhere. Neither is wrong. Neither is
evidenced.

**What is no longer an open question:** whether success bodies carry a `status` block. The one
genuine `200` answers it and §8's structural fixture asserts it (`JOBVITE-API.md:397`); an earlier
revision listed it here while two other sections answered it.

---

## 13. ADRs

**An ADR here does two different jobs, and conflating them was a real defect in this document.**

1. **Recording a deviation from a `priority: required` standard.** This is the job the
   **`Type: Deviation`** and **`Type: Both`** ADRs below do - NOT all of them, and the count
   is deliberately not written here - and it has **nothing to do with the freeze**. A deviation must be recorded the moment
   it is decided - `httpx2` instead of the mandated `httpx` is a deviation whether or not anything
   is frozen, and waiting for a freeze would just mean an unrecorded deviation in the meantime.
   That is why deviation ADRs exist against a document that is not frozen, which reads as a
   contradiction only because of the second job.
2. **Being the sole instrument that may change a frozen `DESIGN.md`.** This is a change-control
   policy local to this project, and it starts applying only at the freeze.

**These are separate and must stay distinguishable**, because after the freeze the question "is
ADR-0012 a standards deviation, a design change, or both?" has to have an answer - the freeze rule's
teeth depend on it. **Every ADR carries a `Type:` field**, `Deviation`,
`Design change`, or `Both`. The eleven below are all `Deviation`, recorded before any freeze, and
`docs/adr/README.md` states the same split so a reader arriving there is not misled by its title.

The eleven required at freeze:

- **ADR-0001** - target `fastmcp 4.0.0b4` and the sessionless spec rather than the stable line.
- **ADR-0002** - in-process rate limiting instead of the mandated Redis token bucket. **Scope
  includes** `rate-limiting.md:361-362` (a 429 must use a problem detail, and ours raises
  `MCPError`), rule 5's `RateLimit-*` response headers, and the limitation that every supporting
  measurement was sequential and single-client.
- **ADR-0003** - `problem+json` cannot be set on an MCP tool error; scope and consequences.
- **ADR-0004** - `ResponseLimitingMiddleware` excluded; size bounded in-tool.
- **ADR-0005** - the `ai/` standards domain binds this repository by intent.
- **ADR-0006** - single `main` branch rather than the mandated `main`+`develop`. **Scope includes**
  B97 branch *naming*, which the branch-model deviation does not touch, and the "merge only from
  develop or hotfix" clause the deviation necessarily voids. B99's four properties - PR, approval,
  CI green, currency, squash - **relocate onto `main`** rather than retiring.
- **ADR-0007** - `httpx2` rather than `httpx`, matching what FastMCP ships.
- **ADR-0008** - special-category EEO fields excluded from output models, **on scope grounds**:
  `gdpr-data-rights.md` is `priority: required` and its DSAR/RTBF machinery attaches to systems that
  store personal data, which this is not. Article 30 records-of-processing is separately satisfied
  by `docs/data-inventory.md`.
- **ADR-0009** - the audit log records that an approval response was received and what it said, but
  cannot record **who** approved, because a host may auto-respond with no human present.
  `agent-guardrails.md:79` requires that identity and it is unsatisfiable on this transport.
  **Scoped to the approver only.** The *caller's* identity is knowable - §4.4 already derives it for
  rate limiting - and is recorded. This ADR does not dispose of that, and must not be read as doing
  so.
- **ADR-0010** - coverage targets remapped from the standard's category model, which has no
  category matching an MCP tool module. Loosening a mandated coverage number is exactly what this
  mechanism exists to record.
- **ADR-0011** - three log producers per invocation against `request-middleware.md:145`'s *"exactly
  one structured log entry per request"*. `StructuredLoggingMiddleware` runs with
  `include_payloads=False` and so emits no arguments, while B17 mandates **redacted** ones, which
  forces `audit.py` as a third producer. **Scope includes** the cost: three records correlated by
  `request_id`, which §5.3 now propagates through `request_id_var` (B40 closed in this revision).
  The correlation the deviation depends on therefore exists; what remains is the deviation itself,
  three records where the clause asks for one.

**Freeze procedure, and one step exists because it already failed once:** every **conditional**
dismissal in the standards analysis is re-tested at freeze. `architecture/caching.md` was dismissed
as "optional here; if a cache is added it becomes live", a cache was then added, and nothing
re-evaluated it - the condition tripped silently and it took a second sweep to notice. **A
conditional dismissal is a dated claim about the design, not a permanent verdict.**
**Both named candidates have now been tested, and the results differ.**
`backend/idempotency.md` **did go live** - its dismissal rested in part on a circular leg, and it is
reopened as B108 and disposed of in §2.2. It is the **second** conditional dismissal to trip
unnoticed, after `architecture/caching.md`. `devops/docker.md` **was re-tested and its dismissal
stands**: there is no Dockerfile, no compose file and no image build in CI, and §10 ships a PyPI
package - the container references in §7.4 concern one an operator might run us in, not an image we
publish. **Tested-and-standing is a different object from untested, and this sentence previously
recorded neither.**

**The re-test is a numbered step of this procedure, not a reviewer's discretion.** Round 5 asked
round 6 to re-test these two by name and round 6 did not, which is how a procedure that has now
failed twice has never once caught its own quarry. Whoever performs the freeze runs the re-test and
records the outcome for each conditional dismissal, standing or tripped.

**And for each disposal elsewhere in this document that states a condition voiding it** - B107 in §7.2 and B108 in §2.2 today. *Conditional dismissal* is this section's term of art for an entry in the standards register, and both of those disposals live outside it: B107's own argument is that an untriggered paragraph *"rots silently... which is precisely how the conditional dismissal of `backend/idempotency.md` went unnoticed"*, and it was then written outside the sweep that would have caught it. **A procedure that has already failed twice would not have caught these a third time.**
