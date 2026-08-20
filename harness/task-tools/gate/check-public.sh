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
# Paths restored to pristine before grading (anti-gaming). Default = the RealWorld
# tests dir, so the pre-existing node tasks are unchanged.
mapfile -t PROTECTED_TEST_PATHS < <(task_list protected_test_paths)
[ "${#PROTECTED_TEST_PATHS[@]}" -gt 0 ] || PROTECTED_TEST_PATHS=(src/tests)

# Installed dependency trees are vendor bytes, not participant edits, so they are
# excluded from every diff-scope view. Most subject repos gitignore them (zarr and
# sqlfluff both ignore .venv), but that is the repo's choice, not ours — take the
# list from the stack driver so a non-ignored install dir can never be read as an
# agent edit. Empty for the `none` stack, which installs nothing.
SCOPE_EXCL=()
while IFS= read -r keep; do
  [ -n "$keep" ] && SCOPE_EXCL+=(":!$keep")
done < <(stack_clean_keep)

# `git status --porcelain -uall` over the participant tree, install dirs excluded.
tree_status() {
  git -C "$SUBJECT_DIR" -c core.quotepath=false status --porcelain \
    --untracked-files=all -- "${SCOPE_EXCL[@]+"${SCOPE_EXCL[@]}"}" 2>/dev/null
}

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

# Write the JSON report of whatever has been marked so far. A function, not a
# trailing block, so an early abort still leaves a report naming the reason — a
# missing report reads as "the harness broke", which is the wrong diagnosis.
emit_report() {
  [ -n "${GATE_REPORT:-}" ] || return 0
  [ "${#ids[@]}" -gt 0 ] || return 0
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
}

# --- G0: git must be able to READ the subject repo -----------------------------
# Every diff-scope judgement below, and every "restore to pristine" that keeps an
# agent from grading itself, is a git call whose stderr was discarded. When git
# refuses the repo those calls return EMPTY, which is indistinguishable from a
# clean tree: P6/T1 pass vacuously and the restores silently do nothing. The
# mechanism and the batch-1 evidence are documented once, on git_trust_subject in
# lib.sh — which the HIDDEN gate now calls too. Both gates are separate `docker
# run` invocations, so a fix exported in one cannot reach the other; that is
# precisely how the hidden gate went without this guard for a whole batch.
if git_trust_subject; then
  mark G0-subject-readable "git can read the subject tree (diff-scope is meaningful)" 0
else
  mark G0-subject-readable "git cannot read $SUBJECT_DIR: $(git_subject_error)" 1
  emit_report
  echo "== public gate: FAIL (subject tree unreadable; nothing was graded) =="
  exit 1
fi

if [ "$GATE_TYPE" = "test_generation" ]; then
  # ===================== test-generation gate (T1–T4) =====================
  WRITE_SCOPE="$(task_field agent_write_scope)"
  echo "== public gate ($(task_field task_id)) [test_generation] =="

  # T1 diff-scope FIRST, before we touch the tree. The only allowed change is NEW
  # files under WRITE_SCOPE; any tracked-file edit, or any out-of-scope add, fails.
  scope_out="$(tree_status \
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
    stack_post_patch
    pattern="$(stack_selector "${graded[@]}")"

    # T2 suite-green: hermetic baseline (the new tests live inside its scope).
    stack_baseline_tests
    mark T2-suite-green "baseline suite ($BASELINE_PATTERN)" $?

    # T3 coverage: measure branch coverage of the target mappers achieved BY the
    # agent's tests; per-file thresholds evaluated by coverage_eval.py.
    COV_DIR="$WORKDIR/.covrun"
    cov_summary="$(stack_coverage_summary "$pattern" "$COV_DIR")"
    if [ -n "$cov_summary" ] && [ -f "$cov_summary" ]; then
      cov_detail="$(pilot_python "$SCRIPT_DIR/coverage_eval.py" "$cov_summary" "$TASK_YAML")"
      cov_rc=$?
    else
      cov_detail="coverage summary not produced"; cov_rc=1
    fi
    mark T3-coverage "$cov_detail" "$cov_rc"
    rm -rf "$COV_DIR"

    # T4 tests-pass: the agent's new tests pass against the pinned (pristine) code.
    stack_run_selected "$pattern"
    mark T4-tests-pass "agent's new tests pass on the pinned target files" $?
  fi

