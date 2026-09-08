# REVIEW-218-R2: the R1 fix at `7e8adfa`, and the census R1 said was still owed

Fresh reviewer (`review-218-r2`). I did not write the subject and I am not `review-218`.
Worktree `/tmp/review-218-r2`, detached at `7e8adfa`. Subject: commit `7e8adfa` on `main`
(local, unpushed), which fixes the nine findings `REVIEW-218-R1.md` raised against `e485bce`.
Nothing pushed, nothing merged, `docs/plans/IMPLEMENTATION-PLAN.md` not edited.

Deliverables: this file and `docs/reviews/probe-218-frame-census.py`, both committed here.

## Verdict

**Half A.** Eight of R1's nine findings are genuinely fixed and I re-derived each one. But the
fix broke a citation of its own, one paragraph away from the sentence announcing that citations
break - and it over-corrected R1's H1 into a second false statement, which the census refutes.

**Half B.** The census is done. All **166** DESIGN.md citations resolved at both blobs.
**The split is real, sharp, and has exactly one exception, and that exception is R1's H1.**

    QUALIFIED (111)   c15b138 88   135c3ac 0    identical-at-both 18   undecidable 5
    BARE      (55)    135c3ac 42   c15b138 3    identical-at-both  1   out-of-scope 4
                                   (all 3 are the same citation, `:300`)   mention 4   other 1

**2 High, 4 Medium, 2 Low, 2 nits. Every finding ships a fix.**

---

## Part 1 - Half A: R1's nine findings, re-derived

| R1 | claim | verdict at `7e8adfa` |
|---|---|---|
| H1 | the FORM is not the discriminator | **fixed, then over-corrected** - R2-H2 |
| H2 | 111 is the QUALIFIED population; count the two separately | **fixed in substance**, selector wrong - R2-M1, R2-M2 |
| M1 | "16 unrecorded" is not a number the checker prints | **fixed**, moved to `#239`, whose row now reads 66 + 52 = 118 |
| M2 | FIVE re-freezes, not two or four | **fixed and correct** |
| M3 | "touches zero citations" false; the DELETED span was quoted | **fixed** - count back to 111, digits gone |
| L1 | scope the rule to a DESIGN.md antecedent | **applied to a rule that no longer exists** - R2-M3 |
| L2 | 25 of 25, not "five sampled" | **fixed** |
| N1 | a 173-character run-on | **fixed** - §1 now wraps at 98 |
| N2 | some citations are identical at both blobs | **NOT applied** - R2-M4 |

Re-derivations, each command's exit read on its own line.

**The qualified population is back to 111, equal at all three commits `#111` and `#218` name:**

    $ git grep -o "DESIGN\.md:[0-9]" <rev> -- docs/plans/IMPLEMENTATION-PLAN.md | wc -l
    0ec4c85  111      04432c5  111      e485bce  112      7e8adfa  111

**The five re-freeze shas are correct and complete**, and all five are distinct DESIGN.md blobs:

    $ git log --oneline c15b138..HEAD -- docs/DESIGN.md
    d1f1a52  e3b5c97  86ab20e  aca9397  8a9d63c        (5 commits, 5 distinct blob ids)

**M3's span is gone, not quoted:** `grep -n '1264\|1306'` over the file returns nothing.

**The gate claim in the commit message holds.** Eight checkers re-run here, each rc read on its
own line: `check-checkers-are-wired`, `check-clause-citations`, `check-obligations`,
`check-design-freeze`, `check-design-citations`, `check-row-floor-exactness`,
`check-brief-report-references`, `check-cross-references` - **all rc=0**. `ruff check .` rc=0,
including the probe this review adds.

---

## Part 2 - Half B: the census

`docs/reviews/probe-218-frame-census.py`, committed here. Run it:

    python3 docs/reviews/probe-218-frame-census.py --controls      # 6/6 fired, rc 0
    python3 docs/reviews/probe-218-frame-census.py                 # thresholds 1, 2, 3
    python3 docs/reviews/probe-218-frame-census.py --adjudicated   # the table below

