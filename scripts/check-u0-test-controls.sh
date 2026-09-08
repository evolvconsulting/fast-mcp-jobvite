#!/usr/bin/env bash
# Positive-control harness for U0's own tests.
#
# Why this exists. Every U0 test asserts a property of a FILE - the manifest, the
# marker config, `.env.example`, `.gitignore`, the fixtures directory. That class of
# test is the easiest in the world to write green and hollow: a glob at a path that
# does not exist returns a clean empty list, a membership check over a set nobody
# populated passes, and a parser that matched nothing satisfies every assertion
# written over its output. A green from tests/ is worth exactly what their failure
# modes are worth, so each one is broken here on purpose and required to go red.
#
# The rule the design gates already follow (DESIGN.md:1564-1569, and the reason
# check-coupling-controls.py exists): a checker that has only ever passed is the
# same failure as the sentence it replaced.
#
# Each control makes ONE mutation to a COPY of the tree and requires the suite to
# fail with the NAMED test - not merely to fail, since a mutation that breaks
# collection outright would turn every control green while testing nothing.
#
# The real repository is read and never written.
#
# Usage: scripts/check-u0-test-controls.sh
# Exit 0 when every control fires, 1 otherwise. CI asserts fired == held and
# never a literal count.

set -uo pipefail

# Timeout bounds - each declared ONCE and interpolated into the abort
# message that explains it, so a changed bound cannot leave prose behind
# still quoting the old one. The names below are separate decisions,
# even where two of them share a value today.
BASELINE_TIMEOUT=900
ROW_TIMEOUT=900

# THE ONE CANONICAL RESULT LINE (task #107). This arms an EXIT trap that prints
# `HARNESS-RESULT name=... rows=... floor=... status=refused` on ANY exit, so an
# abort cannot render identically to a pass. `harness_result_ran` below upgrades
# it to ok/breach from the real exit code. The format lives in the sourced file
# and nowhere else - the shape lists it replaces are why.
# shellcheck source=lib/harness-result.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/harness-result.sh"

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Prefer the project venv; fall back to whatever `uv run` provides in CI.
if [ -x "$REPO/.venv/bin/python" ]; then
  PY=("$REPO/.venv/bin/python")
else
  PY=(uv run --frozen --project "$REPO" python)
fi

BAD=0
TOTAL=0

# The subset of the tree the suite reads. docs/ is required: conftest.py points
# FIXTURES_DIR into docs/research/fixtures.
#
# scripts/ added by U15: tests/test_file_type_gate.py imports the gate from
# scripts/check-committed-file-types.py, so without it this harness's copied
# tree fails at COLLECTION and every control below aborts. This is a one-entry
# data addition, not a change to U0's harness logic.
#
# .github added after 9ca76fe: tests/test_workflow_pins.py walks
# .github/workflows/ and carries a positive control asserting the walk actually
# found mirror.yml. Without .github staged, that control fires CORRECTLY - the
# walk really did find nothing in the copied tree - the BASELINE goes red, and
# the harness aborts before running a single control. So the gate went down
# reporting a true fact about a tree this script had built wrong.
#
# THIS IS THE FOURTH TIME, AND THE PREVIOUS COMMENT SAID WHAT TO DO ABOUT IT.
# U1 landed server.json at the repository root and
# test_server_json_declares_every_variable reads it; server.json was not in the
# list, so the file was absent from the copy, the baseline went red with a
# FileNotFoundError, and all eleven controls stopped running again.
#
# So the allow-list is gone, as its own comment prescribed. THE UNIT OF STAGING
# IS NOW THE TREE: `git ls-files` decides, and NOTHING here selects a subset of
# it. An allow-list of paths selects for exactly the path nobody thought of, and
# it selected for .github, then for tests/credentialed, and now for server.json.
#
# THERE IS NO DENY-LIST EITHER, and this comment claimed there was one for four
# commits. A `SKIP_TOP=(.git .venv venv node_modules)` array sat here, read by
# nothing - `grep -rna SKIP_TOP` returned that single declaration - while the
# prose above it described that dead array as the live staging mechanism. Eight
# review rounds read past it. Both are gone; the paragraph now describes what
# `stage()` actually does, which is: everything git tracks, and only that.
#
# Untracked build artifacts (.venv, caches, .pytest_cache) need no exclusion
# rule, because git does not track them - which is the whole reason a deny-list
# was never needed. It also means the copy matches what CI checks out rather
# than what somebody remembered to name.

