> **STATUS: AUTHORITATIVE** — 2026-07-26. The current authoritative
> telemetry-completeness report (batch 3). Supersedes
> [`report/batch2/telemetry-completeness.md`](../batch2/telemetry-completeness.md)
> and [`report/batch1/telemetry-completeness.md`](../batch1/telemetry-completeness.md).

# Telemetry-completeness report — Phase 3 feasibility (batch 3, AUTHORITATIVE)

Prepared for **CP-DATA (final)** (CLAUDE.md; SPEC §2.3; binding protocol
`methodology/feasibility-protocol.md`). This document reports whether the
**measurement system works** — it makes **no vendor-comparative claims** and all
metric outputs are **NON-COMPARATIVE, internal-only** (SPEC §1.2 claims register).

**Batch 3 is the authoritative controlled feasibility dataset.** It re-collects the 27
controlled Product-A runs (plus the warm-series) on the harness *as fixed after batch 2*
— defect Fixes 1–5 **and** the subject-isolation remediation FIX A–E (pre-gate diff
archiving, per-leg `invocation.txt`, task-config enforcement, and the staged-subject
posture). A re-collection was required because the harness changed **materially**, so
batch-2 numbers are no longer collected under the same harness version. Batch 2, batch 1,
and the mini revalidation are retained as **provenance only** in the Appendix. The
standing warm-cache evidence is the **2026-07-26 warm-series revalidation**
(`results/feasibility-warm-series/`) on the redesigned driver — the batch-2 warm-series
it replaces is now provenance (§4.4).

## 1. Scope of this dataset

Batch 3 (CP-SPEND approved for batch 3; `--spend-cap-usd 30` enforced in-runner;
**actual realized $4.97** marginal across 28 known-cost legs). Collected on a **single
harness version** (product `2.1.220`; auto-approve tools; valid-UUID sessions;
`modelUsage` capture; per-run diff archiving; pilot-v2 contract; W1 `w1-v1`;
subject staged outside the lab repo). Output lives in `results/feasibility-batch3/`;
batch 1 (`results/feasibility/`) and batch 2 (`results/feasibility-batch2/`) are
**untouched** (clean per-batch spend-cap accounting, one harness version per dataset).

| Group | Cells | Runs |
|---|---|---|
| Controlled (Product A) | F1,F2,F3 × {P0, C2, P1} × 3 reps, cold | 27 |
| Cache warm-series | F1 × C1 (rep1 cold, reps 2–3 resumed) | 3 |
| **Total billable runs** | | **30** |

- **F1** = `pilot-realworld-draft-articles` — feature gate (pilot-v2).
- **F2** = `w4-realworld-missing-user-id` — bugfix gate (sealed-w4-v2).
- **F3** = `w1-realworld-mapper-tests` — **test-generation gate** (w1-v1; sealed
  mutation-catch, 10/10). **All three gate types are exercised.**
- **Product B (C3) and dual-bill (C5) are NOT in this batch** — deliberately dropped
  (see §1.2) and deferred to Phase 4 with the provider-side collector.
- **All 30 runs pass the event-log-derived validator** (`harness.telemetry.validate`,
  values re-derived from the immutable event log; **0 zero-fills**). The kill-switch
  never fired. 28 subject invocations exited 0; the 2 exit-1 cases are the warm-series
  resumed reps (§4.4) — subject-agent behaviour, not a harness crash: the runner
  captured the empty output, ran the gate, and wrote a valid summary with the affected
  fields marked `unavailable`.

## 1.1 Subject-isolation posture (recorded verbatim per run)

Batch 3 runs under the post-FIX-A–E posture. Every run stamps, authoritatively:

```
identity.permission_profile =
  "skip-all-tools; subject-staged-in-temp-outside-lab-repo;
   no-relative-path-to-canonical|hidden|task.yaml; harness-env-pointers-scrubbed;
   same-uid; no-container; no-fs-namespace; absolute-path-fs-access-NOT-confined;
   no-network-policy"
identity.network_policy = "no-network-policy"
```

