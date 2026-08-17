# Sealed mutation-catch check — for the human to author (W1b; SPEC §2.6)

This directory's contents are **gitignored** (only this README is tracked).
Everything you author here is human-held: never commit it, never paste it into a
model prompt, never place it under `results/`.

W1b is a **test-generation** task, so the sealed artifact is not a test — it is an
**executable runner** that mutation-tests the tests the agent wrote. Same shape as
W1's sealed runner, different subject.

| file | what it is |
|---|---|
| `check.sh` | executable; must be `chmod +x`. Drops each mutant into the subject tree, runs the agent's tests, and reports whether they caught it. |
| `mutants/` | the seeded mutants (one patch or one full replacement file each). |
| `VERSION` | human-readable label, e.g. `sealed-w1b-v1 2026-08-16 m=8`. |

Until `check.sh` exists and is executable, the 10-point validator reports checks 6
and 7 as `awaiting_human` (not failed) and still exits 0.

## What the agent produces, and what T1–T4 already guarantee

The agent adds **one new file** `tests/test_<something>_properties.py` and may change
nothing else. Before your runner is reached, the public gate has already established:

- **T1** only new files under `tests/` changed — no product edits, no conftest edits;
- **T2** `tests/test_indexing.py` plus the agent's file pass together;
- **T3** branch coverage of `src/zarr/core/indexing.py` ≥ 30%;
- **T4** the agent's tests pass against the pristine pinned product.

None of that proves the tests **assert** anything. A Hypothesis test that draws an
array, calls `zarray.blocks[idx]`, and asserts only `.shape` passes all four: a
10-line smoke test already reaches 26.19% branch coverage, and the threshold is only
30%. Closing that gap is what you are authoring. **Your runner is the authoritative
meaningfulness check** (SPEC §2.6); T3 is a coarse necessary-condition filter.

## What to mutate

Mutate **`src/zarr/core/indexing.py` only**, in the block- and mask-indexing paths —
the code the task is about. Line numbers below are at the pin
(`b9d396460da369bea86f4bd978d3746f7a41076b`); the class names are the durable
anchors.

| # | anchor | mutation shape | what it kills |
|---|---|---|---|
| M1 | `BlockIndexer.__init__` (l. 1045) — the per-dim start/stop computed from `chunk_shape` | off-by-one: `stop` short or long by one chunk | tests that assert only `.shape` when the selection is a single full chunk |
| M2 | `BlockIndexer` — the negative-index normalisation (`dim_sel + nchunks`) | drop the wraparound | tests that never draw a negative block index |
| M3 | `BlockIndexer` — the step-1 slice handling | treat `step` as ignored rather than rejected | tests that never draw a strided slice, or that swallow the exception |
| M4 | `BlockIndex.__setitem__` / `set_block_selection` write path (l. 1131) | write the value transposed, or write to the wrong chunk on the last (partial) chunk | **write-direction** tests that assert nothing after the write |
| M5 | `MaskIndexer.__init__` (l. 1299) — the flattening of the boolean mask to coordinates | use C-order where F-order is required (or vice versa) | tests whose mask has ≤1 True, or that compare only lengths |
| M6 | `is_mask_selection` (l. 1159) — the shape/dtype guard | accept a mask whose shape does not match the array | tests that always pass a correctly shaped mask (all of them will; this one is a **control** — see below) |
| M7 | `BoolArrayDimIndexer` (l. 623) — `nitems` / the per-chunk `dim_out_sel` offset | drop the running offset so chunk 2+ writes at the wrong output position | tests on single-chunk arrays only; the numpy oracle catches it only if the array spans chunks |
| M8 | `CoordinateIndexer` (l. 1169) — the sort that puts coordinates in chunk order | remove the sort / remove the inverse permutation applied to results | tests that compare sorted results, or that use a mask with one True |

Eight is a good number: enough that a vacuous suite cannot get lucky, small enough to
author in a sitting. **Adjust the list to what you can actually make fail** — a mutant
that the *canonical* does not catch is a bug in the mutant, not a finding. Verify
against the canonical before sealing (below).

### Keep at least one mutant that the canonical does NOT catch, and label it

M6 above is a plausible candidate. Record such mutants in a `control` list and
**exclude them from the pass threshold**. Their job is to tell you, later, whether a
surprisingly high score came from a genuinely better suite or from a leak. Do not let
a control mutant silently make the gate stricter than the canonical.

## `check.sh` contract

`harness/task-tools/gate/check-hidden.sh` (branch `test_generation`) does not read
your mutants. It only:

