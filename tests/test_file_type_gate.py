"""U15 - the committed-file-type gate.

`DESIGN.md:1724-1734`, threat row C8-I1.

**How this suite is built to be falsifiable in BOTH directions**,
because a refusal-only suite is green against a gate that refuses
everything, and a permission-only suite is green against a gate that
permits everything:

- Every refusal assertion has a **partner** asserting an ordinary file
  of the same shape is permitted.
  `test_an_ordinary_python_file_is_permitted` and the other
  `_is_permitted` tests are the whole of the "permits everything"
  defence; delete them and a `classify` returning a constant string
  passes the rest.
- Every permission assertion is paired with the refusal it must not
  swallow.
- The end-to-end arms drive **`git commit` itself** against an installed
  hook in a throwaway repository, so they test the gate as it is
  actually invoked rather than a function called the way its author had
  in mind.

**The gate's stated ceiling is not tested here and must not be**
(`DESIGN.md:1732-1734`): it stops a *file* of the wrong type. It does
nothing about confidential prose pasted into Markdown, which is the
incident that actually happened.
`test_the_gate_does_NOT_stop_confidential_prose_in_markdown` pins that
limit as a fact so nobody later reads this suite as closing it.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import subprocess
import sys
import types

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GATE_PATH = REPO_ROOT / "scripts" / "check-committed-file-types.py"

# A real, structurally valid one-page PDF. Not the bare 5-byte magic
# string: a test that only ever sees `b"%PDF-"` proves the gate matches
# a literal, not that it refuses the class of file that actually leaked.
REAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R>>endobj\n"
    b"4 0 obj<</Length 46>>stream\nBT /F1 24 Tf 72 700 Td (CONFIDENTIAL) Tj ET\nendstream endobj\n"  # noqa: E501
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


def _load_gate() -> types.ModuleType:
    """Import the gate by path.

    Its filename is hyphenated and not a module.
    """
    spec = importlib.util.spec_from_file_location("u15_gate", GATE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


# ----------------------------------------------------------------------
# The instrument itself. If the gate file is missing or unreadable, a
# glob-style suite over it passes vacuously - U0-REPORT section 7 named
# that trap and this is the same control one unit later.
# ----------------------------------------------------------------------


def test_the_gate_script_exists_and_is_executable_and_is_not_empty() -> None:
    assert GATE_PATH.is_file(), (
        f"{GATE_PATH} does not exist; every test below is vacuous"
    )
    assert GATE_PATH.stat().st_mode & 0o111, "the gate is not executable"
    # Not decoration. A ZERO-BYTE Python file runs and exits 0, so an
    # empty gate is indistinguishable from a working one to anything
    # that only reads an exit code. The amputation harness's tree B is
    # exactly this case.
    assert GATE_PATH.stat().st_size > 1000, "the gate is empty or a stub"


def test_the_rule_tables_are_populated() -> None:
    """A gate with empty tables permits everything and 'runs'."""
    assert len(gate.ALLOWED_EXTENSIONS) >= 10
    assert len(gate.DENIED_EXTENSIONS) >= 10
    assert len(gate.MAGIC) >= 10
    assert ".pdf" in gate.DENIED_EXTENSIONS
    assert ".raml" in gate.DENIED_EXTENSIONS


# ----------------------------------------------------------------------
# POSITIVE CONTROLS. These are what stop the suite passing against a
# gate that refuses everything. Named as such so a future editor does
# not "tidy" them.
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "path, data",
    [
        ("src/fast_mcp_jobvite/server.py", b"def main() -> None:\n    pass\n"),
        ("docs/DESIGN.md", b"# Design\n\nOrdinary prose.\n"),
        ("pyproject.toml", b'[project]\nname = "x"\n'),
        (".github/workflows/ci.yml", b"on: [push]\n"),
        ("uv.lock", b"version = 1\n"),
        (".gitignore", b".env\n"),
        ("LICENSE", b"Apache License\n"),
        ("NOTICE", b"evolv Consulting\n"),
        (".env.example", b"JOBVITE_API_KEY=\n"),
        # The regression that the two shipped gates refused each other
        # on: detect-secrets needs this file committed and `.baseline`
        # is not an extension anyone would think to allowlist.
        (".secrets.baseline", b'{"results": {}}\n'),
    ],
)
def test_an_ordinary_repository_file_is_permitted(path: str, data: bytes) -> None:
    assert gate.classify(path, data) is None, (
        f"{path} was refused but must be permitted"
    )


# ----------------------------------------------------------------------
# Rule 1 - extension denylist, and rule 2 - allowlist-first.
# ----------------------------------------------------------------------


# These two assert the DENYLIST's own message, not merely "was refused".
#
# Why the message and not the refusal: rule 1 is redundant with rule 2
# today and the gate says so at its own definition - neither `.pdf` nor
# `.raml` is on the allowlist either, so removing them from the denylist
# entirely still produces a refusal, just a different one. The mutation
# harness caught this: an earlier version of these two tests asserted
# only `".pdf" in reason`, which the rule-2 message ALSO satisfies, so
# both controls survived and the tests were pinning nothing. The
# denylist's whole value is the message that names the incident rather
# than saying "unknown type", so that is what is asserted.


def test_a_pdf_by_extension_is_refused_BY_THE_DENYLIST() -> None:
    reason = gate.classify("docs/vendor.pdf", b"not actually pdf bytes")
    assert reason is not None
    assert "vendor document" in reason, f"refused, but not by rule 1: {reason!r}"


def test_the_raml_that_leaked_is_refused_BY_THE_DENYLIST() -> None:
    reason = gate.classify("api.raml", b"#%RAML 1.0\ntitle: Jobvite\n")
    assert reason is not None
    assert "vendor API description" in reason, f"refused, but not by rule 1: {reason!r}"


def test_rules_1_and_2_are_both_reachable_and_give_different_answers() -> None:
    """The redundancy the gate claims is real and observable.

    It shows in the refusal message.
    """
    denied = gate.classify("x.pdf", b"text\n")
    unknown = gate.classify("x.bin", b"text\n")
    assert denied is not None and unknown is not None
    assert denied != unknown, "rule 1 and rule 2 are indistinguishable"


def test_an_unknown_extension_is_refused_not_permitted() -> None:
    """Allowlist-first.

    This is the rule that catches the type nobody predicted.
    """
    reason = gate.classify("thing.bin", b"harmless text\n")
    assert reason is not None
    assert "allowlist" in reason


def test_an_unknown_extensionless_basename_is_refused() -> None:
    reason = gate.classify("some/random_file", b"harmless text\n")
    assert reason is not None


# ----------------------------------------------------------------------
# Rule 3 - magic numbers. The arm the design says matters most, because
# an extension denylist alone passes the leaked PDF renamed.
# ----------------------------------------------------------------------


def test_a_real_pdf_renamed_markdown_is_refused_by_its_bytes() -> None:
    reason = gate.classify("docs/research/notes.md", REAL_PDF)
    assert reason is not None, "a PDF renamed .md was PERMITTED - this is the incident"
    assert "PDF" in reason


def test_the_magic_rule_and_the_extension_rule_are_independently_load_bearing() -> None:
    """Neither rule alone suffices, proven in both directions.

    Extension-only would pass the renamed PDF. Magic-only would pass a
    `.pdf` that happens to hold plain text, and would still let the
    extension through.
    """
    renamed_pdf = gate.classify("notes.md", REAL_PDF)
    text_in_a_pdf_name = gate.classify("notes.pdf", b"just some text\n")
    assert renamed_pdf is not None and "PDF" in renamed_pdf
    assert text_in_a_pdf_name is not None and ".pdf" in text_in_a_pdf_name
    # ... and the partner: neither rule fires on the ordinary case.
    assert gate.classify("notes.md", b"just some text\n") is None


@pytest.mark.parametrize(
    "signature, label",
    [
        (b"PK\x03\x04", "zip"),
        (b"\x89PNG\r\n\x1a\n", "png"),
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "legacy office"),
        (b"\x7fELF", "elf"),
    ],
)
def test_other_binary_containers_are_refused_under_a_text_name(
    signature: bytes, label: str
) -> None:
    reason = gate.classify("docs/report.md", signature + b"\n")
    assert reason is not None, f"{label} content passed under a .md name"


# ----------------------------------------------------------------------
# Rule 4 - the NUL backstop.
# ----------------------------------------------------------------------


def test_a_nul_byte_is_refused_even_with_an_allowed_extension() -> None:
    reason = gate.classify("notes.txt", b"api notes\x00binary junk\n")
    assert reason is not None
    assert "NUL" in reason


def test_the_nul_backstop_catches_content_no_magic_signature_matches() -> None:
    """The backstop's point: an unknown binary with no signature."""
    exotic = b"\x11\x22\x33nothing-in-the-MAGIC-table\x00\x44"
    assert gate.classify("data.txt", exotic) is not None
    # Partner: the same file without the NUL is permitted, so this is
    # not passing merely because `data.txt` is refused for some other
    # reason.
    assert gate.classify("data.txt", exotic.replace(b"\x00", b"_")) is None


