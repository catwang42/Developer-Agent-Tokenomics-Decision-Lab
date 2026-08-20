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
| `backfill-v3.json` | the **v3** backfill: the v2 window and ownership rule with the fixed 3M per-run plausibility ceiling replaced by a rate ceiling (25,000 input-side tokens/s over the attributed window). 30 further legs attributed, 5 still refused, none of them on the rate ceiling. The measurements behind the number, and its KNOWN LIMIT, are in `batch1.log` under *F* and in `harness/collectors/README.md`. |
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
  The delivery defect (and two more found with it) is fixed in the harness and recorded
  in `batch1.log` *G*; the fix changes the instrument, so any re-run is a **separate
  dataset**, never merged into this one. The re-run is
  `scripts/screening-batch1-makeup-driver.sh --profile w6` into
  `results/screening-batch1-makeup-w6/`; running it needs CP-SPEND.
- **17 runs were ended by the harness before the agent finished**, under batch 1's flat
  1800s bound. Their gate results are instrument observations, not capability ones, and
  every grader in the decision table refuses the cells they sit in.
- **Product-B token totals are attributed on 72 of the 77 planned legs** — 38 under
  collector rule v1, 4 under v2, 30 under v3. The fixed 3M per-run plausibility ceiling
  was refusing duration rather than contamination on the long Gemini-executor arms; v3
  replaces it with a rate ceiling and recovered 30 legs, none of the remaining 5
  refusals being a rate refusal. The 5 are boundary and third-party cases and their
  usage stays `unavailable`, never zero. See `batch1.log` *D (cont.)* and *F*.
- **W3-escalation-probe grades `confounded_by_run_budget`.** Both halves are reported
  and neither is graded. The remedy is the makeup pass under the per-task
  `agent_timeout_s` now pinned in each `task.yaml`
  (`scripts/screening-batch1-makeup-driver.sh --profile w3`, into
  `results/screening-batch1-makeup/`; running it needs CP-SPEND).

Coverage is uneven across arms and several cells are confounded, so **nothing in this
folder supports a comparison of any kind** — not between arms, not between products,
not between tasks.
