# Consolidated screening table — every dataset, one row per cell

**STATUS: PENDING** — this document opens at **CP-FINDINGS**.

Generated 2026-08-23T10:56:01Z from `results/`; harness `afcf79c`. Zero model spend: nothing here re-runs an agent or a gate.

NON-COMPARATIVE / INTERNAL — descriptive per-cell figures only. No cross-product or cross-configuration ranking, no vendor claim, no model-efficiency attribution (CLAUDE.md rule 4, SPEC §1.2). Nothing here may appear in docs, on the site, or in any external-facing report before **CP-FINDINGS**.

## How a cell was filled

Datasets are **superseded per rep**, never pooled. A slot is `(task_id, configuration_id, rep)`, and the latest attempt that is neither truncated nor adjudicated void fills the slot; earlier attempts at the same slot are superseded, not averaged in. A cell run under batch 1's flat bound and the same cell re-run under its own pinned budget are two instruments; averaging them would report a number no run produced.

117 of 122 slots filled across 42 cells; 36 run(s) superseded. Datasets in scope: `screening-batch1`, `screening-batch1-makeup`, `screening-batch1-makeup-w6`, `screening-batch1-confound-makeup`.

**Accepted** is the pre-registered outcome and the only primary one. **Quality** is exploratory secondary, extracted from archived sealed output; it never overrides a verdict, and the two columns are expected to disagree — that disagreement is the point. A cost printed `≤` is a cache-blind upper bound on Product-B spend, not an exact figure.

**Cost rule** names the provider-window attribution rule each cell's Product-B tokens were drawn under — `v1` a silence-bounded window, `v2` serialized run ownership with an ingestion tail, `v3` the same window under a rate ceiling. A refused window still names its rule: the rule was applied, the tokens were withheld. Arms with no Product-B leg read `n/a`, because for them no window was ever drawn — that is not a missing measurement. A cell marked ⚠ spans more than one rule, so its reps were priced on more than one instrument and its median is not a like-for-like figure.

## Cells

