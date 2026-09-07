"""Classify merge-invented lines as REFLOW vs NEW TEXT.

REFLOW test: strip the line's leading comment/markup
furniture, collapse all whitespace, and ask whether the
remaining text occurs VERBATIM as a substring of either
parent's whitespace-collapsed version of that same file.
A re-wrapped paragraph keeps its word sequence, so a
genuine reflow line is a substring of a parent; genuinely
new text is not.

MERGES is a FIXED historical population, so this probe can
never be a statement about HEAD.

Controls are asserted in controls() before any
classification is printed.
"""

from __future__ import annotations

import re
import subprocess
import sys

MERGES = [
    "73dd717",
    "92cb89b",
    "a881344",
    "f2a7bce",
    "5bf3fb1",
    "69fba1a",
    "abd856d",
    "3421ce6",
    "517a810",
    "e26c199",
]

FURNITURE = re.compile(r"^[\s#>*|+\-:]+")


def show(rev: str, path: str) -> list[str] | None:
    p = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True, text=True)
    if p.returncode != 0:
        return None
    return p.stdout.splitlines()


def flatten(text: str) -> str:
    return " ".join(re.sub(r"[#>*|]", " ", text).split())


def norm(line: str) -> str:
    return flatten(FURNITURE.sub("", line))


def parents(merge: str) -> list[str]:
    out = subprocess.run(
        ["git", "rev-list", "--parents", "-n", "1", merge],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return out[1:]


def invented(merge: str, path: str) -> list[str]:
    """Re-derive one (merge, path)'s invented lines, set semantics."""
    mine = show(merge, path)
    if mine is None:
        return []
    par = set()
    for p in parents(merge):
        lines = show(p, path)
        if lines is not None:
            par |= set(lines)
    seen = set()
    out = []
    for ln in mine:
        if ln not in par and ln not in seen and ln.strip():
            seen.add(ln)
            out.append(ln)
    return out


def paths_for(merge: str) -> list[str]:
    ps = set()
    for p in parents(merge):
        ps |= set(
            subprocess.run(
                ["git", "diff", "--name-only", p, merge],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.splitlines()
        )
    return sorted(x for x in ps if x)


def is_reflow(line: str, merge: str, path: str) -> bool:
    n = norm(line)
    if len(n) < 12:
        return False  # too short to be a meaningful substring match
    for p in parents(merge):
        lines = show(p, path)
        if lines is None:
            continue
        blob = flatten(" ".join(lines))
        if n in blob:
            return True
    return False


def controls() -> None:
    # Positive: furniture is stripped from the left edge.
    assert norm("  # the quick brown fox") == "the quick brown fox"
    assert norm("      + #: A bare name") == "A bare name"
    # Negative: stripping must not swallow real words.
    assert norm("#+-* hello world") == "hello world"
    assert norm("") == ""
    print("NORM_CONTROLS_PASS")


def main() -> int:
    controls()
    grand = {"REFLOW": 0, "NEW": 0}
    for m in MERGES:
        for path in paths_for(m):
            inv = invented(m, path)
            if not inv:
                continue
            r = [x for x in inv if is_reflow(x, m, path)]
            n = [x for x in inv if not is_reflow(x, m, path)]
            grand["REFLOW"] += len(r)
            grand["NEW"] += len(n)
            print(f"{m} {path}: total={len(inv)} reflow={len(r)} new={len(n)}")
            for x in r:
                print(f"    REFLOW  {x[:110]}")
    tot = sum(grand.values())
    print(f"GRAND reflow={grand['REFLOW']} new={grand['NEW']} total={tot}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
