# REPOINT-403: the citations ADR-0036's DESIGN.md amendment moved, repointed

Author: JACK (Tier 0 of the fast-mcp lane), 2026-09-08, on branch `chore/fastmcp-4.0.3`.
Notebook: evolv `consensus/JACK.md` J-0083 (the correction) and J-0084 (the rulings).
Found by review round 2 of this branch (`consensus/JACK-review-jobvite-403-R2.md`, F6 and F7).

## What happened

`f608850` amended `docs/DESIGN.md` section 10 for ADR-0036 and added ten lines (hunks at 1485,
1490, 1499 and 1518; 2134 lines before, 2144 after). The repository's procedure after a design
edit is `check-design-citations.py --since <sha>` followed by `repoint-design-citations.py`, and
I did not run it. The Gate's citation step checks only that a cited line EXISTS, which is why every
replay and both review rounds passed it; its own NOTE in `ci.yml` says it cannot see this class.

Separately, `3c2a79b` added ten lines to `docs/research/FASTMCP.md` above line 100, and my later
commit `58d1195` claimed in its message that the three line-number citations into that file
"still point where they did" because its own edit was net-zero. That was false: the citations
were already ten lines stale, and the three citing lines are not touched anywhere on the branch.

## Measured before anything was changed

```
python3 docs/reviews/check-design-citations.py --since a9a85ed
  MOVED lines:  232
  BROKEN lines:  23     (targets whose content changed: the amended section itself)
python3 docs/reviews/repoint-design-citations.py a9a85ed
  refused: 136 citation(s) live in a directory NOBODY HAS RULED on
git show a9a85ed:docs/research/FASTMCP.md | grep -n ...
  "your-client-secret" at 357, "secret-key" at 587, the mirror sentence at 845 (on main)
  now at 367, 597 and 855; .pre-commit-config.yaml:59 cited 354 and 584 (stale by three on
  main already; .secrets.baseline's line_number fields say 357 and 587), mirror.yml:69 cited 845
```

## The rulings (J-0084), written into `docs/reviews/repoint-design-citations.py`

The tool refuses to repoint a directory nobody has ruled on, and its author deliberately left
`docs/reviews`, `docs/worklogs` and `docs/briefs` unruled rather than rule them from their names.
Ruled after reading what sits there:

| path | ruling | why |
|---|---|---|
| `docs/worklogs/`, `docs/archive/` | RECORD | reports of work at a time; their citations are evidence of what was read then |
| `docs/briefs/` | RECORD | the briefs that dispatched that work |
| `docs/briefs/PREAMBLE.md` | LIVE | the live working rule; the longest matching prefix now wins, so this file ruling holds under the directory ruling |
| `pyproject.toml`, `.pre-commit-config.yaml` | LIVE | the manifest and the hook configuration as they are |
| `docs/reviews/*.py`, `docs/reviews/*.sh` | LIVE | instruments that run against the current tree; their own example citations carry `REPOINT-EXEMPT` and are skipped |
| `docs/reviews/*.md`, `docs/reviews/*.txt` | RECORD | reviews, rulings, audits, evidence files |

Everything else stays UNRULED and refused, as before.

## What the tool did

```
python3 docs/reviews/repoint-design-citations.py a9a85ed            (dry run: 0 UNRULED)
python3 docs/reviews/repoint-design-citations.py a9a85ed --write
  69 citation(s) repointed across 27 file(s)
  163 citation(s) in RECORD paths are NOT repointed (14 docs/adr/, 85 docs/reviews/*.md,
  33 docs/worklogs/, 25 docs/plans/, 4 docs/briefs/, 2 docs/archive/; the tool's print
  string said "in docs/adr/" at the time, false as worded, fixed after round 3)
```

Files the tool changed: `.github/workflows/ci.yml`, `.pre-commit-config.yaml`,
`docs/reviews/check-checkers-are-wired.py`, `docs/reviews/probe-218-frame-census.py`,
`scripts/check-committed-file-types.py`, `scripts/check-u0-test-controls.sh`,
`scripts/check-u9-http-controls.sh`, `scripts/check_advisories.py`, seven modules under
`src/fast_mcp_jobvite/`, twelve files under `tests/`, and `pyproject.toml`. Every change is a
`DESIGN.md:N` or `DESIGN.md:N-M` string moved by the amount the amendment shifted its subject.

## Repointed by hand, because the target's content changed

