#!/usr/bin/env bash
# Task 10-point validation (SPEC 2.8), parameterized by TASK_DIR. Proves a
# candidate task is a valid benchmark: pinnable, reproducible, fails before
# modification, and accepted by the deterministic gate on the canonical solution.
#
# The ten checks (SPEC 2.8):
#   1 commit exists            2 deps/ORM at commit     3 paths exist
#   4 clean install            5 baseline tests pass     6 pre-modification failure
#   7 hidden-test pass on canonical patch                8 no leakage
#   9 clean-container build    10 deterministic reset
#
# Pre-modification failure (check 6) is satisfied via the task's PUBLIC test:
#   - bugfix tasks ship a repro test that fails until the defect is fixed;
#   - feature tasks ship a feature-spec test that fails because the endpoints /
#     fields do not exist yet on the unmodified repo (SPEC 2.8 feature-task
#     interpretation). Either way the public gate must FAIL before modification.
#
# Toolchain-specific steps (install, test, build, coverage) come from the stack
# driver named by task.yaml `stack:` — see harness/task-tools/stacks/README.md.
# A stack may declare a check to have no referent (a review task installs and
# builds nothing); those are recorded `not_applicable` WITH a reason, never
# silently passed.
#
# Emits validation-report.json + a human summary. Runs end-to-end in the clean
# container (harness/task-tools/Dockerfile). Exit 0 iff no check FAILED (checks
# awaiting the human-held hidden tests are reported awaiting_human, not failed).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness/task-tools/lib.sh
. "$SCRIPT_DIR/lib.sh"

REPORT_PATH="${VALIDATION_REPORT:-$WORKDIR/validation-report.json}"
PIN="$(manifest_task pinned_commit)"
REPO_URL="$(manifest_task repo)"
TASK_ID="$(task_field task_id)"
CANONICAL_PATCH="$TASK_DIR/$(task_field canonical_patch)"
mapfile -t TARGET_PATHS < <(task_list target_paths)
GATE_TYPE="$(task_field gate_type 2>/dev/null || echo solution)"
# The public check that must FAIL pre-modification, per gate type: the solution
# gate's public test, or the test-generation gate's coverage check (no agent tests
# yet -> 0% coverage). The tests dir that must exist (check 3): the agent's write
# scope for test-generation, else the task's declared tests dir (RealWorld default).
case "$GATE_TYPE" in
  test_generation)
    PREMOD_CHECK_ID="T3-coverage"
    TESTS_DIR="$(task_field agent_write_scope)" ;;
  pr_review)
    # No public gate can run before the sealed defect map exists (see below).
    PREMOD_CHECK_ID="R1-defect-recall"
    TESTS_DIR="$(task_field_opt tests_dir .)" ;;
  *)
    PREMOD_CHECK_ID="P1-public-test"
    TESTS_DIR="$(task_field_opt tests_dir src/tests/services)" ;;
esac

# Checks the stack declares to have no referent (see stacks/none.sh). Recorded
# not_applicable WITH a reason — never silently passed, never counted as failed.
declare -A NA_REASON=()
while IFS=$'\t' read -r na_id na_why; do
  [ -n "$na_id" ] && NA_REASON["$na_id"]="$na_why"
done < <(stack_na_checks)

nums=(); ids=(); specs=(); statuses=(); details=()
HIDDEN_HASH="null"; HIDDEN_VERSION="null"

record() { nums+=("$1"); ids+=("$2"); specs+=("$3"); statuses+=("$4"); details+=("$5")
  printf '  [%-14s] %2s. %s — %s\n' "$4" "$1" "$2" "$5"; }
mark() { # num id spec code detail  (code: 0 pass, 2 awaiting_human, else fail)
  local st
  case "$4" in 0) st=pass ;; 2) st=awaiting_human ;; *) st=fail ;; esac
  record "$1" "$2" "$3" "$st" "$5"
}
# True (and records the check) when this stack declares the check inapplicable.
na() { # num id spec
  [ -n "${NA_REASON[$2]:-}" ] || return 1
  record "$1" "$2" "$3" not_applicable "${NA_REASON[$2]}"
}

