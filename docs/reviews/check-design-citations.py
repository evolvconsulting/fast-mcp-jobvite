#!/usr/bin/env python3
"""Every `DESIGN.md:N` citation points at a line that exists.

After an edit it also says which ones moved.

**Why this exists, and why now.** Three citations to `DESIGN.md` have
been found pointing at the wrong lines, none of them by a gate. The line
numbers below are the ones in the object frozen at `135c3ac`, where the
defects were found. A record of where a defect WAS does not move, so
each carries the marker:

  - `DESIGN.md:603` cited a section that does not exist. ADR-0019.
    REPOINT-EXEMPT
  - `DESIGN.md:918-923` was contracted by one line. REPOINT-EXEMPT. It
    dropped the `http` transport row §7.2 leans on - found by U1, in a
    brief I wrote.
  - Three separate citations of the three runtime pins pointed nine
    lines above them, at the prose paragraph about the resolve - found
    by U4.

`check-cross-references.py` cannot see any of these: it validates `§n.m`
SECTION pointers, and these are `file:line` RANGES. **Nothing checks a
line range at all.**

A contracted range is the sharper failure. A dangling one announces
itself; a contracted one still resolves, still quotes accurately, and
lands the reader on text that reads exactly like it could be the
subject.

WHAT THIS CAN AND CANNOT DO, stated plainly because the gap matters:

  It CAN check that a cited line exists, and it CAN say which citations
  a given edit to DESIGN.md moved, and where to.

  It CANNOT check that a range CONTAINS ITS SUBJECT. That needs a
  subject recorded beside the citation, which is what
  `docs/OBLIGATIONS.md` does for its 28 rows and what task #30 proposes
  generalising. **A green here means "the citation resolves", never "the
  citation is right"** - which is exactly the distinction that let all
  three defects above survive.

THE `--since` MODE IS THE POINT. `docs/DESIGN.md`'s freeze SHA lives in
`docs/DESIGN-FREEZE.txt` and is not retyped here - it was retyped
once, the design moved at `86ab20e`, and every copy went on naming
the old object.
REPOINT-EXEMPT for the addresses above. That edit shifts an unknown
number of the citations in this tree, and there are 841 of them (by this
script, not by the grep I first reached for, which said 836). Run:

    python3 docs/reviews/check-design-citations.py \
        --since "$(cat docs/DESIGN-FREEZE.txt)"

before and after, and it maps old line numbers to new ones through a
real diff, then reports every citation whose target moved. Without it,
applying those ADRs means either re-checking them by hand or shipping
them unverified. MEASURED: a five-line insertion at line 300 moves 723
of the 841.

Usage:
    python3 docs/reviews/check-design-citations.py # bounds + inventory
    python3 docs/reviews/check-design-citations.py --since <sha> python3
    docs/reviews/check-design-citations.py --controls

Exit 0 when every citation resolves, 1 otherwise. No dependencies.
"""

from __future__ import annotations

import contextlib
import difflib
import io
import pathlib
import re
import subprocess
import sys

import repoint_exempt

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DESIGN = REPO_ROOT / "docs" / "DESIGN.md"
FREEZE = REPO_ROOT / "docs" / "DESIGN-FREEZE.txt"
PYPROJECT = REPO_ROOT / "pyproject.toml"

# Examples, REPOINT-EXEMPT: `DESIGN.md:603`, `DESIGN.md:918-924` - these
# are what the pattern MATCHES, not citations of anything, so they must
# not move. The filename is required so this does not match a bare
# number, and `docs/DESIGN.md:` forms are caught by the same pattern.
_CITATION = re.compile(r"DESIGN\.md:(\d+)(?:-(\d+))?")

_SEARCH_SUFFIXES = {".py", ".toml", ".md", ".yml", ".yaml", ".sh"}
_SKIP_PARTS = {".git", ".venv", "venv", "__pycache__", ".ruff_cache", ".pytest_cache"}


def _stderr_of(exc: BaseException) -> str:
    """The captured stderr of a failed subprocess, ready to append.

    `CalledProcessError.__str__` reports only "returned non-zero exit
    status N" and drops the output entirely, so a refusal built from
    the exception alone names the exit code and not the cause. Round 3
    found the two refusals below doing exactly that while
    `_report_moves` a few lines away surfaced `git show`'s stderr
    properly. Returns "" when there is nothing to add, so the caller
    can concatenate unconditionally.
    """
    text = getattr(exc, "stderr", None)
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    return f": {text.strip()}" if isinstance(text, str) and text.strip() else ""


