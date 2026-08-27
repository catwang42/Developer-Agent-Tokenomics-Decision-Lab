# Measure Before You Route

**The unit-economics audit layer for AI coding agents** — a reproducible measurement
harness plus a half-day decision lab, built to answer what an agent costs per *accepted
engineering outcome*.

## The problem

Every team evaluating AI coding agents is handed the same artifact: a cost comparison
with a big percentage on it, no gate on whether the work was any good, and no statement
of what varied between the two columns. Quality is where those comparisons quietly
break — this lab's own third feasibility batch put **27 of 27** controlled runs through
the acceptance gate with zero escalations, meaning the task roster could not separate a
frontier configuration from an economical one on quality at all, and every cost number
computed on top of it was a comparison of indistinguishable outcomes. A benchmark that
cannot fail a configuration cannot rank one either.

!!! quote "The thesis"

    The enterprise question is no longer *"which model is best."* It is which **complete
    configuration** — product, model tier, routing policy, cache behaviour and human
    review — produces reliable work at an economically defensible cost.

    This lab measures that, and explicitly refuses the leaderboard framing: a product
    black-box result, a within-product model result and a routing-policy result answer
    three different questions and never merge onto one chart.

## Receipts

Each row links to the artifact that carries it. No result from an in-flight batch appears
here; figures enter public material only through the findings checkpoint.

| Receipt | What it says | Evidence |
|---|---|---|
| **A roster that can't fail anything can't rank anything** | Batch 3: 27/27 controlled runs accepted, zero escalations — a ceiling effect that motivated rebuilding the task roster around commit-mined, post-cutoff work | [batch-3 telemetry completeness](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/pre-cleanup-2026-08-27/report/batch3/telemetry-completeness.md) (archived at tag) · [workload roster](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/main/tasks/suite/WORKLOADS.md) |
| **Four human-authored sealed acceptance gates** | Authored, 10-point validated and frozen *before* the screening window; the sealed set is human-held, never committed, and its hash is recorded on every graded run | [screening pre-registration §3](https://github.com/catwang42/Developer-Agent-Tokenomics-Decision-Lab/blob/main/manifest/cp-screen-prereg.md) · [Sealed Evaluation](sealed-evaluation.md) |
| **A seven-point benchmark audit checklist** | Self-reported tokens · unmeasured claims · confounded variables · cache-blind math · no quality gate · n=1 · decorative extrapolation | [Cheatsheet](cheatsheet.md) |
| **Three comparison types, never one chart** | A finding is a product black-box result, a within-product model result, or a routing-policy result; the renderer bands them with a labelled gap and never sorts across them | [Cheatsheet, point 3](cheatsheet.md) · [Screening report](screening-report.md) |

## How it measures

- **Receipts before doctrine.** Every claim points at the run, the file or the hash
  behind it. Missing telemetry is recorded as `unavailable` with a confidence tier —
  never zero-filled, never imputed, never taken from a model's self-report.
- **Quality gate before economics, lexicographically.** A configuration that fails
  non-inferiority is eliminated, not discounted; cost is compared among survivors only,
  and failed attempts are billed to the configuration that failed.
- **Two cost views, both reported.** Marginal operating and fully allocated — a finding
  is robust only if its direction survives both.
- **Sealed, human-authored hidden tests.** Held outside the repository, validated against
  a canonical solution before anyone is graded by them ([Sealed Evaluation](sealed-evaluation.md)).
- **Pre-registration, published either way.** Arms, cells, repetitions, hypotheses and
  declared deviations are committed before the first run.
- **Cache-aware accounting.** Cache state is a controlled variable; all four token
  classes are recorded with their tier and priced from a dated snapshot.
- **Contamination-guarded collection.** Tasks carry a declared contamination tier, and
  post-cutoff work is mined from real commits.

## Status

**Screening batch 1 is in flight** — 7 tasks × up to 7 arms per task, 42 pre-registered
cells × 3 repetitions = **126 runs**, all cold-cache, registered before launch.

Screening is hypothesis-seeking positioning evidence (SPEC §5): not publishable on its
own, and no figure from it is public until CP-FINDINGS clears the numbers and the scoping
language. Results land on the [screening report](screening-report.md) page, which today
renders its empty state on purpose.

## Where to start

| You are… | Start here |
|---|---|
| Running or forking the lab | [Operator Guide](OPERATOR.md) — no AI assistant required |
| Attending a session | [Pre-work Setup](setup.md), then [M0 · The Decision Problem](m0-decision-problem.md) |
| Auditing someone else's benchmark | [Cheatsheet](cheatsheet.md) — the seven-point checklist |
| Checking how grading works | [Sealed Evaluation](sealed-evaluation.md) |
| Looking for the underlying records | [Evidence & Methodology](evidence.md) |

> The module pages (M0–M4), the agenda and the trust commitments are built out in Phase 5
> from SPEC §3. Until then several of them are stubs.
</content>
