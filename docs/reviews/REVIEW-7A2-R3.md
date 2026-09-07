# REVIEW-7A2-R3 - fresh adversarial round on `REVAMP-238-ci.md` §7a.2

Reviewer: fresh, had not seen R7A2 rounds 1 or 2. Target `6f89364`, file
`docs/reviews/REVAMP-238-ci.md` lines 438-642. Everything below was recomputed
from the three run payloads (`33630968540`, `33614887374`, `33629034552`) and
from the tree at `6f89364`, never from the section's own prose.

**3 High, 6 Medium, 5 Low, 4 Nit.**

The section's single most load-bearing claim - *at 12 lanes sharding is a
REGRESSION* - is CORRECT and survives every perturbation I could construct.
The defects are in the corroboration around it.

---

## What I reproduced, and it holds

| claim | verdict |
|---|---|
| `step_ci(k) = scale*(B + (R+overhead)/k)` reproduces all four cells | **YES** - 303.97 / 163.32 / 298.06 / 219.53 |
| 33 steps, 3311s, largest 298s from run 33630968540 under the stated rule | **YES**, exactly |
| 12 `harness-*` keys at `ci.yml:1649`-`:2132`, 16 job keys total | **YES** (`awk` over the `jobs:` block: 16 keys, 12 harness) |
| fixed jobs 161 / 62 / 52 / 19s, none binding | **YES**, from the payload |
| `13 = 271 - 258` on the U3 amputation lane | **YES** |
| unsharded floor 311s at EVERY lane count | **YES**, verified k=12..33; fixed side never binds |
| 323 / 294 / 277 / 245 / 240 sharded | **YES**, reproduced to the second - but see M2 |
| queue 3-5s; runs A,B share 16 names, 5 with C | **YES** (3s / 4s / 4s; 16, 5, 5) |
| 888 tests; U3 rows 10.6:1; U9 47%->64% baseline at k=2 | **YES** |
| covdb option's 78s shard + 141s map job | **YES**, both derive from the published model |
| self-confession: overhead column deleted by the first rewrite | **TRUE** (`e108bc6` dropped it, `733979a` had it) |
| self-confession: "packed all 44 packable steps" | **TRUE** (`e108bc6`: 44 steps, 3719s) |
| self-confession: pooled gaps 55/159/91 | **TRUE** (`733979a`) |
| self-confession: "376/304/304, only the THIRD was wrong" | **TRUE** - actual per-run largest is 376 / 304 / **298** |

### The regression claim is robust (attack item 4)

I perturbed it four ways. The 12-lane sign never flips:

| perturbation | unsharded | sharded | delta |
|---|---|---|---|
| as published | 311 | 323 | **+12** |
| overhead = 0 | 311 | 324 | **+13** |
| overhead x0.5 | 311 | 323 | **+12** |
| overhead x2 | 311 | 323 | **+12** |
| setup 6s / 8s / 15s / 20s | 304/306/313/318 | 316/318/325/330 | **+12 each** |
| U3 re-anchored on this run's 258s (M2) | 311 | 318 | **+7** |
| 3-run MEDIAN population (n=34, 3446s) | 317 | 340 | **+23** |

The setup constant cancels exactly - it is added to both columns - so the 13s
figure, which the section correctly flags as one delta from one job, cannot
affect the regression sign or the crossing lane at all. That is worth saying in
the section, because §7a.2 currently calls 13s "load-bearing" without noting it
is load-bearing only for the ABSOLUTE 311, never for the comparison the
recommendation rests on.

---

## HIGH

### H1. The "unreconciled" 1.814x-vs-1.567x disagreement reconciles exactly, from numbers in this same section

`:609-611` says the gap "is NOT reconciled. Both are one ratio of two noisy
numbers over the same harness, and nobody has established which run pair each
used."

