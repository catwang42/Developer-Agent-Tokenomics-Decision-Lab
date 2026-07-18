# Task harness (shared engine for pilot + suite tasks)

One parameterized engine drives the SPEC §2.8 10-point validation and the SPEC
§2.6 deterministic-first acceptance gate for **every** benchmark task. Point
`TASK_DIR` at a task directory and the same scripts run it:

```bash
TASK_DIR=tasks/pilot-realworld            bash harness/task-tools/validate.sh
TASK_DIR=tasks/suite/W4-complex-bugfix    bash harness/task-tools/validate.sh
```

This is the foundation for the 11-task expanded suite (SPEC §2.3): tasks add data,
not code.

## Scripts

| Script | Role |
|---|---|
| `lib.sh` | Paths, `task.yaml` + manifest readers, hermetic jest, prisma generate |
| `setup.sh` | Clone subject repo at the pinned commit, verify SHA, `npm ci`, generate |
| `reset.sh` | Deterministic reset; prints canonical working-tree hash |
| `gate/check-public.sh` | Visible deterministic-first gate (P1–P6) |
| `gate/check-hidden.sh` | Sealed hidden gate; records `sha256` version+hash |
| `validate.sh` | 10-point validation → `validation-report.json` + summary |
| `Dockerfile` | Clean-container validation env (subject repo cloned at runtime) |

## What a task directory must provide

```
tasks/<task>/
├── task.yaml            # task definition (see fields below)
├── canonical/<x>.patch  # canonical solution patch — PRODUCT code only
├── tests/<x>.test.ts    # PUBLIC test (repro for bugfix; feature-spec for feature)
├── gate/test-compat.patch  # OPTIONAL harness-owned type-compat shim (*.test.ts only)
├── hidden/              # gitignored, human-held sealed tests (+ README-FOR-HUMAN.md)
└── README.md
```

`task.yaml` fields the harness reads: `task_id`, `manifest_key` (which
`manifest/delivery-manifest.yaml` entry holds `repo`/`pinned_commit`),
`canonical_patch` (PRODUCT code only), `public_test`, `public_test_desc`,
`public_test_kind` (`repro`|`feature`), `target_paths` (list of PRODUCT files, for
diff-scope), `baseline_test_pattern`, `baseline_test_scope`, `contamination_tier`,
and optional `test_compat_patch` (harness-owned type-compat shim, `*.test.ts` only).

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
