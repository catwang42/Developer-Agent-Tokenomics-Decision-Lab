# Gate-fairness audit — F1 WRONG_SOLUTION runs (revalidation)

Per the CP-DATA condition (2026-07-19): inspect the revalidation F1 rejections and
classify each as **(i)** feature genuinely absent/broken, or **(ii)** functionally
plausible but failing the sealed tests on implementation *shape*. This is a
gate/task-fairness analysis — **not** a model comparison (the accepted/rejected
pattern is n=1 instrument data and lives only in the completeness report).

## Runs audited

| Run | Gate signature | Diff available? | Class |
|---|---|---|---|
| F1·P1·rep1 (strong leg) | P6-diff-scope fail (test-file edit) + P1 fail | **yes** (survived on disk) | **(ii) shape mismatch** |
| F1·P0·rep1 | P6-diff-scope fail (`src/app/…`) + P1 fail | no (reset-overwritten) | undetermined* |
| F1·P0·rep2 | P6-diff-scope fail (`src/app/…`) + P1 fail | no (reset-overwritten) | undetermined* |

`*` Diffs were not archived pre-fix (the provenance gap). Now fixed
(`_archive_agent_diff` writes `agent-solution.diff` per run); these two are
re-classified in the batch-2 re-collection. **Not fabricated here.**

## F1·P1·rep1 — classification (ii), with evidence

The agent (strong leg) produced a genuine, near-canonical implementation:

**`schema.prisma` — identical to canonical:**
```
+  draft       Boolean   @default(false)
```

**`article.service.ts` — persists draft on create; excludes drafts from the list:**
```js
// createArticle
-  const { title, description, body, tagList } = article;
+  const { title, description, body, tagList, draft = false } = article;
   ...
   data: { title, description, body, draft, slug, ... }

// buildFindAllQuery (feeds getArticles' count + findMany)
+  queries.push({ draft: { equals: false } });
```
It also added the same exclusion to `getFeed` (beyond canonical).

**Why it failed — pure shape mismatch.** The public *and* sealed hidden tests use a
DB-free Prisma mock and assert the *shape* of the `where` the service builds:
```js
expect(call.where?.AND ?? []).toEqual(
  expect.arrayContaining([expect.objectContaining({ draft: false })]));
```
`expect.objectContaining({ draft: false })` requires an AND element whose `draft`
property **equals `false`**. The agent emitted `{ draft: { equals: false } }` —
**functionally identical in Prisma** (both exclude drafts) but its `draft` is an
object, so the matcher fails. The rejection is on implementation shape, not on the
feature being absent or broken → **case (ii).** (The separate P6-diff-scope failure
— an out-of-scope test-file edit — is a real behavioral issue but not why the
feature test failed; the gate restores tests before grading P1.)

## Remedy applied (task, not gate — per the directive)

The gate was **NOT** loosened to admit shape variants. Instead the pilot task prompt
was tightened to pin the contract shape (matching the canonical patch and the test):
- `tasks/pilot-realworld/task.yaml` prompt now specifies the `draft Boolean
  @default(false)` field, persisting `draft` in the create `data`, and excluding
  drafts via a plain `{ draft: false }` entry in the query's top-level `AND` array;
  and constrains edits to the two target files (addressing the P6 out-of-scope
  failures).
- `task_suite_version` bumped **pilot-v1 → pilot-v2**.
- **Sealed hidden-test hash UNCHANGED** (`sha256:105c2418…`) — tests/gate untouched.
- 10-point validation re-run: **10/10 pass** (canonical still accepted, sealed
  hidden passes, premod still fails, reset deterministic).

## Provenance fix

`harness/runner/run.py::_archive_agent_diff` now writes `agent-solution.diff`
(tracked product diff + untracked-file list) for every live run before any reset, so
future WRONG_SOLUTION rejections are inspectable and this audit is repeatable on the
batch-2 re-collection.
