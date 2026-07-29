#!/usr/bin/env bash
# Shared helpers for the parameterized task harness (sourced, not executed).
#
# One engine, many tasks: every task-specific value is read from $TASK_DIR/task.yaml
# and the delivery manifest. Point TASK_DIR at a task directory (e.g.
# tasks/pilot-realworld or tasks/suite/W4-complex-bugfix) and the same
# setup/reset/validate/gate scripts drive it. No side effects on source beyond
# defining functions and read-only paths.

# Directory of this library == harness/task-tools/ ; repo root == two up.
TASKTOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$TASKTOOLS_DIR/../.." && pwd)"

# The task under test. Required.
: "${TASK_DIR:?TASK_DIR must point at a task directory (e.g. tasks/pilot-realworld)}"
TASK_DIR="$(cd "$TASK_DIR" && pwd)"
TASK_YAML="$TASK_DIR/task.yaml"

# Subject repo clone (gitignored; overridable for CI/containers).
WORKDIR="${TASK_WORKDIR:-$TASK_DIR/.work}"
SUBJECT_DIR="$WORKDIR/repo"

MANIFEST="$REPO_ROOT/manifest/delivery-manifest.yaml"
VENV_PY="$REPO_ROOT/.venv/bin/python"

# Prefer the project venv python; fall back to python3 (containers without .venv).
pilot_python() {
  if [ -x "$VENV_PY" ]; then
    "$VENV_PY" "$@"
  else
    python3 "$@"
  fi
}

# Read a top-level scalar from task.yaml (e.g. target_path, canonical_patch).
task_field() {
  pilot_python - "$TASK_YAML" "$1" <<'PY'
import sys
try:
    import yaml
except ImportError:
    sys.exit("PyYAML unavailable; cannot read task.yaml")
with open(sys.argv[1], encoding="utf-8") as fh:
    data = yaml.safe_load(fh)
val = (data or {}).get(sys.argv[2])
if val is None:
    sys.exit(f"task.yaml {sys.argv[2]} is missing")
print(val)
PY
}

# Read a top-level list from task.yaml, one item per line (e.g. target_paths).
task_list() {
  pilot_python - "$TASK_YAML" "$1" <<'PY'
import sys
import yaml
with open(sys.argv[1], encoding="utf-8") as fh:
    data = yaml.safe_load(fh)
for item in (data or {}).get(sys.argv[2]) or []:
    print(item)
PY
}

# Read a scalar from the manifest entry named by task.yaml's manifest_key
# (e.g. pilot_task.pinned_commit).
manifest_task() {
  local mkey
  mkey="$(task_field manifest_key)"
  MKEY="$mkey" pilot_python - "$MANIFEST" "$1" <<'PY'
import os, sys
import yaml
with open(sys.argv[1], encoding="utf-8") as fh:
    data = yaml.safe_load(fh)
entry = (data or {}).get(os.environ["MKEY"]) or {}
val = entry.get(sys.argv[2])
if val is None:
    sys.exit(f"manifest {os.environ['MKEY']}.{sys.argv[2]} is missing")
print(val)
PY
}

# Print coverage_target.files[].path, one per line (test-generation gate T3). Empty
# output if the task declares no coverage_target (non-test-generation tasks).
coverage_files() {
  pilot_python - "$TASK_YAML" <<'PY'
import sys
import yaml
with open(sys.argv[1], encoding="utf-8") as fh:
    data = yaml.safe_load(fh) or {}
for f in ((data.get("coverage_target") or {}).get("files") or []):
    print(f["path"])
PY
}

# jest via the subject repo's own toolchain, hermetic (no nx daemon / cloud).
run_jest() {
  ( cd "$SUBJECT_DIR" \
      && NX_DAEMON=false NX_CLOUD_ACCESS_TOKEN='' CI=true \
         npx jest --config jest.config.ts "$@" )
}

# Ensure the Prisma client matches the current schema (canonical solutions may
# change schema.prisma). Idempotent and fast.
prisma_generate() {
  ( cd "$SUBJECT_DIR" && npx prisma generate >/dev/null 2>&1 )
}
