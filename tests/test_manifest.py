"""DESIGN.md §8 case #11 - `mcp` is pinned, the resolve has no drift.

Three arms, and the third is the one that earns the case its keep:

1. `mcp` is present in `[project].dependencies` with an `==` pin.
   DESIGN.md:1485-1488 pins it explicitly rather than relying on
   `fastmcp` to hold it, because the `ResponseLimiting` regression
   arrived through the transitive SDK with zero change to the code that
   broke.
2. `uv lock --check` exits 0 without amending `uv.lock` - the same lock
   CI installs with `uv sync --frozen`. Asserted by hashing the file
   either side, because a command that rewrites the lock and then
   reports agreement has proven nothing.
3. **The negative arm.** Until ADR-0036 this was "a manifest with the
   `fastmcp-slim` line removed FAILS to resolve", guarding a pin that
   is gone: at the GA `fastmcp==4.0.3` that mutation RESOLVES, so the
   arm could only pass by testing nothing. The MECHANISM it existed
   for is kept and is what the arm asserts now - a PRERELEASE pin
   whose transitive is not named still fails under
   `prerelease = "explicit"`, measured against the real 4.0.0b4 that
   made the rule (IMPLEMENTATION-PLAN.md:266-276).
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import shutil
import subprocess
import tomllib

import pytest

from .conftest import PYPROJECT, UV_LOCK


def _dependencies() -> list[str]:
    with PYPROJECT.open("rb") as fh:
        deps = tomllib.load(fh)["project"]["dependencies"]
    assert isinstance(deps, list)
    return [str(d) for d in deps]


def test_mcp_is_pinned_with_a_double_equals() -> None:
    deps = _dependencies()
    mcp = [d for d in deps if re.match(r"^mcp\b", d)]
    assert mcp == ["mcp==2.1.1"], f"expected an == pin on mcp, dependencies are {deps}"


def test_the_runtime_dependency_set_is_exactly_these_and_nothing_else() -> None:
    """A CLOSED set over the whole runtime dependency list.

    Not a claim about two pins.

    **This test was renamed, and the rename is the point.** It used to
    be called
    `test_fastmcp_and_fastmcp_slim_are_pinned_at_the_same_version` - a
    name describing two pins, on a body that closes the ENTIRE list.
    That gap is collision 10: an auditor asking "will my change break a
    test?" reads names, so a unit adding a scheduled runtime dependency
    saw nothing relevant here and would have been surprised by a red
    build reading as a manifest-integrity breach. Six review rounds read
    the name and missed the body.

    The closed set is a real property and is kept: a dependency arriving
    without anyone deciding to add it should fail here. Adding one is
    meant to cost a deliberate edit.

    **Widen this set by APPENDING. Never relax it to a subset check.**
    DESIGN.md:1499-1501 states three pins; ADR-0036 removes the second
    of them, because at the GA 4.0.3 `fastmcp-slim` resolves unnamed
    and the comment calling it load-bearing had become false. The
    remaining two are not to be removed or reordered.
    """
    assert set(_dependencies()) == {
        "fastmcp==4.0.3",
        "mcp==2.1.1",
        # U3's, added under the serialised dependency slot.
        # DESIGN.md:303-304 forbids a custom logging module and names
        # loguru as what covers that need.
        "loguru==0.7.3",
        # U4's, APPENDED under the same slot - the set stays CLOSED.
        # httpx2 is ADR-0007's client (fastmcp 4.0.0b4 installs no
        # `httpx` at all) and ships the MockTransport
        # DESIGN.md:1440-1441 rests the credential-free test strategy
        # on; defusedxml parses the HR-XML hardened fallback of
        # DESIGN.md:349-352. Both were already resolved transitively at
        # these exact versions, so `uv lock` added four lines and moved
        # nothing.
        "httpx2==2.12.0",
        "defusedxml==0.7.1",
        # U1's. config.py imports pydantic_settings directly; it had
        # been arriving transitively, so nothing would have noticed a
        # bump that dropped it.
        "pydantic-settings==2.15.0",
        # U7's, APPENDED under the same slot - the set stays CLOSED.
        # `tenacity` is DESIGN.md:359-361's retry mechanism and
        # `circuitbreaker` is B37's breaker; STANDARDS.md:374-375
        # blesses both at `^9` and `^2`, confirmed against the CORPUS
        # (`standards/architecture/reference-architecture.md:95`) rather
        # than the local digest, which §8 says is not the authority for
        # currency. `circuitbreaker` was adopted by MEASUREMENT and not
        # by blessing - see scripts/probe-breaker-call-path.py.
        "tenacity==9.1.2",
        "circuitbreaker==2.1.3",
    }


def test_prerelease_is_explicit() -> None:
    """`--prerelease=allow` is global in uv; `explicit` confines it.

    DESIGN.md:1518-1520.
    """
    with PYPROJECT.open("rb") as fh:
        assert tomllib.load(fh)["tool"]["uv"]["prerelease"] == "explicit"


def test_the_absent_slim_pin_justification_comment_survives() -> None:
    """The comment IS the specification here.

    It records WHY `fastmcp-slim` is no longer named, which is the
    half a reader cannot recover from the manifest itself: an absent
    line leaves no trace of the decision that removed it. Renamed with
    its subject rather than deleted - the guarded claim changed, the
    property that a claim is guarded did not.
    """
    text = PYPROJECT.read_text()
    assert "a GA pin resolves it unnamed" in text


def test_uv_lock_check_passes_without_amending_the_lockfile() -> None:
    before = hashlib.sha256(UV_LOCK.read_bytes()).hexdigest()
    proc = subprocess.run(
        ["uv", "lock", "--check"],
        cwd=PYPROJECT.parent,
        capture_output=True,
        text=True,
    )
    after = hashlib.sha256(UV_LOCK.read_bytes()).hexdigest()
    assert proc.returncode == 0, (
        f"uv lock --check failed:\n{proc.stdout}\n{proc.stderr}"
    )
    assert before == after, (
        "uv lock --check rewrote uv.lock; its agreement proves nothing"
    )


@pytest.mark.network
def test_a_prerelease_pin_without_its_transitive_still_fails(
    tmp_path: pathlib.Path,
) -> None:
    """The mechanism DESIGN.md:1518-1520 pins, asserted as BEHAVIOUR.

    `prerelease = "explicit"` confines uv's global `--prerelease=allow`,
    and the cost is that a prerelease arriving TRANSITIVELY must be
    named or the resolve fails. `test_prerelease_is_explicit` above
    reads that setting out of the manifest; it cannot tell a live
    setting from an inert one. This arm runs it.

    The fixture is the real 4.0.0b4 that made the rule, so the arm
    keeps firing after ADR-0036 dropped the `fastmcp-slim` line it used
    to be written against. That mutation now RESOLVES at 4.0.3, which
    is why the old arm could not simply be left in place: it would have
    gone green by testing nothing.

    Marked `network` and deselected from the default offline suite: it
    performs a real resolve. CI runs it as its own step. It is excluded
    by SELECTION, never by skipif - a skip is a green that tested
    nothing (DESIGN.md:1310-1312).
    """
    manifest = PYPROJECT.read_text()
    mutated = manifest.replace('"fastmcp==4.0.3"', '"fastmcp==4.0.0b4"')
    assert mutated != manifest, "mutation was a no-op; this control would be vacuous"
    assert 'prerelease = "explicit"' in mutated, (
        "the fixture lost the setting under test; the arm would prove nothing"
    )

    (tmp_path / "src" / "fast_mcp_jobvite").mkdir(parents=True)
    (tmp_path / "src" / "fast_mcp_jobvite" / "__init__.py").touch()
    (tmp_path / "pyproject.toml").write_text(mutated)

    proc = subprocess.run(["uv", "lock"], cwd=tmp_path, capture_output=True, text=True)
    combined = proc.stdout + proc.stderr
    assert proc.returncode != 0, (
        "a prerelease pin resolved with its transitive unnamed. Either uv's "
        'behaviour changed or prerelease = "explicit" is no longer in force; '
        f"DESIGN.md:1518-1520 needs an ADR before it is touched. Output:\n{combined}"
    )
    assert "fastmcp-slim" in combined, (
        f"failed, but not for the stated reason:\n{combined}"
    )


@pytest.mark.network
def test_the_unmutated_manifest_still_resolves(tmp_path: pathlib.Path) -> None:
    """Positive control for the arm above.

    A refusal-path test is not a guard unless the happy path still
    succeeds (DESIGN.md:1451-1452). Without this, a `uv` that failed on
    EVERYTHING - a broken binary, no network, a bad cache - would make
    the control above pass.
    """
    (tmp_path / "src" / "fast_mcp_jobvite").mkdir(parents=True)
    (tmp_path / "src" / "fast_mcp_jobvite" / "__init__.py").touch()
    shutil.copy(PYPROJECT, tmp_path / "pyproject.toml")

    proc = subprocess.run(["uv", "lock"], cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 0, (
        f"the real manifest failed to resolve:\n{proc.stdout}\n{proc.stderr}"
    )
