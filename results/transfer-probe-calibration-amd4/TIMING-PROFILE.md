# Dataset timing profile: transfer-probe

Dataset: `transfer-probe-calibration-amd4`
Profile: **transfer-probe** — agent_timeout_s is a SOFT budget (stamped, not enforced); hard kill at 3x; --print-timeout re-pinned per task to agent_timeout_s

> **NEW ARM CONDITION.** This dataset did not run under the batch-1 timing contract.

The transfer probe measures the cost of failure, so an attempt that is cut off reports the budget instead of the bill. Under this profile the task's agent_timeout_s becomes a soft line: crossing it stamps overrun_flag and overrun_s on the leg's model_call_completed event, emits a warning, and the attempt continues. The hard kill moves to 3x, which is a backstop against a hung process rather than a budget.

Product B's --print-timeout is re-pinned per task to that same agent_timeout_s, which restores TIMEOUT PARITY: under the manifest's flat 15m0s pin a 2700s task budget gave Product B 900s and then a product error, so the two products were not being given the same amount of time to fail in. print < kill still holds by construction (T < 3T), so the product's own timeout still fires before ours.

This is a NEW ARM CONDITION. Runs under this profile are not comparable with batch-1 or batch-2 timing on duration, on truncation rate, or on any cost figure that a truncation would have bounded. Do not pool them.

## Resolved per task

| task | agent_timeout_s | soft budget | hard kill | --print-timeout |
|---|---|---|---|---|
| BigCodeBench/13 | 600 | 600s | 1800s | 10m0s |
| BigCodeBench/147 | 600 | 600s | 1800s | 10m0s |
| BigCodeBench/15 | 600 | 600s | 1800s | 10m0s |
| BigCodeBench/241 | 600 | 600s | 1800s | 10m0s |
| BigCodeBench/93 | 600 | 600s | 1800s | 10m0s |
