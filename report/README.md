# report/ — how to read the feasibility reports

New here? Start with this file, then open the **authoritative** report:
[`report/batch3/telemetry-completeness.md`](batch3/telemetry-completeness.md).

## What these reports measure — and what they do not claim

These reports answer one question: **does the measurement system work?** They record
whether the harness produces validator-passing, honestly-tiered telemetry (token counts,
cost reconstructed without model self-report, cache state, isolation posture) across the
task/config matrix.

They are **NON-COMPARATIVE and internal-only** (SPEC §1.2 claims register). They do
**not** rank vendors or products, do not make "audit-grade" or vendor-superiority claims,
do not convert anything to headcount/FTE, and put **no number into any public docs/site**
before the CP-FINDINGS checkpoint. A metric that "computes" here means the *instrument*
works, not that one tool beats another.

## Which dataset is authoritative today

**`report/batch3/`** documents the authoritative dataset (`results/feasibility-batch3/`).
Exactly **one** telemetry-completeness report is AUTHORITATIVE at any time; every other is
SUPERSEDED. The chain: batch 1 (NO_WRITE defect) → batch 2 (pre-isolation-FIX harness) →
**batch 3 (current)**.

## The pairing rule: every dataset names its report

Every dataset directory under `results/` names the report that documents it (see
`results/README.md`). The common case is a one-to-one pairing:

> `report/batchN/`  ⟷  `results/feasibility-batchN/`

So `report/batch2/` documents `results/feasibility-batch2/`, and so on. This is what keeps
the repo navigable: from any dataset you can find its report, and from any report you can
find its runs.

**Cross-cutting and one-off datasets are documented inside the relevant batch report, not
in their own folders — this is a decision, not an omission:**
- **warm-series** (`results/feasibility-warm-series/`) → batch 3 report **§4.4**
- **revalidation** (`results/revalidation/`) → batch 3 report **appendix**
- **smoke** (`results/smoke/`) → batch 3 report **§4**

The one exception is the **screening smoke**, which does get its own folder because it is
not batch-3-era and not a telemetry dataset at all: `report/smoke-screening/` documents
`results/smoke-screening/` — the smoke itself in `smoke-report.md`, and the verification
of the fixes it forced in `re-smoke/re-smoke-report.md` (append-only, not a rewrite).
Both are **harness evidence, not measurements**.

They are small, single-purpose datasets tied to batch-3-era conclusions; giving each its
own `report/` folder would fragment the record without adding clarity.

## How to read the criteria table

Each telemetry-completeness report has a pass/fail table (its §2) with one row per
feasibility criterion. The verdicts:

- **PASS** — the criterion is met on the dataset (e.g. validator passes with zero
  zero-fills; cost reconstructed without self-report).
- **PARTIAL** — partially met, with the gap stated explicitly and carried as a named
  condition (e.g. a capability proven in one mode but not another).
- **PENDING** — not yet collected, but planned and not fabricated (e.g. human-effort
  timings awaiting reviewers). PENDING is honest absence, never a zero-fill.

"Unavailable" fields inside a run are recorded as `unavailable` with a confidence tier —
never imputed or zero-filled (a core non-fabrication rule).

## Why superseded batches are kept, not deleted

A superseded report is a **historical record**. Each batch was collected on a materially
different harness version, so its numbers are only meaningful against that version — they
are never edited to describe a later batch, and they are never pooled with the authoritative
set. Retaining them (rather than deleting) means any figure ever produced can be traced to
the exact runs and harness that produced it. Each superseded report carries a **STATUS**
banner in its first few lines giving the date, the reason, and its successor.

## Where cross-cutting findings live

Investigations that are **not** dataset-scoped live in
[`report/findings/`](findings/) — e.g. the gate-fairness audit, the subject-isolation leak
finding and its verification, the W1 coverage-ceiling analysis, and the screening-window
[model-pin resolution](findings/model-pin-resolution-2026-08-16.md) (which model ids
actually resolve, and what usage shape they report), and the
[Vertex token-metric surface](findings/vertex-token-metric-surface-2026-08-16.md)
(what the billing plane exposes: whether effort levels are separable, and whether
cached input tokens are). These describe harness/task properties that span batches,
so they are not tied to a single `batchN/`.

Three more were added by the final analysis pass, and each spans every screening
dataset rather than any one of them:

- [offline regrade-v2 sweep](findings/regrade-v2.md) — what re-grading the archived
  diffs under gate images carrying the PR #27 content digest changed, separating
  grader artifacts from genuine failures;
- [graded quality extraction](findings/graded-quality-extraction.md) — the
  exploratory-secondary quality figures read out of already-archived sealed output,
  and why W3 and W4b yield none;
- [confound-makeup enumeration](findings/confound-makeup-enumeration.log) — every
  truncated run no later attempt replaced, and the derivation of the replacement
  slots from it.

## Layout

```
report/
  README.md                      ← you are here
  REPORT-SPEC.md                 ← what a report must contain
  batch1/telemetry-completeness.md   (SUPERSEDED)
  batch2/telemetry-completeness.md   (SUPERSEDED)
  batch2/human-effort-rubric.md      (SUPERSEDED — never completed)
  batch3/telemetry-completeness.md   (AUTHORITATIVE)
  batch3/human-effort-rubric.md      (PENDING — active criterion-6 instrument)
  smoke-screening/smoke-report.md         (AUTHORITATIVE — the screening smoke)
  smoke-screening/re-smoke/re-smoke-report.md
                                     (AUTHORITATIVE — verification of the smoke's fixes)
  findings/                      ← cross-cutting, non-dataset-scoped investigations
  workshop-dashboard/            ← dashboard spec
```

Only `README.md` and `REPORT-SPEC.md` live directly in `report/`; everything else is under
`batchN/`, `smoke-screening/`, `findings/`, or `workshop-dashboard/`.
