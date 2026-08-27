# Evidence & Methodology

This page is an **index into the repository**, not a report. The lab's rule is that every
claim points at the file behind it, so the methodology documents, the per-batch
instrument reports and the standing engineering findings are all linked here directly.

!!! warning "What you will *not* find here"

    No comparative result, no ranking, no vendor claim. The per-batch reports answer one
    question — *does the measurement system work?* — and are explicitly non-comparative
    and internal-only (SPEC §1.2 claims register). Screening figures reach public
    material only through **CP-FINDINGS**, and a site build carrying one only through
    **CP-PUBLISH**.

## Methodology

The rules that were fixed before any data was collected.

| Document | What it fixes |
|---|---|
| [Metrics — economics & quality](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/main/methodology/metrics.md) | Acceptance, ECST and QA-ECST, the two cost views, HEAC, the statistical rules — and the forbidden list (FTE conversion, zero-filling, self-reported tokens, unscoped aggregates) |
| [Cache protocol](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/main/methodology/cache-protocol.md) | Cache state as a controlled variable: cold-default runs, the warm-series discipline, and the four token classes recorded per run |
| [Routing-policy ladder](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/main/methodology/routing-policy.md) | The policy families — static assignment, cheap-first escalation, scripted delegation, policy-driven delegation — and what each can and cannot support causally |
| [Feasibility protocol](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/main/methodology/feasibility-protocol.md) | How a batch is run and what has to be true before its telemetry counts |

## Pre-registration and pinning

| Document | What it fixes |
|---|---|
| [Screening pre-registration (CP-SCREEN-PREREG)](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/main/manifest/cp-screen-prereg.md) | The frozen roster, the arm matrix, the registered hypotheses, the pinned run conditions, the declared deviations — committed before the first run |
| [Delivery manifest](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/main/manifest/delivery-manifest.yaml) | The only place where placeholder labels (Product A/B, `STRONG_MODEL_A`) resolve to exact selectors |
| [Dated rate cards](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/tree/main/pricing) | Price snapshots by date — every cost is recomputed from a snapshot, never quoted from memory |
| [Run template](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/main/manifest/RUN_TEMPLATE.md) | The per-run registration form: hypotheses before data |

## Instrument reports

One report per dataset, paired by name. The feasibility-era reports were retired from the
working tree in the 2026-08-27 cleanup and are preserved, unedited, at the tag
`pre-cleanup-2026-08-27` — the links below resolve there.

| Report | Status |
|---|---|
| [Report index](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/main/report/README.md) | Start here — the screening datasets, the pairing rule and the claims boundary |
| [Batch 3 telemetry completeness](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/pre-cleanup-2026-08-27/report/batch3/telemetry-completeness.md) | ARCHIVED at the tag — the home of the 27/27 ceiling-effect finding |
| [Batch 2](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/pre-cleanup-2026-08-27/report/batch2/telemetry-completeness.md) · [Batch 1](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/pre-cleanup-2026-08-27/report/batch1/telemetry-completeness.md) | ARCHIVED at the tag — superseded when written, never edited |
| [Datasets index](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/main/results/README.md) | Every directory under `results/`, what it is, and the report that documents it |

## Standing findings

Cross-cutting engineering records that are not scoped to one dataset. None of them
contains a model or product comparison.

| Finding | What it records |
|---|---|
| [Gate-fairness audit](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/main/report/findings/gate-fairness-audit.md) | Whether rejected runs were genuinely wrong or merely the wrong *shape* for the sealed tests — a fairness analysis of the gate itself |
| [W1 coverage analysis](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/main/report/findings/w1-coverage-analysis.md) | Why the test-generation branch target is an honest reachability ceiling rather than 100% |
| [Subject-isolation leak](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/main/report/findings/subject-isolation-leak.md) | A weakness found in the host-isolation posture, which runs it touched, and what the telemetry can and cannot settle about it |
| [Subject-isolation verification](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/main/report/findings/subject-isolation-verification.md) | The containerised, network-disabled posture verified offline |
| [Model-pin resolution](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/main/report/findings/model-pin-resolution-2026-08-16.md) | How the Product-A tier pins for the screening window were resolved, and why a routed label is recorded rather than an inferred backend version |
| [Provider token-metric surface](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/main/report/findings/vertex-token-metric-surface-2026-08-16.md) | What the billing plane actually exposes — the measurement surface the provider-side collector is built against |

## The harness itself

| Component | What it does |
|---|---|
| [Runner](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/tree/main/harness/runner) | Executes one pinned run: staging, isolation posture, the acceptance gate, the event log and derived summary |
| [Adapters](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/main/harness/adapters/README.md) | One declared adapter per product; exit codes and timeouts are workshop-owned, not vendor behaviour |
| [Container posture](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/main/harness/container/README.md) | What the sandbox actually guarantees — stated precisely, because overstating a posture is how a weak sandbox gets cited as a strong one |
| [Telemetry schema & validators](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/tree/main/harness/telemetry) | The schema every run is validated against, and the summariser that builds a decision table from a batch |
</content>
