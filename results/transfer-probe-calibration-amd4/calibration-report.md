# Transfer-probe calibration

STATUS: PENDING (awaiting CP-DATA review) — calibration verdict: FAIL

Slice: `bcb-hard-5-2026-08-28-amd2` — 5 pinned BigCodeBench-Hard tasks.
Prereg: `manifest/preregistrations/2026-08-27-transfer-probe.md`

Grading is the SOURCE's own unit-test oracle. Cost is OURS. Nothing in this report is a claim about either product's general capability, and the slice is five tasks.

## Verdicts

| strategy | verdict | pass_match | cost (measured vs published) | frontier calls |
|---|---|---|---|---|
| r9 | **fail** | 4/5 | $1.1539 vs $0.1401 | 1 |

## Per task

### r9

| task | category | published | measured | shape (pub / ours) |
|---|---|---|---|---|
| BigCodeBench/13 | A_no_gate_fired_all_pass | pass | pass | cheap / cheap |
| BigCodeBench/15 | AMENDMENT_2_REPLACEMENT_uncategorised | pass | pass | cheap-cheap / cheap-cheap |
| BigCodeBench/93 | C_all_escalate_all_pass | pass | pass | cheap-cheap-frontier / cheap-cheap-frontier |
| BigCodeBench/147 | E_r9_fails_r6_passes | fail | pass | cheap-cheap-frontier / cheap-cheap |
| BigCodeBench/241 | B_r9_only_early_escalation | pass | pass | cheap-frontier / cheap-cheap |

## Fidelity caveats

- J-2: rung identity differs (three Product-A economical rungs vs three Gemini tiers). Rung COUNT and the frontier are preserved.
- J-11: the evidence the gate reads is reconstructed from unittest stderr; the source's typed evidence came from an external capture harness that is not vendored.
- J-12: the subject is an agentic CLI, not a chat completion. Its final response text is graded; agentic overhead is in the bill.
- cost_criterion_blocker: criterion (b) compares two model families' prices and was shown unpassable before the run.