### How it decides, stated before it measured

A citation RESOLVES at a blob when the text at those line numbers shares at least *threshold*
distinctive tokens (lowercased alphanumeric, 6+ chars, minus a stoplist) with the sentence citing
it. The citing context is the plan's lines [L-2 .. L+2] with every citation token stripped, so a
line number cannot match itself. **Nothing is truncated** - R1 nearly filed a false finding
because `cut -c1-170` hid evidence at column 171, and this probe reads whole lines.

**This is a proxy, and it is reported as one.** Three defences:

1. **The threshold is swept.** At 1, 2 and 3 the bare `135c3ac`-only class is **32, 32, 32** and
   the qualified `135c3ac`-only class is **0, 0, 0**. The shape is not a threshold artifact.
2. **Byte-identical citations get their own class** rather than being scored as agreement.
3. **Everything the proxy did not place in a clean single-blob class was READ BY HAND** at both
   blobs, and the verdict recorded in the script's `ADJUDICATED` table with its reason - 31 rows,
   so the next reader can disagree with a named row instead of with a paragraph.

**Selector reuse is declared.** `_QUALIFIED` and `_BARE` are copied verbatim from
`docs/reviews/probe-204-bare-citations.py` (`#204`). Agreement with `#204` is therefore **not**
independent confirmation of either; we share an instrument. R1 made the same disclosure about its
`^- ` bullet selector and it was right to.

**The zero was checked for comparability, because a clean zero that explains itself is the bug.**
`QUALIFIED / 135c3ac-only = 0` is not zero by construction: the identical code path, the identical
`135c3ac` blob read, and the identical scoring function produce **32** on the bare side. The
`135c3ac` arm of the instrument demonstrably fires. The zero is a fact about the qualified
population, not about the instrument.

### The four counts

**QUALIFIED - 111 occurrences, `#111`'s exact population.**

| class | n | notes |
|---|---|---|
| resolves at `c15b138` | **88** | includes all nine the proxy could not decide, read by hand |
| resolves at `135c3ac` | **0** | at threshold 1, 2 and 3, and after hand-reading every doubtful row |
| byte-identical at both | **18** | cannot indicate a frame at all - see R2-M4 |
| undecidable | **5** | the citing sentence carries no subject phrase; listed in full below |

The five undecidable: `plan:204 DESIGN.md:413`, `plan:710 DESIGN.md:1546-1552`,
`plan:759 DESIGN.md:1746`, `plan:771 DESIGN.md:502-534`, `plan:1165 DESIGN.md:1177-1202`.

**BARE - 55 occurrences.**

