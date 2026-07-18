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
├── task.yaml          # task definition (see fields below)
├── canonical/<x>.patch  # authentic/canonical solution patch
├── tests/<x>.test.ts    # PUBLIC test (repro for bugfix; feature-spec for feature)
├── hidden/              # gitignored, human-held sealed tests (+ README-FOR-HUMAN.md)
└── README.md
```

`task.yaml` fields the harness reads: `task_id`, `manifest_key` (which
`manifest/delivery-manifest.yaml` entry holds `repo`/`pinned_commit`),
`canonical_patch`, `public_test`, `public_test_desc`, `public_test_kind`
(`repro`|`feature`), `target_paths` (list, for diff-scope),
`baseline_test_pattern`, `baseline_test_scope`, `contamination_tier`.

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
