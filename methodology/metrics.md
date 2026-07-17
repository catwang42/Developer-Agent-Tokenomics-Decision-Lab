# Metrics — Economics & Quality (SPEC §2.4–2.5; implement in report/generate.py)

## Quality
- **Acceptance**: binary per run from the pre-registered independent gate (SPEC §2.6):
  hidden deterministic tests → type/lint → regression → (security) → timed human rubric.
  The generating model is never the sole verifier.
- **Success rate** = accepted / total attempts, reported with an uncertainty interval.
- **Quality non-inferiority margin**: declared in the run pre-registration before data.

## Economics (all in BOTH cost views)
- **Cost views**: marginal_operating (additional observable cost of the task) and
  fully_allocated (under declared seat/subscription/committed-spend allocation).
  A finding is robust only if its direction survives both.
- **Cost per attempt** = leg-summed provider + machine cost of one run (all token
  classes priced from the dated snapshot; cache_write premium, cache_read discount).
- **ECST (expected cost per accepted task)**, per task:
  ECST = Σ(cost of ALL attempts, incl. failed + verification) / count(accepted).
- **QA-ECST**: ECST reported BY task class / complexity band / language / risk level.
  A suite-wide aggregate only with a declared task-mix weighting model (SPEC §2.4).
- **HEAC (human-effort-adjusted cost)** = ECST + (active+review+correction minutes ×
  loaded_rate_per_minute declared in the delivery manifest). Blocked minutes reported
  separately, never monetized into headcount.
- **Escalation policies (P1)**: report intention-to-route AND completed-route; failed
  economical attempts always included in ECST.
- **Diagnostics only** (never headline): frontier_token_share, raw token deltas.
- **Latency**: wall-clock median + IQR; P95 only at sufficient n.

## Statistical rules (declared before data — SPEC §2.4)
Medians + IQR for cost; uncertainty interval on success rate; paired task-level
comparisons where applicable; bootstrap CIs for cost differences when justified;
failure categories reported separately; excluded/missing-cost runs never averaged as
zero; descriptive statistics preferred at pilot scale.

## Forbidden
FTE conversions from runtime · zero-filling unavailable telemetry · model self-reported
token counts · unscoped or suite-aggregated claims without declared weights.
