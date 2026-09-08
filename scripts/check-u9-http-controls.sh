#!/usr/bin/env bash
# U9 MUTATION harness. Change one value - does the NAMED test notice?
#
# THIS UNIT HAS NO REQUIRED CASE. IMPLEMENTATION-PLAN.md SS U9 says so in
# as many words: "No SS8 case owns this unit ... nothing in the coupling
# gate will miss them if they are dropped." Every other unit here has a
# required case that goes red when its behaviour goes. U9 does not. So
# these two harnesses are the whole of this unit's defence, and a
# surviving row here is not a nit - it is the one instrument that would
# have noticed, reporting that it would not have.
#
# THE ROW THAT MATTERS MOST IS M1, and it is the one with a threat row
# of its own. `include_payloads` flipped to True sends raw candidate PII
# to the framework log (C2-I1). The framework's DEFAULT for that keyword
# is ALSO False, which is why the mutation flips it to True rather than
# deleting the keyword: deleting it changes no behaviour and would be a
# row that cannot fail. That is stated here because a reader checking
# the harness is entitled to know which rows can fire and which cannot.
#
# M2 IS THE POSITIVE CONTROL'S MIRROR. It ADDS an excluded middleware
# rather than removing an adopted one, because the absence assertion is
# what a future contributor would break by re-adding `ResponseCaching`
# for latency - the exact regression ADR-0004 and DESIGN.md's caching
# paragraph exist to prevent.
#
# LANDING AND RESTORE ARE CHECKED WITH `cmp`, NOT WITH `git diff`.
# `git diff --quiet` reports NO DIFFERENCE for an UNTRACKED file
# whatever that file contains, and this harness is untracked until it is
# committed.
#
# PYTHONDONTWRITEBYTECODE=1: `.pyc` invalidation keys on (mtime, size),
# and a mutation that swaps one value can be the same size inside one
# second - in which case the interpreter reuses stale bytecode, the
# mutated code never runs, and the row reports a clean survivor that is
# an instrument fault rather than a finding.

# `-e` deliberately omitted: these harnesses read the exit code of a suite that
# is EXPECTED to fail. See docs/adr/0023-harnesses-drop-e-from-strict-mode.md
set -uo pipefail

# Timeout bounds - each declared ONCE and interpolated into the abort
# message that explains it, so a changed bound cannot leave prose behind
# still quoting the old one. The names below are separate decisions,
# even where two of them share a value today.
BASELINE_TIMEOUT=900
ROW_TIMEOUT=300
SELECTOR_TIMEOUT=120

# THE ONE CANONICAL RESULT LINE (task #107). This arms an EXIT trap that prints
# `HARNESS-RESULT name=... rows=... floor=... status=refused` on ANY exit, so an
# abort cannot render identically to a pass. `harness_result_ran` below upgrades
# it to ok/breach from the real exit code. The format lives in the sourced file
# and nowhere else - the shape lists it replaces are why.
# shellcheck source=lib/harness-result.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/harness-result.sh"

export PYTHONDONTWRITEBYTECODE=1

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 3

HARDENING="src/fast_mcp_jobvite/http_hardening.py"
SUITE="tests/test_http_hardening.py"
# THE PYTEST LOG THIS RUN READS ITS VERDICTS OUT OF. Per-RUN, never a fixed
# name. Two worktrees on one machine run these harnesses concurrently, and a
# fixed path gives both the SAME INODE: independent `>` offsets leave a NUL
# hole, `grep` then reports "binary file matches" on STDERR and returns an
# EMPTY capture at exit 0, and a rival's `FAILED <nodeid>` lines are read as
# THIS run's kill. Both directions were reproduced - see
# docs/reviews/probe-284-shared-path-collision.sh, and #262 for the false kill
# this class already produced. CI can never catch a regression here: the runner
# has no second worktree.
OUT="$(mktemp /tmp/u9-mut-XXXXXX)"
BACKUP_DIR=$(mktemp -d)
PRISTINE_DIR=$(mktemp -d)
trap 'harness_result_emit; rm -rf "$BACKUP_DIR" "$PRISTINE_DIR" "$OUT"' EXIT

