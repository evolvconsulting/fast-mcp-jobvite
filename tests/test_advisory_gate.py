"""The advisory-expiry gate. DESIGN.md:1596-1615, §8 case #15.

HOW THE CLOCK IS PINNED, stated because a self-referential date test is
the exact shape of a green that tested nothing. Every date in this file
is a LITERAL, and `now` is passed in as `NOW` - a literal too. Nothing
here calls `date.today()` or `datetime.now()`, so no fixture is derived
from the clock the implementation reads.

That matters because the obvious way to write these tests is
`expires = today + timedelta(days=31)` judged against `today`, which
passes against ANY threshold the implementation happens to use, and
passes on an implementation that reads the clock twice and compares it
to itself. With both sides pinned, `EXPIRES_AT_30` and `EXPIRES_AT_31`
are real boundaries: they straddle a fixed number, and a mutant that
moves the threshold to 29 or 31 lands on one of them.

EVERY REJECTION ARM HAS ITS POSITIVE CONTROL, and each rejection is made
attributable to ONE field: the over-budget entry has NOT expired, and
the expired entry is WITHIN budget, so neither can be passing for the
other's reason.

**THE ASSERTIONS ARE ON THE EMITTED FLAGS, NOT ONLY THE EXIT CODE.** A
script that exits 0 and emits nothing passes every exit-code test in
this file while silently disabling every ignore it was asked to honour.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_advisories.py"


def _load_gate() -> Any:
    """Import the gate by path.

    `scripts/` is not a package and is not on `sys.path`, so the module
    is loaded from its file rather than imported by name.

    Returns:
        The imported module.
    """
    spec = importlib.util.spec_from_file_location("check_advisories", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_advisories"] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate()

# --- The pinned clock. Every date below is a literal.
# ------------------------
NOW = dt.date(2026, 8, 28)
RECORDED = dt.date(2026, 8, 20)

EXPIRES_UNEXPIRED = dt.date(2026, 9, 10)  # 21 days after RECORDED, after NOW
EXPIRES_AT_30 = dt.date(2026, 9, 19)  # exactly 30 days after RECORDED
EXPIRES_AT_31 = dt.date(2026, 9, 20)  # 31 days: one day over the budget
EXPIRES_AT_NOW = NOW  # expires today: NOT yet expired

# Expired, but WITHIN budget, so the refusal is attributable to expiry
# alone.
RECORDED_OLD = dt.date(2026, 7, 1)
EXPIRES_PAST = dt.date(2026, 7, 20)  # 19 days after RECORDED_OLD, before NOW

ADVISORY = "GHSA-xxxx-yyyy-zzzz"
OTHER_ADVISORY = "PYSEC-2026-1234"
REASON = "transitive; our code never constructs the vulnerable parser"


def entry(**overrides: Any) -> dict[str, Any]:
    """Build a legal entry, then apply overrides.

    Starting from a LEGAL entry and breaking exactly one field is what
    makes each rejection attributable to that field.

    Args:
        **overrides: Fields to replace. A field set to `None` is
            deleted, which is how the missing-field arms are built.

    Returns:
        The entry.
    """
    base: dict[str, Any] = {
        "id": ADVISORY,
        "date": RECORDED,
        "reason": REASON,
        "expires": EXPIRES_UNEXPIRED,
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


# --- ARM 2, the positive control for all four rejection arms
# ----------------


def test_an_unexpired_entry_is_honoured_AND_ITS_FLAG_IS_EMITTED() -> None:
    """§8 #15's positive control.

    The flag is the assertion, not the exit code.
    """
    flags, refusals = gate.check_entries([entry()], NOW)
    assert refusals == []
    assert flags == ["--ignore-vuln", ADVISORY]


def test_the_emitted_id_comes_from_the_table_not_a_second_list() -> None:
    """The table is the single source.

    A different id in, a different flag out.
    """
    flags, refusals = gate.check_entries([entry(id=OTHER_ADVISORY)], NOW)
    assert refusals == []
    assert flags == ["--ignore-vuln", OTHER_ADVISORY]


def test_every_honoured_entry_gets_a_flag() -> None:
    """Two legal entries emit two flag pairs, in table order."""
    entries = [entry(), entry(id=OTHER_ADVISORY)]
    flags, refusals = gate.check_entries(entries, NOW)
    assert refusals == []
    assert flags == [
        "--ignore-vuln",
        ADVISORY,
        "--ignore-vuln",
        OTHER_ADVISORY,
    ]


def test_an_empty_table_is_legal_and_emits_no_flags() -> None:
    """The shipped state: the table is empty and stays empty."""
    assert gate.check_entries([], NOW) == ([], [])


# --- ARM 1: past its recorded expiry -> rejected
# ----------------------------


def test_an_entry_past_its_recorded_expiry_is_rejected() -> None:
    """§8 #15.

    Within budget, so the refusal is attributable to expiry alone.
    """
    entries = [entry(date=RECORDED_OLD, expires=EXPIRES_PAST)]
    flags, refusals = gate.check_entries(entries, NOW)
    assert flags == []
    assert len(refusals) == 1
    assert "expired" in refusals[0]
    assert ADVISORY in refusals[0]


def test_the_expired_arms_entry_would_be_legal_but_for_its_expiry() -> None:
    """Positive control ON the expired fixture itself.

    Judged against a `now` before the expiry, the SAME entry passes. So
    the rejection above is caused by the expiry and not by the budget,
    the id, or the shape of the fixture.
    """
    entries = [entry(date=RECORDED_OLD, expires=EXPIRES_PAST)]
    flags, refusals = gate.check_entries(entries, dt.date(2026, 7, 10))
    assert refusals == []
    assert flags == ["--ignore-vuln", ADVISORY]


def test_an_entry_expiring_today_is_not_yet_expired() -> None:
    """The boundary.

    `expires == now` is the last legal day, not the first dead one.
    """
    flags, refusals = gate.check_entries([entry(expires=EXPIRES_AT_NOW)], NOW)
    assert refusals == []
    assert flags == ["--ignore-vuln", ADVISORY]


def test_an_entry_expiring_the_day_before_now_is_expired() -> None:
    """One day the other side of the same boundary."""
    yesterday = dt.date(2026, 8, 27)
    entries = [entry(date=dt.date(2026, 8, 10), expires=yesterday)]
    flags, refusals = gate.check_entries(entries, NOW)
    assert flags == []
    assert "expired" in refusals[0]


# --- ARM 3: no expiry at all -> rejected
# ------------------------------------


def test_an_entry_with_no_expiry_is_rejected() -> None:
    """An ignore with no expiry never expires.

    That is the whole failure mode.
    """
    flags, refusals = gate.check_entries([entry(expires=None)], NOW)
    assert flags == []
    assert len(refusals) == 1
    assert "no expiry" in refusals[0]


def test_an_entry_with_no_date_is_rejected() -> None:
    """A missing `date` makes the 30-day budget unmeasurable.

    The budget is measured from `date`.
    """
    flags, refusals = gate.check_entries([entry(date=None)], NOW)
    assert flags == []
    assert "no date" in refusals[0]


def test_an_entry_with_no_reason_is_rejected() -> None:
    """DESIGN.md:1604-1607 requires a written unreachability reason."""
    flags, refusals = gate.check_entries([entry(reason=None)], NOW)
    assert flags == []
    assert "no written reason" in refusals[0]


def test_an_entry_with_a_blank_reason_is_rejected() -> None:
    """Whitespace is not a written reason."""
    flags, refusals = gate.check_entries([entry(reason="   ")], NOW)
    assert flags == []
    assert "no written reason" in refusals[0]


# --- ARM 4: expiry more than 30 days out -> rejected
# ------------------------


def test_an_expiry_more_than_30_days_out_is_rejected() -> None:
    """31 days.

    NOT expired, so the refusal is attributable to the budget alone.
    """
    entries = [entry(expires=EXPIRES_AT_31)]
    flags, refusals = gate.check_entries(entries, NOW)
    assert flags == []
    assert len(refusals) == 1
    assert "31 days" in refusals[0]
    assert "more than the 30" in refusals[0]


def test_an_expiry_exactly_30_days_out_is_honoured() -> None:
    """The other side of the budget boundary.

    `no more than 30` includes 30.
    """
    flags, refusals = gate.check_entries([entry(expires=EXPIRES_AT_30)], NOW)
    assert refusals == []
    assert flags == ["--ignore-vuln", ADVISORY]


def test_the_30_day_budget_is_measured_from_the_recorded_date_not_from_now() -> None:
    """Measured from `now` the budget would refill on every CI run.

    This entry was recorded long ago with a far-future expiry. Its
    expiry is only 22 days from NOW, so a from-now implementation
    honours it. From the recorded date it is 129 days, which is what the
    design budgets.
    """
    entries = [entry(date=dt.date(2026, 5, 12), expires=dt.date(2026, 9, 18))]
    flags, refusals = gate.check_entries(entries, NOW)
    assert flags == []
    assert "129 days" in refusals[0]


# --- ARM 5: blanket ignore -> rejected
# --------------------------------------


def test_a_blanket_ignore_with_no_advisory_id_is_rejected() -> None:
    """DESIGN.md:1614-1615. Never a blanket ignore."""
    flags, refusals = gate.check_entries([entry(id=None)], NOW)
    assert flags == []
    assert len(refusals) == 1
    assert "BLANKET" in refusals[0]


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_a_blank_advisory_id_is_a_blanket_ignore(blank: str) -> None:
    """An id of whitespace names no advisory.

    So it suppresses all of them.
    """
    flags, refusals = gate.check_entries([entry(id=blank)], NOW)
    assert flags == []
    assert "BLANKET" in refusals[0]


def test_a_wildcard_id_is_not_silently_expanded() -> None:
    """A `*` is emitted verbatim, never treated as 'all advisories'.

    Stated as a CEILING rather than a claim of safety: this gate does
    not interpret ids, so `pip-audit` receives `*` as an id and matches
    nothing.
    """
    flags, _ = gate.check_entries([entry(id="*")], NOW)
    assert flags == ["--ignore-vuln", "*"]


# --- Fail-closed: one illegal entry suppresses ALL flags
# --------------------


def test_one_illegal_entry_suppresses_every_flag_in_the_table(
    tmp_path: Path,
) -> None:
    """A partial emit would honour the legal rows.

    CI would meanwhile think the gate refused.
    """
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(
        "[tool.fast-mcp-jobvite.advisory-ignores]\n"
        "entries = [\n"
        f'  {{ id = "{ADVISORY}", date = 2026-08-20, reason = "{REASON}",'
        " expires = 2026-09-10 },\n"
        f'  {{ id = "{OTHER_ADVISORY}", date = 2026-07-01, reason = "{REASON}",'
        " expires = 2026-07-20 },\n"
        "]\n",
        encoding="utf-8",
    )
    rc = gate.main(["--pyproject", str(manifest), "--now", NOW.isoformat()])
    assert rc == gate.EXIT_REFUSED


# --- The CLI, end to end
# ----------------------------------------------------


def _write(manifest: Path, body: str) -> None:
    manifest.write_text(body, encoding="utf-8")


def test_cli_emits_the_flag_on_stdout_for_a_legal_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """End-to-end: exit 0 AND the flag actually on stdout."""
    manifest = tmp_path / "pyproject.toml"
    _write(
        manifest,
        "[tool.fast-mcp-jobvite.advisory-ignores]\n"
        "entries = [\n"
        f'  {{ id = "{ADVISORY}", date = 2026-08-20, reason = "{REASON}",'
        " expires = 2026-09-10 },\n"
        "]\n",
    )
    rc = gate.main(["--pyproject", str(manifest), "--now", NOW.isoformat()])
    out = capsys.readouterr().out
    assert rc == gate.EXIT_OK
    assert out.strip() == f"--ignore-vuln {ADVISORY}"


def test_cli_exits_non_zero_and_emits_no_flags_on_an_expired_entry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit code AND stdout.

    Either alone can be right for a wrong reason.
    """
    manifest = tmp_path / "pyproject.toml"
    _write(
        manifest,
        "[tool.fast-mcp-jobvite.advisory-ignores]\n"
        "entries = [\n"
        f'  {{ id = "{ADVISORY}", date = 2026-07-01, reason = "{REASON}",'
        " expires = 2026-07-20 },\n"
        "]\n",
    )
    rc = gate.main(["--pyproject", str(manifest), "--now", NOW.isoformat()])
    out = capsys.readouterr().out
    assert rc == gate.EXIT_REFUSED
    assert "--ignore-vuln" not in out
    assert "expired" in out


