# Telemetry-completeness report — Phase 3 feasibility (batch 1)

Prepared for **CP-DATA** (CLAUDE.md; SPEC §2.3; binding protocol
`methodology/feasibility-protocol.md`). This document reports whether the
**measurement system works** — it makes **no vendor-comparative claims** and all
metric outputs are **NON-COMPARATIVE, internal-only** (SPEC §1.2 claims register).

## 1. Scope of this dataset

Batch 1 (CP-SPEND approved 2026-07-19, option (a): $60 cap enforced in-runner).
Run commit `d3e1b99`+ (harness through `e1ce9e9`); task suite `17b9990`.

| Group | Cells | Runs |
|---|---|---|
| Controlled (Product A) | F1,F2 × {P0, C2, P1} × 3 reps, cold | 18 |
| Product companions | F1 × {C3, C5} × 2 reps, cold | 4 |
| Cache warm-series | F1 × C1 (rep1 cold, reps 2–3 resumed) | 3 |
| **Total billable runs** | | **25** |

- **F1** = `pilot-realworld-draft-articles` (feature_implementation gate).
- **F2** = `w4-realworld-missing-user-id` (repro/bug_fix gate).
- **F3** (W1 test-generation gate) is **deferred to batch 2** (its own mini
  CP-SPEND), per the approved decision. This report therefore covers **18 of the
  27 controlled runs and 2 of the 3 gate types**; the full-27 / third-gate-type
  go/no-go completes only after batch 2.
- **Total realized spend: $5.23** (marginal, event-log-derived; global endpoint).
  Well under the $60 ceiling; the kill-switch never needed to fire.

## 2. Pass/fail criteria (protocol §"Pass/fail criteria")

| # | Criterion | Result | Verdict |
|---|---|---|---|
| 1 | Validator passes; zero zero-fills | **25/25** summaries + event logs valid; 0 zero-fills | ✅ PASS |
| 2 | Cost reconstruction w/o self-report | **25/25** costed from token metadata only; C1/C2 every usage field authoritative; product unavailable fields enumerated | ✅ PASS |
| 3 | Harness stability | **0 crashes**; reset determinism identical (F1: 1 hash/16 runs, F2: 1 hash/9); gate reproducibility from Phase 2 validation reports | ✅ PASS |
| 4 | Escalation telemetry | **6/6** P1 runs record ITR + CR + both leg costs incl. failed attempt | ✅ PASS |
| 5 | Metric computability | ECST, QA-ECST-by-class, HEAC, both cost views compute end-to-end (`harness/evaluator/metrics.py`) | ✅ PASS |
| 6 | Human effort | rubric timings for the 9-run subset | ⏳ **PENDING** (human reviewer time; not fabricated) |
| 7 | Cache | warm-series shows cache_read capture + costing delta vs naive | ✅ PASS |

**Stop condition (self-report):** NOT triggered — every controlled run's cost is
reconstructed from provider token metadata (`claude -p --output-format json`
`usage`), never from model self-report or estimates.
**Narrow condition (partial telemetry):** TRIGGERED for Product B (C3/C5 executor)
— it stays in the **proxy/black-box tier** with the documented limitations in §4.

## 3. Per-configuration field availability

Token classes in the top-level `usage` view (n runs per tier):

| Config | Surface | input | output | cache_creation | cache_read | Cost |
|---|---|---|---|---|---|---|
| P0 (strong, Product A) | controlled_api | auth ×6 | auth ×6 | auth ×6 | auth ×6 | derived |
| C2 (economical, Product A) | controlled_api | auth ×6 | auth ×6 | auth ×6 | auth ×6 | derived |
| P1 (cheap-first, Product A) | controlled_api | auth ×6 | auth ×6 | auth ×6 | auth ×6 | derived (2 legs) |
| C1 (strong, warm-series) | controlled_api | auth ×3 | auth ×3 | auth ×3 | auth ×3 | derived |
| C5 conductor (Product A) | controlled_api | auth | auth | auth | auth | derived |
| C5 executor (Product B) | product_blackbox | **unavail** | **unavail** | **unavail** | **unavail** | **unavailable** |
| C3 (Product B) | product_blackbox | **unavail** | **unavail** | **unavail** | **unavail** | **unavailable** |

"auth" = authoritative (from product JSON usage metadata). `reasoning_tokens` /
`tool_result_tokens` are `unavailable` on all configs (not separately exposed) —
recorded, never zero-filled. Cost is always `derived` (from tokens × pinned
prices) or `unavailable`, never self-reported.

## 4. Key measurement findings (for CP-DATA)

1. **Product A does not expose a concrete build behind a floating alias.**
   `claude -p --output-format json` reports usage keyed (in `modelUsage`) by the
   *selector we requested* — e.g. a P0 run returns `claude-sonnet-4-6@default`,
   not a dated build id. So `@default` **cannot be pinned to a concrete version
   from telemetry**. The floating-alias mitigation records what the product does
   expose (the selector, authoritative) but the concrete build is **unavailable**
   — a reproducibility caveat carried per run, not an inference (SPEC §6.3).
