# CP-SPEND package — Phase 3 feasibility dataset (batch 1)

Prepared for the **CP-SPEND** checkpoint (CLAUDE.md; SPEC §2.3; binding protocol
`methodology/feasibility-protocol.md`). This document is the material the human
reviews before **any** live benchmark run. It does **not** authorize spend.

**Status (updated 2026-07-19):** the pre-spend deliverables are now resolved and
verified in `--dry-run` (no spend):
- **Manifest resolved** — `manifest/delivery-manifest.yaml`: STRONG_MODEL_A =
  `claude-sonnet-4-6@default`, ECONOMICAL_MODEL_A = `claude-haiku-4-5@20251001`
  (both GA on Vertex, project `vital-octagon-19612`, region `us-central1`, verified
  from the live publisher-model list — not guessed); Product B tiers = verbatim
  Gemini selector labels; `cost_basis: marginal_api_cost` on all legs.
- **Pricing pinned** — `pricing/prices-2026-07-19.json`, published rates with source
  URLs + retrieval timestamps inside the file.
- **`--cache-state` contract implemented** (was §4.4) — required flag, cold-freshness
  proven from the event log, warm-series session resume; 6 new tests green.
- **F3 = option (b)** — batch 1 excludes F3; it becomes batch 2 (own mini CP-SPEND).

All token/cost figures below are **a-priori planning estimates, NOT telemetry** —
the feasibility runs produce the first authoritative token data (CLAUDE.md 1–3).

> ⚠️ **Ceiling flag:** the HIGH end of the batch-1 envelope (§3) is **~$64.5**
> (global) / **~$70.4** (regional), which **exceeds the $60 not-to-exceed ceiling**.
> EXPECTED is ~$30 and LOW ~$11. Per the batch-1 instruction, this is surfaced for a
> decision **before anything runs** — see §3 for options.

---

## 1. Run matrix

### Batch A — the 27 controlled runs (SPEC §2.3, protocol §"The 27 controlled runs")
3 tasks × 3 configurations × 3 reps, cold-cache, fresh sessions, controlled harness
(Product A). Configurations: **P0** (strong single-model baseline), **C2**
(economical single-model), **P1** (cheap-first escalation).

| Task | Ready? | Runs (×3 cfg ×3 rep) |
|---|---|---|
| F1 = `pilot-realworld-draft-articles` (`30b68e1`) | ✅ ready | 9 |
| F2 = `w4-realworld-missing-user-id` (`88b258c`) | ✅ ready | 9 |
| F3 = W1 test-generation | ❌ **BLOCKED** (see §4) | 9 |

Ready now in Batch A: **18 runs** (F1, F2). Blocked: **9 runs** (F3).

> **P1 bills up to two legs per run.** On gate-fail the economical attempt cost is
> retained *and* the strong attempt runs (runner `execute()` cheap_first path). The
> 6 ready P1 cells (F1,F2 × 3 reps) can therefore execute up to 12 leg-billings.

### Batch B — companion: product-telemetry feasibility (protocol §"Companion runs")
F1 × {C3, C5} × 2 reps = **4 runs** (C4 optional, +2). C3 = Product B black-box
(`agy`); C5 = hybrid conductor(Product A)+executor(Product B), both legs billed.
Purpose: enumerate authoritative/derived/unavailable fields per product; validate
dual-leg aggregation on real C5 data; record selector labels verbatim.

### Batch C — companion: cache warm-series (protocol §"Companion runs")
F1 × C1 × one 3-run series (run 1 cold, runs 2–3 warm) = **3 runs**. **BLOCKED** on
the `--cache-state` runner contract (see §4). Purpose: validate cache-state capture +
cache-aware costing; becomes the ex120 teaching input.

### Batch D — companion: human-effort subset (protocol §"Companion runs")
Timed review rubric applied to **9 of the already-produced runs** (one rep per cell),
two reviewers on ≥3 of them. **No new model spend** — human reviewer time only.

### Totals (new billable model runs)
| | Ready-to-run | Blocked | Total |
|---|---|---|---|
| Batch A (controlled) | 18 | 9 (F3) | 27 |
| Batch B (C3/C5) | 4 (+2 C4 opt) | — | 4–6 |
| Batch C (warm C1) | 0 | 3 (cache-state) | 3 |
| **Total** | **22–24** | **12** | **34–36** |

---

## 2. Exact invocations

Live runs require `LAB_ALLOW_SPEND=1` **and** a fully-resolved manifest + pricing
snapshot (runner refuses otherwise — `run.py` `main()` / `resolve_model()`).

```bash
# Batch A — controlled 27 (per ready task, per config, per rep 1..3):
for task in tasks/pilot-realworld tasks/suite/W4-complex-bugfix; do
  for cfg in P0 C2 P1; do
    for rep in 1 2 3; do
      LAB_ALLOW_SPEND=1 bash harness/runner/run.sh \
        --task "$task" --config "$cfg" --rep "$rep" \
        --phase feasibility --cache-state cold        # <-- flag pending (§4)
    done
  done
done

# Batch B — product telemetry (F1 × {C3,C5} × rep 1..2):
for cfg in C3 C5; do for rep in 1 2; do
  LAB_ALLOW_SPEND=1 bash harness/runner/run.sh \
    --task tasks/pilot-realworld --config "$cfg" --rep "$rep" \
    --phase feasibility --cache-state cold
done; done

# Batch C — warm-series (F1 × C1, run1 cold then 2..3 warm in one session):
#   pending --cache-state warm-series support (§4).
```

Outputs land in `results/feasibility/<run_id>/` (event log + validated summary).

---

## 3. Budget estimate (a-priori planning — NOT telemetry) vs the $60 ceiling

No prior runs exist, so per-run token volumes are planning bands, not measurements.
Costing is derived by the runner from `pricing/prices-2026-07-19.json`.

