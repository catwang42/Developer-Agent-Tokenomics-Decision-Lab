#!/usr/bin/env bash
# regrade-v2 sweep — re-grade the screening evidence offline, at zero model spend.
#
# WHY THE WHOLE SCREENING SET AND NOT A SHORTLIST. Every gate image on this host
# carries a bare `:<pin12>` tag: the content digest that makes a gate-logic change
# invalidate the cache landed in PR #27, after every screening run was graded. So
# "cells whose gate image predates the fixes" is not a subset of the screening
# data — it is all of it, and the sweep says so by re-grading all of it rather
# than by picking the cells where a flip was expected.
#
# The earlier datasets (feasibility*, pilot-reference, revalidation, smoke*, the
# aborted gatefix batch) are deliberately NOT swept: they are documented by their
# own authoritative reports and none of them feeds the final consolidated table.
# That exclusion is a scoping decision, stated here so it is not mistaken for
# coverage.
#
# The sealed sets are gitignored and human-held, so HIDDEN_TESTS_DIR points at the
# tree that holds them. They are mounted read-only into the gate container and
# hashed by the gate itself; this script never reads them.
#
# Usage: tools/regrade-v2-sweep.sh [--dry-run]
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PY:-$REPO/.venv/bin/python}"
SEALED_TREE="${SEALED_TREE:-$HOME/Developer-Agent-Tokenomics-Decision-Lab}"
DRY=()
[ "${1:-}" = "--dry-run" ] && DRY=(--dry-run)

# task_id -> task dir. Only tasks with a sealed set can be graded at all.
#
# The pilot task is here because screening-batch1 contains 15 of its runs and they
# were graded by the same pre-#27 images as everything else. Its sealed set lives
# outside tasks/suite/ (tasks/pilot-realworld/hidden), which is the only reason it
# was missed on the first pass — not a scoping decision.
TASKS=(
  "pilot-realworld-draft-articles:tasks/pilot-realworld"
  "w1-realworld-mapper-tests:tasks/suite/W1-test-generation"
  "w1b-zarr-block-mask-properties:tasks/suite/W1b-zarr-block-mask-properties"
  "w3-sqlfluff-segment-method-migration:tasks/suite/W3-migration"
  "w4-realworld-missing-user-id:tasks/suite/W4-complex-bugfix"
  "w4b-zarr-consolidated-order:tasks/suite/W4b-zarr-consolidated-order"
  "w6-hono-router-review:tasks/suite/W6-pr-review"
)
DATASETS=(screening-batch1 screening-batch1-makeup screening-batch1-makeup-w6)

echo "== regrade-v2 sweep =="
echo "   harness:    $(git -C "$REPO" rev-parse --short HEAD) ($(git -C "$REPO" rev-parse --abbrev-ref HEAD))"
echo "   sealed:     $SEALED_TREE/<task>/hidden (mounted ro; never read by the harness)"
echo "   datasets:   ${DATASETS[*]}"
echo "   started:    $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

rc_total=0
for ds in "${DATASETS[@]}"; do
  [ -d "$REPO/results/$ds" ] || { echo "-- $ds: absent, skipped"; continue; }
  for entry in "${TASKS[@]}"; do
    task_id="${entry%%:*}"; task_dir="${entry#*:}"
    compgen -G "$REPO/results/$ds/${task_id}__*" >/dev/null || continue
    sealed="$SEALED_TREE/$task_dir/hidden"
    if [ ! -d "$sealed" ]; then
      echo "-- $ds / $task_id: SKIPPED — no sealed set at $sealed"
      rc_total=1
      continue
    fi
    echo "-- $ds / $task_id"
    HIDDEN_TESTS_DIR="$sealed" "$PY" -m harness.runner.regrade \
      --generation 2 --results "$REPO/results/$ds" --task "$REPO/$task_dir" \
      "${DRY[@]}" 2>&1 | sed 's/^/   /'
    rc=${PIPESTATUS[0]}
    [ "$rc" -eq 0 ] || { echo "   !! regrade exited $rc"; rc_total=1; }
    echo
  done
done

echo "   finished:   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
exit "$rc_total"
