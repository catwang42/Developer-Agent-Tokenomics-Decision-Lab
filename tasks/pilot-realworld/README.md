# Pilot Task — `pilot-realworld-missing-user-id`

Candidate pilot task (SPEC §2.8) until the 10-point validation passes and
**CP-TASK** approves the human-held hidden tests. The pilot's job is to prove the
*measurement system* works (telemetry capture, gate reproducibility, reset
determinism) — **not** to support any workload-class claim.

## What the task is (commit-mined — WORKLOAD-SELECTION.md §4)

The task is derived from a real merged upstream fix in the RealWorld / "Conduit"
reference API (`gothinkster/node-express-realworld-example-app`, MIT):

- **Canonical fix commit:** `30b68e1` — *"fix: missing user id"*.
- **Pinned commit (task start):** `88b258c` — its **parent**, where the bug is
  present. Recorded in `manifest/delivery-manifest.yaml` (`pilot_task`) and
  mirrored in `task.yaml`.

The bug: `getCurrentUser()` (`src/app/routes/auth/auth.service.ts`) selects the
user's fields from Prisma but omits `id`, so the returned profile has no `id` and
the issued JWT is signed with an undefined id. The **canonical patch**
(`canonical/fix-missing-user-id.patch`) is the authentic one-line upstream fix
(`+ id: true` in the `select`). The agent's task is to reproduce that fix from the
pinned commit.

Commit-mining gives us a pre-modification failure proof for free (the fix's own
effect is absent at the parent commit) and an authentic acceptance criterion.

## Acceptance gate (SPEC §2.6, deterministic-first)

Two scripts under `gate/`:

- **`check-public.sh`** — the visible teaching gate. Deterministic-first checks,
  in SPEC §2.6 priority order, restricted to those reproducible on this repo:
  1. `P1` public repro test — `getCurrentUser` requests `id` from the data layer
  2. `P2` regression — hermetic DB-free unit suites still pass
  3. `P3` type check — `tsc -p tsconfig.app.json --noEmit`
  4. `P4` build — `nx build` (the app compiles)
  5. `P5` no leakage — no planted solution / markers / patches in the tree
  6. `P6` diff scope — only the allowed path changed vs the pin
- **`check-hidden.sh`** — the sealed, authoritative gate. Loads human-held tests
  from `tasks/hidden/` (gitignored), records their `sha256` version+hash into the
  result, runs them, then removes them. Reports `AWAITING_HUMAN` (exit 2) until a
  human authors them (see `tasks/hidden/README-FOR-HUMAN.md`).

The generating model is never the sole verifier of its own work (SPEC §2.6): the
gate is deterministic and independent of the agent.

### Why the repro asserts on `findUnique` arguments

The suite uses a deep Prisma mock (`src/tests/prisma-mock.ts`) that returns its
mocked value verbatim, **ignoring the `select` clause**. So a return-value-only
assertion cannot distinguish the buggy code from the fix. The only faithful,
DB-free signal of the defect is *what the service asked the data layer for* — the
repro asserts `select` includes `id: true`. Fails at `88b258c`, passes on the fix.

### Excluded static checks (documented, not hidden)

`eslint` and `prettier` are **not** part of the gate: the upstream tree is not
clean under them at `88b258c`, so they would fail regardless of the agent's work
and are therefore invalid acceptance signals for this task. Only checks that pass
on the clean canonical solution are admissible.

## Baseline test scope — hermetic, DB-free (`baseline_test_scope: hermetic_db_free`)

The upstream `auth.service.test.ts` imports the service **before** the Prisma mock
registers, so it instantiates a real Prisma client and fails without a live
Postgres (a pre-existing upstream bug, present at `88b258c` and at HEAD). The
pilot's deterministic-first baseline is therefore the **hermetic DB-free unit
suites** (`article|profile|utils`); the DB-dependent auth integration suite is out
of the pilot's hermetic scope. This is a declared scoping decision, recorded in
`task.yaml` and the validation report — not a silent exclusion.

## The 10-point validation (`validate.sh`, SPEC §2.8)

Runs all ten checks from a clean clone and emits `validation-report.json` plus a
human summary. In the shipped state (no human-held hidden tests) it reports
**9 passed, 1 awaiting-human (check 7), 0 failed** and exits 0. With sealed tests
present it reports **10/10**. To demonstrate the full machinery, a labeled
`tests/fixtures/pilot-hidden-SYNTHETIC/` fixture stands in for the sealed tests:

```bash
# Shipped state (hidden tests human-held): 9 pass + 1 awaiting-human
bash tasks/pilot-realworld/validate.sh

# Prove the whole pipeline reaches 10/10 using the SYNTHETIC fixture:
HIDDEN_TESTS_DIR="$PWD/tests/fixtures/pilot-hidden-SYNTHETIC" \
  bash tasks/pilot-realworld/validate.sh

# Clean-container run (needs network to clone the subject repo):
docker build -f tasks/pilot-realworld/Dockerfile -t pilot-validate .
docker run --rm --network=host pilot-validate
```

## Files

| Path | Role |
|---|---|
| `task.yaml` | Task definition (mirrors manifest pins; adds gate wiring) |
| `lib.sh` | Shared paths / manifest+task readers / hermetic jest |
| `setup.sh` | Clone at pin, verify SHA, `npm ci`, `prisma generate` |
| `reset.sh` | Deterministic reset; prints canonical tree hash |
| `validate.sh` | 10-point validation → `validation-report.json` |
| `Dockerfile` | Clean-container validation environment |
| `gate/check-public.sh` | Visible deterministic-first gate |
| `gate/check-hidden.sh` | Sealed hidden gate (hash recorded per run) |
| `gate/repro/…repro.test.ts` | Public repro test |
| `canonical/fix-missing-user-id.patch` | Authentic upstream one-line fix |

The subject repo clones into `tasks/pilot-realworld/.work/` (gitignored); nothing
from it is committed here.

## Contamination tier: `famous`

The RealWorld / "Conduit" app is a canonical, widely-forked teaching
implementation, heavily represented in training data. Recorded per run as
`identity.contamination_tier: famous` (schema-v2).

**Why `famous` (not lower):** memorization is a live confound here, and we accept
that on purpose — the pilot proves the measurement system, not a workload claim.

**What it does NOT license:** a `famous` task cannot on its own substantiate a
class-level economic claim. Any such claim needs a second, materially different
task at tier `obscure` or `post_cutoff` (`tasks/WORKLOAD-SELECTION.md` §3,
extending SPEC §5.2), preferably sourced by commit mining (§4).
