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

# Read a top-level scalar from task.yaml, falling back to a default when the key
# is absent (task_field aborts instead — keep that behaviour for required fields).
task_field_opt() { # key default
  DEFAULT="$2" pilot_python - "$TASK_YAML" "$1" <<'PY'
import os, sys
import yaml
with open(sys.argv[1], encoding="utf-8") as fh:
    data = yaml.safe_load(fh) or {}
val = data.get(sys.argv[2])
print(os.environ["DEFAULT"] if val is None else val)
PY
}

# Read one key of a top-level mapping in task.yaml (e.g. stack_cmds.baseline).
# Prints the empty string when the mapping or the key is absent.
task_map() { # map_key sub_key
  pilot_python - "$TASK_YAML" "$1" "$2" <<'PY'
import sys
import yaml
with open(sys.argv[1], encoding="utf-8") as fh:
    data = yaml.safe_load(fh) or {}
val = (data.get(sys.argv[2]) or {}).get(sys.argv[3])
print("" if val is None else val)
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

# ---------------------------------------------------------------------------
# Stack drivers (harness/task-tools/stacks/*.sh)
#
# The engine above is repo-agnostic; everything that depends on a TOOLCHAIN
# (install, test runner, build, coverage) is delegated to a stack driver named by
# task.yaml `stack:`. Default `node` = the original RealWorld engine, so the
# pre-existing tasks are unaffected. See stacks/README.md for the contract.
# ---------------------------------------------------------------------------

# Run a declared command string with the subject repo as cwd. The command comes
# from the task definition (a repo artifact, reviewed at CP-SCREEN-PREREG), never
# from a model or from run-time input.
subject_run() {
  [ -n "${1:-}" ] || return 0
  ( cd "$SUBJECT_DIR" && eval "$1" )
}

# One entry of task.yaml `stack_cmds:` (empty when unset).
stack_cmd() { task_map stack_cmds "$1"; }

TASK_STACK="$(task_field_opt stack node)"
case "$TASK_STACK" in
  node|python|none) ;;
  *) echo "  FAIL  unknown task.yaml stack: $TASK_STACK" >&2; exit 1 ;;
esac

# Default: every SPEC 2.8 check applies. A driver may override (see stacks/none.sh).
stack_na_checks() { :; }

# shellcheck source=/dev/null
. "$TASKTOOLS_DIR/stacks/$TASK_STACK.sh"

# Leakage scan shared by SPEC 2.8 check 8 and the public gate's P5: planted answer
# markers under the task's source root, or a stray *.patch anywhere in the
# participant tree. Installed dependency trees (node_modules, .venv…) are skipped —
# they are vendor bytes, not participant-visible material.
# Returns 0 when leakage IS found, so callers read `if leak_found; then ...`.
leak_found() {
  local src_root grep_excl=(--exclude-dir=.git) find_prune=() keep
  src_root="$SUBJECT_DIR/$(task_field_opt source_root src)"
  while IFS= read -r keep; do
    [ -n "$keep" ] || continue
    grep_excl+=(--exclude-dir="$keep")
    find_prune+=(-path "$SUBJECT_DIR/$keep" -prune -o)
  done < <(stack_clean_keep)
  grep -rIl "${grep_excl[@]}" -e 'CANONICAL SOLUTION' -e 'PILOT-ANSWER' \
    "$src_root" >/dev/null 2>&1 && return 0
  find "$SUBJECT_DIR" "${find_prune[@]+"${find_prune[@]}"}" -name '*.patch' -print \
    2>/dev/null | grep -q . && return 0
  return 1
}
