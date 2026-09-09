#!/usr/bin/env python3
"""Resolve every DESIGN.md citation in the plan at BOTH frozen blobs.

A census of `docs/plans/IMPLEMENTATION-PLAN.md` against `135c3ac`
and `c15b138`.

WHY THIS EXISTS. `#218`'s declaration says the plan has more than
one reference frame and that nothing about a citation tells you
which one it is in. `REVIEW-218-R1.md` ends by saying the true
shape of the split is still unmeasured - 25 table rows plus 4
qualified samples plus one counter-example is not a survey. This
is the survey. It is a PROBE, not a gate: nothing here decides
what to do, it decides what is true.

POPULATIONS. Two, never added, because adding them is exactly how
the previous two revisions of that declaration went wrong.

  QUALIFIED  `DESIGN.md:NNN` - `#111`'s population, 111 members.
  BARE       `` `:NNN` ``    - a population `#111` never counted.

SELECTORS ARE REUSED, AND THAT IS DECLARED. `_QUALIFIED` and
`_BARE` below are copied VERBATIM from
`docs/reviews/probe-204-bare-citations.py` (`#204`), together with
its three left-boundary exclusion shapes. Reusing a selector means
agreement with `#204` is NOT independent confirmation of either;
it means we share an instrument. Stated so no reader mistakes one
for the other.

WHAT "RESOLVES" MEANS, STATED BEFORE IT IS MEASURED. A citation
RESOLVES at a blob when the text at those line numbers in that
blob shares at least `--threshold` DISTINCTIVE tokens with the
sentence citing it. A DISTINCTIVE token is a lowercased
alphanumeric word of 6+ characters not in `_STOP`. The citing
context is the plan's lines [L-2 .. L+2] with every citation token
stripped out, so a line number cannot match itself.

THIS IS A PROXY AND IS REPORTED AS ONE.

  1. `--threshold` is swept (1, 2, 3) and all three tables print.
     A split that exists at only one threshold is an artifact.
  2. Every member of every class of 12 or fewer is PRINTED IN FULL
     with both blobs' text, for a human to adjudicate.
  3. A citation whose text is BYTE-IDENTICAL at both blobs gets
     its own class. It cannot indicate a frame at any threshold,
     and scoring it as "both" would be a clean number that means
     nothing.
  4. Nothing is truncated. R1 nearly published a false finding
     because `cut -c1-170` hid evidence sitting at column 171.
  5. `--adjudicated` overrides the proxy with hand-read verdicts,
     each carrying its reason. The proxy was WRONG in at least one
     direction (plan:1179) and understated ONLY-135c3ac by five;
     both are recorded in `ADJUDICATED` rather than in prose.

KNOWN LIMITATION, NAMED RATHER THAN LEFT TO BE DISCOVERED. The
antecedent scan walks backwards through contiguous non-blank
lines, and a markdown TABLE is contiguous non-blank lines. So a
filename in row 14 of the §1 table becomes the "nearest
antecedent" of rows 15-25, which is wrong - every row of that
table cites `DESIGN.md` §8. The antecedent census is therefore a
DIAGNOSTIC, and BARE citations are resolved WITHOUT being filtered
by it. A bare citation into another file lands in NEITHER, which
is the honest answer for it.

Usage:
    python3 docs/reviews/probe-218-frame-census.py
    python3 docs/reviews/probe-218-frame-census.py --threshold 2
    python3 docs/reviews/probe-218-frame-census.py --members
    python3 docs/reviews/probe-218-frame-census.py --adjudicated
    python3 docs/reviews/probe-218-frame-census.py --controls

Exit 0 on a census, 1 if a control does not fire.
"""

from __future__ import annotations

import argparse
import collections
import pathlib
import re
import subprocess
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PLAN = "docs/plans/IMPLEMENTATION-PLAN.md"
DESIGN = "docs/DESIGN.md"
BLOB_A = "135c3ac"  # the original freeze
BLOB_B = "c15b138"  # the re-freeze the document names in its header