| Task | Arm | Accepted | Quality (median) | Attempt cost (median) | Cost rule | Wall-clock s | Reps | Provenance |
|---|---|---|---|---|---|---|---|---|
| `pilot-realworld-draft-articles` | **C2** | 3/3 | — | $0.2260 | n/a | 78 | 3/3 | 3 regrade-v2 |
| `pilot-realworld-draft-articles` | **C3** | 2/2 | — | ≤$1.0032 | v1 | 276 | 2/3 ⚠ | 2 regrade-v2 |
| `pilot-realworld-draft-articles` | **C3-med** | 3/3 | — | ≤$0.8109 | v1 | 223 | 3/3 | 3 regrade-v2 |
| `pilot-realworld-draft-articles` | **C3-prev** | 2/2 | — | ≤$0.3797 | v1 | 132 | 2/3 ⚠ | 2 regrade-v2 |
| `pilot-realworld-draft-articles` | **C5** | 2/2 | — | ≤$1.0427 (n=1 of 2) | v1,v2,v3 ⚠ | 259 | 2/3 ⚠ | 2 regrade-v2 |
| `pilot-realworld-draft-articles` | **P0** | 3/3 | — | $0.5673 | n/a | 115 | 3/3 | 3 regrade-v2 |
| `w1-realworld-mapper-tests` | **C2** | 3/3 | 6/6 | $0.4061 | n/a | 94 | 3/3 | 3 regrade-v2, 3 changed |
| `w1-realworld-mapper-tests` | **C3** | 3/3 | 6/6 | ≤$1.0317 | v1 | 301 | 3/3 | 3 regrade-v2, 3 changed |
| `w1-realworld-mapper-tests` | **C3-med** | 3/3 | 6/6 | ≤$0.8777 | v1 | 217 | 3/3 | 3 regrade-v2, 3 changed |
| `w1-realworld-mapper-tests` | **C3-prev** | 3/3 | 6/6 | ≤$0.9860 | v1 | 207 | 3/3 | 3 regrade-v2, 3 changed |
| `w1-realworld-mapper-tests` | **C5** | 3/3 | 6/6 | ≤$2.0968 (n=2 of 3) | v1,v3 ⚠ | 436 | 3/3 | 1 original, 2 regrade-v2, 2 changed; 1 from `screening-batch1-confound-makeup` |
| `w1-realworld-mapper-tests` | **P0** | 3/3 | 6/6 | $0.6166 | n/a | 149 | 3/3 | 3 regrade-v2, 3 changed |
| `w1b-zarr-block-mask-properties` | **C2** | 0/3 | 7/7 | $1.8454 | n/a | 1309 | 3/3 | 3 regrade-v2 |
| `w1b-zarr-block-mask-properties` | **C3** | 0/3 | 7/7 | ≤$5.6937 | v1,v2,v3 ⚠ | 917 | 3/3 | 3 regrade-v2 |
| `w1b-zarr-block-mask-properties` | **C3-med** | 0/3 | 7/7 | ≤$4.8368 | v1,v2,v3 ⚠ | 832 | 3/3 | 3 regrade-v2 |
| `w1b-zarr-block-mask-properties` | **C3-prev** | 0/3 | 7/7 | ≤$6.2909 | v1,v2,v3 ⚠ | 635 | 3/3 | 3 regrade-v2 |
| `w1b-zarr-block-mask-properties` | **C5** | 0/3 | 7/7 | ≤$12.5686 | v1,v2,v3 ⚠ | 1765 | 3/3 | 3 regrade-v2 |
| `w1b-zarr-block-mask-properties` | **P0** | 0/3 | 7/7 | $3.3656 | n/a | 1228 | 3/3 | 1 original, 2 regrade-v2; 1 from `screening-batch1-confound-makeup` |
| `w3-sqlfluff-segment-method-migration` | **C2** | 0/3 | — | $7.3093 | n/a | 3236 | 3/3 | 1 original, 2 regrade-v2; 1 from `screening-batch1-confound-makeup`; 2 from `screening-batch1-makeup` |
| `w3-sqlfluff-segment-method-migration` | **C3** | 0/3 | — | ≤$8.3401 (n=1 of 3) | v1,v2,v3 ⚠ | 918 | 3/3 | 3 regrade-v2; 2 from `screening-batch1-makeup` |
| `w3-sqlfluff-segment-method-migration` | **C3-med** | 0/3 | — | ≤$8.2767 | v1,v2,v3 ⚠ | 912 | 3/3 | 3 regrade-v2 |
| `w3-sqlfluff-segment-method-migration` | **C3-prev** | 0/3 | — | ≤$9.8591 | v1,v2,v3 ⚠ | 913 | 3/3 | 3 regrade-v2 |
| `w3-sqlfluff-segment-method-migration` | **C5** | no gradable run | — | unavailable — no run filled this cell | — | — | 0/3 ⚠ | — |
| `w3-sqlfluff-segment-method-migration` | **P0** | 0/2 | — | $15.7401 | n/a | 5272 | 2/3 ⚠ | 1 original, 1 regrade-v2; 1 from `screening-batch1-confound-makeup`; 1 from `screening-batch1-makeup` |
| `w3-sqlfluff-segment-method-migration` | **P1** | 0/2 | — | $21.4868 | n/a | 8002 | 2/3 ⚠ | 1 original, 1 regrade-v2; 1 from `screening-batch1-confound-makeup`; 1 from `screening-batch1-makeup` |
| `w4-realworld-missing-user-id` | **C2** | 3/3 | — | $0.4465 | n/a | 112 | 3/3 | 3 regrade-v2 |
| `w4-realworld-missing-user-id` | **C3** | 1/2 | — | ≤$1.3939 | v1 | 328 | 2/3 ⚠ | 2 regrade-v2 |
| `w4-realworld-missing-user-id` | **C3-med** | 3/3 | — | ≤$0.6402 | v1 | 229 | 3/3 | 3 regrade-v2 |
| `w4-realworld-missing-user-id` | **C3-prev** | 0/3 | — | ≤$1.1796 | v1 | 228 | 3/3 | 3 regrade-v2 |
| `w4-realworld-missing-user-id` | **C5** | 2/3 | — | ≤$2.2357 | v1 | 450 | 3/3 | 3 regrade-v2 |
| `w4-realworld-missing-user-id` | **P0** | 3/3 | — | $0.7959 | n/a | 204 | 3/3 | 3 regrade-v2 |
| `w4b-zarr-consolidated-order` | **C2** | 0/3 | — | $0.7557 | n/a | 282 | 3/3 | 3 regrade-v2 |
| `w4b-zarr-consolidated-order` | **C3** | 0/3 | — | ≤$5.2385 | v1,v2,v3 ⚠ | 818 | 3/3 | 3 regrade-v2 |
| `w4b-zarr-consolidated-order` | **C3-med** | 0/3 | — | ≤$1.3857 | v1 | 917 | 3/3 | 3 regrade-v2 |
| `w4b-zarr-consolidated-order` | **C3-prev** | 0/3 | — | ≤$2.0892 | v1,v2,v3 ⚠ | 913 | 3/3 | 3 regrade-v2 |
| `w4b-zarr-consolidated-order` | **C5** | 0/3 | — | ≤$7.3831 (n=1 of 3) | v1,v2,v3 ⚠ | 1271 | 3/3 | 2 original, 1 regrade-v2; 2 from `screening-batch1-confound-makeup` |
| `w4b-zarr-consolidated-order` | **P0** | 0/3 | — | $1.1823 | n/a | 326 | 3/3 | 3 regrade-v2 |
| `w6-hono-router-review` | **C2** | 1/3 | 4/6, 1 fabricated | $1.4230 | n/a | 780 | 3/3 | 1 original, 2 regrade-v2, 1 changed; 1 from `screening-batch1-confound-makeup`; 2 from `screening-batch1-makeup-w6` |
| `w6-hono-router-review` | **C3** | 0/3 | 6/6, 3 fabricated | ≤$1.3797 | v3 | 352 | 3/3 | 3 regrade-v2; 3 from `screening-batch1-makeup-w6` |
| `w6-hono-router-review` | **C3-med** | 1/3 | 6/6, 4 fabricated | ≤$0.7409 | v3 | 231 | 3/3 | 3 regrade-v2, 1 changed; 3 from `screening-batch1-makeup-w6` |
| `w6-hono-router-review` | **C3-prev** | 0/3 | 5/6, 5 fabricated | ≤$0.8028 | v3 | 289 | 3/3 | 3 regrade-v2; 3 from `screening-batch1-makeup-w6` |
| `w6-hono-router-review` | **P0** | 3/3 | 6/6 | $3.2237 | n/a | 694 | 3/3 | 3 regrade-v2, 3 changed; 3 from `screening-batch1-makeup-w6` |

