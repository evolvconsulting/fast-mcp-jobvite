# Architecture Decision Records

An ADR here does **two different jobs**, and they must stay distinguishable:

1. **`Deviation`** - records a decision that departs from a `priority: required` standard, or that a
   reviewer would otherwise be right to file as a defect. **This is independent of the freeze.** A
   deviation is recorded when it is decided; that is why the ADRs exist against a design that is
   not yet frozen, which is correct rather than contradictory.
2. **`Design change`** - after the freeze, an ADR is the only instrument that may change
   `docs/DESIGN.md`. This job begins at the freeze and not before.

**Every ADR carries a `Type:` field** - `Deviation`, `Design change`, or `Both` - because after the
freeze "is this a deviation or a design change?" must have an answer, and the freeze rule's teeth
depend on telling them apart. `DESIGN.md` §13 states the same split.

The convention began at 0012, and **0001 to 0011 were backfilled** as `Deviation` - which is what
this paragraph had already asserted collectively, and each file now says for itself. Round 2 of the
code review found the gap: the two ADRs in its scope, 0010 and 0011, are deviations that sat in the
unlabelled half, and **once a convention exists, the ABSENCE of the field reads as "not a
deviation"** rather than as "written before the field did". A classification that lives only in the
index is not carried by the artifact a reader opens.

Format: Status, Type, Context, Decision, Consequences. Every ADR cites the clause it deviates from
at its `file:line`, and says what evidence the decision rests on.

## The index: every decision, one line, without opening a file

**This is what this section is for.** An ADR is an immutable decision record and there are a lot of
them, so the cost of the set is not the count - it is having to open every file to learn what was
decided. Each row below states the DECISION, not the topic. Where a decision is qualified, partial,
or explicitly leaves something open, the row says so rather than reading clean.

The number of ADRs is not written here as a literal, for the reason ADR-0034 gives. Derive it:

    ls docs/adr/0*.md | wc -l                  # the numbered ADRs
    python3 docs/reviews/check-adr-numbers.py  # unique, contiguous, and all of them listed below

That checker refuses this table in BOTH directions - a file with no row, and a row with no file -
so it cannot silently stop short the way it once stopped at 0023 with twelve ADRs missing.

**`Status` is read from each file's own `Status:` line, not assumed.** Every line but one begins
with the word `Accepted` - `0029`'s reads *Accepted in part*. `0036` landed as the first `Proposed`
ADR here, the instrument by which Tier 0 changes the frozen design, written by a sub-orchestrator
that measured the change and did not decide it; it was Accepted the same day by JACK as Tier 0
under Phil's directive with KING's concurrence, and its status line says on its face who decided
and on what authority, which a change to a Phil-accepted ADR must. Nothing here is Superseded or
Rejected. Several lines carry a qualifier after the status word and it is load-bearing in each. The
rest of each line is an attribution, not a qualification. **This paragraph named a count and four ADR
numbers until 0036 landed and made both wrong** - the count is gone rather than corrected, for the
reason ADR-0034 gives. Re-derive rather than trusting this paragraph:

    grep -H '^\*\*Status:\*\*' docs/adr/0*.md
    grep -H '^\*\*Type:\*\*'   docs/adr/0*.md

**SUPERSESSION: no ADR here supersedes or is superseded by another.** That is a statement about a
form, not a claim that nothing was ever revised - FOUR ADRs AMEND an earlier one's decision while
leaving it standing as the record of what was decided when. Those edges are on both rows:

- **0028 amends 0021.** 0021 defined `approval_mechanism` as a closed set of `elicitation`,
  `sampling`, `no_handler`; 0028 renames `sampling` to `mrtr`. A reader acting on 0021's spelling
  emits a value the design no longer names.
- **0033 completes 0021.** 0021 deliberately left `approval_state`'s own vocabulary alone, and
  0028 says in terms that it does not fold that in either; 0033 settles it.
- **0035 widens 0034's selector.** 0034 replaced a stale count with the selector `Type: Deviation`;
  0035 makes it `Type: Deviation` **and** `Type: Both`. 0035 states outright that it does NOT
  revisit 0034's ruling, which stands.
