# Stack drivers

The task harness (`setup.sh`, `reset.sh`, `validate.sh`, `gate/check-*.sh`) is one
engine for many tasks: everything task-specific is read from `$TASK_DIR/task.yaml`
and the delivery manifest. Until the screening roster it was also one engine for
one *toolchain* — npm + Prisma + jest + nx, the RealWorld/Conduit subject repo.

The screening roster (SPEC §5.1) adds Python subject repos and a review-class
workload with no executable subject at all, so the toolchain-dependent primitives
moved behind a **stack driver**: a sourced shell file named by `task.yaml`'s
`stack:` field.

| `stack:` | driver | used by |
|---|---|---|
| `node` (default) | `node.sh` | the RealWorld tasks (pilot, W1, W4) — behaviour unchanged |
| `python` | `python.sh` | uv-managed venv + pytest, fully command-driven from `stack_cmds:` |
| `none` | `none.sh` | review-class tasks: the subject is READ, never executed |

`lib.sh` sources `stacks/$stack.sh` after defining its own helpers, so a driver may
use `task_field`, `task_list`, `task_map`, `stack_cmd`, `subject_run`,
`pilot_python`, `coverage_files`, `$SUBJECT_DIR` and `$WORKDIR`.

## Driver contract

Each driver defines these functions. Return code 0 = success unless stated.

| function | used by | meaning |
|---|---|---|
| `stack_install` | setup.sh | install dependencies in `$SUBJECT_DIR` (network allowed; runs at image build) |
| `stack_post_patch` | validate.sh, gates | regenerate anything derived from source after the tree changes |
| `stack_clean_keep` | setup/reset, `leak_found` | one gitignored install dir per line, preserved across resets |
| `stack_deps_ok` / `stack_deps_detail` | check 2 | dependency manifest present at the pin **and** installed |
| `stack_installed_ok` / `stack_install_detail` | check 4, setup.sh | a clean install materialised |
| `stack_config_paths` | check 3 | build/config files that must exist at the pin, one per line |
| `stack_baseline_tests` / `stack_baseline_detail` | check 5, P2 | run the hermetic baseline suite |
| `stack_selector` | gates | join repo-relative test paths into one runner selector |
| `stack_run_selected` | P1, T4, hidden gate | run the tests named by a selector |
| `stack_run_selected_graded` | hidden gate (`solution`) | as above, and write `<STATUS>\t<test id>` lines to `$2` — **ids and statuses only, never assertion text** |
| `stack_typecheck` / `stack_typecheck_detail` | P3 | static type check (may be a declared no-op) |
| `stack_build` / `stack_build_detail` | check 9, P4 | build (may be a declared no-op) |
| `stack_coverage_summary` | T3 | write an istanbul `coverage-summary.json` for a selector; print its path |
| `stack_na_checks` | validate.sh | optional: `<check-id>\t<reason>` lines for checks with no referent |

`stack_na_checks` is how a driver says *this SPEC §2.8 check cannot apply here*.
Those checks are recorded `not_applicable` **with the reason** in
`validation-report.json` — never passed vacuously, never failed spuriously
(CLAUDE.md rule 3 in spirit: unavailable is recorded, not zero-filled). Only
`none.sh` uses it today, for checks 2/4/5/9.

## The `python` driver's `stack_cmds:`

`python.sh` holds no repo knowledge: every primitive is a command string from
task.yaml, run with the subject repo as cwd.

```yaml
stack: python
dependency_manifests: [pyproject.toml, uv.lock]   # must exist at the pin (check 2)
stack_cmds:
  install:    uv sync --frozen --no-default-groups --group test
  deps_probe: .venv/bin/python -c "import zarr, pytest"
  baseline:   .venv/bin/python -m pytest tests/test_metadata -q -p no:cacheprovider
  select:     .venv/bin/python -m pytest {SEL} -q -p no:cacheprovider
  coverage:   .venv/bin/python -m pytest {SEL} -q --cov=... --cov-report=json:{COV_OUT}
  build:      .venv/bin/python -c "import zarr"
  typecheck:  ""      # optional; empty/absent = declared no-op
```

Placeholders: `{SEL}` = the selector from `stack_selector` (a space-separated list
of pytest paths); `{COV_OUT}` = where the coverage.py JSON must be written.
`covpy_to_summary.py` then re-shapes it into the istanbul summary that
`coverage_eval.py` evaluates, so both stacks share one threshold decision.

These command strings are task definitions — repo artifacts reviewed at
CP-SCREEN-PREREG. They are never taken from a model or from run-time input.
