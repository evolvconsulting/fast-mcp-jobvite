# suborch-jobvite-403: fastmcp 4.0.0b4 -> 4.0.3

**Verdict: the work is DONE and MEASURED, and it is HELD.** The bump contradicts a frozen
design and an Accepted ADR, so ADR-0036 lands **Proposed** and Tier 0 rules. Do not merge
`e90d21d` or `3c2a79b` until it is Accepted.

- Worktree: `/tmp/suborch-jobvite-403`, branch `chore/fastmcp-4.0.3`, cut from `a9a85ed`.
- **Left in place, not removed**, per the brief's closing instruction.
- Nothing pushed, nothing merged, the shared checkout at
  `repos/fast-mcp-jobvite` was read (`git worktree list`, `git log`) and never checked out.
  It was on `main` at `a9a85ed`, clean; `chore/fastmcp-4.0.3` did not exist, so no sibling
  branch was needed.
- Tier-2 workers spawned: **zero**. Six of six Tier-1 runs now.

Tier 0 lands it, if it rules to, with:

    git -C /home/plafayette/claude_projects/evolv/repos/fast-mcp-jobvite merge --ff-only chore/fastmcp-4.0.3

## 1. Canon actually read

**Read in full:** `docs/briefs/PREAMBLE.md`; `docs/briefs/PROTOCOL-sub-orchestrators.md`;
`docs/adr/0001-target-fastmcp-4-beta.md`; `docs/adr/README.md`; `pyproject.toml`;
`tests/test_manifest.py`; `docs/reviews/check-adr-numbers.py`; `scripts/check-suite-floor.sh`.

**Read at the freeze, never the working tree:** `docs/DESIGN.md` at
`d1f1a52`, derived from `docs/DESIGN-FREEZE.txt` and not retyped from the brief. Read §10 in
full (`:1480-1540`) and grepped the whole blob for the pin vocabulary. **The working tree copy
is byte-identical to the frozen blob** (`diff -q`, no output), so the freeze has not drifted.

**Read in part, by grep and section:** `docs/research/FASTMCP.md` (target, bottom-line table,
release table, version facts, the sections the bump touches); `docs/DECISIONS.md` (header, D1,
D17); `docs/research/COMPLIANCE-SPEC.md` (the four beta references only);
`.github/workflows/ci.yml` (the whole `test` job, parsed rather than skimmed).

**Deliberately NOT read:** the evolv-coder TIER-1 standards set and `MUST-READ-DOCS.md`. The
brief's own §"The jobvite canon" says fast-mcp-jobvite's canon **outranks** evolv-coder's for
this repo, and this change touches no evolv-coder artifact. The jobvite-local equivalents
(`docs/research/STANDARDS.md`, `COMPLIANCE-SPEC.md`) were consulted through the citations
`pyproject.toml` already carries. **Say so plainly: if a `priority: required` clause in the
evolv-coder corpus bears on a dependency pin, I did not check it.**

**Looked for and found:** `docs/reviews/check-checkers-are-wired.py` exists and is wired.
`docs/adr/` holds 35 numbered ADRs plus a README index; `standards/architecture/adr/` was not
consulted (out of repo).

## 2. Baseline Gate, `a9a85ed`, before any change

Replayed from `.github/workflows/ci.yml` **by parsing the YAML**, not by retyping: a generator
extracts every `run:` block of `jobs.test` verbatim and executes each under `bash -e`, which is
how GitHub runs them. 31 run-steps.

    RC STEP 01 = 0   Install from the frozen lock
    RC STEP 02 = 0   No lock drift
    RC STEP 03 = 0   Lint
    RC STEP 04 = 0   Format
    RC STEP 05 = 0   Types
    RC STEP 06 = 0   Default suite, zero skips
    RC STEP 07 = 0   Network-dependent arms
    RC STEP 08 = 0   The README's Quickstart still works
    RC STEP 09 = 0   Docs-lint amputations, every row caught
    RC STEP 10 = 0   Collect the credentialed suite
    RC STEP 11 = 0   Harness anchors still resolve
    RC STEP 12 = 0   Every DESIGN.md citation resolves to a line that exists
    RC STEP 13 = 0   Every harness is wired and has a row floor
    RC STEP 14 = 0   Every checked row floor EQUALS its harness's live row count
    RC STEP 15 = 0   The floor container's own arms
    RC STEP 16 = 0   A test name reaches a verdict as a literal, never as a pattern
    RC STEP 17 = 0   No SIGPIPE-prone pipeline judges a gate
    RC STEP 18 = 0   A harness that diagnoses a landing failure publishes it
    RC STEP 19 = 0   The gate records who is mutating
    RC STEP 20 = 0   The mirror refuses a zero-ref push
    RC STEP 21 = 0   Every report a brief cites is committed
    RC STEP 22 = 0   Controls for the brief-report reference gate
    RC STEP 23 = 0   The bare-citation discriminator's controls
    RC STEP 24 = 0   ADR numbers are unique and contiguous, and the index matches
    RC STEP 25 = 0   Every pytest invocation is bounded by a timeout
    RC STEP 26 = 0   Committed file types, whole tree
    RC STEP 27 = 0   Commit-time hooks run clean - secret scan, shellcheck, file types
    RC STEP 28 = 0   Advisory audit - the expiry half
    RC STEP 29 = 0   Dependency audit
    RC STEP 30 = 0   Capability drift report
    RC STEP 31 = 0   ADR-0010's per-module coverage floors

