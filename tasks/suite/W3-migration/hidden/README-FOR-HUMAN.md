# Sealed test — for the human to author (W3; SPEC §2.6)

This directory's contents are **gitignored** (only this README is tracked).
Everything you author here is human-held: never commit it, never paste it into a
model prompt, never place it under `results/`.

W3 is a `solution` gate, so the sealed artifact is ordinary pytest module(s), not an
executable runner. The harness injects them, runs them, records their hash, and
removes them.

| | |
|---|---|
| filename glob | `*_sealed_test.py` (`hidden_test_glob` in `task.yaml`) |
| injected into | `test/core/dialects/` (`hidden_test_dest`) |
| also needed | nothing — the gate creates `test/core/dialects/__init__.py` if absent and removes it afterwards |
| version label | `hidden/VERSION`, e.g. `sealed-w3-v1 2026-08-16` |

**The suffix matters.** sqlfluff sets `python_files = "*_test.py"` in
`[tool.pytest.ini_options]`. A module named `test_something.py` is **silently not
collected** — it would report a vacuous pass. Name it `something_sealed_test.py`.

Until a matching file exists, the validator reports check 7 as `awaiting_human` (not
failed) and still exits 0.

## What the public gate already establishes

`tests/common_test.py` is **upstream's own** `test/core/dialects/common_test.py`,
byte for byte (only a provenance comment header is prepended). It is 9 tests over
ansi and bigquery, and each asserts both halves of the contract: the deprecated
wrapper emits `DeprecationWarning`, **and** it returns exactly what the free function
returns. Empirically, at the pin it fails at import
(`ImportError: cannot import name 'ObjectReferenceLevel'`) and with the canonical
applied it is `9 passed`.

The public gate also runs P2 regression over the hermetic baseline — `test/core`,
`test/utils`, `test/dialects/bigquery_test.py`, and the AL05/RF01/RF02/RF03/ST05/
ST09/ST11 rule tests. With the canonical applied that is `996 passed, 28 skipped`
plus `449 passed`, zero failures, five `DeprecationWarning`s (all from
`test/dialects/bigquery_test.py`, which still calls the old methods on purpose).

So the public gate already covers: the nine names exist and are importable, ansi and
bigquery agree, the wrappers warn, and nothing regressed.

## What the sealed test must add

Aim at the three ways a plausible-but-wrong migration passes the public gate.

1. **Dispatch that only knows the two dialects the public test uses.** A
   `if dialect_name == "bigquery": ... else: ...` passes everything above. Assert the
   free functions behave correctly for at least three more dialects that have their
   own reference/alias shapes — e.g. `snowflake`, `tsql`, `postgres`, `hive` — by
   parsing a qualified reference in each and comparing
   `iter_raw_references(segment, dialect_name)` and
   `extract_possible_references(...)` against the segment's own (deprecated) method
   result. Build the segments with `Linter(dialect=...)`, as upstream's test does.

2. **Wrappers that delegate but do not warn, or warn but do not delegate.** Assert
   the pairing for **every** migrated method, not the subset the public test happens
   to touch, and assert the two properties in the same call: wrap the call in
   `pytest.warns(DeprecationWarning)` **and** compare its return value to the free
   function's. The methods migrated by the canonical are on
   `ObjectReferenceSegment`, `WildcardExpressionSegment`, `ColumnReferenceSegment`,
   `TableReferenceSegment`, `FromExpressionElementSegment`, `JoinClauseSegment`, and
   `FromClauseSegment` in `dialect_ansi.py`, with BigQuery overrides of the column-
   and table-reference variants in `dialect_bigquery.py`. Read the canonical patch
   for the exact list; do not trust this paragraph as complete.

