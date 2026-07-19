# Batch-2 plan — full 27-run re-collection + F3 + human-effort (CP-SPEND draft)

Planning doc for the **single batch-2 CP-SPEND** (CLAUDE.md; SPEC §2.3; protocol
`methodology/feasibility-protocol.md`). Batch 1's 25 runs are superseded (NO_WRITE);
this re-collects the full 27 on the **fixed** harness (auto-approve tools; valid-UUID
sessions; modelUsage version capture; diff archiving; pilot-v2 contract). **This
draft does not authorize spend** and has blocking human prerequisites (§3).

## 1. Run matrix (all on the fixed harness)

### Controlled 27 (SPEC §2.3) — 3 tasks × {P0, C2, P1} × 3 reps, cold
| Task | Status |
|---|---|
| F1 = pilot-realworld (**pilot-v2**, contract pinned) | ready |
| F2 = w4-realworld-missing-user-id | ready |
| F3 = W1 test-generation | ⛔ **BLOCKED** — no-spend scaffold DONE; awaits human sealed test + 10-point validation (§3.2) |

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

### 3.1 Subject-isolation decision — ✅ DECIDED 2026-07-19: containerized, no network
Subjects run inside the task-tools Docker container with **network disabled**
(offline), still cwd-scoped. The runner execs the subject CLI inside the container;
`SUBJECT_PERMISSION_PROFILE` updates to record the containerized+offline posture
authoritatively. (Batch 1/revalidation used skip-perms + cwd on the bare dev VM.)
Implementation is a no-spend harness change, done before the batch-2 CP-SPEND.

### 3.2 F3 / W1 pinning — needs human sealed-test authoring (STOP)
No-spend work **DONE** (2026-07-19):
- W1 pinned in the manifest (`w1_task`, same RealWorld pin as pilot).
- Canonical reference tests (`canonical/mapper-tests.patch`): 100% branch on
  article.mapper, reachable ceiling (5/6 = 83.33%) on author.mapper, all six planned
  mutants caught, applies cleanly, baseline suite green. `author.mapper` cannot reach
  100% branch (one unreachable defensive `?.` leg) — human decision 2026-07-19
  "keep branches, honest ceiling"; evidence in `report/w1-coverage-analysis.md`.
- Test-generation gate wired: `check-public.sh` gate_type dispatch (T1 diff-scope,
  T2 suite-green, T3 per-file coverage, T4 tests-pass) + `validate.sh` gate_type
  support; gate logic split into offline-testable `scope_eval.py` / `coverage_eval.py`
  with unit tests. Verified end-to-end on a pinned checkout (no spend): pre-mod FAIL,
  canonical PASS, out-of-scope edit → T1 FAIL, vacuous test → T3 FAIL.

**STOP — remaining before F3 enters batch 2 (not done here):**
1. **(human)** author the sealed mutation-catch hidden test + runner
   (`tasks/suite/W1-test-generation/hidden/README-FOR-HUMAN.md`); human-authored,
   human-held. Then record its version + SHA in `manifest` (`w1_task.sealed_hidden_test`,
   currently `awaiting_human`).
2. **(me, no spend)** 10-point validation with the sealed test present → on 10/10,
   bump `task_suite_version: w1-v1-draft → w1-v1`. (Deferred here per session scope:
   "do not start validation".) W1's CP-SCREEN-PREREG must disclose this feasibility reuse.

### 3.3 Human-effort subset schedule
Human reviewers apply the timed rubric to the 9-run subset (one rep per cell), ≥2
reviewers on ≥3 runs. Produces criterion-6 timings + inter-reviewer spread; feeds
HEAC. **No model spend** — schedule is a calendar/assignment decision.

## 4. Sequence & checkpoints
1. **(human)** subject-isolation decision (§3.1) → I implement it (no spend).
2. **(me, no spend)** W1 pinning scaffold ✅ DONE (canonical + gate + validate
   support; §3.2) → **STOP: human sealed-test authoring** → W1 10-point validation.
3. **(me, no spend)** finalize this doc with W1 in the matrix + isolation posture →
   **CP-SPEND (batch 2)** approval.
4. **(me)** run batch 2 under the kill-switch → validate all → update
   `report/telemetry-completeness.md` (full 27, three gate types) + human-effort →
   **CP-DATA (final)**.
5. No result in docs/site until **CP-FINDINGS**.

## 5. What this plan does NOT do
No spend; no sealed-test authoring (human); no isolation decision (human); no
comparative/vendor claims. Metric outputs remain NON-COMPARATIVE, internal-only.
