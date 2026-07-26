# Batch-2 package — full 27-run re-collection + F3 + human-effort (CP-SPEND)

CP-SPEND package for the **single batch-2 run** (CLAUDE.md; SPEC §2.3; protocol
`methodology/feasibility-protocol.md`). Batch 1's 25 runs are superseded (NO_WRITE);
this re-collects the full 27 on the **fixed** harness (auto-approve tools; valid-UUID
sessions; modelUsage version capture; diff archiving; pilot-v2 contract). The
blocking human prerequisites (§3) are now **RESOLVED** — subject isolation
implemented + verified offline, and W1/F3 promoted to `w1-v1` on a human-authored
sealed test (10/10). **Approving this checkpoint authorizes the spend in §2 under
the §2 kill-switch; nothing runs before `CHECKPOINT APPROVED: CP-SPEND`.**

**Package contents (CLAUDE.md CP-SPEND gate = budget + configs + manifest):**
- Budget & kill-switch: §2 (ceiling $30, `--spend-cap-usd 30`).
- Run matrix: §1 (all three gate types; F1 feature, F2 bugfix, F3 test-generation).
- Configs: `harness/configurations/{C1..C5}.yaml`; policies
  `harness/policies/{p0-baseline,p1-cheap-first}.yaml`.
- Manifest: `manifest/delivery-manifest.yaml` (pins + all three sealed-test hashes);
  per-run pre-registration via `manifest/RUN_TEMPLATE.md`.
- Isolation posture: containerized, network-disabled subjects
  (`report/findings/subject-isolation-verification.md`).
- CP-DATA condition 1 (gate-fairness) status: §3.4.

## 1. Run matrix (all on the fixed harness)

### Controlled 27 (SPEC §2.3) — 3 tasks × {P0, C2, P1} × 3 reps, cold
| Task | Status |
|---|---|
| F1 = pilot-realworld (**pilot-v2**, contract pinned) | ready |
| F2 = w4-realworld-missing-user-id (**sealed-w4-v2**) | ready |
| F3 = W1 test-generation (**w1-v1**, sealed test recorded, 10/10) | ready |

### Companions (re-collected; batch-1's were NO_WRITE / invalid)
- Product telemetry: F1 × {C3, C5} × 2 reps (Product B `agy` fix now applied).
- Cache warm-series: F1 × C1, 3-run series (cold → resume ×2).
- Human-effort subset: 9 already-produced runs, timed rubric, ≥2 reviewers on ≥3
  (**no model spend** — §3.3).

**Billable model runs:** 27 controlled + ~4 product + 3 warm ≈ **34**.

## 2. Cost estimate — grounded in revalidation ACTUALS (not a-priori)

Revalidation real agentic runs (8–20 turns) cost **$0.12–0.56** each (cache-read of
the repo dominates; real edits added little). Extrapolated:

| Group | Runs | $/run band | Subtotal |
|---|---|---|---|
| Controlled 27 | 27 | 0.10–0.65 | $3–18 |
| Product companions | ~4 | 0.10–0.40 (Product B often cost-unavailable) | $0.4–1.6 |
| Warm-series | 3 | 0.04–0.30 | $0.1–0.9 |
| **Total** | ~34 | | **~$4–20** |

**Proposed ceiling: $30** (headroom over the ~$20 high band), enforced by the
in-runner `--spend-cap-usd` kill-switch. Actual is expected well under.

## 3. Prerequisites — human stops before any run

### 3.1 Subject-isolation decision — ✅ DECIDED 2026-07-19; ✅ IMPLEMENTED 2026-07-19
Subjects run inside the task-tools Docker container with **network disabled**
(offline), still cwd-scoped. **NO-SPEND harness change done 2026-07-19:**
- `harness/container/` (`exec.py` argv builder + `ContainerExecutor` + per-task
  `Dockerfile.subject` baking deps at build time + `build-subject-image.sh`).