Summary lines, verbatim:

    ================= 889 passed, 6 deselected in 70.49s (0:01:10) =================
    suite floor OK: 889 passed, floor 888
    ====================== 2 passed, 893 deselected in 1.68s =======================
    suite floor OK: 2 passed, floor 2
    =============== 4/895 tests collected (891 deselected) in 1.16s ================

**0 skipped.** The baseline is green on all 31.

### The red baseline that was my instrument, not the tree

Step 30 first read `RC = 1`:

    ERROR    Failed to call factory function 'create_server': tool 'get_candidate' is
    enabled but requires unset variable(s): JOBVITE_API_KEY, JOBVITE_API_SECRET; ...
    ::error::fastmcp inspect failed

My generator copied each step's `run:` and **dropped its per-step `env:`**. That step carries
`JOBVITE_API_KEY: inspect-only-not-a-credential`, `JOBVITE_API_SECRET: ...`,
`JOBVITE_TOOLS: search_jobs`. With CI's env the step exits 0 and writes a 10,413-byte
`inspect.json` listing one tool, `search_jobs`. The generator now emits workflow, job and step
env, and the fix was applied **before** any post-bump measurement so both runs ask the same
question. Recorded because it is the brief's own trap - a gate run without CI's arguments is a
different, weaker question - committed by the instrument built to avoid it.

## 3. THE RULING TIER 0 OWES: the bump contradicts the frozen design

Four independent sources, and one of them is the repository's own test:

1. **`docs/DESIGN.md:1485`** (frozen at `d1f1a52`) - *"Python `>=3.12`. `fastmcp==4.0.0b4`
   targeting the sessionless `2026-07-28` spec as deliberate early adopters."*
2. **`docs/DESIGN.md:1497-1506`** - the packaging block stated **verbatim**, carrying
   `"fastmcp==4.0.0b4"`, `"fastmcp-slim==4.0.0b4"`, `"mcp==2.1.1"` and
   `[tool.uv] prerelease = "explicit"`.
3. **`docs/adr/0001-target-fastmcp-4-beta.md`**, Decision - *"Pin `fastmcp==4.0.0b4` and target
   the sessionless `2026-07-28` spec."* Status Accepted (Phil, 2026-08-27).
4. **`tests/test_manifest.py:166-170`**, the assertion message of the control that fires:
   *"removing the fastmcp-slim pin STILL resolved. Either uv's behaviour changed or the pin is
   no longer load-bearing; DESIGN.md:1499-1501 needs an ADR before the line is touched."*

`PROTOCOL-sub-orchestrators.md:18-20` - *"A frozen design changes only by numbered ADR. A
sub-orchestrator that thinks the design is wrong reports it and stops; it does not decide."*
So I did not decide. `docs/adr/0036-fastmcp-4-0-3-ga-replaces-the-4-0-0b4-beta.md` is
**Proposed** and `docs/DESIGN.md` is not touched.

**What I did instead of stopping cold**, and why it is not a ruling: I measured the whole
change on my own unmerged branch so that Tier 0 rules on evidence rather than on my prose. The
brief asked for a measurement; PROTOCOL forbids a decision. Landing a measured diff on a branch
only Tier 0 can merge is the first without being the second.

### The measurement that settles the `fastmcp-slim` half

Five real `uv lock` resolves, each in its own scratch directory, none in the worktree:

