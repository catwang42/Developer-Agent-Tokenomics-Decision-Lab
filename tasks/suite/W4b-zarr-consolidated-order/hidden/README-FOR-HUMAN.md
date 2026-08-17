# Hidden tests — for the human to author (W4b; SPEC §2.6 sealed policy)

This directory's contents are **gitignored** (only this README is tracked). The
sealed hidden tests are **human-held**: never commit them, paste them into a model
prompt, or place them under `results/`.

The shared hidden gate (`harness/task-tools/gate/check-hidden.sh`) finds every file
here matching `hidden_test_glob` — for this task **`test_*_sealed.py`** — records a
`sha256` version+hash, copies them into the subject repo's
`tests/test_metadata/`, runs them with the subject's own pytest, then removes them.
Until you author tests here, the 10-point validator reports check 7 as
`awaiting_human` (not failed) and still exits 0.

Name the files `test_<something>_sealed.py` so they (a) match the glob, (b) are
collected by pytest, and (c) cannot collide with an upstream module already in
`tests/test_metadata/`.

## The defect, precisely

Subject: `ConsolidatedMetadata._flat_to_nested` in `src/zarr/core/group.py`, at pin
`a994a4fc972fed428eab6a26d4f14bb95d22c144`.

It rebuilds a nested node tree from a **flat** mapping of slash-separated keys. At
the pin it groups keys by parent with:

```python
keys = sorted(metadata, key=lambda k: k.count("/"))
grouped = {k: list(v) for k, v in itertools.groupby(keys, key=lambda k: k.rsplit("/", 1)[0])}
```

`itertools.groupby` groups **consecutive runs only**, and the sort key is depth
alone — so same-parent keys that are not adjacent after that sort land in separate
runs, and the dict comprehension keeps only the last run per parent. Every earlier
run is silently dropped: those children never get attached to their parent, and the
bogus slash-containing key stays at the top level. The upstream fix accumulates into
a `defaultdict(list)` instead (`canonical/fix-flat-to-nested-order.patch`).

The persisted key order is arbitrary, so **the correct behaviour is that the
reconstructed tree is identical for every permutation of the same key set.**

## What the sealed test must assert

The public test (`tests/test_consolidated_order_public.py`, the upstream PR's own
test, injected by the public gate) already covers three key orders on a two-level
tree. The sealed test exists so a solution that special-cases the public test's
shape does not pass. Make it discriminating along these axes:

1. **Order-independence as a property, not three examples.** Build a key set, then
   assert that `ConsolidatedMetadata.from_dict(...)` produces the *same* nested
   structure for several *different* permutations of it — compare the permutations
   against each other, not against a hand-written expected tree. `itertools.permutations`
   over a small key set is enough; do not import Hypothesis (it is a test-group
   dependency of the subject repo and this must stay cheap and deterministic).
2. **Depth ≥ 3.** The public test is two levels deep. Use at least `a/b/c` so a fix
   that only repairs the top level is caught.
3. **More than two children per parent, and >2 sibling subtrees**, so a fix that
   keeps only the first *or* only the last run still fails.
4. **No bogus top-level keys.** Assert that no key in `consolidated.metadata`
   contains a `/`. This is the direct signature of a dropped run and is what a
   partial fix most often leaves behind.
5. **Mixed node types.** Include at least one array among the groups (an entry with
   `node_type: "array"` and its required fields) so the fix is not specific to
   groups.
6. **Round-trip.** Assert `ConsolidatedMetadata.from_dict(cm.to_dict())` reproduces
   the same nested structure — the flattening/nesting pair must be stable.

Keep it in-process and store-free: `ConsolidatedMetadata.from_dict` takes plain
dicts, so no store, no I/O, no network, no `async`. Deterministic — no randomness,
no time.

Do **not** assert on the sorted order of `grouped`, on `itertools` being absent, or
on any other implementation detail: the gate grades behaviour, and a different but
correct fix must pass.

## How to verify it in BOTH directions

Both directions must be checked by hand before you seal, because the validator only
exercises the canonical direction.

```bash
cd tasks/suite/W4b-zarr-consolidated-order
TASK_DIR=$PWD bash ../../../harness/task-tools/setup.sh      # clone + uv sync at the pin
SUBJ=.work/repo

# --- direction 1: MUST FAIL on the pinned (buggy) tree ---
git -C $SUBJ checkout -q --force a994a4fc972fed428eab6a26d4f14bb95d22c144
cp hidden/test_*_sealed.py $SUBJ/tests/test_metadata/
( cd $SUBJ && .venv/bin/python -m pytest tests/test_metadata/test_*_sealed.py -q )
# expect: FAILURES. If it passes here, the test does not discriminate — rewrite it.

# --- direction 2: MUST PASS on the canonical fix ---
git -C $SUBJ apply "$PWD/canonical/fix-flat-to-nested-order.patch"
( cd $SUBJ && .venv/bin/python -m pytest tests/test_metadata/test_*_sealed.py -q )
# expect: all passed.

# clean up so nothing sealed is left in the work tree
rm -f $SUBJ/tests/test_metadata/test_*_sealed.py
git -C $SUBJ checkout -q -- .
```

Then run the full validator, which will now exercise check 7 for real:

```bash
TASK_DIR=tasks/suite/W4b-zarr-consolidated-order bash harness/task-tools/validate.sh
# expect: 10 passed, 0 awaiting-human, 0 n/a, 0 failed
```

Add a `VERSION` file here with a human-readable label (e.g.
`sealed-w4b-v1 2026-08-16 permutation+depth3`). Record the printed
`hidden_test_hash` in `manifest/delivery-manifest.yaml` under `w4b_task`
(replacing `sealed_hidden_test.status: awaiting_human`) and in
`manifest/RUN_TEMPLATE.md`. Rotate/reseal per evaluation cycle (SPEC §2.6).