| class | n | members where the class is small |
|---|---|---|
| resolves at `135c3ac` | **42** | |
| resolves at `c15b138` | **3** | `plan:37`, `plan:58`, `plan:1764` - **all three are `:300`** |
| byte-identical at both | **1** | `plan:1727 :289-290` (R1's N2, confirmed) |
| not a DESIGN.md citation | **1** | `plan:36 :1737` - a line number in THIS file |
| a bare mention of a QUALIFIED citation | **4** | `plan:52` listing `:1370 :1466 :1627 :1846` |
| antecedent is another file | **4** | `:172` x2 tech-stack.md, `:316` STANDARDS.md, `:70` |

### What this settles

**The form predicts the frame in 130 of the 131 citations that can discriminate at all.**
88 qualified go to `c15b138` and none goes to `135c3ac`; 42 bare go to `135c3ac` and the only
three that go to `c15b138` are three printings of one citation, `:300` - R1's H1, at its site
(`plan:1764`) and twice more where the declaration quotes it.

So R1's H1 stands exactly as R1 framed it: it kills the **rule**, because a rule with a
counter-example is not a rule. It does not license the opposite claim, and `7e8adfa` makes the
opposite claim. That is R2-H2.

### One instance worth naming, because it is the whole finding in one sentence

`docs/plans/IMPLEMENTATION-PLAN.md:271-273`:

> `DESIGN.md:1466-1472` now states that every "CI runs" sentence in that document is a
> specification ... `:1426` reads *"CI **must** run"* accordingly.

    $ git show 135c3ac:docs/DESIGN.md | sed -n '1426p'
    CI must run `python3 docs/reviews/check-coupling.py docs/DESIGN.md`, which enforces §11's internal
    $ git show c15b138:docs/DESIGN.md | sed -n '1426p'
                                                                    # empty

Two citations in **one sentence**, in **different frames**, and the only thing telling them apart
is their form. The qualified one is at `c15b138`; the bare one is at `135c3ac` and is a blank line
at `c15b138`.

---

## Part 3 - findings

### R2-H1 (High) - the fix broke its own citation, in the paragraph about broken citations

`docs/plans/IMPLEMENTATION-PLAN.md:35-36`:

> **THE FORM IS NOT THE DISCRIMINATOR, AND THE COUNTER-EXAMPLE IS IN THIS FILE.** `:1737` cites a
> bare `:300` ...

Measured at `HEAD` (`7e8adfa`):

    $ sed -n '1737p' docs/plans/IMPLEMENTATION-PLAN.md
       models, U12 the job-feed model, and U8 and U12 start at the same instant. `DESIGN.md:291` -
    $ sed -n '1764p' docs/plans/IMPLEMENTATION-PLAN.md
       `:300` at the frozen `c15b138` list `utils/constraints.py` and require every input model to import
    $ git show e485bce:docs/plans/IMPLEMENTATION-PLAN.md | sed -n '1737p'
       `:300` at the frozen `c15b138` list `utils/constraints.py` and require every input model to import

`1737` was correct at `e485bce`, which is where R1 read it. **`7e8adfa` grew the blockquote by 27
lines and moved the site to `1764` in the same commit that typed `1737` into the new prose.** The
number was carried forward from R1's report rather than re-derived after the edit that invalidated
it. A reader following it lands on a paragraph about U8 and U12 registration order.

This is the document's own subject, one paragraph over, and it is the third artefact tonight where
a fix rebuilt its defect one column over. The same stale `1737` is also in the commit message and
in `#218`'s row.

**FIX.** Do not repoint it - the number will move again on the next edit to this blockquote, which
is exactly why the document already refuses repointing as a remedy. Use the subject phrase, which
is the document's OWN stated remedy at :80-82:

> **THE FORM IS NOT THE DISCRIMINATOR, AND THE COUNTER-EXAMPLE IS IN THIS FILE.** The ADR-0012
> paragraph in §9 - *"`Status: Accepted` as of `a39bd2a`"* - cites a bare `:300` and names its own
> blob in its own words.

Then correct the commit message's `:1737` and `#218`'s row the same way.

### R2-H2 (High) - "nothing about a citation tells you which frame" is over-corrected, and the census refutes it

`docs/plans/IMPLEMENTATION-PLAN.md:21-22`:

> **THIS DOCUMENT HAS MORE THAN ONE REFERENCE FRAME, AND NOTHING ABOUT A CITATION TELLS YOU WHICH
> ONE IT IS IN. RE-DERIVE ANY CITATION YOU INTEND TO RELY ON.**

The census says otherwise: of the 131 citations that discriminate at all, **130 sit exactly where
their form predicts**. Zero qualified citations of 111 resolve at `135c3ac`. One bare citation of
55, printed three times, resolves at `c15b138`.

The previous revision was wrong because it published a 25-row sample as a syntactic law. This
revision is wrong in the mirror: it publishes a single counter-example as the destruction of a
signal that is right 130 times out of 131, and it does so in the sentence that is the reader's
only guidance. **"Nothing tells you" is not the cautious version of "the form tells you" - it is
a second unmeasured claim, and this time the measurement exists.** A reader who believes it will
re-derive 166 citations to discover that the form was right about all but one.

**FIX.** Replace the headline and the paragraph under it with the measurement and its exception:

> **THIS DOCUMENT HAS MORE THAN ONE REFERENCE FRAME. THE FORM OF A CITATION PREDICTS WHICH ONE,
> WITH ONE KNOWN EXCEPTION, AND PREDICTION IS NOT PERMISSION - RE-DERIVE ANYTHING YOU RELY ON.**
> Measured over all 166 by `docs/reviews/probe-218-frame-census.py`: of the **111 qualified**
> `DESIGN.md:NNN` citations, **88 resolve at `c15b138` and none resolves at `135c3ac`**; 18 are
> byte-identical at both blobs and 5 cannot be decided from their own sentence. Of the **55 bare**
> `` `:NNN` `` citations, **42 resolve at `135c3ac`**, four cite other files, and **three resolve
> at `c15b138` - all three are the same citation, `:300`**, whose sentence names `c15b138` itself.
> So: a bare citation is a `135c3ac` line number 42 times out of 45, and `:300` is the exception
> that makes this a measured tendency rather than a rule.

### R2-M1 (Medium) - the selector printed for the 111 does not return 111

`docs/plans/IMPLEMENTATION-PLAN.md:47-49`:

> its selector is `grep -rno 'DESIGN\.md:[0-9]' .`, which returns 111 both at `#111`'s own ruling
> commit `0ec4c85` and at `04432c5`.

Run as printed, from the repository root:

    $ git grep -o "DESIGN\.md:[0-9]" 0ec4c85 -- . | wc -l
    1871
    $ git grep -o "DESIGN\.md:[0-9]" 04432c5 -- . | wc -l
    2155

The `-r ... .` form is repository-wide. `#111` used it that way deliberately - its own row says the
container held "152 citation occurrences outside them - **docs/plans 111**, .github/workflows 20,
..." - so 111 was that selector's **docs/plans share**, never its total. The document prints the
command and the number as if the first produced the second. **R1's own suggested fix named the
file; the applied fix dropped it.** A reader re-deriving the figure gets 1871 and concludes the
declaration is out by a factor of seventeen.

**FIX.**

> its selector, restricted to this file, is
> `grep -o 'DESIGN\.md:[0-9]\+' docs/plans/IMPLEMENTATION-PLAN.md | wc -l`, which returns 111 at
> `#111`'s ruling commit `0ec4c85`, at `04432c5` and here. (`#111` ran it repository-wide, where
> `docs/plans` was 111 of 152 occurrences outside the swept directories.)

