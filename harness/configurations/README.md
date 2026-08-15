# Configurations C1–C6 (SPEC §2.1, v2.2)
One YAML per configuration. model_ref values are placeholders resolved ONLY by
manifest/delivery-manifest.yaml. cost_basis is declared per delivery org (subscription
seat vs API). The runner refuses to start if manifest resolution or cost_basis is missing.

A *configuration* is the product+model stack. The routing policy it executes is a
separate axis (`harness/policies/`, families B1–B4 in SPEC §2.1b); the two never merge
into one comparison.

| ID | File | Current window (SPEC v2.2) |
|---|---|---|
| C1 | `C1.yaml` | Scheduled — Product A strong tier (baseline) |
| C2 | `C2.yaml` | Scheduled — Product A economical tier |
| C3 | `C3.yaml` | Scheduled for screening — Product B, current Flash generation, with the declared companion **C3-prev** (prior Flash generation, same tier). C3 vs C3-prev is the Product-B within-product **generational** panel |
| C4 | `C4.yaml` | **Never yet run; dropped from the current screening window by human decision (2026-08-15).** Retained as a declared configuration; may be scheduled in a later window |
| C5 | `C5.yaml` | Companion runs — Product A conductor → Product B executor, governed by pinned policy **P3** (currently inline here; extraction to `p3-policy-delegation.yaml` is a Phase-4 build step). Executor-leg cost `unavailable` until the provider-side collector exists |
| C6 | *(no file)* | **Declared, not scheduled.** Gateway/router layer (LiteLLM-style); named on the routing ladder so the family can be placed, never presented as measured. No YAML until router infrastructure exists and a CP-SPEND schedules it |

C3-prev is a declared companion of C3 (same product, same tier, one model generation
apart), not a separate configuration ID; the manifest resolves both generation
selectors.