3. **Call sites that were never rewritten** — task requirement 3. This is the
   requirement with no public-gate coverage at all: leaving `RF01.py` calling
   `segment.extract_possible_references(...)` still passes every existing test,
   because the wrapper works. Assert it directly: lint a small SQL string with each
   of AL05, RF01, RF02, RF03, ST05, ST09, ST11 inside
   `warnings.catch_warnings(record=True)` with `simplefilter("always")`, and assert
   **no** `DeprecationWarning` whose message mentions the migrated methods was
   raised. Do the same for `sqlfluff.utils.analysis.query` / `select` via a lint that
   exercises them. Pick SQL that actually triggers each rule — a rule that never
   fires proves nothing. `test/rules/std_test.py` has usable fixtures.

Also worth asserting, cheaply:

4. `ObjectReferenceLevel` is an `Enum` with the levels the rules use, and the free
   functions accept both an `ObjectReferenceLevel` member and a plain `int` for the
   level argument (the canonical's `_level_to_int` exists for that back-compat).
5. `extract_possible_multipart_references` on BigQuery's hyphenated /
   multipart table references returns the same partition as the deprecated method —
   this is the single most dialect-specific behaviour in the migration.

### Do not assert

- module-internal helper names (`_raw_refs`, `_iter_raw_references_default`,
  `_level_to_int`, `deprecated_segment_method`, the `Protocol` class): they are the
  canonical's decomposition, not the contract. An equally correct migration may
  factor differently and must still pass.
- exact `DeprecationWarning` message text beyond "mentions the method name".
- the number of files changed, or that a given function lives in a given file beyond
  the nine names required to be importable from `sqlfluff.core.dialects.common`.

## How to verify it in BOTH directions

```bash
TASK=tasks/suite/W3-migration
SUBJ=$PWD/$TASK/.work/repo
DEST=$SUBJ/test/core/dialects

mkdir -p "$DEST" && touch "$DEST/__init__.py"
cp $TASK/hidden/*_sealed_test.py "$DEST/"

# --- direction 1: must FAIL at the pin (pre-modification) ---------------------
git -C "$SUBJ" checkout -- src
(cd "$SUBJ" && .venv/bin/python -m pytest test/core/dialects -q -p no:cacheprovider)
echo "pinned -> $?"      # expect non-zero (ImportError at collection is fine)

# --- direction 2: must PASS on the canonical ----------------------------------
git -C "$SUBJ" apply "$PWD/$TASK/canonical/migrate-segment-methods-to-free-functions.patch"
(cd "$SUBJ" && .venv/bin/python -m pytest test/core/dialects -q -p no:cacheprovider)
echo "canonical -> $?"   # expect 0

git -C "$SUBJ" checkout -- src
rm -rf "$DEST"
```

A sealed test that fails on the canonical is a bug in the sealed test — the canonical
IS the reference migration. A sealed test that passes at the pin is not testing the
migration.

Then re-run the validator:

```bash
TASK_DIR=tasks/suite/W3-migration bash harness/task-tools/validate.sh
# before you author: 9 pass, 1 awaiting-human, 0 n/a, 0 failed
# after  you author: 10 pass, 0 awaiting-human, 0 n/a, 0 failed
```

## Escalation probe — read this before authoring

W3 is the **designated escalation probe** for the screening batch (SPEC §5.1). It was
chosen because the economical tier is predicted to fail it. That imposes two
obligations on the sealed test:

- **Register the prediction first.** Write it in `manifest/preregistrations/` before
  any run, and before you tune anything here. The prediction must not be adjusted
  after seeing a result, and the sealed test must not be loosened or tightened after
  a run to make a prediction come true.
- **Author for the contract, not for the prediction.** Every assertion above must be
  one the canonical satisfies and a correct alternative migration would also satisfy.
  If you find yourself adding an assertion because it seems likely to trip a specific
  model, delete it.

Record the printed `hidden_test_hash` in `manifest/delivery-manifest.yaml` under
`w3_task.sealed_hidden_test` (replacing `status: awaiting_human`), and re-seal per
evaluation cycle (SPEC §2.6).
