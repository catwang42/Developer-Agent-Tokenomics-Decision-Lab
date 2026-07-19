#!/usr/bin/env bash
# HIDDEN acceptance gate (SPEC 2.6 sealed-hidden-test policy), parameterized by
# TASK_DIR. Loads sealed hidden tests from HIDDEN_TESTS_DIR (default
# $TASK_DIR/hidden, gitignored and human-held), records their version + content
# hash so every result can cite which sealed tests judged it, runs them against
# the subject working tree, then removes them.
#
# Exit codes: 0 hidden tests passed · 1 hidden tests failed · 2 no hidden tests.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness/task-tools/lib.sh
. "$SCRIPT_DIR/../lib.sh"

HIDDEN_DIR="${HIDDEN_TESTS_DIR:-$TASK_DIR/hidden}"

echo "== hidden gate ($(task_field task_id)) =="
echo "  source: $HIDDEN_DIR"

mapfile -t hidden_files < <(
  find "$HIDDEN_DIR" -type f \( -name '*.test.ts' -o -name '*.spec.ts' \) 2>/dev/null | sort
)

if [ "${#hidden_files[@]}" -eq 0 ]; then
  echo "  AWAITING_HUMAN — no sealed hidden tests found"
  echo "  A human must author them per $HIDDEN_DIR/README-FOR-HUMAN.md"
  if [ -n "${HIDDEN_REPORT:-}" ]; then
    printf '{"gate": "hidden", "status": "awaiting_human", "hash": null, "version": null}\n' \
      > "$HIDDEN_REPORT"
  fi
  exit 2
fi

HIDDEN_HASH="$(
  HIDDEN_DIR="$HIDDEN_DIR" pilot_python - "${hidden_files[@]}" <<'PY'
import hashlib, os, sys
base = os.environ["HIDDEN_DIR"]
h = hashlib.sha256()
for p in sorted(sys.argv[1:]):
    h.update(os.path.relpath(p, base).encode("utf-8")); h.update(b"\0")
    with open(p, "rb") as fh:
        h.update(fh.read())
    h.update(b"\0")
print("sha256:" + h.hexdigest())
PY
)"
HIDDEN_VERSION="$(cat "$HIDDEN_DIR/VERSION" 2>/dev/null || echo "unversioned")"
echo "  version: $HIDDEN_VERSION"
echo "  hash:    $HIDDEN_HASH"

# Keep Prisma client in step with the (patched) schema before running.
prisma_generate

injected=()
# Invoked only via `trap cleanup EXIT`, so shellcheck sees it as unreachable.
# SC2317 (shellcheck 0.9.x, what CI ships) and SC2329 (0.11.x, its successor)
# are the same false positive under different codes; disable both so this stays
# clean across runner shellcheck bumps.
# shellcheck disable=SC2317,SC2329
cleanup() { for f in "${injected[@]}"; do rm -f "$f"; done; }
trap cleanup EXIT

names=()
for src in "${hidden_files[@]}"; do
  base="$(basename "$src")"
  cp "$src" "$SUBJECT_DIR/src/tests/services/$base"
  injected+=("$SUBJECT_DIR/src/tests/services/$base")
  names+=("$base")
done

pattern="$(printf '%s|' "${names[@]}" | sed 's/|$//')"
run_jest --testPathPattern "$pattern" >/dev/null 2>&1
rc=$?

if [ -n "${HIDDEN_REPORT:-}" ]; then
  HIDDEN_HASH="$HIDDEN_HASH" HIDDEN_VERSION="$HIDDEN_VERSION" HIDDEN_RC="$rc" \
    pilot_python - "$HIDDEN_REPORT" <<'PY'
import json, os, sys
rc = int(os.environ["HIDDEN_RC"])
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump({
        "gate": "hidden",
        "status": "pass" if rc == 0 else "fail",
        "hash": os.environ["HIDDEN_HASH"],
        "version": os.environ["HIDDEN_VERSION"],
    }, fh, indent=2)
PY
fi

echo "== hidden gate: $([ "$rc" -eq 0 ] && echo PASS || echo FAIL) =="
exit "$rc"
