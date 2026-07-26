# Batch-3 package — 30-run Product-A re-collection on the isolated harness (CP-SPEND)

CP-SPEND package for the **single batch-3 run** (CLAUDE.md rule 5; SPEC §2.3;
protocol `methodology/feasibility-protocol.md`). This re-collects **Product A only**
on the harness as fixed since batch 2 (defect Fixes 1–5 + subject-isolation
remediation FIX A–E). Batch 2's Product-A cells are superseded for re-collection
because the harness that produced them has since changed in ways that affect what
each run records and how the subject is isolated (§1). **Approving this checkpoint
authorizes the spend in §3 under the §3 kill-switch and nothing else; nothing runs
before the human writes `CHECKPOINT APPROVED: CP-SPEND`.**

**Status:** awaiting approval. Prepared 2026-07-26 on branch `phase/3-harness`.
No model spend occurred in preparing it.

**Package contents (CLAUDE.md CP-SPEND gate = budget + configs + manifest):**
- Budget & kill-switch: §3 (ceiling $30, `--spend-cap-usd 30`).
- Run matrix: §2 (30 runs, Product A only; three gate types F1/F2/F3).
- Configs: `harness/configurations/{C1,C2}.yaml`; policies
  `harness/policies/{p0-baseline,p1-cheap-first}.yaml`.
- Manifest: `manifest/delivery-manifest.yaml` (pins + all three sealed-test hashes).
- Isolation posture: §5 (staged-subject **host** mode, `SUBJECT_PROFILE_HOST`).
- Results directory: `results/feasibility-batch3/` (§6 — batch 1 & 2 untouched).

## 1. Why re-collect rather than reuse batch 2

Batch 2's Product-A runs are technically valid but were produced on a harness that
has since changed in two material ways. Reusing them would mix harness versions
inside one feasibility dataset. The changes:

### Defect Fixes 1–5 (harness-owned instrumentation, SPEC §1.3)
1. **Fix 1 — untracked-file capture in the agent diff.** `agent-solution.diff` now
   archives the contents of untracked files the agent created, not just tracked-file
   hunks; batch-2 diffs could under-represent an agent's work.
2. **Fix 2 — per-leg `invocation.txt`.** Each run now records argv + product version
   + exit code + raw stdout/stderr (credentials redacted) per billing leg. Batch 2
   had no such artifact, so a run's raw provenance was not inspectable after the fact.
3. **Fix 3 — corrected agy invocation.** The adapter no longer prepends a bogus `run`
   token (Product-B only; see §4).
4. **Fix 4 — task configuration declarations reconciled + enforced.** The per-task
   declared config set is now reconciled against what the runner accepts and enforced
   at launch, closing a gap where a run could execute under a config the task never
   declared.
5. **Fix 5 — archive the agent diff BEFORE the gate mutates the subject.**
   `agent-solution.diff` is now captured pre-gate; any harness gate patch is isolated
   in `post-gate.diff`. In batch 2 the gate could overwrite the agent's diff before it
   was archived — the exact provenance gap that left two batch-2 F1·P0 runs
   **undetermined** in the gate-fairness audit (batch-2 plan §3.4). Re-collection under
   Fix 5 produces inspectable per-run diffs for every cell.

### Subject-isolation remediation FIX A–E (`report/` isolation record)
A leak was found and remediated: the subject tree was previously staged **inside** the
lab repo, so an agent could reach `canonical/`, `hidden/`, and `task.yaml` by relative
path. Remediation:
- **FIX A** — stage the subject tree in a temp dir **outside** the lab repo.
- **FIX B** — scrub harness path pointers from the agent's environment.
- **FIX C** — honest `SUBJECT_PROFILE_HOST` label (see §5) replacing the old
  `cwd-confined-.work-repo` wording, which no longer describes the boundary.
- **FIX D** — exclude `canonical/` from the subject Docker image (.dockerignore).
- **FIX E** — regression test: a staged subject cannot reach answers by relative
  traversal.

**Bearing on the data:** batch-2 runs were staged inside the repo and stamped the old
host label; batch-3 runs are staged outside the repo and stamp `SUBJECT_PROFILE_HOST`
verbatim. The isolation posture recorded on a run is part of its provenance, so batch
2 and batch 3 must not be pooled — batch 3 is the clean, self-consistent set.

## 2. Run matrix — 30 runs, **Product A only**

### Controlled 27 (SPEC §2.3) — F1/F2/F3 × {P0, C2, P1} × 3 reps, **cold cache**
| Task | Pin / gate |
|---|---|
| F1 = pilot-realworld (feature, **pilot-v2** contract) | ready |
| F2 = w4-realworld-missing-user-id (bugfix, **sealed-w4-v2**) | ready |
| F3 = W1 test-generation (**w1-v1**, sealed mutation-catch runner, 10/10) | ready |

- **P0** = `harness/policies/p0-baseline.yaml` (strong single-model).
- **C2** = `harness/configurations/C2.yaml`.
- **P1** = `harness/policies/p1-cheap-first.yaml` (cheap-first routing).

### Warm-cache series — F1 × C1 × 3 reps
`harness/configurations/C1.yaml`; run as a cold → resume ×2 series to exercise the
cache-warm cost path.

