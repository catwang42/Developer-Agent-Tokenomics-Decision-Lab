# Timed human-effort rubric — batch-2 feasibility subset (criterion 6)

Purpose: record the **human review/correction effort** to judge an agent's output, so
HEAC has real inputs (SPEC §2.6 timed-rubric tier; metrics.md HEAC). This measures the
*instrument*, NON-COMPARATIVE — no vendor claims, no headcount/FTE conversion.

**HEAC** = ECST + (active + review + correction minutes × `loaded_rate_per_minute`).
`loaded_rate_per_minute` is a **delivery-manifest input** (not yet set); record raw
**minutes** here and HEAC is computed later (no model spend). `blocked_minutes` are
reported separately and **never monetized into headcount**.

## The 9-run subset (one rep per controlled cell)

Review the agent's produced diff for each (view it, don't run the model):
`git show --no-index` is unnecessary — each run dir has `agent-solution.diff`.

| # | Cell | Run dir (under `results/feasibility-batch2/`) |
|---|---|---|
| 1 | F1·P0 | `pilot-realworld-draft-articles__P0__rep1__20260720T032707` |
| 2 | F1·C2 | `pilot-realworld-draft-articles__C2__rep1__20260720T033336` |
| 3 | F1·P1 | `pilot-realworld-draft-articles__P1__rep1__20260720T033737` |
| 4 | F2·P0 | `w4-realworld-missing-user-id__P0__rep1__20260720T034118` |
| 5 | F2·C2 | `w4-realworld-missing-user-id__C2__rep1__20260720T034547` |
| 6 | F2·P1 | `w4-realworld-missing-user-id__P1__rep1__20260720T035048` |
| 7 | F3·P0 | `w1-realworld-mapper-tests__P0__rep1__20260720T035514` |
| 8 | F3·C2 | `w1-realworld-mapper-tests__C2__rep1__20260720T040255` |
| 9 | F3·P1 | `w1-realworld-mapper-tests__P1__rep1__20260720T041142` |

The task prompt for each is in its `task.yaml` (`tasks/pilot-realworld/`,
`tasks/suite/W4-complex-bugfix/`, `tasks/suite/W1-test-generation/`).

## What to time (stopwatch; one pass per run, per reviewer)

Judge each run as if you were the reviewing engineer deciding whether to merge the
agent's diff. Record **minutes** (decimals ok, e.g. 3.5) in four buckets:

- **review_minutes** — stopwatch from opening `agent-solution.diff` + the task prompt to
  reaching your own accept/needs-work judgment (read the diff, check it against the task,
  spot-check correctness). This is the core number.
- **correction_minutes** — if the diff is **not** mergeable as-is, the hands-on time you
  (would) spend editing it to a mergeable state. If mergeable as-is, record **0**.
- **active_minutes** — time spent *actively steering the agent during generation*. These
  runs were **autonomous** (no human in the loop), so this is normally **0**; record >0
  only if you did hands-on steering.
- **blocked_minutes** — idle waiting during your review (e.g. waiting on a local build or
  test run), recorded separately; not part of the monetized sum.

## Anti-bias protocol

- **≥2 reviewers on ≥3 of the 9 runs** (for inter-reviewer spread); one reviewer on the
  rest is fine.
- Where practical, judge **before** looking at the gate verdict or the run's cost, so
  your review time isn't anchored by knowing it passed/failed.
- Use the same method each run (read diff → check against task → judge). Don't re-run the
  model. Don't optimize for speed; time honest review.
- If you can't judge a run (e.g. diff unreadable), record the bucket as `unavailable`
  with a one-line reason — **do not** enter 0.

## Recording table (fill this in; add rows for a 2nd reviewer)

| # | Cell | reviewer | review_min | correction_min | active_min | blocked_min | notes |
|---|---|---|---|---|---|---|---|
| 1 | F1·P0 | | | | | | |
| 2 | F1·C2 | | | | | | |
| 3 | F1·P1 | | | | | | |
| 4 | F2·P0 | | | | | | |
| 5 | F2·C2 | | | | | | |
| 6 | F2·P1 | | | | | | |
| 7 | F3·P0 | | | | | | |
| 8 | F3·C2 | | | | | | |
| 9 | F3·P1 | | | | | | |
| … | (2nd reviewer, ≥3 rows) | | | | | | |

When complete, hand this back: I'll ingest the minutes (no model spend) into each run's
`human_effort` slot, compute per-cell HEAC (once `loaded_rate_per_minute` is set in the
manifest), and report inter-reviewer spread — closing criterion 6.
