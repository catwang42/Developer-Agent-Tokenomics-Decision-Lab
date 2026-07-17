# Phase 1 — Telemetry Foundation (SPEC §2.7)
**Goal:** canonical telemetry implemented and tested — event log + derived run summary,
every field carrying value + confidence tier; cost engine with cost_basis and two
economic views. NO live API calls in this phase.
**Branch:** phase/1-telemetry

## Tasks
1. Freeze harness/telemetry/schema-v2.json (starter provided): review against SPEC §2.7
   field list (identity/config, usage, agent behavior, economics & people); extend if
   fields are missing. Confidence enum: authoritative|derived|proxy_observed|unavailable.
2. Implement harness/telemetry/telemetry.py:
   - EventLog append-only writer (JSONL) for the SPEC event types
   - RunSummary deriver (aggregates events -> summary; never zero-fills)
   - validate(run_dir) -> pass/fail with reasons
3. Implement harness/telemetry/costing.py:
   - loads pricing/prices-<date>.json; computes derived USD per token class
   - marginal_operating and fully_allocated views; cost_basis handling per SPEC §2.7
4. Unit tests in tests/ using SYNTHETIC fixtures under tests/fixtures/ (clearly labeled).
   Include: unavailable-field handling, dual-bill (two provider legs) aggregation,
   cache-class math, cost-basis views.

## Acceptance checklist
- [ ] schema validates fixtures; validator rejects zero-filled/unlabeled fields
- [ ] dual-bill fixture aggregates both legs; unavailable stays unavailable
- [ ] tests/run-tests.sh green; shellcheck clean
**Checkpoint: CP-SCHEMA** — human approves the frozen schema + validator behavior.
