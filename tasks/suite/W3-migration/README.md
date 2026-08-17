# W3 — behaviour-parity migration (sqlfluff segment methods → free functions)

Screening task, added 2026-08-16. Candidate **C5** in
[`tasks/proposals/2026-08-commit-mined-candidates.md`](../../proposals/2026-08-commit-mined-candidates.md).
Definition: [`task.yaml`](task.yaml) · workload framing: [`workload.yaml`](workload.yaml).

> **This is the designated escalation probe for the screening batch** (SPEC §5.1).
> It was selected *because* the economical tier is predicted to fail it. The
> prediction is registered by the human in `manifest/preregistrations/` before any
> run, and the result is published either way — a pass refutes the prediction and is
> reported as such.

## Provenance

Commit-mined per `tasks/WORKLOAD-SELECTION.md` §4. Both SHAs were resolved through
the GitHub API and re-verified locally against a clone (`parents[0]` of N equals
N−1; squash merge, single parent).

| | |
|---|---|
| Repo | [sqlfluff/sqlfluff](https://github.com/sqlfluff/sqlfluff) · MIT · 9,855 stars (2026-08-16) |
| PR | [#7962](https://github.com/sqlfluff/sqlfluff/pull/7962) — *refactor: extract reference/alias segment methods into dialect-dispatched free functions* |
| Merged | 2026-06-17T18:52:26Z |
| N (fix) | `ee00054a89fe1850695601297d41d7e95559eb00` |
| N−1 (pin) | `7700446fdb424ba56a2b1963a624d3747df53744` |
| Contamination tier | `post_cutoff` — declared before running, never revised on results; model-relative (WORKLOAD-SELECTION §2) |

## The change

Reference and alias resolution lives as methods on dialect segment classes
(`ObjectReferenceSegment` and friends in `dialect_ansi.py`, overridden in
`dialect_bigquery.py`). Rules and analysis utilities call those methods, coupling
rule logic to the dialect class hierarchy. The PR moves that logic into nine
dialect-dispatched free functions in `sqlfluff.core.dialects.common`, keeps every
migrated method as a thin deprecated wrapper that delegates and emits a
`DeprecationWarning`, and rewrites the in-tree call sites to bypass the wrappers.

The real change is **1,551 lines across 12 source files**:

```
src/sqlfluff/core/dialects/common.py     +473    src/sqlfluff/rules/references/RF03.py     29
src/sqlfluff/dialects/dialect_ansi.py     303    src/sqlfluff/rules/structure/ST05.py      10
src/sqlfluff/dialects/dialect_bigquery.py 123    src/sqlfluff/rules/structure/ST09.py      20
src/sqlfluff/rules/references/RF01.py      57    src/sqlfluff/rules/structure/ST11.py      17
src/sqlfluff/rules/aliasing/AL05.py        12    src/sqlfluff/utils/analysis/query.py       4
src/sqlfluff/rules/references/RF02.py       4    src/sqlfluff/utils/analysis/select.py     12
```

plus, upstream, `test/core/dialects/common_test.py` (+131, the public gate here),
`test/core/dialects/__init__.py` (+1) and `test/dialects/bigquery_test.py` (+58).
`canonical/` contains the source half only — the test half is the gate.

## Why it should discriminate

- **Breadth, not depth.** No single insight solves it; 12 files must move together
  and stay consistent. Batch 3's ceiling came from tasks where one correct edit was
  enough.
- **The failure mode is silent.** Requirement 3 — rewrite the call sites so they stop
  going through the wrappers — has **no public-gate coverage**. A migration that
  leaves `RF01.py` calling the deprecated method still passes every existing test,
  because the wrapper works. That is exactly the kind of half-done migration a weaker
  configuration produces, and it is what the sealed test is aimed at.
- **Dialect dispatch is a trap.** Special-casing the two dialects the visible test
  exercises (ansi, bigquery) passes the public gate and breaks snowflake, tsql,
  postgres and hive.
- **Back-compat is a second, opposite constraint.** The wrappers must both *warn* and
  *return exactly what the free function returns*. Getting one without the other is
  easy; upstream's own test asserts both in every case.

## Gate

`gate_type: solution`, `stack: python`. Hermetic: no network, no database, no dbt
plugin.

| check | what runs |
|---|---|
| P1 public test | upstream's own `test/core/dialects/common_test.py`, byte for byte (only a provenance comment header prepended), injected into `test/core/dialects/` |
| P2 regression | `test/core` + `test/utils` + `test/dialects/bigquery_test.py`, then `test/rules -k 'AL05 or RF01 or RF02 or RF03 or ST05 or ST09 or ST11'` |
| P3/P4 | `import sqlfluff, sqlfluff.core.dialects.common` |
| P5 | no planted solution markers or stray patches |
| P6 | only the 12 declared source files changed; **any** edit under `test/` fails |
| hidden | sealed pytest module, human-held — see [`hidden/README-FOR-HUMAN.md`](hidden/README-FOR-HUMAN.md) |

**Measured, on this machine (2 cores):**

| | at the pin | with `canonical/` applied |
|---|---|---|
| public test | `ImportError: cannot import name 'ObjectReferenceLevel'` (collection error) | `9 passed in 9.30s` |
| baseline part 1 | `987 passed, 28 skipped in 39s` | `996 passed, 28 skipped in 39.29s` (= 987 + the 9 injected) |
| baseline part 2 | `449 passed` | `449 passed in 79.87s` |

Zero failures with the canonical applied; the only diagnostics are five
`DeprecationWarning`s, all from `test/dialects/bigquery_test.py`, which calls the old
methods on purpose. Behaviour parity holds. Whole-suite runtime for reference:
`2387 passed in 1508.93s` serial — far too slow for a per-run gate, which is why the
rules scope is filtered to the seven rules this migration reaches.

## Environment pinning

Upstream `requirements_dev.txt` is **completely unpinned** (`ruff`, `pytest`,
`mypy[mypyc]`, …), so a pinned commit would not imply a pinned environment and SPEC
§2.8 checks 4/5/9 would measure a moving target.
[`env/requirements.lock.txt`](env/requirements.lock.txt) holds 81 exact versions
frozen (`uv pip freeze`) from the venv that produced every number above. The two
local editables (`.` and `plugins/sqlfluff-plugin-example`, needed by
`test/core/plugin_test.py`) are installed separately with `--no-deps`.

## Current status

Ten-point validation stands at **9 pass · 1 awaiting_human · 0 n/a · 0 failed** —
check 7 awaits the sealed test. See the run section of
[`hidden/README-FOR-HUMAN.md`](hidden/README-FOR-HUMAN.md) for what to author; note
in particular that pytest here is configured `python_files = "*_test.py"`, so a
sealed module named `test_*.py` would be silently uncollected.

## Run it

```bash
TASK_DIR=tasks/suite/W3-migration bash harness/task-tools/setup.sh
TASK_DIR=tasks/suite/W3-migration bash harness/task-tools/validate.sh
TASK_DIR=tasks/suite/W3-migration bash harness/task-tools/reset.sh
```

No model spend is involved in any of the above.

## Files

| path | tracked | what |
|---|---|---|
| `task.yaml` | yes | task definition, pins, prompt, gate wiring |
| `workload.yaml` | yes | W3 workload framing, probe and class-claim notes |
| `canonical/migrate-segment-methods-to-free-functions.patch` | yes | `git diff N-1 N -- src/sqlfluff/` (12 files, 1,551 lines) |
| `tests/common_test.py` | yes | the public gate: upstream's own new test module |
| `env/requirements.lock.txt` | yes | 81 exact pins, frozen from the measured venv |
| `hidden/README-FOR-HUMAN.md` | yes | sealed-test authoring instructions |
| `hidden/*_sealed_test.py`, `hidden/VERSION` | **no** | sealed, human-held |
| `.work/` | no | runtime clone; never committed |
