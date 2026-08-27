# Operator Guide — run the lab, no AI assistant required

This is the front door for **using or forking** the lab. Running it — validation,
batches, telemetry checks, aggregation, reports, the site — needs **plain shell,
Python, and Node only.** No AI assistant is in the runtime path.

## Three roles (don't conflate them)

1. **Build agent — provenance, not a dependency.** Claude Code was the tool that
   originally built this repository, phase by phase (see the repo-root
   `GETTING_STARTED.md` and `CLAUDE.md`). Any agent — or a human — could rebuild or extend
   it. **Claude Code was the build tool and appears nowhere in the runtime path.**
2. **Benchmark subjects — the things under measurement.** The AI coding agents being
   measured, driven through **declared adapters** (`claude_code` and `agy` today;
   extensible via the adapter contract — see `harness/adapters/README.md`). Subjects are
   AI agents by definition; the operator drives them through **deterministic adapters**.
3. **Lab runtime — deterministic.** Everything in this guide runs from a shell. The
   acceptance gate's **primary path is deterministic** (SPEC §2.6) — build/typecheck/
   public + sealed hidden tests. Model-based rubric review is **supplementary and
   separately measured** (the human-effort / HEAC subset), never part of the
   deterministic accept/reject decision.

If you are authoring your own hidden tests, see
[Sealed evaluation → *Authoring your own set (fork operators)*](sealed-evaluation.md).

---

## Quickstart

```bash
# Python 3.10+ and Node.js 18+ required. From the repo root:
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
bash tests/run-tests.sh
```

Expected: the last line is `[tests] PASS — JSON: <n>, YAML: <n>, shell: <n>, + python
unit tests`, exit `0`. `shellcheck` is auto-installed via `apt` if absent. This single
command is the whole quality gate; if it is green, your checkout is healthy.

---

## No-spend operations

None of these bill any model account. They use stub adapters, synthetic fixtures, or
read already-collected telemetry. Copy-paste as written.

### 1. Full quality gate (JSON/YAML validation, shellcheck, structure gate, unit tests)

```bash
bash tests/run-tests.sh
```
Exit `0`; final line `[tests] PASS — …`. Non-zero if any check fails.

### 2. Report ↔ results structure gate (the pairing gate a fork must keep green)

```bash
.venv/bin/python -m unittest tests.test_report_structure -v
```
Exit `0` (`OK`). Enforces the append-only report rules (see **Fork guidance** below).
Also runs inside `tests/run-tests.sh` — this is how to run just that check.

### 3. Dry-run a single controlled run (stub adapter — no spend)

```bash
bash harness/runner/run.sh \
  --task tasks/pilot-realworld --config P0 --dry-run --cache-state cold \
  --manifest tests/fixtures/manifest-SYNTHETIC.yaml --out-root /tmp/lab-dry
```
Exit `0`; prints `run_dir: /tmp/lab-dry/…` then a `validate: PASS` line. Configs:
`P0`, `P1`, `C1`, `C2`, `C3`, `C5`. `--cache-state {cold|warm-series}` is required.
Dry-run output only ever lands under `--out-root`, never under `results/`.

### 4. Dry-run the warm-series driver (stub — no spend)

```bash
bash harness/runner/run-warm-series.sh \
  --task tasks/pilot-realworld --config C1 --reps 3 --dry-run \
  --manifest tests/fixtures/manifest-SYNTHETIC.yaml --out-root /tmp/lab-warm
```
Exit `0`; prints one line per rep — rep 1 `[cold]`, reps 2..n `[warm-series]` — each
ending `validate=PASS`. The driver stages the subject tree once, resets it between reps,
and cleans up once; the prompt is byte-identical across reps.

### 5. Reset a subject working tree to its pinned commit (no spend)

```bash
TASK_DIR=tasks/pilot-realworld bash harness/task-tools/reset.sh
```
Exit `0`; prints `reset_ok pin=<sha> tree=<hash>`. Idempotent (same tree hash every
run). Preserves `node_modules`.

### 6. Aggregate a dataset — descriptive, NON-COMPARATIVE

```bash
bash harness/aggregate/run.sh results/screening-batch1
```
Exit `0`; prints a NON-COMPARATIVE per-cell table (acceptance counts + descriptive cost
stats over known costs only; unavailable-cost legs counted, never zero-imputed). Add
`--json-out /tmp/agg.json` to also write JSON. No cross-product/cross-config ranking.

### 7. Compute metrics (ECST / QA-ECST / HEAC) — NON-COMPARATIVE

```bash
.venv/bin/python -m harness.evaluator.metrics results/screening-batch1 > /tmp/metrics.json
```
Exit `0`; writes a NON-COMPARATIVE metric bundle (JSON) to stdout. HEAC uses
`loaded_rate_per_minute` declared in `manifest/delivery-manifest.yaml` (a declared org
input, never a measurement); the human term is `unavailable` unless the criterion-6
human-effort subset has been recorded. A benign `RuntimeWarning` from `python -m` may
appear on stderr — it does not affect the JSON on stdout.

### 8. Build / serve the site

