# Measure Before You Route

**The unit-economics audit layer for AI coding agents** — a reproducible measurement
harness plus a half-day decision lab, built to answer what an agent costs per *accepted
engineering outcome*.

[![ci](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/actions/workflows/ci.yml/badge.svg)](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/actions/workflows/ci.yml)
[![deploy-pages](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/actions/workflows/deploy-pages.yml/badge.svg)](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/actions/workflows/deploy-pages.yml)
[![spec](https://img.shields.io/badge/SPEC-v2.1.1%20frozen-5e35b1)](SPEC.md)
[![pre-registered](https://img.shields.io/badge/runs-pre--registered-0277bd)](manifest/cp-screen-prereg.md)
[![license](https://img.shields.io/badge/license-MIT-555)](LICENSE)

**Lab site:** <https://catwang42.github.io/Developer-Agent-Tokenomics-Decision-Lab/>

## The problem

Every team evaluating AI coding agents is handed the same artifact: a cost comparison
with a big percentage on it, no gate on whether the work was any good, and no statement
of what varied between the two columns. Quality is where those comparisons quietly
break — this lab's own third feasibility batch put **27 of 27** controlled runs through
the acceptance gate with zero escalations, meaning the task roster could not separate a
frontier configuration from an economical one on quality at all, and every cost number
computed on top of it was a comparison of indistinguishable outcomes. A benchmark that
cannot fail a configuration cannot rank one either.

> **Thesis: the enterprise question is no longer "which model is best." It is which
> *complete configuration* — product, model tier, routing policy, cache behaviour and
> human review — produces reliable work at an economically defensible cost.** This lab
> measures that, and explicitly refuses the leaderboard framing: a product black-box
> result, a within-product model result and a routing-policy result answer three
> different questions and never merge onto one chart.

## Receipts

Every row links to the file in this repository that carries it. No result from an
in-flight batch appears here; figures enter public material only through CP-FINDINGS.

| Receipt | What it says | Evidence |
|---|---|---|
| **A roster that can't fail anything can't rank anything** | Batch 3: 27/27 controlled runs accepted, zero escalations — a ceiling effect that motivated rebuilding the task roster around commit-mined, post-cutoff work | [`report/batch3/telemetry-completeness.md`](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/pre-cleanup-2026-08-27/report/batch3/telemetry-completeness.md) (archived at tag `pre-cleanup-2026-08-27`) · [`tasks/suite/WORKLOADS.md`](tasks/suite/WORKLOADS.md) |
| **Four human-authored sealed acceptance gates** | W4b, W3, W1b and W6 authored, 10-point validated and frozen *before* the screening window; the sealed set is human-held, never committed, and its hash is recorded on every graded run | [`manifest/cp-screen-prereg.md`](manifest/cp-screen-prereg.md) §3 · [`docs/sealed-evaluation.md`](docs/sealed-evaluation.md) |
| **A seven-point benchmark audit checklist** | Self-reported tokens · unmeasured claims · confounded variables · cache-blind math · no quality gate · n=1 · decorative extrapolation — one canonical wording, one canonical home | [`docs/cheatsheet.md`](docs/cheatsheet.md) |
| **Three comparison types, never one chart** | A finding is a product black-box result, a within-product model result, or a routing-policy result; the renderer bands them with a labelled gap and never sorts across them | [`docs/cheatsheet.md`](docs/cheatsheet.md) (point 3) · [`docs/screening-report.md`](docs/screening-report.md) |

## What this buys you

- **A number you can defend in a procurement review** — cost per *accepted* outcome, not
  cost per run, with failed attempts charged to the configuration that produced them.
- **A grading story that survives the obvious objection** — hidden tests written by a
  human, held outside the repo, fingerprinted on every result.
- **A bill you can decompose** — four token classes at four prices, cache-aware, with
  every leg of a multi-provider workflow itemised or explicitly marked `unavailable`.
- **A vocabulary for refusing bad evidence** — seven named failure modes, and the rule
  that a recommendation without its break-even conditions is an advertisement.
- **Something to run, not just read** — the harness, the tasks and the lab all fork.

## How it measures

- **Receipts before doctrine.** Every claim in this repo points at the run, the file or
  the hash behind it. Missing telemetry is recorded as `unavailable` with a confidence
  tier — never zero-filled, never imputed, never inferred from a model's self-report.
- **Quality gate before economics, lexicographically.** The gate is pre-registered,
  independent and deterministic-first; a configuration that fails non-inferiority is
  *eliminated*, not discounted, and cost is only compared among survivors. Failed
  attempts are billed to the configuration that failed, never averaged away
  ([`docs/cheatsheet.md`](docs/cheatsheet.md) · [`methodology/metrics.md`](methodology/metrics.md)).
- **Two cost views, both reported.** Marginal operating cost and fully allocated cost; a
  finding counts as robust only if its direction survives both.
- **Sealed, human-authored hidden tests.** Written by the evaluation operator, gitignored,
  validated against a canonical solution before anyone is graded by them
  ([`docs/sealed-evaluation.md`](docs/sealed-evaluation.md)).
- **Pre-registration, published either way.** Arms, cells, repetitions, hypotheses and
  declared deviations are committed before the first run
  ([`manifest/cp-screen-prereg.md`](manifest/cp-screen-prereg.md)). Registered comparisons
  are reported whichever direction they come out.
- **Cache-aware accounting.** Cache state is a controlled variable, not an accident:
  every run declares cold or warm-series, records all four token classes with their
  confidence tier, and is priced from a dated snapshot. The naive-vs-cache-aware
  recomputation is stated as a pinned-run observation, never as general behaviour
  ([`methodology/cache-protocol.md`](methodology/cache-protocol.md)).
- **Contamination-guarded collection.** Tasks carry a declared contamination tier, and
  post-cutoff work is mined from real commits so the answer cannot already be in the
  weights; provider-side collection captures per-leg usage the CLI does not expose.

## Status

**Screening batch 1 is in flight** — 7 tasks × up to 7 arms per task, 42 pre-registered
cells × 3 repetitions = **126 runs**, all cold-cache, registered before launch in
[`manifest/cp-screen-prereg.md`](manifest/cp-screen-prereg.md).

Screening is hypothesis-seeking positioning evidence (SPEC §5). It is not publishable on
its own, and no figure from it is public until CP-FINDINGS clears the numbers and the
scoping language.

## Results

**Landing here.** The renderer is built and shipped pointed at nothing:
[`docs/screening-report.md`](docs/screening-report.md) describes each view and the
specific mistake it exists to prevent. Until CP-FINDINGS, the empty state is the correct
state — this section carries no numbers on purpose.

## Structure

```
tasks/       The work agents are measured on — visible task, public tests, and a
             human-held hidden/ set per task (gitignored, never committed)
harness/     Runner, product adapters, routing policies, containerised gate,
             telemetry schema + validators, summariser
manifest/    Delivery manifest (resolves Product A/B and tiers) and the frozen
             screening pre-registration
pricing/     Dated rate-card snapshots — costs are recomputed, never quoted
results/     One directory per dataset; every one named in results/README.md with
             the report that documents it (results/cohort/ is gitignored)
docs/        The MkDocs site: operator guide, five modules, sealed-evaluation
             explainer, seven-point cheatsheet, screening-report renderer
report/      Per-batch telemetry-completeness reports and cross-cutting findings
methodology/ Metrics, benchmark rules, cache protocol, routing-policy ladder
```

## Quickstart

```bash
git clone https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab.git
cd Developer-Agent-Tokenomics-Decision-Lab

bash tests/run-tests.sh          # dependency-free: stub adapters, no network, no spend

python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m harness.runner.run --help    # the controlled runner

mkdocs serve                     # the lab site at http://127.0.0.1:8000
```

Nothing above bills an account. Live runs against a real product are gated behind an
approved spend checkpoint — see [`docs/OPERATOR.md`](docs/OPERATOR.md), which is the
front door for running or forking the lab and assumes no AI assistant.

## Three roles

*Run or fork it (no AI assistant required):* [`docs/OPERATOR.md`](docs/OPERATOR.md) —
validation, batches, telemetry checks, aggregation, reports and the site all run on plain
shell + Python + Node. The **benchmark subjects** are the AI coding agents under
measurement, driven through declared adapters
([`harness/adapters/`](harness/adapters/README.md)). The **build agent** was Claude Code,
which constructed this repo phase by phase — that is provenance only
([`CLAUDE.md`](CLAUDE.md), [`GETTING_STARTED.md`](GETTING_STARTED.md), and the phase
plans archived at tag
[`pre-cleanup-2026-08-27`](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/tree/pre-cleanup-2026-08-27/plans));
it appears nowhere in the runtime path.

- **Source of truth:** [`SPEC.md`](SPEC.md) (frozen v2.1.1 — do not edit)
- **Layers (SPEC §0):** 1. Methodology (`methodology/`) · 2A. Balanced reference benchmark
  (`results/pilot-reference/`) · 2B. Positioning-evidence screening (`results/screening/`)
  · 3. Decision lab (`docs/`) · 4. Enterprise assessment (separate engagement)
- **Licence:** MIT ([`LICENSE`](LICENSE))
</content>
