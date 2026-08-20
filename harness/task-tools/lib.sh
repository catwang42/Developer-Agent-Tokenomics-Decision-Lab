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

# The delivery manifest holds the volatile pins (repo URL, pinned commit). It is
# overridable for the same reason TASK_WORKDIR and HIDDEN_TESTS_DIR are: so the
# harness can be driven end-to-end against a throwaway task in a test, without a
# clone and without adding test-only entries to the real manifest. Production
# callers never set it.
MANIFEST="${DELIVERY_MANIFEST:-$REPO_ROOT/manifest/delivery-manifest.yaml}"
VENV_PY="$REPO_ROOT/.venv/bin/python"

# --- git must be able to READ the subject tree --------------------------------
# THE screening-batch-1 instrument defect (results/screening-batch1/batch1.log,
# "W1 HIDDEN-GATE REJECTS ARE AN INSTRUMENT ERROR"). Under container isolation the
# subject tree is a Docker volume seeded from the AGENT image, so its files are
# owned by the agent's uid, while the gate container runs as root. git's
# safe.directory guard refuses a repo it considers dubiously owned:
#
#     fatal: detected dubious ownership in repository at '/lab/.../.work/repo'
#
# Every git call then fails. The failure is silent in the worst possible way: a
# discovery step like "list the agent's new test files" returns EMPTY, which reads
# exactly like "the agent wrote no tests" — so all 16 W1 cells were graded
# `rejected` on a tree the grader could not see. The split in the batch-1 data is
# the signature: gate_type `solution` (no git discovery) 32/32 hidden-pass,
# `test_generation` (git discovery) 15/15 hidden-fail.
#
# We trust THIS path only, through env rather than the operator's gitconfig, and we
# export it so a sealed runner invoked as a child inherits the trust — the sealed
# runner is human-held and must not have to know about our uid arrangement. Callers
# check the return value: git still unable to read the tree means NOTHING can be
# graded, and each gate says so loudly instead of scoring an invisible tree.
#
# Returns 0 if git can read $SUBJECT_DIR (possibly after trusting it), else 1.
git_trust_subject() {
  if git -C "$SUBJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    return 0
  fi
  export GIT_CONFIG_COUNT=1
  export GIT_CONFIG_KEY_0=safe.directory
  export GIT_CONFIG_VALUE_0="$SUBJECT_DIR"
  git -C "$SUBJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1
}

# Why git refuses the subject tree, one line, for a gate's failure message.
git_subject_error() {
  git -C "$SUBJECT_DIR" rev-parse --is-inside-work-tree 2>&1 | head -1
}

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