def test_cli_fails_closed_when_the_manifest_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 2, not 0. A gate that cannot run must not report a pass."""
    rc = gate.main(["--pyproject", str(tmp_path / "nope.toml")])
    assert rc == gate.EXIT_CANNOT_RUN
    assert "cannot read" in capsys.readouterr().out


def test_cli_fails_closed_on_unparseable_toml(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A malformed manifest is exit 2, never an empty-table exit 0."""
    manifest = tmp_path / "pyproject.toml"
    _write(manifest, "[tool.fast-mcp-jobvite.advisory-ignores\nentries = [")
    rc = gate.main(["--pyproject", str(manifest)])
    assert rc == gate.EXIT_CANNOT_RUN
    assert "cannot parse" in capsys.readouterr().out


def test_cli_fails_closed_on_a_bad_now(capsys: pytest.CaptureFixture[str]) -> None:
    """A clock we cannot read is exit 2."""
    rc = gate.main(["--pyproject", str(REPO_ROOT / "pyproject.toml"), "--now", "soon"])
    assert rc == gate.EXIT_CANNOT_RUN
    assert "not an ISO date" in capsys.readouterr().out


def test_entries_that_are_not_tables_are_refused() -> None:
    """A bare string in the array is not an entry."""
    flags, refusals = gate.check_entries(["GHSA-loose-string"], NOW)
    assert flags == []
    assert "not a table" in refusals[0]


