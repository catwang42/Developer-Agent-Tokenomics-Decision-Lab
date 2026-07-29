#!/usr/bin/env bash
# Thin wrapper for the warm-series driver (cache-protocol.md rule 2, redesigned).
# Stages the subject tree ONCE per series, runs rep 1 cold + reps 2..n warm/resumed
# in one process (same staged /var/tmp path, tree reset between reps, byte-identical
# prompt), and cleans up once. Runs from the repo root so `harness` imports and
# prefers the project venv python. All arguments pass through to warm_series.py.
#
#   bash harness/runner/run-warm-series.sh --task tasks/pilot-realworld --config C1 \
#     --reps 3 --dry-run \
#     --manifest tests/fixtures/manifest-SYNTHETIC.yaml --out-root /tmp/warm-dry
#
# A live series bills a real account: it requires a CP-SPEND-approved invocation
# (LAB_ALLOW_SPEND=1) and honours --spend-cap-usd (halts with exit 3 at the cap).
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

exec "$PY" -m harness.runner.warm_series "$@"
