# Task harness (shared engine for pilot + suite tasks)

One parameterized engine drives the SPEC §2.8 10-point validation and the SPEC
§2.6 deterministic-first acceptance gate for **every** benchmark task. Point
`TASK_DIR` at a task directory and the same scripts run it:

```bash
TASK_DIR=tasks/pilot-realworld                       bash harness/task-tools/validate.sh
TASK_DIR=tasks/suite/W4-complex-bugfix               bash harness/task-tools/validate.sh
TASK_DIR=tasks/suite/W3-migration                    bash harness/task-tools/validate.sh
TASK_DIR=tasks/suite/W1b-zarr-block-mask-properties  bash harness/task-tools/validate.sh
```

This is the foundation for the 11-task expanded suite (SPEC §2.3): tasks add data,
not code.

## Stacks and gate types

Two axes, both declared in `task.yaml`, both resolved at run time — no branch in
the engine is per-task.

- **`stack:`** picks a toolchain driver from `stacks/` (`node` · `python` · `none`).
  The driver owns install, dependency probe, baseline, selected-test run, coverage
  and build; the task supplies the commands via `stack_cmds`. Contract:
  [`stacks/README.md`](stacks/README.md).
- **`gate_type:`** picks what "accepted" means: `solution` (P1–P6, the default),
  `test_generation` (T1 diff-scope · T2 suite-green · T3 coverage · T4 tests-pass,
  authoritative check = a sealed mutation-catch runner), or `pr_review` (a
  deterministic matcher over a sealed seeded-defect map).

Checks a stack genuinely cannot perform are reported `not_applicable` **with a
reason**, never silently skipped and never counted as passes (SPEC §2.8).

## Scripts

| Script | Role |
|---|---|
| `lib.sh` | Paths, `task.yaml` + manifest readers, stack dispatch, leak scan |
| `stacks/{node,python,none}.sh` | Per-toolchain drivers behind `task.yaml stack:` |
| `setup.sh` | Clone subject repo at the pinned commit, verify SHA, stack install |
| `reset.sh` | Deterministic reset; prints canonical working-tree hash |
| `gate/check-public.sh` | Visible deterministic-first gate (P1–P6 / T1–T4 / review) |
| `gate/check-hidden.sh` | Sealed hidden gate; records `sha256` version+hash |
| `gate/covpy_to_summary.py` | `coverage.py` JSON → the gate's coverage summary shape |
| `gate/scope_eval.py` | Diff-scope evaluation for the test-generation gate |
| `validate.sh` | 10-point validation → `validation-report.json` + summary |
| `Dockerfile` | Clean-container validation env, `stack: node` |
| `Dockerfile.python` | Clean-container validation env, `stack: python` (uv-based) |

Both images carry tooling + harness only and clone the subject repo at the pinned
commit at run time. `stack: none` tasks run under either.

## What a task directory must provide

```
tasks/<task>/
├── task.yaml            # task definition (see fields below)
├── canonical/<x>.patch  # canonical patch — PRODUCT code only (solution gate);
│                        #   NEW TEST FILES only (test_generation); absent (pr_review)
├── tests/<x>            # PUBLIC test, solution gate only (*.test.ts / *_test.py)
├── env/                 # OPTIONAL task-owned dependency lock, when upstream is unpinned
├── gate/test-compat.patch  # OPTIONAL harness-owned type-compat shim (test files only)
├── hidden/              # gitignored, human-held sealed material (+ README-FOR-HUMAN.md)
└── README.md
```

`task.yaml` fields the harness reads: `task_id`, `manifest_key` (which
`manifest/delivery-manifest.yaml` entry holds `repo`/`pinned_commit`), `stack`,
`stack_cmds`, `gate_type`, `canonical_patch` (PRODUCT code only), `public_test`,
`public_test_dest`, `public_test_support`, `public_test_desc`, `public_test_kind`
(`repro` | `feature` | `pr_own_tests`), `target_paths` (list of PRODUCT files, for
diff-scope), `protected_test_paths`, `baseline_test_pattern`, `baseline_test_scope`,
`contamination_tier`, and optional `test_compat_patch` (harness-owned type-compat
shim, test files only). Test-generation adds `agent_write_scope`, `coverage_target`
and `hidden_test_glob`.

`public_test_kind: pr_own_tests` is the commit-mining default (`tasks/
WORKLOAD-SELECTION.md` §4): the public test is the upstream PR's own test file
lifted verbatim, so the gate is sealed by construction and pre-modification
failure is free — nobody on this side chose what "correct" means.

## Test integrity — an agent cannot pass by editing tests

The gate never trusts test files left by an agent:

1. **`target_paths` lists PRODUCT files only.** `check-public.sh` P6 diff-scope
   fails on **any** change to a test file (or any other non-target path).
2. **Tests are restored to pristine before grading.** After diff-scope,
   `check-public.sh` runs `git checkout -- src/tests` + `git clean -fd -- src/tests`,
   discarding every agent edit (tracked or new) to existing/baseline tests.
3. **The public test is re-injected fresh** from the task definition each run.
4. **Hidden tests are injected only by `check-hidden.sh`**, from
   `tasks/<task>/hidden/` (outside the subject repo), and removed after — they
   never exist in the tree the agent works in.
5. **`test_compat_patch` is harness-owned.** When a schema change makes the
   immutable baseline suite fail to type-check (a new required field), the gate
   applies this shim *after* the restore. It is not part of the agent's solution,
   is not in `target_paths`, and may touch **only** `*.test.ts`
   (`tests/test_tasks.py` enforces this and that `canonical_patch` touches no
   test file). It is the single, mechanically-bounded exception.

Net effect: the agent is graded on product code plus tests it cannot influence.
The sealed hidden tests remain the authoritative acceptance signal.

## Pre-modification failure (check 6) for feature vs bugfix

Both kinds ship a PUBLIC test that must **fail on the unmodified repo**:

- **bugfix** — a repro test that fails until the defect is fixed;
- **feature** — a feature-spec test that fails because the endpoints/fields do
  not exist yet (SPEC §2.8 feature-task interpretation).

The authoritative sealed hidden tests are human-held (`tasks/<task>/hidden/`); the
generating model is never the sole verifier of its own work (SPEC §2.6).

## DB-free baseline scope

The upstream `auth` suite instantiates a real Prisma client (import-order bug) and
needs a live Postgres, so the deterministic baseline is the hermetic DB-free unit
suites (`baseline_test_scope: hermetic_db_free`). The deep Prisma mock returns
values verbatim and ignores `where`/`select`/`data`, so public tests assert on the
**arguments** the service passes to the data layer — the only faithful DB-free
signal. Declared per task, not silently dropped.