def _tracked_files() -> list[pathlib.Path]:
    """Every tracked file worth scanning.

    `git ls-files` is the authority.

    THIS HAS EXACTLY ONE CALL SITE, `main`'s precondition, and every
    arm takes the result as an argument. Round 3 found the reason:
    a guard that proves `git --version` runs proves nothing about
    `git ls-files`, and with only the latter broken both scan arms
    raised a bare `CalledProcessError` at exit 1. One call site inside
    one try/except is the shape that cannot be reached unguarded.

    An earlier version was amputated for the negative control by
    rebinding this name in the module globals. That seam is gone;
    the control passes an empty list instead, which tests the same
    property without a monkeypatch.
    """
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=True,
    ).stdout
    files = []
    for name in out.split("\0"):
        if not name:
            continue
        path = REPO_ROOT / name
        if path.suffix not in _SEARCH_SUFFIXES:
            continue
        if any(part in _SKIP_PARTS for part in pathlib.Path(name).parts):
            continue
        files.append(path)
    return files


#: A line carrying this marker is an EXAMPLE of a citation, not a
#: citation OF anything - the repoint tool and
#: `check-design-citation-shape.py` both honour it, and this file's own
#: docstring uses it. THIS CHECKER DID NOT, which is the asymmetry:
#: `REVIEW-R10.md` quotes the deliberately-out-of-bounds citations its
#: probe planted, as EVIDENCE, and one of those lines already carried
#: the marker and was flagged anyway. A wired gate went red on a report
#: describing the very defect the gate looks for - the sixth time in one
#: day a checker has found the document that documents it.
EXEMPT_MARKER = repoint_exempt.MARKER
#: CITATIONS skipped, not LINES. #142 changed the unit deliberately:
#: the old line count reported 51 while 36 of those lines carried no
#: citation at all, so the number that was supposed to make the
#: exemption visible was mostly counting prose about the exemption.
EXEMPT_SKIPPED = 0

#: BOTH scan arms print this and exit non-zero on an empty corpus. An
#: empty corpus is a BROKEN SELECTOR and never a clean tree. It is a
#: constant so `--controls` can assert this exact string: a control
#: that accepted any non-zero would also pass on a shallow checkout's
#: exit 3, which is a different failure entirely.
EMPTY_CORPUS = (
    "SELECTOR CONTROL: no DESIGN.md citations found anywhere. The "
    "pattern is broken, not the corpus."
)


def citations(
    tracked: list[pathlib.Path],
) -> list[tuple[pathlib.Path, int, int, int]]:
    """Every citation as (file, line-it-appears-on, start, end).

    `tracked` is the enumeration `main` already ran and validated.

    Lines marked `REPOINT-EXEMPT` are skipped and COUNTED, so the
    exemption can never be silent - a skip nobody reports is how a
    population shrinks without anyone noticing.
    """
    found: list[tuple[pathlib.Path, int, int, int]] = []
    global EXEMPT_SKIPPED
    EXEMPT_SKIPPED = 0
    for path in tracked:
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in _CITATION.finditer(line):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else start
                # #142: the marker selects the LINE and the register
                # grants the CITATION. Neither alone is an exemption,
                # and anything else on the line stays in the
                # population - which is the granularity half of R13-H1.
                if repoint_exempt.is_exempt(line, rel, start, end):
                    EXEMPT_SKIPPED += 1
                    continue
                found.append((path, lineno, start, end))
    return found


def line_map(old_text: str, new_text: str) -> dict[int, int | None]:
    """Map each 1-based line of `old_text` into `new_text`, or None.

    None means the line was deleted or changed, so a citation pointing
    at it can no longer be resolved automatically and needs a human.
    """
    old = old_text.splitlines()
    new = new_text.splitlines()
    mapping: dict[int, int | None] = {}
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, i1, i2, j1, _ in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                mapping[i1 + offset + 1] = j1 + offset + 1
        elif tag in ("replace", "delete"):
            for i in range(i1, i2):
                mapping[i + 1] = None
    return mapping


