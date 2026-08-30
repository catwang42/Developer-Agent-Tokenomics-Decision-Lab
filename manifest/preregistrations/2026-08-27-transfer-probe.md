# Transfer probe — do benchmark-winning routing strategies survive a priced oracle?

**Registered:** 2026-08-27, before any probe instrument work merged. Human-authored.
**Result published either way.**

## What is being tested

lexha-redstone/tokenomics-benchmark-multi-llms ranks routing strategies on 148
BigCodeBench-Hard tasks where verification is a free, instant, honest unit test. This
probe asks whether that ranking survives tasks where "done" is a priced human merge
decision and the grader is imperfect.

**Transplant set**, specs frozen verbatim from that repo @
`1a18b04385f9a0da16439ba5f48a2f68ac08d53d`, hashed into `harness/policies/transfer/`:

- **r9** — escalate-on-evidence; their recommended default. Gate *reads* the cheap
  model's failure evidence.
- **r6** — opus-after-ladder; their accuracy champion. Gate *counts* rung failures,
  does not read content.
- **r10** — opus-fresh-solve; discards the cheap attempt and re-solves. Gate consumes
  none of the cheap model's output.

The three form a gradient in how much each strategy trusts the cheap model's output.
That is the variable this probe manipulates. r10 is the control arm and is not
optional.

**Anchors already measured:** P0 = their r0b (claude-opus-5, exact model match);
C2 ≈ their r0a (sonnet 4.6 here vs 5 there — approximate, labeled as such).

## Registered scope

{W6, W4b, W4} × {r9, r6, r10} × rep1–3 = 27 cells, dataset `results/transfer-probe`.
W3 is deferred to the next batch (per-run wall-clock of 2–5h under run-to-completion
budgets does not fit this cycle); no W3 prediction is graded here. Easy-tier tasks
(pilot, W1) are excluded: every arm already passes 3/3, so a ladder collapses to its
first rung and the run carries no information. W1b is excluded as redundant with W4b
as the red-zone sample.

## Predictions (frozen before any run)

**W4 (bugfix — arms separate, cheap tier passes): transfer HOLDS.** Every ladder
collapses to its cheapest passing rung (Flash-Med and Sonnet pass 3/3 here), so all
three strategies land at ≈ cheap-solo cost and equal acceptance. Ordering preserved.

**W6 (review — arms separate, grader imperfect): transfer BREAKS, ordered by
evidence-dependence** — r10 transfers best, r6 partially, r9 worst.

Mechanism, grounded in measurements already in hand
(`report/findings/stopwatch-review-2026-08-26.md`, adjudicated 2026-08-26):

1. W6's sealed gate scores a review report by **line proximity** — a claim counts as
   detected only within ±3 lines of a seeded defect. A substantively correct claim
   reported 22 lines off scored as both MISSED and FABRICATED, and that single offset
   is what failed the run. Merge-readiness on this task is therefore **not** a
   property any runtime-visible signal reports.
2. Transplanted gates can only route on runtime-visible signals. r6's failure-count
   gate under-fires, because rejected work passes the public checks
   (measured: `w6…C2__rep2` public_gate=pass, sealed verdict=rejected).
3. r9's digest reads the cheap model's own report. On this task that report is
   fluent, coherent, and locationally wrong — so the gate sees confidence and does
   **not** escalate, while the sealed gate rejects. r9 under-escalates for the same
   reason a human would have to read the code to catch it.
4. r10 never consumes the cheap output, so no corrupted signal reaches its decision.

**W4b (red zone — every measured arm 0/3): cost-of-failure ordering.** All three
strategies predicted 0/3 accepted; the finding is the **bill**, predicted
r6 > r9 ≈ r10, because r6 buys every rung before escalating while r9 and r10 buy
cheap-plus-one-expensive. This is a measurement the source benchmark structurally
cannot produce: its task pool contains no task its arms cannot solve.

**Registered escalation break-even:** escalation beats expensive-solo iff
`p_cheap > C_cheap / C_exp`. On W6: threshold 44%, observed Sonnet p = 33% →
predicted narrow loss on model cost alone, widening once human review minutes are
priced in.