```bash
mkdocs build --strict     # exit 0 on a clean build; fails on broken nav/links
mkdocs serve              # local preview at http://127.0.0.1:8000 (Ctrl-C to stop)
```

### Task authoring (fork operators) — no model spend, but needs Node + network + Docker

Validating a candidate benchmark task runs the SPEC §2.8 ten-point check end-to-end in a
clean container (clones the pinned repo, installs deps, builds an offline image). It runs
for several minutes and bills **no** model account:

```bash
TASK_DIR=tasks/pilot-realworld bash harness/task-tools/setup.sh     # clone@pin + deps
TASK_DIR=tasks/pilot-realworld bash harness/task-tools/validate.sh  # 10-point validation
```
`validate.sh` emits `validation-report.json` and a human summary; exit `0` iff no check
**failed**. Checks that need the human-held sealed hidden tests report `awaiting_human`
(not a failure) when those tests are not present. See the ten checks documented at the
top of `harness/task-tools/validate.sh`, and author hidden tests per
[Sealed evaluation → *Authoring your own set*](sealed-evaluation.md).

---

## Spend-gated operations — require `LAB_ALLOW_SPEND=1` and a funded account

**Do not run these unless you intend to bill a real model account**, and only under a
CP-SPEND-approved plan (CLAUDE.md rule 5). The runner refuses to start a live run unless
`LAB_ALLOW_SPEND=1` is set, and honours `--spend-cap-usd` as an in-runner kill-switch.
The commands below are shown for reference — **this guide does not execute them.** To
inspect their arguments safely (no spend), append `--help`.

Live controlled run (drops `--dry-run`; bills the subject's provider):

```bash
LAB_ALLOW_SPEND=1 bash harness/runner/run.sh \
  --task tasks/pilot-realworld --config P0 --cache-state cold --spend-cap-usd <N>
```

Live warm-series (rep 1 cold, reps 2..n resumed; bills the subject's provider):

```bash
LAB_ALLOW_SPEND=1 bash harness/runner/run-warm-series.sh \
  --task tasks/pilot-realworld --config C1 --reps 3 \
  --phase warm-series --spend-cap-usd <N>
```

Syntax-check either without spending:

```bash
bash harness/runner/run.sh --help
bash harness/runner/run-warm-series.sh --help
```

Live runs write into `results/<phase>/`. Which models/prices a live run resolves come
from `manifest/delivery-manifest.yaml` + `pricing/`; a live run refuses to start on an
unresolved manifest.

**Product-B version pin (pre-batch check).** Product B (`agy`) self-updates, so the
binary can move between the CP-SPEND approval that priced a batch and the run that
spends against it — and a batch whose later runs measure a different build is not the
experiment that was approved. A live run therefore probes `agy --version` **before**
anything is created or billed and refuses to start unless it equals the manifest pin
(`subject_isolation.agent_leg.agy_version`, mirrored in every
`configurations.PRODUCT_B_*.conditions.agy_version`); an unreadable version is a refusal
too. The adapter sets the product's own updater kill-switch
(`AGY_CLI_DISABLE_AUTO_UPDATE=1`) on every invocation, including that probe, and the
state is recorded per run as `conditions.auto_update`. If the check fires, re-pin the
manifest with the drift recorded — do not work around it.

---

## Fork guidance

If you fork this repo to run your own measurements:

- **Keep the structure gate green (CLAUDE.md rule 8 — reports are append-only per
  batch).** Every dataset directory under `results/` is listed in the repo's
  `results/README.md` and names the report that documents it. The pairing rule is:

  > `report/<dataset-name>/`  ⟷  `results/<dataset-name>/`

  **If you run a new batch (e.g. `results/screening-batch2/`) you must create the paired
  `report/screening-batch2/` folder**, with a report carrying a `STATUS`
  banner (`AUTHORITATIVE`, `SUPERSEDED`, or `PENDING`) in its first five lines — and
  no more than one telemetry-completeness report may be `AUTHORITATIVE` at a time. Skip
  this and `tests/test_report_structure.py` (operation 2 above) fails. Cross-cutting
  investigations that are not dataset-scoped go under `report/findings/`. See the repo's
  `report/README.md` for the full convention.
- **Never fabricate telemetry.** Every usage field is either product-authoritative or
  explicitly `unavailable` — never `0`, never model-self-reported (CLAUDE.md rules 1–3).
- **Add a new benchmark subject** through the adapter contract, not by editing the
  runner: see `harness/adapters/README.md` → *Adding a benchmark subject*.
- **Author your own tasks / hidden tests:**
  [Sealed evaluation → *Authoring your own set (fork operators)*](sealed-evaluation.md).
- **Placeholder labels in permanent material** (Product A/B, STRONG_MODEL_A…); exact
  models/prices live only in `manifest/delivery-manifest.yaml` and `pricing/`
  (CLAUDE.md rule 7).

---

*Current as of `main` @ `369bde6`. This footer is refreshed whenever OPERATOR.md's
commands change — re-run the no-spend operations above and update the SHA if you edit
this file.*