Both use the same run pair and the same numerator. `MEASURED-268:125` states
its own derivation literally: `304/167.6 = 1.814x`. And `167.6 = B + R =
14.47 + 153.11`. This section's 1.567 is `304 / (B + R + overhead) =
304 / 193.98 = 1.5673`. The only difference is whether the 26.4s overhead sits
in the denominator - a definitional choice this section introduced when it
restored the overhead column, not an empirical disagreement.

Declaring it unreconciled, and inventing "nobody has established which run
pair", is a false open item in a section whose whole purpose is to be
refittable.

**Fix.** Replace `:609-611` with: "`MEASURED-268:125` derives 1.814x as
`304/167.6`, i.e. `304/(B+R)`. This section derives 1.567x as
`304/(B+R+overhead)` = `304/193.98`. Same run pair, same numerator; the two
differ only in whether the 26.4s overhead is inside the base. Reconciled - and
1.567x is the one consistent with the model above, which divides `R+overhead`."

### H2. "Three independent computations now agree on 14 lanes" - it is one computation, and 14 lanes is insensitive to the thing being corroborated

`:602-607`. Three problems.

1. **Not independent.** `MEASURED-268:402-407` disclaims its own 276s in its
   "did NOT verify" section: *"U9's shard cost modelled on U3's local
   baseline/row split (#259) because I did not measure U9's own baseline ...
   this figure is soft in a direction that matters, and it should be re-derived
   from U9's own numbers before anything is dispatched on it."* That is exactly
   the U3-shaped model this section demolishes at `:484-486`. The section cites
   as corroboration a number produced by the model it just refuted.
2. **14 lanes cannot corroborate the shard arithmetic, because it is
   packing-bound.** I recomputed the 14-lane figure with the U9 shard cost set
   to 209s, 219.5s, 235s and 78.5s. Every one gives 277s on the single run and
   276s on the medians. The agreement at 14 lanes is evidence about the
   PACKING, and says nothing whatever about U9's baseline split.
3. **No third computation is named.** Two documents are cited; the third is
   asserted.

Separately, "the older document was correct and the newer one drifted away from
it before drifting back" reads as a virtue-signal about a number that neither
document has actually earned.

**Fix.** Replace with: "`MEASURED-268:140` publishes 276s at 14 lanes and this
section computes 277s. That is agreement about PACKING, not about the shard
model: at 14 lanes the wall is set by the residual step mix, and I get
276-277s with U9's shard cost set anywhere from 78s to 235s. `MEASURED-268:402`
disclaims its own 276s as modelled on U3's ratio - the model §7a.2 refutes - so
it is not an independent confirmation of the arithmetic here, only of the lane
count."

### H3. "The option that would change the picture" does not change the picture, by the section's own model

`:613-626` presents covdb hoisting as the lever that would alter the
conclusion. I substituted its own published numbers (U9 -> two 78.5s shards
plus a 141s map job) into its own LPT, same population, same 13s setup:

| lanes | sharded, as published | covdb hoisted |
|---|---|---|
| 12 | 323 (regression) | 308 (still no margin) |
| 13 | 294 | 293 |
| **14 (the target)** | **277** | **275** |
| 16 | 245 | 240 |
| 18 | 240 | 240 |

**Two seconds at the stated target.** Past 12 lanes the wall stops being
U9-bound - which is the section's own finding - so making U9 cheaper buys
almost nothing. The heading asserts the opposite, and it is the kind of heading
someone builds against.

Note this is not an argument against hoisting; it is an argument that the
stated payoff is misdescribed. Hoisting would matter if U9 were then sharded
past k=2, which the section does not say.

**Fix.** Retitle to "### The covdb option, which buys less than it looks like"
and add the recomputed row: "Substituted into the table above it gives
12/13/14/16 = 308/293/275/240 - about 2s at the 14-lane target, because past 12
lanes the wall is packing-bound rather than U9-bound. It is worth building only
as a precondition for sharding U9 past k=2, not for the k=2 plan here."

---

## MEDIUM

### M1. `R/(B+R)` contradicts the model printed eight lines below it, and the cut percentages beside it

`:447` says "the payoff is governed by `R/(B+R)`" and the table prints 0.91 /
0.42. But `:457` divides `(R + overhead)` by `k`, so the divisible fraction is
`(R+overhead)/(B+R+overhead)` = **0.925** (U3) and **0.527** (U9).

The section's own k=2 cuts prove it: 46.3% and 26.3% are exactly half of
0.925 and 0.527. Half of 0.91 and 0.42 would be 45.7% and 21.2%. The ratio
column is inconsistent with every other number on its own row - and it
understates U9's shardability by 10 points, which is the direction that matters
for the section's thesis.

**Fix.** Relabel the column `(R+ovh)/(B+R+ovh)` with 0.93 / 0.53, and change
`:446-447` to "the payoff is governed by the divisible fraction
`(R+overhead)/(B+R+overhead)`; `R/(B+R)` is the intuition and is 1-10 points
lower."

### M2. The sharded column mixes a step measured in one run with a shard model anchored on another

`:520` scopes the whole table to run 33630968540, and `:564-567` defends the
single-run choice at length. But in that run `U3 audit amputation` measured
**258s**, not the 304s the shard table uses. 304s is U3-amputation's MEDIAN,
drawn in run 33629034552 (`:589-591` says so itself). The sharded column
replaces the 258s step with `2 x 163 = 326s`, silently injecting 68s of U3 work
this run never did.

This is how I know: 323/294/277/245/240 reproduces to the second ONLY under
that substitution. Re-anchoring U3's shard model on this run's own 258s (same
formula, `scale = 258/193.98`) gives:

| lanes | published | re-anchored |
|---|---|---|
| 12 | 323 | **318** |
| 13 | 294 | **288** |
| 14 | 277 | 277 |
| 16 | 245 | 245 |
| 18+ | 240 | 240 |

The regression survives (+7s instead of +12s) and the 14-lane target is
unchanged, so no conclusion moves - but the "ONE run, deliberately" paragraph
is not true of the sharded column, and a reader refitting the table will not
close it.

**Fix.** Add after `:534`: "The sharded column charges U3 at its 304s MEDIAN,
not this run's 258s draw, because the shard model was fitted to the median.
That is a deliberate cross-run mix and it costs the 12- and 13-lane cells:
re-anchored on 258s they read 318 and 288. The 14-lane target and the
regression sign are unchanged." Then soften `:564` to "this table uses one run
for the step population; the shard model alone uses medians."

### M3. "294s leaves 6s of margin" is attached to the wrong lane count

`:555-557`: "It crosses 300s at 13 lanes, but **14 is the target**: 294s leaves
6s of margin against per-step swings measured up to 3.2x."

294s is the **13**-lane figure. 14 lanes is 277s, with 23s of margin. As
written the colon offers 294s as the justification FOR 14, giving the
recommended configuration a margin that belongs to the one being rejected.

**Fix.** "It crosses 300s at 13 lanes, but 13's 294s leaves only 6s of margin
against per-step swings measured up to 3.2x, so **14 is the target** - 277s,
23s of margin."

### M4. The MEASURED-268 pointer does not add up, and names the wrong cause

`:526-530`: "The 5s floor drops three real harness steps; `MEASURED-268` counts
them and publishes 35 steps / 3442s over all three runs."

- 33 + 3 = **36**, not 35.
- The three dropped steps are 4.0s, 3.0s and 0.0s (`U15 gate amputation`,
  `Mirror liveness controls`, `Harness gate controls`). 3311 + 7 = **3318**,
  not 3442. The 5s floor explains 7 of the 131 seconds.
- `MEASURED-268:122` says "median sum", not a sum over three runs.

The real cause is the run set. I reproduced it: median over the union of step
names gives **34 steps / 3446s**, and feeding that into the same LPT with the
same 13s setup returns MEASURED-268's numbers - 317s unsharded at every lane
count, 276s at 14, 252s at 16. So the pointer is right that the populations
differ, and wrong about why.

**Fix.** "`MEASURED-268` uses per-step MEDIANS over all three runs rather than
one run's draws; that is worth ~131s and is the whole of the gap. The 5s floor
accounts for 3 steps and 7s. Its 35-step count is one off the 34 I get from the
same construction, unresolved and immaterial."

### M5. The citation for the load-bearing `overhead/k` choice is half wrong

`:465-467`: "`overhead` is divided by `k` because it is per-row cost - roughly
one `uv run` start per row, at `:151` and `:186`".

`grep -n "uv run" scripts/check-u9-http-amputation.sh` returns exactly two
lines: **`:94`** (the baseline, `pytest $SUITE --cov`) and **`:186`** (the
per-row `pytest $sel`). `:151` is `s = p.read_text()`, inside an inline
`python3 - <<'PY'` heredoc - not a `uv run`, and it starts no process of the
kind being counted.

So there is ONE `uv run` per row, not two, and the other `uv run` in the file is
per-INVOCATION and is precisely the cost that must NOT be divided by k. The
cite supporting the modelling choice points at the wrong line and omits the
contrast that actually justifies it.

**Fix.** "`overhead` is divided by `k` because it is per-row: exactly one
`uv run --frozen pytest` per row at `:186`. The other `uv run` in the file,
`:94`, is the once-per-invocation baseline and is inside `B`, not `overhead` -
which is why `B` is replicated and `overhead` is divided."

### M6. "Two live disagreements" omits the real one and lists one that is not a disagreement

`:600-611` names the 1.814/1.567 gap (H1: reconciles exactly) and the
276-vs-277 gap (which it calls agreement). It does not mention that
`MEASURED-268:131` publishes the unsharded floor as **317s at every lane
count** where this section publishes **311s** - a 6s disagreement on the
section's own headline number, caused by median-304 vs one-run-298 as the
largest step. Nor the 13- and 16-lane sharded cells (289 vs 294, 252 vs 245).

`:636-637`'s "it agrees with `MEASURED-268` to within a few seconds" is doing a
lot of work for a 7s gap at 16 lanes.

**Fix.** Replace the 1.814/1.567 entry with the reconciliation (H1), and make
the live entry: "`MEASURED-268:131` publishes 317s unsharded where this section
publishes 311s, and 289/252 at 13/16 lanes where this section has 294/245. All
of it is medians-over-three-runs versus one run; neither is wrong, and the
larger disagreement (6-7s) is bigger than the 'few seconds' this section claims
elsewhere."

---

## LOW

### L1. "the ~149s a U3-shaped model predicts" - a U3-shaped model predicts 160s

`:485`. U3's shape is 7.5% baseline / 92.5% divisible. Applied to a 298s step at
k=2: `298 * (0.0746 + 0.9254/2) = 160.1s`. 149s is 298/2 - a model with NO
baseline at all, which is not U3's shape and is a straw man weaker than the real
comparison.

**Fix.** "298s -> 219s, not the ~160s U3's own 92.5%-divisible shape would
predict, and nothing like the 149s a baseline-free model would."

### L2. The stated wrapper-exclusion names do not appear in the payload, and one 5.0s install survives the rule

`:524-525` excludes `Set up job`, `Checkout`, `Install uv`, `Set up Python`,
`Post *`, `Complete job`. The actual step names in run 33630968540 are
`Run actions/checkout@v6`, `Run actions/setup-python@v5` and
`Install from the frozen lock`; only `Set up job`, `Install uv`, `Post *` and
`Complete job` match literally.

The 33 still comes out right because everything unmatched happens to fall under
5s - **except one `Install from the frozen lock` at exactly 5.0s**, which the
rule as written admits as a harness work step. Strictly applied, the stated rule
gives **32 steps / 3306s**. Nothing moves (the largest step is still 298s and
the floor is still 311s), but the rule as printed does not reproduce the number
printed beside it.

**Fix.** "...excluding GitHub's own per-job wrapper steps
(`Set up job`, `Run actions/checkout@v6`, `Install uv`,
`Install from the frozen lock`, `Run actions/setup-python@v5`, `Post *`,
`Complete job`)." Recheck the total after: one 5.0s install currently sits
inside the 3311.

### L3. `select-covering-tests.py` cites are correct in content, wrong in path

`:617-618` cites `select-covering-tests.py:47-50` and `:73-77`. The file is
`scripts/lib/select-covering-tests.py` - as `check-u9-http-amputation.sh:133`
itself shows. Both line ranges check out at the real path (`:47-50` reads
`COVERAGE_DB` from any path and fails closed if absent; `:73-77` joins on
`path.endswith("/" + rel)`).

**Fix.** Write `scripts/lib/select-covering-tests.py:47-50` and `:73-77`.

### L4. `check-u9-http-amputation.sh:22` is a comment about the state BEFORE #238

`:482-483` cites `:22` for "it builds a coverage map over the whole 888-test
suite". Line 22 reads `# Before #238 the full 888-test suite ran per row and
this step alone cost 1270s in CI (run 33582613697)` - a comment describing the
behaviour this branch REMOVED. The claim is true; the evidence is `:71`
(`SUITE="tests"`) and `:94-95` (`uv run --frozen pytest $SUITE --cov
--cov-context=test`).

**Fix.** Cite `check-u9-http-amputation.sh:71,:94-95`.

### L5. Wrong confession: the 15 came from the first REWRITE, not the first version

`:605-607`: "the first version of this section's 15 was the sole outlier."

`git show 733979a:docs/reviews/REVAMP-238-ci.md` §7a.2 contains no lane count
at all - it names a 235s step floor and a 290-394s wall. The 15 lanes appear in
`e108bc6` ("it crosses 300s at **15 lanes (276s)**"), the first rewrite. The
same section uses "the first version of this section" for `733979a` two
paragraphs earlier (`:497`, "named a '235s step floor'"), so the phrase now
denotes two different commits in one section.

A wrong confession is still a wrong statement, and this one misattributes an
error to the version that did not make it.

**Fix.** "the first REWRITE's 15 was the sole outlier (the original version
named no lane count)."

### L6. Rounding is inconsistent between the two rows

`303.97 -> 304` (rounded) but `219.53 -> 219` (truncated). A reader refitting
gets 220 for the U9 cell and thinks the table does not close - the exact failure
mode `:462-463` exists to prevent.

**Fix.** Print 220, or add "cells are truncated to the second".

---

## NITS

- **N1.** `:594-595` "a median of 150s but drew 376s once, a 3.2x swing" reads
  as 376/150 = 2.5x. The 3.21x is max/min (117s to 376s). *Fix:* "a 3.2x spread
  across the three runs, 117s to 376s."
- **N2.** `:592-593` "the run that drew 298 was recorded as 304, its median" -
  "its" has two live antecedents, and both happen to be 304 (U3-amputation's
  median, and the median of the three per-run largest steps {376, 304, 298}).
  *Fix:* name which.
- **N3.** `:469` "the two scale factors differ by 8.6%" - 1.703/1.567 is 8.68%
  as a ratio, 8.3% against the larger. Immaterial, but state the base.
- **N4.** `:488-493` "the overhead terms and both scale factors appear nowhere
  outside the table above" is too strong for the scales: both are DERIVED
  (`304/193.98`, `298/175.02`) from CI step times that do appear elsewhere, and
  `MEASURED-268:125` publishes the U3 numerator and denominator explicitly. The
  genuinely free parameters are the two overhead terms - and because
  `scale = k1/(B+R+ovh)` is fitted to `k1`, the k=1 column reproduces BY
  CONSTRUCTION. The refit demonstrates internal consistency, not measurement.
  Worth saying, since `:462-463` presents the refit as what makes the table a
  measurement rather than a claim. Sweeping U9's overhead from 0 to 62.6s moves
  its k=2 cell from 235s to 209s with k=1 pinned at 298s the whole way. *Fix:*
  "the two overhead terms are free parameters fitted alongside each scale to the
  k=1 CI time, so the k=1 column closes by construction; the k=2 column is
  unmeasured model output, and it spans 209-235s for U9 across plausible
  overheads."

---

## Method, and what I did NOT verify

Recomputed from `gh api repos/:owner/:repo/actions/runs/<id>/jobs?per_page=100`
for all three runs; step durations from `started_at`/`completed_at`; my own LPT
(sort descending, place on the least-loaded lane, add setup once). Every table
above is output, not transcription.

- **The four local inputs** (`14.47`/`153.11`, `82.79`/`60.93`) and the two
  overhead terms. Still not in this tree; the section already says so and it is
  still true. The measurement script it says is owed has not appeared.
- **`R7A2` itself.** I did not read the prior review, by design.
- **`MEASURED-268`'s 35-step population.** I get 34 from the same construction
  and did not chase the one-step difference.
- **Whether 14 lanes are admitted promptly.** Externally contended, unchanged
  from `MEASURED-268:409`.
- **Anything about the shard implementation.** This review is arithmetic only.
