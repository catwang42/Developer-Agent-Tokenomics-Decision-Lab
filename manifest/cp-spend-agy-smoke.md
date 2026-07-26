# CP-SPEND package — single Antigravity smoke run (harness verification)

Prepared for the **CP-SPEND** checkpoint (CLAUDE.md rule 5; SPEC §2.3). This
document is the material the human reviews before the run. **It does not authorize
spend.** Nothing runs until the human writes `CHECKPOINT APPROVED: CP-SPEND`.

**Status:** awaiting approval. Prepared 2026-07-26 on branch `phase/3-harness`
after the harness-defect fixes below. No model spend has occurred in preparing it
(only `agy --version` / `agy --help` / `agy models`, which do not bill).

## 1. Purpose (narrow, non-comparative)

A **single** live Antigravity (Product B, config **C3**) run on the pilot task, to:

1. **Verify the corrected invocation executes.** Batch 2's two F1·C3 runs produced
   **zero agent changes** — both `agent-solution.diff` files are byte-identical
   (sha256 `00b547c1…`) to the harness `test-compat.patch`. Root cause: the adapter
   prepended a bogus `run` token (agy 1.1.4 has no `run` subcommand). Confirm the
   fixed command actually drives Antigravity to edit the subject repo.
2. **Inspect agy's raw JSON for a usage block.** The run's `invocation.txt` now
   captures the product's raw stdout/stderr (credentials redacted). Read it to
   determine whether Product B exposes any token counts — the question
   `report/telemetry-completeness.md` §4 finding 3 can no longer answer from batch 2.
3. **Settle `--print` value-vs-boolean.** Whether `--print` takes the prompt as its
   value or is a boolean switch is unresolved from `--help` alone; a verified
   invocation settles it. (The current ordering is correct under either reading.)

**This is a harness-verification smoke run, not screening.** It produces **no
vendor-comparative claim**, is **not** part of the controlled 27, and no number from
it appears in docs/site/report before CP-FINDINGS.

## 2. Exact invocation (ONE run)

```bash
LAB_ALLOW_SPEND=1 bash harness/runner/run.sh \
  --task tasks/pilot-realworld --config C3 --rep 1 \
  --phase smoke --cache-state cold \
  --subject-isolation host \
  --spend-cap-usd 2
```

- Resolves (verified in `--dry-run`, no spend) via `manifest/delivery-manifest.yaml`
  → `PRODUCT_B_ECON_TIER`: selector `"Gemini 3.5 Flash (High)"` (verbatim, present in
  `agy models`; matches `pricing/prices-2026-07-19.json`), `cost_basis:
  marginal_api_cost`, backend model id never inferred (SPEC §6.3).
- Adapter emits: `agy --dangerously-skip-permissions --model "Gemini 3.5 Flash (High)"
  --print <prompt>` — **no `run` token** (Fix 3).
- Output lands in `results/smoke/<run_id>/`: `events.jsonl`, `summary.json`,
  `agent-solution.diff` (pre-gate — Fix 5), `post-gate.diff`, `invocation.txt`
  (argv + product_version + exit code + raw stdout/stderr, redacted — Fix 2).

**Subject isolation:** `host` (the batch-2 posture; the containerized agent leg is
unimplemented). Full containerized isolation + egress allowlist are **not** required
for this Phase-3 smoke run — they are HARD REQUIREMENTS only at the **Phase-4
screening** CP-SPEND (report §6 condition 1).

## 3. Budget vs ceiling

**Ceiling: $2.** A single black-box pilot attempt is expected to cost well under $2
(and Product-B marginal cost may even be recorded `unavailable` if tokens are not
exposed — never zero-filled). `--spend-cap-usd 2` is set for defence in depth: the
in-runner kill-switch halts **before** any *further* run once known spend reaches the
cap, so this authorizes **at most one** billable Product-B run. There is no separate
Product-A/Claude spend in this package.

## 4. Success criteria (what the human checks after the run)

1. Run exits 0; `events.jsonl` + `summary.json` pass the validator.
2. `agent-solution.diff` is **non-empty and NOT identical** to
   `tasks/pilot-realworld/gate/test-compat.patch` (proves Antigravity actually
   edited the repo, i.e. the invocation is fixed), and contains no harness patch
   (Fix 5 — the harness edit, if any, is isolated in `post-gate.diff`).
3. `invocation.txt` records agy's exit code and raw stdout; inspect it for a usage
   block → decide whether to reword report §4 finding 3 to an observed result.

## 5. Guards in place

- Refuses to run without `LAB_ALLOW_SPEND=1`; refuses unresolved manifest/pricing.
- Cost reconstructed from product token metadata, never model self-report.
- Single run; `--spend-cap-usd 2` blocks any second run in the batch dir.
- No Claude/Product-A spend; no screening; no comparative claim.

## 6. What approval covers vs gates

- **Covers:** exactly one C3 run on the pilot task at a $2 ceiling, for harness
  verification and telemetry inspection.
- **Gates:** its output informs whether report §4 finding 3 can move from "not yet
  observed on a verified invocation" to an observed result. It does **not** authorize
  the Phase-4 screening batch (separate CP-SCREEN-PREREG + screening CP-SPEND, with
  containerized isolation + egress mandatory).