stage () {
  local dest="$1"
  # Every tracked file, reproduced with its directory structure. `git -C ... ls-files`
  # is the authority on what the repository contains, which is the whole point:
  # nobody has to remember to add anything.
  local n
  n=$(cd "$REPO" && git ls-files | wc -l)
  [ "$n" -gt 0 ] || { echo "    STAGING CONTROL: git ls-files returned nothing"; return 1; }
  (cd "$REPO" && git ls-files -z | tar --null -cf - -T -) | (cd "$dest" && tar -xf -) || return 1
  # Positive control on the staging itself: the three files whose absence has
  # broken this harness before must be present in the copy. A staging step that
  # silently copies nothing produces a baseline failure that reads like a real one.
  local probe
  for probe in pyproject.toml server.json .github/workflows/mirror.yml; do
    [ -e "$REPO/$probe" ] || continue
    [ -e "$dest/$probe" ] || { echo "    STAGING CONTROL: $probe missing from the copy"; return 1; }
  done
}

run_control () {
  local name="$1" mutate="$2" expect="$3"
  TOTAL=$((TOTAL + 1))
  local work; work=$(mktemp -d)
  stage "$work" || { echo "--- CONTROL $name"; echo "    STAGING ERROR"; BAD=$((BAD+1)); rm -rf "$work"; return; }

  local before after
  before=$(cd "$work" && find . -type f -newer /dev/null | sort | xargs md5sum 2>/dev/null | md5sum)
  ( cd "$work" && eval "$mutate" )
  after=$(cd "$work" && find . -type f | sort | xargs md5sum 2>/dev/null | md5sum)
  echo "--- CONTROL $name"
  if [ "$before" = "$after" ]; then
    echo "    MUTATION WAS A NO-OP; this control would be vacuous"
    BAD=$((BAD + 1)); rm -rf "$work"; return
  fi

  # The row's verdict is "did $expect fire", so the row runs the FILE that
  # defines $expect rather than the whole suite (#238; each full run cost
  # ~80s and this step alone was 927s in CI run 33582613697). The file is
  # DERIVED from the expectation inside the copy, never typed beside it,
  # so a moved test moves the selection with it - and an expectation whose
  # definition cannot be found is a broken row, not a green one. Both
  # verdict branches survive the narrowing: $expect failing still names
  # itself, and a mutation $expect does not notice still exits 0. The
  # BASELINE above stays a full run of the copy on purpose - "the staged
  # tree is wholly green" is its claim, once, not per row.
  local expect_file
  expect_file=$(cd "$work" && grep -rl "def $expect" tests/ | head -1)
  if [ -z "$expect_file" ]; then
    echo "    NO FILE DEFINES $expect in the copy - this row cannot measure."
    BAD=$((BAD + 1)); rm -rf "$work"; return
  fi
  local out rc
  out=$(cd "$work" && timeout -k 30 "$ROW_TIMEOUT" "${PY[@]}" -m pytest "$expect_file" -q -p no:cacheprovider 2>&1); rc=$?
  # A HANG IS NOT A RESULT. Without this branch a 124 falls through to the
  # `$expect` test below, where `$out` is empty, and the row reports "WRONG
  # TEST FIRED" - a real failure with a misleading cause. `TIMED OUT` is the
  # phrase ci-harness-gate.sh greps for, so naming it here is what makes CI
  # fail for the right reason.
  if [ "$rc" -eq 124 ]; then
    echo "    TIMED OUT after ${ROW_TIMEOUT}s - this control NEVER FINISHED, so it"
    echo "    measured nothing. Not a fire and not a miss."
    BAD=$((BAD + 1)); rm -rf "$work"; return
  fi
  if [ "$rc" -eq 0 ]; then
    echo "    DID NOT FIRE: the suite is still green after the mutation"
    BAD=$((BAD + 1))
  # NOT `printf '%s\n' "$out" | grep -q "$expect"`. Under `set -o pipefail`
  # (line 26) that pipeline returns 141, not 0, whenever `grep -q` finds its
  # match and exits while `printf` is still writing - so a control whose
  # mutation breaks ENOUGH tests to fill the pipe buffer is judged "WRONG TEST
  # FIRED" no matter what fired. Measured: the FIXTURES_DIR row below failed
  # exactly this way with `test_fixtures_directory_resolves` present in `$out`
  # and printed in this function's own diagnostic. A bash substring test has no
  # pipeline and cannot SIGPIPE.
  elif [[ "$out" == *"$expect"* ]]; then
    echo "    exit=$rc, '$expect' named in the failure -> CONTROL FIRED"
  else
    echo "    exit=$rc but '$expect' was NOT the failing test -> WRONG TEST FIRED"
    printf '%s\n' "$out" | grep -E '^(FAILED|ERROR)' | sed 's/^/      /'
    BAD=$((BAD + 1))
  fi
  rm -rf "$work"
}

