# JOBVITE FOLLOWUPS - report from suborch-jobvite-followups

Tier-1 sub-orchestrator, dispatched by JACK under `PROTOCOL-super-orchestrators.md`. Brief:
`consensus/JACK-brief-jobvite-followups.md`. Repository `repos/fast-mcp-jobvite`; both open
branches cut from `cc42576` (PR 4's merge) and deliberately NOT rebased after main moved to
`4b3b040`.

Three pieces, not the two the brief opened with: Tier 0 inserted piece 0 mid-task.

    piece 0   board row 36        one archived relative link, the trunk red     MERGED as 4b3b040
    piece 1   board row 19        PREAMBLE.md amended to the adopted protocol   MERGED as 417cbb6
    piece 2   board rows 23, 29   the citation checker's controls population    7e4b4be, 9 commits

**THE PRE-MERGE ROUNDS WERE TIER 0'S, NOT MINE, AND THAT IS WHY THIS BRANCH CONVERGED.** After four
rounds briefed by me on piece 2 whose finding rate did not fall (2M, 2M, 1M, 3M), Tier 0 ruled that
he would brief and run the pre-merge rounds himself on both branches, with his own shape lists. His
round 5 found a MEDIUM on each branch that four rounds of mine had not; his round 6 on piece 2 then
returned nothing at any severity, the first clean round that branch has had. Piece 1's round 6
returned two Lows and two Nits, folded at `030b2b9` with the empty SHA correction `89ba708`; its
round 7 then returned 0C/0H/0M/0L/1N, nothing above a Nit, and the branch took its stub-only commit.

The mechanism, stated because it is the finding of this task and not an apology: every brief I wrote
carried a shape list built from what I had already been shown, so each round was steered toward the
axis of the last defect and away from the next one. The evidence is inside my own briefs. Round 4's
two non-git MEDIUMs came from the single instruction that was not derived from a defect I had
already seen, the line telling it to look at dependencies other than git; and round 5's MEDIUM
(nothing ever called the real scan) was on the one axis none of my four shape lists named.

## What I read

Read in full before the first edit:

- `consensus/JACK-brief-jobvite-followups.md`, and `PROTOCOL-super-orchestrators.md`, which moved
  under me at least four times while I worked (`5faec69`, `bf55860`, `deb6158` as draft 12, and its
  adoption `3e19ce3`). I re-read it before each fold, and round 4 found the one place where I had
  not.
- `docs/briefs/PREAMBLE.md` at `cc42576` (the subject of piece 1).
- `docs/DESIGN.md` at the SHA in `docs/DESIGN-FREEZE.txt`, derived not retyped:
  `git show "$(cat docs/DESIGN-FREEZE.txt)":docs/DESIGN.md`. The freeze names `3ba2a3d`. I did not
  edit it and no piece needed to.
- `docs/reviews/check-checkers-are-wired.py`; `docs/reviews/check-review-coverage.py`'s docstring
  (the stub rules piece 1 documents); `docs/reviews/repoint-design-citations.py:145-160` (the LIVE
  versus RECORD directory doctrine); `docs/worklogs/REPOINT-403-report.md`.
- `.github/workflows/ci.yml`: the `test` job is the required check "Gate - lint, types, tests",
  35 steps of which 31 are `run:` steps.
- Of the TIER-1 standards the brief names as bearing here: `standards/backend/python.md`,
  `standards/devops/ci-cd.md`, `standards/documentation/agentic-coding-standard.md`.

**Not read, said plainly rather than implied:** the other fifteen TIER-1 documents in
`MUST-READ-DOCS.md`. The brief names three as the ones bearing on a checker change and a canon
document change; the rest govern product code neither piece touches. No `priority: required` clause
I read contradicts anything in the brief.

## MEASUREMENT FIRST

### The Gate baseline at `cc42576`, re-measured rather than trusted

    REPLAY test: 31 run-steps replayed, 4 uses-steps not replayed, exit 0

31 of 31 `run:` steps rc=0. Re-measured again directly at the preamble head, so the number is this
branch's and not a remembered one:

    889 passed, 6 deselected in 56.25s

No "skipped" term appears in that line, which is how zero skips renders.

### Board row 23: does either citation checker notice a broken file enumeration?

Method: patch each enumerator to `return []`, re-run every arm, restore from git, and grep AFTER
the restore. Both mutations were asserted LANDED before any arm ran, and after the restore the
marker was absent and `git status --porcelain` was empty.

| arm | intact at `cc42576` | enumeration amputated |
|---|---|---|
| `check-design-citations.py` (default) | rc=0 | `SELECTOR CONTROL: no DESIGN.md citations found anywhere. The pattern is broken, not the corpus.` rc=1 |
| `check-design-citations.py --controls` | `3/3 controls fired.` rc=0 | `3/3 controls fired.` rc=0 |
| `check-design-citations.py --since 28be78a` | 1618 MOVED, 55 BROKEN, rc=1 | `against 28be78a: 0 citation(s) moved, 0 point at changed lines` rc=0 |
| `check-design-citation-shape.py` (default) | rc=0 | `PARSED ZERO CITATIONS. The selector is broken; a green means nothing.` rc=1 |
| `check-design-citation-shape.py --controls` | `7/7 controls fired.` rc=0 | `6/7 controls fired.` rc=1 |

**Row 23 is CONFIRMED and WIDER than the row says.** The row names the `--controls` arm. The
`--since` arm is fail-open too, and worse: it prints an affirmative all-clear (`0 citation(s)
moved`) and exits 0 where the intact run reports 1618 moved and 55 broken at rc=1. A checker that
says "nothing moved" when it enumerated nothing is the shape this whole branch exists to remove.

### The brief's wiring hypothesis, corrected

The brief supposed the `--controls` arm was wired into the Gate. It is not.
`check-design-citation-shape.py` is step 15 of the `static-gates` job, a MERGE-tier job that reports
SKIPPED on pull requests (piece 0 measured that live; it is board row 39). **Neither `--controls`
arm is wired anywhere.** So this fix hardens an instrument run by hand, which is exactly when a
fail-open matters most: nobody is watching the exit code.

### Board row 29 and the floors

No floor moved. `grep` for every assertion of the controls count found nothing to move: the only
"3/3" strings in the repository are historical records in past tense. Re-confirmed at the head:

    docs/reviews/check-row-floors.py                            rc=0
    docs/reviews/check-row-floor-exactness.py                   rc=0
    scripts/check-harness-anchors.py --self-check --floor 464   rc=0
    docs/reviews/check-checkers-are-wired.py                    rc=0
    docs/reviews/probe-repoint-fail-closed.py                   rc=0

### Every citation of `PREAMBLE.md` by line, before piece 1 moved anything

Three citers of the delivery rule at `PREAMBLE.md:133`:

    .github/workflows/ci.yml:1380                      LIVE
    docs/reviews/check-brief-report-references.py:8    LIVE
    docs/briefs/BRIEF-R20-the-held-25.md:115           RECORD

**Three of the delivery rule; four citations of the file, and neither count is exhaustive of the
file.** `docs/archive/reviews/WORKLOG-222-merge-invented-content.md:188` cites `PREAMBLE.md:16-26`,
a different anchor in a RECORD directory, untouched by this work. A reviewer caught me writing
"three files cite PREAMBLE.md:133" in a way that read as exhaustive of the file rather than of one
anchor; this is the corrected form.

By `repoint-design-citations.py:145-160`, `docs/briefs/PREAMBLE.md` is LIVE and `docs/briefs/` is
RECORD, longest prefix wins, so the two LIVE citers move with the sentence and the RECORD one does
not. Both LIVE citers were repointed twice: `:133` to `:173` (`1e42618`), then `:173` to `:177`
(`5c65731`). `BRIEF-R20-the-held-25.md:115` still reads `:133`, deliberately and correctly as a
record of what the file said then. **No third repoint is owed**: `ffc9f2d` rewrote bullet 1 in
place and grew it downward only, and its edit script asserts that the 176 lines above are
byte-identical and that line 177 still opens `1. **Your report, committed on your branch**`.

## PIECE 0 - board row 36, the archived link, MERGED

**What it was.** The trunk had been red since 2026-09-03. Step 32 of the merge-tier job,
"Relative links resolve", failed on one relative markdown link in an archived worklog:
`docs/archive/worklogs/WORKLOG-157-mirror-minutes.md:13`.

**What it is now.** That one link repointed to `../../reviews/REPORT-157-mirror-minutes.md`.
Nothing else changed.

**Two things in the diagnosis I was handed were wrong, and I corrected both before fixing
anything.** The red was FIVE push-to-main runs deep, not three, and began 2026-09-03, not
2026-09-07. And `docs/archive/reviews/` EXISTS with 21 files in it; the target simply is not one of
them, which is a different defect from the directory being absent and would have produced a
different fix.

**Confirmed against the real instrument.** lychee 0.24.2, downloaded and checksummed, run under
CI's exact arguments: 1 error and exit 2 before, 0 errors and exit 0 after.

**Landed.** Merged into main as `4b3b040` (PR 5, a merge commit over four commits: the fix, two
empty commits correcting an earlier message, and three stubs) after three fresh rounds returning
0C/0H/2M/0L/0N, 0C/0H/0M/1L/0N, 0C/0H/0M/0L/0N.

**The verdict read to its end**, which is the part that matters: push-to-main run 34348433466
completed `success`; job "Merge - static gates, supply chain and links" `success`; step 32
"Relative links resolve" `success`. The first `success` push-to-main run since 2026-09-03.

**Its worktree is removed**, on Tier 0's explicit instruction and against the brief's standing
"leave your worktrees" rule. `git worktree remove /tmp/suborch-jobvite-link`, `test -e` reports
absent, and `git worktree list` no longer lists it.

**The standing hazard piece 0 surfaced** is board row 39 and is NOT fixed by this work: branch
protection requires only the `test` job, and the merge-tier job reports SKIPPED on real pull
requests (measured live through `gh api .../branches/main/protection` and
`gh pr view --json statusCheckRollup`). A red step in that job cannot be seen before a merge. That
is why the trunk stayed red for six days, and it is a CI design decision, not mine to take.

## PIECE 1 - board row 19, PREAMBLE.md

Branch `docs/preamble-protocol`, worktree `/tmp/suborch-jobvite-preamble`, head `f1463e8`, nine
commits, 121 insertions and 11 deletions across ten files, seven of which are the one-line review
stubs the last commit carries. Pushed by Tier 0 after round 7 as pull request 6 on
`evolvconsulting/fast-mcp-jobvite` from head `f1463e8`, and MERGED as `417cbb6` at
2026-09-09 03:57 PM CDT, the required check `Gate - lint, types, tests` having finished with
conclusion `success` (Actions run 34403690690).

Every change is a REWRITE IN PLACE. Nothing was appended as a correction under stale text, and no
paragraph now says one thing and contradicts it lower down.

**The paragraph the brief told me to leave alone is unchanged.** "Work you find outside your scope
is REPORTED - never a silent fix and never a silent drop", and its provenance note, are byte for
byte as they were; the `TaskCreate` sentence waits on NEEDS-PHIL item 32.

### The sentences, before and after

**1. The delivery rule's opening claim.**

    before:  Two channels, both required. Your final Agent-tool output does NOT reach me.
    after:   Two channels, both required. Your final Agent-tool output does NOT reach whoever
             dispatched you.

"me" was written by a super-orchestrator for its own briefs and is false for every nested agent.

**2. Who to message.**

    before:  2. **`SendMessage` with `to: "team-lead"`.**
    after:   2. **`SendMessage` to the agent that dispatched you.** A sub-orchestrator answers the
             super-orchestrator, `to: "team-lead"`; a worker or a reviewer answers its own parent,
             by that agent's name, and its brief names it.

**3. The exception, which is the substance of this amendment.** New:

    **THE EXCEPTION, and it is a population rather than an edge case.** Both rules above are
    written for a NAMED teammate. **Below Tier 1 there are no named teammates**
    (`PROTOCOL-super-orchestrators.md` section 5, K-0099 correcting K-0079, canon on 2026-09-09),
    so a reviewer dispatched by a sub-orchestrator is a NESTED, UNNAMED subagent, and its final
    Agent-tool output IS returned to whoever spawned it rather than vanishing. **That returned
    output plus the report FILE are your deliverable.** `SendMessage` may ALSO reach your parent -
    measured arriving, addressed by name in the `to` field and surfacing at the parent tagged by
    the sender's agent id (`PROTOCOL-super-orchestrators.md` section 5, J-0138, and K-0105
    correcting K-0099) - so treat it as a second copy and never as the only one.

