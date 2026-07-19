# Hidden tests — for the human to author (pilot; SPEC §2.6 sealed policy)

This directory's contents are **gitignored** (only this README is tracked). The
sealed hidden tests are **human-held**: never commit them, paste them into a model
prompt, or place them under `results/`.

The shared hidden gate (`harness/task-tools/gate/check-hidden.sh`) finds every
`*.test.ts` / `*.spec.ts` here, records a `sha256` version+hash, copies them into
the subject repo's `src/tests/services/`, runs them, then removes them. Until you
author tests here, the 10-point validator reports check 7 as `awaiting_human`
(not failed) and still exits 0.

## What to author for the pilot (`pilot-realworld-draft-articles`)

Sealed acceptance tests for the Draft-articles feature. At minimum:

1. **Create persists draft.** `createArticle` passes `draft` through to the data
   layer (assert on the `data` arg to `prisma.article.create`).
2. **Public list excludes drafts.** `getArticles` filters drafts out (assert the
   `where` passed to `prisma.article.findMany`/`count` excludes `draft: true`,
   e.g. contains `{ draft: false }`).

Consider adding stronger sealed variants than the public test (e.g. that a
non-draft create defaults `draft` to false, or an author-facing drafts listing if
the task spec is extended).

Requirements:

- **File name:** `draft-articles.hidden.test.ts` (add a `VERSION` file for a label).
- **Import order:** `../prisma-mock` **before** `../../app/routes/article/article.service`.
- **Make it discriminating.** The deep Prisma mock ignores `data`/`where` and
  returns values verbatim, so assert on the **arguments** the service passes to the
  data layer. Read args untyped so the test compiles on the unmodified repo and
  fails at runtime. Must fail at the pinned commit and pass on the canonical fix.
- Keep it DB-free and deterministic.

A non-sealed reference of the right shape:
`tests/fixtures/pilot-draft-hidden-SYNTHETIC/`. Do not ship it as the real test.

## Verify

```bash
TASK_DIR=tasks/pilot-realworld bash harness/task-tools/validate.sh
# expect: 10 passed, 0 awaiting-human, 0 failed
```

Record the printed `hidden_test_hash` in `manifest/RUN_TEMPLATE.md`; rotate/reseal
per evaluation cycle (SPEC §2.6).