# The baseline is not decoration: if the unmutated copy is already red, every
# control below "fires" for a reason that has nothing to do with its mutation.
echo "BASELINE: the unmutated copy"
BASE=$(mktemp -d); stage "$BASE"
base_out=$(cd "$BASE" && timeout -k 30 "$BASELINE_TIMEOUT" "${PY[@]}" -m pytest -q -p no:cacheprovider 2>&1)
base_rc=$?
printf '%s\n' "$base_out" | tail -2
rm -rf "$BASE"
if [ "$base_rc" -eq 124 ]; then
  echo "ABORT: THE BASELINE HUNG - ${BASELINE_TIMEOUT}s with no result, on the INTACT copy."
  echo "TIMED OUT. Nothing below would have measured anything."
  exit 4
fi
if [ "$base_rc" -ne 0 ]; then
  echo "ABORT: the unmutated copy is already red. Fix that before running controls."
  exit 1
fi
echo "================================================================"

run_control "empty a deliberate non-secret default (draft 2's 'fix')" \
  "sed -i 's/^JOBVITE_MAX_RESULTS=50/JOBVITE_MAX_RESULTS=/' .env.example" \
  "test_the_deliberate_non_secret_defaults_are_intact"

run_control "a secret-class variable carries a value" \
  "sed -i 's/^JOBVITE_API_KEY=/JOBVITE_API_KEY=sk-live-abc123/' .env.example" \
  "test_every_secret_class_variable_is_empty"

run_control "drop *.pem from .gitignore" \
  "sed -i '/^\*\.pem$/d' .gitignore" \
  "test_gitignore_covers_every_credential_pattern"

run_control "un-ignore a credential with an extra negation" \
  "printf '!secrets/prod.key\n' >> .gitignore" \
  "test_gitignore_does_not_negate_the_credential_patterns"

run_control "remove --strict-markers from addopts" \
  "sed -i '/\"--strict-markers\",/d' pyproject.toml" \
  "test_an_undeclared_marker_fails_collection"

# ONE expression, not two. This row carried a second `/^  "-m",$/d` that had
# been dead for as long as anyone can check: `-m` and its value sit on ONE line
# of addopts, so the pattern matched nothing and `sed` exited 0 saying so. The
# row still FIRED, because the first expression deletes that whole line by
# itself - which is precisely why nobody noticed. Found by the static anchor
# checker on the first run after it learned to read `sed -i`.
run_control "remove the -m selection from addopts" \
  "sed -i '/\"not credentialed and not network\",/d' pyproject.toml" \
  "test_the_default_selection_deselects_the_credentialed_arm"

run_control "loosen the mcp pin to >=" \
  "sed -i 's/\"mcp==2.1.1\"/\"mcp>=2.1.1\"/' pyproject.toml" \
  "test_mcp_is_pinned_with_a_double_equals"

run_control "delete the absent-slim-pin justification comment" \
  "sed -i 's|# a GA pin resolves it unnamed; measured, not assumed||' pyproject.toml" \
  "test_the_absent_slim_pin_justification_comment_survives"

run_control "point FIXTURES_DIR at a path that does not exist" \
  "sed -i 's|\"docs\" / \"research\" / \"fixtures\"|\"docs\" / \"research\" / \"fixtures-typo\"|' tests/conftest.py" \
  "test_fixtures_directory_resolves"

run_control "drop a variable from .env.example" \
  "sed -i '/^JOBVITE_PAGINATION_START_BASE=/d' .env.example" \
  "test_the_parser_actually_found_variables"

run_control "make uv.lock disagree with the manifest" \
  "sed -i 's/^version = \"0.1.0\"/version = \"0.2.0\"/' pyproject.toml" \
  "test_uv_lock_check_passes_without_amending_the_lockfile"

echo "================================================================"
echo "$((TOTAL - BAD))/$TOTAL controls fired."
# The canonical result line's tally, from the SAME two counters the line
# above prints and the harness's own gate compares - never a recount.
harness_result_tally fired "$((TOTAL - BAD))" "$TOTAL"

# THE ROW FLOOR. `BAD -eq 0` is satisfied by a harness with no rows at all:
# delete every `run_control` call and this prints "0/0 controls fired." and
# exits 0. DERIVED: this harness printed "10/11 controls fired." on the run
# that found the SIGPIPE defect above, and "11/11" once it was fixed - eleven
# rows either way. Lowering this number is a visible diff that has to be
# defended.
ROW_FLOOR=11
# The canonical result line's numbers, taken from the harness's own
# counter and its own floor - never a second copy. Called BEFORE the
# comparison below, because that branch exits.
harness_result_ran "$TOTAL" "$ROW_FLOOR"
if [ "$TOTAL" -lt "$ROW_FLOOR" ]; then
  echo "::error::$TOTAL/$ROW_FLOOR ROWS - THE HARNESS LOST ROWS."
  echo "         A harness with fewer rows than its floor is green for the wrong reason."
  exit 1
fi

[ "$BAD" -eq 0 ]