Quality metrics by task family: W1/W1b mutants caught, W3 sealed rules clean, W4b sealed assertions passed, W6 planted defects found (with fabrications counted separately and never netted off).

## Pre-registrations, graded

Graded over the superseded set above — the same graders the per-dataset table uses, given the runs that survived supersession. Published whichever way they come out, per the registration (CP-SCREEN-PREREG).

### H-effort (C3 vs C3-med) — status: `partial`, 2 task(s) graded

| Task | In scope | Verdict | Reduction | Gate parity |
|---|---|---|---|---|
| `pilot-realworld-draft-articles` | yes | `below_predicted_band` | 13.7% | holds |
| `w1-realworld-mapper-tests` | yes | `below_predicted_band` | 28.0% | holds |
| `w1b-zarr-block-mask-properties` | yes | `not_gradable` | — | — |
| `w3-sqlfluff-segment-method-migration` | yes | `not_gradable` | — | — |
| `w4-realworld-missing-user-id` | no | `exploratory_not_graded` | — | — |
| `w4b-zarr-consolidated-order` | no | `exploratory_not_graded` | — | — |
| `w6-hono-router-review` | no | `exploratory_not_graded` | — | — |

Predicted band: 30.0–50.0% reduction in cost per accepted outcome. Published either way, per the registration. A per-task verdict is a signal about that task under these pinned conditions; it is not a workload-class claim and not a product claim.

### W3 escalation (P1 vs C2) — outcome: `prediction_supported`

- Probe task(s): `w3-sqlfluff-segment-method-migration`
- Economical arm (C2) at the gate: `failed` — accepted 0/3
- Escalation branch: `observed` (2 of 2 probe run(s))
- Basis: the economical solo arm cleared no run of the gate and the escalation branch fired
- **Understrength:** the probe arm is graded on 2 run(s), not the registered 3 — see the limitation ledger.

## Limitation ledger

### Slots that are a finding, not a hole

Every attempt at these slots ran out of wall-clock, and the slot was re-bought at least once under a longer budget before being cut off again. *Does not complete within the budget we bought* is the result for that slot — it is not missing data.

- `w3-sqlfluff-segment-method-migration` **P0** rep 1 — 2 attempt(s): `screening-batch1` stop_reason=claude_timeout after 1812s; `screening-batch1-makeup` stop_reason=claude_timeout after 7210s
- `w3-sqlfluff-segment-method-migration` **P1** rep 1 — 2 attempt(s): `screening-batch1` stop_reason=claude_timeout after 3642s; `screening-batch1-makeup` stop_reason=claude_timeout after 9453s

