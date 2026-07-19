# Subject-isolation verification — containerized, network-disabled posture (batch-2)

**Date:** 2026-07-19 · **Posture:** container / `--network=none` (human decision
`manifest/cp-spend-batch2-plan.md` §3.1; recorded `manifest` `subject_isolation`).
**Scope:** NO-SPEND harness change verified offline. No model API call, no vendor
claim. The live agent leg's model-API egress is deferred to CP-SPEND (see below).

## What was verified (all offline, `docker run --network=none`)

Per-task offline image built by `harness/container/build-subject-image.sh`
(`Dockerfile.subject`; deps baked at BUILD time — build-time network is tooling
setup, not model spend, CLAUDE.md rule 5): `lab-subject/w1-realworld-mapper-tests:30b68e1e8814`.

### 1. Deterministic gate runs offline
- **Pre-modification (pristine baked tree):** public gate → **FAIL**
  (`T1` pass; `T2/T3/T4` fail — no agent tests). Correct pre-mod behavior.
- **Canonical patch applied:** public gate → **PASS**. `T2` suite-green, `T3`
  coverage (article.mapper 0/0=100%, author.mapper 5/6=83.33% honest ceiling),
  `T4` tests-pass — i.e. **jest, `--coverage`, and `nx build` all executed with the
  network disabled**.

### 2. W1 10-point validation INSIDE the container (`--network=none`)
`validate.sh` run against the baked image (setup.sh skips the clone — repo + deps
baked — so the full 10-point runs offline):

```
RESULT: 9 passed, 1 awaiting-human, 0 failed (of 10)
```

| # | check | status |
|---|---|---|
| 1 | commit-exists | pass (HEAD == 30b68e1e8814…) |
| 2 | deps-orm | pass |
| 3 | paths-exist | pass |
| 4 | clean-install | pass |
| 5 | baseline-tests | pass (article\|profile\|utils\|tag\|mapper) |
| 6 | premod-failure | pass (T3-coverage fails pre-mod) |
| 7 | canonical-hidden | **awaiting_human** (canonical accepted by public gate; sealed hidden tests human-held) |
| 8 | no-leakage | pass |
| 9 | clean-build | pass (nx build, **container**) |
| 10 | deterministic-reset | pass (tree=b76a4619b3d7…) |

This is Item 4: W1 pre-mod validation under the SAME environment batch 2 will use —
**no posture delta** between validation and the batch it validates for.

## Not done here (by design)
- **No `task_suite_version` bump.** Check 7 is `awaiting_human`: the sealed
  mutation-catch test is human-authored/held (`tasks/suite/W1-test-generation/hidden/`).
  W1 → `w1-v1` only after the human authors it and the 10-point re-runs 10/10.
- **Live agent-leg egress.** The gate is hermetic offline; the live agent leg
  (`claude -p`/`agy`) needs model-API egress, which `--network=none` blocks. Its
  egress allowlist (a named docker network) is finalized + validated at **CP-SPEND**
  (needs model spend). The container mechanism is wired + unit-tested; only the
  agent-leg network value changes, and whatever is used is recorded authoritatively
  in `identity.network_policy`. For a LIVE run the agent's edits and the gate must
  co-locate in one container instance — a CP-SPEND orchestration detail.
