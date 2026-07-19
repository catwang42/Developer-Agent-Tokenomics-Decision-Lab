# Hidden tests — for the human to author (SPEC §2.6 sealed-hidden-test policy)

This directory is **gitignored** (only this README is tracked). The sealed hidden
tests are **human-held** and must never be committed to this repository, pasted
into a model prompt, or placed under `results/`. This file explains exactly what
to author, where, and how the harness consumes it.

## What the hidden gate does

`tasks/pilot-realworld/gate/check-hidden.sh`:

1. Finds every `*.test.ts` / `*.spec.ts` file in this directory (or in the
   directory named by `HIDDEN_TESTS_DIR`).
2. Computes a **version + content hash** (`sha256:…`) over the sealed files, so
   every result can cite exactly which sealed tests judged it (SPEC §2.6).
3. Copies them into the subject repo's `src/tests/services/`, runs them with the
   project's own jest config, then **removes them** so they never persist.
4. Exit code: `0` pass · `1` fail · `2` no hidden tests found (`AWAITING_HUMAN`).

Until you author tests here, the 10-point validator reports check 7 as
`awaiting_human` (not failed) and still exits 0.

## What to author

Author at least one sealed acceptance test for the pilot task
(`pilot-realworld-missing-user-id`: `getCurrentUser` must retrieve the user's
`id` from the data layer so the returned profile and JWT carry it).

Requirements:

- **File name:** `getCurrentUser.hidden.test.ts` (any `*.test.ts` here is picked
  up). Put a `VERSION` file here too if you want a human-readable version label
  recorded alongside the hash.
- **Import order:** import `../prisma-mock` **before** `../../app/routes/auth/auth.service`,
  or the deep Prisma mock will not be registered before the service loads its
  Prisma client (this is the upstream import-order footgun; see the pilot README).
- **Make it discriminating.** The deep Prisma mock returns its mocked value
  verbatim and ignores the `select` clause, so a return-value-only assertion
  cannot tell the buggy code from the fix. Assert on the arguments the service
  passes to `prisma.user.findUnique` (e.g. `select` includes `id: true`), or
  drive the real behaviour a different way. It must **fail** at the pinned commit
  and **pass** on the canonical solution.
- Keep it **DB-free and deterministic** (no live Postgres, no network, no clock).

A ready-made, non-sealed reference of the right shape lives at
`tests/fixtures/pilot-hidden-SYNTHETIC/` — copy its structure, then write your own
sealed assertion. Do **not** ship the synthetic fixture as the real hidden test.

## Verifying your hidden test

From the repo root, run the validator pointed at this directory (default already
points here):

```bash
bash tasks/pilot-realworld/validate.sh
# expect: 10 passed, 0 awaiting-human, 0 failed
```

Record the printed `hidden_test_hash` in the run pre-registration
(`manifest/RUN_TEMPLATE.md`) and rotate/reseal per evaluation cycle (SPEC §2.6).
