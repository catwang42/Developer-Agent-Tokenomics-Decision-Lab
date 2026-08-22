# Screening findings — release package (CP-FINDINGS)

Findings package for the **Phase-4 screening window** (CLAUDE.md checkpoint table;
SPEC v2.2 §1.2, §5, §5.2). This document is the gate between measured cells and any
number that appears in `docs/`, on the site, or in an external-facing report. It fixes
**which figures are releasable, what each one is scoped to, and what language may carry
it** — before the renderer at `docs/screening-report.md` is pointed at real data.

Approving this checkpoint authorizes **no spend** and **no publish**. It authorizes
figures to leave `report/` and enter the gated renderer. Shipping a Pages build that
contains one is gated separately by **CP-PUBLISH**.

**Status: DRAFT — NOT APPROVABLE.** Blockers in §10 are open. Nothing below is a
number until the consolidated table is regenerated over all four datasets and its
hash is recorded in §2.

---

## 1. What this package approves, and what it does not

**Approves.** The per-cell reporting contract in §4, the cost-state rules in §5, both
pre-registration verdicts in §6, the W6 quality-separation finding in §7, the holes
ledger in §8, and the scoping language in §9 — as the complete set of screening
figures that may enter the gated renderer.

**Does not approve.** Any ranking across the three comparison views of SPEC §2.1; any
promotion of a single task to a workload-class claim (§9, two-task rule); any vendor,
model-efficiency or headcount/FTE conversion; any figure not present in the
consolidated table named in §2; and the Pages deploy itself.

A cell in this package is **hypothesis-seeking positioning evidence about one task**
(SPEC §5). It is never independently publishable as a class result.

---

## 2. Inputs — what this package is graded over

| Input | Value | Tier |
|---|---|---|
| Consolidated table (md) | `report/findings/consolidated-table.md` | authoritative |
| Consolidated table (json) | `report/findings/consolidated-table.json` | authoritative |
| `sha256` of the json | `c07f620c02e2f3cc688333a41eba2e3aff04d0549276998ed674df454ef9e86b` | — |
| `sha256` of the md | `92b44b8dea18f21741115e2b947c666c855407a1f107f7d155d73d5c0e5e4d17` | — |
| `--generated-at` | `2026-08-21T12:28:52Z` | — |
| Harness HEAD at generation | `a7f03af` (the tree the generator ran from; it predates the commit carrying these two files) | — |
| Regrade authority | `report/findings/regrade-v2.md` (AUTHORITATIVE) | authoritative |
| Graded-quality extraction | `report/findings/graded-quality-extraction.md` | exploratory secondary |
| Holes enumeration | `report/findings/confound-makeup-enumeration.log` (AUTHORITATIVE) | authoritative |

**Datasets consolidated (four, superseded per slot, never pooled):**

| Dataset | Role | Instrument condition |
|---|---|---|
| `results/screening-batch1` | original roster | flat 1800s agent budget |
| `results/screening-batch1-makeup` | W3 re-buy | 7200s pinned budget |
| `results/screening-batch1-makeup-w6` | W6 full roster re-buy | delivery defect fixed; 5 arms × 3 reps |
| `results/screening-batch1-confound-makeup` | 11 censored slots | per-task pinned budgets; attribution rule v3 |

Supersession is per `slot = (task_id, configuration_id, rep)`, latest non-truncated,
non-void attempt wins. **Two datasets run under different instrument settings are never
merged into one cell.** A slot no attempt fills is a hole (§8), never an average.

---

## 3. Claims register — what this batch licenses

Every releasable statement below must map to a row here. A statement with no row does
not ship.

| # | Claim | Licensed by | Scope line |
|---|---|---|---|
| F-1 | The instrument separates arms on at least one task | W6 gradient (§7) | one task, one review roster, pinned conditions |
| F-2 | Gate-passing output can still be unmergeable | W1b (§6/§7) | W1b property-test cells only |
| F-3 | Right-censored runs are not capability results | holes ledger (§8) | instrument statement, not a model statement |
| F-4 | Product-B cost is measurable only as a cache-blind upper bound, from a single uncorroborated source | §5.1 | this collector, these windows, this metering surface |
| F-5 | *(reserved — H-effort quality half)* | §6.1 | routine-class tasks only, per registration scope condition |
| F-6 | *(reserved — W3 escalation)* | §6.2 | W3-migration only; designated difficulty probe |
| F-7 | Provider-side per-run attribution in a shared project cannot be scheduled dependably: 9/9 succeeded overnight, 7 refused and 3 deferred in daytime windows | §8 ledger; confound probe evidence (20.7M third-party tokens in-window) | this metric surface, this project class |
| F-8 | A black-box agent CLI can report usage and still yield none, if the harness never requests its structured-output mode | §5.1 (0 of 153 archived invocations; positive product probe) | agy 1.1.13, this adapter |