**4. The self-referential warning**, which I would not have written if a reviewer had not caught
me, and which round 4 then caught again. New, in its final form:

    > **A WARNING ABOUT THIS PARAGRAPH'S OWN HISTORY, because it is the failure it now guards
    > against.** An earlier version of these lines said flatly that `SendMessage` "cannot reach
    > that parent at all". That was INFERRED from a refusal to SPAWN a named teammate ("Teammates
    > cannot spawn other teammates - the team roster is flat"), which says nothing about message
    > delivery, and it was never tested: its author had written "do NOT call SendMessage" into all
    > six of its reviewer briefs, so no attempt was ever made and no evidence could arrive. A
    > sibling lane then measured the opposite. **A brief that forbids the thing in question
    > destroys the evidence for it** (`PROTOCOL-super-orchestrators.md` section 6, J-0139 and
    > K-0105, which state the rule in those words and name this task as where it was learned), and
    > a citation added to an untested sentence makes it better-sourced rather than true.
    >
    > **This sentence was itself uncited until review round 4**, thirteen minutes after the
    > protocol draft carrying the citation had landed. That is the THIRD uncited claim in this one
    > paragraph: round 2 found the original, round 3 found its replacement, round 4 found the
    > lesson drawn from both. A paragraph about unevidenced assertions is exactly where the next
    > one goes unnoticed, so read this one twice.