| arm | manifest | rc | packages | `fastmcp-slim` |
|---|---|---|---|---|
| 1 | as committed (4.0.0b4, slim named) - **positive control** | 0 | 121 | 4.0.0b4 |
| 2 | 4.0.3, slim still named | 0 | 121 | 4.0.3 |
| 3 | 4.0.3, slim line **dropped** | 0 | 121 | 4.0.3 |
| 4 | 4.0.3, slim dropped **and** `[tool.uv]` removed | 0 | 121 | 4.0.3 |
| 5 | 4.0.0b4, slim **dropped** - **negative control** | 1 | - | resolve failed |

Arm 5, verbatim:

    Because there is no version of fastmcp-slim[client]==4.0.0b4 and
    fastmcp==4.0.0b4 depends on fastmcp-slim[client]==4.0.0b4, we can
    conclude that fastmcp==4.0.0b4 cannot be used.

Both controls fire, so neither direction is vacuous. The pin **was** load-bearing and **is
not** at a GA pin, because `prerelease = "explicit"` refuses a transitive PRERELEASE nobody
named and 4.0.3 is not one. Arm 3 is exactly what the old control asserts the negative of, so
**that control cannot survive the bump in place**: after the bump its mutation resolves and it
would pass by testing nothing.

Arm 4 is the one that decided a judgement call: `[tool.uv] prerelease = "explicit"` is **kept**
even though the resolve no longer needs it. It costs nothing and it is what stops a future
prerelease arriving unannounced.

## 4. Lock delta

`uv lock` then `uv sync --frozen`. `git diff --stat uv.lock`: **7 insertions, 9 deletions**.

| package | before | after |
|---|---|---|
| fastmcp | 4.0.0b4 | **4.0.3** |
| fastmcp-slim | 4.0.0b4 | **4.0.3** |
| mcp | 2.1.1 | 2.1.1 |
| mcp-types | 2.1.1 | 2.1.1 |
| pydantic | 2.13.5 | 2.13.5 |
| pydantic-settings | 2.15.0 | 2.15.0 |
| starlette | 1.6.0 | 1.6.0 |
| httpx2 | 2.12.0 | 2.12.0 |
| httpx | absent | absent |

Package count 121 -> 121. Computed as a **set difference over every package in the lock**, not
a spot-check of the nine above: exactly two entries changed, `fastmcp` and `fastmcp-slim`.

## 5. Upgrade-guide audit

Every signal the brief names, `git grep -n` over `src tests scripts docs/reviews server.json
pyproject.toml`. **23 of 29 signals: zero hits.** The six with hits:

| signal | hits | what the guide says | what I did |
|---|---|---|---|
| `ctx.elicit` | 4 call sites, all `await ctx.elicit(..., response_type=...)`: `src/fast_mcp_jobvite/approval.py:494`, `scripts/check-u10-write-amputation.sh:247,249`, `tests/test_arguments_sweep.py:527`; the other 24 are prose | needs `response_type=`; raises on the 2026-07-28 protocol | **Nothing.** Every call site already passes it, and `approval.py`'s era guard is built around it raising on sessionless. |
| `except httpx.` | 4, all inside `docs/reviews/DESIGN-R1.md` and `DESIGN-R2.md` prose | fastmcp raises `httpx2` exceptions; a handler on `httpx.ConnectError` is dead code | **Nothing.** Zero in code. A `-P` grep for bare `httpx` not followed by a digit, over `src tests scripts docs/reviews`, returns **zero hits outside `httpx2`**. ADR-0007 already made this move. |
| `Client(` | 141, none of them the signal | bare-string paths break | **Nothing.** Every hit is `Client(server)`, `Client(StreamableHttpTransport(...))` or our own `JobviteClient(...)`. A dedicated grep for `Client(` followed by a quote returns **0**. |
| `mount(prefix=` | 0 | - | - |
| `remove_tool(` | 0 | - | - |
| `McpError(` | 0 | - | - |

**Correction to my own instrument, and it is the point of listing the last four.** Those four
patterns first ran through `git grep -nE` with unescaped parens and each returned
`fatal: command line, 'McpError(': Unmatched ( or \(`. A grep that ERRORS is **unmeasured, not
zero**, and in a table of 29 signals it would have read as four more clean absences. Re-run with
`git grep -nF`. `Client(` then went from an apparent 0 to 141 hits, none of which is the signal
- so the wrong zero would have been right by accident, which is the worst way to be right.

