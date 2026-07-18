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
#   P6 diff scope                 : only the allowed path(s) changed vs the pin
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
  mark P6-diff-scope "unexpected changes:$unexpected" 1
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
