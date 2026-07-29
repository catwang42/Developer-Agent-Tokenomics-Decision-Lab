# Measure Before You Route — Developer-Agent Economics Decision Lab

A reproducible, audit-ready measurement layer + half-day decision lab for developer-agent
economics: what AI coding agents cost per **accepted engineering outcome**, and when
model-routing policies are economically defensible.

- **Source of truth:** [`SPEC.md`](SPEC.md) (frozen v2.1.1 — do not edit)

**Three roles.** *Run or fork it (no AI assistant required):*
[`docs/OPERATOR.md`](docs/OPERATOR.md) is the front door — validation, batches, telemetry
checks, aggregation, reports and the site all run on plain shell + Python + Node. The
**benchmark subjects** are the AI coding agents under measurement, driven through declared
adapters ([`harness/adapters/`](harness/adapters/README.md)). The **build agent** was
Claude Code, which constructed this repo phase by phase — that is provenance only
([`CLAUDE.md`](CLAUDE.md), [`GETTING_STARTED.md`](GETTING_STARTED.md),
[`plans/`](plans/)); it appears nowhere in the runtime path.

- **Front end:** MkDocs Material site on GitHub Pages (auto-deployed from `docs/`)
- **Grading integrity:** [`docs/sealed-evaluation.md`](docs/sealed-evaluation.md) — why hidden tests exist, who holds them, and what the per-result hash proves

## Layers (SPEC §0)
1. Methodology (`methodology/`) · 2A. Balanced reference benchmark (`results/pilot-reference/`)
· 2B. Positioning evidence screening (`results/screening/`) · 3. Decision lab (`docs/`)
· 4. Enterprise assessment (separate engagement)

## Repository map
```
CLAUDE.md              Build-agent operating manual (rules, checkpoints, workflow) — provenance
SPEC.md                Frozen specification v2.1.1 — single source of truth
GETTING_STARTED.md     Historical build runbook (how this repo was built) — provenance
docs/OPERATOR.md       Operator guide — run or fork the lab (no AI assistant required)
plans/                 Phase-by-phase build plans with acceptance criteria
methodology/           Layer 1: metrics, benchmark rules, evaluation protocol
manifest/              Delivery manifest template + run pre-registration template
harness/               Controlled runner, adapters, policies, evaluator, telemetry schema
tasks/                 Pilot task + suite roadmap (hidden tests NEVER committed here)
results/               feasibility/ pilot-reference/ screening/ (cohort/ is gitignored)
pricing/               Dated rate-card snapshots
report/                Static analysis report + calculator
docs/                  MkDocs site (GitHub Pages) — the workshop front end
tests/                 Dependency-free tests (stub adapters, no network)
```

## Quickstart
See [`GETTING_STARTED.md`](GETTING_STARTED.md).
