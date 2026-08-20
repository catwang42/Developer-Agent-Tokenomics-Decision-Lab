# Screening batch 1 — report folder

**STATUS: PENDING** — the batch has finished running, but nothing in this folder is a
result yet and **no figure here may be read as one**. The telemetry-completeness report
opens at CP-DATA; no number leaves this folder before CP-FINDINGS.

Pairs with the dataset `results/screening-batch1/` (CLAUDE.md rule 8).

## What is in here now

| File | What it is |
|---|---|
| `backfill.json` | the **v1** provider-meter backfill: each run's window had to be surrounded by silence to be attributed. Includes its refusals — a refusal is `unavailable`, never zero. |
| `backfill-v2.json` | the **v2** backfill under serialized-run ownership with a measured ingestion tail. Supersedes an earlier v2 pass of the same name that used a flat 300s tail and propagated inseparability transitively; both defects, and the corrected counts, are recorded in `results/screening-batch1/batch1.log` under *D (cont.)*. |
| `decision-table.json` / `.md` | the arm-map-aware decision table over the repaired dataset, from `harness/telemetry/summarize.py`. **STATUS: PENDING.** Carries verdict provenance (original / amended / void), run-budget confounds and pre-registration grading. |

## State of the batch (as of 2026-08-20)

- **122 runs across 42 cells** completed and validated.
- **Verdicts were repaired offline, at zero model spend.** 36 run verdicts are
  *amended*: the same sealed set re-run against the same archived `agent-solution.diff`
  after the container gate's git-ownership defect was fixed. No agent was re-run.
  17 runs went `rejected → accepted`, 1 to `unavailable`.
- **15 runs are voided.** `w6-hono-router-review` is unscoreable as run — the artifact
  under review was never delivered to the agent — and is adjudicated as such in
  `results/screening-batch1/adjudication.json`. A void is neither an accept nor a reject.
- **17 runs were ended by the harness before the agent finished**, under batch 1's flat
  1800s bound. Their gate results are instrument observations, not capability ones, and
  every grader in the decision table refuses the cells they sit in.
- **Product-B token totals are still largely unavailable.** 4 legs were recovered by the
  v2 attribution rule; 35 runs stay refused, 31 of them on the fixed 3M per-run
  plausibility ceiling, which binds hardest on the long Gemini-executor arms. That is
  why the H-effort registration grades `not_gradable (no_data)` on all 7 tasks. See the
  ceiling note in `batch1.log` — it is an instrument-design question for the human.
- **W3-escalation-probe grades `confounded_by_run_budget`.** Both halves are reported
  and neither is graded. The remedy is the makeup pass under the per-task
  `agent_timeout_s` now pinned in each `task.yaml`
  (`scripts/screening-batch1-makeup-driver.sh`, dry-run only — running it needs
  CP-SPEND).

Coverage is uneven across arms and several cells are confounded, so **nothing in this
folder supports a comparison of any kind** — not between arms, not between products,
not between tasks.