# ---- selectors, COPIED VERBATIM from probe-204-bare-citations.py ----
_FILENAME_CHAR = r"[A-Za-z0-9_./\\-]"
_BARE = re.compile(rf"(?<!{_FILENAME_CHAR}):(\d+)(?:-(\d+))?\b")
_QUALIFIED = re.compile(
    r"(?P<name>[A-Za-z0-9_.\-/]+\.(?:md|py|yml|yaml|sh|toml|txt|cfg|ini|json))"
    r":(\d+)(?:-(\d+))?"
)
# probe-204's three left-boundary exclusion shapes, keyed by the char
# left of the colon.
_EXCLUDE_PREV = {"[", '"', ":"}

_NAME = re.compile(r"[A-Za-z0-9_.\-/]+\.(?:md|py|yml|yaml|sh|toml|txt|cfg|ini|json)")

_STOP = {
    "design",
    "citation",
    "citations",
    "document",
    "against",
    "because",
    "between",
    "written",
    "resolve",
    "resolves",
    "measured",
    "measure",
    "blockquote",
    "revision",
    "population",
    "populations",
    "reference",
    "frames",
    "number",
    "numbers",
    "should",
    "another",
    "itself",
    "example",
    "member",
    "members",
    "sentence",
}

_WORD = re.compile(r"[a-z0-9]{6,}")


