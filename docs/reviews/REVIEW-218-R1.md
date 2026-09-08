# REVIEW-218-R1: the ruling at `e485bce`

Fresh reviewer (`review-218`). Worktree `/tmp/review-218` on branch `review/218-r1` at `e485bce`.
Second worktree `/tmp/review-218-parent` detached at `04432c5`, used to measure the parent gate.
Subject: commit `e485bce`, one file, `docs/plans/IMPLEMENTATION-PLAN.md`. Nothing was edited in
the subject file. Nothing pushed.

## Verdict

The ruling's CONCLUSION - the document has two reference frames and no single sha can be named for
it - **survives**. Every measurement I re-derived from the blobs came back as claimed, and one came
back stronger. But the FRAME the ruling wraps around that conclusion is wrong in two structural
ways, and the highest-value one is the thing the brief asked me to hunt: **there is a bare `:NNNN`
that resolves at `c15b138`, and the document says so in its own sentence.**

2 High, 3 Medium, 2 Low, 2 nits. Every finding ships a fix.

## Part 1: the seven checkable claims, re-derived

Commands run against the blobs, never against a summary.

| # | claim | verdict |
|---|---|---|
| 1 | `:1220` resolves at `135c3ac`, blank at `c15b138` | **CONFIRMED** |
| 2 | `DESIGN.md:1370-1371` resolves at `c15b138`, `]` at `135c3ac` | **CONFIRMED** |
| 3 | `135c3ac:1220-1303` holds exactly 25 top-level bullets | **CONFIRMED** |
| 4 | `:1370`, `:1466`, `:1627`, `:1846` all resolve at `c15b138` | **CONFIRMED** |
| 5 | `:1264-:1306` holds 0 / 12 / 13 bullets at `9d65cc0` / `135c3ac` / `c15b138` | **CONFIRMED** |
| 6 | the commit touches zero citations | **REFUTED** - see M3 |
| 7 | `check-review-coverage.py` was already RED at `04432c5` | **CONFIRMED, and stronger** - see M1 |

Evidence for 1 and 2:

    $ git show 135c3ac:docs/DESIGN.md | sed -n '1220p'
    - the 200-with-401-body trap;
    $ git show c15b138:docs/DESIGN.md | sed -n '1220p'          # empty
    $ git show c15b138:docs/DESIGN.md | sed -n '1370,1371p'
    **A guard that refuses everything is not a guard, and its refusals prove nothing.** Every
    refusal-path test is paired with a positive control showing the happy path still succeeds.
    $ git show 135c3ac:docs/DESIGN.md | sed -n '1370p'
    ]

Evidence for 3 and 5 (`^- ` at column 0 as the top-level-bullet selector):

    135c3ac  1220-1303: 25   1264-1306: 12
    c15b138  1220-1303: 15   1264-1306: 13
    9d65cc0  1220-1303: 12   1264-1306: 0

Claim 4: `c15b138:1466` is *"No CI pipeline exists yet..."*, `:1627` is *"Two commit-time gates..."*,
`:1846` is the `| *(none)* |` must-mitigate row the plan calls an empty table. All three are
nonsense at `135c3ac` (`:1466` is a `pip-audit` fragment, `:1627` a retired-sentence paragraph,
`:1846` a "what this list is not" paragraph). Confirmed.

**And claim 3's sample is understated.** The ruling says "five sampled rows match `135c3ac`
verbatim". I read all 25 table rows at both blobs. **All 25 match `135c3ac` verbatim**; not one
matches `c15b138`. That is L2 below - a free strengthening the ruling declined to take.

## Part 2: findings

### H1 (High) - a bare `:NNNN` that resolves at `c15b138`, in this document, saying so itself

The declaration's headline is **"THIS DOCUMENT HAS TWO REFERENCE FRAMES, AND THE FORM OF THE
CITATION TELLS YOU WHICH"**, and its operative instruction is *"read a bare `:NNNN` with
`git show 135c3ac:docs/DESIGN.md`"*.