- Runner `--subject-isolation {host|container}` + `--subject-network`; the runner
  stamps `identity.permission_profile` + `identity.network_policy` **authoritatively**
  (two postures in `base.py`: `SUBJECT_PROFILE_HOST`/`_CONTAINER`). Adapters route
  their spawn through `resolve_spawn` (host cwd vs `docker run`).
- Deterministic gate verified **fully offline** (`--network=none`): W1 pre-mod FAIL,
  canonical PASS (jest/coverage/nx build ran with no network). Evidence:
  `report/findings/subject-isolation-verification.md`; posture recorded in
  `manifest` `subject_isolation`.
- **Deferred to CP-SPEND (user decision):** the live agent leg's model-API egress
  allowlist (needs model spend to validate). Mechanism wired + unit-tested; the gate
  is hermetic offline now.

**CP-SPEND RESOLUTION (2026-07-20) — batch 2 runs the HOST agent leg.** On approval,
inspection showed the containerized *live-agent* leg is unimplemented: `Dockerfile.subject`
(node:20-slim) bakes no `claude`/`agy` CLI, and `resolve_spawn` passes the agent-leg
container no credentials and no egress (network defaults to `none`). Making it run — bake
the agent CLIs, mount gcloud ADC + Vertex env, wire an egress network for the agent leg
while the gate stays `--network=none` — is **new engineering**, so **both** branches of
decision (4) are unrunnable as written. Per the human (2026-07-20), batch 2 runs
**`--subject-isolation host`** (the proven path; `claude -p` authenticates via the ambient
Vertex env). Every run stamps `identity.permission_profile = host` and
`identity.network_policy = no-network-policy` **verbatim** (authoritative). **Containerized-
subject isolation AND endpoint-allowlist egress become HARD REQUIREMENTS for the Phase-4
screening CP-SPEND** (accept-small / mandate-later, extended from egress to the whole
containerized agent leg). The deterministic gate remains containerized + `--network=none`.
Batch-2 outputs land in `results/feasibility-batch2/` (batch-1 preserved untouched; clean
spend-cap + aggregation).

**Reordering (this session):** containerization was done **before** the W1 pre-mod
validation (below), so the 10-point ran under the SAME containerized *gate* posture batch 2
will use — no posture delta between validation and the batch it validates for.

### 3.2 F3 / W1 pinning — needs human sealed-test authoring (STOP)
No-spend work **DONE** (2026-07-19):
- W1 pinned in the manifest (`w1_task`, same RealWorld pin as pilot).
- Canonical reference tests (`canonical/mapper-tests.patch`): 100% branch on
  article.mapper, reachable ceiling (5/6 = 83.33%) on author.mapper, all six planned
  mutants caught, applies cleanly, baseline suite green. `author.mapper` cannot reach
  100% branch (one unreachable defensive `?.` leg) — human decision 2026-07-19
  "keep branches, honest ceiling"; evidence in `report/findings/w1-coverage-analysis.md`.
- Test-generation gate wired: `check-public.sh` gate_type dispatch (T1 diff-scope,
  T2 suite-green, T3 per-file coverage, T4 tests-pass) + `validate.sh` gate_type
  support; gate logic split into offline-testable `scope_eval.py` / `coverage_eval.py`
  with unit tests. Verified end-to-end on a pinned checkout (no spend): pre-mod FAIL,
  canonical PASS, out-of-scope edit → T1 FAIL, vacuous test → T3 FAIL.

**Containerized pre-mod validation — ✅ DONE 2026-07-19 (this session):** W1's
10-point `validate.sh` ran INSIDE the container (`--network=none`) → **9 pass, 1
awaiting-human, 0 failed**: pre-mod FAILs, canonical accepted offline, clean-build +
deterministic reset offline; check 7 (canonical-hidden) is `awaiting_human` because
the sealed test is human-held. Evidence: `report/findings/subject-isolation-verification.md`.