### R2-M2 (Medium) - the bare-population command counts lines, and the population is occurrences

`docs/plans/IMPLEMENTATION-PLAN.md:56`:

>     grep -c '`:[0-9]' docs/plans/IMPLEMENTATION-PLAN.md

    $ grep -c '`:[0-9]' docs/plans/IMPLEMENTATION-PLAN.md
    50
    $ grep -o '`:[0-9]' docs/plans/IMPLEMENTATION-PLAN.md | wc -l
    55

`grep -c` counts **matching lines**, not matches. This file has lines carrying two and three bare
citations - `plan:52` alone carries four, `plan:2178` carries three - so the published selector
under-reports its own population by five, in a document whose entire subject is instruments that
mis-count. It is also the counterpart of the very error `#165` fixed for the continuation counters.

**FIX.** `grep -o '`:[0-9]' docs/plans/IMPLEMENTATION-PLAN.md | wc -l` - **55 today**.

### R2-M3 (Medium) - `L1`'s fix scopes a rule that `H1`'s fix deleted

`docs/plans/IMPLEMENTATION-PLAN.md:80-82`, the declaration's last paragraph:

> **The rule above governs citations whose nearest antecedent is `DESIGN.md`.** This file also
> carries bare citations into `tech-stack.md`, `STANDARDS.md` and `CREDENTIAL-CHECKLIST.md` ...

There is no rule above. The rule R1-L1 was scoping - *"read a bare `:NNNN` with
`git show 135c3ac:docs/DESIGN.md`"* - was **deleted** by the H1 fix in the same commit. The
paragraph now narrows the scope of nothing, and the only reading a reader can give it is that some
rule exists which they failed to find. Two fixes to one paragraph, applied without re-reading the
paragraph after the first landed.

