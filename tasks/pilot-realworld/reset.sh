#!/usr/bin/env bash
# Deterministic reset (SPEC 2.8, check 10): restore the subject repo working
# tree to the pinned commit, discarding any agent/gate modifications. Prints the
# canonical tree hash of the restored working tree so idempotency can be proven
# (two runs -> identical hash). node_modules and the generated Prisma client are
# preserved (they are gitignored and reproducible), so the hash covers exactly
# the tracked source the agent could change.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tasks/pilot-realworld/lib.sh
. "$SCRIPT_DIR/lib.sh"

if [ ! -d "$SUBJECT_DIR/.git" ]; then
  echo "  FAIL  subject repo not set up; run setup.sh first" >&2
  exit 1
fi

PIN="$(manifest_pilot pinned_commit)"

git -C "$SUBJECT_DIR" -c advice.detachedHead=false checkout --quiet --force "$PIN"
# Remove untracked files (e.g. an injected repro test) but keep node_modules.
git -C "$SUBJECT_DIR" clean -ffd -e node_modules >/dev/null

# Canonical tree hash: stage tracked content and ask git for the tree object.
# After a forced checkout + clean the working tree equals the pinned tree, so
# write-tree yields the pinned commit's tree SHA on every run.
git -C "$SUBJECT_DIR" add -A
TREE_HASH="$(git -C "$SUBJECT_DIR" write-tree)"
# Leave the index matching HEAD so the repo is left pristine, not "staged".
git -C "$SUBJECT_DIR" reset -q

STATUS="$(git -C "$SUBJECT_DIR" status --porcelain)"
if [ -n "$STATUS" ]; then
  echo "  FAIL  working tree not clean after reset:" >&2
  echo "$STATUS" >&2
  exit 1
fi

echo "reset_ok pin=$PIN tree=$TREE_HASH"