### Slots that ARE missing data

None.

### Slots re-bought, then refused by the contamination guard

These slots WERE re-bought under an approved CP-SPEND. The collector then measured background traffic on the subject model and refused to start the run, because a cost attributed across someone else's traffic is not a measurement. **Nothing was billed and nothing was run.** They are holes, but the cause is the measurement window, not the model or the budget, and the remedy is to re-run them in a quiet window.

- `pilot-realworld-draft-articles` **C3** rep 3 — deferred 2026-08-18T02:15:21Z in `screening-batch1`.
- `pilot-realworld-draft-articles` **C3-prev** rep 3 — deferred 2026-08-18T03:46:51Z in `screening-batch1`.
- `pilot-realworld-draft-articles` **C5** rep 3 — deferred 2026-08-18T04:30:43Z in `screening-batch1`.
- `w3-sqlfluff-segment-method-migration` **C5** rep 1 — deferred 2026-08-21T10:06:22Z in `screening-batch1-confound-makeup`. Earlier attempt(s): `screening-batch1` stop_reason=claude_timeout after 2716s
- `w3-sqlfluff-segment-method-migration` **C5** rep 2 — deferred 2026-08-21T10:21:28Z in `screening-batch1-confound-makeup`. Earlier attempt(s): `screening-batch1` stop_reason=claude_timeout after 2713s
- `w3-sqlfluff-segment-method-migration` **C5** rep 3 — deferred 2026-08-21T10:36:33Z in `screening-batch1-confound-makeup`. Earlier attempt(s): `screening-batch1` stop_reason=claude_timeout after 2719s
- `w4-realworld-missing-user-id` **C3** rep 2 — deferred 2026-08-18T08:55:06Z in `screening-batch1`.

### Cells with no evidence at all

Every rep was truncated or voided. The cell is reported with no verdict — which is not the same statement as a rejection.

- `w3-sqlfluff-segment-method-migration::C5`

### Cells running below their registered n

Every figure in these rows is over fewer reps than the design registered.

- `pilot-realworld-draft-articles::C3 (2/3)`
- `pilot-realworld-draft-articles::C3-prev (2/3)`
- `pilot-realworld-draft-articles::C5 (2/3)`
- `w3-sqlfluff-segment-method-migration::P0 (2/3)`
- `w3-sqlfluff-segment-method-migration::P1 (2/3)`
- `w4-realworld-missing-user-id::C3 (2/3)`

### Cells costed at an upper bound

Product-B spend, priced cache-blind. Never restate one of these as an exact cost.

- `pilot-realworld-draft-articles::C3`
- `pilot-realworld-draft-articles::C3-med`
- `pilot-realworld-draft-articles::C3-prev`
- `pilot-realworld-draft-articles::C5`
- `w1-realworld-mapper-tests::C3`
- `w1-realworld-mapper-tests::C3-med`
- `w1-realworld-mapper-tests::C3-prev`
- `w1-realworld-mapper-tests::C5`
- `w1b-zarr-block-mask-properties::C3`
- `w1b-zarr-block-mask-properties::C3-med`
- `w1b-zarr-block-mask-properties::C3-prev`
- `w1b-zarr-block-mask-properties::C5`
- `w3-sqlfluff-segment-method-migration::C3`
- `w3-sqlfluff-segment-method-migration::C3-med`
- `w3-sqlfluff-segment-method-migration::C3-prev`
- `w4-realworld-missing-user-id::C3`
- `w4-realworld-missing-user-id::C3-med`
- `w4-realworld-missing-user-id::C3-prev`
- `w4-realworld-missing-user-id::C5`
- `w4b-zarr-consolidated-order::C3`
- `w4b-zarr-consolidated-order::C3-med`
- `w4b-zarr-consolidated-order::C3-prev`
- `w4b-zarr-consolidated-order::C5`
- `w6-hono-router-review::C3`
- `w6-hono-router-review::C3-med`
- `w6-hono-router-review::C3-prev`

### Cells costed under more than one attribution rule

The reps in these cells had their Product-B tokens drawn from the provider meter under different windowing rules, so the cell's median is taken over figures produced by more than one instrument. Marked ⚠ in the Cost rule column. The rules are not a ranking and one does not correct another; they are successive answers to *which slice of the meter is this run's*.