Zero hits, shown rather than asserted: `ctx.sample`, `ctx.sample_step`, `ctx.list_roots`,
`sampling_handler`, `import_server`, `as_proxy`, `add_tool_transformation`, `serializer=`,
`exclude_args=`, `sse_read_timeout`, `task=True`, `FASTMCP_DECORATOR_MODE`,
`fastmcp.server.proxy`, `fastmcp.server.openapi`, `fastmcp.tools.tool`,
`fastmcp.resources.resource`, `fastmcp.prompts.prompt`, `fastmcp.server.tasks`,
`fastmcp.dependencies`, `CachableToolResult`, `PromptToolMiddleware`, `ResourceToolMiddleware`,
`SkillsProvider`.

`fastmcp.dependencies` deserves a word: the code imports `fastmcp.server.dependencies`
(`http_hardening.py:45`), which is the current path, so the zero is real and not a near-miss.

### The strongest evidence, and the design said it had never been run

`DESIGN.md:1909` rates threat C9-T1 and names its third mitigation *"`fastmcp inspect` output
diffed between builds so capability drift appears in review"* as **"designed and unexecuted"**.
It is executed now. `inspect.json` from the 4.0.0b4 baseline against `inspect.json` from the
4.0.3 tree, compared section by section:

    environment before: {'fastmcp': '4.0.0b4', 'mcp': '2.1.1'}
             ->  after: {'fastmcp': '4.0.3',   'mcp': '2.1.1'}
      capabilities         identical=True
      instructions         identical=True
      prompts              identical=True
      resourceTemplates    identical=True
      resources            identical=True
      serverInfo           identical=True
      tools                identical=True

**Zero capability drift.** Every section byte-identical except the block that names the
version. That is the diff the design specified and never ran, and it is the single best reason
to believe this bump is inert.

## 6. Post-bump Gate

Same generator, same 31 steps, run on the **staged** tree so the `git ls-files` based checkers
could see the new files.

**First post-bump run: 30 of 31 green, `RC STEP 04 = 1`.** Verbatim:

    unformatted: File would be reformatted
       --> tests/test_manifest.py:187:9
    186 |         "a prerelease pin resolved with its transitive unnamed. Either uv's "
        -         "behaviour changed or prerelease = \"explicit\" is no longer in force; "
    187 +         'behaviour changed or prerelease = "explicit" is no longer in force; '

`ruff format` prefers a single-quoted literal to escaping the doubles inside it. Fixed by a
one-line scripted edit, not by running `ruff format`, so the diff stays one line.

**Confirming run on the staged tree: all 31 steps `rc=0`** (889 passed / 6 deselected in
78.53s; 2 passed in the network arm; 4/895 collected).

**FINAL run, on the fully committed branch at `024b04a`, is the authoritative one: all 31
steps `rc=0`, 17:39:43 -> 17:42:06.** Summary lines, verbatim:

    ================= 889 passed, 6 deselected in 94.48s (0:01:34) =================
    suite floor OK: 889 passed, floor 888
    ====================== 2 passed, 893 deselected in 1.76s =======================
    suite floor OK: 2 passed, floor 2
    =============== 4/895 tests collected (891 deselected) in 1.70s ================

The Gate was run **three times post-bump** and the whole 31-step set is green on the final
commit, so the report's claim covers the tree Tier 0 would merge and not an intermediate one.

**Baseline vs post: identical.** 889 passed, 0 skipped, 6 deselected; 2 network; 4 credentialed
collected. The suite count did not move because the two renamed/replaced tests were replaced
one-for-one - deliberately, since 889 is one above the floor of 888 and a bare deletion would
have sat exactly on it.

### One green in that run I refused to accept

Step 27 hung for 21 minutes on `ShellCheck v0.10.0`, which pre-commit runs through
`docker run koalaman/shellcheck:v0.10.0`. Two containers sat "Up 20 minutes"; the same step had
taken **11 seconds** in the previous run. I killed **only those two**, having first confirmed
via `pgrep -aP <my pre-commit pid>` that both were children of my own process and via
`docker inspect` that both mounted `/tmp/suborch-jobvite-403`. No other agent's container was
touched.