`docs/plans/IMPLEMENTATION-PLAN.md:1736-1737`:

> ADR-0012 reads `Status: Accepted` as of `a39bd2a`, and - which is what actually settles it -
> `DESIGN.md:295` and **`:300` at the frozen `c15b138`** list `utils/constraints.py` and require
> every input model to import from it.

Measured:

    $ git show c15b138:docs/DESIGN.md | sed -n '300p'
    Every input model imports its constraints from `utils/constraints.py`. No input model defines its
    $ git show 135c3ac:docs/DESIGN.md | sed -n '300p'
    ---
    $ grep -n 'imports its constraints from' <(git show 135c3ac:docs/DESIGN.md)   # no output
    $ grep -n 'imports its constraints from' <(git show c15b138:docs/DESIGN.md)
    300:Every input model imports its constraints from `utils/constraints.py`. ...

The sentence does not exist anywhere in `135c3ac`. The bare `:300` resolves **only** at `c15b138`,
its qualified sibling `DESIGN.md:295` resolves at `c15b138` too, and the citing sentence names
`c15b138` in its own words. A reader who obeys the new declaration at this site is sent to a
horizontal rule.

This does not overturn the ruling. It kills the ruling's **explanation**. The split is not a
property of the citation FORM; it is a property of the §1 table, which was written in one pass
against one blob. The declaration generalises an n=25-from-one-table sample into a syntactic law
and then publishes that law as a reading instruction, one thousand seven hundred lines above a
site that breaks it.

**FIX.** Restate the split as an observation with a named scope, not a rule over a form:

> **The §1 required-cases table (25 rows, `:1220`-`:1303`) was written against `135c3ac` and its
> rows resolve there, all 25 verbatim. Four qualified citations sampled elsewhere resolve at
> `c15b138`. That is where the evidence stops.** The citation's form is NOT a reliable guide: the
> bare `:300` at line 1737 resolves at `c15b138`, and its own sentence says so. **Re-derive any
> citation you intend to rely on, at both blobs, rather than inferring its frame from its shape.**

### H2 (High) - "Both sentences were false" is not established, and the 111 arithmetic mixes two populations

The old declaration's second sentence was *"all 111 remain correct against `c15b138`"*. The 111 is
not a count of all citations. It is `#111`'s own measurement, and `#111` names its command:
`grep -rno 'DESIGN\.md:[0-9]' .`. That selector cannot match a bare `:1220`.

Measured over the file itself:

    0ec4c85  qualified `DESIGN.md:NNNN` = 111   bare `:NNNN` = 47
    04432c5  qualified = 111                    bare = 47
    e485bce  qualified = 112                    bare = 56

The 111 is exactly the qualified population, at both `#111`'s ruling commit and this commit's
parent. So:

- The counter-example `:1220` **is not a member of the 111.** It cannot falsify a sentence
  quantified over a set it does not belong to.
- Every measurement the ruling made **inside** the 111 - all four qualified citations - resolved at
  `c15b138`, i.e. **supports** the sentence it declares false.
- "That is 29 of 111. The other 82 are UNMEASURED" adds 25 members of one population to 4 members
  of another and subtracts from the second population's denominator. The honest figures are
  **4 of 111 qualified measured (107 unmeasured)** and **25 of 47 bare measured (22 unmeasured)**.

The first sentence (*"every `DESIGN.md:NNN` citation below is a line number in `c15b138`"*) is
genuinely false if you read "DESIGN.md:NNN" as a generic description of a line-number citation
rather than as the literal token. That reading is available. But the ruling asserts BOTH sentences
false and produces evidence against neither the literal form of the first nor any part of the
second.

**FIX.** Replace the "29 of 111" paragraph with two populations, each with its derivation:

