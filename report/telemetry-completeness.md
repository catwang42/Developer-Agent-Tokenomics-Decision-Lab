# Telemetry-completeness report — Phase 3 feasibility (batch 2, AUTHORITATIVE)

Prepared for **CP-DATA** (CLAUDE.md; SPEC §2.3; binding protocol
`methodology/feasibility-protocol.md`). This document reports whether the
**measurement system works** — it makes **no vendor-comparative claims** and all
metric outputs are **NON-COMPARATIVE, internal-only** (SPEC §1.2 claims register).

Batch 2 is the authoritative feasibility dataset. Batch 1 (25 NO_WRITE runs) and the
mini revalidation are retained only as defect-provenance and are summarized in the
Appendix; they are **superseded** by the numbers here.

## 1. Scope of this dataset

Batch 2 (CP-SPEND approved 2026-07-20; $30 cap enforced in-runner via
`--spend-cap-usd`; **actual realized $4.13** marginal + 4 Product-B legs whose cost is
`unavailable`). Collected on the fixed harness (auto-approve tools; valid-UUID
sessions; `modelUsage` capture; per-run diff archiving; pilot-v2 contract; W1 `w1-v1`).
Outputs live in `results/feasibility-batch2/` (batch-1 preserved untouched).

| Group | Cells | Runs |
|---|---|---|
| Controlled (Product A) | F1,F2,F3 × {P0, C2, P1} × 3 reps, cold | 27 |
| Product companions | F1 × {C3, C5} × 2 reps, cold | 4 |
| Cache warm-series | F1 × C1 (rep1 cold, reps 2–3 resumed) | 3 |
| **Total billable runs** | | **34** |

- **F1** = `pilot-realworld-draft-articles` — feature gate (pilot-v2).
- **F2** = `w4-realworld-missing-user-id` — bugfix gate (sealed-w4-v2).
- **F3** = `w1-realworld-mapper-tests` — **test-generation gate** (w1-v1; sealed
  mutation-catch, 10/10). **All three gate types are now exercised** — the batch-1
  gap is closed.
- **All 34 runs exited 0 and pass the event-log-derived validator** (values
  re-derived from the immutable event log); the kill-switch never fired.

## 1.1 Subject-isolation posture (recorded verbatim per run)

Per the CP-SPEND resolution (2026-07-20, decision 4 + the containerization-gap
finding): the containerized **live-agent leg is unimplemented** (`Dockerfile.subject`
bakes no `claude`/`agy`; `resolve_spawn` passes the agent-leg container no creds/egress)
— that is new engineering, so batch 2 ran **`--subject-isolation host`**. Every run
stamps, authoritatively:
`identity.permission_profile = "skip-all-tools; cwd-confined-.work-repo; dev-vm; no-container; no-network-policy"`
and `identity.network_policy = "no-network-policy"` (34/34, verbatim). The deterministic
gate remains containerized + `--network=none` (verified offline). **Full containerized-
subject isolation AND endpoint-allowlist egress are HARD REQUIREMENTS for the Phase-4
screening CP-SPEND** (§6).

## 2. Pass/fail criteria (protocol §"Pass/fail criteria")

| # | Criterion | Result | Verdict |
|---|---|---|---|
| 1 | Validator passes; zero zero-fills | **34/34** summaries + event logs valid; 0 zero-fills; **27/27** controlled | ✅ PASS |
| 2 | Cost reconstruction w/o self-report | **34/34** costed from token metadata only (never `total_cost_usd`); every Product-A usage field authoritative; Product-B unavailable fields enumerated, not silently absent | ✅ PASS |
| 3 | Harness stability | **0 crashes** (34/34 exit 0); reset determinism identical (1 tree hash per task, 3/3); gate reproducibility from the 10-point validations (canonical → same verdict, 3/3 tasks) | ✅ PASS |
| 4 | Escalation telemetry | **9/9** P1 runs record ITR + CR (both `economical`). No escalation *fired* — the economical tier (haiku-4-5) passed every task — so the failed-attempt-cost path carries no live data **this batch**; it was exercised live in revalidation (P1 econ→strong) and by the dry-run stub. See §4.4 | ✅ PASS (routing recorded; escalation-cost path flagged, §4.4) |
| 5 | Metric computability | ECST / QA-ECST-by-class compute **finite on accepted runs across all three gate types** (30/30 controlled accepted); both cost views compute per leg/cell. HEAC pending criterion 6 | ✅ PASS |
| 6 | Human effort | rubric timings for the 9-run subset | ⏳ **PENDING** (human reviewers; scheduled immediately post-batch; not fabricated) |
| 7 | Cache | warm-series shows cache_read capture + cache_creation collapse on resume + cache-aware costing | ✅ PASS |