# --- The shipped manifest
# ---------------------------------------------------


def test_the_shipped_table_is_empty_and_the_gate_passes_it() -> None:
    """DESIGN.md ships the table empty.

    U11 builds the mechanism, not ignores.
    """
    assert gate.load_entries(REPO_ROOT / "pyproject.toml") == []


def test_the_gate_runs_clean_against_the_real_manifest() -> None:
    """Exit 0 with no flags, against the real file and clock."""
    rc = gate.main(["--pyproject", str(REPO_ROOT / "pyproject.toml")])
    assert rc == gate.EXIT_OK


def test_an_absent_table_is_not_an_error(tmp_path: Path) -> None:
    """A manifest with no table yields no entries rather than exit 2."""
    manifest = tmp_path / "pyproject.toml"
    _write(manifest, '[project]\nname = "x"\n')
    assert gate.load_entries(manifest) == []


def test_a_non_array_entries_value_is_refused(tmp_path: Path) -> None:
    """`entries = "GHSA-1"` is a shape error, not an empty table."""
    manifest = tmp_path / "pyproject.toml"
    _write(manifest, '[tool.fast-mcp-jobvite.advisory-ignores]\nentries = "GHSA-1"\n')
    with pytest.raises(gate.AdvisoryTableError, match="not an array"):
        gate.load_entries(manifest)


