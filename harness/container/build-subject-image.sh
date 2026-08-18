#!/usr/bin/env bash
# Build a per-task subject image (deps baked in at build time).
#
#   bash harness/container/build-subject-image.sh tasks/suite/W1-test-generation [gate|agent]
#
#   gate  (default)  the deterministic grader: task material intact, runs --network=none
#   agent            the agent leg: product CLIs baked at pinned versions, NO task
#                    material in any layer (build-asserted), runs on the egress
#                    allowlist network
#
# Prints the resulting image tag on success. Build-time network is used to clone the
# subject repo, `npm ci` and install the product CLIs; this is tooling setup, NEVER
# model spend (CLAUDE.md rule 5). The graded run is then fully offline.
#
# For the agent image the CLI version pins come from manifest subject_isolation
# .agent_leg, and the Product-B binary is staged from this host by stage-agy.sh
# (it has no verifiable public download URL — see that script). The build ASSERTS
# both pins, so a mismatch fails loudly rather than being stamped into telemetry.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DOCKERFILE="$SCRIPT_DIR/Dockerfile.subject"

TASK_DIR_ARG="${1:?usage: build-subject-image.sh <task_dir> [gate|agent]}"
ROLE="${2:-gate}"
case "$ROLE" in
  gate)  TARGET="subject-gate";  TAG_FN="subject_image_tag" ;;
  agent) TARGET="subject-agent"; TAG_FN="agent_image_tag" ;;
  *) echo "build-subject-image: role must be 'gate' or 'agent' (got '$ROLE')" >&2; exit 2 ;;
esac
# Normalise to an absolute path (accept either a repo-relative or absolute arg),
# then to a repo-root-relative path (the docker build context is REPO_ROOT).
if [ -d "$REPO_ROOT/$TASK_DIR_ARG" ]; then
  TASK_DIR_ABS="$(cd "$REPO_ROOT/$TASK_DIR_ARG" && pwd)"
else
  TASK_DIR_ABS="$(cd "$TASK_DIR_ARG" && pwd)"
fi
TASK_DIR_REL="${TASK_DIR_ABS#"$REPO_ROOT"/}"

VENV_PY="$REPO_ROOT/.venv/bin/python"
PY="python3"; [ -x "$VENV_PY" ] && PY="$VENV_PY"

# Compute the deterministic tag from task_id + pinned_commit, reusing the SAME
# slug/pin logic the runner uses (harness.container.subject_image_tag).
TAG="$(cd "$REPO_ROOT" && TASK_DIR="$TASK_DIR_ABS" "$PY" - "$TASK_DIR_ABS" "$TAG_FN" <<'PY'
import os
import sys

import yaml

import harness.container as container

task_dir, tag_fn = sys.argv[1], sys.argv[2]
with open(os.path.join(task_dir, "task.yaml"), encoding="utf-8") as fh:
    ty = yaml.safe_load(fh) or {}
task_id = ty["task_id"]
mkey = ty["manifest_key"]
repo_root = os.getcwd()
with open(os.path.join(repo_root, "manifest", "delivery-manifest.yaml"), encoding="utf-8") as fh:
    manifest = yaml.safe_load(fh) or {}
pin = (manifest.get(mkey) or {})["pinned_commit"]
print(getattr(container, tag_fn)(task_id, pin))
PY
)"

BUILD_ARGS=(--build-arg "BAKE_TASK_DIR=$TASK_DIR_REL")

if [ "$ROLE" = "agent" ]; then
  # Stage the Product-B binary from this host if it is not already vendored, so the
  # resolver below sees it. (The runner's auto-build never stages: a batch that
  # silently copies a host binary mid-flight is not a batch anyone can pin.)
  if [ ! -x "$REPO_ROOT/vendor/agy" ] && command -v agy >/dev/null 2>&1; then
    bash "$SCRIPT_DIR/stage-agy.sh" >/dev/null
  fi
  # Every agent build arg — the CLI pins from the manifest (SPEC 1.4) and the
  # invoking operator's uid/gid — comes from ONE resolver,
  # harness.container.agent_build_args, which the runner's mid-batch auto-build
  # calls too. They were computed separately until batch 1 halted at plan index 19
  # on an auto-built image that had neither the host uid nor the agy pin: a default
  # correct for one caller is a defect waiting for the other. See that function for
  # why the uid must be the host's and when AGY_REQUIRED is 1.
  AGENT_ARGS_RAW="$(cd "$REPO_ROOT" && "$PY" - <<'PY'
import sys

import yaml

from harness.container import agent_build_args

with open("manifest/delivery-manifest.yaml", encoding="utf-8") as fh:
    manifest = yaml.safe_load(fh) or {}
try:
    args = agent_build_args(manifest, ".")
except ValueError as exc:
    print(f"build-subject-image: {exc}", file=sys.stderr)
    raise SystemExit(2)
for key, value in args.items():
    print(f"{key}={value}")
PY
)" || exit 2
  mapfile -t AGENT_ARGS <<< "$AGENT_ARGS_RAW"
  case "$AGENT_ARGS_RAW" in
    *SUBJECT_UID=*) ;;
    *) echo "build-subject-image: agent build args did not resolve a SUBJECT_UID" >&2; exit 2 ;;
  esac
  for arg in "${AGENT_ARGS[@]}"; do BUILD_ARGS+=(--build-arg "$arg"); done
fi

echo "== building subject image ($ROLE) =="
echo "  task:       $TASK_DIR_REL"
echo "  target:     $TARGET"
echo "  tag:        $TAG"
echo "  dockerfile: $DOCKERFILE"
if [ "$ROLE" = "agent" ]; then
  echo "  run_as:     lab (uid $(id -u), gid $(id -g)) — non-root, host-matched"
fi

docker build \
  -f "$DOCKERFILE" \
  --target "$TARGET" \
  "${BUILD_ARGS[@]}" \
  -t "$TAG" \
  "$REPO_ROOT"

echo "  ok    built $TAG"
echo "$TAG"
