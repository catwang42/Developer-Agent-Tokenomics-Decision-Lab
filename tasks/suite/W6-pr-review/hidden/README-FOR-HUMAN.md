# Seeded-defect map — for the human to author (W6; SPEC §2.6 sealed policy)

This directory's contents are **gitignored** (only this README is tracked).
Everything you author here is **human-held**: never commit it, never paste it into
a model prompt, never place it under `results/`.

Unlike the other tasks, W6's sealed material is not a test — it is the **review
artifact plus its ground truth**. You author three files, and the design is meant
to be finishable in one sitting:

| file | what it is |
|---|---|
| `review-diff.patch` | `../review/base-diff.patch` **with your k defects seeded into it**. This is what the agent sees. |
| `defect-map.json` | the ground truth: one record per seeded defect (`id`, `file`, `line`, `class`, `note`). |
| `check.sh` | executable matcher: scores an agent's review report against the map, exit 0 accept / 1 reject / 2 unavailable. |
| `VERSION` | a human-readable label, e.g. `sealed-w6-v1 2026-08-16 k=6`. |

Until `check.sh` exists and is executable, the 10-point validator reports checks 6
and 7 as `awaiting_human` (not failed) and still exits 0.

## The base material

`../review/base-diff.patch` (526 lines) is the **real** upstream diff of
[honojs/hono#5171](https://github.com/honojs/hono/pull/5171) — *"feat(reg-exp-router):
throw UnsupportedPathError during route registration"* — restricted to the three
source files:

```
src/router/reg-exp-router/node.ts     170 changed
src/router/reg-exp-router/router.ts   187 changed
src/router/reg-exp-router/trie.ts      21 changed
```

`src/router/reg-exp-router/router.test.ts` (+194 upstream) is **withheld on
purpose**. A reviewer who can read the PR's own tests has an oracle for your seeded
defects, and the gate would then measure test-reading, not review skill. Do not add
it back.

The PR is a good review target because it is three logically distinct changes in
one diff — a `compareKey` ordering fix, a param-capture fix on wildcard-created
label nodes, and the registration-time `UnsupportedPathError` rework that converts
`Node#insert` from recursion to a loop and moves matcher construction into
`Trie.paths`. There is genuine reasoning to do, and plenty of correct code to
falsely accuse.

## Seeding rules

**Seed k = 6 defects, one per class below.** Each class is anchored to a real
region of the diff so you are modifying code that is genuinely there, not inventing
a hunk. Keep each seeded change **small** (one to three lines) and **plausible** —
it must read like something a tired author would write, not like sabotage.

1. **Off-by-one in slash/segment counting arithmetic** — `trie.ts`. Natural sites:
   the `this.paths[path] = [this.#index++, paramAssoc]` handler-index bookkeeping,
   or the `for (let i = groups.length - 1; i >= 0; i--)` / inner
   `for (let j = tokens.length - 1; j >= 0; j--)` group-restoration loops. A
   `>= 0` → `> 0`, or `#index++` → `++#index`, is exactly the shape.

2. **Inverted guard on the new `UnsupportedPathError` throw** — `node.ts`, the
   conflict check inside `if (!nextNode)`. Flip one condition so a *legal* path is
   rejected at registration: e.g. `regexpStr !== ONLY_WILDCARD_REG_EXP_STR` →
   `regexpStr === ONLY_WILDCARD_REG_EXP_STR`, or drop the
   `(regexpStr.length > 1 || k.length > 1)` clause that lets a single-char pattern
   coexist with single-char literals. This is the highest-value class: the whole
   point of the PR is *when* it throws.

3. **Reordered route-registration precedence** — `node.ts` `compareKey`, or
   `router.ts` `add()`. The PR's own first commit makes wildcard sibling order
   deterministic (`return b === TAIL_WILDCARD_REG_EXP_STR ? -1 : 1`); inverting that
   ternary, or swapping the `[middleware, routes]` iteration order in
   `#buildMatcher`, changes which handler wins without changing any type.

4. **A dropped `else` branch that silently falls through to the wildcard** —
   `node.ts`, the `if (pattern) { … } else { … }` inside the new insert loop, or the
   `token === '*' ? (i === len - 1 ? ONLY_WILDCARD : LABEL) : null` ladder. Removing
   the `i === len - 1` discrimination makes a mid-path `*` behave as a trailing one.

5. **An omitted regex escape on a user-supplied path segment** — `node.ts`
   `buildRegExpStr`, the `regExpMetaChars.has(k) ? \`\\${k}\` : k` arm. Dropping the
   escape is a **route-bypass / catastrophic-backtracking** class defect, and it is
   the one a reviewer is most likely to under-rate. Seed it exactly once.

6. **A `Map`/object reused across registrations, aliasing state between routers** —
   `router.ts`. Natural sites: `this.#tries![method] = new Trie()` reusing
   `this.#tries![METHOD_NAME_ALL]` instead of constructing a fresh `Trie`, or
   `Object.create(null)` replaced by a shared module-level object, or dropping
   `clearWildcardRegExpCache()` / the `this.#tries = undefined` release. Cross-router
   aliasing is invisible in a single-router read and is the class the economical
   tier is predicted to miss.

### The clean-region rule (do not skip this)

**Leave at least TWO substantial regions of the diff completely unseeded**, and
record which ones in `defect-map.json` under `clean_regions`. Half the pass
condition is *zero fabricated issues*, and that half is meaningless unless there is
correct-but-suspicious-looking code available to falsely accuse. Good candidates,
because they look alarming and are correct:

- the whole `#buildMatcher` rewrite in `router.ts` (the sparse-array
  `for (const i in indexReplacementMap)` loop, the shadowed `len` in the nested
  handler-data loops);
- the `childStr === '' ? '' : …` + `.filter(Boolean)` static-branch pruning in
  `buildRegExpStr`, together with the `#index = isStatic ? -1 : index` sentinel.

Both are genuinely correct in the merged PR. Neither may carry a seeded defect.

### Sanity checks before you seal

- `git apply --check` your `review-diff.patch` against the pinned tree
  (`3feb3551d46de1f633e82253f12cf1117316be93`) — it must still apply cleanly.
- Diff your seeded patch against `../review/base-diff.patch`: the result must show
  **exactly k** edited regions, and each one must be listed in `defect-map.json`.
  Any drift here silently turns a clean region into an unlisted defect and makes the
  fabrication half of the gate wrong.
- Do **not** renumber or reflow the hunks; the map's line numbers must be the line
  numbers in the NEW file as the agent sees them.

## `defect-map.json` format

The matcher matches on **file + line + defect-id**, with a symmetric line window of
`line_match_tolerance` (declared as `3` in `task.yaml`, not here — keep the map free
of tuning knobs).

```json
{
  "version": "sealed-w6-v1",
  "k": 6,
  "defects": [
    {
      "id": "D1-offbyone-trie-index",
      "class": "off_by_one",
      "file": "src/router/reg-exp-router/trie.ts",
      "line": 58,
      "note": "handler index advanced before it is stored, so paths[] maps every dynamic path to the next path's handler"
    }
  ],
  "clean_regions": [
    {"file": "src/router/reg-exp-router/router.ts", "start": 151, "end": 211,
     "note": "#buildMatcher rewrite — correct as merged; false-accusation bait"}
  ]
}
```

`line` is the 1-indexed line in the **new** (post-diff) file, not a diff line
number. `class` is free text for your own analysis; the matcher does not key on it.

## `check.sh` contract

`harness/task-tools/gate/check-hidden.sh` (branch `pr_review`) does not read the map
or the review diff. It only:

1. checks `hidden/check.sh` exists and is executable (else exit 2 → `awaiting_human`);
2. fingerprints **every file** in `hidden/` into one `sha256`, and reads `VERSION`,
   so each result cites exactly which sealed set judged it;
3. runs `bash hidden/check.sh` with `SUBJECT_DIR` exported, discards stdout, and
   surfaces stderr into the gate log;
4. honours the exit code verbatim: **0 = accept, 1 = reject, 2 = unavailable**.

So `check.sh` owns everything else. It must:

- read the agent's review report from the run's participant artifact (the runner
  writes it to `$SUBJECT_DIR/review-report.txt`; if it is missing, exit **1**,
  a reject, not 2 — an absent report is a failed review, not an unavailable gate);
- parse lines of the form `<path>:<line> — <description>` (the format `task.yaml`'s
  prompt demands), tolerating `-`, `–` and `:` as the separator, and ignoring any
  line that does not parse rather than crashing;
- count a seeded defect **detected** when a reported line names the same file and a
  line within ±3 of the map's line;
- count a reported issue **fabricated** when it matches no seeded defect within the
  window;
- **collapse duplicates**: several reports pointing at the same seeded defect count
  once, and several fabrications at the same location count once — otherwise a
  verbose reviewer is punished (or rewarded) by volume rather than accuracy;
- print one line per seeded defect to **stderr** — `DETECTED <id>` / `MISSED <id>` —
  plus `FABRICATED <path>:<line>` per unmatched report. This is what lands in the
  gate log, so it must not reveal the map's `note` text for a MISSED defect;
- exit **0** iff `detected >= k - 1` **and** `fabricated == 0`; else exit **1**.

Reserve exit **2** for "the sealed set itself could not run" (map unreadable,
malformed JSON) — never for a bad review.

## How to verify it in BOTH directions

There is no canonical "solution patch" for a review task, so build two fixtures
here and check the matcher against them by hand:

```bash
cd tasks/suite/W6-pr-review

# fixture A — a PERFECT review: one line per seeded defect, correct file+line.
#             check.sh must exit 0.
# fixture B — the SAME review plus one invented issue in a declared clean region.
#             check.sh must exit 1 (the fabrication half of the pass condition).
# fixture C — k-2 defects found, zero fabrications. check.sh must exit 1
#             (the recall half: k-1 is the floor, not k-2).

for f in A B C; do
  SUBJECT_DIR=.work/repo bash hidden/check.sh < /dev/null; echo "fixture $f -> $?"
done
```

Keep those fixtures in `hidden/` too — they are part of the sealed set and are
covered by its hash, which is exactly right: changing a fixture changes the hash and
therefore the recorded identity of the gate.

Then run the validator:

```bash
TASK_DIR=tasks/suite/W6-pr-review bash harness/task-tools/validate.sh
# before you author: 4 pass, 2 awaiting-human, 4 n/a, 0 failed
# after  you author: 6 pass, 0 awaiting-human, 4 n/a, 0 failed
```

The four `not_applicable` checks (2 deps, 4 clean install, 5 baseline tests, 9 clean
build) are correct and expected: nothing in this task is installed, compiled or
executed. They are recorded with their reason, never passed vacuously
(`harness/task-tools/stacks/none.sh`).

## Pre-registration

W6 is a candidate **escalation probe** (SPEC §5.1 names W6 primary, W3 fallback; for
this batch W3 is the designated probe and carries the registered prediction). If you
also want a prediction for W6, register it in `manifest/preregistrations/` **before**
any run, together with `k`. Record the printed `hidden_test_hash` in
`manifest/delivery-manifest.yaml` under `w6_task.sealed_defect_map` (replacing
`status: awaiting_human`). Rotate/reseal per evaluation cycle (SPEC §2.6).