**5. The default when the brief does not say.** New: deliver by BOTH, because asking is not
available to a population whose channel is the thing in doubt; the `ToolSearch` at the top of the
file is a self-diagnostic that answers it without asking (`No matching deferred tools found` means
nested, the task tools mean named teammate); and record in the file which population you believe
you were.

**6. Where each kind of document lives**, the PROTOCOL's ruling (K-0074, adopted 2026-09-08) made
concrete. Three bullets: the per-task BRIEF is `consensus/<OWNER>-brief-<name>.md` under evolv and
`docs/briefs/` keeps canon only; a REVIEW round's prose is `reviews/REVIEW-<subject>-R<n>.md` under
evolv and what lands here is one stub; a WORKLOG still lands in `docs/worklogs/` on the branch with
a copy under evolv. That third bullet is what the PROTOCOL explicitly left for this amendment to
settle (section 5, K-0060 condition 2), and **the settlement is that it does not move.**

**7. The worklog pair rule, which I got wrong twice and Tier 0 corrected once.**

    **THE TWO NAMES ARE NOT DERIVED FROM EACH OTHER, so your brief gives you BOTH paths and this
    file cannot give you a rule for the second.** Your worklog is `docs/worklogs/<TASK>-report.md`
    here; what the operations repository holds is THE REPORT YOUR BRIEF NAMES, normally
    `consensus/<OWNER>-report-<task>.md` - the same content under the brief's name, not a sibling
    under the worklog's. Worked pair, checked byte for byte:
    `docs/worklogs/JOBVITE-BUMP-403-report.md` and `consensus/JACK-report-jobvite-fastmcp-403.md`.
    **IF YOUR BRIEF NAMES ONLY ONE OF THE TWO, REPORT THE GAP RATHER THAN INVENTING THE OTHER
    NAME.** ... **A worklog written by the super-orchestrator working inside the repository has no
    operations copy and this rule does not ask for one**; `docs/worklogs/REPOINT-403-report.md` is
    that case, which is why looking for its twin finds nothing.

My first version named a "pair" whose halves had different names and one of which had no
counterpart at all. My first correction was also wrong. Tier 0 ruled the third version, correcting
MY correction: the copy is the same content under the brief's name, and `REPOINT-403-report.md` is
the Tier-0 case needing no copy.

**8. The stub rules, read out of `check-review-coverage.py` itself** rather than paraphrased.
Three rules, each with the constant that enforces it: the stem must match `REVIEW.*-R<n>`
(`IS_REVIEW`); it must not end in `REVIEW` and must not begin `PLAN-REVIEW` (`NOT_A_COMMIT_REVIEW`);
one declaration per file, a second refused at exit 2. **Break one and the stub is not a defect, it
is INVISIBLE** - the checker skips the file and the round leaves no trace. I tested the
duplicate-declaration refusal live rather than reading it.

**9. Two operational rules the rounds forced in.** Cut the worktree with `git worktree add` against
the product repository, never with a harness's `isolation: "worktree"` option, which cuts from the
SESSION's outer repository (`PROTOCOL-super-orchestrators.md` section 5). And "Remove your worktree
when done" became "**Remove your worktree when done, and say so** - unless your brief keeps it for
me to read", because this brief does exactly that.

**10. The population with no board.** New, near the `ToolSearch` at the top: a nested agent gets
`No matching deferred tools found`, that is a fact about where it sits rather than a broken tool,
and with no task id it claims nothing.

**11. THE DURABILITY THE RULE PROMISED AND NOBODY PROVIDED**, round 4's second Medium and the most
uncomfortable finding on this branch. Bullet 1 said "Your report, committed on your branch" flatly,
to a population including nested reviewers who have no branch and are told elsewhere in the same
file that review prose does not land in this repository at all. Measured:

    all seven reviews/REVIEW-jobvite-*.md files from this task are UNTRACKED in the operations
    repository: `git status --porcelain` reports `??` for every one, and `git log` reports zero
    commits touching any of them.

Four review rounds on this branch and three on the sibling, written, delivered, read, and every one
a single `rm -rf` from gone. That is the 48KB failure the bullet exists to prevent, one repository
over, and the bullet's own wording is what hid it: a rule saying the reports are committed reads as
though they are. The bullet now says which population it addresses, says a reviewer's prose lives
under evolv with its stub committed by whoever dispatched the round, and states the measurement.
**It does NOT invent a rule that reviewers commit their own reports**: reviewers do not commit, by
every brief on this task, and who carries that obligation is not mine to assign. Tier 0 has taken
that gap as his to close and is routing the rule to KING.

### Piece 1's commits

    780b639  docs: amend PREAMBLE to the adopted super-orchestrator protocol      +44/-8, 1 file
    1e42618  docs: fold review round 1 on the PREAMBLE amendment                  +22/-5, 3 files
    5c65731  docs: fold review round 2, and withdraw a sentence I never tested    +35/-9, 3 files
    17293c9  docs: fold review round 3, and cite the sentence that replaced an uncited one  +19/-11
    ffc9f2d  docs: cite the lesson, and stop promising a durability nobody provides  +22/-2, 1 file
    d8ac954  docs: stop the file narrating itself, and cite each source for its own share  +21/-25
    030b2b9  docs: drop a count that reproduces under no reading, and name the committer  +4/-4
    89ba708  docs: correct a SHA in the previous commit's message; no file changes    empty, 0 files
    f1463e8  docs: the review stubs for rounds 1 to 7, the last commit before the push  +7, 7 files

### TIER 0'S FOUR RULINGS ON THE PASSAGES, in their committed form

His principle: **a canon file says what to do and why; its own editing history belongs in the
report, the commit messages and the notebooks.** Two passages narrated this branch's rounds and both
are gone; the phrase "review round 4" now appears nowhere in the file, and the file is SHORTER, 322
lines to 318, which is the right direction for that ruling.

1. **The blockquote about the paragraph's own history GOES**, and the third-uncited-claim count with
   it. The lesson survives in J-0139, K-0105, this report and `5c65731`'s message.
2. **One clause of reason stays, attached to a rule that can be acted on.** I added the route,
   because "report the prohibition to whoever dispatched you" is unactionable for a population that
   may have no message channel, which is the exact defect rounds 1 and 2 both found in this file:
   "Report the prohibition IN YOUR RETURNED OUTPUT to whoever dispatched you, which is the one route
   no brief can take away, and deliver by the file as well."