reset_tree() { bash "$SCRIPT_DIR/reset.sh" >/dev/null 2>&1; }

echo "==================================================================="
echo " 10-point validation — $TASK_ID"
echo " repo $REPO_URL @ $PIN"
echo "==================================================================="

echo "-- setup --"
setup_rc=0
bash "$SCRIPT_DIR/setup.sh" || setup_rc=$?

# 1. commit exists
if [ "$setup_rc" -eq 0 ] && [ "$(git -C "$SUBJECT_DIR" rev-parse HEAD 2>/dev/null)" = "$PIN" ]; then
  mark 1 commit-exists "SPEC-2.8" 0 "pinned commit present; HEAD == $PIN"
else
  mark 1 commit-exists "SPEC-2.8" 1 "pinned commit not checked out (setup rc=$setup_rc)"
fi

# 2. deps/ORM at commit
if ! na 2 deps-orm "SPEC-2.8"; then
  if stack_deps_ok; then
    mark 2 deps-orm "SPEC-2.8" 0 "$(stack_deps_detail)"
  else
    mark 2 deps-orm "SPEC-2.8" 1 "missing/uninstalled dependency manifest for the $TASK_STACK stack"
  fi
fi

# 3. paths exist (each declared target path + test dir + the stack's config files)
paths_ok=1; missing=""
for t in "${TARGET_PATHS[@]}"; do
  [ -e "$SUBJECT_DIR/$t" ] || { paths_ok=0; missing="$missing $t"; }
done
[ -d "$SUBJECT_DIR/${TESTS_DIR%/}" ] || { paths_ok=0; missing="$missing ${TESTS_DIR%/}/"; }
while IFS= read -r cfg; do
  [ -n "$cfg" ] || continue
  [ -e "$SUBJECT_DIR/$cfg" ] || { paths_ok=0; missing="$missing $cfg"; }
done < <(stack_config_paths)
if [ "$paths_ok" -eq 1 ]; then
  mark 3 paths-exist "SPEC-2.8" 0 "${#TARGET_PATHS[@]} target path(s), ${TESTS_DIR%/}/, $(stack_config_paths | tr '\n' ' ')"
else
  mark 3 paths-exist "SPEC-2.8" 1 "expected task paths missing:$missing"
fi

# 4. clean install
if ! na 4 clean-install "SPEC-2.8"; then
  if [ "$setup_rc" -eq 0 ] && stack_installed_ok; then
    mark 4 clean-install "SPEC-2.8" 0 "$(stack_install_detail)"
  else
    mark 4 clean-install "SPEC-2.8" 1 "clean install failed (setup rc=$setup_rc)"
  fi
fi

reset_tree

# 5. baseline tests pass
if ! na 5 baseline-tests "SPEC-2.8"; then
  if stack_baseline_tests; then
    mark 5 baseline-tests "SPEC-2.8" 0 "$(stack_baseline_detail)"
  else
    mark 5 baseline-tests "SPEC-2.8" 1 "baseline suites did not pass"
  fi
fi

# 8. no leakage
leak_rc=0
if leak_found; then leak_rc=1; fi
if [ "$leak_rc" -eq 0 ]; then
  mark 8 no-leakage "SPEC-2.8" 0 "no planted solution/markers/patches in participant tree"
else
  mark 8 no-leakage "SPEC-2.8" 1 "possible leakage detected in participant tree"
fi

# 9. clean-container build
if ! na 9 clean-build "SPEC-2.8"; then
  if stack_build; then
    in_ctr="host"; [ "${TASK_IN_CONTAINER:-0}" = "1" ] && in_ctr="container"
    mark 9 clean-build "SPEC-2.8" 0 "$(stack_build_detail) on clean pinned tree ($in_ctr)"
  else
    mark 9 clean-build "SPEC-2.8" 1 "build failed on clean pinned tree"
  fi