def test_quoted_iso_dates_are_accepted() -> None:
    """TOML gives a bare date natively.

    A quoted one must not silently refuse.
    """
    flags, refusals = gate.check_entries(
        [entry(date="2026-08-20", expires="2026-09-10")], NOW
    )
    assert refusals == []
    assert flags == ["--ignore-vuln", ADVISORY]


def test_a_non_date_expiry_is_refused() -> None:
    """`expires` set to a non-date must not read as absent.

    Nor as a far-future date.
    """
    flags, refusals = gate.check_entries([entry(expires="soon")], NOW)
    assert flags == []
    assert "not an ISO date" in refusals[0]


# --- Review round 1: M1, L1 and M2. Each fix gets its own arm, and each
# -------- refusal is attributable to ONE field, so a test cannot pass
# for the wrong reason.


def test_a_recorded_date_in_the_future_is_refused() -> None:
    """M1.

    The 30-day budget runs from `date`, so a future `date` is unbounded.

    Measured before the fix: `date = "2030-01-01"` with
    `expires = "2030-01-31"` computes a budget of exactly 30, passed
    every check, emitted its flag, and would have stayed legal for
    years. The gate enforced the arithmetic and never the premise
    ADR-0020 rests it on.

    This entry is legal in every OTHER respect - the budget is 30, and
    the expiry is in the future - so a pass here can only mean the
    future-date check is gone.
    """
    entries = [entry(date="2030-01-01", expires="2030-01-31")]
    flags, refusals = gate.check_entries(entries, NOW)
    assert flags == [], "a future-dated entry emitted a flag"
    assert len(refusals) == 1
    assert "in the future" in refusals[0], refusals[0]


