# Screening batch 1 — report folder

**STATUS: PENDING** — the batch is incomplete. This folder holds collector artifacts
only; there is no report in it yet, and **no figure here may be read as a result**.
The telemetry-completeness report opens at CP-DATA, once the registered matrix has
either run or been accounted for cell by cell.

Pairs with the dataset `results/screening-batch1/` (CLAUDE.md rule 8).

## What is in here now

| File | What it is |
|---|---|
| `backfill.json` | provider-meter backfill for the Product-B legs of the runs completed so far, written by the collector after the batch halted. Includes the contamination guard's refusals — a refusal is `unavailable`, never zero. |

## State of the batch (as of 2026-08-18)

- **15 of 126** registered cells completed and validated — all of them on the pilot
  task (`tasks/pilot-realworld`). No other roster task has run.
- **3 cells deferred-contaminated** (pilot C3 rep3, C3-prev rep3, C5 rep3). They never
  ran and cost nothing. They are **holes** in the registered matrix, to be filled by a
  later makeup pass, and must be reported as holes — never averaged over.
- **1 cell refused by the contamination guard** (pilot C5 rep2): its Product-B usage
  stays `unavailable`. See the LIMITATION note appended to
  `results/screening-batch1/batch1.log` for why the refusal stands.
- **Halted at plan index 19** (`W4-complex-bugfix P0 rep1`): the runner's mid-batch
  auto-build baked uid 1001 instead of the host uid, so the credential mounts were
  unreadable and the image guard refused. Fixed on branch `fix/auto-build-host-uid`.

Because the completed cells cover one task and five of seven arms unevenly, **nothing
in this folder supports a comparison of any kind** — not between arms, not between
products, not between tasks.