**Rank-inversion prediction:** r10 ranks third in the source leaderboard
($0.0417/solved vs r9's $0.0353). If r10 outranks r9 on W6, that is a rank inversion
caused by a named mechanism, not noise.

## Calibration gate — runs before any transplant

Each reimplemented strategy runs a 5-task BigCodeBench-Hard slice under the source's
own unit-test oracle and must (a) match the published per-task pass/fail on ≥4 of 5
and (b) land within ±30% of the published arm cost. The runner evaluates this itself
and exits non-zero on failure; the probe driver refuses to start without a passing
report for every strategy.

**Fail → stop.** The fidelity finding is published instead of a transfer verdict.

## Graded question

Rank preservation: does the source ordering of {r9, r6, r10, r0a, r0b} on acceptance
and cost-per-accepted-outcome survive the oracle change, per task? Plus the red-zone
cost-of-failure ordering on W4b. HEAC (human review minutes at the declared rate)
computed for every W6 arm.

## Scope and limits

n=3 reps supports **categorical** claims only — acceptance flips, rank inversions,
off-map report counts, cost-of-failure ordering, HEAC-order reversals. No effect-size
claims, no percentage comparisons against the source's n=148 figures.

"Fabricated" in this instrument means a report falling outside the ±3-line window. It
does **not** mean a false claim, and must not be reported as one.

Budgets run to completion: overrun emits a warning and is stamped in the run record;
hard stop only at 3× the task budget. Spend cap for calibration + probe combined:
$300 (`manifest/cp-spend-transfer-probe.md`).

## Amendment 1 — recorded 2026-08-28, before any calibration result exists
Criterion (a) governs transplant fidelity and remains binding: any (a) failure
stops the probe. Criterion (b) compares a Product-A ladder's bill to the source's
Gemini ladder; judgment call J-2 (rung identity substituted, rung count preserved)
makes ±30% potentially unreachable for reasons unrelated to fidelity. Therefore:
if calibration passes (a) for every strategy and fails only (b), the probe
proceeds, and the (b) gap is published as a priced-substitution limitation
attached to every transfer verdict. Authored by Catherine.

## Amendment 2 — recorded 2026-08-28 SGT, before any strategy calibration result exists
Calibration refused in pre-flight: BigCodeBench/101's reference tests fetch a
remote URL at test time and all four error (HTTP 403) from this environment, so
the oracle cannot score the source's own canonical solution. No model was called,
$0 was spent, and r9/r6/r10 were never executed, so no strategy result existed
when this was written.
Disposition: BigCodeBench/101 is REPLACED in the calibration slice, not dropped,
preserving the registered >=4-of-5 threshold. Replacement rule (mechanical, no
model involvement): the lowest-numbered task in the source's published
BigCodeBench-Hard run set, not already in the slice, whose canonical solution
grades PASS with network disabled in this environment. The selected id and its
record_sha256 are recorded in harness/policies/transfer/calibration-slice.yaml.
Finding recorded: 1 of 5 sampled source tasks has a non-hermetic oracle
(test-time third-party fetch). To be reported to the source repo's author.
Note: dates in this file are SGT; Amendment 1's 2026-08-28 is SGT (UTC 08-27).
Authored by Catherine.

## Amendment 3 — recorded 2026-08-28 SGT, after calibration verdicts, before any probe result
Calibration outcome: r6 and r10 pass criterion (a) 5/5; r9 fails (a) at 3/5, with
a diagnosed mechanism — its evidence gate received ~30-70 input tokens of
stderr reconstructed from unit tests, versus ~10k tokens of typed evidence the
source fed from an external capture harness that is not vendored in the public
repo (J-11). r9 is therefore not reproducible from published artifacts.
Disposition: r9 is EXCLUDED from this cycle's probe and its calibration failure
is published as the fidelity finding the base rule promises. r6 and r10 proceed
under Amendment 1 ((a) pass, (b)-only failure). Probe scope: {W6, W4b, W4} x
{r6, r10} x rep1-3 = 18 cells.
The (b) gaps (+1179% r6, +1022% r10) exceed the +-30% frame by far: source-vs-lab
cost comparisons are NOT meaningful under the J-2 substitution and none will be
published; cost claims are within-lab only, as the prereg's scope section states.
Prediction restated: the r9-worst leg of the evidence-dependence ordering is
untestable this cycle; the graded comparison is r10 vs r6 vs anchors.
Authored by Catherine.

## Amendment 4 — recorded 2026-08-30 SGT, before any r9 probe cell exists
r9 re-enters the probe if and only if a repaired evidence path passes
calibration criterion (a) at 5/5 — the same gate every strategy faced,
threshold unchanged. The repair may alter only HOW failure evidence is captured
and digested; it may consist of installing the source's own capture harness
(ctx-harness, github.com/vamsiramakrishnan/straitjacket) at a pinned commit,
recorded in the spec's provenance with "author confirmation pending". Gate
logic, thresholds and prompts stay verbatim from the frozen spec. Iterating the
evidence mechanism against the source's published rows is calibration, not
tuning: it fits the reimplementation to THEIR measured behaviour. Max 2
calibration iterations. Predictions for r9 remain those frozen 2026-08-27
(transfers worst, by mechanism). On pass: +9 cells ({W6,W4b,W4} x rep1-3),
within the existing $300 cap. On fail, or no pass by 22:00 SGT 2026-08-30:
r9 stays excluded, the fidelity finding stands, consolidation proceeds without
it. Authored by Catherine.

## Amendment 5 — recorded 2026-08-30 SGT, after the Amendment-4 result (4/5) was known
Amendment 4's window closed with r9 at 4/5. The one mismatched cell
(BigCodeBench/147, published fail / measured pass) was decided by the cheap
rung passing at turn 2 — the evidence gate never fired there, so the mismatch
comes from rung-model substitution (J-2), the same artifact Amendment 1
already waived for cost comparisons, not from the evidence path. Every cell
the evidence gate actually influenced matched, including 93, which the
Amendment-4 repair flipped. On that basis r9's 9 cells ({W4,W6,W4b} x
rep1-3) run tonight as an EXPLORATORY arm: reported in its own tier, never
pooled or ranked with the confirmatory r6/r10 cells, and every r9 figure
labelled "entered by post-result Amendment 5". Predictions for r9 remain
those frozen 2026-08-27. Calibration dir:
results/transfer-probe-calibration-amd4. Spend: up to $120 within the $300
cap. This amendment was written after seeing the 4/5; that timing is part of
the record. Authored by Catherine.
