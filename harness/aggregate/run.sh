#!/usr/bin/env bash
# Thin wrapper for the non-comparative aggregation view. Runs from the repo root so
# the `harness` package imports; prefers the project venv python.
#
#   bash harness/aggregate/run.sh results/feasibility
#   bash harness/aggregate/run.sh results/feasibility --json-out /tmp/agg.json
#
# Output is INTERNAL / NON-COMPARATIVE: descriptive per-cell stats only, no vendor
# ranking (CLAUDE.md 1.2 / rule 4).
set -euo pipefail

AGG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$AGG_DIR/../.." && pwd)"
cd "$REPO_ROOT"

VENV_PY="$REPO_ROOT/.venv/bin/python"
if [ -x "$VENV_PY" ]; then
  PY="$VENV_PY"
else
  PY="python3"
fi

exec "$PY" -m harness.aggregate "$@"
