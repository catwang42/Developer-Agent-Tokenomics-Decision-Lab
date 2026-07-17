# Measure Before You Route — Developer-Agent Economics Decision Lab

A reproducible, audit-ready measurement layer + half-day decision lab for developer-agent
economics: what AI coding agents cost per **accepted engineering outcome**, and when
model-routing policies are economically defensible.

- **Source of truth:** [`SPEC.md`](SPEC.md) (frozen v2.1.1 — do not edit)
- **Built by:** Claude Code, phase by phase, per [`CLAUDE.md`](CLAUDE.md) and [`plans/`](plans/)
- **Human role:** approve checkpoints only (see `CLAUDE.md` → Human checkpoints)
- **Front end:** MkDocs Material site on GitHub Pages (auto-deployed from `docs/`)

## Layers (SPEC §0)
1. Methodology (`methodology/`) · 2A. Balanced reference benchmark (`results/pilot-reference/`)
· 2B. Positioning evidence screening (`results/screening/`) · 3. Decision lab (`docs/`)
· 4. Enterprise assessment (separate engagement)

## Repository map
```
CLAUDE.md              Claude Code operating manual (rules, checkpoints, workflow)
SPEC.md                Frozen specification v2.1.1 — single source of truth
GETTING_STARTED.md     Human step-by-step guide to run the build with Claude Code
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
