#!/usr/bin/env bash
# Build a per-task OFFLINE subject image (deps baked in at build time).
#
#   bash harness/container/build-subject-image.sh tasks/suite/W1-test-generation
#
# Prints the resulting image tag on success. Build-time network is used to clone
# the subject repo + `npm ci`; this is tooling setup, NEVER model spend
# (CLAUDE.md rule 5). The graded run is then fully offline (--network=none).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DOCKERFILE="$SCRIPT_DIR/Dockerfile.subject"

TASK_DIR_ARG="${1:?usage: build-subject-image.sh <task_dir> (e.g. tasks/suite/W1-test-generation)}"
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
TAG="$(cd "$REPO_ROOT" && TASK_DIR="$TASK_DIR_ABS" "$PY" - "$TASK_DIR_ABS" <<'PY'
import os
import sys

import yaml

from harness.container import subject_image_tag

task_dir = sys.argv[1]
with open(os.path.join(task_dir, "task.yaml"), encoding="utf-8") as fh:
    ty = yaml.safe_load(fh) or {}
task_id = ty["task_id"]
mkey = ty["manifest_key"]
repo_root = os.getcwd()
with open(os.path.join(repo_root, "manifest", "delivery-manifest.yaml"), encoding="utf-8") as fh:
    manifest = yaml.safe_load(fh) or {}
pin = (manifest.get(mkey) or {})["pinned_commit"]
print(subject_image_tag(task_id, pin))
PY
)"

echo "== building offline subject image =="
echo "  task:       $TASK_DIR_REL"
echo "  tag:        $TAG"
echo "  dockerfile: $DOCKERFILE"

docker build \
  -f "$DOCKERFILE" \
  --build-arg "BAKE_TASK_DIR=$TASK_DIR_REL" \
  -t "$TAG" \
  "$REPO_ROOT"

echo "  ok    built $TAG"
echo "$TAG"
