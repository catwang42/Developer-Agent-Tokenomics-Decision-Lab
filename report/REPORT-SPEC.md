# Results Visualization Contract (implements SPEC §4.2 component 5)
The final-results "dashboard" is a STATIC report — charts generated at build time by
report/generate.py, embedded in the docs site (docs/results.md), published only after
CP-FINDINGS and CP-PUBLISH. No SaaS, no live services, no browser storage.

## Required views (from results/pilot-reference/ run summaries ONLY)
1. **Cost per accepted task, by configuration × task class** — box/strip plot showing
   median, IQR, and individual runs (variance visible, never hidden behind a mean).
2. **Cost-view toggle** — every economic chart rendered twice: marginal_operating and
   fully_allocated. If direction flips between views, the report must say so in text.
3. **Quality panel** — success rate with uncertainty interval per configuration × class;
   failure categories as a separate breakdown (never averaged into cost).
4. **Escalation panel (P1)** — intention-to-route vs completed-route; failed-attempt
   cost share; the measured p_fail feeding the break-even formula.
5. **C5 workflow panel** — stacked conductor/executor legs per run; total cost headline;
   frontier_token_share as a small diagnostic dial (labeled diagnostic).
6. **Break-even & sensitivity explorer** — the static HTML/JS calculator
   (routing-policy.md formula): sliders for task volume, p_fail, review minutes,
   cost view; output always a shaded range, never a point estimate.
7. **Cache economics panel** — the warm-series data only, plotted separately from cold
   cells; naive-vs-cache-aware recomputation of the ex120 pinned run.
8. **Screening annex (results/screening/)** — separate page carrying the mandatory
   transparency label verbatim (SPEC §5); candidate advantages only; nulls/negatives
   shown with equal visual weight.

## Rules
- Every chart caption carries the pinned-conditions scope line (task suite version,
  manifest ref, pricing snapshot date, n per cell).
- No suite-wide aggregate chart without a declared task-mix weighting note.
- Cohort exercise data (results/cohort/) may appear ONLY in a workshop-day view
  shown on the local workshop-day dashboard (see workshop-dashboard/DASHBOARD-SPEC.md), clearly labeled
  "cohort exercise data — operational variance illustration", never merged into 1–8.
- Tech: matplotlib/plotly-static or vanilla JS + SVG; output committed under site
  build, reproducible (same inputs → same charts).
