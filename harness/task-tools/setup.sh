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
clean_excludes=()
while IFS= read -r keep; do
  [ -n "$keep" ] && clean_excludes+=(-e "$keep")
done < <(stack_clean_keep)
git -C "$SUBJECT_DIR" clean -ffd "${clean_excludes[@]+"${clean_excludes[@]}"}" >/dev/null

HEAD_SHA="$(git -C "$SUBJECT_DIR" rev-parse HEAD)"
if [ "$HEAD_SHA" != "$PIN" ]; then
  echo "  FAIL  checked-out SHA $HEAD_SHA != manifest pin $PIN" >&2
  exit 1
fi
echo "  ok    SHA verified: $HEAD_SHA"

if ! stack_installed_ok || [ "${1:-}" = "--reinstall" ]; then
  echo "  -> installing deps ($TASK_STACK stack)"
  stack_install
else
  echo "  ok    deps present (skip reinstall; use --reinstall to force)"
fi

stack_post_patch

echo "  ok    setup complete"
