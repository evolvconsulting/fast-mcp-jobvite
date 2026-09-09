#!/usr/bin/env python3
"""Apply `check-design-citations.py --since <sha>`'s MOVED lines.

The companion to `check-design-citations.py`. That script SAYS which
citations moved; this one MOVES them, from that script's own parsed
output rather than from anything retyped, because retyping a value just
read is the step that has failed repeatedly here.

It refuses to guess:

  - It ignores BROKEN lines entirely. Those are citations whose target
    line CHANGED, and only a human re-reading the subject can repoint
    them.
  - It ignores any line carrying the marker `REPOINT-EXEMPT`. A script
    that WRITES an example citation - a regex test string, a docstring
    illustrating the two forms - is not CITING anything, and repointing
    it corrupts the example silently. Measured: the first pass of this
    batch shifted three of `check-design-citations.py`'s own examples.
  - It keys on (file, line-the-citation-sits-on, old-range), never on a
    naive string replacement, because a single line can carry several
    citations and `DESIGN.md:<n>` can be a prefix of `DESIGN.md:<nn>`.
  - It asserts it parsed a non-zero number of MOVED lines, and fails
    loudly if a citation the report named is not where the report said
    it was.

Usage:
    python3 docs/reviews/repoint-design-citations.py <sha> # dry run
    python3 docs/reviews/repoint-design-citations.py <sha> --write

Exit 0 on success, 1 if anything did not line up. No dependencies.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import repoint_exempt

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "docs" / "reviews" / "check-design-citations.py"
#: Every `--write` appends a row here: the base it moved FROM, the
#: DESIGN.md blob at that base, how many citations moved, the date. A
#: later run whose base carries the SAME blob would report the same
#: moves again and move every LIVE citation a second time, to a wrong
#: target: review round 3 of the 4.0.3 branch measured 73 such
#: re-reports after the first batch. That base is refused.
LOG = REPO_ROOT / "docs" / "reviews" / "REPOINT-LOG.txt"

#: {(old start, old end): (new start, new end)} for ONE cited line
Pairs = dict[tuple[int, int], tuple[int, int]]
#: {(file, line the citation sits on): Pairs}
MoveMap = dict[tuple[str, int], Pairs]

_CITATION = re.compile(r"DESIGN\.md:(\d+)(?:-(\d+))?")
_MOVED = re.compile(
    r"^\s*MOVED:\s+(?P<file>[^:]+):(?P<lineno>\d+): "
    r"DESIGN\.md:(?P<os>\d+)(?:-(?P<oe>\d+))? -> "
    r"DESIGN\.md:(?P<ns>\d+)(?:-(?P<ne>\d+))?\s*$"
)


class CheckerFailed(RuntimeError):  # noqa: N818 - a refusal, not an error
    """The checker did not run cleanly, so its report is not proof."""


def report(sha: str) -> str:
    """The checker's own output.

    Exit 1 is its normal state when moves exist.

    Which is exactly why the exit code cannot be the health check here.
    A crashed checker also exits 1, and this function used to keep only
    `.stdout`, so a traceback on stderr was discarded and an EMPTY
    report was indistinguishable from "nothing moved". Measured: chmod
    000 on one cited file raises PermissionError inside
    `check-design-citations.py` (it catches UnicodeDecodeError only),
    the report comes back empty, and the caller blames its own parser.
    The checker writes nothing to stderr in normal operation - 0 bytes
    over a run that emitted 970 MOVED lines - so anything on stderr is a
    fault, and a fault is refused.
    """
    proc = subprocess.run(
        [sys.executable, str(CHECKER), "--since", sha],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    if proc.stderr.strip():
        raise CheckerFailed(
            f"{CHECKER.name} exited {proc.returncode} and wrote to stderr, so "
            f"its report cannot be trusted. Nothing will be repointed.\n"
            f"{proc.stderr.rstrip()}"
        )
    return proc.stdout


#: #219. THE SINGLE PREFIX WAS AN ALLOWLIST WITH A SILENT DEFAULT, AND
#: THAT IS THE DEFECT, NOT ITS LENGTH. `docs/adr/` was skipped by name
#: and everything else was repointed - so a directory nobody had ruled
#: on got the LIVE treatment by accident rather than by decision. #208
#: measured 26 of its 35 leads sitting in `docs/reviews/` and
#: `docs/worklogs/`, which no ruling covers to this day.
#:
#: Lengthening the list rebuilds the defect one entry over: a named list
#: selects for the path nobody thought of. So the DEFAULT changes
#: instead. Three outcomes, and the unknown one REFUSES:
#:
#:   LIVE    the citation is a claim about the design AS IT IS, so a
#:           moved subject makes it wrong and repointing fixes it.
#:   RECORD  the citation is evidence for something already decided or
#:           already reported. Repointing rewrites the evidence. Ruled
#:           for `docs/adr/` (#203) and `docs/plans/` (#111).
#:   UNRULED everything else. NOT repointed, NOT silently skipped -
#:           reported, so the next person has to decide rather than
#:           inherit my default.
#:
#: I am DELIBERATELY NOT ruling docs/reviews, docs/worklogs or
#: docs/briefs here. A review report and a worklog LOOK like records and
#: I believe they are - but I have not read them, #208 handed me 26
#: leads there rather than a verdict, and a ruling made from a directory
#: name is exactly the reasoning this project keeps finding wrong. The
#: refusal is what makes leaving them undecided SAFE.
#:
#: RULED 2026-09-08 (JACK, evolv consensus/JACK.md J-0084), after
#: f608850 added ten lines to DESIGN.md section 10 and
#: `--since a9a85ed` reported 232 MOVED, 136 of them here. Read, not
#: inferred from a name: docs/worklogs and docs/archive hold reports
#: of work at a time and docs/briefs the briefs that dispatched it,
#: so all three are RECORD; docs/briefs/PREAMBLE.md is the live
#: working rule, LIVE, and the longest matching prefix wins so that
#: file ruling holds under the directory ruling. pyproject.toml and
#: .pre-commit-config.yaml describe the manifest and the hook config
#: as they are, LIVE. docs/reviews is mixed on purpose: a .py or .sh
#: there is an instrument that runs against the current tree (its own
#: examples carry REPOINT-EXEMPT and are skipped), LIVE; a .md or .txt
#: there is a review, a ruling, an audit or an evidence file, RECORD.
LIVE_PREFIXES = (
    "src/",
    "tests/",
    "scripts/",
    ".github/",
    "pyproject.toml",
    ".pre-commit-config.yaml",
    "docs/briefs/PREAMBLE.md",
)
RECORD_PREFIXES = (
    "docs/adr/",
    "docs/plans/",
    "docs/worklogs/",
    "docs/briefs/",
    "docs/archive/",
)
INSTRUMENT_DIRS = ("docs/reviews/",)
INSTRUMENT_SUFFIXES = (".py", ".sh")


def classify(path: str) -> str:
    """LIVE, RECORD or UNRULED.

    The unknown case is UNRULED on purpose - see the note above. The
    longest matching prefix wins, so a file ruled under a directory
    ruled the other way keeps its own ruling.
    """
    if path.startswith(INSTRUMENT_DIRS):
        return "LIVE" if path.endswith(INSTRUMENT_SUFFIXES) else "RECORD"
    live = max((p for p in LIVE_PREFIXES if path.startswith(p)), key=len, default="")
    record = max(
        (p for p in RECORD_PREFIXES if path.startswith(p)), key=len, default=""
    )
    if not live and not record:
        return "UNRULED"
    return "LIVE" if len(live) > len(record) else "RECORD"


def parse(
    text: str,
) -> tuple[
    dict[tuple[str, int], dict[tuple[int, int], tuple[int, int]]],
    list[str],
    list[str],
]:
    """Parse MOVED lines into a move map, plus the unruleable lines.

    The REPOINT-EXEMPT check FAILS CLOSED. If the cited file cannot be
    read, or does not have the line the report named, we do not know
    whether that line is exempt - and "unknown" must not resolve to "not
    exempt, go ahead and rewrite it". The old code swallowed OSError,
    IndexError and UnicodeDecodeError and fell through to the repoint,
    so an unreadable file was silently treated as non-exempt and got
    rewritten anyway. Unreadable lines are now collected and refused by
    the caller.
    """
    moves: dict[tuple[str, int], dict[tuple[int, int], tuple[int, int]]] = {}
    unreadable: list[str] = []
    records: list[str] = []
    unruled: list[str] = []
    for line in text.splitlines():
        m = _MOVED.match(line)
        if not m:
            continue
        # #203/#207: AN ADR IS A RECORD AND ITS CITATIONS ARE NOT
        # REPOINTED. An ADR states what was decided against the design
        # AS IT STOOD; moving its citations rewrites the evidence for a
        # decision already taken.
        #
        # MEASURED, and this is why the rule exists. `b0e86b8`
        # repointed ADR-0017's qualified citation `489-490 -> 495-496`
        # - correct at that moment - and could not see the SAME range
        # cited BARE three lines later, because this tool's report
        # requires a filename. `DESIGN.md` then moved again, so today
        # the repointed half is wrong and the untouched half is still
        # exactly what its author cited. THE HALF NOBODY REPOINTED IS
        # THE HALF THAT STILL MEANS WHAT IT SAID.
        #
        # THE SKIP IS PRINTED, NOT SILENT. A switched-off behaviour and
        # a broken one must not look identical - that shape hid 119 red
        # mirror runs on this project.
        verdict = classify(m["file"])
        if verdict == "RECORD":
            records.append(f"  RECORD, not repointed: {m['file']}:{m['lineno']}")
            continue
        if verdict == "UNRULED":
            unruled.append(f"  UNRULED: {m['file']}:{m['lineno']}")
            continue
        cited_in = pathlib.Path(REPO_ROOT / m["file"])
        try:
            cited_line = cited_in.read_text().splitlines()[int(m["lineno"]) - 1]
        except (OSError, IndexError, UnicodeDecodeError) as exc:
            unreadable.append(
                f"  UNREADABLE: {m['file']}:{m['lineno']}: {type(exc).__name__}: {exc}"
            )
            continue
        old_s = int(m["os"])
        old_e = int(m["oe"]) if m["oe"] else old_s
        # #142. This test USED to be `"REPOINT-EXEMPT" in cited_line`,
        # at LINE granularity. That was unreachable belt-and-braces
        # while the checker skipped the whole line before emitting a
        # MOVED row for it - and it becomes a live over-suppression the
        # moment the checker skips only the exempt CITATION: a line
        # with one registered citation and one ordinary one would emit
        # a MOVED row that this test then silently refused to apply.
        if repoint_exempt.is_exempt(cited_line, m["file"], old_s, old_e):
            continue
        new_s = int(m["ns"])
        new_e = int(m["ne"]) if m["ne"] else new_s
        key = (m["file"], int(m["lineno"]))
        moves.setdefault(key, {})[(old_s, old_e)] = (new_s, new_e)
    if records:
        print(f"\n{len(records)} citation(s) sit in RECORD paths and are NOT")
        print("repointed (docs/adr/, docs/plans/, docs/worklogs/, docs/briefs/,")
        print("docs/archive/, and documents under docs/reviews/; the ruling is")
        print("above LIVE_PREFIXES). A deliberate skip, printed so it cannot be")
        print("mistaken for the tool failing:")
        print("\n".join(records))
    return moves, unreadable, unruled


def apply(moves: MoveMap, write: bool) -> int:
    by_file: dict[str, dict[int, Pairs]] = {}
    for (rel, lineno), pairs in moves.items():
        by_file.setdefault(rel, {})[lineno] = pairs

    applied = missed = 0
    for rel, lines in sorted(by_file.items()):
        path = REPO_ROOT / rel
        text = path.read_text().splitlines(keepends=True)
        for lineno, pairs in lines.items():
            seen: set[tuple[int, int]] = set()

            # ruff B023: `sub` closes over the loop variables `pairs`
            # and `seen` without binding them. That is SAFE HERE and the
            # shape is deliberate: `sub` is never stored, never deferred
            # and never passed anywhere that outlives this iteration -
            # it is handed straight to `_CITATION.sub(...)` on the next
            # statement, which calls it synchronously and discards it
            # before the loop advances. `seen` is then read on the line
            # after that, still in the same iteration.
            #
            # It is fragile rather than wrong: collecting these
            # callables into a list to run later would silently make
            # every one of them use the LAST iteration's `pairs`, and
            # repoint every citation in the tree against the wrong map.
            # If this loop
            # ever stops invoking `sub` on the very next line, bind the
            # two values as default arguments instead of restructuring
            # around it.
            def sub(m: re.Match[str]) -> str:
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else start
                target = pairs.get((start, end))  # noqa: B023 - see above
                if target is None:
                    return m.group(0)
                seen.add((start, end))  # noqa: B023 - see above
                ns, ne = target
                return f"DESIGN.md:{ns}" + (f"-{ne}" if ne != ns else "")

            original = text[lineno - 1]
            text[lineno - 1] = _CITATION.sub(sub, original)
            unseen = set(pairs) - seen
            if unseen:
                missed += len(unseen)
                print(
                    f"  NOT FOUND: {rel}:{lineno}: the report named "
                    f"{sorted(unseen)} but that line does not carry it"
                )
            applied += len(seen)
        if write:
            path.write_text("".join(text))

    print(
        f"\n  {applied} citation(s) repointed across {len(by_file)} file(s)"
        f"{'' if write else ' (DRY RUN, nothing written)'}"
    )
    if missed:
        print(
            f"  {missed} the report named and the tree does not carry. NOTHING IS "
            f"TRUSTWORTHY."
        )
        return 1
    return 0


def design_blob(sha: str) -> str:
    """The blob id of docs/DESIGN.md at `sha`, or "" if git cannot."""
    done = subprocess.run(
        ["git", "rev-parse", f"{sha}:docs/DESIGN.md"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    return done.stdout.strip() if done.returncode == 0 else ""


def already_moved_from(sha: str) -> str | None:
    """The log row whose base carries the same DESIGN.md as `sha`."""
    if not LOG.exists():
        return None
    blob = design_blob(sha)
    for row in LOG.read_text(encoding="utf-8").splitlines():
        if not row.strip() or row.startswith("#"):
            continue
        base, logged_blob, *_ = row.split("\t")
        if blob and blob == logged_blob:
            return row
    return None


def record_write(sha: str, moved: int) -> None:
    """Append this --write to the log, so the base cannot be reused."""
    date = subprocess.run(
        ["date", "+%Y-%m-%d"], capture_output=True, text=True, check=True
    ).stdout.strip()
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{sha}\t{design_blob(sha)}\t{moved}\t{date}\n")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    sha = argv[0]
    prior = already_moved_from(sha)
    if prior:
        print(
            f"  REFUSED: docs/DESIGN.md at {sha!r} is the blob a previous --write "
            "already repointed FROM:\n"
            f"  {prior}\n"
            "  A second run from that base moves every LIVE citation again, to a "
            "wrong target. Use --since a base at or after the commit that carried "
            "that write."
        )
        return 1
    try:
        text = report(sha)
    except CheckerFailed as exc:
        print(f"  CHECKER FAILED: {exc}")
        return 1
    moves, unreadable, unruled = parse(text)
    if unruled:
        print("\n".join(unruled))
        print(
            f"  {len(unruled)} citation(s) live in a directory NOBODY HAS "
            "RULED on. Refusing to repoint anything.\n"
            "  This is not a bug and it is not a missing entry in a list. "
            "Whether a directory holds RECORDS (evidence for something "
            "already decided, which repointing would rewrite) or LIVE "
            "claims about the design as it is, is a DECISION - and the "
            "single-prefix skip this replaced made that decision by "
            "accident for every directory except docs/adr/.\n"
            "  Rule the directory, add it to LIVE_PREFIXES or "
            "RECORD_PREFIXES with the ruling named, and run again."
        )
        return 1
    if unreadable:
        print("\n".join(unreadable))
        print(
            f"  {len(unreadable)} cited line(s) could not be read, so whether "
            "they carry REPOINT-EXEMPT is UNKNOWN. Refusing to repoint "
            "anything: an unknown must not resolve to 'not exempt'."
        )
        return 1
    total = sum(len(v) for v in moves.values())
    if total == 0:
        print(
            "SELECTOR CONTROL: parsed 0 MOVED lines out of "
            f"{len(text.splitlines())} lines of report. The parser is broken, "
            "or there is genuinely nothing to move. Check the report by eye."
        )
        return 1
    print(f"  parsed {total} MOVED citation(s) from the checker's output")
    rc = apply(moves, write="--write" in argv)
    if rc == 0 and "--write" in argv:
        record_write(sha, total)
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
