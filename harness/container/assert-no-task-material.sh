#!/usr/bin/env bash
# Assert that NO task material is present in the agent image (SPEC §6 item 1).
#
# Task material = anything that hands the agent the answer or the grader:
#   canonical/   the reference solution patch
#   hidden/      sealed hidden tests (human-held; never in any image)
#   task.yaml    the task contract — target paths, gate type, write scope
#
# Run at BUILD time (so a bad image never exists) and baked in so it can be re-run
# against a running container or a planted tree. Scans the whole filesystem, not a
# declared subtree: the point is to catch material that arrived somewhere nobody
# expected — `.dockerignore` has silently failed this before (the 2026-07-19 W1
# image shipped canonical/mapper-tests.patch, fixed later by FIX D). A declared-path
# check would have passed on that image.
#
#   assert-no-task-material.sh [ROOT]     # default ROOT=/
#
# Exit 0 = clean. Exit 1 = task material found (paths listed on stderr).
set -uo pipefail

ROOT="${1:-/}"

if [ ! -e "$ROOT" ]; then
  echo "assert-no-task-material: root '$ROOT' does not exist" >&2
  exit 2
fi

# -xdev keeps the scan on one filesystem (mounted volumes are checked separately by
# the caller that mounts them); the pruned paths are kernel pseudo-filesystems.
found="$(find "$ROOT" -xdev \
  \( -path /proc -o -path /sys -o -path /dev -o -path /run \) -prune -o \
  \( -name canonical -o -name hidden -o -name task.yaml \) -print 2>/dev/null | sort)"

if [ -n "$found" ]; then
  {
    echo "assert-no-task-material: FAIL — task material present under '$ROOT':"
    while IFS= read -r hit; do echo "  $hit"; done <<< "$found"
    echo
    echo "The agent image must contain no canonical/ (reference solution), no hidden/"
    echo "(sealed tests) and no task.yaml (the grading contract). Check .dockerignore"
    echo "and the agent stage's strip step in harness/container/Dockerfile.subject."
  } >&2
  exit 1
fi

echo "assert-no-task-material: ok — no canonical/, hidden/ or task.yaml under '$ROOT'"