else
  # ===================== solution gate (P1–P6) =====================
  PUBLIC_TEST="$TASK_DIR/$(task_field public_test)"
  # Where the public test is injected inside the subject tree (repo-relative dir).
  PUBLIC_DST_DIR="$(task_field_opt public_test_dest src/tests/services)"
  PUBLIC_DST_REL="${PUBLIC_DST_DIR%/}/$(basename "$PUBLIC_TEST")"
  PUBLIC_DST="$SUBJECT_DIR/$PUBLIC_DST_REL"
  # Extra files the public test needs in place to be collected (e.g. a package
  # __init__.py that the upstream PR adds alongside its new test module).
  mapfile -t PUBLIC_TEST_SUPPORT < <(task_list public_test_support)
  # Optional harness-owned type-compat shim (empty if the task declares none).
  COMPAT_PATCH_REL="$(task_field test_compat_patch 2>/dev/null || true)"

  echo "== public gate ($(task_field task_id)) =="

  # Keep anything derived from source in step with the (possibly patched) tree.
  stack_post_patch

  # P6 diff scope FIRST, before we inject any gate artifact into the tree.
  changed="$(tree_status | awk '{print $2}' | sort -u)"
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
  for p in "${PROTECTED_TEST_PATHS[@]}"; do
    git -C "$SUBJECT_DIR" checkout -q -- "$p" 2>/dev/null || true
    git -C "$SUBJECT_DIR" clean -fdq -- "$p" 2>/dev/null || true
  done
  # Apply the type-compat shim (touches only *.test.ts) so the immutable baseline
  # suite compiles against a schema change. Not agent-authored, not agent-modifiable.
  if [ -n "$COMPAT_PATCH_REL" ] && [ -f "$TASK_DIR/$COMPAT_PATCH_REL" ]; then
    git -C "$SUBJECT_DIR" apply "$TASK_DIR/$COMPAT_PATCH_REL" \
      || echo "  WARN  test_compat_patch failed to apply" >&2
  fi

  # P5 no leakage: no planted answer markers, and no stray patch files, in the tree.
  leak=0
  leak_found && leak=1
  mark P5-no-leakage "no canonical patch / solution markers in tree" "$leak"

  # P3 type check.
  stack_typecheck
  mark P3-typecheck "$(stack_typecheck_detail)" $?

  # P4 build.
  stack_build
  mark P4-build "$(stack_build_detail)" $?

  # P1 public test: inject, run, then remove so it never pollutes the tree.
  injected_public=("$PUBLIC_DST")
  mkdir -p "$(dirname "$PUBLIC_DST")"
  cp "$PUBLIC_TEST" "$PUBLIC_DST"
  # Any support file the upstream PR added alongside its new test module (e.g. a
  # package __init__.py) is created empty if absent, and removed again after.
  for sup in "${PUBLIC_TEST_SUPPORT[@]+"${PUBLIC_TEST_SUPPORT[@]}"}"; do
    [ -n "$sup" ] || continue
    if [ ! -e "$SUBJECT_DIR/$sup" ]; then
      mkdir -p "$(dirname "$SUBJECT_DIR/$sup")"
      : > "$SUBJECT_DIR/$sup"
      injected_public+=("$SUBJECT_DIR/$sup")
    fi
  done
  stack_run_selected "$(stack_selector "$PUBLIC_DST_REL")"
  public_rc=$?
  rm -f "${injected_public[@]}"
  mark P1-public-test "$(task_field public_test_desc)" "$public_rc"

  # P2 regression: the hermetic baseline suite.
  stack_baseline_tests
  mark P2-regression "baseline suite ($BASELINE_PATTERN)" $?
fi

emit_report

echo "== public gate: $([ "$overall" -eq 0 ] && echo PASS || echo FAIL) =="
exit "$overall"