The observation it carries is still worth keeping, and the census sizes it: 4 of the 55 bare
citations have a non-DESIGN.md antecedent.

**FIX.** Attach it to the measurement R2-H2 installs, as a caveat on the population rather than on
a rule:

> **Four of those 55 are not DESIGN.md citations at all** - `:172` twice into `tech-stack.md`,
> `:316` into `STANDARDS.md`, and the `:70` in §5 that is itself a worked example of this hazard.
> Neither blob has anything to say about them, and they are excluded from the 42.

### R2-M4 (Medium) - R1-N2 was never applied, and the census says it is not a nit

R1's N2 asked for one clause saying that some citations resolve identically at both blobs, so
agreement with one frame is not evidence of that frame. Nothing in `7e8adfa` says it.

Measured: **18 of the 111 qualified citations and 1 of the 55 bare are BYTE-IDENTICAL at both
blobs** - 19 of 166, better than one in nine. `DESIGN.md:64-68` (four sites), `:202-205` (four),
`:289-291` (three), `:291`, `:283`, `:63`, `:137`, `:181-190`, `:245-268`, and bare `:289-290`.

This directly attacks the declaration's own operative instruction. It tells the reader to
re-derive; a reader who re-derives at `c15b138`, gets sensible text, and stops has a **one in nine
chance** of having proved nothing at all. The instruction and the hazard are two paragraphs apart
and neither mentions the other.

**FIX.** One clause in the re-derive instruction:

> Re-derive **at both blobs, not at one**: 19 of the 166 citations here resolve to byte-identical
> text at `135c3ac` and `c15b138` (`DESIGN.md:64-68` and `:202-205` among them), so agreement with
> one frame is not evidence of that frame.

### R2-L1 (Low) - a citation both selectors are blind to, so both populations undercount

`docs/plans/IMPLEMENTATION-PLAN.md:2261`:

> `DESIGN.md:295,300` at the frozen `c15b138` list the module and require every input model ...

`DESIGN.md:295` matches the qualified selector. The `,300` is a citation into the same file and
matches **neither** selector: it has no colon, so `` `:[0-9] `` misses it, and no filename, so
`DESIGN\.md:[0-9]` misses it. This is the same site written as `DESIGN.md:295` + bare `:300` at
`plan:1763-1764`, where both halves ARE counted - so the file contains the same reference in two
shapes, one of which is invisible to every instrument in this repository.

It means **111 and 55 are both floors, not exact counts**, which matters because R2-M1's fix
publishes 111 as an exact figure. `#204`'s ARM B ("continuation") is the arm that would catch this
form and it keys on a colon; this is a comma.

**FIX.** Two parts. (1) Note it where the populations are published: *"Both figures are floors: a
comma-separated continuation like `DESIGN.md:295,300` at :2261 matches neither selector."*
(2) Raise it on `#204` as a fourth shape for `probe-204-bare-citations.py` - a bare `,NNN`
immediately following a citation - since it is a repository-wide blind spot, not a defect of this
file.

### R2-L2 (Low) - the declaration counts one of its own words as a DESIGN.md citation

`plan:36`'s `` `:1737` `` is a line number in THIS file. It matches the bare selector, so it is
one of the 55, and its nearest antecedent scans back to the `DESIGN.md` two lines above. It is the
only member of its class. A reader auditing "the bare population" will try to resolve it against a
design blob.

**FIX.** Write it as `IMPLEMENTATION-PLAN.md:1764` (qualified, so it is unambiguous), or - better,
and consistent with R2-H1 - drop the number for the subject phrase, at which point this finding
closes with R2-H1.

### R2-N1 (nit) - a sentence with no beginning, pre-existing and not this commit's