(30/30, verbatim.) The subject tree is now staged in a fresh `/var/tmp/lab-subject-*`
directory **outside the lab repo**, with no relative path to `canonical/`, `hidden/`, or
`task.yaml`, and harness env pointers scrubbed from the agent environment (isolation
findings in `report/subject-isolation-leak-2026-07-26.md` /
`report/subject-isolation-verification.md`). The label is **honest**: it still records
`no-container`, `no-fs-namespace`, and `absolute-path-fs-access-NOT-confined` — this is
**not** full sandboxing. The deterministic gate remains containerized + `--network=none`.
**Full containerized-subject isolation AND endpoint-allowlist egress remain HARD
REQUIREMENTS for the Phase-4 screening CP-SPEND** (§6, condition 1) — this batch does
not satisfy them and does not claim to.

## 1.2 Why C3/C5 (Product B) were dropped from this batch

Product B (`agy`) exposes **no machine-readable usage** on a verified invocation
(observed 2026-07-26): its `--print` timeout confounded the smoke run and its version
drifted (`1.1.4 → 1.1.7`) during the work. Rather than spend on legs that would only
produce `unavailable` telemetry under an unstable adapter, Product B is deferred to
**Phase 4 with the provider-side (Vertex/console) collector**. It stays in the
**black-box / proxy tier** with documented limitations (SPEC narrow condition). No
Product-B claim is made here. The batch-2 C3/C5 legs (all `unavailable`) remain in the
Appendix as provenance.

## 2. Pass/fail criteria (protocol §"Pass/fail criteria")

| # | Criterion | Result | Verdict |
|---|---|---|---|
| 1 | Validator passes; zero zero-fills | **30/30** summaries + event logs valid via event-log re-derivation; **0 zero-fills**; **27/27** controlled | ✅ PASS |
| 2 | Cost reconstruction w/o self-report | **27/27** controlled runs costed from token metadata only (never `total_cost_usd`); every controlled usage field authoritative (C2/P0/P1 = 9/9 × 4 token classes); warm reps 2–3 `unavailable` and **enumerated, not zero-filled** | ✅ PASS |
| 3 | Harness stability | **0 harness crashes**; reset determinism identical (1 tree hash per task, all reps); gate reproducibility from the 10-point validations (canonical → same verdict, 3/3 tasks). 2 subject-agent exit-1 (warm resume) handled gracefully, not crashes (§4.4) | ✅ PASS |
| 4 | Escalation telemetry | **9/9** P1 runs record ITR + CR (both `economical`). No escalation *fired* — the economical tier (haiku-4-5) passed every task — so the failed-attempt-cost path carries **no live data this batch**. See §4.3 | ⚠️ PASS (routing recorded; escalation-cost path **not exercised**, §4.3) |
| 5 | Metric computability | ECST / QA-ECST-by-class compute **finite on every accepted controlled cell** (27/27 accepted, all three gate types); both cost views compute per leg/cell; **HEAC computes end-to-end** at $1.60/min (§5.1) | ✅ PASS |
| 6 | Human effort | 9/9 rubric timings recorded (single reviewer) and folded into each rep-1 run's `human_effort`; HEAC computes at $1.60/min (§5.1) | ✅ PASS — **n=1 reviewer** (inter-reviewer spread `unavailable`, not fabricated), **n=1 rep**, NON-COMPARATIVE; rubric `report/batch3/human-effort-rubric.md` |
| 7 | Cache | cold `cache_read` capture proven 27/27 + warm-series **costing delta** | ✅ PASS — cold capture 27/27 ✅; warm-series **delta demonstrated** on the redesigned driver (2026-07-26 revalidation, `results/feasibility-warm-series/`, authoritative warm cache tiers, marginal $ collapses on resume — §4.4). Batch-3 fresh-per-rep regression superseded |

**Stop condition (self-report):** NOT triggered — every controlled run's cost is
reconstructed from provider token metadata (`claude -p --output-format json` `usage` /
`modelUsage`), never from model self-report or estimates. (`total_cost_usd` is *recorded*
per leg for provenance in `invocation.txt` but is **not** the cost basis.)
**Narrow condition (partial telemetry):** TRIGGERED for Product B — deferred to Phase 4,
black-box/proxy tier (§1.2).

## 3. Per-configuration field availability

