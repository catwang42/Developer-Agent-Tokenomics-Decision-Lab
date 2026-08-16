# Containerized subject isolation

Two containers, two postures, two different jobs. Recorded authoritatively in
`manifest/delivery-manifest.yaml` (`subject_isolation`) and, per run, in
`identity.permission_profile` + `identity.network_policy` — stamped by the runner,
which knows the mode it launched.

| | deterministic gate | agent leg |
|---|---|---|
| image target | `subject-gate` | `subject-agent` |
| tag | `lab-subject/<task>:<pin12>` | `lab-subject-agent/<task>:<pin12>` |
| network | `--network=none`, always | egress allowlist (`--subject-egress allowlist`) |
| task material | **present** — the gate reads `task.yaml` to know what to grade | **none in any layer**, asserted at build |
| product CLIs | not needed | `claude` + `agy` baked at pinned, build-asserted versions |
| credentials | none | host gcloud config mounted **read-only** at `/creds/gcloud` |
| cwd | `/lab/<task>/.work/repo` | `/subject` |

The split exists because the two requirements are incompatible: the gate cannot work
without `task.yaml` (`harness/task-tools/lib.sh` reads `gate_type`, target paths and
write scope from it) and the agent must never see it. One image cannot be both.

## Pieces

| File | Role |
|---|---|
| `Dockerfile.subject` | Multi-target: `subject-base` → `subject-gate` / `subject-export` → `subject-agent` |
| `exec.py` | `docker_run_argv` (pure argv builder), `ContainerLaunch`, `ContainerExecutor`, image tags, credential mounts, env passthrough, image-label reads, handoff volumes |
| `egress.py` | `EgressPolicy` (allowlist + sha256 + the label stamped into `network_policy`), proxy/network lifecycle |
| `egress/allowlist-model-api.txt` | The allowlist itself — deny-by-default host regexes, each with its provenance |
| `egress/Dockerfile.egress`, `egress/tinyproxy.conf` | The deny-by-default forward proxy |
| `assert-no-task-material.sh` | The build-time exclusion assertion (also baked in, so it can be re-run) |
| `stage-agy.sh` | Vendors the Product-B CLI from the build host with a content hash |
| `verify-egress.sh` | Live, no-spend proof that the allowlist enforces what it claims |
| `build-subject-image.sh` | Resolves the tag + pins and builds either target |

## What each mode enforces (and what it does not)

Overstating a posture is how a weak sandbox gets cited as a strong one, so the
stamps are written to be read literally.

**`--subject-isolation host`** (the feasibility fallback, still supported). The
subject tree is staged in a temp dir outside the lab repo and harness path-pointer
env vars are scrubbed, so `canonical/`, `hidden/` and `task.yaml` are unreachable by
relative traversal or env pointer. Not enforced: the agent runs same-uid on the bare
VM with no container and no filesystem namespace, so absolute-path access to the
wider filesystem remains possible, and there is no network policy at all.

**`--subject-isolation container`, gate.** Hermetic: `--network=none`, deps baked, no
host filesystem except the run's `/out`. It is *not* answer-hiding — task material is
present by design, which is why `assert-no-task-material` is not applied to it.

**`--subject-isolation container`, agent leg.** Filesystem-namespaced; `/subject`
holds the subject repo and nothing else; no `canonical/`, `hidden/` or `task.yaml`
exists in any layer of the image (build-asserted — see below); product CLIs are baked
at versions the build checked against the CLIs themselves; credentials are mounted
read-only. Not enforced: tool permissions are still bypassed *inside* the container,
the process runs as root *in the container*, and egress is **allowlisted, not
absent** — the exact allowlist and its hash are recorded separately in
`identity.network_policy`.

## The exclusion assertion

`.dockerignore` is a statement of intent, not a guarantee. A 2026-07-19 W1 image
shipped `canonical/mapper-tests.patch` because the `**/canonical/` rule postdated the
build — nothing caught it until this assertion was written. So the agent image both
strips and verifies:

* `subject-export` moves the subject repo to a fixed path and deletes `/lab`;
* `subject-agent` starts from a clean base and `COPY --from=subject-export` brings
  only the repo, so no layer of the agent image ever contained task material (a
  `rm -rf` in the final stage would leave it recoverable from `docker save`);
* `RUN assert-no-task-material /` scans the whole filesystem — not a declared subtree,
  because the failure mode is material arriving somewhere nobody thought to look —
  and **fails the build**, so a bad image never exists to be run.

## Egress allowlist (agent leg only)

The agent container joins an `--internal` Docker network, which has **no default
route**. A tinyproxy container sits on that network *and* on `bridge`, making it the
only hop out, and refuses (403) any host not matching
`egress/allowlist-model-api.txt`, naming it in the log. `HTTPS_PROXY` is set for
convenience; it is not the control — an agent that unsets it still has no route.

`identity.network_policy` records the allowlist name and sha256, so runs made under
different allowlists are distinguishable from their summaries alone.

**Enforcement is verified; sufficiency is not.** `verify-egress.sh` proves
deny-by-default with no spend. Whether this exact list is *enough* for a full agentic
run of either product can only be established by a CP-SPEND-approved live run — the
Product-B entries in particular come from strings in the installed binary, not from
an observed `agy` run. When a live run fails, the proxy log names the refused host.

## Agent → gate handoff

The agent's edits must reach a gate that runs in a *different image*. A per-run named
volume is mounted at `/subject` in the agent container and at
`/lab/<task>/.work/repo` in the gate container; Docker seeds an empty named volume
from the image content on first mount, so the agent starts from the pristine baked
tree with no host copy step, and the gate grades exactly what the agent produced.

## Commands (no model spend)

```bash
# Gate image (default target).
bash harness/container/build-subject-image.sh tasks/suite/W1-test-generation

# Agent image: pins come from manifest subject_isolation.agent_leg; agy is staged
# from this host by stage-agy.sh; the build asserts both pins and the exclusion.
bash harness/container/build-subject-image.sh tasks/suite/W1-test-generation agent

# Prove the egress allowlist enforces what it claims (four cases, no spend).
bash harness/container/verify-egress.sh

# Run the deterministic public gate OFFLINE.
docker run --rm --network=none \
  -e TASK_DIR=/lab/tasks/suite/W1-test-generation \
  -e TASK_WORKDIR=/lab/tasks/suite/W1-test-generation/.work \
  lab-subject/w1-realworld-mapper-tests:<pin12> \
  bash /lab/harness/task-tools/gate/check-public.sh
```

The runner drives all of this with `--subject-isolation container`
`--subject-egress allowlist` (defaults: `host`, `none`). A live agent run remains
CP-SPEND-gated; everything above is build/verify tooling and spends nothing.
