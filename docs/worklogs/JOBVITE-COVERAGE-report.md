# JOBVITE COVERAGE BACKLOG - report from suborch-jobvite-followups

Tier-1 sub-orchestrator, re-dispatched by JACK under `PROTOCOL-super-orchestrators.md` (draft 22 at
evolv `9837c03`), section 5's re-dispatch path. Brief:
`consensus/JACK-brief-jobvite-coverage.md`. Board row 55. Repository `repos/fast-mcp-jobvite`, base
`main` at `b38b3cc`, branch `docs/coverage-backlog`, worktree `/tmp/suborch-jobvite-coverage`.

ONE COMMIT: `66147ee`, one file, 186 insertions, nothing else.

## POINTERS THAT LEAVE THIS REPOSITORY

**A READER WHO HAS ONLY `fast-mcp-jobvite` CANNOT RESOLVE MUCH OF WHAT THIS REPORT CITES.** Said once
here rather than at each use. Everything in this list lives somewhere else:

- `PROTOCOL-super-orchestrators.md` and the K- and J- ledger ids quoted from it: the operations
  repository's root. The ids are text inside that document, not files of their own.
- `consensus/...` briefs and reports, and `reviews/REVIEW-*.md` review prose: the operations
  repository. This repository has its own `docs/reviews/`, a different directory holding checkers.
- `ccd5609`, `937631c` and `b0a02d6` resolve only in the operations repository. `git cat-file -t`
  fails on all three here.
- `/tmp/suborch-jobvite-coverage` and `/tmp/review-jobvite-coverage-r1`: this machine, this session,
  and the second already removed.
- "board row N": a live task board outside git entirely, not a file in any repository.

Every other SHA this report names is a commit in this repository.

## THE INSTRUMENT AND WHY IT WAS RED

`docs/reviews/check-review-coverage.py` compares the SET of trunk commits no review round covers
against the set recorded in `docs/reviews/review-coverage-backlog.txt`, and exits 1 when they differ.
It is a RATCHET, not a permit: a recorded line says "known, unread and accounted for", never
"exempt". It is wired into neither repository's CI, so it gates nothing and a required check passing
says nothing about it.

The checker is designed to lag by one merge and says so: a commit cannot record its own sha, so a
merge's commits are recorded by the NEXT change. Whoever opens the next pull request pastes the lines
it printed for the merges before it. This task was that next pull request.

## THE MEASUREMENT, BEFORE ANY EDIT

`uv run --frozen python docs/reviews/check-review-coverage.py`, in the worktree at `b38b3cc`:

    Trunk ref: origin/main = b38b3cc
    Review documents in the population: 52
    Excluded, with a reason: 64
    Trunk commits on origin/main since 8695101: 668
      Fully covered - range AND every path:                     437
      PARTIALLY covered - some files claimed by nobody:          23
      COVERED BY NOTHING:                                       208
      Record-file touches skipped:                               55
      Nothing to read (clean merge, or RECORD paths only):      152
    Backlog recorded in review-coverage-backlog.txt:  66
    Backlog measured now:                            231
    ENTERED, unrecorded:                             165
    CLEARED, still recorded:                           0
    CHANGED KIND:                                      0
    SUBJECT disagrees with the commit:                 0
    rc=1

165 lines to record, 153 NONE and 12 PARTIAL. The kind split was counted by matching " NONE " and
" PARTIAL " in the captured block and cross-checked against the checker's own ENTERED total. Every
one of the 165 resolves with `git cat-file -t`. Forty-four stubs are DECLARED, in ten families:
REVIEW-R10 to R22 and R14-R1, PREAMBLE R1 to R7, CITATIONS R1 to R8, 403 R1 to R6, LINK R1 to R3,
218 R1 to R2, and one each of 231B, 151, 144-145 and CODE-REVIEW-R9.

## THE RECONCILIATION, AND A CORRECTION TO THE BRIEF