- **0036 amends 0001's pin.** 0001 pinned `fastmcp==4.0.0b4` as deliberate early adopters; 0036
  moves it to the GA `4.0.3` now that the line has shipped, and drops the `fastmcp-slim` pin that
  only a prerelease needed. 0001's spec target and its explicit `mcp` pin both stand, so a reader
  acting on 0001 alone gets the right spec and the wrong version.

`0007`'s *"reversing an earlier decision"* reverses an earlier **revision of the design**, not an
ADR. There is no ADR it supersedes.

| ADR | Type | Status | The decision |
|---|---|---|---|
| [0001](0001-target-fastmcp-4-beta.md) | Deviation | Accepted - **its version pin is amended by 0036** | Pin `fastmcp==4.0.0b4` and target the sessionless `2026-07-28` spec, not the stable line. The spec target and the explicit `mcp` pin stand; the version moved to the GA `4.0.3` once the line shipped. |
| [0002](0002-in-process-rate-limiting.md) | Deviation | Accepted | Use FastMCP's own `RateLimitingMiddleware`, in process, instead of the mandated Redis token bucket. |
| [0003](0003-problem-json-on-mcp-transport.md) | Deviation | Accepted | Carry the complete RFC 9457 problem object as the tool result's structured content and set no media type; `problem+json` is applied properly only where a real HTTP surface exists. |
| [0004](0004-exclude-response-limiting-middleware.md) | Deviation | Accepted | Do not adopt `ResponseLimitingMiddleware`; each tool bounds its own response size, capping the page and reporting `showing 50 of 1,240`. |
| [0005](0005-ai-domain-binds-by-intent.md) | Deviation | Accepted | The `ai/` standards domain BINDS this repository, though its literal scope - code that CALLS models - does not reach a server that models call. Obligations B9-B26 apply in full. |
| [0006](0006-single-main-branch.md) | Deviation | Accepted | A single `main` branch, not the mandated `main`+`develop`. |
| [0007](0007-httpx2-not-httpx.md) | Deviation | Accepted, reversing an earlier design revision (NOT an ADR) | Write the Jobvite client against `httpx2`, the client FastMCP actually installs, rather than `httpx`. |
| [0008](0008-eeo-fields-excluded.md) | Deviation | Accepted | Special-category EEO fields appear in no output model, so they never leave the server. |
| [0009](0009-approver-identity-unknowable.md) | Deviation | Accepted | Record that an approval response was received and what it said; do not claim to record WHO approved. Caller identity is knowable, approver identity is not. |
| [0010](0010-coverage-targets-remapped.md) | Deviation | Accepted | Remap the standard's category model onto this repository: tool modules 85%, the Jobvite client 90%, critical paths 95% line and 90% branch, against its 80% floor. |
| [0011](0011-three-log-producers-not-one.md) | Deviation | Accepted | Keep all three per-invocation log producers - `TimingMiddleware`, `StructuredLoggingMiddleware`, `audit.py` - and deviate from `request-middleware.md:145`'s one-log-per-request rule deliberately. |
| [0012](0012-shared-inbound-constraints-module.md) | Design change | Accepted | Add `utils/constraints.py` to §3 as the single module every input model imports its inbound constraints from. No input model defines its own. |
| [0013](0013-secret-absence-case-needs-a-pairing.md) | Design change | Accepted | §8's secret-absence case gains a positive pairing asserting the log stream carries records for an invocation that produced them, so the absence is measured against a stream proved non-empty rather than against silence - the construction §8's audit cases already use. |
| [0014](0014-c8-i1-empty-values-is-wrong.md) | Design change | Accepted | Amend C8-I1's evidence clause to `.env.example` carrying every SECRET-CLASS variable empty (six named). SEVEN of the fifteen variables carry a value, so the clause as written describes evidence that does not exist. No rating and no disposition changes; only the sentence does. |
| [0015](0015-licence-gate-is-a-deny-list.md) | Deviation | Accepted | The licence gate ships as a DENY-list over the flag-list - strong copyleft and non-OSI terms fail - not as an allow-list. Four packages sit on NEITHER list. Its negative arm is verified, so the pass is not vacuous. |
| [0016](0016-setup-uv-v5-not-the-standards-v4.md) | Deviation | Accepted | Stay on `astral-sh/setup-uv@v5` where the standard pins `@v4`. |
| [0017](0017-unmapped-errors-are-internal-error-not-about-blank.md) | Design change | Accepted | The unmapped-error registry row becomes `/problems/internal-error`, 500. `about:blank` is retained only for its real scope - an unmapped HTTP status received FROM Jobvite. |
| [0018](0018-forced-exit-masks-a-crash-as-a-clean-stop.md) | Design change | Accepted | Keep `os._exit`, but give it the status the run actually earned - 70 (`EX_SOFTWARE`) on an abnormal termination - so a crash is not reported as a clean stop. Only the constant moves; the stdio-hang workaround is unchanged. |
| [0019](0019-design-603-cites-a-section-that-does-not-exist.md) | Design change | Accepted | `DESIGN.md:603`'s `(§5.4)` becomes `(§4.1)`, there being no §5.4. Nothing else changes - no behaviour, no threat row, no verification case. |
| [0020](0020-the-30-day-advisory-budget-runs-from-the-recorded-date.md) | Deviation | Accepted | The 30-day advisory-ignore budget is measured from the entry's recorded `date`, not from now; pinned by a named test with both the 30-day and 31-day boundary controls firing. |
| [0021](0021-approval-mechanism-is-required-by-two-rows-and-defined-nowhere.md) | Design change | Accepted - **its vocabulary is amended by 0028** | Define `approval_mechanism` in §5.3 as a CLOSED set (`elicitation`, `sampling`, `no_handler`) recorded on the audit event, repoint the two rows that require it, and add the matching §8 arm. Deliberately does NOT settle `approval_state`'s own vocabulary - that is 0033. |
| [0022](0022-no-cookie-jar-is-a-disable-not-an-omission.md) | Design change | Accepted | Restate the contract as an ACTION - clear the cookie jar after every request, in a `finally` - because `httpx2`'s default is to persist and resend. Held by a test plus a positive control asserting the bare client really does carry cookies. |
| [0023](0023-harnesses-drop-e-from-strict-mode.md) | Deviation | **Accepted** (orchestrator, 2026-08-29) | `scripts/*.sh` keep `set -uo pipefail` and drop ONLY `-e`, scoped BY PURPOSE - anything here whose measurement is the exit code of a command expected to fail, INCLUDING the `ci.yml` `run:` blocks that call them - and never as a general licence to omit `-e`. `-e` would destroy the measurement and strand mutations in the tree. |
| [0024](0024-paging-is-bounded-by-the-servers-honesty-and-nothing-else.md) | Design change | Accepted | An exhaustive scan gets BOTH a zero-progress break and a ceiling not derived from `total`, neither a substitute for the other - and the ruling puts that ceiling in RECORDS, not pages, because a page ceiling is a different record count at each page size. **Still latent: `scan()` has no caller, and an existing 513-line implementation is explicitly NOT adopted by the ruling.** |
| [0025](0025-page-size-budget-and-throttle-are-one-decision.md) | Design change | Accepted - **Q2 and Q3 answered and applied; Q1 WITHDRAWN** | The page size, the outbound budget and the self-throttle are ONE decision, because any one chosen alone falsifies the arithmetic of the other two. The self-throttle is PER-PROCESS (Jobvite sees our process, not our scans), and the outbound budget bounds wall-clock INCLUDING throttle waiting. Q1 - what page size an exhaustive scan uses - is WITHDRAWN, not deferred: it rested on a reading of §4.5 that the design refutes. **None of the three constants is settled and the throttle is unimplemented.** |
| [0026](0026-log-redaction-is-a-property-of-the-entry-point-not-the-client.md) | Design change | Accepted - option (1), plus a constraint the ADR never stated | `JobviteClient` installs the `httpx2` log-redaction filter itself, with an opt-out CONSTRUCTOR keyword defaulting to installing and never a `Settings` field - and the install MUST be idempotent, because a client is built once per invocation and a stacking filter is a slow leak inside the leak fix. |
| [0027](0027-the-budget-must-be-configured-and-the-variable-set-is-closed.md) | Design change | Accepted | `JOBVITE_OUTBOUND_BUDGET_SECONDS` joins §10.1's closed variable list, and three things land TOGETHER: the design's list, the four artefacts the closed-set tests hold equal, and ALL THREE client factories. The retyped `== 15` count is derived rather than typed. |
| [0028](0028-approval-mechanism-names-a-path-this-design-does-not-use.md) | Design change | Accepted - **amends 0021** | Rename the sessionless `approval_mechanism` value `sampling` to `mrtr`, keeping the set closed at three, and land the design, the §8 arm and `approval.py` together. Explicitly does not fold in 0021's `approval_state` restraint - that is 0033. |
| [0029](0029-the-body-size-limit-has-no-middleware-to-live-in.md) | Design change | **Accepted in part** - accepted on the refusal, CORRECTED on the claim | ACCEPTED: `MAX_PAYLOAD_BYTES` is NOT the discharge of `DESIGN.md:165`, and that row stays open. CORRECTED: the title's claim is too strong - an `ASGIMiddleware` seat exists via `http_run_kwargs`, so the body cap is a GAP, not an impossibility, and it is HTTP-only by construction. |
| [0030](0030-the-upstreams-retry-hint-is-dropped-on-every-shape-but-two.md) | Design change | Accepted | `retry_after` is populated on whatever problem shape results, wherever the upstream supplied one. It never becomes a required member, and absent means *we were not told*, never *do not retry*. |
| [0031](0031-the-registry-has-no-row-for-a-refused-approval.md) | Design change | Accepted | Add a registry row - *an approval was required and none was returned* -> `/problems/forbidden`, 403 - minting NO new slug. `detail` separates it from a missing scope, exactly as the design already separates an open breaker from an outage. |
| [0032](0032-a-fifth-middleware-runs-that-the-design-never-assessed.md) | Design change | Accepted | A fifth middleware runs that the design never assessed; ADOPT it rather than switch it off. §7.7 gains a fourth adopted middleware and C2 gains a row, rated LOW. Disabling it to match the document is rejected - fix the document, which is wrong, not the stack, which is fine. |
| [0033](0033-approval-state-is-a-published-vocabulary.md) | Design change | Accepted - **completes 0021** | `approval_state`'s four values (`approved`, `refused`, `pending`, `unavailable`) are correct and §5.3 names them as a closed set. `pending` and `unavailable` must NOT be collapsed: one is an abandoned conversation, the other one that never started. |
| [0034](0034-the-adr-count-in-design-md-is-deleted-not-corrected.md) | Design change | Accepted - **its selector is widened by 0035** | DELETE both ADR counts in `DESIGN.md` §13 rather than correcting them, and repair the universal by naming the class - `Type: Deviation` - in the count's place. No number replaces either: a corrected count is a count that will be wrong again. |
| [0035](0035-the-frozen-selector-must-admit-both.md) | Design change | Accepted - **widens 0034** | The frozen selector admits `Type: Both` as well as `Type: Deviation`; `Both` is NOT retired despite having zero users today; and `from 0012 onward` is DELETED, not corrected, because a boundary that must be maintained is the same defect as a count. Does not revisit 0034's ruling. |
| [0036](0036-fastmcp-4-0-3-ga-replaces-the-4-0-0b4-beta.md) | Design change | Accepted - **amends 0001**; JACK as Tier 0 under Phil's 2026-09-08 directive, KING concurring | Pin the GA `fastmcp==4.0.3` in place of the `4.0.0b4` beta and DROP the explicit `fastmcp-slim` line, which a GA pin resolves unnamed - measured both directions, and the repo's own control names this ADR as the remedy. `mcp==2.1.1` and `prerelease = "explicit"` both STAY. `DESIGN.md` is not edited. |