**Per controlled coding run (agentic, multi-turn, cold cache) — assumed band:**

| Billed class | Low | Expected | High |
|---|---|---|---|
| `input_tokens` (uncached) | 30k | 80k | 150k |
| `cache_creation_tokens` | 40k | 120k | 250k |
| `cache_read_tokens` | 150k | 500k | 1,500k |
| `output_tokens` | 15k | 35k | 70k |

Warm-series runs 2–3 use a cache-dominated band (fewer writes, ~0.2–2.0M reads).
**P1 (cheap-first) and C5 bill two legs** — the estimate conservatively assumes
**every P1 run escalates** (econ attempt + strong attempt both billed) and that
**Product B fully exposes tokens** (in practice its telemetry is partial → some
C3/C5 legs will be `cost_unavailable`, i.e. lower actual spend).

**Computed batch-1 totals** (25 runs: 18 controlled + 4 product + 3 warm; from the
pinned snapshot):

| Claude endpoint basis | LOW | EXPECTED | HIGH |
|---|---|---|---|
| global-endpoint (list rates) | $11.45 | $30.43 | **$64.52** |
| us-central1 regional (+10%) | $12.48 | $33.20 | **$70.39** |

**Against the $60 ceiling:** LOW and EXPECTED are well under; the **HIGH band
exceeds $60** on both bases. The HIGH band is a deliberately conservative
worst-case (max tokens × all-P1-escalate × Product-B-tokens-exposed) — the expected
outcome (~$30) is half the ceiling. Options for the human:

- **(a)** Keep $60 and add a **cumulative-spend kill-switch** to the runner (no-spend
  build work): halt the batch when summed `marginal_operating_usd` crosses a cap.
  This bounds actual spend to ≤$60 regardless of the token tail. *(Recommended.)*
- **(b)** Raise the ceiling to **$75** (covers the regional HIGH tail).
- **(c)** Trim batch 1 (e.g. drop C5 companion, or 2 reps on the priciest P1 cells)
  to pull the HIGH band under $60.

There is currently **no automatic in-runner spend cap** — each run validates
independently but nothing halts the batch at a cumulative dollar figure. Absent
option (a), the ceiling is honoured by monitoring, not enforcement.

**Guards already in place:** runner refuses live runs without `LAB_ALLOW_SPEND=1`;
refuses any unresolved manifest field or missing pricing; cost is reconstructed from
provider token metadata, never model self-report (protocol criterion 2 / stop
condition).

---

## 4. Prerequisites — status

### 4.1 Manifest resolution (`manifest/delivery-manifest.yaml`) — ✅ RESOLVED
All configurations filled and verified in `--dry-run` (resolution + costing pass for
P0/C2/P1/C3/C5). `cost_basis: marginal_api_cost` on all legs; `delivery_date:
2026-07-19`; `pricing_snapshot: pricing/prices-2026-07-19.json`. Remaining
placeholder: `task_suite_commit: TBD` (set to the batch-1 run commit at approval).
Model IDs verified GA on Vertex from the live publisher list (not guessed).

### 4.2 Pricing snapshot (`pricing/prices-2026-07-19.json`) — ✅ PINNED
Four token classes for every provider/model used; source URLs + retrieval timestamps
inside the file. Claude values are global-endpoint list rates with the us-central1
regional +10% recorded as a per-model sensitivity. Gemini values are Vertex global
rates; `cache_write` = base input (no published per-token Gemini write premium).
**Human to confirm** the numbers and the global-vs-regional endpoint choice.

### 4.3 F3 (W1 test-generation) — ✅ DECISION RECORDED: option (b)
Batch 1 excludes F3. F3/W1 runs as **batch 2** with its own mini CP-SPEND, after W1
is pinned and 10-point validated with a human-authored sealed hidden test. Recorded
in `tasks/suite/W1-test-generation/workload.yaml` (`feasibility_reuse`). CP-DATA runs
only after both batches so the completeness report covers the full 27 + all three
gate types. W1's CP-SCREEN-PREREG pre-registration must disclose this feasibility use.

### 4.4 `--cache-state` contract — ✅ IMPLEMENTED (no spend)
`run.py`/`run.sh` now require `--cache-state {cold|warm-series}`; each leg stamps its
`session_id`/`resumed` onto `model_call_started`, and the runner proves cold
freshness from the event log (`assert_cache_contract`) and stamps
`identity.cache_state`/`session_state` authoritatively. Warm-series resumes a session
(`--session-id … --resume`). 6 new tests green; event vocabulary unchanged
(CP-SCHEMA respected — no new event type). Product B session control is not exposed,
so its cold freshness is best-effort and reported as such.

### 4.5 Open for the human at approval
- **The $60 ceiling vs the HIGH envelope tail** — pick option (a)/(b)/(c) in §3.
- **Product B / `agy` availability** — C3/C5 require a working Antigravity CLI +
  Gemini access on this account; confirm before the companion runs.
- `task_suite_commit` pin (§4.1).

### 4.6 Minor: F2 config-list mismatch (non-blocking)
`tasks/suite/W4-complex-bugfix/task.yaml` declares `configurations: [C1,C2,C3,C5]`
(screening framing) — it does not list P0/P1. The runner does not enforce the
task's config list, so feasibility {P0,C2,P1} still runs; noted for consistency.

---

## 5. What CP-SPEND approval covers vs. gates downstream
- **Covers:** the specific batches, configs, tasks, and cost ceiling approved here.
- **Gates:** the feasibility dataset → `report/telemetry-completeness.md` → **CP-DATA**
  (protocol pass/fail criteria 1–7 + go/no-go). No result appears in docs/site until
  **CP-FINDINGS**. This package makes **no vendor-comparative claims**.
