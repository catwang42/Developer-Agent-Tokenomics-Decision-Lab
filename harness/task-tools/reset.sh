#!/usr/bin/env bash
# Deterministic reset (SPEC 2.8, check 10): restore the subject repo working tree
# to the pinned commit, discarding any agent/gate modifications, and print the
# canonical tree hash so idempotency can be proven (two runs -> identical hash).
# node_modules and the generated Prisma client are preserved (gitignored and
# reproducible). Parameterized by TASK_DIR.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness/task-tools/lib.sh
. "$SCRIPT_DIR/lib.sh"

if [ ! -d "$SUBJECT_DIR/.git" ]; then
  echo "  FAIL  subject repo not set up; run setup.sh first" >&2
  exit 1
fi

PIN="$(manifest_task pinned_commit)"

git -C "$SUBJECT_DIR" -c advice.detachedHead=false checkout --quiet --force "$PIN"
git -C "$SUBJECT_DIR" clean -ffd -e node_modules >/dev/null

git -C "$SUBJECT_DIR" add -A
TREE_HASH="$(git -C "$SUBJECT_DIR" write-tree)"
git -C "$SUBJECT_DIR" reset -q

STATUS="$(git -C "$SUBJECT_DIR" status --porcelain)"
if [ -n "$STATUS" ]; then
  echo "  FAIL  working tree not clean after reset:" >&2
  echo "$STATUS" >&2
  exit 1
fi

echo "reset_ok pin=$PIN tree=$TREE_HASH"