**Explicitly NOT licensed by this batch:** any Product-B cost stated as exact rather
than as an upper bound (§5.1); any cross-source validation of Product-B cost, there
being only one source; any cross-product cost ranking; any effort-level cost claim; any
dispersion or variance claim from the makeup datasets (n=2 or replacement slots, per
the driver's `REPS_CAVEAT`).

---

## 4. Per-cell reporting contract

Every released cell carries these columns. A cell missing any of them does not ship.

| Column | Source | Rule |
|---|---|---|
| Task | `task_id` | — |
| Config/policy | `configuration_id` | banded by SPEC §2.1 comparison view; views never share a table |
| Accepted | pre-registered sealed gate | **primary.** Binary. Reported first. |
| Median graded quality | `harness/analysis/quality.py` | **exploratory secondary.** Never overrides a verdict. |
| Cost | `harness/analysis/recost.py` | one of three states, §5 |
| **`attribution_rule`** | collector `attribution_rule.rule` | v1 / v2 / v3, or `n/a` for arms with no Product-B leg. Mixed → list all. |
| Wall-clock s | run summary | median over filled reps |
| Provenance | verdict provenance + source datasets | names every makeup dataset contributing a rep |
| Reps filled | supersession | `n of registered` |

### 4.1 The `attribution_rule` column — why it is mandatory

Batch 1's Product-B legs were attributed under v1 and v2; the confound makeup runs
under **v3** (rate-ceiling, 25k tokens/sec, per the driver's `ATTRIBUTION_RULE`). Four
runs already carry a v1 refusal *and* a v2 attribution — both records stand, because
the rules draw different windows.

A consolidated cost column spanning four datasets therefore spans up to three windowing
rules. **Unlabelled, that is precisely the confound class this lab exists to catch.**
The rule is a property of the figure, not a footnote: it renders in the row.

A cell whose filled reps span more than one rule renders every rule present
(e.g. `v1,v3`) and **may not** have its cost figures compared across those reps.

---

## 5. Cost reporting — three states, and only three

| State | Renders as | When |
|---|---|---|
| Priced | `$0.1234` | every leg exactly priced, cache state measured |
| Bounded | `≤$0.1234` | any leg cache-blind. One bounded leg bounds the whole cell — it is not diluted by exactly-priced runs beside it. |
| Unavailable | `unavailable — <reason>` | any leg unpriced. **Never zero, never inferred from a sibling run.** |

A bare `unavailable` does not ship. The reason renders in the cell.

### 5.1 Product-B cost — present, bounded, and single-source

**41 of 42 cells carry a cost.** C3, C3-med and C3-prev are costed on all 7 tasks; C5 on
5 of 6. The only cost-less cell is `w3…::C5`, which has no runs at all (§8), so its
absence is an evidence hole, not a pricing failure.

Every Product-B-metered cost renders `≤` — a cache-blind upper bound at **derived**
attribution tier, produced by the provider-side collector
(`serialized_run_ownership_with_rate_ceiling`). It is never restated as an exact figure
and never sits in the same column as Product A's per-request `authoritative` costs.

**What is missing is the second source.** The harness invoked agy without
`--output-format json`; the product's default output is text, so no run ever emitted a
usage block and the adapter recorded all token classes `unavailable`. Verified
2026-08-22: 0 of 153 archived invocations across all four datasets contain usage, while
a direct probe of agy 1.1.13 confirms the product DOES expose input / output / thinking /
cache-read counts under that flag.

Three consequences, all of which must travel with every Product-B figure:

1. **Single-source.** Every Gemini cost rests on the provider-side collector with no
   independent cross-check. Product A's figures are corroborated by construction;
   Product B's are not.
2. **Cache-blind by omission, not by necessity.** `cache_read_tokens` was available from
   the product throughout. The `≤` bounds could have been decomposed and were not. This
   bears on the 2026-08-16 `gemini_cache_blindness` decision, which was taken on
   provider-metric evidence with no product-side probe run.
3. **The thinking share is unaccounted.** agy reports `thinking_tokens`; the adapter's
   mapper looks for `reasoning_tokens`. Even with the flag set, that class would have
   been dropped.

Self-caught instrument defect (`report/findings/agy-json-flag-defect.md`). Unrecoverable
from archives — product-reported usage for a past run cannot be reconstructed. Fixed
forward.

An earlier draft of this section stated that these arms carry no cost at all and
attributed it to effort levels being non-label-separable in the provider's metering
surface. Both statements are **superseded**: the cells are costed, and the operative
defect was a missing CLI flag affecting the corroborating source, not the primary one.

### 5.2 C5 — costed on five tasks, absent on the sixth, delegation unobserved

C5's conductor leg (Product A) is priced per request; its executor leg is bounded by the
same collector as the solo arms. Cells render `≤`, and where only some reps are costed
the cell says so (`n=x of y`) — a partially costed run is left out of the median, never
entered as a floor.

On W3, C5 has **zero attempts**: truncated in batch 1, then deferred-contaminated in the
confound makeup (§8). Reported with no verdict, which is not a rejection.

Because `frontier_token_share` derives from executor-side counts that no run reported,
**live delegation behaviour is unobserved** — consistent with policy P3's own record
(`live_delegation: unverified`). No statement about when or why the conductor delegates
is licensed by this batch.

---

## 6. Pre-registrations, graded

Both registrations were frozen before any screening run existed and are **published
whichever way they come out** (CP-SCREEN-PREREG). Graded here over the *superseded* set.

### 6.1 H-effort — C3 (High) vs C3-med (Medium)

**Registered prediction:** Medium clears the same gates as High on routine tasks while
consuming materially fewer tokens; expected 30–50% reduction in cost per accepted
outcome. **Scope condition:** routine classes only — the harder screening tasks
(complex multi-file bugfix, W6) are exploratory for this panel and carry no prediction.

**Verdict: PARTIAL — quality half only.**

| Half | Gradable | Result |
|---|---|---|
| Gate parity (quality) | yes | **holds** on both gradable in-scope tasks — `pilot-realworld-draft-articles` and `w1-realworld-mapper-tests`; `w1b` and `w3` are in scope but `not_gradable` (no arm cleared the gate, so there is no cost-per-accepted-outcome to compare) |
| Cost reduction (30–50% band) | **no** | not gradable — both arms are cache-blind upper bounds (§5.1); a ratio of two `≤` bounds is not a measured reduction and the registered band is not drawn against it |

The predicted band is **not** drawn, compared to, or reported as met/unmet. Recording
the cost half as ungradable is itself the finding, and it ships as one: the registration
was written against a measurement the instrument turned out not to expose for these arms.

Out-of-scope cells (W6, complex bugfix) are reported as exploratory and are excluded
from the parity verdict.

### 6.2 W3 escalation — C2 (economical solo) vs P1 (cheap-first escalation)

**Registered prediction:** the economical tier fails W3's full gate — most likely on the
~30-dialect byte-identical parity requirement or the call-site-rewiring requirement —
causing P1 to escalate to the strong tier. Published either way, including the null.

**Graded from the confound-makeup cells**, under W3's own 7200s pinned budget. Batch 1's
W3 cells ran under the flat 1800s bound and are right-censored; they inform nothing here
and are labelled as holes or confounded in their own rows.

| Element | Value |
|---|---|
| Economical arm at the gate | `failed` — C2 accepted **0/3** |
| Escalation branch fired | `observed` — 2 of 2 probe runs |
| Outcome | `prediction_supported`, **understrength**: the probe arm (P1) is graded on 2 runs, not the registered 3 |
| Reps | 2 per arm — enough to see a split, **not** enough for a dispersion claim |

**Two slots are deliberately absent** and must be reported as a finding, not a gap:
W3 P0 rep1 and W3 P1 rep1 were truncated at 1800s in batch 1 and timed out **again** at
7200s in the W3 makeup. *"Does not complete within two hours"* is the result for those
slots.

---

## 7. W6 — the batch's clearest quality separation

W6 (`w6-hono-router-review`, 6 planted defects, k=6, ≥2 clean regions, `check.sh`
scorer) is the one task where the roster separates arms at the gate.

| Arm | Gradable accepted | Note |
|---|---|---|
| P0 | 3/3 | |
| C2 | 1/2 | third rep arrives from `confound-makeup` — provenance spans two datasets |
| C3-med | 1/3 | |
| C3 | 0/3 | |
| C3-prev | 0/3 | |

Reporting requirements:

- Batch 1's W6 cells are **void** (the artifact under review was never delivered; all
  15 attempts reviewed an empty room and produced a 0-byte diff). Void is neither
  accept nor reject. Void cells are **never** merged with fixed-instrument cells.
- The gradient is a statement about **this review task under these pinned conditions**.
  Promoting it to a code-review-class claim requires a second, materially different
  task from the same class (§9).
- The false-positive column travels with the accept column. A run that found 6 of 6
  planted defects and fabricated a seventh is a rejected run, and the pair of columns
  is the point.
- C2's cell states its two source datasets and its rep count explicitly.

This is the finding that answers the batch-3 problem recorded in the README — a roster
that put 27 of 27 controlled runs through the gate could not separate anything. This one
can.

**Timeout parity: cleared for W6 (B-11).** All nine Gemini runs completed naturally in
115–384s, far under the product's 900s per-invocation timeout; P0 ran 574–693s and C2
475–1201s. The gradient is not an artifact of unequal time. W3 and W4b Gemini cells DO
sit at the ~915s wall and are reported with that ceiling disclosed — the contrast is
itself a finding, and every cross-arm figure carries per-arm time ceilings in its
pinned-conditions line.

**W6 also carries the study's cleanest economic comparison.** Its nine Gemini runs were
collected in an uncontaminated overnight window (9/9 backfilled) and P0/C2 are priced
per request, so cost per accepted outcome is computable across all five arms on the
headline task. An arm with a ~$0.55–1.33 attempt cost and zero accepted reps renders as
undefined cost-per-outcome — cheap per attempt, unboundedly expensive per result. That
single row is the lab's thesis.

---

## 8. Holes ledger — absent evidence, printed with its reason

Two classes, never conflated, never dropped, never averaged around:

| Class | Meaning | Reads as |
|---|---|---|
| Budget exhaustion | every attempt ran out of wall-clock, including ≥1 re-buy under a longer budget | **a result** — "does not complete within the budget bought" |
| Unreplaced loss | slot lost to truncation or void, no later pass re-bought it | **missing data** — says so |
| Deferred-contaminated | the pre-run quiet gate could not establish a clean measurement window; the arm was never invoked, nothing billed | **an instrument refusal** — "declined to measure dirty", published with the probe evidence |

Ledger contents, as generated (full text and per-slot provenance in the consolidated
table's *Limitation ledger*):

| Ledger section | Count | Contents |
|---|---|---|
| Budget exhaustion — **a result** | 2 | W3 **P0** rep 1 (1812s in batch 1, then 7210s in the W3 makeup); W3 **P1** rep 1 (3642s, then 9453s) |
| Unreplaced loss — **missing data** | 0 | none |
| Re-bought, then refused by the contamination guard | 7 | pilot **C3** r3, pilot **C3-prev** r3, pilot **C5** r3, W4 **C3** r2 (all batch 1); W3 **C5** reps 1–3 (confound makeup). Nothing billed, nothing run — the cause is the measurement window, and the remedy is a quiet-window re-run |
| Cells with no evidence at all | 1 | `w3…::C5` — reported with no verdict, which is not a rejection |
| Cells below registered n | 6 | pilot C3, pilot C3-prev, pilot C5, W3 P0, W3 P1, W4 C3 — all 2/3 |
| Cells costed at an upper bound (`≤`) | 26 | every Product-B-metered cell; never restated as an exact cost |
| Cells with a partially costed run | 3 | pilot C5, W1 C5, W4b C5 — the run is left out of the median, not entered as a floor |
| Cells with an uncosted run | 1 | W3 C3 — `unavailable`, never zero |
| Cells with no graded quality | 24 | all pilot, W3, W4 and W4b cells — no extractable per-check detail, which is not a score of zero |

Every hole renders in the cell it belongs to. **A truncated run never renders as a
rejection** — that would convert a harness fault into a model result, which is the
failure mode this whole package exists to prevent.

---

## 9. Scoping language — required on every released figure

1. **Pinned-conditions line.** Every figure carries the conditions it was measured
   under: cache state, isolation posture, egress policy, agent budget, attribution rule,
   model pin.
2. **Cost basis declared.** Marginal vs allocated subscription, stated, never implied.
3. **Confidence tier.** authoritative / derived / proxy_observed / unavailable. A derived
   figure inherits the weakest tier of its inputs. `≥` and `≤` mark known bounds.
   **Unavailable is never zero.**
4. **Two-task rule.** No single task promotes to a workload-class claim. One task is a
   signal about that task.
5. **Three views never merge.** Product-level, model-tier and routing-policy comparisons
   are causally distinct and are banded separately. No table, chart or sentence ranks
   across them.
6. **n disclosed inline.** Where a median rests on fewer runs than the cell has reps, the
   row says `n=x of y`. Makeup datasets carry no dispersion claim at all.
7. **Negative and null results ship.** Both registrations publish either way; the
   ungradable cost half of H-effort is reported, not omitted.

---

## 10. Blockers — this package cannot be approved while any remain

- [ ] **B-1.** Confound makeup finished; all 11 slots present, or the shortfall recorded
      in §8 with its reason. *(driver at slot 5/11 at time of drafting)*
- [ ] **B-2.** Consolidated table regenerated over all four datasets; `sha256` and
      `--generated-at` recorded in §2; harness HEAD recorded.
- [ ] **B-3.** `attribution_rule` column implemented in `consolidate.py`, covered by
      tests, and populated for every cell (§4.1).
- [ ] **B-4.** `unavailable` cost cells carry a stated reason (§5); no bare
      `unavailable` remains in the rendered table.
- [ ] **B-5.** Both registrations graded and rendered (§6), including H-effort's
      explicit PARTIAL verdict.
- [ ] **B-6.** Human stopwatch review complete: W4b P0/C2 rep1 diffs, W3-makeup P0 rep2
      diff, and one W6 accepted-vs-rejected report pair. HEAC inputs recorded.
- [ ] **B-7.** Every §3 claim maps to a rendered figure; every rendered figure maps to a
      §3 claim. No orphans in either direction.
- [ ] **B-8.** W3/W4b graded-quality remains `unavailable` (sealed per-check block absent
      in all generations) — recorded as a limitation, confirmed to affect no verdict.
- [ ] **B-9.** Metering environment stated as a limitation: shared GCP project, 20.7M
      third-party input tokens measured on the subject model inside a live measurement
      window (F-7). `agy-agent-catalog-refresh` is NOT a Cloud Scheduler job in
      us-central1 — provenance restated from `gcloud scheduler jobs list` across all
      locations, or the reference removed.
- [ ] **B-10.** W1's sealed mutant roster is disclosed by descriptive name in published
      gate-hidden receipts (`m1-following-always-false` … `m6-taglist-wrong-shape`) and
      in `tests/fixtures/w1-hidden-runner-SYNTHETIC/`, violating the task's own split
      rule. Recorded in the limitation ledger; W1 declared no longer sealed for future
      measurement or for workshop participants; runner to print opaque IDs before batch
      2. History is NOT rewritten.
- [ ] **B-11.** Timeout parity: CHECKED 2026-08-22 (§7). W6 cleared. W3/W4b Gemini
      ceiling disclosed on every affected figure.
- [ ] **B-12.** Every Product-B cost renders `≤` with derived tier and single-source
      provenance visible (§5.1). No Product-B figure appears in the same column as a
      Product-A `authoritative` cost.

---

## 11. What this package does NOT do

- Does not publish. CP-PUBLISH gates the Pages build.
- Does not authorize spend. No CP-SPEND is requested or implied.
- Does not re-run any agent. Every figure here is read-only over `results/`.
- Does not amend SPEC. Amendments are human-authored, logged and versioned separately.
- Does not repair batch 1. Batch-1 cells stay exactly as they are, labelled confounded
  or void; each makeup dataset keeps its own directory and its own report.

---

## Sign-off

Nothing in this package enters `docs/`, the site, or any external report until the line
below is written by the human reviewer.

```
CHECKPOINT APPROVED: CP-FINDINGS
Reviewer:
Date:
Consolidated table sha256:
```
