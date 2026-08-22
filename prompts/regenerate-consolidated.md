# PROMPT — regenerate the consolidated decision table (post confound-makeup)

Paste into Claude Code **after** the confound makeup driver exits and after the
reconcile PR is merged. Read-only over `results/`. **Zero spend. No container. No model
call. No sealed file is read.** If any step would require one of those, stop and report.

---

## 0. Preconditions — verify before touching anything

Report each as a line. If any fails, **stop and report; do not proceed**.

```bash
# a. confound makeup — expect 8 dirs (3 slots deferred-contaminated; this is correct)
ls -d results/screening-batch1-confound-makeup/*/ | wc -l

# a2. the table already exists from 2026-08-21T12:28:52Z — this is a COLUMN PASS over it
ls -l report/findings/consolidated-table.md report/findings/consolidated-table.json

# b. driver exited; no live process
pgrep -f screening-batch1-makeup-driver.sh || echo "no driver running"

# c. branch reconciled
git ls-remote --heads origin
git status --porcelain
git log --oneline -5

# d. all four datasets present
for d in screening-batch1 screening-batch1-makeup screening-batch1-makeup-w6 \
         screening-batch1-confound-makeup; do
  printf '%-40s %s\n' "$d" "$(ls -d results/$d/*/ 2>/dev/null | wc -l)"
done
```

Confound makeup is KNOWN to hold 8 of 11 (3 deferred-contaminated W3 C5 slots — an
instrument refusal, already documented). 8 is the expected count, not a failure.
If any other count is short, **do not treat the shortfall as data.** Report which slots are
missing against `report/findings/confound-makeup-enumeration.log` and stop. A cap-halt
is resumable with `--start-at N --spend-cap-usd 250`; that is a human decision.

---

## 1. Implement the `attribution_rule` column in `consolidate.py`

The collector records the rule per run (`attribution_rule.rule` ∈ {v1,v2,v3}) in the
provider-usage backfill and refusal artifacts. `consolidate.py` never surfaces it.

**Why this matters — do not skip the reasoning in the code comment.** Batch 1's
Product-B legs were attributed under v1 and v2; the confound makeup runs under v3
(rate-ceiling, 25k tok/s). Four runs already carry a v1 refusal *and* a v2 attribution —
both records stand, because the rules draw different windows. A consolidated cost column
spanning four datasets therefore spans up to three windowing rules. Unlabelled, that is
exactly the confound class this repo exists to catch.

Requirements:

- Read `attribution_rule.rule` from each filled run's backfill/refusal artifact.
- Aggregate per cell as a **sorted set** of rules present across filled reps.
- Render as its own column: `v1`, `v3`, `v1,v3`, or `n/a` for arms with no Product-B leg.
- A refusal artifact still carries a rule — record it. A refused window means the leg's
  tokens are `unavailable`; it does **not** mean the rule is absent.
- Where a cell's filled reps span more than one rule, set a flag on the cell
  (`cost_rule_mixed: true`) so the renderer can mark that its cost figures are not
  comparable across reps.
- Do **not** infer a rule from a sibling run, and do **not** default to v2 when absent —
  absent renders as `unavailable`, consistent with CLAUDE.md rule 3.

Add tests in `tests/test_consolidate.py` covering: single-rule cell; mixed-rule cell;
cell with a refusal-only artifact; arm with no Product-B leg. Use the existing
`tests/fixtures/` pattern — no new fixture framework.

---

## 2. Give every `unavailable` cost a stated reason

`_fmt_cost` currently returns a bare `"unavailable"`. Every unavailable cost must render
`unavailable — <reason>`, drawn from the record, not hard-coded per arm. Reasons already
distinguishable from the data:

| Condition | Reason string |
|---|---|
| every leg unpriced, refusal on record | `no priced leg; provider window refused (<rule>)` |
| some legs priced, some not | `partial: <n> of <m> legs unpriced` |
| no usage record at all | `no provider usage record` |

Keep `cell_cost`'s existing exclusion logic exactly as it is — runs with any unpriced leg
stay out of the median and are counted separately. This change is presentation only; **no
figure may move.** State that explicitly in the commit message.

Preserve the `≤` upper-bound marker and its rule: one cache-blind leg bounds the whole
cell and is not diluted by exactly-priced runs beside it.

---

## 2b. Correct the collector's stated rationale (documentation only, no behaviour change)

`harness/collectors/vertex_token_collector.py` opens by asserting that Product B exposes
no machine-readable usage in headless mode. **That is false**, and it is the documented
justification for the apparatus that produces 41 of the 42 costed cells in this study.

The collector is NOT removed and NOT modified in behaviour. What changes is its stated
role: it was built as the sole cost source; it is now the provider-side cross-check.
Rewrite the module docstring's opening to say, in the file's own voice:

- Product B DOES expose machine-readable usage in headless mode, under
  `--output-format json` (verified 2026-08-22, agy 1.1.13).
- This harness did not request that mode until 2026-08-22; see
  `report/findings/agy-json-flag-defect.md`.
- This collector was built to compensate for that gap and remains the provider-side
  cross-check: independent of the product's self-report, at derived attribution,
  bounded by the provider metric's lack of a cache series for this publisher.

Change no constant, no threshold, no query, no output. `git diff` for this file must
show docstring lines only. If any non-comment line changes, revert and report.

## 2c. Scope the cache-blindness note (additive prose, NO pin change)

`manifest/delivery-manifest.yaml` `notes.gemini_cache_blindness` records that the
provider meters no cache series for this publisher, so cache classes are excluded rather
than zero-filled and Product-B costs are upper bounds.

