# Graded quality extraction — what came out, and the two tasks it could not reach

**STATUS: AUTHORITATIVE (2026-08-21).** Cross-cutting; not dataset-scoped. Documents
`harness/analysis/quality.py` and the per-run `quality-score.json` sidecars it writes
across every dataset under `results/`. Supersedes nothing.

> **EXPLORATORY SECONDARY.** The pre-registered outcome for every task is the binary
> sealed gate, and nothing here moves it. A run the gate rejected is rejected. These
> figures exist to show *how far off* a rejection was, and they are never reported as
> the outcome.

## What this pass does

It reads sealed output that each run **already archived** under `results/` — the
hidden gate's own transcript — and counts. It re-runs nothing, opens no file under
`tasks/*/hidden/`, and overrides no acceptance verdict. Where the detail is not in the
archive the record says `available: false` with the reason. It is never a zero
(CLAUDE.md rule 3: unavailable ≠ 0), because a zero would read as "the model found
nothing" when the truth is "nobody wrote it down".

Truncated runs are excluded outright, whatever their log contains. A run the harness
cut off is not a measurement of the model, and a partial score from one is worse than
none.

Metrics registered, per the extraction scope agreed for this pass:

| task | metric | read from |
|---|---|---|
| W1 | mutants caught (jest mutation runner) | sealed runner stderr |
| W1b | mutants caught, control mutant reported separately | sealed runner stderr |
| W6 | planted defects found, and fabrications — two numbers, never netted | sealed runner stderr |
| W3 | sealed rules clean, 0..7 | per-check block |
| W4b | sealed assertions passed, 0..3 | per-check block |

## What came out

Scored: **W1 18 runs, W1b 18 runs, W6 15 runs** (the confound makeup added one of each). Every other run carries an explicit
reason, and the reasons are counted in the limitation ledger of the consolidated table.

**W3 and W4b produced no graded quality at all.** Both read the hidden gate's
`-- sealed checks (id and status only) --` block, and for every one of their runs that
block is absent.

## Why W3 and W4b are empty

Presence of the per-check block, across all regrade-v2 hidden transcripts:

| task | v2 transcripts | block present | hidden-gate exit |
|---|---|---|---|
| pilot | 9 | 9 | 0 ×9 |
| W4 (node stack) | 17 | 17 | 0 ×17 |
| W1 | 17 | 0 | 0 ×17 |
| W1b | 17 | 0 | 0 ×17 |
| W6 | 14 | 0 | 1 ×9, 0 ×5 |
| **W3** | **15** | **0** | **4 ×15** |
| **W4b** | **16** | **0** | **1 ×16** |

W1, W1b and W6 have no block by design — their sealed runners are mutation and review
harnesses that print one labelled line per mutant/defect to stderr, which is exactly
what this pass reads for them. The block is a `solution`-task device, and it works: the
node stack writes it on all 17 W4 runs and all 9 pilot runs.

The two python-stack `solution` tasks are the gap. `stack_run_selected_graded` in
`harness/task-tools/stacks/python.sh` runs the task's declared pytest selection with
`--tb=no -rA` and greps the short summary for `<STATUS> <node-id>`; for W3 and W4b that
grep matched nothing, so the gate wrote no block (`[ -s "$graded" ]` is false) and only
the exit code survives.

**For W3 the cause is identified and it is not a reporting gap.** The hidden gate exits
**4** — pytest's USAGE ERROR — on all 15 v2 transcripts *and* on all 8 surviving
original (pre-regrade) transcripts. The graded step landed between those two gradings,
so it did not cause this: **W3's sealed suite has never executed, in any grading
generation.** There is nothing to extract because nothing ran.

For W4b the gate exits 1 on all 16 and the summary grep still matched nothing; the
cause is not established from the archive alone and is recorded here as open.

### A third generation, and it settles the ambiguity

The confound makeup (2026-08-21, `results/screening-batch1-confound-makeup/`) is the
first dataset graded **live** by a gate that already carried the per-check step — the
five gate images it used are the content-hashed ones, and their digests recompute from
the tree unchanged. So for its runs, an empty capture cannot mean "the feature did not
exist yet". It came back empty anyway:

| task | runs | hidden exit | per-check block |
|---|---|---|---|
| W3 | 3 | 4 ×3 | absent ×3 |
| W4b | 2 | 1 ×2 | absent ×2 |

That closes the W3 question for good: **exit 4 in all three grading generations**, the
third under a gate that demonstrably records per-check results. The suite does not run,
full stop. For W4b it narrows the open item — the capture is empty under a gate known
to carry the step, so the gap is in `stack_run_selected_graded` for that task's pytest
selection, not in the gate's plumbing. Still unresolved, still recorded, still with no
verdict depending on it.

`harness/analysis/quality.py` distinguishes the two cases by the run's own start stamp
against the commit that added the step (9e84315, 2026-08-21T02:18:18Z), because no run
records a harness sha. A run graded before it says "the detail was never written down";
a run graded after it says "the capture came back empty". Neither is ever a zero.

## Does this change any verdict?

**No.** Two independent reasons, both checked against the archive:

1. The hidden verdict is identical between the original grading and regrade-v2 for
   every W3 and W4b run — `fail` in both.
2. The acceptance decision never reaches the sealed gate for these tasks. Across
   **all 32 W3 runs and all 20 W4b runs, in every arm, zero passed the public checks**:
   every single run fails both `P1-public-test` and `P2-regression`. The gate is
   deterministic-first, so each of those runs is rejected on the public tier before the
   sealed tier is consulted.

That second fact deserves its own line in the limitation ledger, independent of
quality extraction: **W3 and W4b have a 0/32 and 0/20 acceptance rate across every
arm, including the strongest** (counts over all four screening datasets; the confound
makeup added three W3 runs and two W4b runs, and none of them changed it). A task that no arm passes does not discriminate between
arms, and no comparative reading may be taken from either of them. Whether that is a
property of the tasks or of their instruments is not resolved here.

## What was deliberately not done

- **The gate was not changed to chase this.** Gate content is hashed into the gate
  image tag (PR #27), so editing `python.sh` changes the digest for *every* task and
  invalidates the entire regrade-v2 sweep. Buying a re-sweep of 130 runs to recover an
  exploratory-secondary metric on two tasks that no arm passed is not a trade worth
  making before the deadline. Recorded, not improvised around.
- **W4 was not registered for extraction** even though its per-check block is present
  and parseable on all 17 runs. Which quality metrics are extracted is an analysis
  choice; adding one that was not in the agreed scope after seeing the data is exactly
  what pre-registration exists to prevent. Flagged for the human as an available
  extension, not taken unilaterally.

## Reproduce

```
.venv/bin/python -m harness.analysis.quality results            # table
.venv/bin/python -m harness.analysis.quality results --write    # per-run sidecars
```
