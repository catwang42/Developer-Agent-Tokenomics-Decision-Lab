# Hidden tests — for the human to author (W4; SPEC §2.6 sealed policy)

This directory's contents are **gitignored** (only this README is tracked). The
sealed hidden tests are **human-held**: never commit them, paste them into a model
prompt, or place them under `results/`.

The shared hidden gate (`harness/task-tools/gate/check-hidden.sh`) finds every
`*.test.ts` / `*.spec.ts` here, records a `sha256` version+hash, copies them into
the subject repo's `src/tests/services/`, runs them, then removes them. Until you
author tests here, the 10-point validator reports check 7 as `awaiting_human`
(not failed) and still exits 0.

## What to author for W4 (`w4-realworld-missing-user-id`)

At least one sealed test proving `getCurrentUser` retrieves the user's `id` so the
returned profile and JWT carry it.

- **File name:** `getCurrentUser.hidden.test.ts` (add a `VERSION` file for a
  human-readable label).
- **Import order:** `../prisma-mock` **before** `../../app/routes/auth/auth.service`.
- **Make it discriminating.** The deep Prisma mock ignores `select` and returns
  its value verbatim, so assert on the arguments passed to `prisma.user.findUnique`
  (e.g. `select` includes `id: true`). Must fail at the pinned commit and pass on
  the canonical fix.
- Keep it DB-free and deterministic.

A non-sealed reference of the right shape:
`tests/fixtures/w4-bugfix-hidden-SYNTHETIC/`. Do not ship it as the real test.

## Verify

```bash
TASK_DIR=tasks/suite/W4-complex-bugfix bash harness/task-tools/validate.sh
# expect: 10 passed, 0 awaiting-human, 0 failed
```

Record the printed `hidden_test_hash` in `manifest/RUN_TEMPLATE.md`; rotate/reseal
per evaluation cycle (SPEC §2.6).
