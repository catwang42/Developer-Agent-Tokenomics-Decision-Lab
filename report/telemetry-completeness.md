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

## 1.5 Batch-1 validity — ROOT CAUSE of 0/25 acceptance (post-CP-DATA-review)

CP-DATA review flagged the 0/25 acceptance. Investigation (no spend) classifies
**all 25 runs as NO_WRITE — a harness defect, not model failure or a real finding.**

**Root cause:** both adapters invoked their CLI in headless mode **without tool
auto-approval**. In headless mode there is no interactive approver, so the default
permission mode allows read-only tools but **silently denies Edit/Write/Bash**. The
agent reads the repo and reasons, but cannot apply edits → **empty diff** → the gate
correctly reports the feature absent.
- `claude_code` `build_command` passed no permission flag (fix: add
  `--dangerously-skip-permissions`).
- `agy` `build_command` used `--select` (not a valid flag in agy 1.1.4; model
  selection is `--model`) **and** no auto-approve (fix: `--model <verbatim label>`
  + `--dangerously-skip-permissions`).

**Evidence (sample ≥6 across configs; full table classifies 25/25 = NO_WRITE):**

| Run | Agent read repo? (cache_read) | Output | Gate P1 (feature) | Diff | Class |
|---|---|---|---|---|---|
| F1·P0·rep1 | yes — 298,865 | 2,364 | fail | empty* | NO_WRITE |
| F1·C2·rep1 | yes — 147,132 | 3,775 | fail | empty* | NO_WRITE |
| F1·P1·rep1 (2 legs) | yes — 518,534 | 4,956 | fail (both legs) | empty* | NO_WRITE |
| F1·C1·rep1 (warm) | yes — 238,969 | 2,346 | fail | empty* | NO_WRITE |
| F1·C5·rep1 (conductor) | yes — 412,791 | 2,985 | fail | empty* | NO_WRITE |
| F1·C3·rep1 (Product B) | unavailable | unavailable | fail | empty* | NO_WRITE |

`*` The gate records no changed files list, so "empty" is inferred from the joint
signature: **P3-typecheck + P4-build + P2-regression PASS** (pristine tree compiles)
while **P1-feature FAILs** and **P6-diff-scope passes trivially** (no unexpected
paths) — i.e. an unmodified tree. Corroborated by the token profile (every Product A
leg read 100K–1.3M cache tokens — read tools work — with no accepted solution) and
by the structural defect (no auto-approve flag → edits *could not* be applied).
**No run was WRONG_SOLUTION or GATE_ERROR** (no real diffs exist to show).

**Sandbox posture (recorded per CP-SPEND revalidation condition).** The fix runs
subjects with `--dangerously-skip-permissions` (tools auto-approved). Isolation is
currently **weak — confined only by the throwaway per-task `.work/repo` cwd on this
dev VM (no container, no network policy)**; acceptable for revalidation only. The
posture is stamped authoritatively on every run in `identity.permission_profile`
(`SUBJECT_PERMISSION_PROFILE`, `harness/adapters/base.py`; see the adapter README).
**A subject-isolation decision (containerized subject runs, network policy) is a
MANDATORY Phase-4 screening CP-SPEND item** (§6).

**Diagnostic gap (also fixed):** the pre-fix `claude_code` adapter did not record
`num_turns` / `permission_denials`, so per-run denial counts can't be shown from the
stored artifacts. The fix now stamps `num_turns`, `permission_denials`, `is_error`,
`subtype`, `result_chars`, and `product_reported_cost_usd` on `model_call_completed`,
so revalidation runs are self-diagnosing (a NO_WRITE recurrence would show
`permission_denials > 0` / `num_turns == 1`).

**Consequence for the criteria below:** the telemetry *plumbing* criteria (1, 2, 4,
7) were exercised correctly — they faithfully captured what happened — but they were
exercised on **no-write runs**, and the agent-execution + acceptance path was never
exercised on a real solution. **The instrument is NOT yet declared working; a
revalidation batch (mini CP-SPEND, §6) is required.**

## 1.6 Revalidation results (post-fix) — resolves §1.5

Mini CP-SPEND revalidation ran 4 runs (`results/revalidation/`, cold, $15 cap;
**actual $1.38**) on the fixed adapters. The fix is confirmed and §1.5 is resolved:

| Run | num_turns | permission_denials | diff | acceptance | Class |
|---|---|---|---|---|---|
| F2·C2·rep1 | 13 | 0 | non-empty | **accepted** (gate pass) | CORRECT |
| F1·P0·rep1 | 20 | 0 | non-empty (P6 diff-scope fail) | rejected | WRONG_SOLUTION |
| F1·P0·rep2 | 19 | 0 | non-empty | rejected | WRONG_SOLUTION |
| F1·P1·rep1 | 17 (econ) → 8 (strong) | 0 | non-empty (both legs) | rejected | WRONG_SOLUTION |

- **No-write is gone:** every leg ran 8–20 agentic turns with **0 permission
  denials** (was the silent-denial defect). Non-empty diffs confirmed directly —
  F1·P0·rep1 even **fails P6-diff-scope** (only possible if files changed).
