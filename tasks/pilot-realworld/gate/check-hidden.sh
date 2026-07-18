#!/usr/bin/env bash
# HIDDEN acceptance gate (SPEC 2.6 sealed-hidden-test policy) for the pilot task.
#
# Loads sealed hidden tests from HIDDEN_TESTS_DIR (default tasks/hidden/, which
# is gitignored and human-held), records their version + content hash so every
# result can cite exactly which sealed tests judged it, runs them against the
# subject working tree, then removes them so they never persist in the tree.
#
# The hidden tests themselves are authored and held by a human (see
# tasks/hidden/README-FOR-HUMAN.md). Until they exist this gate reports
# AWAITING_HUMAN and exits 2 — distinct from pass (0) and fail (1) — so the
# 10-point validator can honestly show which checks await the human.
#
# Exit codes: 0 hidden tests passed · 1 hidden tests failed · 2 no hidden tests.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tasks/pilot-realworld/lib.sh
. "$SCRIPT_DIR/../lib.sh"

HIDDEN_DIR="${HIDDEN_TESTS_DIR:-$REPO_ROOT/tasks/hidden}"

echo "== hidden gate =="
echo "  source: $HIDDEN_DIR"

# Collect sealed test files (*.test.ts / *.spec.ts), sorted for a stable hash.
mapfile -t hidden_files < <(
  find "$HIDDEN_DIR" -type f \( -name '*.test.ts' -o -name '*.spec.ts' \) 2>/dev/null | sort
)

if [ "${#hidden_files[@]}" -eq 0 ]; then
  echo "  AWAITING_HUMAN — no sealed hidden tests found"
  echo "  A human must author them per tasks/hidden/README-FOR-HUMAN.md"
  if [ -n "${HIDDEN_REPORT:-}" ]; then
    printf '{"gate": "hidden", "status": "awaiting_human", "hash": null, "version": null}\n' \
      > "$HIDDEN_REPORT"
  fi
  exit 2
fi

# Version + content hash over (relative path + bytes) of each sealed file.
HIDDEN_HASH="$(
  HIDDEN_DIR="$HIDDEN_DIR" pilot_python - "${hidden_files[@]}" <<'PY'
import hashlib, os, sys
base = os.environ["HIDDEN_DIR"]
h = hashlib.sha256()
for p in sorted(sys.argv[1:]):
    rel = os.path.relpath(p, base)
    h.update(rel.encode("utf-8"))
    h.update(b"\0")
    with open(p, "rb") as fh:
        h.update(fh.read())
    h.update(b"\0")
print("sha256:" + h.hexdigest())
PY
)"
HIDDEN_VERSION="$(cat "$HIDDEN_DIR/VERSION" 2>/dev/null || echo "unversioned")"
echo "  version: $HIDDEN_VERSION"
echo "  hash:    $HIDDEN_HASH"

# Inject sealed tests, run, then always remove them from the tree.
injected=()
cleanup() { for f in "${injected[@]}"; do rm -f "$f"; done; }
trap cleanup EXIT

names=()
for src in "${hidden_files[@]}"; do
  base="$(basename "$src")"
  dst="$SUBJECT_DIR/src/tests/services/$base"
  cp "$src" "$dst"
  injected+=("$dst")
  names+=("$base")
done

# Run exactly the injected sealed files (basenames OR-joined into one pattern).
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