**THE BRIEF SAID PULL REQUESTS 5, 6 AND 7 "EACH ADDED COMMITS THE FILE DOES NOT RECORD". That is
true and it accounts for THREE of the 165.** Every line was classified by ancestry rather than by
assumption, with `git merge-base --is-ancestor <sha> cc42576` run for each:

    reachable from cc42576, so predating all three pull requests   162
    landed after cc42576                                             3
    sha does not resolve                                             0

and the three are exactly:

    5cd314e   NONE   docs: the three review stubs for this branch's rounds    pull request 5, merged 4b3b040
    f1463e8   NONE   docs: the review stubs for rounds 1 to 7                 pull request 6, merged 417cbb6
    98589f6   NONE   docs: the review stubs for rounds 1 to 8                 pull request 7, merged b38b3cc

**THE RECONCILIATION VINDICATES THE STUB PROTOCOL RATHER THAN FINDING A HOLE IN IT.** Every
branch-side commit of all three merges was walked:

    pull request 5    4 commits:  1 content, 2 empty, 1 stub commit
    pull request 6    9 commits:  7 content, 1 empty, 1 stub commit
    pull request 7   12 commits: 11 content, 0 empty, 1 stub commit

In each case the ONLY commit that enters the backlog is the stub commit. Every CONTENT commit is
covered by its own round's stub and appears nowhere in the recorded set. The empty commits
(`4626b2d`, `d92ea43`, `89ba708`) touch no files and are skipped as nothing to read. The three merge
commits are skipped for the same reason: a clean merge's `--cc` diff is empty.

That is not an oversight. A stub commit is by construction the one commit no round reads
(`PROTOCOL-super-orchestrators.md` section 7, K-0088 ruling 1), and no commit can declare its own
sha. The one-merge lag the checker documents is exactly this.

**SO THE TOP-UP IS 3 LINES OF RECENT WORK AND 162 OF AN OLDER GAP** outstanding since before
`cc42576`, the base both merged branches were cut from. That older gap is what made the checker exit
1, and it is why it also exited 1 at `cc42576` before this task began. Board row 55's own text said
the red predates both branches; the measurement confirms it and puts a number on it.

## SIX OF THE RECORDED LINES ARE MERGE COMMITS

Neither the brief nor the board row names this, and a reader who assumes a merge never enters this
file would read it as a defect:

    13d4020   2dbb0e5   354c811   3eeef83   a27527c   df8c60f

Each carries merge-unique content, so in the checker's own words an "EVIL merge has merge-unique
files, so `--cc` prints them, `substantive` is non-empty, and it is scored below like anything
else". A clean merge prints nothing and is skipped; these six do not. Counted twice by different
methods, `--merges` and a parent count from `rev-list --parents`, six both ways. They are named in
the commit message and in the file's own dated note for that reason.

## THE AUDIT OF ALL 231

Round 1's own "not settled" list says it did not re-audit the pre-existing 66 lines. That audit was
then run over the whole file, all 231 recorded shas:

    resolve with git cat-file -e <sha>^{commit}       231 of 231
    are commits rather than tags or trees            231 of 231
    non-resolving                                      0
    non-commit                                         0

This matters for round 1's finding below: it makes that finding LATENT in this tree rather than live.

## WHAT WAS RECORDED, AND HOW

The 165 lines are the checker's own printed output, pasted verbatim with the leading indent removed
to match the file's format. **THE FORMAT WAS CHECKED BEFORE PASTING, NOT AFTER.** The checker prints
`subject[:56]`, while the file's older entries run to 78 characters, so the comparison was read
first: the checker's test is that the commit's real subject `startswith` the recorded one, so a
56-character subject is a valid prefix and both widths pass. Had that been an equality test, 165
lines would have landed as 165 SUBJECT disagreements. "The tool prints what to paste" is exactly the
kind of claim that deserves one command.

