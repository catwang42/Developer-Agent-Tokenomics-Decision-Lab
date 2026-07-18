#!/usr/bin/env bash
# Task setup (SPEC 2.8): clone the subject repo at the pinned commit, verify the
# SHA against the delivery manifest, install deps from the lockfile, and generate
# the Prisma client. Parameterized by TASK_DIR. Clones into a gitignored work
# dir; nothing here is committed to this repo.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness/task-tools/lib.sh
. "$SCRIPT_DIR/lib.sh"

PIN="$(manifest_task pinned_commit)"
REPO_URL="$(manifest_task repo)"

echo "== task setup ($(task_field task_id)) =="
echo "  repo:   $REPO_URL"
echo "  commit: $PIN"
echo "  target: $SUBJECT_DIR"

mkdir -p "$WORKDIR"

if [ ! -d "$SUBJECT_DIR/.git" ]; then
  echo "  -> cloning"
  git clone --quiet "$REPO_URL" "$SUBJECT_DIR"
fi

if ! git -C "$SUBJECT_DIR" cat-file -e "${PIN}^{commit}" 2>/dev/null; then
  echo "  -> fetching pinned commit"
  git -C "$SUBJECT_DIR" fetch --quiet origin "$PIN" || git -C "$SUBJECT_DIR" fetch --quiet --all
fi

git -C "$SUBJECT_DIR" -c advice.detachedHead=false checkout --quiet --force "$PIN"
git -C "$SUBJECT_DIR" clean -ffd -e node_modules >/dev/null

HEAD_SHA="$(git -C "$SUBJECT_DIR" rev-parse HEAD)"
if [ "$HEAD_SHA" != "$PIN" ]; then
  echo "  FAIL  checked-out SHA $HEAD_SHA != manifest pin $PIN" >&2
  exit 1
fi
echo "  ok    SHA verified: $HEAD_SHA"

if [ ! -d "$SUBJECT_DIR/node_modules" ] || [ "${1:-}" = "--reinstall" ]; then
  echo "  -> npm ci (clean install from lockfile)"
  ( cd "$SUBJECT_DIR" && npm ci --no-audit --no-fund )
else
  echo "  ok    node_modules present (skip reinstall; use --reinstall to force)"
fi

echo "  -> prisma generate"
prisma_generate

echo "  ok    setup complete"
