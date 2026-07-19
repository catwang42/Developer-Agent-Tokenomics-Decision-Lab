#!/usr/bin/env bash
# PUBLIC teaching gate (SPEC 2.6, deterministic-first), parameterized by TASK_DIR.
#
# Judges the CURRENT state of the subject working tree ($SUBJECT_DIR) as a
# candidate solution. Visible checks only; the authoritative sealed hidden tests
# are separate (check-hidden.sh). The generating model is never the sole verifier
# of its own work (SPEC 2.6): this gate is deterministic and agent-independent.
#
# Two gate types (task.yaml `gate_type`, default `solution`):
#
#   solution (feature / bugfix) — the agent writes PRODUCT code; the gate grades it:
#     P1 public deterministic test  : the task's public test passes
#     P2 regression                 : hermetic DB-free unit suites still pass
#     P3 type checking              : tsc --noEmit passes
#     P4 build                      : the app compiles (nx build)
#     P5 no leakage                 : no canonical patch / solution markers in tree
#     P6 diff scope                 : only the allowed PRODUCT path(s) changed vs pin
#
#   test_generation — the agent writes TESTS; the gate grades the tests, not a feature:
#     T1 diff-scope   : ONLY new files under agent_write_scope changed; no product/
#                       config/existing-test edits (checks the contract, not a shape)
#     T2 suite-green  : the DB-free baseline suite passes WITH the agent's new tests
#     T3 coverage     : per-file branch coverage of the target mappers >= min_pct
#     T4 tests-pass   : the agent's new tests pass against the pinned (pristine) code
#
# Anti-gaming is shared in spirit: diff-scope is judged FIRST on the agent's tree,
# then everything the agent must not influence is restored to pristine before the
# remaining checks run — so a solution can never pass by editing what it is graded
# against (tests for `solution`; the product mappers for `test_generation`).
#
# Exit 0 iff every check passes. With GATE_REPORT set, also writes a JSON array.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness/task-tools/lib.sh
. "$SCRIPT_DIR/../lib.sh"

GATE_TYPE="$(task_field gate_type 2>/dev/null || echo solution)"
BASELINE_PATTERN="$(task_field baseline_test_pattern)"
mapfile -t TARGET_PATHS < <(task_list target_paths)

ids=(); statuses=(); details=()
record() { ids+=("$1"); statuses+=("$2"); details+=("$3"); }

overall=0
mark() { # id detail exit-code
  if [ "$3" -eq 0 ]; then
    record "$1" pass "$2"; echo "  [pass] $1 — $2"
  else
    record "$1" fail "$2"; echo "  [fail] $1 — $2"; overall=1
  fi
}

if [ "$GATE_TYPE" = "test_generation" ]; then
  # ===================== test-generation gate (T1–T4) =====================
  WRITE_SCOPE="$(task_field agent_write_scope)"
  echo "== public gate ($(task_field task_id)) [test_generation] =="

  # T1 diff-scope FIRST, before we touch the tree. The only allowed change is NEW
  # files under WRITE_SCOPE; any tracked-file edit, or any out-of-scope add, fails.
  scope_out="$(git -C "$SUBJECT_DIR" -c core.quotepath=false status --porcelain \
                --untracked-files=all -- ':!node_modules' 2>/dev/null \
              | pilot_python "$SCRIPT_DIR/scope_eval.py" "$WRITE_SCOPE" "${TARGET_PATHS[@]}")"
  scope_rc=$?
  graded=()
  while IFS=$'\t' read -r kind path; do
    [ "$kind" = "TEST" ] && [ -n "$path" ] && graded+=("$path")
  done <<< "$scope_out"
  if [ "$scope_rc" -eq 0 ]; then
    mark T1-diff-scope "only new test files under $WRITE_SCOPE" 0
  else
    viol="$(printf '%s\n' "$scope_out" | sed -n 's/^BAD\t/ /p' | tr -d '\n')"
    mark T1-diff-scope "forbidden changes:$viol" 1
  fi

  # Neutralise any product/config/existing-test tampering the agent may have made,
  # while KEEPING the untracked new test files we grade. Restores tracked files to
  # the pinned version; never `git clean` (that would delete the agent's new tests).
  git -C "$SUBJECT_DIR" checkout -q -- . 2>/dev/null || true

  if [ "${#graded[@]}" -eq 0 ]; then
    # No new tests to grade (also the pre-modification state) -> T2/T3/T4 fail.
    mark T2-suite-green "no agent test files under $WRITE_SCOPE" 1
    mark T3-coverage "no agent test files under $WRITE_SCOPE" 1
    mark T4-tests-pass "no agent test files under $WRITE_SCOPE" 1
  else
    prisma_generate
    pattern="$(printf '%s|' "${graded[@]}" | sed 's/|$//')"

    # T2 suite-green: hermetic DB-free baseline (includes the new tests via pattern).
    run_jest --testPathPattern "$BASELINE_PATTERN" >/dev/null 2>&1
    mark T2-suite-green "DB-free baseline suite ($BASELINE_PATTERN)" $?

    # T3 coverage: measure branch coverage of the target mappers achieved BY the
    # agent's tests; per-file thresholds evaluated by coverage_eval.py.
    COV_DIR="$WORKDIR/.covrun"; rm -rf "$COV_DIR"
    cov_from=()
    while IFS= read -r cf; do
      [ -n "$cf" ] && cov_from+=("--collectCoverageFrom=$cf")
    done < <(coverage_files)
    run_jest --testPathPattern "$pattern" --coverage "${cov_from[@]}" \
      --coverageReporters=json-summary --coverageDirectory "$COV_DIR" >/dev/null 2>&1
    cov_summary="$COV_DIR/coverage-summary.json"
    if [ -f "$cov_summary" ]; then
      cov_detail="$(pilot_python "$SCRIPT_DIR/coverage_eval.py" "$cov_summary" "$TASK_YAML")"
      cov_rc=$?
    else
      cov_detail="coverage summary not produced"; cov_rc=1
    fi
    mark T3-coverage "$cov_detail" "$cov_rc"
    rm -rf "$COV_DIR"

    # T4 tests-pass: the agent's new tests pass against the pinned (pristine) mappers.
    run_jest --testPathPattern "$pattern" >/dev/null 2>&1
    mark T4-tests-pass "agent's new tests pass on pinned mappers" $?
  fi