fi

# 6. pre-modification failure (public gate must FAIL on the unmodified task)
reset_tree
if [ "$GATE_TYPE" = "pr_review" ]; then
  # A review task's only gate is the matcher over the SEALED defect map: with no
  # map there is no gate to fail, and an empty review cannot be scored. This is
  # awaiting_human, not a pass — see hidden/README-FOR-HUMAN.md.
  mark 6 premod-failure "SPEC-2.8" 2 \
    "review gate needs the sealed defect map to score an empty review ($TASK_DIR/hidden/)"
  mark 7 canonical-hidden "SPEC-2.8/2.6" 2 \
    "review gate needs the sealed defect map ($TASK_DIR/hidden/)"
else
premod_report="$WORKDIR/gate-premod.json"
GATE_REPORT="$premod_report" bash "$SCRIPT_DIR/gate/check-public.sh" >/dev/null 2>&1
premod_gate_rc=$?
public_status="$(PREMOD_CHECK_ID="$PREMOD_CHECK_ID" pilot_python - "$premod_report" <<'PY' 2>/dev/null || true
import json, os, sys
d = json.load(open(sys.argv[1]))
cid = os.environ["PREMOD_CHECK_ID"]
print(next((c["status"] for c in d["checks"] if c["id"] == cid), "missing"))
PY
)"
if [ "$premod_gate_rc" -ne 0 ] && [ "$public_status" = "fail" ]; then
  mark 6 premod-failure "SPEC-2.8" 0 "public gate fails pre-modification ($PREMOD_CHECK_ID fails)"
else
  mark 6 premod-failure "SPEC-2.8" 1 "gate did not fail pre-modification as required"
fi

# 7. hidden-test pass on canonical patch (also: public gate accepts the canonical fix)
reset_tree
if [ ! -f "$CANONICAL_PATCH" ] && [ "${TASK_IN_CONTAINER:-0}" = "1" ]; then
  # .dockerignore excludes canonical/ from the validation images on purpose
  # (subject isolation, FIX D): the answer patch must not be readable from a tree
  # the agent leg can reach. So a containerized run genuinely CANNOT perform
  # check 7 — that is not_applicable-with-reason, not a failure and not a pass.
  # Check 7 is verified on the host, where canonical/ is present.
  record 7 canonical-hidden "SPEC-2.8/2.6" not_applicable \
    "canonical/ excluded from the container image by .dockerignore (subject isolation); check 7 is host-verified"
else
canon_rc=0
git -C "$SUBJECT_DIR" apply "$CANONICAL_PATCH" || canon_rc=1
stack_post_patch
if [ "$canon_rc" -eq 0 ] && bash "$SCRIPT_DIR/gate/check-public.sh" >/dev/null 2>&1; then
  hidden_report="$WORKDIR/gate-hidden.json"
  HIDDEN_REPORT="$hidden_report" bash "$SCRIPT_DIR/gate/check-hidden.sh" >/dev/null 2>&1
  hidden_rc=$?
  if [ -f "$hidden_report" ]; then
    HIDDEN_HASH="$(pilot_python -c 'import json,sys;print(json.load(open(sys.argv[1])).get("hash") or "null")' "$hidden_report")"
    HIDDEN_VERSION="$(pilot_python -c 'import json,sys;print(json.load(open(sys.argv[1])).get("version") or "null")' "$hidden_report")"
  fi
  case "$hidden_rc" in
    0) mark 7 canonical-hidden "SPEC-2.8/2.6" 0 "canonical patch accepted; sealed hidden tests pass ($HIDDEN_HASH)" ;;
    2) mark 7 canonical-hidden "SPEC-2.8/2.6" 2 "canonical patch accepted by public gate; hidden tests AWAITING_HUMAN ($TASK_DIR/hidden/)" ;;
    *) mark 7 canonical-hidden "SPEC-2.8/2.6" 1 "sealed hidden tests failed on canonical patch" ;;
  esac
