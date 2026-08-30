# Dataset timing profile: transfer-probe

Dataset: `results/transfer-probe`
Profile: **transfer-probe** — agent_timeout_s is a SOFT budget (stamped, not enforced); hard kill at 3x; --print-timeout re-pinned per task to agent_timeout_s

> **NEW ARM CONDITION.** This dataset did not run under the batch-1 timing contract.

The transfer probe measures the cost of failure, so an attempt that is cut off reports the budget instead of the bill. Under this profile the task's agent_timeout_s becomes a soft line: crossing it stamps overrun_flag and overrun_s on the leg's model_call_completed event, emits a warning, and the attempt continues. The hard kill moves to 3x, which is a backstop against a hung process rather than a budget.

Product B's --print-timeout is re-pinned per task to that same agent_timeout_s, which restores TIMEOUT PARITY: under the manifest's flat 15m0s pin a 2700s task budget gave Product B 900s and then a product error, so the two products were not being given the same amount of time to fail in. print < kill still holds by construction (T < 3T), so the product's own timeout still fires before ours.

This is a NEW ARM CONDITION. Runs under this profile are not comparable with batch-1 or batch-2 timing on duration, on truncation rate, or on any cost figure that a truncation would have bounded. Do not pool them.

## Resolved per task

| task | agent_timeout_s | soft budget | hard kill | --print-timeout |
|---|---|---|---|---|
| w4-realworld-missing-user-id | 1200 | 1200s | 3600s | 20m0s |
| w4b-zarr-consolidated-order | 2700 | 2700s | 8100s | 45m0s |
| w6-hono-router-review | 1200 | 1200s | 3600s | 20m0s |
## Calibration gate: OVERRIDDEN by a human

Reason recorded: **Amendment 1+5: (a) pass for r6/r10 (5/5) and r9 (4/5, Amendment-4 evidence repair), (b) waived; r9 runs as an EXPLORATORY arm, never pooled or ranked with r6/r10**

Invoked as `--calibration-override`. Scope: the CALIBRATION preflight refusal only. The spec, schema-enum, manifest-pin and results-README gates were satisfied, not waived, and `LAB_ALLOW_SPEND=1` was still required.

In-plan arms at launch: R6, R10, R9. Excluded: none — Amendment 5 re-entered R9 as an EXPLORATORY arm, reported in its own tier and never pooled or ranked with the confirmatory R6/R10 cells.

What the gate objected to, in its own words:

- r6: no calibration report at results/transfer-probe-calibration-amd4
- r10: no calibration report at results/transfer-probe-calibration-amd4
- r9: calibration verdict is 'fail', not 'pass'

The calibration reports were NOT edited. `results/transfer-probe-calibration/` records verdict `fail` for every strategy and is the evidence for this waiver, not a contradiction of it: the overall verdict fails on criterion (b), a source-vs-lab price comparison that Amendment 1 waived as unpassable under the J-2 model substitution. Criterion (a), the one that governs fidelity, passes: 5/5 for r6 and r10 in that directory. R9's criterion (a) is 4/5 and lives in a SEPARATE dataset, `results/transfer-probe-calibration-amd4/` (the Amendment-4 evidence-path repair); its superseded 3/5 report is still in `results/transfer-probe-calibration/`, so an r9 objection quoted above may be the stale one — read the amd4 report for r9.