# ----------------------------------------------------------------------
# The stated ceiling, pinned as a fact rather than left for a reader to
# assume away. DESIGN.md:1732-1734.
# ----------------------------------------------------------------------


def test_the_gate_does_NOT_stop_confidential_prose_in_markdown() -> None:
    """This asserts a LIMIT, not a capability. It must keep passing.

    The incident that actually happened was confidential *prose*. This
    gate permits it, by design, and `DESIGN.md:1732-1734` says so. If
    someone later makes this test fail by teaching the gate to scan
    prose, that is a design change and needs an ADR - not a quiet edit
    here.
    """
    prose = b"# Notes\n\nCONFIDENTIAL - Jobvite internal pricing, do not distribute.\n"
    assert gate.classify("docs/research/notes.md", prose) is None


# ----------------------------------------------------------------------
# Rule 0 - the override, and the "same commit" property that makes it
# reviewable.
# ----------------------------------------------------------------------


def test_the_allowlist_parser_ignores_comments_and_blank_lines() -> None:
    raw = b"# a comment\n\nvendor/thing.bin\ndocs/x.bin  # trailing comment\n"
    entries = gate.load_allowlist(lambda _p: raw)
    assert entries == {"vendor/thing.bin", "docs/x.bin"}


def test_a_missing_allowlist_is_an_empty_set_not_an_error() -> None:
    def missing(_p: str) -> bytes:
        raise gate.GateError("not in the index")

    assert gate.load_allowlist(missing) == set()