def test_an_expiry_preceding_its_recorded_date_is_refused() -> None:
    """L1. A NEGATIVE budget passed the `> MAX_IGNORE_DAYS` check.

    `expires < now` catches it only when the expiry is also in the past,
    and the `> MAX_IGNORE_DAYS` check compares a NEGATIVE number against
    30. An entry expiring before the day it was recorded is incoherent
    whatever today is.

    **Both dates are in the PAST on purpose.** My first version used
    2027 and 2026, and the future-date check above fired instead - so
    the test passed while saying nothing about this one. A refusal has
    to be attributable to exactly one field or it is not a test of that
    field.
    """
    entries = [entry(date="2026-07-01", expires="2026-06-15")]
    flags, refusals = gate.check_entries(entries, NOW)
    assert flags == []
    assert len(refusals) == 1
    assert "precedes the recorded date" in refusals[0], refusals[0]


def test_a_misspelled_table_raises_rather_than_reading_as_empty(
    tmp_path: Path,
) -> None:
    """M2.

    The gate failed OPEN on a misspelling while its docstring said
    closed.

    Walking the table path and returning `[]` at the first missing key
    cannot distinguish "there is no ignore table", which is the normal
    and shipped state, from "the table is right there and its name is
    misspelled". Measured before the fix: renaming it to
    `advisory-ignore` with a SIX-YEAR-EXPIRED entry inside exited 0,
    emitted nothing, and warned about nothing.

    That is a wrong zero that explains itself - the shape this
    repository has paid for repeatedly - and it is the one input class
    U11's controls did not cover.
    """
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(
        "[tool.fast-mcp-jobvite.advisory-ignore]\n"
        'entries = [{ id = "GHSA-old-old-old", date = "2020-01-01", '
        'reason = "probe", expires = "2020-01-31" }]\n'
    )
    with pytest.raises(gate.AdvisoryTableError) as excinfo:
        gate.load_entries(manifest)
    assert "misspelled" in str(excinfo.value)


def test_an_unknown_key_inside_the_table_raises() -> None:
    """M2's sibling: `entires = [...]` would read as an empty table.

    A typo in the KEY leaves real ignores unread with no signal at all.
    """
    manifest = Path(__file__).parent / "_m2_unknown_key.toml"
    manifest.write_text("[tool.fast-mcp-jobvite.advisory-ignores]\nentires = []\n")
    try:
        with pytest.raises(gate.AdvisoryTableError) as excinfo:
            gate.load_entries(manifest)
        assert "unknown keys" in str(excinfo.value)
    finally:
        manifest.unlink(missing_ok=True)


def test_the_absent_table_is_still_legal(tmp_path: Path) -> None:
    """The control for all three above: a manifest with NO table.

    Without this, the fixes could have been "raise on everything", which
    passes every rejection arm and breaks the shipped state.
    """
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text('[project]\nname = "x"\nversion = "0"\n')
    assert gate.load_entries(manifest) == []
