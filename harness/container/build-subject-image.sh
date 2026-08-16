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
  # Product CLI pins, read from the manifest (the single place volatile versions
  # resolve, SPEC 1.4). The Dockerfile asserts each against the installed CLI.
  eval "$(cd "$REPO_ROOT" && "$PY" - <<'PY'
import yaml

with open("manifest/delivery-manifest.yaml", encoding="utf-8") as fh:
    m = yaml.safe_load(fh) or {}
leg = ((m.get("subject_isolation") or {}).get("agent_leg") or {})
print(f"CLAUDE_CLI_VERSION={leg.get('claude_cli_version', '')}")
print(f"AGY_VERSION={leg.get('agy_version', 'unavailable')}")
print(f"AGY_SHA256={leg.get('agy_sha256', 'unavailable')}")
PY
)"
  if [ -z "${CLAUDE_CLI_VERSION:-}" ]; then
    echo "build-subject-image: manifest subject_isolation.agent_leg.claude_cli_version" >&2
    echo "                     is missing; refusing to bake an unpinned CLI." >&2
    exit 2
  fi
  # Stage the Product-B binary from this host if it is not already vendored.
  if [ ! -x "$REPO_ROOT/vendor/agy" ] && command -v agy >/dev/null 2>&1; then
    bash "$SCRIPT_DIR/stage-agy.sh" >/dev/null
  fi
  if [ ! -x "$REPO_ROOT/vendor/agy" ]; then
    echo "  note  vendor/agy absent — the image will build WITHOUT Product B and" >&2
    echo "        label agy.version=unavailable. Product-B legs cannot run in it." >&2
    AGY_REQUIRED=0; AGY_VERSION=unavailable; AGY_SHA256=unavailable
  else
    AGY_REQUIRED=1
  fi
  BUILD_ARGS+=(
    --build-arg "CLAUDE_CLI_VERSION=$CLAUDE_CLI_VERSION"
    --build-arg "AGY_VERSION=$AGY_VERSION"
    --build-arg "AGY_SHA256=$AGY_SHA256"
    --build-arg "AGY_REQUIRED=$AGY_REQUIRED"
  )
fi

echo "== building subject image ($ROLE) =="
echo "  task:       $TASK_DIR_REL"
echo "  target:     $TARGET"
echo "  tag:        $TAG"
echo "  dockerfile: $DOCKERFILE"

docker build \
  -f "$DOCKERFILE" \
  --target "$TARGET" \
  "${BUILD_ARGS[@]}" \
  -t "$TAG" \
  "$REPO_ROOT"

echo "  ok    built $TAG"
echo "$TAG"