The lines are preceded by a dated block in the file's own style, because the file's header requires
that a line ARRIVES only in a commit whose message says why the backlog grew, and the next reader of
the file will not have the commit message in front of them. That block carries the same three facts:
the three stub commits and why they are NONE by construction, the 162 older lines, and the six
merges.

Nothing else changed: no checker edit, no wiring, no `ci.yml`. The file went from 138 lines to 324,
and from 66 recorded entries to 231.

## THE MEASUREMENT, AFTER

Same command, same tree:

    Trunk ref: origin/main = b38b3cc
    Backlog recorded in review-coverage-backlog.txt: 231
    Backlog measured now:                            231
    ENTERED, unrecorded:                               0
    CLEARED, still recorded:                           0
    CHANGED KIND:                                      0
    SUBJECT disagrees with the commit:                 0
    rc=0
    "The backlog holds at 231, every commit recorded."

The checker prints its own caveat on every path and it is repeated here rather than paraphrased: a
holding ratchet is not full coverage. It says the unread set did not grow and nothing in it went
unnoticed. It does NOT say anyone has read those 231 commits.

## THE SELF-REFERENCE QUESTION, SETTLED BY THE ROUND AND NOT BY ME

Round 1's brief carried one instruction derived from no finding on this branch, because a shape list
built from what its author has been shown steers a round toward the last defect and away from the
next (`PROTOCOL-super-orchestrators.md` section 7; K-0116). That instruction was: DOES THIS COMMIT
RE-ENTER THE BACKLOG?

`66147ee` touches `review-coverage-backlog.txt` and nothing else. The checker's own RECORD note says
that file is exempted precisely because leaving it out once made the ratchet FEED ITSELF, four
commits of pure self-reference where each top-up recorded the one before it. `66147ee` is that exact
shape. **I did not test it before the round, deliberately, and I say so because the alternative is a
round that confirms what its author already knew.**

Round 1 measured it directly with `--ref HEAD`: `66147ee` joins the trunk set, the nothing-to-read
count moves from 152 to 153 with that +1 being `66147ee` itself as a record-only commit, the backlog
holds at 231 = 231, exit 0. It does not become the 166th line. The exemption works on this shape, and
nobody had tested it on this shape before.

## ROUND 1

One FRESH sonnet-class agent, its own detached worktree at `/tmp/review-jobvite-coverage-r1`, removed
by it afterwards. Brief at `consensus/SUBORCH-COVERAGE-brief-review-coverage-R1.md`, prose at
`reviews/REVIEW-jobvite-coverage-R1.md`, both in the operations repository; the prose is 335 lines
and is committed there at `ccd5609`.

    VERDICT   0C / 0H / 0M / 1L / 0N

All seven of the commit's claims were re-derived independently, by swapping `--backlog` against a
scratch copy of the pre-commit baseline rather than trusting the commit message's own printed
numbers, and all seven held exactly.

**L1 (LOW): a recorded sha that does not resolve is not refused.** `read_backlog` validates KIND
membership and duplicate shas, both of which exit 3, but never validates that a recorded sha resolves
to a git object. Reproduced independently by me, both arms, against COPIES via `--backlog` so the
tracked file was never touched and its sha256 was identical before and after:

    a line with its KIND removed        rc=3   "A malformed line is a broken instrument"
    a line whose sha does not resolve   rc=1   CLEARED  <sha> NONE ... - delete this line
                                               and, in the same output, ENTERED, unrecorded: 1
                                               naming the real commit it displaced

The header promises a malformed line exits 3, and for a missing KIND it does. For an unresolvable sha
it does not: the line folds into CLEARED and reads exactly like a legitimate clearance. LOW is the
right severity because soundness holds: the displaced real commit resurfaces as its own ENTERED row
in the same run, so the standard "paste ENTERED, delete CLEARED" remedy still lands. What is lost is
diagnostic clarity, not detection.

