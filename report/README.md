# report/ — index of screening datasets and the reports they feed

126 planned boxes, 153 runs bought, 117 filled, 9 empty with reasons below.

**NON-COMPARATIVE / INTERNAL.** No number in any dataset below is a vendor claim, and
none may appear in the docs, on the site, or in any external-facing report before
**CP-FINDINGS** (SPEC §1.2 claims register). Every screening report is **PENDING** — the
folders exist, but they open at **CP-DATA**.

## Index

| Dataset (`results/`) | What it is | Runs | Report its numbers feed |
|---|---|---|---|
| `screening-batch1/` | Screening batch 1 relaunch, 42 cells; repaired offline at zero model spend (36 verdicts amended by re-running the sealed gates against archived diffs, 15 voided as unscoreable, Product-B usage re-attributed under collector rules v2/v3) | 122 | `report/screening-batch1/` — PENDING; holds `README.md`, `decision-table.{json,md}`, `backfill.json`, `backfill-v2.json`, `backfill-v3.json` |
| `screening-batch1-makeup/` | The W3 makeup pass, 4 cells — 4 arms × 2 reps re-run under the per-task `agent_timeout_s` pin (7200s), which is what lets the W3-escalation registration be graded | 8 | No paired folder — feeds `report/findings/consolidated-table.md` (and `regrade-v2.md`) |
| `screening-batch1-makeup-w6/` | The W6 makeup pass, 5 cells — 5 arms × 3 reps at the 1200s pin under the fixed review-delivery instrument, replacing batch 1's 15 void W6 cells (the artifact under review was never delivered) | 15 | No paired folder — feeds `report/findings/consolidated-table.md` (and `regrade-v2.md`) |
| `screening-batch1-confound-makeup/` | The confound makeup, 5 cells — named replacement slots for runs earlier bounds cut short, each re-bought under its own task's pinned budget; 8 of 11 planned slots ran, 3 were refused by the contamination guard and never billed | 8 | `report/screening-batch1-confound-makeup/` — PENDING; holds `backfill-v3.json`. Also feeds `report/findings/consolidated-table.md` |
| `screening-batch1-aborted-20260817-gatefix/` | **Not a screening result.** Batch 1's first attempt, halted by the kill switch at 5/126 runs when `container_gate()` never mounted the sealed hidden set and every run graded `acceptance.result: error`. Telemetry is real; the outcome variable is absent, so no cell is gradable. Retained as provenance for $1.86 of real spend | 5 | None — no CP-DATA report; its own `batch1.log` is the record |

Run counts reconcile: 122 + 8 + 15 + 8 = **153 runs bought** across the four screening
datasets, of which **117** fill a slot and **36** are superseded (a slot's later attempt
supersedes the earlier one; attempts are never pooled or averaged). The aborted dataset's
5 runs are outside this accounting.

## The 9 empty boxes

42 cells × 3 registered reps = **126** slots; 117 are filled, so 9 are empty. None of
them is unexplained missing data.

**Refused by the contamination guard (7).** Re-bought under an approved CP-SPEND, then
refused at the door: the collector measured background traffic on the subject model and
would not start, because a cost attributed across someone else's traffic is not a
measurement. **Nothing was billed and nothing was run.** The remedy is a quiet window.

- `pilot-realworld-draft-articles` **C3** rep 3
- `pilot-realworld-draft-articles` **C3-prev** rep 3
- `pilot-realworld-draft-articles` **C5** rep 3
- `w3-sqlfluff-segment-method-migration` **C5** reps 1, 2 and 3
- `w4-realworld-missing-user-id` **C3** rep 2

**Budget exhaustion (2).** Every attempt ran out of wall-clock, and the slot was re-bought
at least once under a longer budget before being cut off again. *Does not complete within
the budget we bought* is the result for that slot — a finding, not a hole.

- `w3-sqlfluff-segment-method-migration` **P0** rep 1 (1812s, then 7210s)
- `w3-sqlfluff-segment-method-migration` **P1** rep 1 (3642s, then 9453s)

One cell, `w3-sqlfluff-segment-method-migration::C5`, therefore has no evidence at all and
is reported with no verdict — which is not the same statement as a rejection.

> **Slot-count note.** `report/findings/consolidated-table.{md,json}` currently reads
> "117 of 122" and carries `n_slots: 122`. That figure does not reconcile with its own
> per-cell data (all 42 cells register 3 reps → 126). The per-cell figures above are the
> verified ones; the header is queued for correction in the consolidation step.

## Coming Friday

The **transfer-probe** datasets land Friday and will be added to this index — name,
description, run count and the report they feed, on the same terms as the rows above.

## The rest of report/

- `REPORT-SPEC.md` — what a report must contain.
- `findings/` — cross-cutting investigations that are not scoped to one dataset: the
  gate-fairness audit, the subject-isolation leak and its verification, the W1
  coverage ceiling, model-pin resolution, the Vertex token-metric surface, the
  regrade-v2 sweep, graded-quality extraction, the confound-makeup enumeration, the
  `agy` JSON-flag defect, and the consolidated screening table (**PENDING**, opens at
  CP-FINDINGS).
- `smoke-screening/` — the screening smoke and the re-smoke that verified its fixes.
  **Harness evidence, not measurements.** Its dataset was removed in the 2026-08-27
  cleanup; see the note in `smoke-screening/smoke-report.md`.
- `workshop-dashboard/` — dashboard spec.

Only `README.md` and `REPORT-SPEC.md` live directly in `report/`.

## Provenance

The feasibility-era reports (`batch1/`, `batch2/`, `batch3/`) and every non-screening
dataset under `results/` were removed in the 2026-08-27 repo cleanup. They are recoverable
in full at the tag **`pre-cleanup-2026-08-27`**.
