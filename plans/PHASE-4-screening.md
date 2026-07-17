# Phase 4 — Positioning Evidence Screening (SPEC §5)
**Goal:** pre-registered W1–W5 screening under the anti-selection-bias protocol.
**Branch:** phase/4-screening

## Tasks
1. Define tasks/suite/W1..W5 (mass test generation; scaffold-heavy feature; mechanical
   migration; complex bug repair; small one-off edit). Each: workload.yaml (pinned repo,
   commit, prompt, gate script, reset), pre-registration doc from manifest/RUN_TEMPLATE.md.
2. **CP-SCREEN-PREREG**: all five pre-registrations + transparency label reviewed BEFORE
   any run. No task additions/removals after this point.
3. **CP-SPEND** per batch. Run screening: 5 workloads x {C1,C2,C3,C5} x 3 reps ->
   results/screening/ (label: hypothesis-seeking; not publishable).
4. Screening report per SPEC §5.2 decision rules (candidate advantages only; two-task
   rule flagged; both cost views; C2 comparison mandatory; negative/null findings
   included). **CP-FINDINGS** before the report is referenced anywhere.

## Acceptance checklist
- [ ] pre-registrations committed before runs (git history proves order)
- [ ] all classes reported incl. null/negative; both cost views present
- [ ] report carries the mandatory transparency label verbatim (SPEC §5)

**Inputs added:** tasks/suite/W*/workload.yaml (candidate stubs) + workload-TEMPLATE.yaml — pin repos/commits at CP-SCREEN-PREREG.

**Note:** F2/F3 feasibility usage of W4/W1 candidates must be disclosed in their screening pre-registrations.
