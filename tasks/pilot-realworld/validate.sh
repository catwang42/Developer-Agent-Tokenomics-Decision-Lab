#!/usr/bin/env bash
# Pilot task 10-point validation (SPEC 2.8). Proves the candidate pilot task is a
# valid benchmark: it is pinnable, reproducible, fails before modification, and
# is accepted by the deterministic gate on the canonical solution.
#
# The ten checks (SPEC 2.8):
#   1 commit exists            2 deps/ORM at commit     3 paths exist
#   4 clean install            5 baseline tests pass     6 pre-modification failure
#   7 hidden-test pass on canonical patch                8 no leakage
#   9 clean-container build    10 deterministic reset
#
# Emits a machine-readable validation-report.json and a human summary. Runs
# end-to-end in the clean container built from tasks/pilot-realworld/Dockerfile.
# Exit 0 iff no check FAILED (checks that legitimately await the human-held
# hidden tests are reported as awaiting_human, not failed — SPEC 2.6 / CP-TASK).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tasks/pilot-realworld/lib.sh
. "$SCRIPT_DIR/lib.sh"

REPORT_PATH="${VALIDATION_REPORT:-$WORKDIR/validation-report.json}"
PIN="$(manifest_pilot pinned_commit)"
REPO_URL="$(manifest_pilot repo)"
TASK_ID="$(manifest_pilot task_id)"
TARGET_PATH="$(task_field target_path)"
BASELINE_PATTERN="$(task_field baseline_test_pattern)"
CANONICAL_PATCH="$SCRIPT_DIR/canonical/fix-missing-user-id.patch"

# Parallel arrays for the report.
nums=(); ids=(); specs=(); statuses=(); details=()
HIDDEN_HASH="null"; HIDDEN_VERSION="null"

record() { # num id spec status detail
  nums+=("$1"); ids+=("$2"); specs+=("$3"); statuses+=("$4"); details+=("$5")
  printf '  [%-14s] %2s. %s — %s\n' "$4" "$1" "$2" "$5"
}
# status/exit convention: pass=0 fail=1 awaiting_human=2
mark() { # num id spec code detail
  local st
  case "$4" in
    0) st=pass ;;
    2) st=awaiting_human ;;
    *) st=fail ;;
  esac
  record "$1" "$2" "$3" "$st" "$5"
}

reset_tree() { bash "$SCRIPT_DIR/reset.sh" >/dev/null 2>&1; }
apply_canonical() { git -C "$SUBJECT_DIR" apply "$CANONICAL_PATCH"; }

echo "==================================================================="
echo " Pilot 10-point validation — $TASK_ID"
echo " repo $REPO_URL @ $PIN"
echo "==================================================================="

# --- Setup (clone + verify SHA + clean install + prisma generate) ------------
echo "-- setup --"
setup_rc=0
bash "$SCRIPT_DIR/setup.sh" || setup_rc=$?

# 1. commit exists (and HEAD pinned to it)
if [ "$setup_rc" -eq 0 ] && [ "$(git -C "$SUBJECT_DIR" rev-parse HEAD 2>/dev/null)" = "$PIN" ]; then
  mark 1 commit-exists "SPEC-2.8" 0 "pinned commit present; HEAD == $PIN"
else
  mark 1 commit-exists "SPEC-2.8" 1 "pinned commit not checked out (setup rc=$setup_rc)"
fi

# 2. deps/ORM at commit (package.json + lockfile + prisma schema + generated client)
if [ -f "$SUBJECT_DIR/package.json" ] && [ -f "$SUBJECT_DIR/package-lock.json" ] \
   && [ -f "$SUBJECT_DIR/src/prisma/schema.prisma" ] \
   && [ -d "$SUBJECT_DIR/node_modules/@prisma/client" ]; then
  mark 2 deps-orm "SPEC-2.8" 0 "package.json+lockfile, Prisma schema, generated @prisma/client"
else
  mark 2 deps-orm "SPEC-2.8" 1 "missing deps/lockfile/Prisma schema/generated client"
fi