**RESOLVED — F3 is ready (2026-07-20):**
1. **(human)** ✅ authored the sealed mutation-catch runner
   (`tasks/suite/W1-test-generation/hidden/check.sh` + `VERSION`, human-held,
   gitignored), six seeded mutants per `README-FOR-HUMAN.md`.
2. **(me, no spend)** ✅ wired the `test_generation` hidden gate: `check-hidden.sh`
   now discovers the executable sealed runner, invokes it with `SUBJECT_DIR`
   exported, honors 0/1/2, and records version + a sha256 over the whole sealed set
   (never reading its contents); unit-tested with a SYNTHETIC runner
   (`tests/test_hidden_gate.py`). 10-point validation **10/10** (all six mutants
   caught; canonical accepted; pre-mod fails; deterministic reset).
   `task_suite_version: w1-v1`; manifest `w1_task.sealed_hidden_test` =
   `sealed-w1-v1 2026-07-20 6-mutants`, `sha256:37f3acd6…c51f4e9` (harness-computed
   hidden_test_hash from the validation report; not hand-entered). W1's
   CP-SCREEN-PREREG must disclose this feasibility reuse.

### 3.3 Human-effort subset schedule
Human reviewers apply the timed rubric to the 9-run subset (one rep per cell), ≥2
reviewers on ≥3 runs. Produces criterion-6 timings + inter-reviewer spread; feeds
HEAC. **No model spend** — schedule is a calendar/assignment decision.

### 3.4 Gate-fairness audit — CP-DATA condition 1 status (carried into this package)
The earlier CP-DATA review imposed condition 1: classify every F1 rejection as
(i) feature genuinely absent/broken vs (ii) functionally plausible but failing on
implementation *shape*. Status (`report/findings/gate-fairness-audit.md`):
- **F1·P1·rep1** — classified **(ii) shape mismatch** with archived diff evidence
  (near-canonical impl; failed only because it emitted `{draft:{equals:false}}` vs
  the matcher's `{draft:false}` — functionally identical in Prisma). Remedy was
  applied to the **task, not the gate**: the pilot prompt now pins the contract shape
  (`pilot-v1 → pilot-v2`); the **sealed hidden hash is unchanged** (`sha256:105c2418…`)
  and the gate was **not** loosened. 10-point re-validation: 10/10.
- **F1·P0·rep1 / rep2** — **undetermined**: their diffs were reset-overwritten before
  archiving (the provenance gap). The fix (`run.py::_archive_agent_diff`, writes
  `agent-solution.diff` per run pre-reset) is now in place, so batch-2 re-collection
  will produce inspectable diffs and these two are **re-classified from batch-2 data**,
  not backfilled or fabricated.
- **Bearing on this checkpoint:** condition 1 is substantially discharged; the only
  residual (2 undetermined runs) is *itself a reason to run batch 2* under the now-fixed
  provenance path. No result enters docs/site before CP-FINDINGS regardless.

## 4. Sequence & checkpoints
1. **(human)** subject-isolation decision (§3.1) ✅ → **(me, no spend)** implement it
   ✅ DONE 2026-07-19 (container harness + offline gate verified).
2. **(me, no spend)** W1 pinning scaffold ✅ DONE; `test_generation` hidden gate
   wired + unit-tested ✅ DONE; human sealed test authored ✅; 10-point **10/10**
   ✅ → `w1-v1` bump + sealed hash recorded (§3.2).
3. **(me, no spend)** finalize this doc with W1 in the matrix + isolation posture +
   gate-fairness status ✅ DONE → **CP-SPEND (batch 2)** ⬅ **awaiting approval now**.
4. **(me)** run batch 2 under the kill-switch → validate all → update
   `report/batch2/telemetry-completeness.md` (full 27, three gate types) + human-effort →
   **CP-DATA (final)**.
5. No result in docs/site until **CP-FINDINGS**.

## 5. What this plan does NOT do
No spend; no sealed-test authoring (human); no isolation decision (human); no
comparative/vendor claims. Metric outputs remain NON-COMPARATIVE, internal-only.
