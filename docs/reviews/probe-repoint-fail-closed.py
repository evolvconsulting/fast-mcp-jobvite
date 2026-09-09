#!/usr/bin/env python3
"""The REPOINT-EXEMPT check in repoint-design-citations.py fails CLOSED.

The defect this pins. `parse()` reads the cited line to see whether
it carries the `REPOINT-EXEMPT` marker. That read can fail - the
file may be unreadable, the report may name a line the file does not
have, the bytes may not decode. The original code caught OSError,
IndexError and UnicodeDecodeError and did nothing, so control fell
through to the repoint: "I could not tell whether this line is
exempt" resolved to "it is not exempt, rewrite it". That is a
fail-open on error in the tool that rewrites every `DESIGN.md` citation
in the tree.

Every row is falsifiable. Rows A-D drive `parse()` directly with a
synthetic report so each failure mode is reached deliberately. Row E
is the end-to-end arm the brief asks for: a real cited file is made
unreadable with chmod and the real tool is run, and it must refuse
rather than repoint. Rows C and D are the negative controls - if the
refusal were blanket they would fail, and a gate that refuses
everything is not a gate.

Exit 0 = every row behaved. Exit 1 = at least one row did not.
No dependencies. Nothing is written: the tool runs in DRY RUN.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import re
import stat
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
TOOL = HERE / "repoint-design-citations.py"

_spec = importlib.util.spec_from_file_location("_repoint_probe", TOOL)
assert _spec is not None and _spec.loader is not None
repoint = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(repoint)

FAILURES: list[str] = []


def row(name: str, ok: bool, detail: str) -> None:
    """Print one row's verdict and record it."""
    print(f"########## {name} {'PASS' if ok else 'FAIL'}: {detail}")
    if not ok:
        FAILURES.append(name)


def moved(rel: str, lineno: int) -> str:
    """One MOVED line in exactly the shape the checker emits."""
    # REPOINT-EXEMPT: these are example citations the probe WRITES,
    # not citations of anything. Repointing them corrupts the probe.
    return f"  MOVED: {rel}:{lineno}: DESIGN.md:100 -> DESIGN.md:200"


# A. The cited file does not exist at all -> OSError inside the read.
# LIVE prefix on purpose: #219 made unlisted directories UNRULED, and an
# UNRULED citation never reaches the exempt read this row probes.
missing = "scripts/__no_such_file_probe__.py"
assert not (REPO_ROOT / missing).exists(), "the probe's 'missing' path exists"
moves, unreadable, _unruled = repoint.parse(moved(missing, 1))
row(
    "A. missing file -> OSError is REFUSED, not repointed",
    moves == {} and len(unreadable) == 1 and "UNREADABLE" in unreadable[0],
    f"moves={moves!r} unreadable={unreadable!r}",
)

# B. The report names a line the file does not have -> IndexError.
# A LIVE-prefix file for the same #219 reason as row A.
real = "scripts/ci-harness-gate.sh"
nlines = len((REPO_ROOT / real).read_text().splitlines())
moves, unreadable, _unruled = repoint.parse(moved(real, nlines + 5000))
row(
    "B. line past EOF -> IndexError is REFUSED, not repointed",
    moves == {} and len(unreadable) == 1,
    f"file has {nlines} lines; moves={moves!r} unreadable={unreadable!r}",
)

