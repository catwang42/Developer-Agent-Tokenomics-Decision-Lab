# W1b — property-test generation for block & mask indexing (zarr-python)

Screening task, added 2026-08-16. Candidate **C7** in
[`tasks/proposals/2026-08-commit-mined-candidates.md`](../../proposals/2026-08-commit-mined-candidates.md).
Definition: [`task.yaml`](task.yaml).

**W1b is W1's second task, not a workload of its own.** It has no `workload.yaml`;
[`tasks/suite/W1-test-generation/workload.yaml`](../W1-test-generation/workload.yaml)
names it under `second_task_for_class_claim`. `tasks/WORKLOAD-SELECTION.md` §3
(extending SPEC §5.2): a screening signal only becomes a *workload-class* claim when
a second, materially different task from the same class, at tier `obscure` or
`post_cutoff`, agrees. W1 is hand-authored example-based unit tests over two 20-line
TypeScript mappers at tier `famous`; W1b is commit-mined Hypothesis property tests
over a 30k-line Python array library at tier `post_cutoff`. Different language,
ecosystem, testing style and contamination tier — which is the point.

## Provenance

Commit-mined per `tasks/WORKLOAD-SELECTION.md` §4. Both SHAs were resolved through
the GitHub API and re-verified locally against a clone (`parents[0]` of N equals
N−1; squash merge, single parent).

| | |
|---|---|
| Repo | [zarr-developers/zarr-python](https://github.com/zarr-developers/zarr-python) · MIT · 2,037 stars (2026-08-16) |
| PR | [#4054](https://github.com/zarr-developers/zarr-python/pull/4054) — property tests for block and mask indexing |
| Merged | 2026-06-09T02:27:00Z |
| N (fix) | `96a62b51f8fe86eeb056eee1684eef94b4114e35` |
| N−1 (pin) | `b9d396460da369bea86f4bd978d3746f7a41076b` |
| Contamination tier | `post_cutoff` — declared before running, never revised on results; model-relative (WORKLOAD-SELECTION §2) |

Shares the zarr toolchain image and uv cache with
[W4b](../W4b-zarr-consolidated-order/) (different pin, different checkout); `uv sync`
against the warm shared cache is ~4 s.

## What the participant does

Add **one** new file `tests/test_<something>_properties.py` containing Hypothesis
property tests for block indexing (`Array.blocks[...]`, `get_block_selection`,
`set_block_selection`) and mask indexing (`get_mask_selection`,
`set_mask_selection`, `Array.vindex[mask]`) — read *and* write, dedicated method
*and* indexer property, each compared against a numpy oracle. It may change nothing
else: not `src/zarr/core/indexing.py`, not `src/zarr/testing/strategies.py`, not
`tests/test_properties.py`, not conftest.

### Why it is harder than W1

W1 asks for example-based tests over two mappers with six branches between them, in
a file the agent can read end to end. W1b asks the agent to:

- **write a generator, not examples.** Block indexing is basic indexing over the
  *chunk grid* and is stricter than numpy — only integers and step-1 slices whose
  start references an existing chunk. A strategy that does not filter for that
  produces false failures; a strategy that over-filters produces a vacuous test that
  Hypothesis may not even flag.
- **construct a correct oracle.** The block indexer must be translated into an
  array-space slice before numpy can be asked what the answer is. That translation is
  where the reasoning is, and it is not checkable by staring at the code under test.
- **find the strategies.** `zarr.testing.strategies` is a published surface the agent
  is told to use, and the right combination (`simple_arrays`, `rectilinear_arrays`,
  `np_array_and_chunks`, `basic_indices`, `stores`) is not obvious.
- **notice the config flag.** `rectilinear_arrays()` needs
  `array.rectilinear_chunks` enabled or the test errors on generated input.

## Gate

`gate_type: test_generation`, `stack: python`. Four public checks plus one sealed:

| check | what runs |
|---|---|
| T1 diff-scope | only NEW files under `tests/`; any product, config or existing-test edit fails |
| T2 suite-green | `tests/test_indexing.py` + the agent's new file pass together |
| T3 coverage | branch coverage of `zarr.core.indexing` ≥ 30% |
| T4 tests-pass | the agent's tests pass against the pristine pinned product |
| hidden | sealed mutation-catch runner, human-held — [`hidden/README-FOR-HUMAN.md`](hidden/README-FOR-HUMAN.md) |

### The coverage threshold is measured, not chosen

Both endpoints of the band were measured on this machine:

| suite | statements | branches |
|---|---|---|
| a 10-line smoke test calling every one of the six interfaces once, asserting shapes | 26.90% | **26.19%** |
| `canonical/` (upstream's two property tests) | 31.94% | **34.13%** |

30% sits inside that 8-point band with ~4 points of headroom on each side. `branches`
is the metric because it separates the two suites better than `statements` does. The
absolute number is low because `zarr/core/indexing.py` is one 800-statement module
serving *every* indexing mode while this task targets two — the honest ceiling is not
100%, exactly as in W1 (`report/findings/w1-coverage-analysis.md`).

T3 is a **coarse necessary-condition filter**: an oracle-free suite can clear 30%.
The sealed mutation-catch runner is the authoritative meaningfulness check (SPEC
§2.6).

### Determinism

Every zarr command in this task runs under `HYPOTHESIS_PROFILE=ci`, which selects
zarr's own `derandomize=True` profile (`tests/conftest.py`). A coverage *threshold*
over a randomised strategy is not a gate. Verified: two consecutive derandomized runs
of the canonical produced byte-identical coverage — 250/800 statements, 86/252
branches, both runs.

The baseline command globs `tests/test_*_properties.py` under `nullglob`, so at the
pin — where no such file exists — it collapses to `tests/test_indexing.py` alone
(`150 passed, 1 skipped, 5 xfailed in 30.49s`) and SPEC §2.8 check 5 stays
meaningful. Note zarr's own `tests/test_properties.py` does **not** match that glob.

## Current status

Ten-point validation: **9 pass · 1 awaiting_human · 0 n/a · 0 failed**. Check 7 awaits
the sealed mutation runner; check 6 passes (the pre-modification tree has no agent
tests, so T2/T3/T4 fail as they must) and the canonical is accepted by the full
public gate, which is what confirms the 30% threshold end to end.

## Run it

```bash
TASK_DIR=tasks/suite/W1b-zarr-block-mask-properties bash harness/task-tools/setup.sh
TASK_DIR=tasks/suite/W1b-zarr-block-mask-properties bash harness/task-tools/validate.sh
TASK_DIR=tasks/suite/W1b-zarr-block-mask-properties bash harness/task-tools/reset.sh
```

No model spend is involved in any of the above.

## Files

| path | tracked | what |
|---|---|---|
| `task.yaml` | yes | task definition, pins, prompt, gate wiring, coverage target |
| `canonical/block-mask-property-tests.patch` | yes | reference solution: one new file inlining upstream's strategy + two tests |
| `hidden/README-FOR-HUMAN.md` | yes | sealed mutation-runner authoring instructions |
| `hidden/check.sh`, `hidden/mutants/`, `hidden/VERSION` | **no** | sealed, human-held |
| `.work/` | no | runtime clone; never committed |

`canonical/` is the reference the validator grades; it is never shown to the agent.
Its docstring records exactly what was taken from upstream and what was added: every
assertion, strategy body, filter predicate and decorator is upstream's byte for byte;
new are only the docstring, the import block, and the `_enable_rectilinear_chunks`
autouse fixture (copied verbatim from `tests/test_properties.py` at the pin, because
upstream's tests inherit it from the module they live in and this canonical must be
one self-contained new file).