- **An accepted run exists:** F2·C2 solved the bugfix → **ECST computes finite**
  (`w4-...|C2` ECST_marginal = **$0.1155**, n_accepted=1). Criterion 5 closes.
- **F1 failures are legitimate WRONG_SOLUTION**, not defects (real agentic work,
  wrong/out-of-scope result). Per the CP-SPEND condition, these are treated as
  findings; the harness is **not** iterated to make models pass.
- **Pass criteria (§6) MET:** ≥1 run with non-empty diff + `permission_denials==0`
  + `num_turns>1` (all 4), AND ≥1 accepted (F2·C2).
- **Provenance note (not a blocker):** the agent's diff is reset between runs and
  not archived, so WRONG_SOLUTION diffs aren't inspectable after the fact — a
  provenance improvement to consider for screening (archive the pre-reset diff),
  distinct from any change that would affect pass/fail.

**Batch-1 (§2–§5) status:** its 25 runs remain NO_WRITE and are **not** valid task
outcomes; they are retained only as telemetry-pipeline evidence. The 27-run study
dataset must be **re-collected** on the fixed harness (folds into batch 2 planning).

## 2. Pass/fail criteria (protocol §"Pass/fail criteria")

| # | Criterion | Result | Verdict |
|---|---|---|---|
| 1 | Validator passes; zero zero-fills | **25/25** summaries + event logs valid; 0 zero-fills | ✅ PASS (plumbing) |
| 2 | Cost reconstruction w/o self-report | **25/25** costed from token metadata only; C1/C2 every usage field authoritative; product unavailable fields enumerated | ✅ PASS (plumbing) |
| 3 | Harness stability | **0 crashes**; reset determinism identical (F1: 1 hash/16 runs, F2: 1 hash/9); gate reproducibility from Phase 2. No-write defect (§1.5) **fixed and revalidated** (§1.6: 8–20 agentic turns, 0 denials) | ✅ PASS (defect fixed + revalidated) |
| 4 | Escalation telemetry | **6/6** batch-1 P1 runs record ITR + CR + both leg costs; revalidation P1 escalated on a real gate failure | ✅ PASS |
| 5 | Metric computability | pipeline computes end-to-end (`harness/evaluator/metrics.py`); **ECST now exercised on an accepted run** (revalidation F2·C2 = $0.1155). HEAC still needs the human subset (criterion 6) | ✅ PASS (finite ECST on an accepted run) |
| 6 | Human effort | rubric timings for the 9-run subset | ⏳ **PENDING** (human reviewer time; not fabricated) |
| 7 | Cache | warm-series shows cache_read capture + costing delta vs naive | ✅ PASS (plumbing) |

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

**Instrument VALIDATED (revalidation passed, §1.6).** The no-write defect is fixed
and confirmed on live runs (8–20 agentic turns, 0 permission denials, non-empty
diffs, one accepted run), and every telemetry criterion is now PASS except the
human-effort subset (6, pending). **Conditional GO for Phase 4 screening _design_**;
screening _runs_ remain gated on the conditions below (and CP-SCREEN-PREREG).

Revalidation summary: 4 runs, $1.38; 1 accepted (F2·C2), 3 WRONG_SOLUTION (real
diffs) — the latter are findings, not defects. Product B (`agy`) got the same flag
fix; it revalidates in a separate mini-batch (its tokens remain black-box regardless).

**Conditions before screening runs execute:**
1. **Subject-isolation decision (MANDATORY at Phase-4 screening CP-SPEND)** —
   containerized subject runs and/or network policy, replacing the current
   skip-permissions-in-cwd posture (§1.5). Screening's larger/longer batch must not
   run subjects with bypassed permissions outside a real sandbox.
2. **Batch 2 (F3 / W1 test-generation)** completes the 27 and the third gate type.
3. **Criterion 6 (human-effort subset)** — human reviewers record 9-run rubric
   timings + inter-reviewer spread (no model spend). HEAC stays `unavailable` until.
4. **Rep count** raised per §5 for high-variance cells.
5. Product B remains in the **black-box/proxy tier** with §4 limitations.

**Note on batch-1 spend:** the $5.23 already spent bought no valid task outcomes
(all NO_WRITE), but did validate the telemetry pipeline and surface three harness
defects (UUID session ids, no-write permissions, agy flags) before screening — a
cheap, worthwhile failure.

## 7. What CP-DATA gates

The measurement system is validated (root cause found, fixed, and revalidated on
live runs — §1.6). CP-DATA acceptance of this report clears the
**telemetry-completeness** requirement and unblocks Phase 4 **screening design**,
subject to the §6 conditions (subject-isolation decision, batch 2 / F3, human-effort
subset, rep count) — which are gated at CP-SCREEN-PREREG and the screening CP-SPEND,
not here. The batch-1 25-run study data is superseded (NO_WRITE) and must be
re-collected on the fixed harness. No number here appears in any docs/site/report
until **CP-FINDINGS**. All figures are internal, NON-COMPARATIVE feasibility
telemetry.
