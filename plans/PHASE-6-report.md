# Phase 6 — Pilot Reference Dataset & Static Analysis Report (SPEC §2.3, §4.2)
**Goal:** >=5 reps/cell pilot reference dataset on validated tasks; report generator.
**Branch:** phase/6-report

## Tasks
1. **CP-SPEND**, then pilot reference runs (>=5 reps/cell; rep count revisited after
   observing variance) -> results/pilot-reference/ (write-protected; human merges).
2. report/generate.py: from run summaries -> QA-ECST by task class, HEAC, success rate,
   cost/attempt, both cost views, declared statistics (SPEC §2.4: medians+IQR,
   uncertainty intervals, failure categories separate, ITR+CR for escalation).
3. Technical report draft per SPEC public-positioning boundaries. **CP-FINDINGS**,
   then **CP-PUBLISH** for the site results section.

## Acceptance checklist
- [ ] generator reproducible (same inputs -> same report); stats match SPEC §2.4 rules
- [ ] every figure carries pinned-conditions scope line

**Visualization contract:** report/REPORT-SPEC.md defines all required views — implement against it, do not improvise.
