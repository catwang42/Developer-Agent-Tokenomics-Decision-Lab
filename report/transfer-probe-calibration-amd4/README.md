# R9 re-calibration under prereg Amendment 4 — report folder

**STATUS: PENDING** — opens at CP-DATA. Nothing here is a lab result. It is a
precondition record: five tasks, graded by the *source's* unit-test oracle, testing
whether our transplant of one published routing strategy is faithful. No figure here
is a claim about any product's capability, and no cost figure here will be published
(criterion (b) was waived as unpassable before the run — see below).

Pairs with the dataset `results/transfer-probe-calibration-amd4/` (CLAUDE.md rule 8).
Does **not** supersede `report/`-less `results/transfer-probe-calibration/`, which
remains the record of the 2026-08-27 three-arm run and the evidence behind
Amendment 3's R9 exclusion.

## Outcome, stated first

**R9 reached 4/5 on criterion (a). Amendment 4 requires 5/5. R9 does not re-enter the
probe.** The probe stays at 18 cells, {W4, W6, W4b} × {R6, R10} × 3 reps, and the
r9-worst leg of the evidence-dependence prediction stays untestable this cycle.

One iteration was run. A second was **declined on method grounds, not budget** — see
"Why there was no second iteration".

## What the repair changed

Amendment 4 permits a change to **how failure evidence is captured and digested, and
nothing else**. What changed: the cheap rung's stdout/stderr now goes through the
source's own `ContainedRun` wrapper (vendored byte-exact at
`harness/vendor/straitjacket.py`, from `lexha-redstone/tokenomics-benchmark-multi-llms`
@1a18b04), which drives `ctx-harness` 0.35.1
(`vamsiramakrishnan/straitjacket`@7c69ea7). The gate reads that flow's typed evidence
graph and is prompted with that flow's digest.

What did not change: gate logic, thresholds (`broad_failure_items: 3`), the digest
prompt, and the escalation rule are byte-identical in `r9-spec.yaml`. The level rules
are a single shared function — `_level_from_facts` in
`harness/adapters/transfer_spec.py` — called by both the evidence-graph path and the
old regex path, and `tests/test_vendored_straitjacket.py::TheGateDidNotMove` asserts
the two return the same level on the same facts. That test, plus the wrapper hash pin
and the "no module of ours imports `ctx` except the bridge" AST check, is what makes
the Amendment 4 promise machine-checkable rather than a claim in prose.

**The identification of `ctx-harness` as the harness behind the published rows is this
lab's inference** from the digest header, package name and API surface. It is recorded
in the spec as `author_confirmation: pending` and is not confirmed upstream. Every
report generated from a repaired-path run carries that caveat (J-13).

## Criterion (a): 4/5, and what moved

| task | category | published | measured | shape (published / ours) | match |
|---|---|---|---|---|---|
| BigCodeBench/13 | A_no_gate_fired_all_pass | pass | pass | cheap / cheap | ✅ |
| BigCodeBench/15 | AMENDMENT_2_REPLACEMENT | pass | pass | cheap-cheap / cheap-cheap | ✅ |
| BigCodeBench/93 | C_all_escalate_all_pass | pass | **pass** | cheap-cheap-frontier / cheap-cheap-frontier | ✅ **flipped** |
| BigCodeBench/147 | E_r9_fails_r6_passes | fail | pass | cheap-cheap-frontier / cheap-cheap | ❌ |
| BigCodeBench/241 | B_r9_only_early_escalation | pass | pass | cheap-frontier / cheap-cheap | ✅ |

Against the 2026-08-27 run (3/5), exactly one cell changed: **BigCodeBench/93 went
FAIL → PASS**. Its routing shape was already identical to the published one in both
runs, so what the repair bought was not a different route but a frontier turn that
succeeded — the frontier was handed the source's digest instead of stderr this lab had
reconstructed. That is the fidelity finding in one cell, and it is the reason
Amendment 4 was worth running.

`routing_shape_match` is **3/5, unchanged** from 2026-08-27 (13, 15, 93 match; 147 and
241 do not). The repair did not move any routing decision. Both shape mismatches are
cells where our cheap rung passed at a turn where the source's escalated — a
model-substitution effect (J-2), not an evidence effect.

Every gate decision in the run was `typed=True`, sourced
`ctx_harness_evidence_graph`. **Zero degraded cells** — no cell fell back to untyped
evidence, and there is no fallback path in the code to fall back through.
`frontier_reachability` passed (1 frontier call).

