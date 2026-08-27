# results/ — datasets and the report that documents each

Every dataset directory below names the **report that documents it**. Where a dataset has
no paired report folder, its numbers are read out in a cross-cutting finding instead —
that is stated per row, not left implicit. The index with run counts and the slot
accounting lives in [`report/README.md`](../report/README.md).

**NON-COMPARATIVE, internal-only.** No number in any dataset here is a vendor claim; no
figure appears in docs/site/report until CP-FINDINGS (SPEC §1.2 claims register). Every
screening report is **PENDING** and opens at **CP-DATA**.

| Directory | What it is | Documented by |
|---|---|---|
| `screening-batch1/` | Screening batch 1 relaunch, **COMPLETE (122 runs / 42 cells) but NOT yet a dataset anyone may read numbers from**. Repaired offline at zero model spend: 36 verdicts amended by re-running the sealed gates against the archived agent diffs after the container gate's git-ownership defect, 15 voided as unscoreable (`adjudication.json`), Product-B usage re-attributed under collector rules v2 and v3. 17 runs were cut short by batch 1's flat 1800s bound and their cells are refused by every grader | `report/screening-batch1/` — **PENDING**, opens at CP-DATA; holds `README.md`, `decision-table.{json,md}`, `backfill.json`, `backfill-v2.json`, `backfill-v3.json`. The batch's own `batch1.log` is the running record, including the post-batch repair pass |
| `screening-batch1-makeup/` | The W3 makeup pass, **COMPLETE (8 runs / 4 cells)** — 4 arms × 2 reps under the per-task `agent_timeout_s` pin (7200s), which is what lets the W3-escalation registration be graded. Run 2026-08-20 under an approved CP-SPEND with `scripts/screening-batch1-makeup-driver.sh --profile w3`; Product-B legs attributed under collector rule v2. 2 of the 8 runs (P0 rep1, P1 rep1) hit the 7200s bound and are truncated — refused by every grader, and a budget-exhaustion finding rather than a hole, since both were also truncated at 1800s in batch 1. A separate dataset on purpose: cells run under different instrument settings never merge | **No paired report folder.** Read out in `report/findings/consolidated-table.md` (**PENDING**, opens at CP-FINDINGS) and `report/findings/regrade-v2.md` |
| `screening-batch1-makeup-w6/` | The W6 makeup pass, **COMPLETE (15 runs / 5 cells)** — 5 arms × 3 reps at the 1200s pin under the fixed review-delivery instrument. Batch 1's 15 W6 cells are VOID: the artifact under review was never delivered to the agent, so nothing there is a measurement of anything. Run 2026-08-20 under an approved CP-SPEND with `scripts/screening-batch1-makeup-driver.sh --profile w6`; Product-B legs attributed under collector rule v3. 1 run (C2 rep2) hit the 1200s bound and is truncated; its replacement slot is in `screening-batch1-confound-makeup/`. Never merged with batch 1's void W6 cells — the fix changes the instrument | **No paired report folder.** Read out in `report/findings/consolidated-table.md` (**PENDING**, opens at CP-FINDINGS) and `report/findings/regrade-v2.md` |
| `screening-batch1-confound-makeup/` | The confound makeup, **COMPLETE AS RUN: 8 of 11 planned slots (5 cells); 3 refused, never run**. Named replacement slots for the cells that batch 1's flat 1800s bound (and, for W6 C2 rep2, the W6 makeup's 1200s bound) cut short — not a rep panel: each slot is one specific censored `(task, config, rep)`, re-bought under its own task's pinned budget, enumerated in `report/findings/confound-makeup-enumeration.log`. Run 2026-08-21 under an approved CP-SPEND (cap $150; known spend floor $56.09, 3 legs `unavailable`) with `scripts/screening-batch1-makeup-driver.sh --profile confound`; Product-B legs attributed under collector rule v3. **W3 C5 reps 1–3 were deferred by the contamination guard** — background traffic on the subject model after 4 probes, so nothing was billed and nothing was run; `deferred-contaminated.tsv` records them and they stay holes. First dataset graded live under the PR #27 content-hashed gate images, which is why its W6 run clears `P5-no-leakage` where every pre-fix W6 run failed it. A truncated original and its replacement are never pooled | `report/screening-batch1-confound-makeup/` — **PENDING**, opens at CP-DATA; holds `backfill-v3.json`. Cross-dataset reading is in `report/findings/consolidated-table.md` (**PENDING**, opens at CP-FINDINGS) |
| `screening-batch1-aborted-20260817-gatefix/` | Screening batch 1, **ABORTED at 5/126 runs — NOT a screening result**. Halted by kill switch when every run graded `acceptance.result: error`: `container_gate()` never mounted the sealed hidden set, so the hidden gate reported `awaiting_human` on every containerized run. Telemetry is real and validated; the *outcome* variable is absent, so no cell is gradable. Retained as provenance for $1.86 of real spend | its own `batch1.log` (header note + `HALTED BY OPERATOR` record); no CP-DATA report — there is nothing to report on |
| `pilot-reference/` | empty until CP-FINDINGS (≥5 reps/cell; write-protected; human merges only) | — (populated at CP-FINDINGS) |
| `screening/` | empty until further Phase-4 screening (hypothesis-seeking positioning evidence, SPEC §5) | — (populated when used) |
| `screening-batchN/` | **not yet created** — Phase-4 screening batches beyond batch 1 (W1–W7 × configurations); one directory per batch, same append-only rule | `report/screening-batchN/` (pairs by name; `decision-table.{json,md}` from `harness/telemetry/summarize.py`) |
| `cohort/` | **gitignored** — workshop exercise data (not tracked) | — |

Notes:
- **Superseded per rep, never pooled.** A slot is `(task_id, configuration_id, rep)`, and
  the latest attempt that is neither truncated nor adjudicated void fills it. A cell run
  under batch 1's flat bound and the same cell re-run under its own pinned budget are two
  instruments; averaging them would report a number no run produced.
- Datasets are **immutable provenance** — do not edit or re-run them.
- The **transfer-probe** datasets land Friday and will be added to this table and to
  `report/README.md`.

## Removed in the 2026-08-27 cleanup

The feasibility-era datasets (`feasibility/`, `feasibility-batch2/`, `feasibility-batch3/`,
`feasibility-warm-series/`), the one-off `revalidation/`, `smoke/` and `smoke-gatefix/`
verifications, and the `smoke-screening/` harness evidence were removed from the working
tree, along with their reports (`report/batch1/`, `report/batch2/`, `report/batch3/`).
They are recoverable in full at the tag **`pre-cleanup-2026-08-27`**.