# 3. paths exist (target file + test dir + jest config)
if [ -f "$SUBJECT_DIR/$TARGET_PATH" ] && [ -d "$SUBJECT_DIR/src/tests/services" ] \
   && [ -f "$SUBJECT_DIR/jest.config.ts" ]; then
  mark 3 paths-exist "SPEC-2.8" 0 "$TARGET_PATH, src/tests/services/, jest.config.ts"
else
  mark 3 paths-exist "SPEC-2.8" 1 "expected task paths missing"
fi

# 4. clean install (npm ci from lockfile succeeded during setup)
if [ "$setup_rc" -eq 0 ] && [ -d "$SUBJECT_DIR/node_modules" ]; then
  mark 4 clean-install "SPEC-2.8" 0 "npm ci from committed lockfile succeeded"
else
  mark 4 clean-install "SPEC-2.8" 1 "clean install failed (setup rc=$setup_rc)"
fi

# --- Deterministic-state checks (from a pristine pinned tree) -----------------
reset_tree

# 5. baseline tests pass (hermetic DB-free unit suites)
if run_jest --testPathPattern "$BASELINE_PATTERN" >/dev/null 2>&1; then
  mark 5 baseline-tests "SPEC-2.8" 0 "DB-free unit suites green ($BASELINE_PATTERN)"
else
  mark 5 baseline-tests "SPEC-2.8" 1 "baseline suites did not pass"
fi

# 8. no leakage (participant tree carries no planted answer; fix is absent pre-mod)
leak_rc=0
if grep -rIl --exclude-dir=node_modules --exclude-dir=.git \
     -e 'CANONICAL SOLUTION' -e 'PILOT-ANSWER' -e 'fix-missing-user-id.patch' \
     "$SUBJECT_DIR/src" >/dev/null 2>&1; then
  leak_rc=1
fi
# The canonical/ patch dir must not live inside the subject tree.
if find "$SUBJECT_DIR" -path "$SUBJECT_DIR/node_modules" -prune -o -name '*.patch' -print \
     2>/dev/null | grep -q .; then
  leak_rc=1
fi
if [ "$leak_rc" -eq 0 ]; then
  mark 8 no-leakage "SPEC-2.8" 0 "no planted solution/markers/patches in participant tree"
else
  mark 8 no-leakage "SPEC-2.8" 1 "possible leakage detected in participant tree"
fi

# 9. clean-container build (app compiles from the clean pinned tree)
if ( cd "$SUBJECT_DIR" && NX_DAEMON=false CI=true npx nx build --skip-nx-cache ) >/dev/null 2>&1; then
  in_ctr="host"; [ "${PILOT_IN_CONTAINER:-0}" = "1" ] && in_ctr="container"
  mark 9 clean-build "SPEC-2.8" 0 "nx build succeeds on clean pinned tree ($in_ctr)"
else
  mark 9 clean-build "SPEC-2.8" 1 "nx build failed on clean pinned tree"
fi

# 6. pre-modification failure (the gate must FAIL on the unmodified task)
reset_tree
premod_report="$WORKDIR/gate-premod.json"
GATE_REPORT="$premod_report" bash "$SCRIPT_DIR/gate/check-public.sh" >/dev/null 2>&1
premod_gate_rc=$?
repro_status="$(pilot_python - "$premod_report" <<'PY' 2>/dev/null || true
import json, sys
d = json.load(open(sys.argv[1]))
print(next((c["status"] for c in d["checks"] if c["id"] == "P1-repro-test"), "missing"))
PY
)"
if [ "$premod_gate_rc" -ne 0 ] && [ "$repro_status" = "fail" ]; then
  mark 6 premod-failure "SPEC-2.8" 0 "public gate fails pre-modification (repro test fails)"
else
  mark 6 premod-failure "SPEC-2.8" 1 "gate did not fail pre-modification as required"
fi