**Stop condition (self-report):** NOT triggered — every controlled run's cost is
reconstructed from provider token metadata (`claude -p --output-format json` `usage`),
never from model self-report or estimates. (`total_cost_usd` is *recorded* for
provenance but is **not** the cost basis.)
**Narrow condition (partial telemetry):** TRIGGERED for Product B (C3 / C5 executor)
— it stays in the **proxy/black-box tier** with the §4 limitations.

## 3. Per-configuration field availability

Token classes in the top-level `usage` view (n runs per tier):

| Config | Surface | input | output | cache_creation | cache_read | Cost |
|---|---|---|---|---|---|---|
| P0 (strong, Product A) | controlled_api | auth ×9 | auth ×9 | auth ×9 | auth ×9 | derived |
| C2 (economical, Product A) | controlled_api | auth ×9 | auth ×9 | auth ×9 | auth ×9 | derived |
| P1 (cheap-first, Product A) | controlled_api | auth ×9 | auth ×9 | auth ×9 | auth ×9 | derived (per leg) |
| C1 (strong, warm-series) | controlled_api | auth ×3 | auth ×3 | auth ×3 | auth ×3 | derived |
| C5 conductor (Product A) | controlled_api | auth ×2 | auth ×2 | auth ×2 | auth ×2 | derived |
| C5 executor (Product B) | product_blackbox | **unavail ×2** | **unavail ×2** | **unavail ×2** | **unavail ×2** | **unavailable** |
| C3 (Product B) | product_blackbox | **unavail ×2** | **unavail ×2** | **unavail ×2** | **unavail ×2** | **unavailable** |

"auth" = authoritative (from product JSON usage metadata). `reasoning_tokens`,
`tool_result_tokens`, `code_exec_*`, `search_*` are `unavailable` on **all 34**
configs (not separately exposed by the product JSON) — recorded, never zero-filled.
Cost is always `derived` (tokens × pinned prices from `pricing/prices-2026-07-19.json`)
or `unavailable`, never self-reported.

## 4. Key measurement findings (for CP-DATA)

1. **Product A does not expose a concrete build behind a floating alias.** P0/C1/C5-
   conductor runs meter `claude-sonnet-4-6@default` in `modelUsage` — the selector we
   requested, not a dated build id. `@default` **cannot be pinned to a concrete version
   from telemetry**; the floating-alias mitigation records the authoritative selector
   and marks the concrete build `unavailable` (SPEC §6.3) — never inferred.
2. **Product A uses an auxiliary model internally.** Every P0/C1 ("strong single-model")
   run meters both `claude-sonnet-4-6@default` **and** `claude-haiku-4-5@20251001` in
   `modelUsage`. Top-level `usage` is priced at the leg's model rate; per-`modelUsage`
   cost splitting is a possible future refinement (aux share small). Flagged, not
   silently absorbed.
3. **Product B telemetry is partial (as expected).** C3 and the C5 executor expose **no
   token counts** → cost `unavailable` (missing classes enumerated, never zeroed). The
   verbatim selector label **`"Gemini 3.5 Flash (High)"`** is recorded at
   `proxy_observed`; the backend model id is never inferred.
