# Routing Policy — When to Use a Powerful vs Economical Model

## The routing-policy taxonomy: four families (SPEC §2.1b; taught in ex220-B)

Layer-1 methodology. A *routing policy* is what decides which model does which work; a
*configuration* is the product+model stack that executes it. The two are different axes
and their comparisons never merge (SPEC §2.1: three structurally distinct views).

Policies are **P-labelled artifacts** in `harness/policies/`; their build status,
locations and manifest-pin requirements live in the registry
([`harness/policies/README.md`](../harness/policies/README.md), mirroring SPEC §2.1c).
Resolve any policy reference through that registry — a policy named here but absent
there is a defect.

| Family | Name | What it does | Policy artifact |
|---|---|---|---|
| **B1** | Static assignment | One model does all the work. No routing decision at runtime. By construction, every single-model configuration run is a B1 run | P0 (`p0-baseline.yaml`) |
| **B2** | Escalation (cheap-first) | Economical attempt → pre-registered gate → escalate to the strong tier on failure. **Both legs billed**; intention-to-route and completed-route both recorded | P1 (`p1-cheap-first.yaml`) |
| **B3** | Scripted delegation | A **pinned split file** (`tasks/<task>/split.yaml`) assigns executor vs conductor scopes ahead of time. Both legs itemized on one bill | P2 (`p2-delegation.yaml`; splits pinned, awaiting freeze) |
| **B4** | Policy-driven delegation | The conductor decides at runtime when to delegate to a cross-family executor, under a pinned delegation policy | P3 (`p3-policy-delegation.yaml`; governs C5, pinned, awaiting freeze) |

### What each family does and does not causally support

- **B1 is the null hypothesis every dynamic policy must beat.** Its cost is a plain
  measurement of one stack on one task; it supports no routing claim at all, which is
  exactly its job — it is the baseline the others are scored against.
- **B2 supports a routing claim only when the failure branch is priced.** The number
  that matters is all-in cost per accepted task *including the failed economical
  attempt and its verification*, not the cost of the successful cheap runs. Report it
  under both intention-to-route and completed-route. If the escalation branch has never
  fired on the suite, the policy has not been measured — it has been assumed, and B2
  must be demonstrated from a replay artifact until a live failure→escalation trace
  exists (SPEC §2.9 item 3).
- **B3 supports a within-policy leg comparison, not a product comparison.** Because the
  split is pinned in advance, the executor and conductor legs are a controlled
  assignment — but only on a stack that **itemizes per-leg usage on one bill**. That is
  a capability requirement, not a product mandate: without per-leg usage, a B3 run
  yields one blended number that supports nothing.
- **B4 supports no causal claim.** Product architecture, delegation interface, context
  transfer, tooling, provider paths and two billing mechanisms all change together by
  design. It is a gallery item: both bills on screen, failed delegations and
  verification counted, frontier-token share diagnostic only. **B4/C5 does not inherit
  the causal status of the controlled B1-vs-B2 (P0 vs P1) comparison.** Varying the
  executor tier inside a pinned C5 is a *within-workflow executor-tier comparison* and
  nothing more.
- **Gateway/router stacks (LiteLLM-style, configuration C6)** sit on this ladder as a
  *named* family, not a measured one: telemetry would be proxy-observed at best. Named
  so a vendor's "intelligent routing" pitch can be placed; never presented as measured.

**Merge rules.** Panels never merge across products. Policy comparisons never merge with
product black-box comparisons. A policy result is reported against the configuration it
ran on, never generalized to the family.

## Decision matrix (taught in M3; implemented by P1 = B2 and C5/P3 = B4)
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