**IT WAS NOT FOLDED, AND THAT WAS TIER 0'S RULING, NOT MY CHOICE.** The brief says to fold a Low on an
ordinary commit; the only fix is inside the checker, and the same brief forbids a checker edit twice,
at its lines 49 and 75. I reported that conflict rather than resolving it by picking the instruction
I preferred. Tier 0 ruled that L1 is a pre-existing property of an instrument this branch was scoped
not to touch, found BESIDE the commit rather than in it, that `66147ee` introduces no unresolvable
line, and that K-0088's fold rule is for findings in the branch. L1 is board row 66, with the
suggested fix recorded there: resolve every recorded sha in `read_backlog`, batched through
`git cat-file --batch-check`, exit 3 with a distinct message. It lands in each repository's own
git-handling change, not here. The prohibition was not lifted.

Round 1 also confirmed clean: the KIND-missing refusal matches the header's promise verbatim; one
pull request 7 content commit (`0d6f930`) is absent from the backlog because `REVIEW-CITATIONS-R1.md`
deliberately covers it (`cc42576..f5a1171`), not by accident; and both of the file's claims about
itself, that no tool writes it and that it records a set rather than a count, are true against the
code as it stands.

## MY OWN INSTRUMENT ERRORS

**None on this task, and that is a claim rather than an absence of looking.** The one place this task
could have produced the shape it has produced repeatedly elsewhere was the paste: assuming the
checker's printed lines were paste-ready because the checker printed them. That assumption was
checked against the comparison in the code before 165 lines were written, and it held. The previous
lane's report carries twenty entries in this section; this one carries none, and the difference is
that this task had one moving part rather than a branch of them.

## WHAT I DID NOT VERIFY

- **Any GitHub Actions run for this branch.** It is unpushed with no pull request. No CI has seen it.
- **That the 231 recorded commits are individually classified correctly** as NONE against PARTIAL. I
  recorded the checker's own classification of each; I did not independently re-derive the kind of
  each of the 165, and the checker's own caveat says a declaration is a claim by its author.
- **The pre-existing 66 lines beyond resolvability.** They resolve and they are commits; I did not
  re-audit their kinds or subjects.
- **Whether any of the 208 COVERED BY NOTHING commits should have been covered** by a round that
  exists. That is a question about historical review coverage, not about this file.
- **The checker under any flag except the default and `--backlog`.** `--since` and the other arms
  were not exercised.
- **Round 2.** It had not run when this was written.

## WHAT I DID NOT DO

I did not merge, push, rebase, stash, or touch any tree that is not mine. I did not edit the checker
or `ci.yml`, and did not wire anything. I did not edit board rows 33 or 55's subject. I did not touch
`/tmp/suborch-tpl-*` or `/tmp/review-tpl-*`, which belong to another repository's live lanes. I
appended no attribution trailer to any commit. The branch is not rebased onto anything.

## THE HORIZON

This copy was cut on 2026-09-09 from `consensus/JACK-report-jobvite-coverage.md`. What had already
happened when it was written, named by terminal states only:

    the record        66147ee, one file, 186 insertions, checker rc=1 to rc=0 at b38b3cc
    round 1           0C/0H/0M/1L/0N, prose committed in the operations repository at ccd5609
    the ruling on L1  tracked as board row 66, not folded here, the prohibition unlifted

Round 2 had NOT RUN when this was written, and neither had the stub-only commit, the push, the pull
request or its merge. Those land after this moment and are recorded in the operations repository,
not here.

**EVERY CLAIM ABOUT A FINISHED THING ABOVE NAMES A TERMINAL STATE**, a commit or an exit code, never
an open pull request or a running check. The sentence about round 2 is dated to the writing instead,
which is the other way a sentence survives: it fixes itself to a moment rather than to a state that
moves. The previous lane's report learned that distinction the expensive way, by having three of its
sentences falsified between drafting and sending.