> **WHAT WAS MEASURED, AND OVER WHICH POPULATION.** There are two, and they must not be added.
> **Qualified** `DESIGN.md:NNNN` - 111 occurrences at `0ec4c85`, the population `#111` measured
> (`grep -o 'DESIGN\.md:[0-9]\+' docs/plans/IMPLEMENTATION-PLAN.md | wc -l`). **Four** were read at
> both blobs (`:1370`, `:1466`, `:1627`, `:1846`); all four resolve at `c15b138`, so nothing
> measured here contradicts `#111`. **107 are unmeasured.**
> **Bare** `:NNNN` - 47 occurrences at `0ec4c85`, a population `#111` never counted. **25** were
> read: the whole §1 table, all 25 verbatim at `135c3ac`. **22 are unmeasured, and one of those 22
> is now known to break the pattern** (`:300`, at `c15b138` - see the paragraph above).

### M1 (Medium) - "16 commits are in the backlog unrecorded" is not a number this checker produces

`GATE:` in the commit message says *"check-review-coverage.py is RED and was ALREADY RED at
`04432c5` ... 16 commits are in the backlog unrecorded"*.

Run in a clean worktree detached at `04432c5`, and again at `e485bce`:

    RC_PARENT=1
    RC_HEAD=1
    $ diff /tmp/crc_parent.txt /tmp/crc_head.txt      # no output: byte-identical

    COVERED BY NOTHING: 95
    Backlog recorded in review-coverage-backlog.txt: 66
    Backlog measured now: 118
    ENTERED, unrecorded: 52

`grep -n '\b16\b'` over the output returns nothing. The already-red half of the claim is **CONFIRMED
and understated**: the output is byte-for-byte identical at both commits, which is a stronger
control than "it reads git log, not the working tree" - and the mechanism is visible in the output
itself, where `docs/plans` is listed as a RECORD path, so a commit touching only that file cannot
move this gate. The number attached to it, though, is not from the instrument.

Task `#239` carries the same 16 and inherits the error.

**FIX.** In the commit message and in `#239`, replace *"16 commits are in the backlog unrecorded"*
with *"`ENTERED, unrecorded: 52` (`COVERED BY NOTHING: 95`), unchanged by this edit - the output is
byte-identical at `04432c5` and `e485bce`, because `docs/plans` is a RECORD path in that checker."*

### M2 (Medium) - the re-freeze count is wrong twice, in two different directions, in one commit

- The document says: *"The design has been re-frozen twice since - at `8a9d63c`, and at `d1f1a52`
  today."*
- The commit message says: *"it has now done four times (`c15b138`, `8a9d63c`, `aca9397`,
  `d1f1a52`)"*.

Measured:

    $ git log --oneline c15b138..e485bce -- docs/DESIGN.md
    d1f1a52 ADR-0035: ...
    e3b5c97 ADR-0034: ...
    86ab20e Main was red on two gates ...
    aca9397 ADR-0025: ...
    8a9d63c Apply nine of ten ADRs ...

Five commits changed `DESIGN.md` after `c15b138`. The document's "twice" omits three of them; the
commit message's "four" counts `c15b138` itself as one of the moves and still omits two. Both
numbers appear in the argument that carries the REFUSAL of remedy 1 - the refusal is right, but it
is resting on a retyped figure in a document whose whole subject is retyped figures.

**FIX.** One derived sentence, in both places: *"`DESIGN.md` has changed five times since
`c15b138` - `8a9d63c`, `aca9397`, `86ab20e`, `e3b5c97`, `d1f1a52` - and neither frame tracks it
(`git log --oneline c15b138..HEAD -- docs/DESIGN.md`)."*

### M3 (Medium) - "touches zero citations" is false as written, and the DELETED span is not deleted

The declaration says *"This correction touches **zero** citations."* From the diff:

    removed:  DESIGN.md:1264      `:1306`
    added:    DESIGN.md:1264      `:1306`   DESIGN.md:1370-1371
              `:1220` x3   `:1303`   `:1370` x2   `:1466`   `:1627`   `:1846`