The step then reported `rc=0` **and `ShellCheck ... Passed`**. A green that arrives immediately
after I killed the thing producing it is not evidence, and I did not establish whether those
batches had already completed. So I re-ran step 27 standalone on a clean daemon: **10 seconds,
`rc=0`, ShellCheck Passed.** That standalone run is the evidence; the in-run one is discarded.

## 7. Commits

| sha | subject |
|---|---|
| `228c43d` | docs: ADR-0036 proposes the GA fastmcp pin, and it is NOT accepted |
| `e90d21d` | build: pin fastmcp 4.0.3, the GA line, in place of the 4.0.0b4 beta |
| `3c2a79b` | docs: the beta-era prose follows the pin, and the records do not |

Authored as `ci <ci@example.invalid>`, which is what `git config user.name/user.email` resolves
to from `.git/config` and what 6 of the last 8 non-merge commits on `main` used. No
`Co-Authored-By`, no "Generated with", no em dashes. The Gate was measured on the **final tree**,
not on each commit individually.

Every edit was applied by a **script** with a uniqueness assertion on its anchor and a read-back
after the write, so nothing was hand-typed and every one is replayable. One anchor failed
(`0 occurrences`) and said so rather than no-opping silently; it was a mistyped `fails|` for
`fails||` in my own script, fixed and re-run.

## 8. What I deliberately did NOT change

- **`docs/DESIGN.md`.** Frozen. ADR-0036 is the instrument.
- **`docs/adr/0001`.** An immutable decision record. `docs/adr/README.md` carries the amendment
  edge `0036 -> 0001` instead, in the same both-rows form the file already uses for
  `0028 -> 0021`, `0033 -> 0021` and `0035 -> 0034`.
- **`docs/DECISIONS.md`.** Its own first line: *"Decision log (pre-freeze) ... At design freeze
  each of these becomes a numbered ADR."* D1 became ADR-0001; the log is closed.
- **`CHANGELOG.md:311`.** A dated 2026-08-27 entry. `changelog.d/403-fastmcp-ga.md` records the
  new change, per `changelog.d/README.md`'s rule that only the orchestrator merges fragments.
- **`src/fast_mcp_jobvite/tools/jobs.py:373`** - *"MEASURED against a live FastMCP context on
  fastmcp 4.0.0b4"*. Swapping in 4.0.3 would claim a measurement nobody made.
- **`docs/research/FASTMCP-SPIKE-4.md` (42 hits), `IMPLEMENTATION-PLAN.md` (10),
  `U0-REPORT.md` (9), `COMPLIANCE-SPEC.md` (4), and every `docs/reviews/*`** - executed records
  and review rounds.
- **Every `[FROM SOURCE]` listing in `FASTMCP.md`** (`:50, :70, :90, :153, :259, :418, :512,
  :632, :849`). Each names the version it was read at. Rewriting them to 4.0.3 would claim a
  re-enumeration I did not do; the document's header now says so explicitly instead.
- **`[tool.uv] prerelease = "explicit"`** - kept, see arm 4.
- **`mcp==2.1.1`** - kept, `DESIGN.md:1486-1488`'s reason is untouched by the GA move.

## 9. Every number in the brief I found to be wrong

| brief said | measured | note |
|---|---|---|
| *"The last handoff said 360 passing tests; a static count today found 680 `def test_`"* | **889 passed, 6 deselected, 895 collected** | Both figures were wrong. `def test_` undercounts because parametrisation expands one definition into many cases. |
| *"The Gate is ~3 min"* | **2 min 01s** both times: baseline 16:58:38 -> 17:00:39, first post-bump run 17:09:06 -> 17:11:07 | The confirming run took 23 min 13 s, of which ~21 min was a Docker stall in step 27, not work. |
| *"drop the explicit `fastmcp-slim` line"* (stated as a step) | **Requires an ADR**, and the repo's own test says so | Not a wrong number - a wrong assumption about who may decide. This is the report's headline. |
| *"`mcp` should stay at 2.1.1 under 4.0.3; if it moves, that is a finding"* | **Stays 2.1.1.** No finding. | Confirmed rather than corrected. |
| 4.0.0 GA 2026-08-31, 4.0.3 2026-09-05 | **Confirmed** from the PyPI JSON API: 4.0.0 2026-08-31T18:20:31Z, 4.0.3 2026-09-05T00:31:33Z, and 4.0.3 IS `info.version` today | Confirmed rather than corrected. |
| *"jobvite already uses `httpx2` ... check the CLIENT code for any remaining `httpx.` exception handlers"* | **Zero**, in the client and everywhere else | Confirmed. |
| *"harness-assurance tier is 60-70 min and is NOT in scope"* | **Not run.** Stated, not measured. | See §11. |