else
  mark 7 canonical-hidden "SPEC-2.8/2.6" 1 "canonical patch did not apply / public gate rejected it"
fi
fi   # end: canonical patch present (or host run)
fi   # end: gate types with an executable public gate
reset_tree

# 10. deterministic reset
h1="$(bash "$SCRIPT_DIR/reset.sh" | grep -o 'tree=[0-9a-f]*' || true)"
h2="$(bash "$SCRIPT_DIR/reset.sh" | grep -o 'tree=[0-9a-f]*' || true)"
if [ -n "$h1" ] && [ "$h1" = "$h2" ]; then
  mark 10 deterministic-reset "SPEC-2.8" 0 "reset idempotent ($h1)"
else
  mark 10 deterministic-reset "SPEC-2.8" 1 "reset not idempotent ($h1 vs $h2)"
fi

# --- Emit report -------------------------------------------------------------
passed=0; failed=0; awaiting=0; not_applicable=0
for st in "${statuses[@]}"; do
  case "$st" in
    pass) passed=$((passed + 1)) ;;
    fail) failed=$((failed + 1)) ;;
    awaiting_human) awaiting=$((awaiting + 1)) ;;
    not_applicable) not_applicable=$((not_applicable + 1)) ;;
  esac
done
total=${#statuses[@]}

STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
mkdir -p "$(dirname "$REPORT_PATH")"
V_NUMS="$(printf '%s\n' "${nums[@]}")" V_IDS="$(printf '%s\n' "${ids[@]}")" \
V_SPECS="$(printf '%s\n' "${specs[@]}")" V_STATUSES="$(printf '%s\n' "${statuses[@]}")" \
V_DETAILS="$(printf '%s\n' "${details[@]}")" \
TASK_ID="$TASK_ID" REPO_URL="$REPO_URL" PIN="$PIN" STAMP="$STAMP" \
HIDDEN_HASH="$HIDDEN_HASH" HIDDEN_VERSION="$HIDDEN_VERSION" \
PASSED="$passed" FAILED="$failed" AWAITING="$awaiting" TOTAL="$total" \
NOT_APPLICABLE="$not_applicable" TASK_STACK="$TASK_STACK" GATE_TYPE="$GATE_TYPE" \
pilot_python - "$REPORT_PATH" <<'PY'
import json, os, sys
z = zip(os.environ["V_NUMS"].splitlines(), os.environ["V_IDS"].splitlines(),
        os.environ["V_SPECS"].splitlines(), os.environ["V_STATUSES"].splitlines(),
        os.environ["V_DETAILS"].splitlines())
checks = [{"n": int(n), "id": i, "spec_ref": sp, "status": st, "detail": d}
          for n, i, sp, st, d in z]
report = {
    "task_id": os.environ["TASK_ID"],
    "repo": os.environ["REPO_URL"],
    "pinned_commit": os.environ["PIN"],
    "generated_utc": os.environ["STAMP"],
    "stack": os.environ["TASK_STACK"],
    "gate_type": os.environ["GATE_TYPE"],
    "hidden_test_hash": None if os.environ["HIDDEN_HASH"] == "null" else os.environ["HIDDEN_HASH"],
    "hidden_test_version": None if os.environ["HIDDEN_VERSION"] == "null" else os.environ["HIDDEN_VERSION"],
    "summary": {"passed": int(os.environ["PASSED"]), "failed": int(os.environ["FAILED"]),
                "awaiting_human": int(os.environ["AWAITING"]),
                "not_applicable": int(os.environ["NOT_APPLICABLE"]),
                "total": int(os.environ["TOTAL"])},
    "checks": checks,
}
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(report, fh, indent=2)
print(json.dumps(report, indent=2))
PY

echo "==================================================================="
echo " RESULT: $passed passed, $awaiting awaiting-human, $not_applicable n/a, $failed failed (of $total)"
echo " report: $REPORT_PATH"
echo "==================================================================="
[ "$failed" -eq 0 ]