3. **The citation names only what each source holds** (round 5's LOW 4). K-0105's own subject is the
   TEMPLATE lane's measurement; it does not contain the sentence and mentions jobvite once as an
   open question. Committed: "(section 6 and J-0139, which state the rule in those words; K-0105 is
   the sibling lane's measurement that first exposed the gap)". Tier 0 preferred the smallest
   citation and accepted this one over his own preference, on the ground that the sibling lane
   measuring the opposite is why the rule exists.
4. **The untracked-reports measurement becomes a rule with a dated past measurement** (round 5's
   LOW 1), because its present tense had become false: draft 13 assigned the obligation in section 7
   and the seven files were committed the same day. No draft number and no line range, both of which
   decay.

Plus the stub-commit rule PREAMBLE lacked entirely, in section 7's general form, with `b6afce2` as
a worked example in this repository, verified to resolve and to list two one-line files and nothing
else BEFORE it was cited.

## PIECE 2 - board rows 23 and 29, the citation checker

Branch `fix/citation-controls-population`, worktree `/tmp/suborch-jobvite-citations`, head
`7e4b4be`, nine commits, two files, 452 insertions and 39 deletions.

### Row 23: the controls arm can now see its own corpus

Two new controls, taking the arm from 3 to 5, and the verdict line reshaped by Tier 0's later
ruling:

    CONTROL an inserted line shifts the map -> FIRED
    CONTROL a changed line maps to None -> FIRED
    CONTROL the pattern reads both forms -> FIRED
    CONTROL the corpus is enumerated (557 files, all 3 named members present) -> FIRED
    CONTROL an amputated enumeration is REFUSED by both arms -> FIRED

    5 fired, 0 not fired, 0 could not run, of 5 controls.
    rc=0

**The positive arm** runs the real `_tracked_files()` result and requires three NAMED members: this
checker itself, `docs/DESIGN.md` and `pyproject.toml`.

**My first version of it was blind and a reviewer proved it.** It required every suffix in
`_SEARCH_SUFFIXES` to be represented - derived from the very declaration a narrowing mutation
shrinks, so it shrank along with the mutation and still read 5/5 at rc=0. **A control derived from
the thing under test cannot fail with it.** Named members do not have that property.

**The negative arm** is what row 23 actually asks for. It requires BOTH scan arms to print
`EMPTY_CORPUS`:

    SELECTOR CONTROL: no DESIGN.md citations found anywhere. The pattern is broken, not the corpus.

With the enumeration amputated at source the arm reports itself and the count drops, and the
`--since` arm which used to print `0 citation(s) moved` at rc=0 now prints `EMPTY_CORPUS` at rc=1.
That is the fail-open closed on both arms.

**What the control does NOT reach, stated in the file rather than implied.** It proves the
enumeration RUNS and REACHES three named members; it does not BOUND the corpus. Measured (round 2,
reproduced by round 4): widening `_SKIP_PARTS` to exclude five of this repository's own RECORD
directories takes the corpus from 557 files to 347 and the citations from 2101 to 1561, a quarter
gone, while the arm still prints 5 of 5 at exit 0. **No floor is added for it, deliberately**: a
count here would be a second copy of a number that moves with every commit, which is the decay this
repository has paid for repeatedly. Bounding the corpus is a different property and wants its own
instrument. Round 4 concurred with disclosing rather than flooring it.

### THE SAME SCREW, FOUR TIMES, and every turn was found by a reviewer rather than by me

This is the carryable part of piece 2, so it is stated as a sequence rather than a list of fixes.

1. **Round 1's guard wrapped ONE call site**, the positive control arm's `_tracked_files()`.
2. **Round 2 found the two scan arms and the negative arm still crashed** with `git` ABSENT from
   PATH - not shimmed to fail, which is what I had measured - raising a bare `FileNotFoundError` at
   exit 1. **A guard at the self-test call site and not at the real ones is the exact defect this
   branch exists to remove, committed by its own fix.** `44bbfb0` added a `git --version` probe.
3. **Round 3 found that probe proves the BINARY LAUNCHES and nothing about the CALL.** With a git
   whose `ls-files` fails and whose other subcommands work, both scan arms raised a bare
   `CalledProcessError` at exit 1 again. Reproduced three ways, one with no stub at all: against
   the real `/usr/bin/git` under `GIT_DIR=/nonexistent-git-dir`, `git --version` exits 0 and
   `git ls-files -z` exits 128, and the default arm (the one `ci.yml` wires) died at
   `subprocess.CalledProcessError: Command '['git', 'ls-files', '-z']' returned non-zero exit
   status 128.` with rc=1. `b7c619c` ran the actual enumeration once in `main` and threaded it.
4. **Tier 0 then ruled the other half**, measured on the template's copy at `634ef4b`: converting
   only the ABSENT case left the RAN-AND-FAILED case crashing. `7755e8e` routed every git call
   through one `_git` wrapper raising one exception type, and deleted the two things that made
   unreachable: the `(OSError, subprocess.CalledProcessError)` tuple, and `_stderr_of`, a helper
   the previous commit had added one commit earlier.
5. **Round 4 found three more, and TWO OF THE THREE ARE NOT GIT AT ALL** - which is why I missed
   them, having searched along the axis the previous rounds happened to run down.

### Round 4's three, each reproduced by me before folding

**M1, a third mode in the wrapper I had just written.** `_git` passes `text=True`, so
`subprocess.run` decodes, so git emitting non-UTF-8 raises `UnicodeDecodeError` - neither `OSError`
nor `CalledProcessError`, straight past a guard naming those two. The docstring one line above said
"Two modes, one exit code" and was wrong about the code beneath it. Stub git exiting 0 with
`\xff\xfe` on `ls-files`:

    before:  UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 0: invalid start byte
             rc=1
    after:   REFUSED: the tracked-file enumeration could not run, so nothing can be scanned:
             git ls-files -z ran but its output is not UTF-8: 'utf-8' codec can't decode byte 0xff
             in position 0: invalid start byte
             rc=3

**M2, and the likeliest of the three to happen for real.** `repoint_exempt.RegisterError` is caught
nowhere in this file, though the message it raises with literally says "That is a BROKEN
INSTRUMENT". The code said the right thing and exited the wrong way. `REPOINT-EXEMPT.txt` is plain
text, hand-edited as ordinary exemption work. Moving it aside: rc=1 with a bare traceback before,
rc=3 naming the cause after.

**M3, a tracked file gone from disk.** `citations()`'s per-file read caught `UnicodeDecodeError`
and not `OSError`, so a plain `mv` of a real tracked file with the index untouched crashed with
`FileNotFoundError` at rc=1. rc=3 after, naming the path.

### The fix closes the class, and Tier 0 ruled it stands

I have now enumerated dependency exception types three times - `(OSError, CalledProcessError)`,
then `GitError` - and **each enumeration missed one**, because a list of types is a claim about
what can go wrong and I have been wrong about that at every round. A fourth list would be the same
mistake, longer.

So `main` became `_dispatch`, and the new `main` catches anything that escapes, names its type,
prints the traceback to stderr unabridged, and returns 3. **It cannot be incomplete because it
names no types.**

I flagged the trade to Tier 0 rather than settling it myself: a blanket `except Exception` means a
genuine logic bug now reports as a broken instrument rather than crashing loudly. **He ruled it
stands**, on the ground that a checker's exit codes are a contract - 1 a finding about the tree, 2
a refusal, 3 a broken instrument - so a logic bug escaping must report as 3 with its type named and
its traceback printed, because exit 1 there would be a FALSE STATEMENT ABOUT THE TREE, which is
worse than a quiet crash. It is a floor under the specific guards, the file says so, and M1 keeps
its own named refusal above it.

### The guards, and two rulings that shaped them

`main` establishes its preconditions before any arm runs, all at exit 3, this checker's existing
"BROKEN INSTRUMENT, not a finding" code:

    REFUSED: docs/DESIGN.md could not be read, so no control can run: <the OSError>
    REFUSED: docs/DESIGN.md could not be read, so nothing was scanned: <the OSError>
    REFUSED: the tracked-file enumeration could not run, so nothing can be scanned: <the cause>

Tier 0 ruled the DESIGN.md guard into the broken-instrument shape at exit 3 rather than a per-arm
control, then accepted my departure from the letter of it, putting it at the top of `main` as a
`try`/`except` on the read. The wording "could not be read" with the OSError, rather than "is
missing", is his ruling on a point I raised against my own text: the file can be present and
unreadable.

**Nine git runs, three arms by three failure shapes, every one rc=3 with zero traceback lines:**

    git absent (PATH REPLACED, only python3 reachable)   default rc=3  --controls rc=3  --since rc=3
    git ls-files exits 128 (real git otherwise)          default rc=3  --controls rc=3  --since rc=3
    git emits non-UTF8 on ls-files                       default rc=3  --controls rc=3  --since rc=3

**That framing overstates arm-independence and round 4 was right to say so:** `main` refuses before
dispatch, so the nine runs happened but are not nine independent observations of the guard.

### NOT RUN, and Tier 0 correcting his own ruling

He had let a missing precondition report a fraction at rc=1. rc=1 is this checker's code for a
control that RAN and did not fire; an arm whose precondition is missing did not run, and reporting
it as a failed control said the opposite of what happened while printing a fraction that read as an
arm which had answered.

The rule: an arm that cannot run is reported NOT RUN with its reason, the count prints the three
outcomes separately, and the run exits 3. Only an arm that ran and did not fire yields rc=1.
Re-planted, with `docs/DESIGN-FREEZE.txt` moved aside:

    before:  CONTROL an amputated enumeration is REFUSED by both arms -> DID NOT FIRE
             (DESIGN-FREEZE.txt is missing, so --since has no sha: ...)
             4/5 controls fired.
             rc=1

    after:   CONTROL an amputated enumeration is REFUSED by both arms -> NOT RUN
             (DESIGN-FREEZE.txt could not be read, so --since has no sha: [Errno 2] No such file
             or directory: '/tmp/suborch-jobvite-citations/docs/DESIGN-FREEZE.txt')
             4 fired, 0 not fired, 1 could not run, of 5 controls.
             rc=3

Round 4 then found the same distinction one level down (its LOW): the negative control's own
`git show` precondition was still counted DID NOT FIRE while its `DESIGN-FREEZE.txt` sibling, fixed
one commit earlier by the same ruling, was counted NOT RUN. Now NOT RUN with its reason.

### Row 29: the docstring sentence

`repoint-design-citations.py`'s `already_moved_from()` documented the field-COUNT check (round 4's
F13 on the earlier PR) and not the field-CONTENT check the same function gained (round 5's F15).
Added:

    A row whose blob field is not a 40-character blob id is refused
    the same way (review round 5, F15).

### Piece 2's commits

    0d6f930  fix: the citation checker's controls arm can now see its own corpus          +83/-5
    f5a1171  docs: already_moved_from's docstring documents the field-content check too    +2/-0
    c1a246b  fix: guard every read the controls arm depends on, and read argv by position +126/-28
    d009b24  fix: the controls refusal says "could not be read", not "is missing"          +4/-1
    44bbfb0  fix: guard git itself, and read DESIGN.md once instead of three times         +52/-12
    b7c619c  fix: guard the enumeration itself, not a proxy for it                        +109/-69
    7755e8e  fix: one _git wrapper, and NOT RUN stops wearing a finding's exit code        +87/-36
    3cb6af0  fix: close the class, because enumerating its members has failed three times  +60/-2
    7e4b4be  fix: a control that scans the real corpus, which no control did               +43/-0

### THE SIXTH CONTROL, and the false green it closes

Tier 0's round 5 found that NO control ever called `citations(tracked)` with the real list.
Control 4 checked MEMBERSHIP in the list `_dispatch` built; control 5 passed `[]`. `citations()` is
the only path to `repoint_exempt.is_exempt` and to the per-file read, so round 4's register and
vanished-file defects were STRUCTURALLY UNREACHABLE from `--controls`. Reproduced in one tree with
`docs/reviews/REPOINT-EXEMPT.txt` moved aside:

    --controls : 5 fired, 0 not fired, 0 could not run, of 5 controls.   rc=0
    default    : This is a BROKEN INSTRUMENT, not a finding. Exit 3.     rc=3

**That is board row 23's original defect one turn deeper: the arm had been hardened to reach the
ENUMERATION and still never reached the SCAN.** After the sixth control, four plants:

    intact                    6 fired, 0 not fired, 0 could not run, of 6 controls.  rc=0
    REPOINT-EXEMPT.txt aside  5 fired, 0 not fired, 1 could not run, of 6 controls.  rc=3
    a tracked file off disk   5 fired, 0 not fired, 1 could not run, of 6 controls.  rc=3
    DESIGN-FREEZE.txt aside   5 fired, 0 not fired, 1 could not run, of 6 controls.  rc=3

**ONE DEPARTURE FROM THE DICTATED SHAPE, and Tier 0 accepted it as right rather than tolerated.**
He specified the control report FIRED with the counts it saw. Written literally, a scan returning
ZERO citations from a non-empty corpus prints FIRED, which is a green on a broken selector: the
fail-open this branch exists to close, rebuilt inside the control that closes it. An empty result is
therefore DID NOT FIRE at rc=1, which is what both scan arms already say about an empty corpus. I
proved that branch reachable by amputation rather than asserting it, with a pattern that keeps both
capture groups and matches nothing:

    CONTROL the real corpus scans end to end -> DID NOT FIRE (0 citations across 557 files; the
    selector is broken, not the corpus)
    4 fired, 2 not fired, 0 could not run, of 6 controls.
    rc=1

**I DECLINED TO CLAIM THE SIXTH CONTROL ADDS A SIGNAL THE OTHERS DO NOT**, because under that
mutation control 3 also fails and I had not enumerated the cases where it would not. Round 6
settled it with a third mutation I did not build: the exemption forced to always hold. Controls 1
to 5 all FIRED and only the sixth caught it. The signal is not redundant, and the round rather than
its author established that.

## WHAT DID NOT CONVERGE, AND WHAT CHANGED WHEN IT DID

**Piece 2's finding rate did not fall**: 0C/0H/2M/0L/2N, then 0C/0H/2M/1L/0N, then 0C/0H/1M/1L/1N,
then 0C/0H/3M/1L/2N. Four fresh rounds, and the last was the largest. Piece 1's did not fall
either: 0C/1H/1M/1L/2N, 0C/0H/3M/2L/1N, 0C/0H/2M/2L/2N, 0C/0H/2M/0L/0N.

**Every round also refuted at least one confident claim of mine**, and on piece 2 the refuted claim
was usually the previous fix's own summary of itself. `7755e8e` said "there is no second,
independently-failing call left to guard" and "this is not a fourth version of the same
near-miss"; round 4 falsified both within the hour.

**Tier 0's ruling on that, which is the right diagnosis:** the instrument is not converging under
briefs written by the same author. Four rounds of mine each carried my shape list, which is built
from what I had already been shown, so each round was steered toward the axis of the last defect
and away from the next one. Round 4's two non-git MEDIUMs were found by the one line in its brief
that told it to look at dependencies OTHER than git - the only instruction I wrote that was not
derived from a defect I had already seen.

He therefore runs his own fresh round on both branches with his own brief and his own shape list,
and neither branch's stub commit is landed until they return. **This report is written before
those rounds and does not predict them.**

**The one thing that is different about `3cb6af0`:** it is the first change on this branch that
closes a CLASS instead of an instance, so it is the first fix whose correctness does not depend on
my having correctly predicted the failure modes - the exact thing I had been wrong about four
times. That was an argument for it, not evidence about it. The evidence came from Tier 0's rounds.

**WHAT ACTUALLY BROKE THE PATTERN.** Rounds 5 and 6 were briefed by Tier 0, and round 5 found on
each branch a defect four rounds of mine had not: on piece 2, that no control ever called the real
scan; on piece 1, four claims of my own that did not hold. Round 6 on piece 2 then returned nothing
at any severity. The variable that changed was not the effort or the number of rounds; it was who
wrote the shape list.

**AND THE ROUND SETTLED A QUESTION ITS AUTHOR COULD NOT.** I declined to claim the sixth control
adds a signal control 3 does not, because I had not enumerated the cases. Round 6 built a third
mutation I had not thought of - the exemption forced always to hold - and controls 1 to 5 all FIRED
while only the sixth caught it. Declining to claim it was right; the claim is now true and measured,
and neither half of that could have come from me.

## MY OWN INSTRUMENT ERRORS, every one caught and corrected

Listed because Tier 0 asked for them as a set, and because they are one family.

1. **A brief that could only return one value.** I asserted `SendMessage` "cannot reach that parent
   at all" from a refusal to SPAWN a named teammate, then wrote "do NOT call SendMessage" into all
   six of my reviewer briefs, so no attempt could be made and no evidence could arrive. Tier 0
   asked whether it was MEASURED or INFERRED; the answer was INFERRED. **I manufactured the absence
   I then cited.** This is K-0105 and PROTOCOL section 6's J-0139.
2. **A probe that left the real dependency reachable, the same shape.** Re-measuring the git-absent
   case I wrote `PATH="$stub:$PATH"` where the probe needs `PATH="$stub"`, so real git stayed on
   the path and all three arms returned their INTACT codes. Re-run with PATH replaced, all three
   are rc=3. **An instrument that can only return one value returns it**, and this one read exactly
   like the fix having broken.
3. **A wrong non-zero from a bad path.** My first run of the anchors check used
   `docs/reviews/check-harness-anchors.py` and returned rc=2. That was `python3` failing to open a
   file that does not exist; the checker is at `scripts/`. At the real path it is rc=0 and prints
   `OK: all 464 anchors resolve in their target file ... (floor 464)`.
4. **Four assertions wrong about a file that was RIGHT, one shape.** Three searched the whole file
   for a pattern and matched the COMMENT documenting that pattern: the `_tracked_files()` call
   count said four where the code has one; the "no bare git call" check fired on `_git`'s own two
   lines; the "no dead `CalledProcessError`" check fired on the comment explaining its removal. The
   fourth guessed a rename count of six where the file had five and refused to edit. **A grep for a
   defect pattern always finds the paragraph explaining the defect.**
5. **Read-back assertions quoting the sentence in my head rather than the file**, three times: new
   text legitimately contains its own anchor when the edit appends to it; an 8-space-indented line
   contains the 4-space string as a substring; and a phrase my own new text wraps across a line
   break is not contiguous in the file.
6. **An empty PATH measuring the shell.** My first probe of the git-absent case used an empty PATH,
   where `rc=127` was the shell failing to find `python3`, not the checker refusing.
7. **A replay that straddled an edit.** I started a Gate replay and then changed one comment line
   while it ran. That replay was DISCARDED, not reported; the reported one ran on a tree whose
   sha256 I recorded before and verified after.
8. **A replay killed for system memory**, which produced no output at all. I verified the file's
   sha256 unchanged and `git status` showing only my intended modification, then re-ran clean. Only
   the re-run is reported.
9. **Three lint errors in my own new text** (N818 wanting an `Error` suffix, D107 a missing
   `__init__` docstring, W505 a 74-column summary line), caught by the Gate before the commit
   rather than after it.
10. **A stale number inside one branch.** A brief of mine quoted "git failing 3/5 rc=1" that my own
    earlier fold had already turned into a clean rc=3. **A number copied forward from a previous
    round is a cache**, and this one decayed in hours.
11. **A PHANTOM LINE COUNT, four times over.** I reported PREAMBLE.md as 323 lines when it is 322.
    `wc -l`, `git show | wc -l` and `splitlines()` all say 322; only `split("\n")` says 323, because
    a file ending in a newline yields an empty final element. A method error, not a typo: the same
    counter would have been wrong on every file. The edit script now subtracts it and every count
    is cross-checked against `wc -l` before a message states it.
12. **A PATTERN-SHAPED SWEEP REPORTING ITS OWN SILENCE AS A PROPERTY.** I claimed the amended file
    "cites no protocol line numbers anywhere" after grepping for three shapes I had in mind. The
    shape actually present, `file.md:NN`, matched none of them. The correct claim is "no line
    number into `PROTOCOL-super-orchestrators.md`": `:40` carries one into the older
    `PROTOCOL-sub-orchestrators.md`, untouched by this branch and resolving today.
13. **A MUTATION THAT COULD NOT REACH THE BRANCH IT AIMED AT.** Proving the sixth control's empty
    path, my first amputation used a pattern with NO capture groups, so `citations()` raised
    IndexError and exercised the NOT RUN path instead. A mutation must leave the code able to reach
    the branch under test. Round 6 confirmed the wrong-instrument diagnosis independently.
14. **A LINE CITATION THAT WAS NEVER RIGHT, beside one that decayed while being corrected.** I cited
    PROTOCOL section 6's sentence at ":258-262", read off an unnumbered `sed` window rather than a
    numbered read. It has NEVER been at :258: :259 at bf55860 and deb6158, :261 at 8745bb9, :262 at
    66f9e87. Round 5's own correction, ":259-263", was right against the draft its brief pinned and
    stale within hours. **Three correct-at-the-time answers in eight hours is why the amended file
    cites sections and ledger entries and no line numbers into that document at all.**
15. **A brief sending a reviewer to the wrong place.** I told round 3 to hunt a "wrong `14 moved`"
    claim among the five commit messages, "where every one of the four lived". It is not there:
    `git log -S"14 moved" cc42576..HEAD` returns nothing, and the string is in no commit message,
    no tracked file at any commit, and no edit script. That error was caught in a working draft and
    never landed. The reviewer reported the absence rather than manufacturing a match, and both
    later rounds re-derived the negative independently.
16. **An off-by-one diffstat.** My brief gave `b7c619c` as +109/-70; `git show --numstat` says
    +109/-69.
17. **A CITATION COPIED OUT OF A MESSAGE AND NEVER RESOLVED, inside the very commit that
    folded a decayed record.** Folding round 6 I carried a SHA out of the super-orchestrator's
    ruling into `030b2b9`'s message: "b0a06d2 committed fourteen REVIEW-jobvite-*.md files".
    `b0a06d2` resolves to nothing; the commit is `b0a02d6`. He caught his own transposition two
    minutes later, after my commit was already written. The three figures that sentence carries I
    DID re-derive (fourteen at that commit, four of them preamble, eighteen now, all exact);
    **the citation attached to them I did not.** A figure and its citation are two claims and I
    checked one of them. Remedied by `89ba708`, an empty commit whose message corrects the SHA and
    names the origin, because `030b2b9` cannot be amended without rewriting a commit a round had
    already been dispatched over.

18. **A COLUMN LIMIT IMPORTED FROM THE WRONG FILE, and an assertion that ran after its own
    write.** The script that added entry 17 asserted a 101-column maximum, which is
    `PREAMBLE.md`'s convention and not this document's: the report's own tables run to 153
    columns, so it failed on NINE PRE-EXISTING lines it had never touched. **The check ran after
    `write_text`, so its failure did not prevent the change.** I read the file's real state back
    rather than assuming a failed assertion meant a rolled-back edit; the renumbering and entry 17
    had both landed correctly, and my new text was 98 columns and never in question. A limit is a
    property of the file it came from, and a check placed after the write reports on damage rather
    than preventing it.

19. **A COUNT STATED ABOUT A MESSAGE I HAD WRITTEN MINUTES EARLIER.** Reporting the SHA
    correction, I told the super-orchestrator that `89ba708`'s message "quotes the string
    `b0a06d2` once". It occurs THREE times, at lines 10, 12 and 45: the quoted erratum, the
    sentence stating that it resolves to nothing, and the closing list of what was checked.
    **He caught it; I did not.** The figure carries no consequence, which is exactly why it is
    worth listing: it is the same instrument that produced "seven" and that left the SHA itself
    unresolved, turned on a message of my own composition inside the very report of the earlier
    failure. Re-derived here by `grep -o | wc -l`, not by eye.

## HOW THE EDITS WERE MADE

Every edit on both branches was applied by a script that asserts each anchor occurs EXACTLY ONCE
before substituting and reads the file back afterwards. The scripts are at
`/tmp/claude-1000/-home-plafayette-claude-projects-evolv/cb8018da-df03-4fe5-9a62-5b884124cfb6/scratchpad/`:
`edit-preamble.py`, `fold-preamble-r1.py`, `fold-preamble-r2.py`, `fold-preamble-r4.py`,
`edit-citations.py`, `fold-citations-guards.py`, `fold-citations-r2.py`, `fold-citations-r3.py`,
`fold-citations-jack.py`, `fold-citations-r4.py`. **They are NOT committed to either repository**,
which is what made an earlier claim about them unverifiable to two reviewers; the paths above are
the remedy and discharge round 3's LOW 2. `ruff format` was run over
`check-design-citations.py` as its own step after the last fold, so its committed text is the
formatter's rather than the script's verbatim output.

`ruff`'s `W505` caps doc lines at 72 columns and applies to COMMENTS as well as docstrings. My
hand-written comments broke it 15 times on one fold and 20 on the next. The fix was mechanical:
`_reflow_long_comments()` rewraps every comment paragraph holding an over-length line and then
asserts none remains. Docstrings are outside its reach and were corrected by hand.

## THE REPLAY TABLE

The verdict is the tool's own `REPLAY` line, never a wrapper's exit code.

| tree | verdict | note |
|---|---|---|
| `cc42576` (baseline) | `REPLAY test: 31 run-steps replayed, 4 uses-steps not replayed, exit 0` | 31/31 rc=0 |
| preamble replays 1-6 | `... exit 0` each | 31/31 rc=0 each, one per commit plus a final |
| citations replay 1 | `... 3 run-steps replayed ... exit 1` | **STEP 6/35 Lint: rc=1**, W505 comment lines, caught before the commit |
| citations replay 2 | `... 6 run-steps replayed ... exit 1` | **STEP 9/35 Default suite: rc=1**, the KNOWN limiter flake |
| citations replays 3-8, 10, 12, 13 | `... exit 0` each | 31/31 rc=0 each |
| citations replay 9 | `... exit 0` | **DISCARDED**: straddled a one-line edit |
| citations replay 11 | none | **KILLED by the system for low memory**, no output produced |
| link (piece 0) x2 | `... exit 0` | 31/31 rc=0 |

**Both results of the flake, reported and not argued.** Citations replay 2 failed at
`tests/test_http_hardening.py::test_a_malformed_inbound_request_id_is_replaced[wrong-version]` with
`Rate limit exceeded for client: aa502ab6c0e58a5e`, `1 failed, 888 passed, 6 deselected in 65.70s`.
Re-run of that file alone: `32 passed in 3.65s`, rc=0. The next full replay of the same tree:
31/31 rc=0. That test is one of the three arms in `test_http_hardening.py` that board rows 12 and
22 already name; it is not a new one.

**One test WAS new and is now in row 22.** The preamble branch's round 2 flaked
`tests/test_tools_candidates.py::test_the_candidate_id_reaches_the_wire_as_a_query_parameter`,
which is not in `test_http_hardening.py` at all - the fifth distinct test to show this flake, and
the first outside that file. Clean on a single-test re-run.

I did not touch the limiter, its tests, or `INBOUND_BURST_CAPACITY`.

## THE REVIEW ROUNDS

A FRESH sonnet agent per round, each in its own detached worktree at my head, each removing it
afterwards and saying so. Briefs at `consensus/SUBORCH-FOLLOWUPS-brief-review-*.md`. Prose reports
at `reviews/REVIEW-jobvite-*.md`.

    piece 0   0C/0H/2M/0L/0N   0C/0H/0M/1L/0N   0C/0H/0M/0L/0N
    piece 1   0C/1H/1M/1L/2N   0C/0H/3M/2L/1N   0C/0H/2M/2L/2N   0C/0H/2M/0L/0N
              0C/0H/0M/4L/0N   0C/0H/0M/2L/2N   0C/0H/0M/0L/1N
    piece 2   0C/0H/2M/0L/2N   0C/0H/2M/1L/0N   0C/0H/1M/1L/1N   0C/0H/3M/1L/2N
              0C/0H/1M/0L/0N   0C/0H/0M/0L/0N

Rounds 1 to 4 on each branch were briefed by me. Every round from the fifth on was Tier 0's, briefed
by him. The first clean round either branch has had is piece 2's round 6, and it is the first round
on this task that no brief of mine shaped; piece 1 reached nothing-above-Nit one round later, at its
round 7.

Piece 1 exceeded its three-round budget and Tier 0 extended it by one. Piece 2 likewise, and Tier 0
granted its fourth after I reported round 3 and asked rather than spending it. **I dispatched no
round without a budget for it.** Piece 1 then took three further rounds under Tier 0's own briefs
and piece 2 two, with piece 2's seventh still to run when this was written.

### THE SENDMESSAGE MEASUREMENTS

The instrument this task was wrong about, now fired five times. Three payloads I hold verbatim:

    {"success":true,"message":"Message sent to suborch-jobvite-followups's inbox",
     "msg_id":"bdcdd456-d65d-43aa-bcb2-59b295154314",
     "routing":{"sender":"ac5abc41759a9551e", ... "target":"@suborch-jobvite-followups", ...}}

    {"success":true,"message":"Message sent to suborch-jobvite-followups's inbox",
     "msg_id":"ea2c34a8-ce1d-4776-a0ab-ae62ed84980e",
     "routing":{"sender":"a59e9cf48cdf9a00b", ... "target":"@suborch-jobvite-followups", ...}}

    {"success":true,"message":"Message sent to suborch-jobvite-followups's inbox",
     "msg_id":"a035dc5f-b0f6-4d9b-8211-32e55222293e",
     "routing":{"sender":"a2829b50159a1dccb", ... "target":"@suborch-jobvite-followups", ...}}

Two earlier ones (`review-jobvite-link-r3` and `review-jobvite-preamble-r3`) arrived at my end as
teammate messages; J-0141 carries the first, and the second is recorded as an independent
replication rather than a repeat. **Every one: `success: true`, addressed by NAME in the `to` field,
surfacing at the parent tagged by the sender's raw agent id.** That is exactly the mechanism
PREAMBLE now describes and exactly what six of my briefs had forbidden anyone from testing.

## CROSS-LANE ITEMS I REPORTED RATHER THAN FIXED

1. **A sibling brief carries the inverted claim.** `SUBORCH-brief-review-template-carried-R1.md`
   lines 133-134 tells its reviewer to `SendMessage` while also saying "Text you emit in your own
   session reaches nobody" - backwards for a nested agent, whose emitted output is exactly what
   returns. Reported to Tier 0; not mine to edit.
2. **Board row 39**, the merge-only static-gates steps invisible on pull requests, filed by Tier 0
   after piece 0 measured it.
3. **The untracked review reports** (piece 1's M2 above). Tier 0 has taken it as his to close and
   is routing the rule for who commits them to KING.

## WHAT I DID NOT DO

I did not merge, push, rebase, stash, or touch any tree that is not mine. I did not check anything
out in the shared checkout. I did not edit `docs/DESIGN.md` or `docs/DESIGN-FREEZE.txt`, touch the
limiter or its tests, wire or unwire a gate, or edit board rows 19, 23 or 29. I appended no
attribution trailer to any commit. Pieces 1 and 2 are still on `cc42576` and were not rebased onto
`4b3b040`. Both worktrees are kept, as instructed, with clean trees.

## THE HORIZON OF THIS COPY

This copy was cut on 2026-09-09 from consensus/JACK-report-jobvite-followups.md. PIECE 1 WAS
FINISHED by then: its stub-only commit `f1463e8`, its pull request, and the merge `417cbb6` at
03:57 PM CDT all precede this sentence and are described above. What lands AFTER it, and is
recorded in the operations repository rather than here: piece 2's stub-only commit, its pull
request and its merge, and the commit that carries this copy.

**EVERY CLAIM ABOUT PIECE 1 ABOVE NAMES A TERMINAL STATE**, a merge SHA or a finished run, never
an open pull request or a running check. That is deliberate and it was learned here: three
sentences in this report were made false between being drafted and being sent, by the very events
they described, twice inside five minutes. A terminal state cannot decay. An in-flight one decays
while you are writing about it.

## WHAT I DID NOT VERIFY

- **The JOB AND STEP detail of piece 1's Actions run.** I read run 34403690690 only as far as its
  status and conclusion (`completed`, `success`, on head `f1463e8`), from the API and not from its
  job and step list. Tier 0 reads each merge's push-to-main run to its end (K-0091), and that
  reading is recorded in the operations repository, not here. Piece 2 is unpushed, has no pull
  request and has no Actions run at all. Every Gate figure quoted in this report for pieces 1 and
  2 comes from the local replayer and hand-copied `run:` blocks, never from the real runner.
- **Tier 0's round 7 on piece 2**, which had not run when this was written. Nothing here predicts
  it, and piece 2's stub-only commit waits on it.
- **That the `--controls` arms stay unwired.** I established they are wired nowhere today. I did
  not test what happens if someone wires the negative arm into CI, where its synthetic empty corpus
  runs in the same process as the real scan.
- **Whether the corpus SHOULD be bounded.** I measured that the new control does not bound it and
  recorded the gap in the file. Whether a bounding instrument is worth building is a decision I did
  not take.
- **Whether the backstop hides a class of real bug in practice.** Tier 0 ruled the trade; I did not
  measure how often a logic error would now surface as exit 3 rather than a crash, because no such
  error is known to exist in this file today.
- **The limiter flake's actual historical cause.** Row 22's mechanism is a positive control on the
  real class, not a confirmation of what happened on any specific run. I re-ran and moved on, as
  instructed.
- **The fifteen TIER-1 standards I did not read**, listed above with my reason.