2. **Product A uses an auxiliary model internally.** P0/C1 ("strong single-model")
   runs meter both `claude-sonnet-4-6@default` **and** `claude-haiku-4-5@20251001`
   in `modelUsage`. The top-level `usage` object is priced at the leg's model
   rate; per-model cost splitting via `modelUsage` is a possible future refinement
   (the aux share is small). Flagged, not silently absorbed.
3. **Product B telemetry is partial (as expected).** C3 and the C5 executor expose
   **no token counts** → cost `unavailable` (enumerated missing classes, never
   zeroed). The verbatim selector label (`"Gemini 3.5 Flash (High)"`) is recorded
   at `proxy_observed`; the backend model id is never inferred.
4. **Dual-bill (C5) captures the frontier leg precisely.** The conductor (Product
   A) leg is fully costed ($0.337 with a 4-class component breakdown); the executor
   (Product B) leg is `unavailable`; the top-level cost is correctly
   `cost_unavailable` (mixed basis) and `frontier_token_share` is `unavailable`
   (cannot compute without executor tokens) — no fabricated ratio.
5. **Acceptance rate was 0/25.** Neither model passed the sealed hidden tests for
   F1/F2 in these single-attempt configs. This is a real outcome; its consequence
   for metrics is in §5. (Feasibility measures the *instrument*, not model skill.)
6. **Cache carryover is real and large (criterion 7).** Warm-series C1:

   | rep | cache_state | cache_creation | cache_read | marginal $ |
   |---|---|---|---|---|
   | 1 | cold | 43,973 | 238,969 | 0.2718 |
   | 2 | warm (resumed) | **574** | 88,240 | **0.0360** |
   | 3 | warm (resumed) | 9,270 | 286,271 | 0.1741 |

   Resumed runs collapse cache-*creation* (43,973 → 574) — the provider prompt
   cache carried over — and the runner captures it + costs it cache-aware. This is
   the ex120 teaching input.

## 5. Metric computability & per-cell dispersion

`harness/evaluator/metrics.py` computes all metrics end-to-end (tested, no spend):
- **ECST / QA-ECST**: **`undefined` (0 accepted tasks)** for every cell — correct
  and honest (Σ attempt cost / 0), never a fabricated finite number. The attempt-
  cost numerator is still reported (e.g. F1 = $3.886 known floor; F2 = $1.344).
- **HEAC**: **`unavailable`** — depends on the criterion-6 human-effort subset.
- **Both cost views** (marginal_operating, fully_allocated) compute per leg/cell.

Per-cell **marginal cost** dispersion (median / IQR / min–max, n=3 unless noted):

| Cell | median $ | IQR $ | range $ |
|---|---|---|---|
| F1·P0 | 0.2143 | 0.4272 | 0.124–0.552 |
| F1·C2 | 0.1155 | 0.0905 | 0.093–0.183 |
| F1·P1 | 0.5121 | 0.1530 | 0.463–0.616 |
| F1·C1 | 0.1741 | 0.2358 | 0.036–0.272 |
| F1·C5 (n=2) | 0.2662 (floor) | — | 0.195–0.337 |
| F2·P0 | 0.0772 | 0.2393 | 0.076–0.315 |
| F2·C2 | 0.0613 | 0.0746 | 0.024–0.099 |
| F2·P1 | 0.2343 | 0.2442 | 0.106–0.350 |

**Rep-count implication:** dispersion is **high relative to the median** in several
cells (F1·P0 IQR > 2× median; F1·C1 range ~7.5×). Three reps localize the central
tendency but not tight intervals. **Recommendation:** for screening, budget **≥5
reps** on high-variance cells (strong single-model and cold cache-sensitive cells)
and report medians with IQR, not means; re-assess after batch 2 adds F3.

## 6. Go / No-Go

**GO for Phase 4 screening design — conditional**, on the measurement system:
the instrument is proven on 25 runs across 2 gate types — validator 25/25, cost
reconstructed without self-report, escalation + cache telemetry captured, metrics
compute. Conditions before screening runs execute:
1. **Batch 2 (F3 / W1 test-generation)** completes the 27 and the third gate type
   (own mini CP-SPEND), before the full-suite go/no-go is final.
2. **Criterion 6 (human-effort subset)** — human reviewers record the 9-run rubric
   timings + inter-reviewer spread (no model spend). HEAC stays `unavailable` until
   then.
3. **Rep count** raised per §5 for high-variance cells.
4. Product B remains in the **black-box/proxy tier** with §4 limitations; no metric
   requiring its tokens is treated as authoritative.

## 7. What CP-DATA gates

Acceptance of this report unblocks Phase 4 **screening design** (not screening
runs, which need CP-SCREEN-PREREG). No number here appears in any docs/site/report
until **CP-FINDINGS**. All figures are internal, NON-COMPARATIVE feasibility
telemetry.
