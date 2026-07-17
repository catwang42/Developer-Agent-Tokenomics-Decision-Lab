# Phase 5 — Workshop Site on GitHub Pages (SPEC §3; may run in parallel after Phase 0)
**Goal:** the decision-lab curriculum as a polished MkDocs Material site, auto-deployed.
**Branch:** phase/5-site

## Tasks
1. Build out docs/: index (module cards + 240-min agenda + formats), setup (pre-work +
   doctor), m0..m4 module pages, exercises/ex110..ex410 pages (timed parts + completion
   checklists), cheatsheet (claims register card + seven-point audit checklist),
   facilitator.md (fallback ladder, checkpoint script, disclosure slide text).
2. Follow the claims register (SPEC §1.2) — placeholders for models, no exact pilot
   percentages, black-box disclaimer on gallery pages.
3. report/calculator: static HTML/JS break-even & sensitivity calculator embedded in docs
   (no external services, no browser storage).
4. mkdocs build --strict green; deploy workflow publishes to Pages on main.
5. Any page that will show measured results loads them from results/pilot-reference/
   ONLY, and only after **CP-FINDINGS**; site publish of results content gated by
   **CP-PUBLISH**.

## Acceptance checklist
- [ ] mkdocs build --strict green; site nav complete; a11y-reasonable defaults
- [ ] zero claims-register violations (grep audit listed in PR)

**Inputs added:** plans/EXERCISE-SPECS.md is the content contract for all exercise pages; methodology/*.md feed M3.

6. Governance scenario pack (3 scenarios) + one-page decision-memo template under docs/exercises/ (ex410 inputs); simple report/cohort-display.py for the ex230 in-room variance view (static, labeled, not a service).

7. Workshop-day dashboard per report/workshop-dashboard/DASHBOARD-SPEC.md (serve.sh, collect.py, submit-cohort.sh, export.sh, views 1-6) with SYNTHETIC-fixture tests.