def _blob(rev: str) -> list[str]:
    out = subprocess.run(
        ["git", "show", f"{rev}:{DESIGN}"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=True,
    )
    return out.stdout.split("\n")


def _plan_lines() -> list[str]:
    return (REPO_ROOT / PLAN).read_text(encoding="utf-8").split("\n")


def distinctive(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


class Cite:
    """One citation occurrence in the plan, with its cited span."""

    __slots__ = ("kind", "line", "col", "start", "end", "raw", "antecedent")

    def __init__(
        self,
        kind: str,
        line: int,
        col: int,
        start: int,
        end: int,
        raw: str,
        antecedent: str,
    ) -> None:
        """Record one occurrence; `start`/`end` are DESIGN.md lines."""
        self.kind, self.line, self.col = kind, line, col
        self.start, self.end, self.raw, self.antecedent = start, end, raw, antecedent


def _nearest_antecedent(lines: list[str], idx: int, col: int) -> str:
    """The last filename token at or before (idx, col).

    Scans back through contiguous non-blank lines.
    """
    names = _NAME.findall(lines[idx][:col])
    if names:
        return str(names[-1])
    j = idx - 1
    while j >= 0 and lines[j].strip():
        names = _NAME.findall(lines[j])
        if names:
            return str(names[-1])
        j -= 1
    return ""


def collect() -> list[Cite]:
    lines = _plan_lines()
    out: list[Cite] = []
    for i, line in enumerate(lines):
        taken: set[int] = set()
        for m in _QUALIFIED.finditer(line):
            taken.update(range(m.start(), m.end()))
            a = int(m.group(2))
            b = int(m.group(3)) if m.group(3) else a
            out.append(
                Cite("QUALIFIED", i + 1, m.start(), a, b, m.group(0), m.group("name"))
            )
        for m in _BARE.finditer(line):
            if m.start() in taken:
                continue
            prev = line[m.start() - 1] if m.start() > 0 else ""
            if prev in _EXCLUDE_PREV:
                continue
            a = int(m.group(1))
            b = int(m.group(2)) if m.group(2) else a
            out.append(
                Cite(
                    "BARE",
                    i + 1,
                    m.start(),
                    a,
                    b,
                    m.group(0),
                    _nearest_antecedent(lines, i, m.start()),
                )
            )
    return out


def _cited_text(blob: list[str], a: int, b: int) -> str | None:
    if a < 1 or b > len(blob):
        return None
    return "\n".join(blob[a - 1 : b])


def _context(lines: list[str], ln: int) -> str:
    lo, hi = max(0, ln - 3), min(len(lines), ln + 2)
    chunk = "\n".join(lines[lo:hi])
    chunk = _QUALIFIED.sub(" ", chunk)
    chunk = _BARE.sub(" ", chunk)
    return chunk


def classify(
    cites: list[Cite],
    blob_a: list[str],
    blob_b: list[str],
    threshold: int,
) -> list[dict[str, Any]]:
    lines = _plan_lines()
    rows = []
    for c in cites:
        ta = _cited_text(blob_a, c.start, c.end)
        tb = _cited_text(blob_b, c.start, c.end)
        ctx = distinctive(_context(lines, c.line))
        oa = len(distinctive(ta or "") & ctx)
        ob = len(distinctive(tb or "") & ctx)
        ra = ta is not None and ta.strip() != "" and oa >= threshold
        rb = tb is not None and tb.strip() != "" and ob >= threshold
        cls = {
            (True, True): "BOTH",
            (True, False): "ONLY-135c3ac",
            (False, True): "ONLY-c15b138",
            (False, False): "NEITHER",
        }[(ra, rb)]
        rows.append(
            {
                "c": c,
                "ta": ta,
                "tb": tb,
                "oa": oa,
                "ob": ob,
                "cls": cls,
                "identical": ta is not None and ta == tb,
                "oor": ta is None or tb is None,
            }
        )
    return rows


def _table(
    rows: list[dict[str, Any]], kind: str
) -> tuple[list[dict[str, Any]], collections.Counter[str]]:
    """Split rows by kind, scoping QUALIFIED to DESIGN.md.

    DESIGN.md is `#111`'s population and the only one either blob can
    speak to. BARE is NOT scoped, on purpose: the antecedent scan
    cannot be trusted inside a markdown table (see KNOWN LIMITATION
    above), so every bare citation is resolved and its antecedent is
    printed for the reader to judge.
    """
    if kind == "QUALIFIED":
        sub = [
            r
            for r in rows
            if r["c"].kind == kind and r["c"].antecedent.endswith("DESIGN.md")
        ]
    else:
        sub = [r for r in rows if r["c"].kind == kind]
    counts = collections.Counter(r["cls"] for r in sub)
    return sub, counts


def _print_census(rows: list[dict[str, Any]], threshold: int, members: bool) -> None:
    print(f"\n===== THRESHOLD {threshold} =====")
    for kind in ("QUALIFIED", "BARE"):
        sub, counts = _table(rows, kind)
        ident = sum(1 for r in sub if r["identical"])
        oor = sum(1 for r in sub if r["oor"])
        print(
            f"\n{kind}: {len(sub)} occurrences "
            f"({ident} byte-identical at both blobs, {oor} out of range at a blob)"
        )
        for cls in ("BOTH", "ONLY-135c3ac", "ONLY-c15b138", "NEITHER"):
            print(f"    {cls:14s} {counts.get(cls, 0)}")
        for cls in ("BOTH", "ONLY-135c3ac", "ONLY-c15b138", "NEITHER"):
            mem = [r for r in sub if r["cls"] == cls]
            if mem and (members or len(mem) <= 12):
                print(f"  -- members of {kind}/{cls} ({len(mem)}) --")
                for r in mem:
                    c = r["c"]
                    print(
                        f"     plan:{c.line} {c.raw!r} antecedent={c.antecedent!r} "
                        f"overlap 135c3ac={r['oa']} c15b138={r['ob']}"
                        f"{' IDENTICAL' if r['identical'] else ''}"
                    )
                    print(f"       135c3ac: {r['ta']!r}")
                    print(f"       c15b138: {r['tb']!r}")


def _print_antecedents(cites: list[Cite]) -> None:
    print("\n===== BARE citations by nearest antecedent =====")
    for name, n in collections.Counter(
        c.antecedent for c in cites if c.kind == "BARE"
    ).most_common():
        print(f"    {n:4d}  {name or '(none)'}")
    print("\n===== QUALIFIED citations by file =====")
    for name, n in collections.Counter(
        c.antecedent for c in cites if c.kind == "QUALIFIED"
    ).most_common():
        print(f"    {n:4d}  {name}")


#: HAND ADJUDICATION. The overlap proxy cannot read meaning, so
#: every citation it did NOT place in a clean ONLY-* class at
#: threshold 1 was READ at both blobs by `review-218-r2` and the
#: verdict recorded here WITH ITS REASON, keyed by (plan line,
#: token). This is the part of the census a human is responsible
#: for. It is written down rather than carried in prose so the
#: next reader can disagree with a named row, not a paragraph.
ADJUDICATED: dict[tuple[int, str], tuple[str, str]] = {
    # BARE.
    (33, ":1220"): ("135c3ac", "the declaration quoting table row 1"),
    (50, ":1220"): ("135c3ac", "the same, quoted again"),
    (318, ":1220"): ("135c3ac", "135c3ac:1220 verbatim, the 401-body trap"),
    (36, ":1737"): ("NOT-A-DESIGN-CITATION", "a line in THIS file"),
    (52, ":1370"): ("MENTION", "a QUALIFIED citation listed in bare form"),
    (52, ":1466"): ("MENTION", "same"),
    (52, ":1627"): ("MENTION", "same"),
    (52, ":1846"): ("MENTION", "same"),
    (37, ":300"): ("c15b138", "R1-H1, quoted in the declaration"),
    (58, ":300"): ("c15b138", "R1-H1, referred to again"),
    (1764, ":300"): ("c15b138", "R1-H1 AT ITS SITE; names c15b138"),
    (271, ":1426"): ("135c3ac", "`CI must run ...`; BLANK at c15b138"),
    (342, ":1303"): ("135c3ac", "`- **approval on BOTH eras**`"),
    (759, ":1738"): ("135c3ac", "resolves at 135c3ac at plan:987 too"),
    (1727, ":289-290"): ("CANNOT-DISCRIMINATE", "identical (R1-N2)"),
    (1330, ":172"): ("OUT-OF-SCOPE", "antecedent backend/tech-stack.md"),
    (2002, ":172"): ("OUT-OF-SCOPE", "antecedent tech-stack.md"),
    (1999, ":316"): ("OUT-OF-SCOPE", "antecedent STANDARDS.md"),
    (1427, ":70"): ("OUT-OF-SCOPE", "antecedent CREDENTIAL-CHECKLIST.md"),
    (1034, ":602"): ("135c3ac", "the plan quotes 135c3ac:602 VERBATIM"),
    # QUALIFIED - the ten the proxy could not decide at threshold 1.
    (86, "DESIGN.md:1846"): (  # REPOINT-EXEMPT: a dict KEY, not a claim
        "c15b138",
        "the `| *(none)* |` row",
    ),
    (2090, "DESIGN.md:1846"): (  # REPOINT-EXEMPT: a dict KEY, not a claim
        "c15b138",
        "same row, same blob",
    ),
    (2073, "DESIGN.md:1848"): (  # REPOINT-EXEMPT: a dict KEY, not a claim
        "c15b138",
        "the no-total-in-prose rule",
    ),
    (746, "DESIGN.md:1549-1564"): (  # REPOINT-EXEMPT: a dict KEY, not a claim
        "c15b138",
        "`.env.example` settings",
    ),
    (934, "DESIGN.md:1244-1249"): ("c15b138", "test markers, not limits"),
    (952, "DESIGN.md:455"): ("c15b138", "`Every scan starts at start=0.`"),
    (1017, "DESIGN.md:353"): (  # REPOINT-EXEMPT: a dict KEY, not a claim
        "c15b138",
        "`one call, four rows created`",
    ),
    (1102, "DESIGN.md:1370-1371"): ("c15b138", "`]` at 135c3ac"),
    (1588, "DESIGN.md:1416-1421"): ("c15b138", "the three pinned deps"),
    (204, "DESIGN.md:413"): ("UNDECIDABLE", "no subject phrase cited"),
    # THE PROXY GOT THIS ONE BACKWARDS, 7 tokens to 6. Reading
    # settles it: the plan says the cited lines call stdio coverage
    # "reasoning, not measurement", which is c15b138:413-416.
    # Recorded as an instrument failure of this probe in R2.
    (1179, "DESIGN.md:413-416"): ("c15b138", "`reasoning, not a measurement`"),
}


def adjudicate(
    rows: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], str, str]]:
    """Proxy verdict at threshold 1, OVERRIDDEN by any hand-read row."""
    out = []
    for r in rows:
        c = r["c"]
        hand = ADJUDICATED.get((c.line, c.raw))
        if hand:
            v, why = hand
        elif r["identical"]:
            v, why = "CANNOT-DISCRIMINATE", "byte-identical at both blobs"
        elif r["oa"] > r["ob"]:
            v, why = "135c3ac", f"overlap {r['oa']} vs {r['ob']}"
        elif r["ob"] > r["oa"]:
            v, why = "c15b138", f"overlap {r['ob']} vs {r['oa']}"
        else:
            v, why = "UNDECIDABLE", f"overlap tied at {r['oa']}"
        out.append((r, v, why))
    return out