Token classes in the top-level `usage` view (n runs per tier; "auth" = authoritative,
from product JSON usage metadata):

| Config | Surface | input | output | cache_creation | cache_read | Cost |
|---|---|---|---|---|---|---|
| P0 (strong, `claude-sonnet-4-6@default`) | controlled_api | auth ×9 | auth ×9 | auth ×9 | auth ×9 | derived |
| C2 (economical, `claude-haiku-4-5@20251001`) | controlled_api | auth ×9 | auth ×9 | auth ×9 | auth ×9 | derived |
| P1 (cheap-first, economical leg = haiku-4-5) | controlled_api | auth ×9 | auth ×9 | auth ×9 | auth ×9 | derived (per leg) |
| C1 (strong, warm-series) | controlled_api | auth ×1 / **unavail ×2** | auth ×1 / **unavail ×2** | auth ×1 / **unavail ×2** | auth ×1 / **unavail ×2** | derived ×1 / **unavail ×2** |

The C1 `unavail ×2` are the resumed warm reps whose subject invocation returned **empty
stdout** (§4.4) — no usage JSON to parse — so all token classes and cost are
`unavailable`, never zeroed. `reasoning_tokens`, `tool_result_tokens`, `code_exec_*`,
`search_*` are `unavailable` on **all 30** runs (not separately exposed by the product
JSON) — recorded, never zero-filled. Cost is always `derived` (tokens × pinned prices
from `pricing/prices-2026-07-19.json`) or `unavailable`, never self-reported.

## 4. Key measurement findings (for CP-DATA)

### 4.1 Product A does not expose a concrete build behind a floating alias
P0/C1 runs meter `claude-sonnet-4-6@default` in `modelUsage` — the selector we
requested, not a dated build id. `@default` **cannot be pinned to a concrete version
from telemetry**; the floating-alias mitigation records the authoritative selector and
marks the concrete build `unavailable` (SPEC §6.3) — never inferred.

### 4.2 Product A uses an auxiliary model internally
Every P0 ("strong single-model") run meters **both** `claude-sonnet-4-6@default` **and**
`claude-haiku-4-5@20251001` in `modelUsage` (confirmed batch 3). Top-level `usage` is
priced at the leg's model rate; per-`modelUsage` cost splitting is a possible future
refinement (aux share small). Flagged, not silently absorbed. (C2/P1 economical runs
meter haiku only.)

### 4.3 Escalation observed as "no escalation"
All 9 P1 (cheap-first) runs recorded `intention_to_route = economical` and
`completed_route = economical`: the economical tier (haiku-4-5) **passed the gate on all
three tasks**, so the strong tier was never invoked and each run has a single
`economical_attempt` leg. The routing telemetry is captured on every run, but the
**failed-attempt / escalation-cost accumulation path carries no live data this batch**
(same as batch 2; it was exercised live in the batch-1 revalidation and by the dry-run
`escalate` stub). **Recommendation (carried to §6):** screening must include ≥1 task the
economical tier is expected to fail, to exercise real econ→strong escalation-cost
telemetry.

### 4.4 Cache — cold capture proven; warm-series regressed under fresh-per-rep staging
**Cold `cache_read` capture is proven**: all 27 controlled runs and C1 rep1 record
`cache_read` / `cache_creation` authoritatively and cost them cache-aware
(e.g. C1 rep1: cache_creation 69,316; cache_read 150,390; marginal $0.3219).

