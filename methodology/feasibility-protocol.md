# Feasibility Dataset Protocol (the 27 runs + companions) — SPEC §2.3 made concrete

## Purpose (unchanged)
Prove the measurement system works. Output = telemetry-completeness report + go/no-go.
NEVER comparative vendor claims. Dispersion observed here sets the pilot-reference
rep count (>=5 default, adjusted).

## The 27 controlled runs
3 tasks x 3 configurations (P0 strong · economical single-model · P1 cheap-first) x 3
reps, cold-cache, fresh sessions, controlled harness.

### Feasibility tasks F1–F3 — chosen for GATE-TYPE diversity, not language balance
| ID | Gate type exercised | Source |
|---|---|---|
| F1 | Feature gate (schema+endpoint checks) | the validated pilot RealWorld task |
| F2 | Bugfix gate (failing repro test -> green, no unrelated diffs) | W4 candidate, validated via the same 10-point script |
| F3 | Coverage-delta gate (test generation) | W1 candidate, validated likewise |
F2/F3 double-use as suite candidates is permitted: feasibility makes no claims, and the
screening pre-registration must disclose their prior feasibility use.

## Companion runs (outside the 27)
- **Product telemetry feasibility:** F1 x {C3, C5} x 2 reps (C4 optional) — enumerate
  authoritative/derived/unavailable per field; validate dual-leg aggregation on real
  C5 data; record selector labels verbatim.
- **Cache warm-series:** F1 x C1 x one 3-run series (run 1 cold, 2–3 warm) — validates
  cache-state capture + cache-aware costing; becomes the ex120 teaching input.
- **Human-effort subset:** apply the timed review rubric to 9 runs (one rep per cell);
  two reviewers on >=3 of them; report inter-reviewer spread. Proves HEAC inputs are
  recordable, not just schema slots.

## Pass/fail criteria (go/no-go for Phase 4+)
| # | Criterion | Threshold |
|---|---|---|
| 1 | Validator passes | 27/27 summaries + event logs valid; zero zero-fills |
| 2 | Cost reconstruction | 100% of runs costed WITHOUT model self-report; every usage field authoritative or derived for C1/C2; unavailable fields enumerated (not silently absent) for product runs |
| 3 | Harness stability | 0 harness crashes; reset determinism (identical tree hash) 27/27; gate reproducibility: canonical patch -> same verdict 3/3 per task |
| 4 | Escalation telemetry | P1 cells record ITR + CR + failed-attempt costs on every run |
| 5 | Metric computability | ECST, QA-ECST-by-class, HEAC, both cost views compute end-to-end from the 27 runs (output labeled NON-COMPARATIVE, internal only) |
| 6 | Human effort | rubric timings recorded for the 9-run subset; inter-reviewer spread reported |
| 7 | Cache | warm-series shows cache_read capture + costing delta vs naive |
**Stop condition** (per accepted research): if total task cost cannot be reconstructed
without self-report or uncontrolled estimates, halt and fix measurement before any
further phase. **Narrow condition:** products with incomplete telemetry stay in a
proxy/black-box tier with documented limitations.

## Output
report/telemetry-completeness.md: per-config field table (authoritative/derived/
unavailable), stability results vs criteria 1–7, per-cell dispersion (median, IQR,
min–max) feeding the rep-count decision, and the go/no-go statement. CP-DATA reviews
this document.
