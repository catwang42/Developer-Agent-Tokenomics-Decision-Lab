#!/usr/bin/env bash
# Thin wrapper for the controlled runner. Runs from the repo root so the
# `harness` package imports, and prefers the project venv python (falls back to
# python3 in containers without .venv). All arguments pass through to run.py.
#
#   bash harness/runner/run.sh --task tasks/pilot-realworld --config P0 --dry-run \
#     --cache-state cold \
#     --manifest tests/fixtures/manifest-SYNTHETIC.yaml --out-root /tmp/dry
#
# --cache-state {cold|warm-series} is REQUIRED (cache-protocol.md rule 4).
# --spend-cap-usd N caps cumulative batch spend (default 60; halts with exit 3
#   before starting a run once completed sibling runs' realized cost reaches N).
set -euo pipefail

RUNNER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$RUNNER_DIR/../.." && pwd)"
cd "$REPO_ROOT"

VENV_PY="$REPO_ROOT/.venv/bin/python"
if [ -x "$VENV_PY" ]; then
  PY="$VENV_PY"
else
  PY="python3"
fi

exec "$PY" -m harness.runner.run "$@"
