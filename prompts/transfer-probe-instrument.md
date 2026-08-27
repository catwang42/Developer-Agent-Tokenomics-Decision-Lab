# Transfer-probe instrument. No spend. No agent runs. results/ and manifest/ read-only.

Prereg (authoritative): manifest/preregistrations/2026-08-27-transfer-probe.md
Read it first. If anything below contradicts it, the prereg wins — stop and say so.

Tasks A and B are independent — run as parallel subagents; C–F sequential after.

## A. Freeze the strategy specs (network: raw.githubusercontent.com allowed)
From lexha-redstone/tokenomics-benchmark-multi-llms at the sha in the prereg,
extract THREE strategies verbatim into harness/policies/transfer/:
  r9-spec.yaml  — escalate-on-evidence: digest prompt, threshold, escalation rule
  r6-spec.yaml  — opus-after-ladder: rung order, failure-count trigger
  r10-spec.yaml — opus-fresh-solve: discard rule, what (if anything) carries over
Each spec records: source repo+sha, source file paths, sha256 of extracted content,
and every judgment call made (list them; zero is suspicious). Do not paraphrase
prompts. r0a/r0b map to our C2/P0 — record the sonnet version mismatch on r0a.

## B. Timeout parity re-pin + run-to-completion (probe profile ONLY)
New driver profile `transfer-probe`: per-task --print-timeout = the task's
agent_timeout_s (adapter needs print < kill; move both together). Batch-1 pins
untouched. Budgets warn-don't-kill: at task budget emit overrun_flag + warning and
continue; hard kill only at 3x budget. Stamp overrun_s. NEW ARM condition; the
dataset marker says so.

## C. Strategy adapters
harness/adapters/transfer_r9.py, transfer_r6.py, transfer_r10.py, driven ONLY by
the spec yamls. Legs use existing claude_code.py / agy.py adapters (JSON usage
capture live; provider-side collector still runs as cross-check). Emit routing
events: per attempt, which rung/gate fired, the gate's input evidence verbatim,
the decision. frontier_token_share per run.

## D. Calibration path — gate is AUTOMATIC
Runner executes each strategy over a 5-task BigCodeBench-Hard slice (their public
task jsonl; the 5 task ids pinned in the spec dir) under the source's own
unit-test oracle, into results/transfer-probe-calibration. Grading = their oracle,
cost = ours. It evaluates the prereg criterion ITSELF (>=4/5 pass match AND cost
within +-30%) and exits non-zero on failure, writing a report either way. The
probe driver (E) refuses to start without a passing report for EVERY strategy.

## E. Probe driver plan
Dataset results/transfer-probe. Cells:
  W6  x {r9, r6, r10} x rep1-3   (9 runs)
  W4b x {r9, r6, r10} x rep1-3   (9 runs)
  W4  x {r9, r6, r10} x rep1-3   (9 runs)
27 runs. Run order: W4 first (shortest), then W6, then W4b. Spend cap $300 shared
with calibration. Print the two launch commands (calibration, then probe) verbatim;
do not launch either.

## F. Tests + report
Tests: spec loading; each gate's logic from fixture evidence — including a fixture
where the cheap report is fluent but locationally wrong and r9 must NOT escalate
(that is the registered mechanism); overrun stamping; calibration evaluation.
bash tests/run-tests.sh green. Report: SPECS / REPIN / ADAPTERS / CALIB-PATH /
PLAN / LAUNCH-CMDS / TESTS / JUDGMENT-CALLS / SURPRISES. Stop. No merge, no launch.