4. **Escalation observed as "no escalation".** All 9 P1 (cheap-first) runs recorded
   `intention_to_route = economical` and `completed_route = economical`: the economical
   tier (haiku-4-5) **passed the gate on all three tasks**, so the strong tier was never
   invoked. The routing telemetry is captured on every run, but the **failed-attempt /
   escalation-cost accumulation path carries no live data this batch**. It was exercised
   live in revalidation (a real econ→strong escalation with both-leg costs) and by the
   dry-run `escalate` stub. **Recommendation:** screening should include ≥1 task the
   economical tier is expected to fail, to exercise real escalation-cost telemetry.
5. **Dual-bill (C5) captures the frontier leg precisely; no fabricated ratio.** The
   conductor (Product A) leg is fully costed ($0.316 and $0.216 across the two reps,
   4-class component breakdown); the executor (Product B) leg is `unavailable`; the
   top-level cost is correctly `unavailable` (mixed basis) and `frontier_token_share`
   is `unavailable` (cannot compute without executor tokens).
6. **Acceptance (instrument data, NON-COMPARATIVE).** 32/34 accepted. All **30 controlled
   Product-A runs accepted** (P0/C2/P1 × F1/F2/F3, 3/3 each) — the pilot-v2 contract +
   w1-v1 sealed gate grade real solutions cleanly. The 2 rejections are both F1·C3
   (Product B); real black-box outcomes, not harness defects. This is an *instrument*
   result, not a skill comparison.
7. **Cache carryover is real (criterion 7).** Warm-series C1:

   | rep | cache_state | cache_creation | cache_read | marginal $ |
   |---|---|---|---|---|
   | 1 | cold | 7,537 | 221,969 | 0.1145 |
   | 2 | warm (resumed) | 3,479 | 250,463 | 0.0817 |
   | 3 | warm (resumed) | 2,623 | 177,977 | 0.1069 |

   Resumed runs collapse cache-*creation* (7,537 → 3,479 → 2,623) — the provider prompt
   cache carried over — and the runner captures + costs it cache-aware. This is the
   ex120 teaching input.

## 5. Metric computability & per-cell dispersion

All metrics compute end-to-end from the 34 runs (non-comparative, internal):
- **ECST / QA-ECST**: **finite on every accepted controlled cell** (Σ attempt cost ÷
  accepted). Values below.
- **HEAC**: `unavailable` until the criterion-6 human subset lands.
- **Both cost views** (marginal_operating, fully_allocated) compute per leg/cell.

Per-cell **marginal cost** (median / IQR / min–max, n=3) and ECST (accepted-only):

| Cell | median $ | IQR $ | range $ | acc | ECST $ |
|---|---|---|---|---|---|
| F1·P0 | 0.2037 | 0.2239 | 0.117–0.341 | 3/3 | 0.2202 |
| F1·C2 | 0.0446 | 0.0383 | 0.034–0.073 | 3/3 | 0.0506 |
| F1·P1 | 0.0406 | 0.0133 | 0.035–0.048 | 3/3 | 0.0410 |
| F1·C1 (warm-series) | 0.1102 | 0.0327 | 0.082–0.115 | 3/3 | 0.1021 |
| F1·C5 (n=2, dual-bill) | conductor $0.216–0.316 | — | executor unavailable | 2/2 | n/a (mixed basis) |
| F1·C3 (n=2, Product B) | unavailable | — | unavailable | 0/2 | undefined (0 accepted) |
| F2·P0 | 0.1841 | 0.2304 | 0.174–0.404 | 3/3 | 0.2538 |
| F2·C2 | 0.1111 | 0.0569 | 0.093–0.150 | 3/3 | 0.1180 |
| F2·P1 | 0.0478 | 0.0233 | 0.034–0.057 | 3/3 | 0.0465 |
| F3·P0 | 0.2840 | 0.1058 | 0.277–0.383 | 3/3 | 0.3144 |
| F3·C2 | 0.1450 | 0.0576 | 0.090–0.148 | 3/3 | 0.1279 |
| F3·P1 | 0.1007 | 0.0257 | 0.092–0.118 | 3/3 | 0.1034 |

