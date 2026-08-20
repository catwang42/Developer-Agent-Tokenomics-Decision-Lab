# results/ — datasets and the report that documents each

Every dataset directory below names the **report that documents it**. The pairing rule:
`report/batchN/` documents `results/feasibility-batchN/`. Cross-cutting and one-off
datasets are documented inside the relevant batch report rather than in their own folder
(a deliberate choice — see `report/README.md`).

**Authoritative dataset: `feasibility-batch3/`** — the current controlled feasibility
instrument, collected on a single fixed harness version. All other feasibility datasets
are **superseded** and retained (never deleted) as provenance: each was collected on a
materially different harness version, so pooling them would mix versions inside one
dataset. Keeping them lets any number in a superseded report be traced to its exact runs.

| Directory | What it is | Documented by |
|---|---|---|
| `feasibility/` | batch 1 (25 runs), **superseded** — the NO_WRITE-defect set (agents couldn't write files → 0/25 accepted) | `report/batch1/` |
| `feasibility-batch2/` | batch 2 (34 runs), **superseded** — pre-isolation-FIX harness | `report/batch2/` |
| `feasibility-batch3/` | batch 3 (30 runs), **AUTHORITATIVE** — 27 controlled + 3 warm (warm regressed here) | `report/batch3/` |
| `feasibility-warm-series/` | standing warm-cache evidence (3 runs), **standalone — NOT pooled with batch 3** | `report/batch3/telemetry-completeness.md` §4.4 |
| `revalidation/` | one-off no-write-fix verification (4 runs) | `report/batch3/` appendix |
| `smoke/` | one-off Antigravity (Product B) invocation verification (1 run) | `report/batch3/telemetry-completeness.md` §4 |
| `smoke-screening/` | screening smoke (8 completed + 1 aborted) **plus the 4-run re-smoke** that verified the fixes, **harness evidence, NOT measurements** — live test of the containerized agent leg and the provider-side collector; found 4 blocking defects, all fixed and re-verified | `report/smoke-screening/` (smoke) + `report/smoke-screening/re-smoke/` (fix verification) |
| `pilot-reference/` | empty until CP-FINDINGS (≥5 reps/cell; write-protected; human merges only) | — (populated at CP-FINDINGS) |
| `screening/` | empty until Phase 4 (hypothesis-seeking positioning evidence, SPEC §5) | — (populated in Phase 4) |
| `screening-batch1-aborted-20260817-gatefix/` | screening batch 1, **ABORTED at 5/126 runs — NOT a screening result**. Halted by kill switch when every run graded `acceptance.result: error`: `container_gate()` never mounted the sealed hidden set, so the hidden gate reported `awaiting_human` on every containerized run. Telemetry is real and validated; the *outcome* variable is absent, so no cell is gradable. Retained as provenance for $1.86 of real spend | its own `batch1.log` (header note + `HALTED BY OPERATOR` record); no CP-DATA report — there is nothing to report on |
| `smoke-gatefix/` | one-off verification (1 run) that the container gate mounts the sealed hidden set, after the defect that aborted the 2026-08-17 attempt. **Harness evidence, NOT a measurement** — a single C2 cell run to confirm the hidden gate reports a real verdict instead of `awaiting_human` | `report/screening-batch1/` (the fix it verifies is PR #21) |
| `screening-batch1/` | screening batch 1 relaunch, **COMPLETE (122 runs / 42 cells) but NOT yet a dataset anyone may read numbers from**. Repaired offline at zero model spend: 36 verdicts amended by re-running the sealed gates against the archived agent diffs after the container gate's git-ownership defect, 15 voided as unscoreable (`adjudication.json`), Product-B usage re-attributed under collector rules v2 and v3 (72 of 77 legs). 17 runs were cut short by batch 1's flat 1800s bound and their cells are refused by every grader | `report/screening-batch1/` — **PENDING**, opens at CP-DATA; holds `backfill.json` (v1), `backfill-v2.json`, `backfill-v3.json`, `decision-table.{json,md}`. The batch's own `results/screening-batch1/batch1.log` is the running record, including the post-batch repair pass |
| `screening-batch1-makeup/` | the W3 makeup pass (4 arms × 2 reps) under the per-task `agent_timeout_s` pin (7200s), which is what lets the W3-escalation registration be graded. Launched under an approved CP-SPEND with `scripts/screening-batch1-makeup-driver.sh` (profile `w3`); **in flight — no cell here is a result yet**. A separate dataset on purpose: cells run under different instrument settings never merge | `report/screening-batch1-makeup/` (pairs by name) once it exists |
| `screening-batch1-makeup-w6/` | **not yet created** — the W6 makeup pass (5 arms × 3 reps, 1200s pin) under the fixed review-delivery instrument. Batch 1's 15 W6 cells are VOID: the artifact under review was never delivered to the agent, so nothing there is a measurement of anything. `scripts/screening-batch1-makeup-driver.sh --profile w6`; a live run needs CP-SPEND and the sealed `review-diff.patch` on the host. Never merged with batch 1's void W6 cells — the fix changes the instrument | `report/screening-batch1-makeup-w6/` (pairs by name) once it exists |
| `screening-batchN/` | **not yet created** — Phase-4 screening batches beyond batch 1 (W1–W7 × configurations); one directory per batch, same append-only rule as feasibility | `report/screening-batchN/` (pairs by name; `decision-table.{json,md}` from `harness/telemetry/summarize.py`) |
| `cohort/` | **gitignored** — workshop exercise data (not tracked) | — |

Notes:
- **NON-COMPARATIVE, internal-only.** No number in any dataset here is a vendor claim; no
  figure appears in docs/site/report until CP-FINDINGS (SPEC §1.2 claims register).
- `feasibility-warm-series/` is its own dataset on purpose: it is the standing warm-cache
  evidence and must not be averaged into the batch-3 controlled 27.
- Superseded datasets are **immutable provenance** — do not edit or re-run them.