def _report_bounds(total_lines: int, tracked: list[pathlib.Path]) -> int:
    found = citations(tracked)
    if not found:
        print(EMPTY_CORPUS)
        return 1

    bad = [
        f"{p.relative_to(REPO_ROOT)}:{ln}: DESIGN.md:{s}"
        + (f"-{e}" if e != s else "")
        + f" is past the end of DESIGN.md ({total_lines} lines)"
        for p, ln, s, e in found
        if s > total_lines or e > total_lines or s < 1 or e < s
    ]
    print(
        f"  {len(found)} DESIGN.md citations across "
        f"{len({p for p, _, _, _ in found})} files"
    )
    print(f"  highest line cited: {max(e for _, _, _, e in found)} of {total_lines}")
    # R13-H1: THIS LINE DID NOT EXIST AND THE DOCSTRING SAID IT DID.
    # `citations()` says skips are "COUNTED, so the exemption can never
    # be silent - a skip nobody reports is how a population shrinks
    # without anyone noticing." EXEMPT_SKIPPED was assigned, reset and
    # incremented - and READ NOWHERE. I wrote both the counter and the
    # claim, on the same day, and never ran the check it describes.
    #
    # The review proved the consequence with a plant: a line reading
    # `DESIGN.md:99999-99999 REPOINT-EXEMPT` passes THIS gate and the
    # shape gate, both exit 0, nothing printed - a citation 97,866
    # lines past the end of a 2133-line file.
    print(f"  citations exempt (marked AND registered): {EXEMPT_SKIPPED}")
    print(repoint_exempt.report())
    if bad:
        print(f"\n{len(bad)} problem(s):")
        for b in bad:
            print(f"  FAIL: {b}")
        return 1
    print("\nEvery citation resolves to a line that exists.")
    print(
        "NOTE: that is NOT the same as pointing at the right line. This checker "
        "cannot see a contracted range; three have been found by hand."
    )
    return 0