# C. NEGATIVE CONTROL. A readable line with no marker must still be
#    collected for repointing. If this row fails the refusal is blanket
#    and the tool has been broken rather than fixed.
# dir=scripts/: the temp files' relative paths must start with a LIVE
# prefix (#219), or classify() routes them to unruled and rows C and D2
# probe nothing. The directory is untracked and removed on exit.
with tempfile.TemporaryDirectory(dir=REPO_ROOT / "scripts") as td:
    plain = pathlib.Path(td) / "plain.txt"
    plain.write_text("a citation lives here: DESIGN.md:100\n")  # REPOINT-EXEMPT
    rel_plain = str(plain.relative_to(REPO_ROOT))
    moves, unreadable, _unruled = repoint.parse(moved(rel_plain, 1))
    row(
        "C. readable, unmarked line IS repointed (negative control)",
        moves == {(rel_plain, 1): {(100, 100): (200, 200)}} and unreadable == [],
        f"moves={moves!r} unreadable={unreadable!r}",
    )

    # D2. #142's RULE, THE REFUSING HALF. A line carrying the marker
    #     but with NO row in the register is NOT exempt, so it must be
    #     repointed like any other line. Before #142 the marker alone
    #     suppressed the repoint, and this row asserted that; the rule
    #     changed underneath it and the row is now the assertion that
    #     the change actually took effect.
    #
    #     A temp path is the RIGHT fixture for this half precisely
    #     because it can never be registered - the register is keyed on
    #     (path, address) and this path does not exist until the run.
    marked = pathlib.Path(td) / "marked.txt"
    marked.write_text("DESIGN.md:100  # REPOINT" + "-EXEMPT\n")  # REPOINT-EXEMPT
    rel_marked = str(marked.relative_to(REPO_ROOT))
    moves, unreadable, _unruled = repoint.parse(moved(rel_marked, 1))
    row(
        "D2. marker WITHOUT a register row does NOT exempt (#142)",
        moves == {(rel_marked, 1): {(100, 100): (200, 200)}} and unreadable == [],
        f"moves={moves!r} unreadable={unreadable!r}",
    )

# D. NEGATIVE CONTROL, and it must stay a real one. The exemption
#    itself must still work, and must be distinguishable from the
#    refusal: excluded from moves AND absent from the unreadable list.
#
#    The fixture is THIS FILE, because after #142 an exemption needs
#    BOTH the marker on the line AND a `(path, address)` row in
#    docs/reviews/REPOINT-EXEMPT.txt - and this file genuinely has one
#    for address 100-100. There is no way to write this arm against a
#    throwaway file any more, which is the point of the register.
#
#    The line number is SEARCHED FOR, not written down: editing
#    anything above it would otherwise move it and this row would
#    quietly start testing a different line. The register key is the
#    ADDRESS (100-100), never the line number, so only the lookup of
#    the marker text depends on position.
#
#    THE SELECTOR REQUIRES THE CITATION TOO, NOT JUST THE MARKER.
#    Searching for the marker alone picked line 2 - a sentence of
#    DOCSTRING PROSE describing the mechanism, which carries the marker
#    only because the marker is a bare substring. The row passed, and
#    it was testing prose. That is this repo's oldest recurring defect
#    wearing a new hat, so the fixture must be a line that actually
#    carries the citation the register row is about.
_SELF = "docs/reviews/probe-repoint-fail-closed.py"
_MARKER = "REPOINT" + "-EXEMPT"
_CITED = "DESIGN.md" + ":100"
_self_lines = (REPO_ROOT / _SELF).read_text().splitlines()
_marked_linenos = [
    n for n, ln in enumerate(_self_lines, 1) if _MARKER in ln and _CITED in ln
]
assert _marked_linenos, (
    f"{_SELF} has no line carrying BOTH {_MARKER} and {_CITED}; "
    "row D would be testing prose rather than a registered citation"
)
# #219 made docs/reviews UNRULED, which would short-circuit this row
# before the exemption lookup runs (moves={} and unreadable=[] for the
# WRONG reason - the vacuous pass measured on 2026-09-02). J-0084
# (2026-09-08) then ruled a .py under docs/reviews LIVE. Either way
# the register key this row depends on names THIS file, so the
# classification is widened for exactly this one call and restored,
# and the restore is asserted against what classify() said BEFORE the
# widening, not against a ruling this probe does not own: the first
# Gate replay after J-0084 went red on an assertion of "UNRULED" here.
_before = repoint.classify(_SELF)
_saved_prefixes = repoint.LIVE_PREFIXES
repoint.LIVE_PREFIXES = _saved_prefixes + (  # type: ignore[attr-defined]
    "docs/reviews/",
)
try:
    moves, unreadable, _unruled = repoint.parse(moved(_SELF, _marked_linenos[0]))
finally:
    repoint.LIVE_PREFIXES = _saved_prefixes  # type: ignore[attr-defined]
assert repoint.classify(_SELF) == _before, "LIVE_PREFIXES not restored"
row(
    "D. marker AND a register row IS skipped, and is not called unreadable",
    moves == {} and unreadable == [],
    f"line={_marked_linenos[0]} moves={moves!r} unreadable={unreadable!r}",
)