**Billable model runs: 27 + 3 = 30, all Product A** (`claude -p --output-format json`
usage metadata, authoritative tier). No Product-B / `agy` runs in this package (§4).

## 3. Cost estimate & kill-switch — grounded in batch-2 ACTUALS

The same 30-cell Product-A structure cost, in batch 2:

| | Value |
|---|---|
| 30 Product-A runs, total | **$4.1336** |
| Mean per run | **$0.138** |

**Caveat — this $4.13 undercounts true spend.** A run whose cost cannot be fully
reconstructed (e.g. a leg reporting `unavailable`) records its run-level cost as
**None**, so it contributes **$0** to the batch-2 total rather than its real (unknown)
cost. The figure is therefore a **lower bound**, not the true actual. Batch 3 is
Product-A only, where usage metadata is authoritative, so its total should be a
tighter reconstruction — but the ceiling is set with headroom accordingly.

**Ceiling: $30**, enforced by the in-runner kill-switch **`--spend-cap-usd 30`**
(runner default is $60; this lowers it). The switch halts the batch **before** starting
any further run once known cumulative spend reaches the cap. $30 is ~7× the batch-2
actual — deep headroom over a lower-bound baseline, with the switch as the hard stop.

## 4. Why C3 and C5 are DROPPED (Product B → Phase 4)

C3 (Product B solo) and C5 (Product A conductor + Product B executor, dual-bill) are
**removed from this batch**. Reasons, from the approved smoke run
(`manifest/cp-spend-agy-smoke.md`; evidence committed 2026-07-26):

1. **No machine-readable usage (observed 2026-07-26).** With the corrected invocation
   (Fix 3), `agy --print` emits a **plain-text transcript with no JSON usage block** —
   confirmed by inspecting the smoke run's `invocation.txt`. Product B exposes no
   parseable token counts, so its marginal cost can only ever be recorded
   `unavailable` from the product side. This is now an **observed** result, superseding
   the earlier "not yet observed on a verified invocation" wording in
   `report/telemetry-completeness.md` §4 finding 3.
2. **`--print` timeout confounded the smoke run.** The smoke run exited non-zero with
   `Error: timeout waiting for response`; the product's print/timeout behaviour is not
   yet a controlled variable. Including C3/C5 now would inject an uncontrolled failure
   mode into the feasibility batch.
3. **Version drift 1.1.4 → 1.1.7.** The batch-2 defect was diagnosed against agy
   **1.1.4**; the smoke run recorded product version **1.1.7** (`invocation.txt`). The
   product moved under us between batches — a moving target unsuitable for a controlled
   feasibility cell.

**Product B moves to Phase 4** and is measured there with the **provider-side
collector** (usage read from the billing provider, not the product's stdout), which is
the correct instrument given (1). No Product-B claim, comparative or otherwise, is
made from this batch.

## 5. Isolation posture

- **Batch 3 runs `--subject-isolation host`** in the **staged-subject** mode, stamping
  `identity.permission_profile = SUBJECT_PROFILE_HOST` **verbatim** (authoritative):
  `skip-all-tools; subject-staged-in-temp-outside-lab-repo;
  no-relative-path-to-canonical|hidden|task.yaml; harness-env-pointers-scrubbed;
  same-uid; no-container; no-fs-namespace; absolute-path-fs-access-NOT-confined;
  no-network-policy`. This is the honest boundary after FIX A–E: the subject is staged
  outside the lab repo and cannot reach answers by relative path, but it is not
  containerized and absolute-path FS access is not confined.
- **The containerized live-agent leg remains a Phase-4 requirement**, not satisfied
  here. Full container isolation + model-API egress allowlist for the agent leg are
  **HARD REQUIREMENTS at the Phase-4 screening CP-SPEND** (carried from the batch-2
  resolution and report §6 condition 1), not at this Phase-3 feasibility batch. The
  deterministic gate continues to run containerized under `--network=none`.

## 6. Results directory

All batch-3 output lands in **`results/feasibility-batch3/`**. Batch 1
(`results/feasibility/`) and batch 2 (`results/feasibility-batch2/`) are **not**
overwritten or aggregated into batch 3 — clean spend-cap accounting and a
single-harness-version dataset.

## 7. Sequence & downstream gates

1. **(me, no spend)** finalize this package ✅ → **CP-SPEND (batch 3)** ⬅ **awaiting
   approval now**.
2. **(me)** on approval, run the 30 runs under `--spend-cap-usd 30` → validate every
   `events.jsonl` + `summary.json` → aggregate into
   `results/feasibility-batch3/aggregate-noncomparative.json`.
3. **(me, no spend)** update `report/telemetry-completeness.md` (30 Product-A runs,
   three gate types, single harness version) + re-classify the two previously
   undetermined F1·P0 runs from batch-3 diffs (Fix 5) → **CP-DATA (final)**.
4. No result enters docs/site/report before **CP-FINDINGS**.

## 8. What this plan does NOT do

No spend before approval; no Product-B / `agy` runs (deferred to Phase 4); no
containerized agent leg (Phase 4); no sealed-test authoring; no comparative or vendor
claims. All metric outputs remain NON-COMPARATIVE and internal-only.
