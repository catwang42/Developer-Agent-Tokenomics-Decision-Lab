#!/usr/bin/env bash
# Shared helpers for the pilot-task scripts (sourced, not executed).
# No side effects on source beyond defining functions and read-only paths.

# Directory of this library == tasks/pilot-realworld/
PILOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Repository root == two levels up.
REPO_ROOT="$(cd "$PILOT_DIR/../.." && pwd)"

# Where the subject repo is cloned. Gitignored; overridable for CI/containers.
WORKDIR="${PILOT_WORKDIR:-$PILOT_DIR/.work}"
SUBJECT_DIR="$WORKDIR/repo"

MANIFEST="$REPO_ROOT/manifest/delivery-manifest.yaml"
TASK_YAML="$PILOT_DIR/task.yaml"
VENV_PY="$REPO_ROOT/.venv/bin/python"

# Prefer the project venv python; fall back to python3 (containers without .venv).
pilot_python() {
  if [ -x "$VENV_PY" ]; then
    "$VENV_PY" "$@"
  else
    python3 "$@"
  fi
}

# Read a scalar from manifest pilot_task by key (e.g. pinned_commit, repo).
manifest_pilot() {
  local key="$1"
  pilot_python - "$MANIFEST" "$key" <<'PY'
import sys
try:
    import yaml
except ImportError:
    sys.exit("PyYAML unavailable; cannot read manifest")
path, key = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    data = yaml.safe_load(fh)
pilot = (data or {}).get("pilot_task") or {}
val = pilot.get(key)
if val is None:
    sys.exit(f"manifest pilot_task.{key} is missing")
print(val)
PY
}

# Read a top-level scalar from task.yaml (e.g. target_path, baseline_test_pattern).
task_field() {
  local key="$1"
  pilot_python - "$TASK_YAML" "$key" <<'PY'
import sys
try:
    import yaml
except ImportError:
    sys.exit("PyYAML unavailable; cannot read task.yaml")
path, key = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    data = yaml.safe_load(fh)
val = (data or {}).get(key)
if val is None:
    sys.exit(f"task.yaml {key} is missing")
print(val)
PY
}

# jest via the subject repo's own toolchain, hermetic (no nx daemon / cloud).
run_jest() {
  ( cd "$SUBJECT_DIR" \
      && NX_DAEMON=false NX_CLOUD_ACCESS_TOKEN='' CI=true \
         npx jest --config jest.config.ts "$@" )
}