def print_adjudicated() -> None:
    a, b = _blob(BLOB_A), _blob(BLOB_B)
    rows = classify(collect(), a, b, 1)
    for kind in ("QUALIFIED", "BARE"):
        sub, _ = _table(rows, kind)
        ver = adjudicate(sub)
        counts = collections.Counter(v for _, v, _ in ver)
        print(f"\n===== ADJUDICATED {kind}: {len(sub)} occurrences =====")
        for v, n in counts.most_common():
            print(f"    {v:22s} {n}")
        for r, v, why in ver:
            if counts[v] <= 12:
                print(f"    plan:{r['c'].line:5d} {r['c'].raw:18s} -> {v:22s} {why}")


def controls() -> int:
    """Controls. Each must FIRE, and each names what it would miss."""
    fails = []
    a, b = _blob(BLOB_A), _blob(BLOB_B)
    cites = collect()
    rows = classify(cites, a, b, 2)

    # C1: line 1220 at 135c3ac is the table row 1 text; blank at
    # c15b138.
    t135 = _cited_text(a, 1220, 1220)
    tc15 = _cited_text(b, 1220, 1220)
    if t135 != "- the 200-with-401-body trap;":
        fails.append(f"C1 135c3ac:1220 is {t135!r}")
    if (tc15 or "").strip() != "":
        fails.append(f"C1 c15b138:1220 is {tc15!r}, expected blank")

    # C2: :300, R1's H1 counter-example. Substantive at c15b138, `---`
    # at 135c3ac.
    if _cited_text(a, 300, 300) != "---":
        fails.append("C2 135c3ac:300 is not `---`")
    if "imports its constraints" not in (_cited_text(b, 300, 300) or ""):
        fails.append("C2 c15b138:300 lost its sentence")

    # C3: NEGATIVE. A citation whose text is identical at both blobs
    # must be
    #     flagged identical, or the census would silently score it as
    # evidence.
    ident = [r for r in rows if r["identical"] and not r["oor"]]
    if not ident:
        fails.append("C3 no byte-identical citation found - the flag is untested")

    # C4: AMPUTATION. Strip the overlap test and everything non-blank
    # becomes
    #     BOTH; the census must NOT already look like that.
    allboth = classify(cites, a, b, 0)
    n_both_0 = sum(1 for r in allboth if r["cls"] == "BOTH")
    n_both_2 = sum(1 for r in rows if r["cls"] == "BOTH")
    if n_both_0 <= n_both_2:
        fails.append(
            "C4 threshold does no work: BOTH at t=0 is "
            f"{n_both_0}, at t=2 is {n_both_2}"
        )

    # C5: the antecedent scan must find the non-DESIGN.md antecedents
    # R1-L1 named.
    ants = {c.antecedent for c in cites if c.kind == "BARE"}
    for want in ("tech-stack.md", "DESIGN.md"):
        if not any(a2.endswith(want) for a2 in ants):
            fails.append(f"C5 antecedent {want} never found")

    # C6: the two blobs must not be the same object, or every class
    # collapses.
    if a == b:
        fails.append("C6 the two blobs are byte-identical")

    for f in fails:
        print(f"CONTROL FAILED: {f}")
    if not fails:
        print("controls: 6/6 fired")
    return 1 if fails else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=int, default=None)
    ap.add_argument("--members", action="store_true")
    ap.add_argument("--controls", action="store_true")
    ap.add_argument("--adjudicated", action="store_true")
    args = ap.parse_args(argv)

    if args.controls:
        return controls()
    if args.adjudicated:
        print_adjudicated()
        return 0

    a, b = _blob(BLOB_A), _blob(BLOB_B)
    cites = collect()
    print(
        f"{PLAN} at HEAD; {DESIGN} at "
        f"{BLOB_A} ({len(a)} lines) and {BLOB_B} ({len(b)} lines)"
    )
    print(f"total citation occurrences: {len(cites)}")
    _print_antecedents(cites)
    for t in [args.threshold] if args.threshold else [1, 2, 3]:
        _print_census(classify(cites, a, b, t), t, args.members)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
