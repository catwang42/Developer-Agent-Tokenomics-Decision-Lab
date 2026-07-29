#!/usr/bin/env bash
# HIDDEN acceptance gate (SPEC 2.6 sealed-hidden-test policy), parameterized by
# TASK_DIR. Loads sealed, human-held hidden artifacts from HIDDEN_TESTS_DIR
# (default $TASK_DIR/hidden, gitignored), records their version + a content hash
# so every result can cite which sealed tests judged it, applies them against the
# subject working tree, then leaves the tree clean.
#
# Two shapes, dispatched by task.yaml `gate_type` (default `solution`):
#
#   solution        — sealed *.test.ts / *.spec.ts are injected under
#                     src/tests/services and run with jest.
#
#   test_generation — the sealed artifact is an EXECUTABLE runner (convention:
#                     check.sh) that mutation-tests the AGENT's produced tests. We
#                     only DISCOVER it (we never read/print the mutant set — it is
#                     human-held), invoke it with SUBJECT_DIR exported, surface its
#                     stderr (per-mutant caught / NOT-caught) into the gate log, and
#                     honor its exit contract verbatim.
#
# Exit codes (both shapes): 0 accept · 1 reject · 2 hidden unavailable / awaiting human.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness/task-tools/lib.sh
. "$SCRIPT_DIR/../lib.sh"

HIDDEN_DIR="${HIDDEN_TESTS_DIR:-$TASK_DIR/hidden}"
GATE_TYPE="$(task_field gate_type 2>/dev/null || echo solution)"

echo "== hidden gate ($(task_field task_id)) [$GATE_TYPE] =="
echo "  source: $HIDDEN_DIR"

# Write the gate-hidden.json report — shape shared by both gate types and consumed
# unchanged by validate.sh. Args: status hash version ("null" -> JSON null).
write_hidden_report() {
  [ -n "${HIDDEN_REPORT:-}" ] || return 0
  HR_STATUS="$1" HR_HASH="$2" HR_VERSION="$3" pilot_python - "$HIDDEN_REPORT" <<'PY'
import json, os, sys
def norm(v): return None if v in ("", "null") else v
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump({
        "gate": "hidden",
        "status": os.environ["HR_STATUS"],
        "hash": norm(os.environ["HR_HASH"]),
        "version": norm(os.environ["HR_VERSION"]),
    }, fh, indent=2)
PY
}

# Deterministic SHA-256 over the given sealed files (relpath + bytes, sorted).
# Reads bytes only to hash them; never prints file contents.
hidden_content_hash() {
  HIDDEN_DIR="$HIDDEN_DIR" pilot_python - "$@" <<'PY'
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
}

# ---------------------------------------------------------------------------
# test_generation — executable sealed runner (mutation-catch). See header.
# ---------------------------------------------------------------------------
if [ "$GATE_TYPE" = "test_generation" ]; then
  ENTRYPOINT="$HIDDEN_DIR/check.sh"    # convention; human-authored, human-held
  if [ ! -x "$ENTRYPOINT" ]; then
    echo "  AWAITING_HUMAN — no executable sealed runner at $HIDDEN_DIR/check.sh"
    echo "  A human must author it per $HIDDEN_DIR/README-FOR-HUMAN.md"
    write_hidden_report awaiting_human null null
    exit 2
  fi

  # Fingerprint the whole sealed set (all files in HIDDEN_DIR), and read its
  # declared version — exactly as the jest path records hash + version.
  mapfile -t sealed_files < <(find "$HIDDEN_DIR" -type f 2>/dev/null | sort)
  HIDDEN_HASH="$(hidden_content_hash "${sealed_files[@]}")"
  HIDDEN_VERSION="$(cat "$HIDDEN_DIR/VERSION" 2>/dev/null || echo "unversioned")"
  echo "  version: $HIDDEN_VERSION"
  echo "  hash:    $HIDDEN_HASH"
  echo "  runner:  check.sh (sealed; contents never shown)"

  # Invoke the sealed runner with the subject repo exported. Discard its stdout
  # (test-runner noise); capture stderr — the per-mutant caught / NOT-caught
  # lines — and surface it into the gate log, prefixed. The runner owns what it
  # emits; the harness never reads the mutant fixtures itself.
  runner_err="$(mktemp)"
  SUBJECT_DIR="$SUBJECT_DIR" bash "$ENTRYPOINT" >/dev/null 2>"$runner_err"
  rc=$?
  if [ -s "$runner_err" ]; then
    echo "  -- sealed runner (stderr) --"
    sed 's/^/  | /' "$runner_err"
  fi
  rm -f "$runner_err"

  case "$rc" in
    0) status=pass ;;
    2) status=unavailable ;;
    *) rc=1; status=fail ;;
  esac
  write_hidden_report "$status" "$HIDDEN_HASH" "$HIDDEN_VERSION"
  case "$rc" in
    0) echo "== hidden gate: PASS ==" ;;
    2) echo "== hidden gate: UNAVAILABLE ==" ;;
    *) echo "== hidden gate: FAIL ==" ;;
  esac
  exit "$rc"
fi

# ---------------------------------------------------------------------------
# solution (default) — sealed jest tests injected under src/tests/services.
# ---------------------------------------------------------------------------
mapfile -t hidden_files < <(
  find "$HIDDEN_DIR" -type f \( -name '*.test.ts' -o -name '*.spec.ts' \) 2>/dev/null | sort
)

if [ "${#hidden_files[@]}" -eq 0 ]; then
  echo "  AWAITING_HUMAN — no sealed hidden tests found"
  echo "  A human must author them per $HIDDEN_DIR/README-FOR-HUMAN.md"
  write_hidden_report awaiting_human null null
  exit 2
fi

HIDDEN_HASH="$(hidden_content_hash "${hidden_files[@]}")"
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

write_hidden_report "$([ "$rc" -eq 0 ] && echo pass || echo fail)" "$HIDDEN_HASH" "$HIDDEN_VERSION"

echo "== hidden gate: $([ "$rc" -eq 0 ] && echo PASS || echo FAIL) =="
exit "$rc"