- `pilot-realworld-draft-articles::C5 (v1,v2,v3)`
- `w1-realworld-mapper-tests::C5 (v1,v3)`
- `w1b-zarr-block-mask-properties::C3 (v1,v2,v3)`
- `w1b-zarr-block-mask-properties::C3-med (v1,v2,v3)`
- `w1b-zarr-block-mask-properties::C3-prev (v1,v2,v3)`
- `w1b-zarr-block-mask-properties::C5 (v1,v2,v3)`
- `w3-sqlfluff-segment-method-migration::C3 (v1,v2,v3)`
- `w3-sqlfluff-segment-method-migration::C3-med (v1,v2,v3)`
- `w3-sqlfluff-segment-method-migration::C3-prev (v1,v2,v3)`
- `w4b-zarr-consolidated-order::C3 (v1,v2,v3)`
- `w4b-zarr-consolidated-order::C3-prev (v1,v2,v3)`
- `w4b-zarr-consolidated-order::C5 (v1,v2,v3)`

### Cells with an unattested attribution rule

None.

### Cells with a partially costed run

A dual-billed run whose second leg reported no usage. Its per-leg figures stand; its run total does not, and it is left out of the cell's median rather than entered as a floor.

- `pilot-realworld-draft-articles::C5`
- `w1-realworld-mapper-tests::C5`
- `w4b-zarr-consolidated-order::C5`

### Cells with an uncosted run

No leg of the run reported a priceable cost. Recorded `unavailable`, never zero.

- `w3-sqlfluff-segment-method-migration::C3`

### Cells with no graded quality

The archived gate log carries no extractable per-check detail, so there is no secondary measure for the cell — which is not a score of zero.

- `pilot-realworld-draft-articles::C2`
- `pilot-realworld-draft-articles::C3`
- `pilot-realworld-draft-articles::C3-med`
- `pilot-realworld-draft-articles::C3-prev`
- `pilot-realworld-draft-articles::C5`
- `pilot-realworld-draft-articles::P0`
- `w3-sqlfluff-segment-method-migration::C2`
- `w3-sqlfluff-segment-method-migration::C3`
- `w3-sqlfluff-segment-method-migration::C3-med`
- `w3-sqlfluff-segment-method-migration::C3-prev`
- `w3-sqlfluff-segment-method-migration::P0`
- `w3-sqlfluff-segment-method-migration::P1`
- `w4-realworld-missing-user-id::C2`
- `w4-realworld-missing-user-id::C3`
- `w4-realworld-missing-user-id::C3-med`
- `w4-realworld-missing-user-id::C3-prev`
- `w4-realworld-missing-user-id::C5`
- `w4-realworld-missing-user-id::P0`
- `w4b-zarr-consolidated-order::C2`
- `w4b-zarr-consolidated-order::C3`
- `w4b-zarr-consolidated-order::C3-med`
- `w4b-zarr-consolidated-order::C3-prev`
- `w4b-zarr-consolidated-order::C5`
- `w4b-zarr-consolidated-order::P0`

### Cells with partial graded quality

None.

### Standing limitations

- Screening is hypothesis-seeking positioning evidence (SPEC §5): a result on one task is a signal about that task under these pinned conditions, never a workload-class or product claim.
- Every Product-B cost is a cache-blind UPPER BOUND, never an exact cost (manifest notes.gemini_cache_blindness); it is printed with a ≤.
- Product-B token counts are provider-side (authoritative) attributed to a serialized run window (derived), so the derived figures inherit the weaker tier. Never authoritative end to end.
- Graded quality is EXPLORATORY SECONDARY, extracted from archived sealed output. The pre-registered outcome is the binary gate and does not move.
- Truncated runs are excluded from quality extraction entirely: a partial score from a run the harness cut off reads as a model that found little, when the truth is that it was stopped.
- Datasets are superseded per rep, never pooled. Reps run under different agent budgets are different instruments.
- The same applies to the money: a Product-B cost is only as comparable as the rule that drew its provider window, which is why the rule is printed beside the figure and a cell spanning two of them is marked.
- W3 and W4b have no graded quality on any run: the python stack's per-check capture came back empty for every one of them, and W3's sealed suite never executed at all (pytest usage error, exit 4, in all three grading generations — original, regrade-v2, and the confound makeup's live grading under a gate that does carry the per-check step). No verdict depends on it — see report/findings/graded-quality-extraction.md.
- No W3 or W4b run in any arm passed the public checks (0 of 32 and 0 of 20 runs carrying a public gate), so neither task discriminates between arms and no comparative reading may be taken from either.