**Rep-count implication:** dispersion is far tighter than batch 1, but the **strong
single-model P0 cells remain the widest** (F1·P0 and F2·P0 each have IQR ≈ median,
driven by one ~2× rep). Economical (C2) and cheap-first (P1) cells are tight
(IQR ≪ median). **Recommendation:** for screening, budget **≥5 reps on strong /
cold-sensitive cells** (P0, C1) and report medians with IQR (not means); 3 reps
suffice for economical/cheap-first cells. Re-assess after screening scale.

## 6. Go / No-Go

**Instrument VALIDATED on the authoritative full-27 dataset.** All three gate types
exercised; 30/30 controlled Product-A runs accepted; every telemetry criterion PASS
except the human-effort subset (6, pending). **GO for Phase 4 screening _design_**;
screening _runs_ remain gated on the conditions below and at CP-SCREEN-PREREG.

**Conditions before screening runs execute:**
1. **Containerized-subject isolation AND endpoint-allowlist egress (MANDATORY at the
   Phase-4 screening CP-SPEND).** Batch 2 ran host-isolated (§1.1) because the
   containerized agent leg is unimplemented; screening's larger/longer batch must run
   subjects in a real sandbox with restricted egress (bake `claude`/`agy` + mount ADC +
   Vertex env + egress network for the agent leg; gate stays `--network=none`).
2. **Criterion 6 (human-effort subset)** — reviewers record 9-run rubric timings +
   inter-reviewer spread (no model spend). HEAC stays `unavailable` until then.
3. **Escalation-cost coverage** — include ≥1 screening task the economical tier is
   expected to fail, so real econ→strong escalation cost is captured (§4.4).
4. **Rep count** raised per §5 for strong/cold-sensitive cells (≥5).
5. Product B remains in the **black-box / proxy tier** with the §4 limitations.

**Spend note:** batch 2 cost **$4.13** (well under the $30 ceiling) and produced a
clean, fully validated 34-run dataset.

## 7. What CP-DATA gates

The measurement system is validated on the authoritative dataset (full 27 + companions,
three gate types, validator-passing telemetry, honest unavailable-not-zero handling). CP-DATA
acceptance clears the **telemetry-completeness** requirement and unblocks Phase 4
**screening design**, subject to the §6 conditions (containerization + egress, human-
effort subset, escalation coverage, rep count) — which are gated at CP-SCREEN-PREREG and
the screening CP-SPEND, not here. **No number in this report appears in any docs / site /
public report until CP-FINDINGS.** All figures are internal, NON-COMPARATIVE feasibility
telemetry.

## Appendix — batch-1 + revalidation provenance (superseded)

Retained for audit; **not** valid task outcomes.

- **Batch 1 (25 runs, $5.23, 2026-07-19):** 0/25 accepted — root-caused to a harness
  defect (headless CLIs invoked without tool auto-approval → silent Edit/Write denial →
  empty diff → gate correctly reports feature absent). All 25 classified NO_WRITE. Fixes:
  `--dangerously-skip-permissions` (both adapters); agy `--model <verbatim>` (not
  `--select`); valid-UUID sessions; `num_turns`/`permission_denials`/`is_error` recorded.
- **Revalidation (4 runs, $1.38):** confirmed the fix — 8–20 agentic turns, 0 permission
  denials, non-empty diffs, **1 accepted** (F2·C2), 3 WRONG_SOLUTION (real diffs, treated
  as findings not defects). A **gate-fairness audit** (`report/gate-fairness-audit.md`,
  CP-DATA condition 1) classified F1·P1·rep1 as a shape mismatch (case ii) and remedied
  the **task, not the gate** (pilot-v1 → pilot-v2; sealed hash unchanged). The two F1·P0
  diffs were not archived pre-fix; per-run `agent-solution.diff` archiving is now wired,
  and they are re-classifiable from batch-2 provenance if needed. Full history in git.