# THE PRISTINE COPY, TAKEN ONCE BEFORE ROW 1. `cp backup file; cmp file
# backup` compares equal BY CONSTRUCTION and can detect only a failed
# `cp`, never "the tree still carries this row's mutation".
cp "$HARDENING" "$PRISTINE_DIR/http_hardening.py" ||
  { echo "COULD NOT TAKE PRISTINE COPY of $HARDENING"; exit 3; }

echo "########## BASELINE - the intact tree"
# BOUNDED, exactly as the rows below are, and for the same reason. This was
# unbounded until this was measured: `U9 HTTP hardening amputation` takes
# 24m19s and PASSES, against 27-77s for the steps either side of it. Where one
# step legitimately runs for 24 minutes, a real hang is indistinguishable from
# normal slowness for as long as anyone will wait.
# `timeout` returns 124, which is why a hang and a red suite get DIFFERENT
# messages and DIFFERENT exit codes: "never finished" and "finished red" need
# different diagnoses, and this project has been bitten before by two states
# that render identically.
timeout "$BASELINE_TIMEOUT" uv run --frozen pytest $SUITE -q -p no:cacheprovider >"$OUT" 2>&1
baseline_rc=$?
if [ "$baseline_rc" -eq 124 ]; then
  echo "ABORT: THE BASELINE HUNG - ${BASELINE_TIMEOUT}s with no result, on the INTACT tree."
  echo "       This is not a red suite. Nothing below ran, and the harness is"
  echo "       not at fault until this is explained. Last 20 lines:"
  tail -20 "$OUT"
  exit 4
fi
if [ "$baseline_rc" -ne 0 ]; then
  echo "ABORT: the intact suite is red; every row below would be meaningless."
  tail -20 "$OUT"
  exit 3
fi
tail -1 "$OUT"
echo

FIRED=0
TOTAL=0

# Every selector a row aims at, in row order. Verified ONCE against the INTACT
# tree after the last row - see the block above harness_result_ran.
SELECTORS=()

# ---------------------------------------------------------------------------
# mutate <label> <file> <test-selector> <old> <new>
# ---------------------------------------------------------------------------
mutate() {
  local label="$1" file="$2" selector="$3" old="$4" new="$5"
  TOTAL=$((TOTAL + 1))
  # Recorded for the ONE intact-tree check after the last row (#249/R24-H1).
  # Appended here, beside the TOTAL it must equal, so a row added without a
  # selector shows up as a count mismatch rather than as silent under-coverage.
  SELECTORS+=("$selector")

  echo "########## $label"
  echo "  target: $selector"

  # SC2155: declared and assigned separately, so a failing `cp` cannot
  # be masked by `local`'s own exit status.
  local backup
  backup="$BACKUP_DIR/${TOTAL}_http_hardening.py"
  cp "$file" "$backup" || { echo "  COULD NOT BACK UP"; echo; return; }

  if ! OLD="$old" NEW="$new" FILE="$file" python3 - <<'PY'
import os, pathlib, sys
p = pathlib.Path(os.environ["FILE"])
s = p.read_text()
old, new = os.environ["OLD"], os.environ["NEW"]
n = s.count(old)
if n != 1:
    print(f"  ANCHOR NOT UNIQUE ({n} hits)", file=sys.stderr)
    sys.exit(1)
p.write_text(s.replace(old, new))
PY
  then
    echo "  COULD NOT APPLY - the anchor moved. Fix the harness."
    cp "$backup" "$file"
    echo
    return
  fi

  if cmp -s "$file" "$backup"; then
    echo "  MUTATION DID NOT LAND despite a successful write"
    cp "$backup" "$file"
    echo
    return
  fi

  timeout "$ROW_TIMEOUT" uv run --frozen pytest "$selector" -q -p no:cacheprovider \
    >"$OUT" 2>&1
  local rc=$?

  cp "$backup" "$file"
  if ! cmp -s "$file" "$PRISTINE_DIR/http_hardening.py"; then
    echo "  RESTORE FAILED - $file still differs from the pristine copy taken"
    echo "  before row 1. STOPPING."
    exit 3
  fi

  if [ "$rc" -eq 124 ]; then
    echo "  TIMED OUT after ${ROW_TIMEOUT}s - this row is unbounded. Rewrite it."
  fi

  if [ "$rc" -ne 0 ]; then
    FIRED=$((FIRED + 1))
    echo "  KILLED - the named test went red, as it must"
  else
    echo "  *** SURVIVED *** the named test passed against the mutation."
    echo "      The assertion does not check what its name claims."
    tail -1 "$OUT" | sed 's/^/      /'
  fi
  echo
}

