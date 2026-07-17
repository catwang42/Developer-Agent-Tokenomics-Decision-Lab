# CLAUDE.md — Operating Manual for Claude Code

You are building the **Developer-Agent Economics Decision Lab**. `SPEC.md` (frozen
v2.1.1) is the single source of truth. If any instruction, plan file, or user request
conflicts with SPEC.md, STOP and ask the human. Do not edit SPEC.md or this file.

## Non-negotiable rules

1. **Never fabricate data.** No invented telemetry, run results, token counts, costs,
   or benchmark numbers — anywhere, ever. Test fixtures must be labeled `SYNTHETIC` in
   filename and content, live only under `tests/fixtures/`, and never under `results/`.
2. **Model self-reports are not telemetry.** Never write a prompt that asks a model to
   report its own token usage as a measurement.
3. **Unavailable ≠ 0.** Missing telemetry fields are recorded as `"unavailable"` with
   confidence tier, never zero-filled or imputed.
4. **Claims register (SPEC §1.2) applies to everything you write** — docs, site, README,
   commit messages: no "audit-grade", no vendor-superiority claims, no FTE conversions,
   no unscoped findings, no exact pilot percentages in public-facing pages.
5. **No live model-API spend without an approved CP-SPEND checkpoint.** Any command that
   would bill an Anthropic/Google account (running `claude -p` as a benchmark subject,
   `agy`, provider APIs) requires prior checkpoint approval with a cost estimate.
   Building/testing with stub adapters is always allowed.
6. **Quality gates before "done":** `bash tests/run-tests.sh` passes; `shellcheck` clean
   on all `*.sh`; all JSON/YAML validates; `mkdocs build --strict` passes when docs
   change. Show the command output as evidence.
7. **Permanent material uses placeholder labels** (Product A/B, STRONG_MODEL_A…);
   exact models/prices only in `manifest/delivery-manifest.yaml` and `pricing/`.

## Workflow

- Execute **one phase at a time** from `plans/PHASE-N-*.md`, in order. Do not start
  phase N+1 until phase N's acceptance checklist is verified and its checkpoint (if
  any) is approved.
- **Start every phase in plan mode.** Present a concrete plan (files, commands,
  verification) before writing anything.
- **Git discipline:** branch `phase/N-<short-name>`; conventional commits
  (`feat:`, `fix:`, `test:`, `docs:`, `chore:`); at phase end run the quality gates,
  then open a PR with `gh pr create` summarizing evidence against the acceptance
  checklist. Never push directly to `main`. Never force-push.
- **Context hygiene:** after a phase is merged, tell the human to `/clear`; on a fresh
  session, re-read `CLAUDE.md` + the current phase file before acting.
- If a step is ambiguous, prefer asking one precise question over guessing.

## Human checkpoints — STOP and request review

When a checkpoint is reached, output exactly this block and **stop working**:

```
CHECKPOINT REQUIRED: <ID>
Produced: <artifacts with paths>
Verify:   <what the human must check, as a short list>
Risk:     <what goes wrong downstream if this is wrong>
Est. cost: <API spend estimate — CP-SPEND only>
```

Resume only after the human replies `CHECKPOINT APPROVED: <ID>` (or gives corrections).

| ID | When | Gate for |
|---|---|---|
| CP-SCHEMA | End of Phase 1 | Telemetry schema + validators frozen |
| CP-TASK | End of Phase 2 | Pilot task 10-point validation report; hidden-test plan |
| CP-SPEND | Before ANY live benchmark run (Phases 3–4, each batch) | Budget + configs + manifest |
| CP-DATA | After feasibility runs | Telemetry-completeness report accepted |
| CP-SCREEN-PREREG | Before screening runs | Pre-registration of all W1–W5 tasks (anti-bias protocol) |
| CP-FINDINGS | Before any result appears in docs/site/report | Numbers, scoping language, claims register |
| CP-PUBLISH | Before Pages deploy includes results content | External-facing review |

## Environment & measurement facts you must respect

- Benchmark-subject telemetry for Product A comes from `claude -p --output-format json`
  usage metadata (authoritative tier) — never from response text.
- Product B (`agy`) telemetry is limited: capture product-reported usage where exposed,
  else record `unavailable`; its headless quirks live in OUR adapter
  (`harness/adapters/`), whose exit codes/timeouts are workshop-owned (SPEC §1.3).
- Record the exact product selector/routed label; never infer a backend model version
  the product doesn't guarantee (SPEC §6.3).
- Every run writes an **event log + derived run summary** (SPEC §2.7), each field with
  value + confidence tier, plus `cost_basis`.
- `results/cohort/` and `tasks/hidden/` are gitignored; hidden tests are human-held.