else
  # ===================== solution gate (P1–P6) =====================
  PUBLIC_TEST="$TASK_DIR/$(task_field public_test)"
  PUBLIC_DST="$SUBJECT_DIR/src/tests/services/$(basename "$PUBLIC_TEST")"
  # Optional harness-owned type-compat shim (empty if the task declares none).
  COMPAT_PATCH_REL="$(task_field test_compat_patch 2>/dev/null || true)"

  echo "== public gate ($(task_field task_id)) =="

  # Keep the generated Prisma client in step with the (possibly patched) schema.
  prisma_generate

  # P6 diff scope FIRST, before we inject any gate artifact into the tree.
  changed="$(git -C "$SUBJECT_DIR" -c core.quotepath=false status --porcelain \
              --untracked-files=all -- ':!node_modules' 2>/dev/null | awk '{print $2}' | sort -u)"
  unexpected=""
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    allowed=0
    for t in "${TARGET_PATHS[@]}"; do [ "$f" = "$t" ] && allowed=1 && break; done
    [ "$allowed" -eq 0 ] && unexpected="$unexpected $f"
  done <<< "$changed"
  if [ -z "${unexpected// /}" ]; then
    mark P6-diff-scope "only allowed path(s) changed vs pin" 0
  else
    mark P6-diff-scope "unexpected changes (incl. any test-file edit):$unexpected" 1
  fi

  # --- Restore tests to pristine, then apply harness-owned type-compat shim ------
  # Diff-scope has already judged the agent's tree; now neutralise any test-file
  # tampering before grading. Restore tracked test files to the pinned version and
  # remove untracked ones (e.g. an agent-added test), so P1/P2/P3/P4 run against
  # tests the agent cannot influence.
  git -C "$SUBJECT_DIR" checkout -q -- src/tests 2>/dev/null || true
  git -C "$SUBJECT_DIR" clean -fdq -- src/tests 2>/dev/null || true
  # Apply the type-compat shim (touches only *.test.ts) so the immutable baseline
  # suite compiles against a schema change. Not agent-authored, not agent-modifiable.
  if [ -n "$COMPAT_PATCH_REL" ] && [ -f "$TASK_DIR/$COMPAT_PATCH_REL" ]; then
    git -C "$SUBJECT_DIR" apply "$TASK_DIR/$COMPAT_PATCH_REL" \
      || echo "  WARN  test_compat_patch failed to apply" >&2
  fi

  # P5 no leakage: no planted answer markers, and no stray patch files, in the tree.
  leak=0
  if grep -rIl --exclude-dir=node_modules --exclude-dir=.git \
       -e 'CANONICAL SOLUTION' -e 'PILOT-ANSWER' \
       "$SUBJECT_DIR/src" >/dev/null 2>&1; then
    leak=1
  fi
  if find "$SUBJECT_DIR" -path "$SUBJECT_DIR/node_modules" -prune -o -name '*.patch' -print \
       2>/dev/null | grep -q .; then
    leak=1
  fi
  mark P5-no-leakage "no canonical patch / solution markers in tree" "$leak"

  # P3 type check.
  ( cd "$SUBJECT_DIR" && npx tsc -p tsconfig.app.json --noEmit ) >/dev/null 2>&1
  mark P3-typecheck "tsc -p tsconfig.app.json --noEmit" $?

  # P4 build.
  ( cd "$SUBJECT_DIR" && NX_DAEMON=false CI=true npx nx build --skip-nx-cache ) >/dev/null 2>&1
  mark P4-build "nx build (app compiles)" $?

  # P1 public test: inject, run, then remove so it never pollutes the tree.
  cp "$PUBLIC_TEST" "$PUBLIC_DST"
  run_jest --testPathPattern "$(basename "$PUBLIC_TEST")" >/dev/null 2>&1
  public_rc=$?
  rm -f "$PUBLIC_DST"
  mark P1-public-test "$(task_field public_test_desc)" "$public_rc"

  # P2 regression: hermetic DB-free unit suites.
  run_jest --testPathPattern "$BASELINE_PATTERN" >/dev/null 2>&1
  mark P2-regression "DB-free unit suites ($BASELINE_PATTERN)" $?
fi

if [ -n "${GATE_REPORT:-}" ]; then
  GR_IDS="$(printf '%s\n' "${ids[@]}")" \
  GR_STATUSES="$(printf '%s\n' "${statuses[@]}")" \
  GR_DETAILS="$(printf '%s\n' "${details[@]}")" \
  pilot_python - "$GATE_REPORT" <<'PY'
import json, os, sys
ids = os.environ["GR_IDS"].splitlines()
statuses = os.environ["GR_STATUSES"].splitlines()
details = os.environ["GR_DETAILS"].splitlines()
checks = [{"id": i, "status": s, "detail": d}
          for i, s, d in zip(ids, statuses, details)]
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump({"gate": "public", "checks": checks}, fh, indent=2)
PY
fi

echo "== public gate: $([ "$overall" -eq 0 ] && echo PASS || echo FAIL) =="
exit "$overall"