**The warm-series delta was NOT captured this batch — a regression from the isolation
harness change.** The warm protocol resumes rep1's session (`claude ... --resume
<session-id>`) for reps 2–3 to measure a warm prompt cache. Under batch 3's new posture,
each rep stages a **fresh subject tree in a new `/var/tmp/lab-subject-*` path**
(isolation FIX A). On resume, the model's carried-over conversation state indicates the
task is already complete, so both resumed reps returned **empty stdout, exit 1, and an
empty diff** → the gate correctly failed P1 (feature absent) and the usage/cost fields
are `unavailable` (not zeroed). Observed identically for C1 rep2 and rep3.

Consequence: the warm-cache **costing delta** was not demonstrated by batch 3 itself.
The batch-2 warm-series (captured cleanly on the pre-FIX harness) served as the
**interim** standing evidence — now **superseded** by the 2026-07-26 revalidation on the
redesigned driver (see Remediation status below). Batch-2 table retained as provenance
(marginal $ collapses on resume as `cache_creation` carries over):

| batch-2 rep (provenance) | cache_state | cache_creation | cache_read | marginal $ |
|---|---|---|---|---|
| 1 | cold | 7,537 | 221,969 | 0.1145 |
| 2 | warm (resumed) | 3,479 | 250,463 | 0.0817 |
| 3 | warm (resumed) | 2,623 | 177,977 | 0.1069 |

**Remediation (carried to §6):** the warm-series protocol must be redesigned to be
compatible with fresh-per-rep staging — e.g. a two-turn single-session measurement, or
resuming within a persisted staged tree — before warm-cache costing can be claimed under
the current isolation posture. This is a **narrow** methodology gap, not a stop
condition: cost reconstruction without self-report holds for every cold run.

**Remediation status (2026-07-26):** the persisted-staged-tree redesign is
**implemented as a no-spend change** — `harness/runner/warm_series.py` stages the
subject tree ONCE per series, reuses that path across all reps, resets the tree in
place between reps (deterministic; `node_modules` preserved), keeps the prompt
byte-identical, and cleans up once. It preserves the FIX-A isolation guarantee (staged
outside the lab repo; no relative traversal to canonical/hidden) and is covered by
stub/dry-run tests. Its **live validation is a single 3-run attempt gated at the
warm-series CP-SPEND** (`manifest/cp-spend-warm-series-plan.md`, cap $3), with a
**one-attempt stopping rule recorded before the run**: if reset+resume yields gradable
work, criterion 7 returns to full pass; if it no-ops again, that is recorded as a
methodology finding (session resume and tree reset are incompatible), criterion 7 stays
**PARTIAL** with the limitation documented, and warm-cache measurement design moves to
Phase 4 — **no second attempt, no prompt modification to force success**. Until that
attempt runs, criterion 7 remains PARTIAL and **no warm-cache costing delta is claimed
under the batch-3 posture**.

**Outcome (2026-07-26, `results/feasibility-warm-series/`) — GRADABLE WORK; criterion 7
→ PASS.** The single approved 3-run series (F1 × C1, cap $3; realized **$0.5450**) ran on
the redesigned driver (product `2.1.220`, host-staged FIX-A posture). Reps 2–3 resumed
the same session on the same persisted staged path (reset to the identical tree hash
`b76a4619…` every rep) and produced **non-empty, gate-graded, accepted** diffs (all three
`agent-solution.diff` byte-identical, md5 `9beaf1bb…`) — **not** the batch-3 no-op. Warm
`cache_read` / `cache_creation` are authoritative and the warm **costing delta** is
demonstrated (marginal $ collapses on resume as `cache_creation` carries over):

| warm-series rep (authoritative) | cache_state | cache_creation | cache_read | marginal $ |
|---|---|---|---|---|
| 1 | cold | 69,557 | 113,041 | 0.3128 |
| 2 | warm (resumed) | 3,988 | 243,706 | 0.1084 |
| 3 | warm (resumed) | 2,995 | 308,011 | 0.1239 |

This series is the **standing warm-cache evidence**, collected as its own dataset (NOT
pooled with the batch-3 controlled 27). The reset-based warm protocol is confirmed
compatible with the FIX-A posture; §6 condition 2 is cleared. (Per the pre-registered
stopping rule this is the single attempt — no re-run. The Phase-4 SPEC-amendment open
question in §9 of the CP-SPEND package — same-task/reset-tree vs. real multi-task warm
sessions — is unaffected by this result.)

### 4.5 Acceptance (instrument data, NON-COMPARATIVE)
**27/27 controlled Product-A runs accepted** (P0/C2/P1 × F1/F2/F3, 3/3 each) — the
pilot-v2 contract + w1-v1 sealed gate grade real solutions cleanly. The only rejections
are the 2 warm-resume reps (empty diff, §4.4), which are a warm-protocol artifact, not a
solution-quality or harness result. This is an *instrument* result, not a skill
comparison.

**W4 (F2) note — byte-identity is uninformative as a leak test here.** All nine F2
(`w4-realworld-missing-user-id`) runs (P0/C2/P1 × 3 reps) produced an
`agent-solution.diff` **byte-identical to the canonical patch** (md5 `9f66c261…`,
verified across all nine and against
`tasks/suite/W4-complex-bugfix/canonical/fix-missing-user-id.patch`). This is expected,
not suspicious: the correct minimal fix is a **single line** (add `id: true` to the
`select` in `getCurrentUser`), so there is essentially one correct minimal form for it to
converge on. **P5-no-leakage passed on all nine** (no canonical patch / solution markers
in the participant tree). For a one-line fix in a `famous`-tier repo (§4.1 / SPEC §6.3;
`tasks/WORKLOAD-SELECTION.md`), **byte-identity to canonical carries no signal about
leakage** — a legitimately-solved one-liner and a memorized one look the same at the byte
level. We therefore rely on P5's tree-marker check (which passed) and on the famous-tier
memorization caveat — a class-level claim still requires the second, materially different
`obscure`/`post_cutoff` companion task — **not** on diff-identity, for this cell.

**Consequence for human effort (criterion 6, §6 condition 3).** Because the W4 diff is
identical across all nine runs, the **three W4 review cells (F2·P0, F2·C2, F2·P1) present
reviewers with the same patch**. Per-cell human-effort (HEAC) timings for those three
cells therefore carry an **order effect**: a reviewer who has already read the identical
diff in one cell reviews it faster in the next. When the criterion-6 subset is collected,
**record review order for the W4 cells** and interpret any cross-cell HEAC difference among
F2·P0/F2·C2/F2·P1 as confounded by that order effect, not as a cell-level effort signal.

## 5. Metric computability & per-cell dispersion

All controlled metrics compute end-to-end from the 27 runs (non-comparative, internal):
- **ECST / QA-ECST**: **finite on every accepted controlled cell** (Σ attempt cost ÷
  accepted). Values below.
- **HEAC**: **computes end-to-end** at `loaded_rate_per_minute = $1.60/min` on all nine
  controlled cells (criterion 6 recorded, §5.1).
- **Both cost views** (marginal_operating, fully_allocated) compute per leg/cell.

Per-cell **marginal cost** (median / min–max, n=3) and ECST (accepted-only). With n=3
per cell the IQR is not separately reported (ill-defined at n=3); min–max bounds the
spread. Full cost stats in `results/feasibility-batch3/aggregate-noncomparative.json`;
full ECST/HEAC bundle in `results/feasibility-batch3/metrics-noncomparative.json`.

| Cell | median $ | range $ | acc | ECST $ |
|---|---|---|---|---|
| F1·P0 | 0.2360 | 0.206–0.244 | 3/3 | 0.2287 |
| F1·C2 | 0.0681 | 0.042–0.068 | 3/3 | 0.0594 |
| F1·P1 | 0.0418 | 0.042–0.044 | 3/3 | 0.0424 |
| F1·C1 (warm-series) | 0.3219 (rep1 only) | rep2–3 unavailable (batch-3 regression; revalidated separately — §4.4) | 1/3 | 0.3219 |
| F2·P0 | 0.2414 | 0.236–0.499 | 3/3 | 0.3254 |
| F2·C2 | 0.0722 | 0.037–0.108 | 3/3 | 0.0721 |
| F2·P1 | 0.0461 | 0.012–0.062 | 3/3 | 0.0400 |
| F3·P0 | 0.4306 | 0.358–0.625 | 3/3 | 0.4713 |
| F3·C2 | 0.0932 | 0.092–0.148 | 3/3 | 0.1111 |
| F3·P1 | 0.1966 | 0.132–0.265 | 3/3 | 0.1978 |

**Rep-count implication:** consistent with batch 2, the **strong single-model P0 cells
are the widest** — F2·P0 (0.236–0.499) and F3·P0 (0.358–0.625) each have one ~2× rep;
economical (C2) and cheap-first (P1) cells are tighter. **Recommendation:** for
screening, budget **≥5 reps on strong / cold-sensitive cells** (P0, C1) and report
medians with min–max/IQR (not means); 3 reps suffice for economical/cheap-first cells.
Re-assess after screening scale.

## 5.1 HEAC (human-effort-adjusted cost) — criterion 6

HEAC = ECST + (active + review + correction minutes) × `loaded_rate_per_minute`
(**$1.60/min**, a DECLARED manifest input — NOT a measurement, SPEC §1.2). The minutes
are the single-reviewer stopwatch timings recorded in
`report/batch3/human-effort-rubric.md` (review order 1,4,7,2,5,8,3,6,9), folded into each
rep-1 run's `human_effort` slot (authoritative tier); full bundle in
`results/feasibility-batch3/metrics-noncomparative.json`.

**Scope — attaches to every HEAC figure below:** **n=1 reviewer** (single-operator
deployment; **inter-reviewer spread is `unavailable`** — recorded as such, never
fabricated), **n=1 rep** per cell (rep 1 only), **NON-COMPARATIVE / internal-only**. HEAC
is a *feasibility* result (the metric computes end-to-end), not a configuration ranking.

| Cell | ECST $ (model) | review+corr min | HEAC $ | reviewer verdict |
|---|---|---|---|---|
| F1·P0 | 0.2287 | 3.5 | 5.83 | would-merge |
| F1·C2 | 0.0594 | 3.0 | 4.86 | would-merge |
| F1·P1 | 0.0424 | 1.5 | 2.44 | would-merge |
| F2·P0 | 0.3254 | 2.0 | 3.53 | would-merge |
| F2·C2 | 0.0721 | 1.0 | 1.67 | would-merge |
| F2·P1 | 0.0400 | 1.0 | 1.64 | would-merge |
| F3·P0 | 0.4713 | 7.0 | 11.67 | would-merge |
| F3·C2 | 0.1111 | 15+18 | 52.91 | **would-not-merge** (gate: accepted) |
| F3·P1 | 0.1978 | 18+20 | 61.00 | **would-not-merge** (gate: accepted) |

(F1·C1 warm-series: HEAC `unavailable` — the warm reps were not human-reviewed.)

**Gate ≠ reviewer (rows F3·C2, F3·P1).** All nine runs are **gate-accepted** — the
deterministic gate passed. On the two F3 (W1 test-generation) economical/cheap-first
cells the reviewer judged the produced test suite **would-not-merge as-is** (≈490–550
lines, repetitive fixtures, weak scope discipline) and estimated 18 and 20 min of
correction. That is a **reviewer verdict** (stored in `human_effort.reviewer_verdict`),
**NOT a gate outcome** — each run's `acceptance.result` remains `accepted`. The correction
minutes flow into HEAC, which is why those two cells dominate.

**Finding (feasibility, non-comparative):** at $1.60/min the **human term dominates HEAC**
— review/correction dollars swamp the model's cents (e.g. F3·P1: $0.20 model vs. $61
total). HEAC is finite on every accepted controlled cell; criterion 6 is satisfied as an
*instrument* result at the scope above.

## 6. Go / No-Go

**Instrument VALIDATED on the authoritative controlled dataset (27/27), on a single
fixed harness version, under an honestly-labelled isolation posture.** All three gate
types exercised; validator-passing telemetry with zero zero-fills; cost reconstructed
without self-report. **GO for Phase 4 screening _design_.** Screening _runs_ remain
gated on the conditions below and at CP-SCREEN-PREREG / the screening CP-SPEND.

**Conditions before screening runs execute:**
1. **Containerized-subject isolation AND endpoint-allowlist egress (MANDATORY at the
   Phase-4 screening CP-SPEND).** Batch 3 ran host-staged (§1.1); screening must run
   subjects in a real sandbox with restricted egress (bake `claude`/`agy` + mount ADC +
   Vertex env + egress allowlist for the agent leg; gate stays `--network=none`).
2. **Warm-series protocol redesign (§4.4) — CLEARED (2026-07-26).** The resume-based
   warm measurement was incompatible with fresh-per-rep staging; the persisted-staged-tree
   redesign (`harness/runner/warm_series.py`) was validated in the single approved 3-run
   series (`results/feasibility-warm-series/`, $0.5450): reps 2–3 produced gate-accepted
   diffs with authoritative warm cache tiers and a costed delta. Criterion 7 → PASS.
   (Not a screening precondition anymore.)
3. **Criterion 6 (human-effort subset) — CLEARED (2026-07-26).** The 9-run rubric
   timings are recorded (single reviewer) and folded into each rep-1 run's
   `human_effort`; HEAC computes end-to-end at $1.60/min (§5.1). **Inter-reviewer spread
   is `unavailable`** — single-operator deployment, recorded not fabricated; a second
   reviewer remains desirable at screening scale but is not a blocking precondition.
4. **Escalation-cost coverage (§4.3)** — include ≥1 screening task the economical tier
   is expected to fail, so real econ→strong escalation cost is captured.
5. **Rep count** raised per §5 for strong/cold-sensitive cells (≥5).
6. **Product B** re-enters at Phase 4 with the provider-side collector; stays in the
   black-box / proxy tier with documented limitations (§1.2).

**Spend note:** batch 3 cost **$4.97** (well under the $30 ceiling) and produced a
validator-passing 30-run dataset (27 controlled accepted).

## 7. What CP-DATA gates

The measurement system is validated on the authoritative batch-3 dataset (full 27
controlled, three gate types, validator-passing telemetry, honest
unavailable-not-zero handling, honest isolation labelling). Both previously-open criteria
are now **cleared**: the **warm-series delta** (criterion 7) by the 2026-07-26
revalidation (§4.4), and the **human-effort subset** (criterion 6) by the recorded 9-run
rubric + HEAC computation (§5.1, at n=1 reviewer / n=1 rep, non-comparative). All
feasibility criteria on the authoritative batch-3 dataset are satisfied. CP-DATA
acceptance clears the **telemetry-completeness** requirement for the controlled
instrument and unblocks Phase 4 **screening design**, subject to the §6 conditions
(gated at CP-SCREEN-PREREG and the screening CP-SPEND, not here). **No number in this
report appears in any docs / site / public report until CP-FINDINGS.** All figures are
internal, NON-COMPARATIVE feasibility telemetry.

## Appendix — batch-2, batch-1 + revalidation provenance (superseded)

Retained for audit; **not** the authoritative controlled dataset.

- **Batch 2 (34 runs, $4.13, 2026-07-20):** the prior authoritative dataset — 27
  controlled + 4 product companions (C3/C5, all Product-B legs `unavailable`) + 3
  warm-series, collected on the pre-isolation-FIX harness (`cwd-confined-.work-repo`
  host posture). Superseded by batch 3 for the controlled instrument because the harness
  changed materially (FIX A–E). **Its warm-series (table in §4.4) is carried forward as
  the standing warm-cache evidence**, since batch 3's warm-series regressed. Batch-2 C5
  showed dual-leg aggregation cost the conductor (Product A) leg precisely ($0.216 /
  $0.316) with the executor (Product B) leg and `frontier_token_share` correctly
  `unavailable` — retained as the C5 aggregation provenance for Phase 4.
- **Batch 1 (25 runs, $5.23, 2026-07-19):** 0/25 accepted — root-caused to a harness
  defect (headless CLIs invoked without tool auto-approval → silent Edit/Write denial →
  empty diff → gate correctly reports feature absent). All 25 classified NO_WRITE. Fixes:
  `--dangerously-skip-permissions` (both adapters); agy `--model <verbatim>` (not
  `--select`); valid-UUID sessions; `num_turns`/`permission_denials`/`is_error` recorded.
- **Revalidation (4 runs, $1.38):** confirmed the fix — 8–20 agentic turns, 0 permission
  denials, non-empty diffs, 1 accepted (F2·C2), 3 WRONG_SOLUTION (real diffs, treated as
  findings not defects). A **gate-fairness audit** (`report/gate-fairness-audit.md`)
  classified F1·P1·rep1 as a shape mismatch (case ii) and remedied the **task, not the
  gate** (pilot-v1 → pilot-v2; sealed hash unchanged). Per-run `agent-solution.diff`
  archiving is now wired. Full history in git.