# ----------------------------------------------------------------------
# END TO END, against a real `git commit` with the real hook installed.
# ----------------------------------------------------------------------


def _git(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture()
def scratch_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """A throwaway git repo with the gate script copied in.

    Deliberately NOT the real repository: an end-to-end test that
    commits must never be able to write to the tree it is run from.
    """
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / GATE_PATH.name).write_bytes(GATE_PATH.read_bytes())
    _git(repo.parent, "init", "-q", str(repo))
    _git(repo, "config", "user.email", "u15@test")
    _git(repo, "config", "user.name", "u15")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    return repo


def _run_gate(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(repo / "scripts" / GATE_PATH.name), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def test_e2e_an_ordinary_staged_file_passes(scratch_repo: pathlib.Path) -> None:
    """POSITIVE CONTROL for every e2e refusal below.

    **Exit code 0 alone is NOT enough here, and this is the assertion
    the amputation harness caught.** A zero-byte
    `check-committed-file-types.py` runs and exits 0, so an earlier
    version of this test passed against a gate that had been deleted
    down to an empty file - while every refusal test around it correctly
    failed. A green positive control paired with red refusals reads as
    "the gate is too permissive", which is the wrong diagnosis and the
    expensive kind of wrong.

    So the gate must also SAY it looked: the success line carries the
    number of files checked, and that number must be non-zero. This is
    the same pairing U0 used for `.env.example` - an instrument that
    cannot be satisfied by silence (U0-REPORT section 7).
    """
    (scratch_repo / "ok.py").write_text("x = 1\n")
    _git(scratch_repo, "add", "ok.py")
    result = _run_gate(scratch_repo)
    assert result.returncode == 0, result.stdout + result.stderr

    match = re.search(r"(\d+) file\(s\) checked", result.stdout)
    assert match is not None, (
        f"the gate exited 0 without reporting what it checked: {result.stdout!r}"
    )
    assert int(match.group(1)) >= 1, "the gate exited 0 having checked nothing"


def test_e2e_a_real_pdf_staged_as_markdown_is_refused(
    scratch_repo: pathlib.Path,
) -> None:
    (scratch_repo / "vendor-spec.md").write_bytes(REAL_PDF)
    _git(scratch_repo, "add", "vendor-spec.md")
    result = _run_gate(scratch_repo)
    assert result.returncode == 1, result.stdout + result.stderr

    # Assert the per-file REASON line, not the whole of stdout. The
    # refusal banner itself contains the word "PDF" ("A CONFIDENTIAL
    # vendor PDF ... reached public remotes"), so
    # `"PDF" in result.stdout` is satisfied by any refusal for any
    # reason. The amputation harness caught this: with the rule tables
    # emptied, the file was refused as an unknown extension and this
    # test still passed, reporting that magic-number sniffing worked
    # when it had been deleted.
    reason_lines = [ln for ln in result.stdout.splitlines() if "vendor-spec.md:" in ln]
    assert reason_lines, f"no per-file reason emitted: {result.stdout!r}"
    assert "PDF" in reason_lines[0], (
        f"refused, but not by its bytes: {reason_lines[0]!r}"
    )


def test_e2e_a_nul_bearing_file_is_refused(scratch_repo: pathlib.Path) -> None:
    (scratch_repo / "notes.txt").write_bytes(b"notes\x00junk\n")
    _git(scratch_repo, "add", "notes.txt")
    result = _run_gate(scratch_repo)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "NUL" in result.stdout


def test_e2e_the_gate_reads_the_index_not_the_worktree(
    scratch_repo: pathlib.Path,
) -> None:
    """A file poisoned in the index is refused, worktree aside.

    This is the property that makes the gate meaningful at all: what
    gets committed is the index, not what happens to be on disk when it
    runs.
    """
    target = scratch_repo / "vendor-spec.md"
    target.write_bytes(REAL_PDF)
    _git(scratch_repo, "add", "vendor-spec.md")
    target.write_text("# actually fine now\n")  # worktree cleaned, index still bad
    result = _run_gate(scratch_repo)
    assert result.returncode == 1, "the gate read the worktree, not the index"


def test_e2e_an_override_needs_its_allowlist_entry_staged(
    scratch_repo: pathlib.Path,
) -> None:
    """DESIGN.md:1730-1731 - the exception is in the same diff."""
    (scratch_repo / "thing.bin").write_text("hello\n")
    (scratch_repo / ".file-type-allowlist").write_text("thing.bin\n")
    _git(scratch_repo, "add", "thing.bin")  # allowlist NOT staged

    unstaged = _run_gate(scratch_repo)
    assert unstaged.returncode == 1, "an unstaged exception was honoured"

    _git(scratch_repo, "add", ".file-type-allowlist")  # now in the same commit
    staged = _run_gate(scratch_repo)
    assert staged.returncode == 0, staged.stdout + staged.stderr
    assert "exception" in staged.stdout


def test_e2e_the_gate_fails_closed_when_it_cannot_run(
    scratch_repo: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """An error is a refusal.

    A control that fails open is worse than none.
    """
    stub_dir = tmp_path / "stub"
    stub_dir.mkdir()
    stub = stub_dir / "git"
    stub.write_text('#!/bin/sh\necho "fatal: simulated" >&2\nexit 128\n')
    stub.chmod(0o755)

    result = subprocess.run(
        [sys.executable, str(scratch_repo / "scripts" / GATE_PATH.name)],
        cwd=scratch_repo,
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": f"{stub_dir}:/usr/bin:/bin"},
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Failing closed" in result.stderr


def test_e2e_an_unknown_argument_fails_closed(scratch_repo: pathlib.Path) -> None:
    result = _run_gate(scratch_repo, "--pretty-please")
    assert result.returncode == 2, result.stdout + result.stderr


def test_e2e_all_mode_checks_every_tracked_file(scratch_repo: pathlib.Path) -> None:
    """--all is the CI arm. Partner below proves it can also go red."""
    clean = _run_gate(scratch_repo, "--all")
    assert clean.returncode == 0, clean.stdout + clean.stderr

    (scratch_repo / "sneaked.md").write_bytes(REAL_PDF)
    _git(scratch_repo, "add", "sneaked.md")
    _git(scratch_repo, "commit", "-q", "--no-verify", "-m", "bypassed the hook")
    dirty = _run_gate(scratch_repo, "--all")
    assert dirty.returncode == 1, (
        "--all did not catch a file committed with --no-verify"
    )