## Why there was no second iteration

Amendment 4 allows at most two. The remaining mismatch is BigCodeBench/147: published
**fail**, ours **pass**, closed out at turn 2 by the cheap rung. The evidence gate never
reached a decision that could have differed, because there was no third turn to route.

To match, our cheap rung would have to *fail* a task the source's cheap rung failed.
Nothing inside Amendment 4's permitted scope can cause that: it is the J-2 model
substitution, not the evidence tier. The only levers that would move it are the gate,
the thresholds or the model ladder — all of which Amendment 4 forbids and the amendment
was written to forbid.

Re-running the identical configuration and hoping sampling noise flips 147 is the one
thing that would have "worked", and it is p-hacking against a pre-registered criterion.
The second iteration was not spent. **Recorded spend for this work: $1.1539 of the $10
cap, and $1.1539 against the probe's shared $300 cap.**

## Token volume: the "29 input tokens" figure, resolved

The report's `token_volume_delta` diagnostic reads **input 29 / output 7,858** against a
published **10,347 / 11,492**. The 29 is not a measurement error and it is not the
prompt volume. `claude -p --output-format json` reports 2–3 *uncached* `input_tokens`
per call and puts the rest in `cache_creation_tokens` / `cache_read_tokens`;
`_sum_tokens` counts only `input_tokens` and `output_tokens`, which is what produces
figures in the tens.

Re-derived from this run's own event logs (10 model calls, all `authoritative`):

| class | tokens |
|---|---|
| `input_tokens` | 29 |
| `cache_creation_tokens` | 156,958 |
| `cache_read_tokens` | 44,072 |
| **prompt-side total** | **201,059** |
| `output_tokens` | 7,858 |
| `reasoning_tokens`, `tool_result_tokens` | `unavailable` (not exposed separately by the product JSON) — not zero |

So the honest comparison against the published ~10.3k prompt tokens is **201,059 —
about 19× the published figure, not a shortfall**. The excess is agentic-CLI overhead
(system prompt, tool definitions, tool results, per-turn re-priming), which is caveat
J-12 and is in the bill; it is not routing-prompt volume.

The volume that actually reaches the evidence gate is a third number, and the small
one: **3,564 characters of digest across 5 gate decisions (≈891 tokens, ≈713 chars per
decision)**. That is the source's own digest at its own length — `SJ_RAW_CAP` bounds it
long before the spec's character cap does.

`_sum_tokens` was deliberately **not** changed. Redefining it would silently break
comparability with the already-committed R6 and R10 reports, which is a worse outcome
than a diagnostic that needs this paragraph.

## Known defect in the committed artifact

`results/transfer-probe-calibration-amd4/r9/calibration-report.json` and
`calibration-report.md` were written by the pre-fix report builder and carry
`fidelity_caveats[1]` as the **old J-11 wording** — "the evidence the gate reads is
reconstructed from unittest stderr". **That sentence is false for this run.** The
builder now derives the caveat from the run's recorded provenance
(`_evidence_caveat`), so an arm that ran the capture harness emits J-13 and an arm that
did not emits J-11, and the two can no longer drift.

The artifact is left exactly as the run wrote it. Calibration reports are not edited
after the fact to say something different from what the run said (CLAUDE.md rule 8);
the correction lives here, and the code fix ships in the same PR.

## Criterion (b)

`cost_within_30pct` failed: $1.1539 measured vs $0.1401 published, δ = +7.24×. Expected
and non-informative — it compares a Product-A ladder's bill against a Gemini ladder's,
and Amendment 1 waived it as unpassable before any run. It is **not** evidence that the
routing logic differs; `routing_shape_match` is the diagnostic for that. No
source-vs-lab cost figure will be published.

## Files

| Path | What it is |
|---|---|
| `results/transfer-probe-calibration-amd4/r9/calibration-report.json` | the run's own report, as written, verdict `fail` |
| `results/transfer-probe-calibration-amd4/calibration-report.md` | roll-up, STATUS: PENDING |
| `results/transfer-probe-calibration-amd4/r9/BigCodeBench_*/events.jsonl` | the raw measurement — every token figure above is re-derivable from these |
| `harness/vendor/NOTICE.md` | provenance and licence for the vendored wrapper and the pinned harness |
