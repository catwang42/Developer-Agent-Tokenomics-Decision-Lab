# ABORTED — not a run, not data

This directory holds a single `run_started` event and nothing else. The run was
killed by the operator at 2026-08-17 ~02:54:50Z, about 100 seconds after it started,
because the immediately preceding run (`…__C3__rep1__20260817T024401`) was found to
have written **outside** its staged subject tree, into the lab's own
`tasks/pilot-realworld/.work/repo` — the tree this run had just staged from.

Its staged input was therefore contaminated with the previous run's solution, so
whatever it produced could not have been graded honestly. It is retained, empty and
labelled, rather than deleted: the abort is part of the smoke's provenance.

**No summary.json, no cost, no usage.** It contributes nothing to any total and must
not be counted as a run. See `report/smoke-screening/smoke-report.md` finding
**SMOKE-3**.