**Two further corrections, to the brief's boilerplate rather than its numbers.** The isolation
section's `EVOLV_CODER_DOCS_ROOT` and `tests/ci/test_api_contract_diff.py` clauses are already
marked inapplicable by the brief itself, and they are: no such file exists here
(`git ls-files tests/ci/` is empty). The `--floor 464` figure in `ci.yml`'s anchor step was
**derived from the workflow, not from the brief**, per `PREAMBLE.md`'s instruction, and it is
464 today, not the 458 that `pyproject.toml:347`'s comment still names in passing.

## 10. Findings outside my scope - REPORTED, not filed

`PREAMBLE.md`: *"If your brief is silent, report it and do not create it."* It is silent, so
these are not on the board.

1. **The Gate leaves an untracked `inspect.json` in the tree.** Step 30 writes it and
   `.gitignore` does not list it. `check-committed-file-types.py`'s population is
   `git ls-files`, so it is invisible to the gate that would refuse it. I did not commit it and
   did not add it to `.gitignore` - that is a `.gitignore` change on a branch already carrying a
   held ADR. **Suggested fix:** one line, `inspect.json`, in the coverage-artefact block of
   `.gitignore`, in its own commit.
2. **`pyproject.toml:347` names an anchor floor of 458; `ci.yml` says 464.** Harmless today
   because the comment is prose and `ci.yml` is the enforcer, and it is exactly the retyped
   constant `PREAMBLE.md` exists to warn about. **Suggested fix:** delete the number from the
   comment rather than correcting it, per ADR-0034's reasoning.
3. **`docs/research/FASTMCP.md:676`** recommends
   `constraint-dependencies = ["fastmcp-slim==4.0.0b3"]` - `b3`, a version this project never
   pinned, in a "Prerelease install" section. Still correct advice *for a prerelease*, so I left
   it. **Suggested fix:** if anyone touches that section, say which prerelease it is an example
   of.
4. **A docker-backed pre-commit hook can wedge indefinitely** (21 minutes vs 11 seconds, same
   tree). On a GitHub runner this would burn the job's 15-minute timeout and read as a code
   failure. **Suggested fix:** none proposed; it may be purely local to Docker-on-WSL2, and I
   have one occurrence, which is not enough to characterise it.

## 11. What I could NOT settle, and what I did not attempt

**Could not settle:**

- **Whether pre-commit reported `ShellCheck ... Passed` for batches that were SIGKILLed.** I
  killed two containers and the step returned 0 with a Passed line. I could not tell whether
  those batches had already finished before I looked. I re-ran the step clean rather than
  reason about it, so the conclusion is safe, but the underlying question is open and it is the
  shape of a real defect: a hook whose container dies must not render as a pass.
- **Whether any `priority: required` clause in the evolv-coder standards corpus bears on a
  dependency pin.** I read the jobvite canon, which the brief says outranks it here, and did not
  open the 18 TIER-1 documents. If one of them forbids or constrains a GA-vs-prerelease pin, I
  would not have seen it.
- **Whether 4.0.1 or 4.0.2 introduced anything between 4.0.0 and 4.0.3 that matters.** I audited
  against the 3-to-4 upgrade guide, which is a major-version document. I did not read release
  notes for the three patch releases.

**Did not attempt** (a separate list on purpose):

- **The harness-assurance tier.** The brief scoped it out. `scripts/check-u0-test-controls.sh`,
  whose row I edited, runs there and **not** in the Gate (`ci.yml:2126`, inside the
  `harness-assurance` job that starts at `:1817`). Its anchor is statically verified by Gate
  step 11, which passed, so the sed pattern resolves - but **the row has not been executed since
  I changed it.** That is the single most likely place for fallout from this branch, and it is
  the first thing I would run with more time.
- **`docs/reviews/check-obligations.py`.** `PREAMBLE.md` requires it if a change moves an
  obligation anchor. I do not believe this change moves one; I did not run it to prove that.
- **Whether `server.json` should reference the framework version.** `grep -c fastmcp` returns
  0, so the bump cannot have stranded anything there, but I did not reason about whether a
  server manifest ought to name it.
- **Any push, merge, rebase, stash, or branch move.** Not attempted by design.