## An ADR's citations are AS AT its acceptance, and are NOT repointed

**MEASURED, all 64 `DESIGN.md:N` citations carried by the ADRs THEMSELVES - `docs/adr/0*.md`, 19 of
the 35 numbered files - read one at a time (`docs/reviews/CITATION-READ-ADR-VERDICTS.md`):
46 DRIFTED, 14 CORRECT, 2 WRONG, 2 boundary.** Seventy-two per cent point at text that WAS the
cited subject when written and is not any more, because `DESIGN.md` moved under them.

    grep -rhoE 'DESIGN\.md:[0-9]+(-[0-9]+)?' docs/adr/0*.md | wc -l    # 64, the population read
    grep -rhoE 'DESIGN\.md:[0-9]+(-[0-9]+)?' docs/adr/*.md  | wc -l    # more: this README quotes

**NAMING THAT BOUNDARY IS NOT PEDANTRY: THE COMMIT THAT FIRST WROTE THE SENTENCE ABOVE FALSIFIED
IT.** It said *"all 64 in this directory"*, and ruling on four citations meant quoting them, so the
bare directory grep returned 68 and the paragraph was wrong about itself on arrival - **the
ADR-0034 shape eight lines below, in the same commit as the claim.** The rewrite you are reading
quoted three more while explaining it. **So no total for `docs/adr/*.md` is written here**: it
moves whenever this file discusses a citation, which is the ADR-0034 remedy - a count that cannot
be maintained is DELETED, not corrected. What the extras have in common is that they are
QUOTATIONS, not citations - the class `check-brief-report-references.py`'s docstring rules on, one
corpus over - and no selector here can tell the two apart, which is why the population that was
read is named by PATH above rather than left to one.

**They stay.** An ADR is a DECISION RECORD: it states what was decided against the design as it
stood. Repointing its citations rewrites the evidence for a decision already taken and makes every
ADR silently claim to be about today's design. #111 ruled the same shape for `docs/plans` and the
reasoning carries.

**THE CASE THAT MAKES THIS NON-OBVIOUS IS IN THIS DIRECTORY.** `ADR-0034` cites `DESIGN.md:2063`
for the words *"all eleven ADRs"*. At `e3b5c97^` line 2063 reads exactly that - and `e3b5c97` is
the commit that APPLIED ADR-0034 and deleted the count. **The ADR's own accepted change falsified
its own citation**, and the re-freeze made the stale reading official. That is drift arriving in
one commit, from the decision itself, and no reader looking only at today's freeze can tell it
apart from carelessness.

**THE WORKED CASE, AND IT IS THE EMPIRICAL ARGUMENT FOR THIS RULE.** `ADR-0017` cites ONE range
twice - qualified at `:16`, bare at `:67`. `b0e86b8` ("Repoint 713 DESIGN.md citations") moved the
qualified half `489-490 -> 495-496` and could not see the bare half, because its selector requires
the filename. Measured across three trees:

    at acceptance 02245b1   :489-490  IS the seven-member problem object   BOTH halves correct
    at b0e86b8              :495-496  IS that sentence                     the repoint was right
    at the freeze d1f1a52   the sentence is at :546-547                    the repoint is now wrong

**THE HALF THAT WAS NEVER TOUCHED IS THE ONE THAT STILL MEANS WHAT ITS AUTHOR WROTE.** The
repointed half was correct for exactly as long as it took `DESIGN.md` to move again, and it left
the document contradicting itself in the meantime. `:16` is restored to `489-490`: the ADR agrees
with itself again and is back to the record it was.

**SO THE REPOINT TOOL MUST NOT LEARN THE BARE FORM.** That was proposed as "the only fix that stops
the class recurring", and it is the wrong direction - it would let a sweep move BOTH halves and
produce a consistent document that is still wrong at the next re-freeze, twice as thoroughly. **The
fix is for the repoint tool to stop touching `docs/adr/` at all**, which this rule already implies
and which no selector needs to learn.

**HOW TO READ A CITATION THAT DOES NOT MATCH.** Date the citation, then read the design as it was:

    git log -S'DESIGN.md:2063' --reverse -- docs/adr/0034-*.md   # when the citation was written
    git show <that sha>^:docs/DESIGN.md | sed -n '2063p'         # what it said then

**`git blame` IS THE WRONG INSTRUMENT and gives a confidently wrong answer.** It returns the last
commit to TOUCH the line, which for prose is a later rewrite - it dated ADR-0019's citations three
days after they were written, to a `DESIGN.md` the author never saw.

**NO SHA IS RETROFITTED INTO THE EXISTING ADRs**, and the reason is measured rather than argued.

Five ADRs already name a `DESIGN.md` blob with `git show <sha>:docs/DESIGN.md` - 0019, 0024, 0025,
0030, 0031 - and **in every one of them, line-numbered citations elsewhere in the same file drifted
anyway.**

    grep -lE 'git show [0-9a-f]{7}:docs/DESIGN\.md' docs/adr/00*.md | wc -l    # 5

**THOSE FIVE LINES ARE NOT ONE FORM, AND CALLING THEM ONE WAS THE ERROR.** Read one at a time, only
`ADR-0019:18` declares a SCOPE - *"Verified against the frozen object `git show
135c3ac:docs/DESIGN.md`"*. The other four INTRODUCE ONE QUOTATION each - *"`git show
c15b138:docs/DESIGN.md`, lines 486-487:"* - and bind that quotation and nothing else. A sentence
calling all five *"a citations-are-against-`<sha>` line"* describes one of them.

**WHAT ALL FIVE DO SHOW, PER FILE**, is that a blob named anywhere in an ADR does not bind the line
numbers elsewhere in it (`docs/reviews/CITATION-READ-ADR-VERDICTS.md`, the DRIFTED table):

    0019   4 bare `DESIGN.md:603`                                    all 4 DRIFTED
    0024   5 bare `DESIGN.md:N`                                      all 5 DRIFTED
    0025   3 bare `DESIGN.md:373-375`                                all 3 DRIFTED
    0031   3 bare `DESIGN.md:N`                                      all 3 DRIFTED
    0030   `:356-359` and `:361-362`, THREE LINES BELOW the sha, filename omitted
           both exact at `c15b138`, both DRIFTED at the freeze `d1f1a52`

**`ADR-0030` IS THE TIGHTEST CASE IN THE SET AND EVERY SELECTOR RUN HERE WAS BLIND TO IT.** Its two
citations omit the filename, so `grep -E 'DESIGN\.md:[0-9]+'` returns zero for that file and it
reads as carrying no citation at all - a review round concluded exactly that. It carries two, three
lines under the sha, and both drifted:

    git show c15b138:docs/DESIGN.md | sed -n '356,359p'   # the open-breaker/outage 503, as cited
    git show d1f1a52:docs/DESIGN.md | sed -n '356,359p'   # "Ordered timeout, then retry, then breaker"

**Proximity is the strongest binding short of naming the blob inline, and it still failed.**

(The count was five only on the second attempt. The first selector asked for "an ADR mentioning a
seven-hex sha near the words `git show`", which also matched ADRs recording where a fix LANDED, and
returned twelve; the discriminator is naming a `DESIGN.md` BLOB, not naming a commit. **The second
selector was loose too, one column over.** It counts blob-naming LINES, and this section is about a
FORM - which is how four quote-introducers were read as scope declarations, and how `0030`'s bare
citations were read as an absence. Every one of these was caught the same way: two independently
derived numbers disagreed, and nothing else looked.)

**`ADR-0019` IS THE PROOF THAT A SCOPE DECLARATION DOES NOT BIND EITHER.** `:18` names the frozen
object outright, and all four of its `DESIGN.md:603` citations drifted anyway. **The ADR that best
documented its own reference point is the one with four drifted citations in it.** Each
`DESIGN.md:603` still resolves on its own against the current freeze, and a reader who lands on one
never sees the paragraph.

**THE FORM THAT BINDS PUTS THE SHA INSIDE THE CITATION**, and that exists too. `ADR-0025:117`:

> `git show 8a9d63c:docs/DESIGN.md`, §4.5, lines 453-455 **of that blob**

There is no number there that can drift, because the blob is named and immutable - **and it binds
that quotation only.** The same file's three `DESIGN.md:373-375` citations sit outside it and all
three drifted. That is not a contradiction with the row above; it is the scope of the form, stated
exactly.

**SO: NEW ADRs SHOULD CITE THE BINDING FORM. Existing ones are not rewritten.** Retrofitting is a
sweep over a record set, which is the thing this whole section refuses; and adding the NEAR form
would deploy, for the thirteenth time, a convention already measured not to work.

## Acknowledged non-conformances without an ADR

One obligation is knowingly unmet and deliberately has no ADR, because an ADR would imply a
decision we are not entitled to make:

- **`threat-modeling.md:146`** requires mitigations to become numbered functional requirements.
  The corpus contradicts itself about the ticket prefix - `agentic-coding-standard.md` expects
  `FEAT/FR/BUG/TECH`, `quality-gates.md` adds `TECH`, `development-workflow.md:166` expects
  layer-prefixed `[FE-001]`, and this work is tracked as `EC-###`. **Inventing a prefix to satisfy
  a clause the standards cannot agree on would move the defect rather than fix it.** Recorded here
  so it is visible rather than skipped.

