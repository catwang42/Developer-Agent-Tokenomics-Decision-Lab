# Transfer probe, aborted 2026-08-30 (unauthenticated legs) — report folder

**STATUS: AUTHORITATIVE** — this is not a telemetry-completeness report and does not
compete with the one that is. It documents an instrument failure that produced **no
measurements**, so there is nothing here that opens at CP-DATA and nothing that could
ever reach CP-FINDINGS. It is complete as written.

Pairs with the dataset `results/transfer-probe-aborted-20260830-authfail/` (CLAUDE.md
rule 8). Does not supersede any report; nothing previously described this dataset.

## What the dataset is

Eleven R9 run directories produced on 2026-08-30 (UTC) in which the subject agent was
never reached. All 36 billing legs returned `"Not logged in · Please run /login"` with
`terminal_reason: api_error`, exit code 1, zero tokens and `$0.00`. Known spend for the
dataset is **$0.0000**.

The full account — root cause, the env comparison against the working 2026-08-27 R6/R10
batch, the per-run table, and the ledger note — is in the dataset's own
`README.md`. It is not duplicated here; that file is the record.

## Why there are no numbers in this folder

There is no decision table, no backfill and no completeness accounting, because there is
no telemetry to account for. Zero tokens across every leg is not a low measurement, it is
the absence of one. Writing a table of zeros would invite exactly the reading that must
not happen: that R9 is cheap.

The one figure worth stating is the negative one, and it belongs in the spend record
rather than in any result: **this dataset cost $0.00 against the $120 Amendment 5
allocation and the $300 CP-SPEND cap.** The false start and the aborted batch together
consumed none of the budget.

## Effect on the registered plan

None. The nine R9 slots ({W4, W6, W4b} × rep1–3) were re-bought after the launch
environment was corrected, and that data is in `results/transfer-probe/`. Prereg
Amendment 5 is unaffected: it registered nine exploratory R9 cells and nine were
ultimately bought. No amendment was needed for this, and none was written — an
authentication failure that bills nothing changes no registered condition.

Supersession does not apply between the two datasets. An unauthenticated no-op is not an
attempt at a slot, so the re-run is not "the latest attempt" over these eleven; they are
outside the slot accounting entirely, in the same way
`screening-batch1-aborted-20260817-gatefix/`'s five runs sit outside batch 1's.

## Follow-ups (not done tonight)

1. `completed_cells()` in `harness/runner/transfer_probe.py` treats any directory holding
   a `result.json` as settled and never retries it, and does not read `adjudication.json`.
   A void adjudication therefore cannot free a slot — the only remedy available tonight
   was to move the directories out of the dataset. Teaching the resume path to honour void
   adjudications would make this class of repair a documented act rather than a `mv`.
2. Operator docs should pin `CLAUDE_CODE_USE_VERTEX`, `ANTHROPIC_VERTEX_PROJECT_ID` and
   `CLOUD_ML_REGION` as part of the launch command for any live batch, and the driver
   could refuse to start a live run when they are absent from its own environment — a
   preflight refusal, in the same family as the existing RESULTS-README and CALIBRATION
   gates. That check would have cost nothing and saved the whole episode.

Both are batch-2 work.
