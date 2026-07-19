# Containerized subject isolation (batch-2 posture)

Human decision (2026-07-19, `manifest/cp-spend-batch2-plan.md` §3.1): benchmark
subjects run **inside the task-tools Docker container with the network disabled**
(`--network=none`), replacing the batch-1/revalidation posture (skip-perms + cwd on
the bare dev VM). Recorded authoritatively in `manifest/delivery-manifest.yaml`
(`subject_isolation`) and, per run, in `identity.permission_profile` +
`identity.network_policy` (stamped by the runner — it knows the mode it launched).

## Pieces

| File | Role |
|---|---|
| `exec.py` | `docker_run_argv` (pure argv builder), `ContainerExecutor`, `subject_image_tag`, `image_exists`, `build_subject_image` |
| `Dockerfile.subject` | Per-task OFFLINE image; bakes the subject repo + `node_modules` + Prisma client at BUILD time |
| `build-subject-image.sh` | Wrapper: computes the deterministic tag and builds the image |

## Why bake deps (not mount the host's)

The graded run is offline, so the container needs its deps present with no network.
The host toolchain is node v22 while the image is node v20, and Prisma/esbuild ship
platform-specific native binaries — installing INSIDE the image (build-time network)
guarantees the deps match the container platform. Build-time `git clone` + `npm ci`
is tooling setup, **never model spend** (CLAUDE.md rule 5).

## Offline gate flow (fully verified, no spend)

```bash
# 1. Build the per-task image (build-time network; not spend).
TAG="$(bash harness/container/build-subject-image.sh tasks/suite/W1-test-generation | tail -1)"

# 2. Run the deterministic public gate OFFLINE (jest/coverage/build, no network).
docker run --rm --network=none \
  -e TASK_DIR=/lab/tasks/suite/W1-test-generation \
  -e TASK_WORKDIR=/lab/tasks/suite/W1-test-generation/.work \
  "$TAG" bash /lab/harness/task-tools/gate/check-public.sh
```

The runner drives this automatically with `--subject-isolation container` (default
`host` for back-compat and `--dry-run`).

## Live agent leg — CP-SPEND finalization item

The deterministic **gate** runs `--network=none` (hermetic; verified this session).
The live **agent leg** (`claude -p` → Vertex, `agy` → Google) needs egress to the
model API, which `--network=none` blocks. Its egress posture — a model-API-only
allowlist (a named docker network) — is **finalized and validated at CP-SPEND**
(it cannot be validated without model spend). The container mechanism (argv builder +
`ContainerExecutor`) is in place and unit-tested; only the agent-leg network value
changes from `none` to the approved egress network at run time, and whatever value
is used is recorded authoritatively in `identity.network_policy`.