def _report_moves(sha: str, new: str, tracked: list[pathlib.Path]) -> int:
    # `check=True` USED TO RAISE HERE, and the traceback it produced
    # cost three CI rounds to read. On a SHALLOW checkout the blob is
    # simply absent, `git show` exits 128, and CalledProcessError
    # propagated out of a probe two layers up - where it surfaced as
    # `exit=1 failed=none`, which names nothing at all.
    #
    # A MISSING OBJECT IS A BROKEN INSTRUMENT, NOT A FINDING, and the
    # two must not share an exit code. `check-design-freeze.py` already
    # says this for the same cause; here is its sibling learning it.
    done = subprocess.run(
        ["git", "show", f"{sha}:docs/DESIGN.md"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    if done.returncode != 0:
        detail = done.stderr.strip()
        print(f"git show {sha}:docs/DESIGN.md failed: {detail}")
        # THE PHRASING IS THE WHOLE TRICK, and my first version missed
        # the one git actually emits. A depth-1 clone that HAS the path
        # but not the commit says "exists on disk, but not in <sha>" -
        # not "bad object", which is what a wholly unknown ref gets.
        # Matching only the second left the hint silent in the exact
        # case it was written for; a local shallow-clone control is
        # what showed that.
        missing = (
            "bad object",
            "unknown revision",
            "exists on disk, but not in",
            "does not exist",
        )
        if any(phrase in detail for phrase in missing):
            print(f"THE COMMIT {sha[:7]} IS NOT IN THIS CLONE. That is almost")
            print("always a SHALLOW checkout - `actions/checkout` defaults to")
            print("fetch-depth 1 and cannot see it. Set `fetch-depth: 0` on the")
            print("job. It is NOT evidence that any citation moved.")
        print("This is a BROKEN INSTRUMENT, not a finding. Exit 3.")
        return 3
    old = done.stdout
    # AN EMPTY CORPUS IS A BROKEN INSTRUMENT HERE TOO, AND THIS ARM DID
    # NOT SAY SO. `_report_bounds` has refused one since it was written.
    # This arm computed `citations()` at the loop below, so with
    # `_tracked_files()` returning nothing it printed "0 citation(s)
    # moved, 0 point at changed lines" and exited 0 - where the same
    # run with the enumeration intact reported 1618 moved and 55
    # pointing at changed lines, and exited 1. Measured 2026-09-09
    # against 28be78a by patching the enumerator to return an empty
    # list. Board row 23.
    #
    # POSITION IS LOAD-BEARING. Below the `git show`, so a shallow
    # checkout still gets its own message and its own exit 3; above the
    # byte-identical short circuit, which answers "no citation can have
    # moved" without ever asking whether there are any.
    found = citations(tracked)
    if not found:
        print(EMPTY_CORPUS)
        return 1
    if old == new:
        print(f"DESIGN.md is byte-identical to {sha}. No citation can have moved.")
        return 0

    mapping = line_map(old, new)
    moved: list[str] = []
    broken: list[str] = []
    for path, lineno, start, end in found:
        new_start, new_end = mapping.get(start), mapping.get(end)
        rel = path.relative_to(REPO_ROOT)
        cited = f"DESIGN.md:{start}" + (f"-{end}" if end != start else "")
        if new_start is None or new_end is None:
            broken.append(
                f"{rel}:{lineno}: {cited} - that line CHANGED; a human "
                "must re-read the subject"
            )
        elif (new_start, new_end) != (start, end):
            new_cited = f"DESIGN.md:{new_start}" + (
                f"-{new_end}" if new_end != new_start else ""
            )
            moved.append(f"{rel}:{lineno}: {cited} -> {new_cited}")

    print(
        f"  against {sha}: {len(moved)} citation(s) moved, "
        f"{len(broken)} point at changed lines"
    )
    for line in broken:
        print(f"  BROKEN: {line}")
    for line in moved:
        print(f"  MOVED:  {line}")
    return 1 if (moved or broken) else 0


def controls(text: str, tracked: list[pathlib.Path]) -> int:
    """Prove each check can go red, on real content.

    `text` is docs/DESIGN.md and `tracked` is the file enumeration,
    both already obtained and validated by `main`. Round 2 found
    this function re-reading DESIGN.md, so the claim that one guard
    covered three read sites was true only for a file unreadable at
    START; round 3 found the same shape in the enumeration. Taking
    both values makes the claim true and leaves each with a single
    guarded call site.
    """
    fired = total = 0

    total += 1
    mapping = line_map(text, "inserted\n" + text)
    if mapping.get(10) == 11:
        fired += 1
        print("  CONTROL an inserted line shifts the map -> FIRED")
    else:
        print(
            f"  CONTROL an inserted line shifts the map -> DID NOT FIRE "
            f"(got {mapping.get(10)})"
        )

    total += 1
    lines = text.splitlines()
    lines[9] = "THIS LINE IS REPLACED"
    if line_map(text, "\n".join(lines)).get(10) is None:
        fired += 1
        print("  CONTROL a changed line maps to None -> FIRED")
    else:
        print("  CONTROL a changed line maps to None -> DID NOT FIRE")

    total += 1
    if _CITATION.findall("see DESIGN.md:918-924 and DESIGN.md:603"):  # REPOINT-EXEMPT
        fired += 1
        print("  CONTROL the pattern reads both forms -> FIRED")
    else:
        print("  CONTROL the pattern reads both forms -> DID NOT FIRE")

    # THE THREE CONTROLS ABOVE NEVER TOUCH THE CORPUS. They exercise
    # the pattern and the line map against hardcoded strings, so with
    # `_tracked_files()` returning nothing this arm still printed
    # "3/3 controls fired." at exit 0 while the real scan had no file
    # to read. Measured 2026-09-09, both checkers, same amputation: this
    # arm did not move at all and the sibling
    # `check-design-citation-shape.py --controls` went 7/7 exit 0 to
    # 6/7 exit 1. Board row 23. A controls arm blind to its own
    # population certifies a checker that is scanning nothing.
    # THE READ IS GUARDED BECAUSE A BROKEN INSTRUMENT MUST NOT WEAR A
    # FINDING'S EXIT CODE. `_tracked_files()` runs `git ls-files` with
    # `check=True`, so a git that cannot run raised CalledProcessError
    # as a bare traceback at exit 1 - and 1 is this checker's code for
    # "a citation does not resolve".
    #
    # AND IT NAMES MEMBERS, BECAUSE SIZE ALONE CANNOT SEE A NARROWED
    # SELECTOR. Review round 1 dropped ".md" from _SEARCH_SUFFIXES and
    # the real scan fell from 2101 citations across 239 files to 916
    # across 92 with nothing going red. MY FIRST FIX FOR THAT WAS ALSO
    # BLIND: it required every suffix in _SEARCH_SUFFIXES to appear in
    # the enumeration, which is derived from the very declaration the
    # mutation narrows, so it shrank with it and still read 5/5 at
    # exit 0. Measured, not reasoned. The members below are named
    # instead, and each is a module constant rather than a retyped
    # path, so none of them decays on its own.
    #
    # WHAT THIS DOES NOT REACH, and round 2 measured it wider than the
    # first statement of it admitted. This control proves the
    # enumeration RUNS and REACHES three named members. It does not
    # BOUND the corpus, so any narrowing that keeps those three is
    # invisible to it: dropping ".yml", ".yaml" or ".sh" from the
    # declared suffixes, and also a widened `_SKIP_PARTS`. Measured:
    # excluding five of this repository's own RECORD directories took
    # the corpus from 557 files to 347 and the citations from 2101 to
    # 1561, a quarter of them gone, while this arm still printed "5/5
    # controls fired." at exit 0.
    #
    # NO FLOOR IS ADDED FOR IT, deliberately. A count here would be a
    # second copy of a number that moves with every commit, which is the
    # decay this repository has paid for repeatedly; bounding the corpus
    # is a different property and wants its own instrument rather than a
    # constant in this one. The gap is recorded rather than papered
    # over.
    #
    # THIS ARM NO LONGER GUARDS THE ENUMERATION and does not need to:
    # `main` runs it before dispatch and returns 3 if it fails, so an
    # enumeration this arm cannot trust never reaches it. That is
    # STRONGER than the version round 2 reviewed, which reported DID
    # NOT FIRE and carried on to print a count: a broken enumerator now
    # produces no controls verdict at all rather than a partial one.
    total += 1
    here = pathlib.Path(__file__).resolve()
    must = {here: "this checker", DESIGN: "DESIGN.md", PYPROJECT: "pyproject.toml"}
    gone = [name for path, name in must.items() if path not in tracked]
    if tracked and not gone:
        fired += 1
        print(
            f"  CONTROL the corpus is enumerated ({len(tracked)} files, "
            f"all {len(must)} named members present) -> FIRED"
        )
    else:
        why = f"{len(tracked)} file(s)"
        if gone:
            why += f", MISSING: {', '.join(gone)}"
        print(f"  CONTROL the corpus is enumerated -> DID NOT FIRE ({why})")

    # AND THE NEGATIVE ARM, because a control that can only pass is the
    # same defect one column over: the arm above would fire on any
    # non-empty list, including one that had lost every file but this
    # one. Here the enumeration is amputated and BOTH scan arms must
    # refuse, by the exact message rather than by a bare non-zero.
    # `--since` is given the frozen SHA, read and never retyped, so the
    # arm needs no historical commit of its own.
    # SAME GUARD, SAME REASON. The frozen SHA is the only sha this arm
    # can reach without retyping a historical commit, and reading it was
    # unguarded: with docs/DESIGN-FREEZE.txt moved aside the arm raised
    # FileNotFoundError as a bare traceback at exit 1. Reported by the
    # template's port of this change, 8659780 on
    # chore/carried-machinery.
    total += 1
    try:
        frozen = FREEZE.read_text(encoding="utf-8").strip()
    except OSError as exc:
        print(
            "  CONTROL an amputated enumeration is REFUSED by both arms -> "
            f"DID NOT FIRE (DESIGN-FREEZE.txt is missing, so --since has no "
            f"sha: {exc})"
        )
    else:
        # AN EMPTY LIST *IS* THE AMPUTATED ENUMERATION, passed straight
        # in. The previous version rebound `_tracked_files` in the
        # module globals to do this; round 3's fix threads the
        # enumeration through instead, so the seam is gone and with it
        # the risk that a future refactor captures or inlines the name
        # and silently defeats the control.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            bounds_rc = _report_bounds(len(text.splitlines()), [])
            moves_rc = _report_moves(frozen, text, [])
        said = buf.getvalue().count(EMPTY_CORPUS)
        if (bounds_rc, moves_rc, said) == (1, 1, 2):
            fired += 1
            print("  CONTROL an amputated enumeration is REFUSED by both arms -> FIRED")
        else:
            print(
                f"  CONTROL an amputated enumeration is REFUSED by both arms -> "
                f"DID NOT FIRE (bounds rc={bounds_rc}, --since rc={moves_rc}, "
                f"{said} of 2 refusals printed)"
            )

    print(f"\n{fired}/{total} controls fired.")
    return 0 if fired == total else 1


def main(argv: list[str]) -> int:
    # ARGV IS READ BY POSITION, NOT BY MEMBERSHIP, and review round 1
    # found why that matters. `repoint-design-citations.py` takes its
    # SHA positionally and shells out to `--since <sha>`, so running
    # that tool as `--controls` built `--since --controls` here - and
    # the old `"--controls" in argv` matched the VALUE of `--since` and
    # ran the self-test instead of a scan. It exited 1 either way, which
    # is how a wrong mechanism kept a right-looking exit code. `git
    # rev-parse --controls:docs/DESIGN.md` exits 0 and echoes the string
    # back, so the sibling tool's own blob guard never fired on it
    # either.
    mode = argv[0] if argv else ""

    # DESIGN.md IS READ BY EVERY ARM AND WAS GUARDED BY NONE. Moving it
    # aside gave a bare FileNotFoundError at exit 1 on all three arms,
    # and 1 is this checker's code for "a citation does not resolve", so
    # an instrument that could not run wore a finding's exit code. EXIT
    # 3 is what this file already reserves for that distinction:
    # `_report_moves` returns it for a blob git cannot read, saying
    # "This is a BROKEN INSTRUMENT, not a finding."
    #
    # THE GUARD IS HERE, and after round 2's fold there is exactly one
    # read: `controls` and `_report_moves` take the text rather than
    # re-reading it. `main` is the only entry point - `__main__` calls
    # it and nothing imports this module - so proving the file readable
    # once before dispatch covers every arm. It catches an
    # unreadable-but-present file too, which a bare `exists()` test
    # would not.
    #
    # This paragraph named "the three read sites (:299 ..., :336 ...)"
    # until round 3; the fold that removed two of them left the
    # sentence describing a file that no longer existed, which is the
    # decay this repository rewrites in place rather than annotating.
    try:
        design_text = DESIGN.read_text()
    except OSError as exc:
        if mode == "--controls":
            print(
                "REFUSED: docs/DESIGN.md could not be read, so no control "
                f"can run: {exc}"
            )
        else:
            print(
                "REFUSED: docs/DESIGN.md could not be read, so nothing was "
                f"scanned: {exc}"
            )
        return 3

    # AND THE ENUMERATION MUST RUN, which is the third turn of one
    # screw and the last one it has. Round 1 guarded ONE call site, the
    # positive control arm's. Round 2 found the two scan arms and the
    # negative arm still crashed when `git` was absent, and added a
    # `git --version` probe here. Round 3 found that probe proves the
    # BINARY LAUNCHES and nothing about the CALL: with a git whose
    # `ls-files` fails and whose other subcommands work, both scan arms
    # raised a bare `CalledProcessError` at exit 1 again. Reproduced
    # against the real `/usr/bin/git` under a bogus `GIT_DIR`, with no
    # stub at all: `git --version` exits 0, `git ls-files` exits 128.
    #
    # A PROXY FOR A DEPENDENCY IS NOT THE DEPENDENCY. So this runs the
    # actual enumeration, once, and every arm takes the result. There
    # is no second, independently-failing call left to guard.
    #
    # SAME CAVEAT AS THE READ ABOVE, stated rather than implied: this
    # proves the enumeration ran when the run started. Nothing here
    # re-runs it, so unlike the previous two versions there is no later
    # moment at which the same command can fail differently.
    try:
        tracked = _tracked_files()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(
            "REFUSED: the tracked-file enumeration could not run, so "
            f"nothing can be scanned: {exc}{_stderr_of(exc)}"
        )
        return 3

    if mode == "--controls":
        return controls(design_text, tracked)
    if mode == "--since":
        # The old form indexed past the end of argv and raised
        # IndexError as a bare traceback; same class as the reads above.
        if len(argv) < 2:
            print("REFUSED: --since needs a commit-ish argument")
            return 3
        return _report_moves(argv[1], design_text, tracked)
    return _report_bounds(len(design_text.splitlines()), tracked)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
