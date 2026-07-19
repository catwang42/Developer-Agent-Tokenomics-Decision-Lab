# W1 / F3 coverage analysis — why the branch target is an honest ceiling, not 100%

Instrument note for the test-generation gate (SPEC 2.6). Records the measured branch
structure of the two target mappers and the reachability finding that sets the T3
coverage thresholds. Not a model comparison; no run results. Decided with the human
2026-07-19 ("keep branches, honest ceiling").

## Target files (pinned commit `30b68e1e…`)

- `src/app/routes/article/article.mapper.ts`
- `src/app/routes/article/author.mapper.ts`

Measured with the subject repo's own toolchain (ts-jest + istanbul), coverage
collected only from the two files, exercised by the canonical reference tests
(`canonical/mapper-tests.patch`):

| File | Statements | Functions | Branches | Uncovered |
|---|---|---|---|---|
| article.mapper.ts | 100% | 100% | **100%** (0/0 — no branches) | — |
| author.mapper.ts | 100% | 100% | **83.33%** (5/6 legs) | line 8 |

## Why author.mapper.ts caps at 5/6 branch legs

`author.mapper.ts` (verbatim at the pin):

```ts
const authorMapper = (author: any, id?: number) => ({
  username: author.username,          // line 4 — dereferences `author` with NO ?.
  bio: author.bio,
  image: author.image,
  following: id
    ? author?.followedBy.some((followingUser: Partial<User>) => followingUser.id === id)
    : false,                          // line 8 — `author?.followedBy` optional chain
});
```

istanbul instruments three branch points (6 legs):

1. `cond-expr` (ternary `id ? … : false`) — both legs reachable ✓
2. `cond-expr` (optional chain `author?.followedBy`) — the **nullish-`author` leg is
   never taken**
3. `binary-expr` on line 8 — both legs reachable ✓

The nullish leg of `author?.` is **unreachable by construction**: line 4 reads
`author.username` with no optional chaining, so a nullish `author` throws a
`TypeError` *before* line 8 runs. Verified directly:

```
authorMapper(undefined, 42)  ->  TypeError: Cannot read properties of undefined (reading 'username')
```

The only ways to make that leg reachable are to edit the mapper source (add
`/* istanbul ignore next */`, or make line 4 defensive). The task forbids that: the
mappers are `target_paths` (immutable), the agent may not touch them, and neither may
the canonical patch. So 100% branch coverage of `author.mapper.ts` is impossible for
any valid solution, and requiring it would be an unfair gate that rejects even the
canonical.

## Decision: gate on the reachable ceiling (task fix, not gate loosening)

Following the gate-fairness precedent (`report/gate-fairness-audit.md` — fix the task,
never loosen the gate to admit vacuous work), `task.yaml`'s `coverage_target` gates
per file on the reachable branch ceiling:

```yaml
coverage_target:
  metric: branches
  files:
    - {path: src/app/routes/article/article.mapper.ts, min_pct: 100}
    - {path: src/app/routes/article/author.mapper.ts,  min_pct: 83.33}   # 5/6 legs
```

This is **not** a weakening of meaningfulness. 83.33% here means *every reachable
branch is covered* — an agent hitting it must exercise both ternary legs and the
`.some` predicate both ways. Vacuous coverage still fails T3 (pct drops below the
minimum), and the AUTHORITATIVE meaningfulness check is the sealed, human-authored
**mutation-catch** hidden test (`hidden/README-FOR-HUMAN.md`), which T1–T4 cannot
substitute for.

## Canonical evidence (no model spend; reused pinned checkout)

The canonical tests (`canonical/mapper-tests.patch`, 8 tests) were verified on a
checkout at the same pin:

- **Coverage:** article 100% branch, author 83.33% branch (both meet the gate).
- **Suite-green:** the hermetic DB-free baseline (`article|profile|utils|tag|mapper`,
  `auth` excluded — needs `DATABASE_URL`) stays green with the new tests: 5 suites,
  22 passed + 1 todo.
- **Mutation-catch (the six planned mutants):** all caught (≥1 canonical test fails
  each):

  | Mutant | Caught |
  |---|---|
  | authorMapper `following` → always `false` | ✓ |
  | authorMapper `following` → always `true` | ✓ |
  | authorMapper `.some` predicate `=== id` → `!== id` | ✓ |
  | articleMapper `favorited` → always `false` | ✓ |
  | articleMapper `favoritesCount` → `length + 1` | ✓ |
  | articleMapper `tagList.map(tag => tag.name)` → `tag => tag` | ✓ |

  (These are the *suggested* mutants in the human-authoring spec; the sealed set is
  human-authored and human-held. This table is instrument evidence that the canonical
  is non-vacuous, not the sealed test.)
