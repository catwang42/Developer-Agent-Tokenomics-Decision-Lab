# Routing Policy — When to Use a Powerful vs Economical Model

## Decision matrix (taught in M3; implemented by P1/C5)
| Work characteristic | Route to | Why |
|---|---|---|
| Judgment-dense: requirements, design, edge cases, integration correctness | STRONG | Errors are expensive; retries costly |
| Volume-dense: scaffold, boilerplate, mass test generation, mechanical migration | ECONOMICAL first | Output-heavy; failures cheap to detect via gate |
| Verification, final review, merge decision | STRONG, clean state | Never trust the generator; independent gate first |
| Small one-off edits (below break-even) | whatever is open | Routing overhead exceeds savings |
| Grounded search / doc sweeps | ECONOMICAL with grounding | Capability + cost |

## Break-even rule (measurable, per task class, from reference data)
Expected policy cost: E[P1] = c_econ + gate_cost + p_fail × (c_strong + gate_cost)
Route economical-first only when, for that task class:
1. E[P1] < c_strong under BOTH cost views, and
2. quality is non-inferior under the declared margin.
c_econ, c_strong, p_fail come from measured pilot-reference distributions — never
assumed. Small tasks typically fail condition 1 (fixed overhead dominates).

## Adoption gate (four conditions, ALL required — SPEC §2.5)
1. Quality non-inferior under the declared margin
2. Economic gain exceeds the ORG-set business-relevance threshold
3. Gain survives verifier, retries, rework, human review (i.e., ECST/HEAC, not tokens)
4. Direction stable across tasks and repeated runs (per declared statistics)

## Cache interaction
Warm caches shift break-even: repeated-context work discounts the strong model more
(cache_read pricing), narrowing the economical advantage. Break-even is therefore
computed per cache protocol (cold vs warm-series) — see cache-protocol.md.
