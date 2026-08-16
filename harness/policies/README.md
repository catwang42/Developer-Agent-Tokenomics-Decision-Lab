# Routing policies — artifact registry (mirrors SPEC §2.1c)

Every routing policy and acceptance-gate artifact the lab uses, with its location and
build status. Lab users and forkers resolve **any** policy or gate reference in the
specification through this table; a policy referenced elsewhere in the spec but absent
here is a specification defect.

This file mirrors SPEC §2.1c. SPEC is the source of truth — if the two disagree, SPEC
wins and this file is the thing to fix. Family definitions (B1–B4) and what each does
and does not causally support live in
[`methodology/routing-policy.md`](../../methodology/routing-policy.md).

## Routing policies (`harness/policies/`)

| ID | File | Status | What it encodes | Used by | Manifest pin |
|---|---|---|---|---|---|
| P0 | `p0-baseline.yaml` | **Exists** | Static strong single-model baseline; no escalation; deterministic gate | Controlled set; ex220-B/B1 | — (model refs resolve via manifest) |
| P1 | `p1-cheap-first.yaml` | **Exists** | Economical attempt → pre-registered gate → escalate on fail; records intention-to-route, completed route, failed-attempt costs; both legs billed | Controlled set; ex220-B/B2 | — (model refs resolve via manifest) |
| P2 | `p2-delegation.yaml` | **To build (Phase 4, SPEC §6 item 3)** | Scripted delegation: pinned `tasks/<task>/split.yaml` assigns executor vs conductor scopes; both legs itemized | ex220-B/B3 | split-file hash per task |
| P3 | `p3-policy-delegation.yaml` | **To build (Phase 4, SPEC §6 item 3).** C5's delegation rules currently live inline in `harness/configurations/C5.yaml`; extracting them into P3 is the build step | Policy-driven delegation governing C5: conductor decides when to delegate to the cross-family executor | ex220-B/B4; C5 companion runs | policy hash (**required before any C5 run is cited in workshop material**) |

## Acceptance-gate artifacts (SPEC §2.6 priority order; per task)

| Artifact | Location | Status |
|---|---|---|
| Deterministic public checks (typecheck, build, regression, diff-scope, no-leakage, public feature test) | `tasks/<task>/` gate scripts + public tests | **Exist** for the pilot, W4, W1 |
| Sealed hidden tests | `tasks/<task>/hidden/` (gitignored, human-authored) | **Exist and hashed in the manifest** for all three tasks: pilot-v2, sealed-w4-v2, w1-v1 (three sha256s recorded) |
| Human-review rubric (timed) | `report/batchN/human-effort-rubric.md` | **Exists**; executed for batch 3 (criterion 6) |
| Evaluator | `harness/evaluator/` | **Exists**; version and hash published per SPEC §2.6 |

## Not yet pinned in the manifest

Open, SPEC §6 item 6: per-task **prompt hashes** · the **P3 policy hash** · **Product-B
version** and **`--print-timeout`** pins.

## Rules

- **Policies are executed by configurations, not the reverse.** `harness/configurations/`
  declares the product+model stack; a policy declares the routing decision. Comparisons
  across the two axes never merge (SPEC §2.1b).
- **Model references are placeholders** (`STRONG_MODEL_A`, `ECONOMICAL_MODEL_A`) and
  resolve only through `manifest/delivery-manifest.yaml`. Never hardcode a model ID or a
  price in a policy file.
- **A policy is not citable until its manifest pin exists** where the table above
  requires one. P3 in particular: no C5 run may be cited in workshop material before its
  policy hash is in the manifest.
