#!/usr/bin/env bash
# Thin wrapper for the controlled runner. Runs from the repo root so the
# `harness` package imports, and prefers the project venv python (falls back to
# python3 in containers without .venv). All arguments pass through to run.py.
#
#   bash harness/runner/run.sh --task tasks/pilot-realworld --config P0 --dry-run \
#     --manifest tests/fixtures/manifest-SYNTHETIC.yaml --out-root /tmp/dry
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