| site | was | now | note |
|---|---|---|---|
| `pyproject.toml:10-11` | `1497-1506`, "at `fastmcp==4.0.0b4` plus an explicit `fastmcp-slim==4.0.0b4`" | `1505-1513`, the block as it is (`fastmcp==4.0.3`, `mcp==2.1.1`) with the beta named as history | round 2's F7 |
| `pyproject.toml:23` | `1486-1488` | `1487-1490` | the `mcp` reason moved two lines down |
| `tests/test_manifest.py:6` | `1485-1488` | `1485-1490` | the sentence grew by two lines |
| `tests/test_manifest.py:71` | `1499-1501`, "states three pins" | `1507-1508`, "states two pins; the block held three until ADR-0036 removed the second" | the block has two pins now |
| `tests/test_manifest.py:114`, `:154`, `:189` | `1518-1520` | `1525-1530` | the prerelease paragraph was rewritten for the GA pin |
| `.pre-commit-config.yaml:59` | FASTMCP.md `354` and `584` | `367` and `597` | round 2's F6 |
| `.github/workflows/mirror.yml:69` | FASTMCP.md `845` | `855` | round 2's F6 |

The seventeen BROKEN sites in records (ADR-0020, ADR-0036, four worklogs, one archived worklog,
REVIEW-R14) stay as written: they cite the design as it was when they were written, and ADR-0036
says so in its own text ("frozen at d1f1a52"). Two live sites, `pyproject.toml:23` and
`tests/test_manifest.py:6`, still read BROKEN under `--since a9a85ed` after the hand repoint,
by construction: the checker compares the cited lines' content against the old design by line
number, and these now cite lines whose content the amendment rewrote. A future `--since` run
against a base at or after this commit reads them clean.

## Verified afterwards

```
python3 docs/reviews/check-design-citations.py                      rc=0
python3 docs/reviews/check-design-citation-shape.py                 rc=0
python3 scripts/check-harness-anchors.py --self-check --floor 464   rc=0  (all 464 anchors resolve)
python3 docs/reviews/check-design-citations.py --since a9a85ed      MOVED 236 (163 records, left; 73 LIVE citations the batch
                                                                    had already moved, which a run from the OLD base re-reports
                                                                    as moves to wrong targets, so that base is refused now),
                                                                    BROKEN 19 (17 records, 2 by construction)
uv run --frozen ruff check .                                        rc=0
uv run --frozen ruff format --check .                               rc=0
```

The whole `test` job is replayed over the committed tree before the branch is pushed, and the
replayer's own verdict line is quoted in the commit's notebook entry.

## Corrected after review round 3 (`consensus/JACK-review-jobvite-403-R3.md`)

- F8 (High): the machine batch moved four keys of `docs/reviews/probe-218-frame-census.py`'s
  `ADJUDICATED` dict (`1846`, `1846`, `1848`, `1549-1564`). Those keys are the plan's citations
  as written at blob `c15b138`, matched by exact lookup against `docs/plans/IMPLEMENTATION-PLAN.md`,
  a RECORD that keeps the old values; moved, the four lookups went silent. Reverted, each line
  marked `REPOINT-EXEMPT` as its `:353` sibling already was, and three register rows added (the
  two `1846` keys share one). The tool is not idempotent against the base it has already moved
  from: a second `--since a9a85ed --write` would have moved every LIVE citation again (73 of
  them). `docs/reviews/REPOINT-LOG.txt` now records each write's base and DESIGN.md blob, and
  the tool refuses a base whose blob it has already moved from. Measured: `a9a85ed` refused;
  `3ba2a3d` (the current design) not refused, nothing to move.
- F9 (Medium): "163 citations in docs/adr/" was the tool's hardcoded print string, written when
  docs/adr/ and docs/plans/ were the only RECORD prefixes; 14 of the 163 are docs/adr/. The
  string and this worklog now say RECORD paths.
- F10 (High): a second instance of the dropped one-module rule, `docs/research/FASTMCP.md`'s
  section "The httpx to httpx2 decision", still titled "(open)", is rewritten to name ADR-0007
  and point at design rule 3.
- F11 (Nit): the dropped-rule quote sits in ADR-0007's Consequences, not its Decision; the
  commit that fixed rule 3 and the notebook said Decision.
- F12 (Low): the hand-repoint table above cited `tests/test_manifest.py:113`, `:153`, `:188`;
  the earlier hand edit in that file had shifted them to 114, 154, 189. Corrected.

## Not done here

- Records are not repointed and their BROKEN citations are not rewritten; that is the ruling, not
  an omission.
- No `CITATION-REPOINT-MAP.md`-style subject-by-subject map was written for the 69 machine
  moves: every one is a pure shift of a citation whose subject the checker found unchanged, which
  is the case that map exists to argue against applying a constant offset to. The seven hand
  repoints above are the only judgement calls, and each names its subject.
