# Sealed hidden test — W1 / F3 (test-generation) — HUMAN AUTHORING SPEC

This directory's contents (except this README) are **sealed, human-authored, and
human-held** — gitignored (`**/hidden/*`), never committed, injected only by
`check-hidden.sh` at run time and recorded by SHA-256. Do not let any model author
this (SPEC/CLAUDE non-negotiables).

## What the sealed test must do — MEANINGFULNESS via mutation-catch

The public gate (T1–T4) proves the agent's tests exist, keep the suite green, hit
**100% branch coverage** of the two mappers, and pass on correct code. But
coverage ≠ meaningful: a suite can execute every branch and assert nothing useful.
The sealed test closes that gap by **mutation testing** — it must fail an agent
whose tests do not actually catch broken behavior.

Author, in this dir, a `check-hidden` step (script + mutant fixtures) that:

1. Takes the agent's produced test file(s) under `src/tests/` (unmodified).
2. For each **seeded mutant** of the mappers, replaces the mapper source with the
   mutant, runs the agent's tests, and requires **≥1 of them to FAIL** (the mutant
   is "caught"). Restore the pristine mapper between mutants.
3. **Accept** only if the agent's tests catch **every** mutant in the set; else
   **reject**. (Exit codes per the harness contract: 0 accept, 1 reject, 2 hidden
   unavailable — mirrors `harness/task-tools/gate/check-hidden.sh`.)

### Suggested mutant set (author/adjust; keep sealed)
- **authorMapper**: `following: id ? … : false` → force `following` always `false`
  (kills tests that only check the `id`-absent path) and always `true`.
- **authorMapper**: flip the `.some(...)` predicate (`=== id` → `!== id`).
- **articleMapper**: `favorited` → always `false`; `favoritesCount` →
  `favoritedBy.length + 1` (off-by-one); `tagList.map(tag => tag.name)` →
  `tag => tag` (wrong shape).
Each mutant must be caught by any test suite that asserts the true mapped values.

## Then: 10-point validation + version bump
After authoring, run `TASK_DIR=tasks/suite/W1-test-generation bash
harness/task-tools/validate.sh` (no model spend): the **canonical** reference tests
(`canonical/mapper-tests.patch`) must be accepted (catch all mutants, 100% branch,
suite green), and the **pre-modification** tree must fail (no mapper tests yet).
On success set `task_suite_version: w1-v1`, record the sealed hash in
`manifest/delivery-manifest.yaml` (`w1_task.sealed_hidden_test`), and W1 is ready
for the batch-2 CP-SPEND.

## Contamination note
Same RealWorld repo as F1 (contamination_tier: famous). W1's CP-SCREEN-PREREG
pre-registration must disclose this feasibility reuse (workload.yaml
`feasibility_reuse`).
