# W6 — PR review against a sealed seeded-defect map (hono RegExpRouter)

Screening task, added 2026-08-16. Candidate **C8** in
[`tasks/proposals/2026-08-commit-mined-candidates.md`](../../proposals/2026-08-commit-mined-candidates.md).
Definition: [`task.yaml`](task.yaml) · workload framing: [`workload.yaml`](workload.yaml).

## Provenance

Commit-mined per `tasks/WORKLOAD-SELECTION.md` §4. Both SHAs were resolved through
the GitHub API and re-verified locally against a clone (`parents[0]` of N equals
N−1; squash merge, single parent).

| | |
|---|---|
| Repo | [honojs/hono](https://github.com/honojs/hono) · MIT · 31,686 stars (2026-08-16) |
| PR | [#5171](https://github.com/honojs/hono/pull/5171) — *feat(reg-exp-router): throw UnsupportedPathError during route registration* |
| Merged | 2026-08-03T21:18:54Z |
| N (fix) | `8a0b18fd9b4d64dd2eb1d7f18e3536fc06cb54b2` |
| N−1 (pin) | `3feb3551d46de1f633e82253f12cf1117316be93` |
| Contamination tier | `post_cutoff` — declared before running, never revised on results; model-relative (WORKLOAD-SELECTION §2) |

## What the participant does

Unlike every other task in the suite, the participant writes no code. It **reads a
diff and reports defects**, one per line, as `<path>:<line> — <description>`. The
diff it reads is [`review/base-diff.patch`](review/base-diff.patch) — the real
upstream change, restricted to the three source files — **with k defects seeded into
it by the human**. The seeded copy and its ground-truth map are sealed
(`hidden/`, gitignored, human-held).

```
src/router/reg-exp-router/node.ts     170 changed
src/router/reg-exp-router/router.ts   187 changed
src/router/reg-exp-router/trie.ts      21 changed
```

`src/router/reg-exp-router/router.test.ts` (+194 upstream) is **deliberately
withheld** (`withheld_paths` in `task.yaml`). A reviewer that can read the PR's own
tests has an oracle for the seeded defects, and the task would then measure test
reading, not review skill.

## Why this PR, and why it should discriminate

The diff is three logically distinct changes braided into one review:

1. a `compareKey()` ordering fix — the only-wildcard vs. tail-wildcard comparison was
   inconsistent, so sibling order was not a total order;
2. a param-capture fix — a route like `/w/:id/y` registered after `/w/*/x` reused the
   label node the unnamed wildcard created and silently lost the param value
   (`nextNode.#varIndex ??= context.varIndex++`);
3. the headline rework: paths are inserted into per-method tries incrementally in
   `add()` so unsupported combinations throw `UnsupportedPathError` at
   **registration** rather than at first match. `Node#insert` goes from recursion to
   a loop, `pathErrorCheckOnly` becomes `isStatic`, `buildRegExpStr()` learns to
   prune empty static branches, and `Trie` grows `#index` / `paths`.

Three properties make it a plausible discriminator between configurations:

- **The bugs are about *when* code runs, not what it computes.** Registration-order
  and cross-registration aliasing defects are invisible to a reader who checks each
  hunk locally and never simulates two `add()` calls in sequence.
- **There is abundant correct-but-alarming code.** The `#buildMatcher` rewrite and
  the `#index = isStatic ? -1 : index` sentinel look wrong and are not. The gate's
  zero-fabrication half turns that into a real cost.
- **Recall and precision are gated together.** `>= k-1` detections **and** zero
  fabrications. A configuration that compensates for weak localisation by listing
  every suspicious line fails, which is exactly the failure mode a
  detections-only score would reward.

Batch 3's ceiling effect (27/27 accepted) came from tasks where a single correct
edit was enough. This task has no single edit; the score is a joint precision/recall
condition over a 526-line diff.

## Gate

`gate_type: pr_review`, `stack: none`. Nothing is installed, compiled, or executed
in the subject tree, so the four SPEC §2.8 checks that exist to prove an *execution*
environment — 2 deps/ORM, 4 clean install, 5 baseline tests, 9 clean container build
— are recorded `not_applicable` **with a reason** rather than passed vacuously
(`harness/task-tools/stacks/none.sh`).

The harness never reads the defect map. `check-hidden.sh`'s `pr_review` branch
discovers the human-authored `hidden/check.sh`, hashes the whole sealed set,
invokes the runner, and honours its exit contract (`0` accept · `1` reject · `2`
awaiting/unavailable) — the same executable-runner shape already used by the
`test_generation` gate. Matching is by **file + line + defect-id** with
`line_match_tolerance: 3`.

## Current status

Ten-point validation runs today at **4 pass · 2 awaiting_human · 4 not_applicable ·
0 failed**. Checks 6 (pre-modification failure) and 7 (hidden-test pass) are
`awaiting_human` because the sealed set does not exist yet; they are *not* failures
and the validator still exits 0.

Everything the human needs in order to author the sealed set in one sitting — the
six defect classes anchored to concrete regions of the real diff, the ≥2
clean-region rule, the `defect-map.json` schema, and the `check.sh` exit contract
plus a both-directions verification recipe — is in
[`hidden/README-FOR-HUMAN.md`](hidden/README-FOR-HUMAN.md).

## Run it

```bash
TASK_DIR=tasks/suite/W6-pr-review bash harness/task-tools/setup.sh     # clone + checkout pin
TASK_DIR=tasks/suite/W6-pr-review bash harness/task-tools/validate.sh  # 10-point report
TASK_DIR=tasks/suite/W6-pr-review bash harness/task-tools/reset.sh     # deterministic reset
```

No model spend is involved in any of the above.

## Files

| path | tracked | what |
|---|---|---|
| `task.yaml` | yes | task definition, pins, prompt, gate wiring |
| `workload.yaml` | yes | W6 workload framing, class-claim and probe notes |
| `review/base-diff.patch` | yes | the real upstream diff (526 lines), src files only |
| `hidden/README-FOR-HUMAN.md` | yes | seeding + matcher authoring instructions |
| `hidden/review-diff.patch` | **no** | sealed: base diff with k defects seeded |
| `hidden/defect-map.json` | **no** | sealed: ground truth |
| `hidden/check.sh`, `hidden/VERSION` | **no** | sealed: matcher + label |
| `.work/` | no | runtime clone; never committed |
