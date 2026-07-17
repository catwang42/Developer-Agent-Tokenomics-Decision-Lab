# Phase 3 — Controlled Harness, Adapters, Feasibility Dataset (SPEC §2.1–2.3, §4.2)
**Goal:** runnable harness for the three declared controlled configurations
(P0 strong single-model, economical single-model, P1 cheap-first escalation) plus
product adapters (C3/C4) and dual-bill workflow adapter (C5); then the 27-run
feasibility dataset and a telemetry-completeness report.
**Branch:** phase/3-harness

## Tasks
1. harness/runner/run.sh + run.py: given (task, configuration, policy, manifest) ->
   execute -> event log + run summary via Phase 1 lib. Supports --dry-run using stub
   adapters (no spend) for tests.
2. Adapters (harness/adapters/):
   - claude_code.py: drives claude -p --output-format json; usage from JSON metadata
     (authoritative); never parses token counts from prose.
   - agy.py: WORKSHOP-OWNED wrapper (headless quirks; our exit codes; record product
     selector label verbatim; mark usage fields unavailable where not exposed).
   - hybrid_c5.py: conductor+executor legs, both bills tagged, frontier-share computed.
3. Policies: implement p0-baseline.yaml and p1-cheap-first.yaml semantics (economical
   attempt -> deterministic gate -> escalate on failure; intention-to-route AND
   completed-route recorded).
4. Stub-adapter test suite proving the full pipeline with SYNTHETIC fixtures.
5. **CP-SPEND** with per-batch cost estimate. After approval: run the feasibility set —
   3 tasks x 3 controlled configurations x 3 reps = 27 runs (SPEC §2.3) -> results/feasibility/.
   Separate small product/workflow telemetry feasibility runs for C3/C4/C5.
6. Generate report/telemetry-completeness.md: per configuration, which fields are
   authoritative/derived/unavailable; harness stability notes. NO vendor rankings.

## Acceptance checklist
- [ ] --dry-run pipeline green end-to-end with stubs; tests green; shellcheck clean
- [ ] feasibility runs written with event logs + summaries; validator passes all
- [ ] completeness report contains zero comparative vendor claims
**Checkpoints: CP-SPEND (before runs), CP-DATA (report review).**

**Inputs added:** harness/configurations/, methodology/{metrics,routing-policy,cache-protocol}.md — implement against these, do not re-derive.

**Protocol:** methodology/feasibility-protocol.md is binding for this phase — tasks F1–F3, companion runs (product/C5, warm-series, human-effort subset), and the 7 pass/fail criteria. The completeness report must address every criterion.