**That statement remains true and its pin does not change.** It describes the provider
metric, and the provider metric is still cache-blind. What is newly known is that a
second, unused source exists.

Append one scope sentence to that note, changing nothing else:

> This describes the provider metric. The product exposes `cache_read_tokens` under
> `--output-format json`, unused in this batch; with that flag in force the cache-read
> class stops being excluded and Product-B costs move from an upper bound toward an
> exact figure.

Constraints: no numeric value, pin, hash or key may change anywhere in the manifest.
Print the note verbatim before and after in your report. If honouring the repo's
human-authored-amendment rule strictly, the human may prefer to make this edit
themselves — if so they will say so and you skip 2c; do not skip it on your own
judgement.

## 3. Regenerate

```bash
GEN_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
.venv/bin/python -m harness.analysis.consolidate results \
  --dataset screening-batch1 \
  --dataset screening-batch1-makeup \
  --dataset screening-batch1-makeup-w6 \
  --dataset screening-batch1-confound-makeup \
  --out-md   report/findings/consolidated-table.md \
  --out-json report/findings/consolidated-table.json \
  --generated-at "$GEN_AT"

sha256sum report/findings/consolidated-table.json
git rev-parse --short HEAD
```

Status stays **PENDING** on the rendered table. No figure leaves `report/` before
CP-FINDINGS.

---

## 4. Verify the output before reporting it

Do not report success on exit code alone. Check each and report the actual value:

1. **Slot accounting.** Filled + holes = registered slots, per task and per arm. Any
   discrepancy is a bug in supersession, not a data property.
2. **Supersession sanity.** No cell pools a batch-1 (1800s) rep with a pinned-budget rep
   of the same slot. Spot-check `w3-sqlfluff-segment-method-migration` and
   `w6-hono-router-review` by hand and paste the rows.
3. **Holes classified.** Every hole is `budget exhaustion` or `unreplaced loss`. Confirm
   W3 P0 rep1 and W3 P1 rep1 land in **budget exhaustion** — they timed out at 1800s and
   again at 7200s, so "does not complete at 2h" is the result, not a gap.
4. **No truncated run renders as a rejection.** Grep the rendered table for any cell
   where a truncated attempt produced a `rejected` verdict. Expect zero.
5. **W6 gradient.** Confirm P0 3/3, C2 (now with its confound rep), C3-med 1/3, C3 0/3,
   C3-prev 0/3, and that batch-1's W6 cells remain **void** and unmerged.
6. **Product-B cost unchanged in value.** 41 of 42 cells are costed (`≤` bounds);
   `w3…::C5` is the sole cost-less cell because it has no runs. This pass adds columns
   and reasons — **no cost figure may move.** Diff the before/after cost column and
   confirm zero numeric changes.
7. **Both preregs still rendered and UNCHANGED.** They are already graded in the
   existing table (H-effort parity holds on pilot and w1; W3-escalation
   `prediction_supported`, understrength at n=2). This pass must not alter either
   verdict. The H-effort cost half stays ungradable: both arms are cache-blind upper
   bounds, and a ratio of two `≤` bounds is not a measured reduction — the registered
   30–50% band is NOT drawn.
8. **Attribution rules populated.** No cell with a Product-B leg shows an empty rule.
   Report how many cells are mixed-rule.
9. **Tests.** `bash tests/run-tests.sh` green.
10. **Scoped edits stayed scoped.** `git diff --stat` shows only: `consolidate.py`,
    its tests, `report/findings/consolidated-table.*`,
    `harness/collectors/vertex_token_collector.py` (docstring lines only), and
    `manifest/delivery-manifest.yaml` (one appended sentence). Nothing under
    `results/`, nothing in `manifest/cp-findings.md`.

---

## 5. Report back — this format, nothing else

```
SLOTS      filled=<n>  holes=<n> (exhaustion=<n>, unreplaced=<n>)  registered=<n>
DATASETS   <per-dataset run counts contributing filled slots>
W6         P0 _/_  C2 _/_  C3-med _/_  C3 _/_  C3-prev _/_   (batch1 W6 = void, unmerged)
COST       priced=<n>  bounded=<n>  unavailable=<n>   solo-B all unavailable? Y/N
RULES      v1=<n> v2=<n> v3=<n> mixed=<n> n/a=<n>
PREREG     H-effort: parity=<...>, cost-half=ungradable
           W3-escalation: economical=<...>, escalation=<...>, outcome=<...>
TABLE      sha256=<...>  generated_at=<...>  harness=<short-sha>
TESTS      <pass/fail>
COLLECTOR  docstring corrected: yes/no   non-docstring lines changed: <must be 0>
CACHENOTE  <the gemini_cache_blindness note, verbatim BEFORE>
           <the same note, verbatim AFTER>
DIFFSTAT   <git diff --stat, verbatim>
SURPRISES  <anything that did not match the expectations above, or "none">
```

Then **stop.** Do not open a PR, do not update `docs/`, do not point the renderer at the
data, do not write anything into `manifest/cp-findings.md`. Those are human gates.

---

## Guardrails

- Read-only over `results/`. Never edit, move or delete a run directory.
- Never pool two datasets into one cell. Supersede per slot or record a hole.
- Never infer an unavailable figure from a sibling run. Unavailable is not zero.
- Never convert a harness fault into a model result.
- If an assumption in this prompt contradicts what you find in the repo, **stop and say
  so** rather than resolving it yourself. The repo is authoritative; this prompt is not.