Qualified count goes 111 -> 112. Two citations are removed and eight added.

The **intent** is sound and is what `#111` actually constrains: no citation is REPOINTED. Say that.

Separately, the §1 remedy claims the span *"is DELETED"* under `#166`/ADR-0034. It is not deleted -
it is quoted inside the sentence announcing its deletion: *"The span this sentence used to name -
`DESIGN.md:1264` through `:1306`, against `9d65cc0` - is DELETED"*. The digits are still in the
file and still match a `DESIGN.md:[0-9]` selector, which is exactly why the qualified count rose to
112. This is the use-to-mention rewrite, not a deletion, and it is the shape `#215` recorded as "the
finding rebuilt inside its own remedy".

**FIX.** Two edits.
1. Replace *"touches zero citations"* with *"**REPOINTS zero citations** - no line number in this
   document is moved to a different blob. It adds citations to its own worked example and removes
   one span; the count of qualified citations goes 111 -> 112."*
2. In §1, either drop the numbers from the announcement (*"The span this sentence used to name,
   against `9d65cc0`, is DELETED because it resolved nowhere: that range held 0 top-level bullets
   at `9d65cc0`, 12 at `135c3ac` and 13 at `c15b138`."*) or state plainly that the digits are kept
   as a mention and are not a citation, so a future scan does not re-find them as live.

### L1 (Low) - the bare-form reading rule misdirects bare citations that are not DESIGN.md at all

The instruction *"read a bare `:NNNN` with `git show 135c3ac:docs/DESIGN.md`"* is unconditional, but
several bare citations in this document have a different antecedent:

- `:1303` -> *"`backend/tech-stack.md:157` and `:172` both read..."* - tech-stack.md
- `:1975` -> *"`tech-stack.md:157`/`:172`"* - tech-stack.md
- `:1972` -> *"`docs/research/STANDARDS.md:374-375` and `:316`"* - STANDARDS.md
- `:1400` -> *"draft 2 wrote a bare `:70` whose nearest antecedent was `CREDENTIAL-CHECKLIST.md`"* -
  which is itself a paragraph about this exact hazard

**FIX.** Scope the rule: *"a bare `:NNNN` **whose nearest antecedent is `DESIGN.md`**". The document
already contains the counter-case, at :1400, and it can cite itself for it.

### L2 (Low) - the sample is 25 of 25, and saying "five" throws away the stronger result

The declaration says the table was checked two ways, one of which is *"five sampled rows match
`135c3ac` verbatim"*. I read all 25 rows at both blobs; all 25 match `135c3ac` verbatim and none
matches `c15b138`. That is the same command run 25 times instead of 5.

**FIX.** *"all 25 rows read at both blobs: 25 match `135c3ac` verbatim, 0 match `c15b138`"*, and
drop the word "sampled" - there is no sample left, it is a census of the table.

### N1 (nit) - the §1 rewrite leaves a 173-character run-on

`docs/plans/IMPLEMENTATION-PLAN.md:283` is 173 characters where the surrounding prose wraps near
100; the new sentence was joined onto the old tail (*"...holds exactly 25 top-level bullets. The new
member is **#18**, the SIGTERM teardown case Q2 added; everything below it"*). Nothing gates on it
(the file already has 139 lines over 100, nearly all table rows, and the count moved 139 -> 141),
so this is cosmetic.

**FIX.** Re-wrap :280-284 at the paragraph's own width and put "The new member is #18..." on its own
line.

### N2 (nit) - some citations resolve identically at both blobs and cannot indicate a frame

`:289-290` is byte-identical at `135c3ac` and `c15b138`:

      tools/candidates.py         search_candidates, get_candidate, create_candidate; their input models
      tools/jobs.py               search_jobs, get_job_feed; their input models

A reader checking a citation to decide which frame they are in can land on one that does not
discriminate and conclude either thing.

**FIX.** One clause in the reading instruction: *"and note that some citations resolve identically
at both blobs (`:289-290`, for instance), so agreement with one frame is not evidence of that
frame."*

## Part 3: the brief's other three questions

**Is "unmeasured" honest, or was there a cheap way to settle more?** Partly honest, and there was a
cheaper way than the ruling took. The 25-row census cost 25 `sed -n` calls; the ruling did 5 and
inferred the rest from a bullet count. More importantly, the 24 bare citations OUTSIDE the table
were never enumerated at all, and enumerating them is one `grep -no`. I did it, and the fourth one I
read was H1. **The 82 is not just wrong arithmetic (H2) - it is a denominator that hid the cheapest
remaining measurement behind a word.**

**Does the ruling argue against `#111` by name and on its merits?** **Yes, and this is the strongest
part of it.** It names `#111`, quotes `#111`'s own stated reason back at it (*"honestly out of date
... confidently wrong"*), and turns that reason against `#111`'s remedy rather than around it: a
declaration naming one frame for a two-frame document already produces the failure `#111` was
guarding against. It also names the refused remedy (repoint the bare halves) and refuses it under
ADR-0017 by shape rather than by preference. `#218`'s constraint is met.

**Is the rewritten declaration internally consistent?** **No.** H2 (two populations added), M2 (two
different wrong re-freeze counts, one in the doc and one in the message), M3 ("zero citations" beside
eight added ones, and a "DELETED" span still present) are all internal. The document is prose about
citation frames written immediately after getting citation frames wrong, and it reproduces the class
it names: a retyped figure (M2), a denominator not re-derived (H2), and a deletion that is a mention
(M3).

## What I did NOT verify

- **The 82 - now 107 and 22 - unmeasured citations.** I read the 25 table rows, the 4 qualified
  samples, and 21 of the 24 bare citations outside the table. **I did not read the other 107
  qualified citations at either blob.** H1 is one counter-example, not a survey; the true shape of
  the split is still unmeasured, and a survey of all 168 is roughly 20 minutes of `sed`.
- **`GATE: seven of eight python checkers rc=0`.** The commit does not name the eight, so the claim
  has no population I can re-derive. I ran three: `check-cross-references.py` rc=0,
  `check-review-coverage.py` rc=1 (M1), `check-plan-measurements.py` rc=2 - and the rc=2 is an unmet
  precondition (no `.venv` in my worktree), which is `#221`'s designed refusal, not a red. I did not
  identify or run the other five, and I did not run `ruff`.
- **Whether `:1370`, `:1466`, `:1627`, `:1846` are the RIGHT lines for the claims that cite them** -
  I verified they resolve to coherent text at `c15b138` and to nonsense at `135c3ac`, which is the
  frame question. I did not check `:1466` and `:1627` against the plan's surrounding sentences for
  subject agreement.
- **`9d65cc0`'s standing.** I confirmed the 0/12/13 counts. I did not establish what `9d65cc0` is,
  whether it was ever a freeze, or whether the original sentence was true when written against some
  third blob.
- **Anything downstream of the plan.** I did not check whether any brief, test or script reads the
  declaration I am reviewing.

## Instrument failures in this review, recorded

1. I truncated blob lines with `cut -c1-170` and concluded `:602` resolved at neither blob. The
   quoted phrase was at column 171. Re-run without `cut`, `:602` resolves at `135c3ac` exactly as
   the plan says. **A width limit on a diagnostic is a silent false negative**; the finding I nearly
   filed was mine, not the ruling's.
2. My bullet selector is `^- ` at column 0. It cannot see an indented continuation bullet. The
   counts agree with the ruling's, which means we may share the selector, not that the selector is
   right.

<!-- REVIEW-COVERS: 04432c5..e485bce PATHS: docs/plans/IMPLEMENTATION-PLAN.md -->
