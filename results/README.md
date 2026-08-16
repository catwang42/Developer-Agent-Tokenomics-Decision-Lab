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
| `pilot-reference/` | empty until CP-FINDINGS (≥5 reps/cell; write-protected; human merges only) | — (populated at CP-FINDINGS) |
| `screening/` | empty until Phase 4 (hypothesis-seeking positioning evidence, SPEC §5) | — (populated in Phase 4) |
| `screening-batchN/` | **not yet created** — Phase-4 screening batches (W1–W7 × configurations); one directory per batch, same append-only rule as feasibility | `report/screening-batchN/` (pairs by name; `decision-table.{json,md}` from `harness/telemetry/summarize.py`) |
| `cohort/` | **gitignored** — workshop exercise data (not tracked) | — |

Notes:
- **NON-COMPARATIVE, internal-only.** No number in any dataset here is a vendor claim; no
  figure appears in docs/site/report until CP-FINDINGS (SPEC §1.2 claims register).
- `feasibility-warm-series/` is its own dataset on purpose: it is the standing warm-cache
  evidence and must not be averaged into the batch-3 controlled 27.
- Superseded datasets are **immutable provenance** — do not edit or re-run them.
