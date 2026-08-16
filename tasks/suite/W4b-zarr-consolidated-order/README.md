# W4b — complex bugfix (`w4b-zarr-consolidated-order`)

W4's **second** complex-bugfix task: the one that can carry a workload-**class**
claim. W4's first task is `famous` (RealWorld/Conduit), and
`tasks/WORKLOAD-SELECTION.md` §3 — extending SPEC §5.2 — allows a class claim only
with a second, materially different task at tier `obscure` or `post_cutoff`. This
one is `post_cutoff`, Python, and in a real scientific-data library rather than a
teaching app.

Added to the roster because batch 3 showed a **ceiling effect**: 27/27 controlled
runs accepted, zero escalations, so cost-per-accepted-outcome could not separate
configurations. This task is harder than W4 on the axis that matters — the fix is
one hunk, but *finding* it requires reasoning about an ordering invariant.

## Task (commit-mined)

Sourced per WORKLOAD-SELECTION.md §4 from a real merged PR:
[zarr-developers/zarr-python#4227](https://github.com/zarr-developers/zarr-python/pull/4227),
merged 2026-08-02, MIT, ~2.0k stars.

| | |
|---|---|
| **Pinned commit (agent start, N−1)** | `a994a4fc972fed428eab6a26d4f14bb95d22c144` |
| **Canonical fix commit (N)** | `24f9ad19430dc88bc1d92b5e1936ac6b3e20f4fe` |

Both SHAs were resolved against the GitHub API and re-verified in a local clone;
the merge commit's `parents[0]` is exactly the pinned commit (squash merge, single
parent).

`ConsolidatedMetadata._flat_to_nested` (`src/zarr/core/group.py`) rebuilds a nested
node tree from a flat mapping of slash-separated keys. It groups keys by parent with
`itertools.groupby` over a list sorted **by depth only** — but `groupby` groups
*consecutive runs*, so same-parent keys that are not adjacent land in separate runs
and the surrounding dict comprehension keeps only the last one. Children are
silently dropped from their parent and linger as bogus slash-containing top-level
keys. The upstream fix replaces the comprehension with a `defaultdict(list)`
accumulator.

## Why it is a discriminator

- **Non-local reasoning.** The failing behaviour is order-dependence, and the
  triggering orders are exactly the ones the pinned code's own sort produces for
  case-differing siblings. Nothing crashes; nothing is obviously wrong on a read.
- **Localisation in a large tree.** `src/zarr/` is ~30k lines; the symptom
  ("children missing from consolidated metadata") does not name the function.
- **A plausible wrong fix exists.** Sorting the keys differently makes the public
  test's three orders pass while leaving the `groupby` run-adjacency bug intact —
  which is why the sealed test asserts order-independence as a *property* over
  permutations, at depth ≥ 3 (see `hidden/README-FOR-HUMAN.md`).

## Gate

Solution gate (P1–P6). Public test = the upstream PR's **own** new test,
`tests/test_consolidated_order_public.py`, copied verbatim with its three
parametrised orders; the file header records the exact derivation delta.

Empirically verified this session on the pinned tree:

```
pre-modification   1 failed, 2 passed in 0.50s   (order1, the interleaved-siblings case)
canonical patch    3 passed in 0.21s
```

That is SPEC §2.8 check 6 and the canonical half of check 7.

Baseline scope is `tests/test_metadata` — hermetic and in-process. The remote-store
suites live behind zarr's `remote-tests` dependency group, which this task
deliberately does not install, so the gate has no network dependency.

## Contamination tier: `post_cutoff` (merged 2026-08-02)

Tier is **model-relative** (WORKLOAD-SELECTION §2): what is recorded here is the
merge date; the cutoff basis for each subject product is recorded per run. Declared
before running and never revised on results.

## Run

```bash
TASK_DIR=tasks/suite/W4b-zarr-consolidated-order bash harness/task-tools/validate.sh
# shipped: 9 pass + 1 awaiting-human (check 7, sealed test not yet authored)
```

## Files

`task.yaml` (pins, `stack: python`, `stack_cmds`) ·
`canonical/fix-flat-to-nested-order.patch` (the upstream fix, product code only) ·
`tests/test_consolidated_order_public.py` (public repro) ·
`hidden/README-FOR-HUMAN.md` (sealed-test authoring plan). Screening metadata lives
in `../W4-complex-bugfix/workload.yaml`, which names this task as W4's second task.
The subject repo clones into `.work/` (gitignored).