# ===========================================================================
# THE MIDDLEWARE STACK - the three adopted, the five excluded, and the one
# value a threat row is written about.
# ===========================================================================

# C2-I1, DESIGN.md:1830. Flipped to True the framework log receives raw
# candidate PII. Flipping rather than deleting, because the framework's
# own default is False and a deleted keyword changes nothing.
mutate "M1  include_payloads is flipped to True" \
  "$HARDENING" \
  "$SUITE::test_structured_logging_is_constructed_with_include_payloads_false" \
  '        StructuredLoggingMiddleware(include_payloads=False),' \
  '        StructuredLoggingMiddleware(include_payloads=True),'

# The regression ADR-0004 and DESIGN.md's caching paragraph exist to
# prevent: somebody re-adds a cache for latency, and a candidate-PII
# result is served to a public-job-data token.
mutate "M2  ResponseCachingMiddleware is re-added to the stack" \
  "$HARDENING" \
  "$SUITE::test_the_five_excluded_middleware_are_absent" \
  '    return [
        RequestIdMiddleware(),' \
  '    from fastmcp.server.middleware.caching import ResponseCachingMiddleware

    return [
        ResponseCachingMiddleware(),
        RequestIdMiddleware(),'

# DESIGN.md:411-413: the default keys every caller to the literal
# "global", so one noisy integrator throttles everyone.
mutate "M3  get_client_id is dropped and the limiter keys everyone to global" \
  "$HARDENING" \
  "$SUITE::test_the_rate_limiter_has_a_get_client_id" \
  '            get_client_id=rate_limit_client_id,' \
  '            get_client_id=None,'

# The same defect from the other side: the callable stays wired but
# returns one constant, so every caller shares a bucket again. This is
# the row the LIVE per-client arm exists for - M3 is visible by reading
# the object, this one is not.
mutate "M4  rate_limit_client_id returns one constant for every caller" \
  "$HARDENING" \
  "$SUITE::test_rate_limiting_is_per_client" \
  '    token = get_access_token()
    if token is None:
        return ANONYMOUS_CLIENT_ID
    return token.client_id' \
  '    return ANONYMOUS_CLIENT_ID'

# DESIGN.md:414-422. `desired_calls + 2`, where the 2 is FastMCP's own
# client's connect sequence.
mutate "M5  the burst loses the connect-sequence allowance" \
  "$HARDENING" \
  "$SUITE::test_the_burst_is_the_designs_sizing" \
  'INBOUND_BURST_CAPACITY: Final = DESIRED_TOOL_CALLS_PER_BURST + 2' \
  'INBOUND_BURST_CAPACITY: Final = DESIRED_TOOL_CALLS_PER_BURST'

# ===========================================================================
# SCOPES - the three data classes of SS4.1, and the transport they apply on
# ===========================================================================

# A tool moves to the wrong data class, so a jobs token reaches
# candidate PII. C1-E1.
mutate "M6  search_jobs is scoped to candidate PII instead of job data" \
  "$HARDENING" \
  "$SUITE::test_two_differently_scoped_tokens_see_different_tool_sets" \
  '    SEARCH_JOBS: SCOPE_JOBS,' \
  '    SEARCH_JOBS: SCOPE_CANDIDATES,'

# DESIGN.md:917-921. Applied on stdio, `_RequireScopes` denies an absent
# token and every tool disappears from a transport the design declares
# fully authorised.
mutate "M7  the scopes are applied on stdio too" \
  "$HARDENING" \
  "$SUITE::test_scopes_are_NOT_applied_on_stdio" \
  '    if settings.mcp_transport != "http":
        return
    for tool in registered_tools(server):' \
  '    for tool in registered_tools(server):'

# The other direction: the scope is never applied at all, so every token
# sees every tool. This is the silent one - nothing fails, the server
# just stops enforcing SS7.2.
mutate "M8  the scopes are never applied at all" \
  "$HARDENING" \
  "$SUITE::test_scopes_are_applied_on_http" \
  '        tool.auth = require_scopes(TOOL_SCOPES[tool.name])' \
  '        tool.auth = None'

# ===========================================================================
# THE VERIFIER, AND THE CLIENT ID IT MINTS
# ===========================================================================

# The limiter interpolates `client_id` into the MCPError it RAISES, so a
# raw token there is published to the caller and the log.
mutate "M9  the client id becomes the bearer token itself" \
  "$HARDENING" \
  "$SUITE::test_the_client_id_is_never_the_token" \
  '    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]' \
  '    return token'

# A verifier that authenticates but grants nothing: every token holds
# every scope. The map is read and its scopes thrown away.
mutate "M10 every token is issued every scope" \
  "$HARDENING" \
  "$SUITE::test_the_verifier_carries_each_token_and_its_scopes" \
  '            token: {"client_id": token_client_id(token), "scopes": list(scopes)}' \
  '            token: {"client_id": token_client_id(token), "scopes": ["*"]}'

# ===========================================================================
# THE BIND, AND THE GUARD LISTS
# ===========================================================================

# `allowed_origins=None` is not "no origins" - `server/http.py:242`
# reads `is not None` to decide whether the list was set at all, so None
# restores the framework default this unit exists to replace.
mutate "M11 allowed_origins reverts to the framework default" \
  "$HARDENING" \
  "$SUITE::test_off_loopback_SETS_the_guard_lists" \
  '        kwargs["allowed_origins"] = []' \
  '        kwargs["allowed_origins"] = None'

# The guard lists are set unconditionally, which narrows `allowed_hosts`
# on a loopback bind and breaks `localhost` against 127.0.0.1 for no
# threat that exists inside the host.
mutate "M12 the guard lists are set on loopback too" \
  "$HARDENING" \
  "$SUITE::test_loopback_leaves_the_guard_lists_alone" \
  '    if not is_loopback(settings.mcp_host):
        host = settings.mcp_host' \
  '    if True:
        host = settings.mcp_host'

# ===========================================================================
# THE INBOUND CORRELATION ID (C7-T1)
# ===========================================================================

# The header is read under the wrong name, so a caller's id is never
# found and every request mints a fresh one. Silent: the tool still
# gets a well-formed UUID.
mutate "M13 the inbound header is looked up under the wrong name" \
  "$HARDENING" \
  "$SUITE::test_a_valid_inbound_request_id_reaches_the_tool_unchanged" \
  '        inbound = get_http_headers().get(REQUEST_ID_HEADER.lower())' \
  '        inbound = get_http_headers().get("x-correlation-id")'

# The validation is skipped and the header is used verbatim. This is
# C7-T1 itself: a value carrying a newline writes a second,
# attacker-authored line into the audit stream.
mutate "M14 the inbound id is bound without being validated" \
  "$HARDENING" \
  "$SUITE::test_a_malformed_inbound_request_id_is_replaced" \
  '        with request_id_scope(resolve_request_id(inbound)):' \
  '        with request_id_scope(inbound or resolve_request_id(None)):'

# ===========================================================================
# THE ROW FLOOR (R4-M4, applied here by R7-H2)
# ===========================================================================
#
# `FIRED -ne TOTAL` is satisfied by 0 == 0, so a harness whose rows were
# all deleted - or all skipped - reports fully green. `TOTAL -gt 0` below
# was the only floor, which one surviving row satisfies. Lowering this
# number is a visible diff that has to be defended.
#
# 14 is DERIVED, not typed: this harness was run at 03c4ae6 in a
# dedicated worktree and reported "14/14 controls fired", with 14 rows
# counted from the log. A floor copied from a report or a task record
# would be a second copy of a number that is measured in one place.
ROW_FLOOR=14

# ===========================================================================
# DO ALL THE SELECTORS STILL RESOLVE? ONE process, on the INTACT tree.
# ===========================================================================
#
# The property: a renamed, moved or misspelled test must not report a verdict
# forever while running nothing. Until now it was bought with a SECOND pytest
# process per row - `--collect-only`, inside mutate(), before each mutation
# landed. That doubled the process count of the whole harness, and process
# startup is what a per-row harness is made of.
#
# It also asked the question in the wrong place. The property is about the
# INTACT tree, and mutate() is a loop over MUTATED ones. #244 tried replacing
# the per-row probe with a per-row rule reading pytest's rc plus its
# `^ERROR <file> - <Exception>` line, and R24 measured that rule wrong in BOTH
# directions:
#
#   * A mutation that breaks an import reached from `tests/conftest.py` makes
#     pytest abort at CONFTEST LOAD: rc=4, "ImportError while loading conftest",
#     and NO short-test-summary section - so the discriminating line is absent
#     and a REAL KILL reads as a renamed selector.
#   * A genuinely renamed selector PLUS a mutation that breaks the TEST
#     module's own import DOES print that line, so the guard stayed silent and
#     the row was counted KILLED on a test that does not exist.
#
# Neither direction is answerable from a MUTATED run. So ask the intact tree,
# ONCE, after the last row. Every row above restored its file and compared it
# to the pristine copy (exit 3 if it differed), so the tree here is the tree
# row 1 started on, and one `pytest "${SELECTORS[@]}" --collect-only` covers
# the whole row set: one extra process per HARNESS in place of one per ROW.
#
# The recorded count is checked against TOTAL first, so a row that ran without
# recording its selector cannot pass as covered. It REFUSES rather than
# reporting - exit 3, and `harness_result_emit`'s EXIT trap prints
# `status=refused`, which is the honest word for a harness that cannot aim.
#
# Ported from 84d4959 (R24-H1), which was written, reviewed and never landed.
# The same shape already sits on main in check-u3-audit-controls.sh, arrived at
# from the other direction by #252's per-row selection work.
# `-eq 0` FIRST, and it is not redundant with the mismatch test beside it
# (R249-L2). At TOTAL=0 - every `mutate` call deleted - `0 -ne 0` is FALSE, so
# the mismatch arm alone passes, `pytest "${SELECTORS[@]}" --collect-only` runs
# with NO node ids, collects the WHOLE suite, exits 0, and the success line
# below announces a check that asked nothing. `check-u3-audit-controls.sh:461`
# carries this guard for the same reason; dropping it was this port's own
# defect, not one inherited from 84d4959.
if [ "$TOTAL" -eq 0 ] || [ "${#SELECTORS[@]}" -ne "$TOTAL" ]; then
  echo "########## RECORDED ${#SELECTORS[@]} SELECTORS FOR $TOTAL ROWS."
  echo "The check below covers exactly the selectors it is handed. At zero rows"
  echo "it would collect the whole suite and pass having asked nothing; at a"
  echo "mismatch it cannot cover every row. Either way its pass would mean less"
  echo "than it claims. Fix the harness."
  exit 3
fi
timeout "$SELECTOR_TIMEOUT" uv run --frozen pytest "${SELECTORS[@]}" \
  --collect-only -q -p no:cacheprovider >"$OUT" 2>&1
sel_rc=$?
if [ "$sel_rc" -ne 0 ]; then
  echo "########## A SELECTOR DOES NOT RESOLVE ON THE INTACT TREE (pytest rc=$sel_rc)."
  if [ "$sel_rc" -eq 124 ]; then
    echo "Read this, not the lines below: collection NEVER FINISHED within"
    echo "${SELECTOR_TIMEOUT}s. That is a hang, not a rename."
  fi
  echo "At least one row named a test that was renamed or moved, so that row"
  echo "has been reporting a verdict without ever running its killer."
  echo "pytest, on the restored tree:"
  tail -20 "$OUT"
  echo "Any row above whose target appears in those ERROR lines printed a"
  echo "verdict it did not earn - read the target, not the verdict."
  exit 3
fi
echo "########## ALL $TOTAL SELECTORS RESOLVE (one intact-tree process)"
# The canonical result line's numbers, taken from the harness's own
# counter and its own floor - never a second copy. Called BEFORE the
# comparison below, because that branch exits.
harness_result_ran "$TOTAL" "$ROW_FLOOR"
if [ "$TOTAL" -lt "$ROW_FLOOR" ]; then
  echo "########## $TOTAL/$ROW_FLOOR ROWS - THE HARNESS LOST ROWS."
  echo "A harness with fewer rows than its floor is green for the wrong reason."
  exit 1
fi

echo "$FIRED/$TOTAL controls fired."
# The canonical result line's tally, from the SAME two counters the line
# above prints and the harness's own gate compares - never a recount.
harness_result_tally fired "$FIRED" "$TOTAL"
[ "$TOTAL" -gt 0 ] && [ "$FIRED" -eq "$TOTAL" ] && exit 0
exit 1
