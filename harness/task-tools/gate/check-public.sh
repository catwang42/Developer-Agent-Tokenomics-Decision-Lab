#!/usr/bin/env bash
# PUBLIC teaching gate (SPEC 2.6, deterministic-first), parameterized by TASK_DIR.
#
# Judges the CURRENT state of the subject working tree ($SUBJECT_DIR) as a
# candidate solution. Visible checks only; the authoritative sealed hidden tests
# are separate (check-hidden.sh). The generating model is never the sole verifier
# of its own work (SPEC 2.6): this gate is deterministic and agent-independent.
#
# Checks, in SPEC 2.6 priority order (restricted to those reproducible on this
# repo — eslint/prettier are excluded because the upstream tree is not clean under
# them at the pinned commit, so they would fail regardless of the agent's change):
#   P1 public deterministic test  : the task's public test passes
#   P2 regression                 : hermetic DB-free unit suites still pass
#   P3 type checking              : tsc --noEmit passes
#   P4 build                      : the app compiles (nx build)
#   P5 no leakage                 : no canonical patch / solution markers in tree
#   P6 diff scope                 : only the allowed PRODUCT path(s) changed vs pin
#
# Anti-gaming (the agent cannot pass by editing tests):
#   * target_paths lists PRODUCT files only; P6 fails on ANY test-file edit.
#   * before grading, ALL test files are restored to their pinned version
#     (tracked edits discarded, untracked test files removed), so agent edits to
#     existing/baseline tests never reach P1/P2/P3/P4.
#   * the public test is (re)injected fresh from the task definition.
#   * an optional harness-owned test_compat_patch (type-compat only, NOT
#     agent-authored) is applied AFTER the restore so the immutable baseline suite
#     compiles against a schema change.
#   * hidden tests live outside the subject repo and are injected only by
#     check-hidden.sh, never present in the tree the agent sees.
#
# Exit 0 iff every check passes. With GATE_REPORT set, also writes a JSON array.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness/task-tools/lib.sh
. "$SCRIPT_DIR/../lib.sh"

PUBLIC_TEST="$TASK_DIR/$(task_field public_test)"
PUBLIC_DST="$SUBJECT_DIR/src/tests/services/$(basename "$PUBLIC_TEST")"
BASELINE_PATTERN="$(task_field baseline_test_pattern)"
mapfile -t TARGET_PATHS < <(task_list target_paths)
# Optional harness-owned type-compat shim (empty if the task declares none).
COMPAT_PATCH_REL="$(task_field test_compat_patch 2>/dev/null || true)"

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