1. checks `hidden/check.sh` exists and is executable (else exit 2 → `awaiting_human`);
2. fingerprints **every file** under `hidden/` into one `sha256` and reads `VERSION`,
   so each result cites exactly which sealed set judged it;
3. runs `bash hidden/check.sh` with `SUBJECT_DIR` exported, discards stdout, and
   surfaces stderr into the gate log;
4. honours the exit code verbatim: **0 = accept · 1 = reject · 2 = unavailable**.

So `check.sh` owns the loop. It must:

- discover the agent's test file(s): untracked files under `$SUBJECT_DIR/tests/`
  matching `test_*_properties.py`. If there are none, exit **1** (a reject — the
  agent produced nothing to grade), not 2;
- for each mutant: apply it to `$SUBJECT_DIR`, run
  `HYPOTHESIS_PROFILE=ci .venv/bin/python -m pytest <agent files> -q -p no:cacheprovider`
  from `$SUBJECT_DIR`, and record **caught** iff pytest exits non-zero;
- **always restore** the tree between mutants (`git -C "$SUBJECT_DIR" checkout -- src`)
  — including on failure paths, via a `trap`. A leaked mutant poisons every later
  result and, worse, the run that follows;
- set `HYPOTHESIS_PROFILE=ci`. zarr's `ci` profile is `derandomize=True`
  (`tests/conftest.py`), so "caught" is a property of the test, not of the seed. The
  canonical's coverage was byte-identical across two derandomized runs; without this
  the whole gate is a coin flip on rare-example mutants;
- impose a per-mutant timeout (the canonical's two properties take ~70–90 s at
  `max_examples=300`; budget ~5 min per mutant and treat a timeout as **not caught**,
  logging it distinctly);
- print one line per mutant to **stderr** — `CAUGHT M3` / `NOT-CAUGHT M3` /
  `TIMEOUT M3`, and `CONTROL M6 <caught|not-caught>` for control mutants — and
  nothing that reveals the mutation itself;
- exit **0** iff every non-control mutant is caught; else **1**.

  Start at "all of them". Relax only with a written reason in `VERSION` — the whole
  point of a mutation gate is that a real oracle catches an off-by-one, and W1's
  sealed runner already uses all-or-nothing.

Reserve exit **2** for "the sealed set itself could not run" (missing `.venv`,
unreadable mutant, `git` failure) — never for a bad test suite.

## How to verify it in BOTH directions

```bash
TASK=tasks/suite/W1b-zarr-block-mask-properties
SUBJ=$PWD/$TASK/.work/repo

# --- direction 1: the CANONICAL must score a clean pass -----------------------
git -C "$SUBJ" checkout -- . && git -C "$SUBJ" clean -fd -e .venv -e .uv-cache
git -C "$SUBJ" apply "$PWD/$TASK/canonical/block-mask-property-tests.patch"
SUBJECT_DIR="$SUBJ" bash $TASK/hidden/check.sh; echo "canonical -> $?"   # expect 0
# Any NOT-CAUGHT here is a MUTANT bug (or a control), not an agent finding.

# --- direction 2: a VACUOUS suite must be rejected ----------------------------
# Write tests/test_vacuous_properties.py: draw the same arrays, call every one of
# the six interfaces, assert ONLY .shape and .dtype, no numpy oracle. It will pass
# T1/T2/T4 and sit just under or over T3.
SUBJECT_DIR="$SUBJ" bash $TASK/hidden/check.sh; echo "vacuous -> $?"     # expect 1

git -C "$SUBJ" checkout -- . && git -C "$SUBJ" clean -fd -e .venv -e .uv-cache
```

Keep the vacuous fixture in `hidden/` — it is part of the sealed set and is covered
by its hash, which is correct: changing the fixture changes the recorded identity of
the gate.

Then re-run the validator:

```bash
TASK_DIR=tasks/suite/W1b-zarr-block-mask-properties bash harness/task-tools/validate.sh
# before you author: 9 pass, 1 awaiting-human, 0 n/a, 0 failed
# after  you author: 10 pass, 0 awaiting-human, 0 n/a, 0 failed
```

## After sealing

Record the printed `hidden_test_hash` in `manifest/delivery-manifest.yaml` under
`w1b_task.sealed_hidden_test` (replacing `status: awaiting_human`), and re-seal per
evaluation cycle (SPEC §2.6). Note in the manifest that W1b is W1's
`second_task_for_class_claim`: a test-generation **class** claim needs both, and W1b
is the `post_cutoff` half.