`plan:86` begins *"where the eight-ADR batch landed - no open Critical, High or Medium findings"*.
Its subject was lost before `0ec4c85`: `git show 0ec4c85:...` shows the same dangling clause
directly under the blockquote. Not introduced by `7e8adfa`, and I record it only because the
declaration now ends immediately above it, so it reads as if the blockquote lost a line.

**FIX.** Restore a subject: *"**The design is frozen at `c15b138`**, where the eight-ADR batch
landed - no open Critical, High or Medium findings ..."*.

### R2-N2 (nit) - the re-freeze list and its command diverge on the next re-freeze

`plan:76` says *"It has moved five times since `c15b138`"* beside
`git log --oneline c15b138..HEAD -- docs/DESIGN.md`. Both are correct today (I ran it: five
commits, five distinct blob ids). But `HEAD` is reader-relative, so on the sixth re-freeze the
command returns 6 and the sentence still says five - the exact failure mode M2 was raised for,
reintroduced through the endpoint rather than through the number.

**FIX.** Pin the range in the printed command and let the divergence be visible:
`git log --oneline c15b138..d1f1a52 -- docs/DESIGN.md` (five, always), with a second line:
*"For what has happened since, run it against `HEAD`."*

---

## What I did NOT verify

- **The 5 UNDECIDABLE qualified citations.** Named in Part 2. Their citing sentences carry no
  subject phrase, so I could not settle them from the plan's own words; settling them means
  reading the surrounding argument of both blobs, which I did not do. They cannot change the
  `135c3ac`-only zero into a non-zero without one of them resolving at `135c3ac` **and not** at
  `c15b138`, which none of them appeared to on a skim - but a skim is not a measurement.
- **Whether any citation is on the RIGHT line for its claim.** I measured which blob a citation
  belongs to. I did not measure whether it is correct within that blob - a citation can be in the
  right frame and still point at the wrong paragraph. That is `#52`'s and `#196`'s question.
- **`9d65cc0`'s standing**, same as R1: I confirmed its digits are gone from §1 and did not
  establish what it was.
- **`check-plan-measurements.py` and `check-review-coverage.py`.** I ran the eight the commit
  message names and `ruff`. The other checkers in `docs/reviews/` I did not run; `#239` covers
  the review-coverage red and I did not re-open it.
- **Anything downstream.** I did not check whether any brief, test or script reads this
  declaration.
- **The commit message and `#218`'s row beyond the `:1737` in them.** I checked R2-H1's number in
  both; I did not audit the rest of either against the file.

## Instrument failures in this review, recorded

1. **My overlap proxy got one citation backwards.** `plan:1179 DESIGN.md:413-416` scored 7 tokens
   at `135c3ac` against 6 at `c15b138` and would have been published as the single qualified
   counter-example - a finding of exactly the shape and size R1's H1 had. Reading the citing
   sentence settles it the other way: the plan says the cited lines call stdio coverage
   *"reasoning, not measurement"*, which is `c15b138:413-416` verbatim. **A margin of one token is
   not a verdict.** It is now a named row in `ADJUDICATED` rather than a number in a table.
2. **My proxy understated the `135c3ac` bare class by five**, because its distinctive-token rule
   needs 6+ character words and citations like `:1220` ("the 200-with-401-body trap") and `:1426`
   ("CI must run") are carried entirely by short words. All five were caught by hand-reading every
   non-clean class, which is why that pass exists; had I published the automated table alone, the
   42 would have read 37.
3. **My antecedent scan is wrong inside a markdown table.** It walks back through contiguous
   non-blank lines, and a table is contiguous non-blank lines, so `CREDENTIAL-CHECKLIST.md` in row
   14 of the §1 table became the "nearest antecedent" of rows 15-25. Named in the probe's
   docstring, and the reason bare citations are resolved WITHOUT being filtered by antecedent.
4. **I reused `#204`'s selectors** rather than writing my own. Agreement between this census and
   `#204`'s counts is therefore shared-instrument agreement, not independent confirmation.

<!-- REVIEW-COVERS: 4bc96a4..7e8adfa -->