# E. END TO END, the arm the brief asks for. Take a file the live report
#    really names, make it unreadable, and run the real tool. It must
#    refuse (exit 1, says UNREADABLE) and must NOT report repointing
#    anything.
# A COMMIT SHA, not a credential. detect-secrets reads 40 hex
# characters as a "Hex High Entropy String" and cannot tell a git
# object from a key, so the mitigation the tool itself prints is
# used here. Marked INLINE rather than baselined: a baseline entry
# is invisible at the call site, and this repo has already watched
# the baseline be rewritten by the hook and then fail as unstaged.
SHA = "28be78adcca7f81e98307743640490f061fae3a9"  # pragma: allowlist secret
report_text = repoint.report(SHA)
cited = [
    m.group("file")
    for m in (repoint._MOVED.match(li) for li in report_text.splitlines())  # noqa: SLF001
    if m is not None
]
victim_rel = next(
    (c for c in cited if (REPO_ROOT / c).is_file() and c.endswith(".md")),
    None,
)
if victim_rel is None:
    row("E. end-to-end chmod refusal", False, "no cited .md file to use")
else:
    victim = REPO_ROOT / victim_rel
    before_mode = stat.S_IMODE(victim.stat().st_mode)
    before_bytes = victim.read_bytes()

    # A control on the control: the SAME command with the file readable
    # must NOT refuse, or row E proves nothing about the chmod.
    baseline = subprocess.run(
        [sys.executable, str(TOOL), SHA],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    row(
        "E0. readable baseline does NOT refuse (control on the control)",
        "UNREADABLE" not in baseline.stdout
        and "CHECKER FAILED" not in baseline.stdout
        and (
            re.search(r"\d+ citation\(s\) repointed", baseline.stdout) is not None
            or "UNRULED" in baseline.stdout
        ),
        f"rc={baseline.returncode} tail={baseline.stdout.strip().splitlines()[-1:]!r}",
    )

    try:
        os.chmod(victim, 0o000)
        # NOT an assert. `chmod 000` does not deny a process able to
        # override it - root, or CAP_DAC_OVERRIDE - and on a runner
        # this raised AssertionError, exiting non-zero with NO ROW
        # NAMED. CI reported "exit=1 failed=none", the least useful
        # thing a probe can say. The row REFUSES instead: it cannot be
        # measured where the permission is not enforced, and a refusal
        # is honest where a failure would be a lie about the subject.
        if os.access(victim, os.R_OK):
            os.chmod(victim, before_mode)
            row(
                "E. unreadable cited file -> REFUSED, not measured here",
                True,
                "chmod 000 did not deny this process (root or "
                "CAP_DAC_OVERRIDE), so the unreadable case cannot be "
                "staged here. NOTHING was tested by this row.",
            )
            print()
            if FAILURES:
                print(f"  {len(FAILURES)} row(s) did not behave: {FAILURES}")
                raise SystemExit(1)
            print("  rows ran; row E refused, see above.")
            raise SystemExit(0)
        run = subprocess.run(
            [sys.executable, str(TOOL), SHA],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=False,
        )
    finally:
        os.chmod(victim, before_mode)

    restored = os.access(victim, os.R_OK) and victim.read_bytes() == before_bytes
    # The victim is a file the UPSTREAM checker also has to read, so
    # chmod 000 kills the checker (it catches UnicodeDecodeError only)
    # and the report comes back empty. Before the fix that empty report
    # reached the parser and the tool blamed its own selector. It must
    # now say the checker failed, and say so by NAME.
    row(
        "E. unreadable cited file -> the tool REFUSES and repoints nothing",
        run.returncode == 1
        and "CHECKER FAILED" in run.stdout
        and "PermissionError" in run.stdout
        and "SELECTOR CONTROL" not in run.stdout
        and "citation(s) repointed" not in run.stdout,
        f"rc={run.returncode} victim={victim_rel} "
        f"tail={run.stdout.strip().splitlines()[-1:]!r}",
    )
    row(
        "E1. the probe restored the victim file (mode and bytes)",
        restored,
        f"mode={oct(before_mode)} bytes={len(before_bytes)}",
    )

print()
if FAILURES:
    print(f"  {len(FAILURES)} row(s) did not behave: {FAILURES}")
    raise SystemExit(1)
print("  every row behaved. The exempt check fails CLOSED.")
raise SystemExit(0)
