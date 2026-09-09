# Task #157 — the mirror job's per-job minute rounding

<!--
NO `REVIEW-COVERS` LINE, for WORKLOG-143's reason: these commits have
not been reviewed, and declaring coverage here would manufacture it.
-->

Branch `fix/157-mirror-minutes`, worktree `fmj-worktrees/w157`, cut
from `main` at `ccbdaae`.

**The findings, the measurement, the gate exit codes and the
corrections to my brief are in
[`docs/reviews/REPORT-157-mirror-minutes.md`](../../reviews/REPORT-157-mirror-minutes.md),
and they are there ONCE.** This file deliberately does not restate
them. Two copies of one measurement is the defect `PREAMBLE.md` opens
with — *"a retyped constant decays"* — and a worklog that paraphrases
its own report is the cheapest way to produce a second, wronger copy.

## The one-line version

The mirror ran on every push, billed **213 minutes over 213 billed
runs** in `2026-08-28..2026-09-02` for **10.9 minutes** of runner time,
and **0 of those 213 runs executed the step that copies anything** —
`MIRROR_TOKEN` does not exist. It now runs daily, plus on tag pushes,
plus on demand: **~31 min a month against ~1300**. The mirror itself is
current regardless (20 refs, identical SHAs on both remotes), because
`origin` carries two push URLs.

## Commits

    4aca097  Mirror on a daily schedule, not on every push
    a3fc38f  Correct my own header: the currency check would NOT
             have caught R3-H1
    (this commit)  the report and this worklog

## Housekeeping

`.github/workflows/ci.yml` (`suborch-161`) and
`scripts/check-u1-boot-amputation.sh` (`suborch-156`) were read but not
written. No push, no merge, no remote or credential changed, no
workflow disabled, re-enabled or re-run.