# 7. hidden-test pass on canonical patch (also: public gate accepts the canonical fix)
reset_tree
canon_rc=0
apply_canonical || canon_rc=1
if [ "$canon_rc" -eq 0 ] \
   && bash "$SCRIPT_DIR/gate/check-public.sh" >/dev/null 2>&1; then
  hidden_report="$WORKDIR/gate-hidden.json"
  HIDDEN_REPORT="$hidden_report" bash "$SCRIPT_DIR/gate/check-hidden.sh" >/dev/null 2>&1
  hidden_rc=$?
  if [ -f "$hidden_report" ]; then
    HIDDEN_HASH="$(pilot_python -c 'import json,sys;print(json.load(open(sys.argv[1])).get("hash") or "null")' "$hidden_report")"
    HIDDEN_VERSION="$(pilot_python -c 'import json,sys;print(json.load(open(sys.argv[1])).get("version") or "null")' "$hidden_report")"
  fi
  case "$hidden_rc" in
    0) mark 7 canonical-hidden "SPEC-2.8/2.6" 0 "canonical patch accepted; sealed hidden tests pass ($HIDDEN_HASH)" ;;
    2) mark 7 canonical-hidden "SPEC-2.8/2.6" 2 "canonical patch accepted by public gate; hidden tests AWAITING_HUMAN (tasks/hidden/)" ;;
    *) mark 7 canonical-hidden "SPEC-2.8/2.6" 1 "sealed hidden tests failed on canonical patch" ;;
  esac
else
  mark 7 canonical-hidden "SPEC-2.8/2.6" 1 "canonical patch did not apply / public gate rejected it"
fi
reset_tree

# 10. deterministic reset (two resets -> identical working-tree hash)
h1="$(bash "$SCRIPT_DIR/reset.sh" | grep -o 'tree=[0-9a-f]*' || true)"
h2="$(bash "$SCRIPT_DIR/reset.sh" | grep -o 'tree=[0-9a-f]*' || true)"
if [ -n "$h1" ] && [ "$h1" = "$h2" ]; then
  mark 10 deterministic-reset "SPEC-2.8" 0 "reset idempotent ($h1)"
else
  mark 10 deterministic-reset "SPEC-2.8" 1 "reset not idempotent ($h1 vs $h2)"
fi

# --- Emit report -------------------------------------------------------------
passed=0; failed=0; awaiting=0
for st in "${statuses[@]}"; do
  case "$st" in
    pass) passed=$((passed + 1)) ;;
    fail) failed=$((failed + 1)) ;;
    awaiting_human) awaiting=$((awaiting + 1)) ;;
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
pilot_python - "$REPORT_PATH" <<'PY'
import json, os, sys
nums = os.environ["V_NUMS"].splitlines()
ids = os.environ["V_IDS"].splitlines()
specs = os.environ["V_SPECS"].splitlines()
statuses = os.environ["V_STATUSES"].splitlines()
details = os.environ["V_DETAILS"].splitlines()
checks = [
    {"n": int(n), "id": i, "spec_ref": sp, "status": st, "detail": d}
    for n, i, sp, st, d in zip(nums, ids, specs, statuses, details)
]
report = {
    "task_id": os.environ["TASK_ID"],
    "repo": os.environ["REPO_URL"],
    "pinned_commit": os.environ["PIN"],
    "generated_utc": os.environ["STAMP"],
    "hidden_test_hash": None if os.environ["HIDDEN_HASH"] == "null" else os.environ["HIDDEN_HASH"],
    "hidden_test_version": None if os.environ["HIDDEN_VERSION"] == "null" else os.environ["HIDDEN_VERSION"],
    "summary": {
        "passed": int(os.environ["PASSED"]),
        "failed": int(os.environ["FAILED"]),
        "awaiting_human": int(os.environ["AWAITING"]),
        "total": int(os.environ["TOTAL"]),
    },
    "checks": checks,
}
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump(report, fh, indent=2)
print(json.dumps(report, indent=2))
PY

echo "==================================================================="
echo " RESULT: $passed passed, $awaiting awaiting-human, $failed failed (of $total)"
echo " report: $REPORT_PATH"
echo "==================================================================="

[ "$failed" -eq 0 ]
