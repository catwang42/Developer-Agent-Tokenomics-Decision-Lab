# Pilot Task — `pilot-realworld-draft-articles` (feature)

The SPEC §2.8 RealWorld **feature task**: add a *Draft articles* feature to the
RealWorld/Conduit API. Candidate pilot until the 10-point validation passes and
**CP-TASK** approves the human-held hidden tests. The pilot's job is to prove the
*measurement system* works (telemetry capture, gate reproducibility, reset
determinism) — **not** to support any workload-class claim.

> The commit-mined `missing-user-id` **bugfix** now lives at
> `tasks/suite/W4-complex-bugfix/` as the suite's first commit-mining exemplar
> (F2 feasibility bugfix). This directory is the feature pilot per frozen SPEC §2.8.

## The feature

Articles gain a boolean `draft` field (default false, persisted on the `Article`
model). Draft articles are **excluded from the public article list** (`GET
/articles`). The canonical solution (`canonical/draft-articles.patch`) persists
`draft` on create and pushes a `{ draft: false }` filter into the public list
query. Files touched: `src/prisma/schema.prisma`, `src/app/routes/article/article.service.ts`.

**Pinned commit:** `30b68e1` (RealWorld HEAD; the Draft feature does not exist
there). Recorded in `manifest/delivery-manifest.yaml` (`pilot_task`).

## Acceptance gate (SPEC §2.6, deterministic-first)

Driven by the shared harness (`harness/task-tools/`):

- **`gate/check-public.sh`** — visible checks: `P1` public feature test · `P2`
  DB-free regression suites · `P3` typecheck · `P4` build · `P5` no-leakage ·
  `P6` diff-scope (only the two allowed paths).
- **`gate/check-hidden.sh`** — sealed, authoritative. Loads human-held tests from
  `tasks/pilot-realworld/hidden/` (gitignored), records their `sha256`
  version+hash, runs them, removes them. `AWAITING_HUMAN` until authored
  (`hidden/README-FOR-HUMAN.md`).

### Pre-modification failure for a feature (SPEC §2.8)

The public feature test fails on the unmodified repo because the `draft`
field/behaviour does not exist yet — the standard feature-task pre-mod failure.
The deep Prisma mock ignores `data`/`where` and returns values verbatim, so the
test asserts on the **arguments** the service passes to the data layer (create
`data.draft`; list `where.AND` contains `{ draft: false }`), read untyped so it
compiles pre-mod and fails at runtime. Passes on the canonical solution.

### Excluded static checks & DB-free baseline

`eslint`/`prettier` are excluded (the upstream tree is not clean under them, so
they would fail regardless of the agent's work). Baseline is scoped to the
hermetic DB-free unit suites (`article|profile|utils`); the upstream `auth`
integration suite needs a live Postgres (import-order bug). Both are declared, not
silently dropped — see `harness/task-tools/README.md`.

## Run the 10-point validation

```bash
# Shipped state (hidden tests human-held): 9 pass + 1 awaiting-human (check 7)
TASK_DIR=tasks/pilot-realworld bash harness/task-tools/validate.sh

# Prove the whole pipeline reaches 10/10 with the SYNTHETIC hidden fixture:
HIDDEN_TESTS_DIR="$PWD/tests/fixtures/pilot-draft-hidden-SYNTHETIC" \
  TASK_DIR=tasks/pilot-realworld bash harness/task-tools/validate.sh

# Clean-container run (needs network to clone the subject repo):
docker build -f harness/task-tools/Dockerfile -t task-validate .
docker run --rm --network=host -e TASK_DIR=/lab/tasks/pilot-realworld task-validate
```

## Contamination tier: `famous`

RealWorld/Conduit is a canonical, widely-forked teaching app — strongly present in
training data. Recorded per run as `identity.contamination_tier: famous`.

**Why `famous` (not lower):** memorization is a live confound, accepted on purpose
— the pilot proves the measurement system, not a workload claim.

**What it does NOT license:** a `famous` task cannot substantiate a class-level
economic claim. Any such claim needs a second, materially different task at tier
`obscure` or `post_cutoff` (`tasks/WORKLOAD-SELECTION.md` §3, extending SPEC §5.2),
preferably sourced by commit mining (§4).

## Files

`task.yaml` · `canonical/draft-articles.patch` · `tests/draft-articles.public.test.ts`
· `hidden/README-FOR-HUMAN.md` · `README.md`. Engine: `harness/task-tools/`. The
subject repo clones into `.work/` (gitignored).
