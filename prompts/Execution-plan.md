# EXECUTION PLAN — batch-1 publish + transfer probe, Tue 25 → Fri 28 Aug (SGT)

Goal by Friday: batch 1 signed and published, PLUS the transfer probe — lexha's two
winning routing strategies (r9, r6) calibrated on their own tasks, then run under your
human-gated oracle on W4 and W6, pre-registered, published either way — PLUS a clean
repo (old batches, plans and stale reports deleted; one plain index of every dataset)
and SPEC v3 stating the pivot's rules in plain language.

Dependency rules — do not jump ahead:
- SPEC v3 and the instrument PR must BOTH be merged before the probe launches (W4).
- The cleanup can merge any time Wednesday; the dashboard PR comes AFTER the cleanup
  (it builds on the cleaned report structure).
- The old rename task (report/batchN -> feasibility-batchN) is DEAD — deletion
  replaces renaming. Do not run it.
- Batch-1 sign-off (T4) happens BEFORE cleanup, spec rewrite, or any probe work merges.

Three lanes. YOU = human-only gates. CC = Claude Code. Parallel work uses **git
worktrees** — never two Claude Code sessions in one working tree (that already bit us
once).

```bash
# one-time setup for parallel lanes (run today):
cd ~/Developer-Agent-Tokenomics-Decision-Lab
git worktree add ../lab-docs main        # lane 2: rename + dashboard tasks
# main tree stays lane 1: instrument work + runs
```

**SYNC POINTS — stop and paste output to Claude (chat) before proceeding:**

| # | When | What you paste |
|---|---|---|
| S1 | Phase A sha mismatch, or any git surprise | the command output |
| S2 | Teammate replies, OR Wed 10:00 no-reply | their message / "no reply" |
| S3 | Prereg drafted, before freeze-commit | the prediction paragraphs |
| S4 | Instrument PR report arrives, before merge | the full CC report |
| S5 | **Calibration gate (HARD STOP)** | the calibration numbers |
| S6 | Probe finished | slot count + log tail |
| S7 | Thursday analysis numbers, before CP-TRANSFER sign | threshold, ranks, fab tax |
| S8 | Friday pre-publish (optional) | claims-walk result |

---

# TUESDAY

## T1 — Merge PR #36 + preconditions (YOU, 15 min)

Merge PR #36 on GitHub (use --merge). Then:

```bash
cd ~/Developer-Agent-Tokenomics-Decision-Lab
git checkout main && git fetch origin --prune && git reset --hard origin/main
git log --oneline -3
sha256sum report/findings/consolidated-table.json   # expect 6a0e7062…
ls results/screening-batch1-confound-makeup/*/quality-score.json | wc -l   # expect 8
```

Mismatch → **S1**.

## T2 — Teammate message (YOU, 15 min) — SEND FIRST, clock is running

> Hey — I've been reading tokenomics-benchmark-multi-llms closely. r9 is a genuinely
> strong result and I want to build on it rather than beside it. Proposal: I transplant
> r9 and r6 into my Decision Lab harness and test whether their wins survive a
> human-gated oracle — tasks where "solved" is a priced merge decision instead of a
> unit test, and where I've measured the cheap tier fabricating failure evidence.
> Calibrated on a BCB-Hard slice first so fidelity is provable; pre-registered before I
> run; published whichever way it lands, with your repo credited as the screening
> layer. Two asks: (1) the r9 gate verbatim — digest prompt, threshold, escalation
> rule — and r6's rung spec, so I'm testing your strategy and not my paraphrase of it;
> (2) separately, want to trade audits? My collector methodology can check whether
> $/solved figures are cache-aware — my data says cache-blind math overstates spend
> 50–168% — and I'd take the same scrutiny back. If this works we've got a joint
> "delegability map": your breadth where verification is free, my instrument where it
> isn't.

Fallback if no reply by **Wed 10:00**: CC extracts both specs from their public repo
(Task A below already does this); fidelity marked "best-effort pending author review."
Reply arrives later → verify extracted specs against it. Either way → **S2**.

## T3 — Stopwatch review (YOU, 90 min) — lane 1, solo, no Claude

File: `report/findings/stopwatch-review-2026-08-25.md` (note the date).

```bash
grep -rn "hourly\|rate\|usd_per\|review_cost" methodology/ SPEC.md manifest/delivery-manifest.yaml | grep -iv token | head
git checkout -b chore/stopwatch-review
nano report/findings/stopwatch-review-2026-08-25.md
```

Template:

```markdown
# Stopwatch review — HEAC human-review inputs
Reviewer: Catherine. Single sitting per artifact, timer running, no fixing.
Rate: <pinned or declared> USD/h. Limitation: reviewer not blind to gate verdicts.

| # | Artifact | Minutes | Decision (merge / request-changes / reject) | Notes, defects found |
|---|---|---|---|---|
```

Rules: read the public task README untimed → start timer → review as a contractor's PR
→ decide → stop timer. One sitting each. The five artifacts:

```bash
less results/screening-batch1/w4b-zarr-consolidated-order__P0__rep1__*/agent-solution.diff
less results/screening-batch1/w4b-zarr-consolidated-order__C2__rep1__*/agent-solution.diff
less results/screening-batch1-makeup/w3-sqlfluff-segment-method-migration__P0__rep2__*/agent-solution.diff
find results/screening-batch1-makeup-w6/w6-hono-router-review__P0__rep1__* -name '*report*' -o -name '*.diff' | xargs ls -la
grep -l 'fabricat' results/*/w6-hono-router-review__C2__rep*/quality-score.json
```

Artifact 5: review **cold** — do NOT look up which defect was fabricated. Record (a)
did you catch the invented defect unaided, (b) minutes spent disproving it. Those two
numbers feed the fabrication-tax figure AND the transfer prediction.

```bash
git add report/findings/stopwatch-review-2026-08-25.md
git commit -m "findings: stopwatch review — HEAC inputs (5 artifacts)"
git push -u origin chore/stopwatch-review
```

PR → merge.

## T4 — CP-FINDINGS sign-off (YOU, 45 min)

```bash
git checkout main && git fetch origin && git reset --hard origin/main
git checkout -b chore/cp-findings-signoff
nano manifest/cp-findings.md
```

Edits C1–C8 exactly as previously specified (sha `6a0e7062…` / `2026-08-23T10:56:01Z` /
`afcf79c`; §6.1 below-band verdict table; F-5; B-9 restatement with
"source not identified"; B-6 += stopwatch file ref with the 08-25 date; run_budget
limitation line; tick B-1…B-12 — actually walk B-7's claims map; status → APPROVED;
sign-off block). Commit, push, PR, merge. **Batch 1 is now signed. The probe never
touches it.**

## T5 — Write + freeze the prereg (YOU, 60 min) — after S2/S3

`manifest/preregistrations/2026-08-25-transfer-probe.md`:

```markdown
# Transfer probe — do benchmark-winning routing strategies survive a priced oracle?
**Registered:** 2026-08-25, before any probe instrument work merged. Human-authored.

**Transplant set:** r9 (escalate-on-evidence, their recommended default) and r6
(opus-after-ladder, their accuracy champion), specs frozen verbatim from
lexha-redstone/tokenomics-benchmark-multi-llms @ <commit-sha>, spec files hashed in
harness/policies/transfer/. Anchors already measured: P0 = their r0b (claude-opus-5,
exact match); C2 ≈ their r0a (sonnet version differs: 4.6 here vs 5 there — anchor is
approximate and labeled so).

**Targets and predictions (frozen):**
- W4 (bugfix): transfer HOLDS. The ladder collapses to its cheapest passing rung
  (Flash-Med passes 3/3 here); both strategies ≈ cheap-solo cost at equal acceptance.
- W6 (review): transfer BREAKS, by mechanism: transplanted strategies can only route
  on runtime-visible signals, and on W6 those signals systematically pass work the
  sealed gate rejects (measured: C2 rep1 public_gate=pass, result=rejected). r6's
  failure-count gate under-fires; r9's digest consumes model-generated evidence that
  this task fabricates (measured: 3–5 invented defects per cheap-tier cell).
- Escalation break-even, registered: escalation beats expensive-solo iff
  p_cheap > C_cheap/C_exp. On W6: threshold 44%, observed Sonnet p = 33% →
  predicted narrow loss on model-cost alone, widening under HEAC.

**Calibration criterion (gate, run before any transplant):** each reimplemented
strategy runs a 5-task BigCodeBench-Hard slice under the unit-test oracle and must
match the published per-task pass/fail on ≥4 of 5 AND land within ±30% of published
arm cost. Fail → stop; fidelity finding published instead.

**Graded question:** rank preservation — does the source leaderboard's ordering of
{r9, r6, r0a, r0b} on acceptance and $/accepted survive the oracle change, per task?
**HEAC computed for every arm** from stopwatch minutes at the declared rate.
**Scope:** n=3 reps → categorical claims only (acceptance flips, rank inversions,
fabrication counts, HEAC-order reversals). No effect-size claims.
**Result published either way.** Run-to-completion budgets: overrun warns, never
kills, except a 3× hard safety ceiling.
```

→ **S3** (paste predictions), then commit on branch `prereg/transfer-probe`, PR, merge.
The prereg merges **before** the instrument PR — that ordering is the point.

## T6 — Instrument prompt (CC, evening; lane 1) — after T5 merges

Save as `prompts/transfer-probe-instrument.md`, commit on a branch, PR, merge, then in
tmux (`tmux attach -t token`):

```
Read prompts/transfer-probe-instrument.md and execute it on branch
feat/transfer-probe-instrument. Commit, push, open a PR, do not merge.
No spend, no agent runs, do not touch results/ or manifest/. Stop and report.
```

Contents of `prompts/transfer-probe-instrument.md`:

```markdown
# Transfer-probe instrument. No spend. No agent runs. results/ and manifest/ read-only.

Prereg (authoritative for scope): manifest/preregistrations/2026-08-25-transfer-probe.md

Tasks A and B are independent — run them as parallel subagents; C–F sequential after.

## A. Freeze the strategy specs (network: raw.githubusercontent.com allowed)
From lexha-redstone/tokenomics-benchmark-multi-llms at its current HEAD (record the
commit sha): extract r9's gate (digest prompt, threshold, escalation rule) and r6's
rung ladder (rung order, failure-count trigger) VERBATIM into
harness/policies/transfer/r9-spec.yaml and r6-spec.yaml. Each spec records: source
repo+sha, source file paths, sha256 of extracted content, and every judgment call you
had to make (list them; zero is suspicious). Do not paraphrase prompts. Their solo
baselines r0a/r0b map to our C2/P0 — record the model-version mismatch on r0a.

## B. Timeout parity re-pin + run-to-completion (probe profile ONLY)
New driver profile `transfer-probe`: per-task --print-timeout = the task's
agent_timeout_s (adapter requires print < kill; move both). Batch-1 pins untouched.
Budgets warn-don't-kill: at task budget emit overrun_flag + warning and continue;
hard kill only at 3x budget (safety). Stamp overrun_s in the run record. This is a
NEW ARM condition; the dataset marker must say so.

## C. Strategy adapters
harness/adapters/transfer_r9.py and transfer_r6.py, driven ONLY by the spec yamls
(no strategy logic hardcoded). Legs use existing claude_code.py / agy.py adapters —
JSON usage capture is live, so every leg reports product-side usage; the provider-side
collector still runs as cross-check. Emit routing events: per attempt, which rung/gate
fired, the gate's input evidence (verbatim), and the decision. frontier_token_share
computed per run.

## D. Calibration path
A runner that executes a strategy over a 5-task BigCodeBench-Hard slice (their public
jsonl, tasks pinned by id in the spec dir) under the unit-test oracle, into dataset
results/transfer-probe-calibration. Grading = their oracle, cost = our costing. Output
a calibration report: per-task pass/fail vs their published rows, arm cost vs theirs,
PASS/FAIL against the prereg criterion.

## E. Probe driver plan
Dataset results/transfer-probe. Cells: W6 x {r9, r6} x rep1-3; W4 x {r9, r6} x rep1-3;
W4 x {C3, C3-med} x rep1-3 (exact-cost model-tier replication under the fixed
adapter). 18 runs. Spend cap $100. Print the two launch commands (calibration, probe)
verbatim; do not launch.

## F. Tests + report
Tests for spec loading, gate logic (fixture evidence -> expected route), overrun
stamping, calibration grading. bash tests/run-tests.sh green. Report format:
SPECS / REPIN / ADAPTERS / CALIB-PATH / PLAN / LAUNCH-CMDS / TESTS / JUDGMENT-CALLS /
SURPRISES. If anything here contradicts the repo or the prereg, stop and say so.
```

When its report arrives → **S4** (paste it). Review the spec yamls against lexha's
source yourself before merging — that's your fidelity gate, not CC's.

## T7 — SPEC v3 draft (CC, evening; lane 2, PARALLEL with T6) — after T4 signs

Runs at the same time as T6 because it's in the OTHER tree. Open a second tmux window:

```bash
tmux new-window -t token -n spec
cd ~/Developer-Agent-Tokenomics-Decision-Lab/../lab-docs && claude   # the worktree from setup — separate tree
```

Prompt:

```
Draft SPEC v3 + methodology update on branch spec/v3-pivot. No spend, no agent runs.
Rewrite SPEC.md and methodology/ to state the lab's current purpose in plain
language: (1) benchmarks rank routing strategies where checking is free and
instant; this lab tests whether those rankings survive tasks where "done" is a
paid human merge decision; (2) new run rules from the pivot — per-task fair time
limits for all models, runs finish with an overrun warning instead of being
killed (hard stop only at 3x budget), usage read from the product's JSON output,
human review minutes priced into cost per accepted outcome. Add one "Versions"
section: v2.2 governed the batch-1 measurements (frozen in git history; tag
pre-cleanup-2026-08-26 marks that tree once the cleanup PR lands); v3 governs
everything from the transfer probe onward. Plain language throughout — a new
engineer must understand every section without asking. Do not touch manifest/,
results/, or report/. This is a DRAFT for human approval: commit, push, open a
PR, do not merge, stop and report.
```

You review it Wednesday morning (W1). The spec is your document — CC drafts, you decide.

---

# WEDNESDAY

## W1 — Morning merges, in this order (YOU, ~2 h)

1. **SPEC v3 PR** — read the whole draft as its owner; edit wording on the branch if
   needed, then merge. This must land before any probe run exists, so the probe is
   governed by written rules, not intentions.
2. **Instrument PR** — after S4. Check: spec verbatim-ness against lexha's source,
   judgment-call list, re-pin scoped to the probe profile only, overrun logic,
   batch-1 pins untouched. Merge.

**The probe may not launch until BOTH are merged.**

## W2 — CP-SPEND note + launch calibration (YOU, 15 min)
`manifest/cp-spend-transfer-probe.md`: ~30 runs total (12 calibration + 18 probe),
cap $100, purpose = prereg ref. Commit to main via quick PR. Then run the CALIBRATION
launch command from the S4 report, in tmux lane 1. Monitor:

```bash
LOG="$(ls -t results/transfer-probe-calibration/*.log | head -1)"
grep -E '\[[0-9]+/' "$LOG" | tail -5
```

## W3 — CALIBRATION GATE (YOU) → **S5, HARD STOP**
Paste the calibration report to chat. Criterion: ≥4/5 pass-match per arm AND cost
within ±30%. PASS → W4. FAIL → do not transplant; the fidelity finding is Thursday's
deliverable instead, and W4/W6 transplant cells are cut.

## W4 — Launch the probe (YOU, 5 min)
Run the PROBE launch command from S4, tmux lane 1. ~18 runs; W6 at 1200s + spacing;
done same day. Keep tmux attached or confirm keepalive.

## W5 — PARALLEL, lane 2 (CC in ../lab-docs worktree, while probe runs)
Session 2 of Claude Code in `../lab-docs` — a different tree, so no collision.
**The old rename task is dead — deletion replaces renaming.** Two tasks, in order.

### W5a — Repo cleanup (CC, then YOU review+merge)

```
Repo cleanup, on branch chore/repo-cleanup. No spend, no agent runs.
1. Tag first so everything stays recoverable in history:
   git tag pre-cleanup-2026-08-26 && git push origin pre-cleanup-2026-08-26
2. DELETE: plans/ entirely; report/batch1, report/batch2-quick, report/batch3;
   every results/ dataset that is NOT one of the four screening-batch1* datasets.
   git rm, not archive.
3. Fix every reference the deletions break — search the whole repo including
   harness/, manifest/, tests/, docs/, results/README.md. Zero broken paths
   afterward; prove with grep.
4. Write report/README.md as one plain index table: each of the four datasets —
   name, one-line description, run count, and which report its numbers feed.
   Top line, plain words: "122 planned boxes, 153 runs bought, 117 filled,
   5 empty with reasons stated below."
5. Do NOT touch: results/screening-batch1*, report/screening-batch1*,
   report/findings/, manifest/, SPEC.md, methodology/.
6. bash tests/run-tests.sh and mkdocs build --strict must both pass.
Commit, push, open a PR, do not merge. Report what was deleted and the grep proof.
Stop.
```

Your review checklist for this PR: (a) the tag exists on origin BEFORE any deletion
commit; (b) nothing under the four screening datasets or report/findings moved;
(c) read the new report/README.md index **as a newcomer would** — this table is the
fix for "which run goes with which report," so judge it on that; (d) the grep proof
shows zero broken paths. Merge.

Note: B-10's "52 published receipts" count refers to the tree at sign-off; one of
those files lives in a deleted feasibility dataset and remains in history and the tag.
No checkpoint edit needed — the sign-off describes the state it was signed under.

### W5b — Dashboard (CC, AFTER W5a merges; then YOU review+merge)

Dashboard prompt (ONE amendment from the original): wire to
report/findings/consolidated-table.json but **display the table's own embedded sha256
and generated_at fields — do not hardcode them** (Friday's table has a new sha). All
other hard rules unchanged: three views never share a chart; tiers + scope lines on
every figure; ≤ renders as ≤; unavailable renders its reason; no figure not in the
table; list every displayed number beside its source cell. mkdocs build --strict
passes against the CLEANED tree. Branch feat/dashboard-live; PR; no merge.

Review the number-to-cell listing against the table. Merge.

---

# THURSDAY

## Th1 — Probe finished check (YOU, 10 min) → **S6**
```bash
ls -d results/transfer-probe/*/ | wc -l    # expect 18 (or the S5-adjusted count)
LOG="$(ls -t results/transfer-probe/*.log | head -1)"
grep -E 'execution finished|overrun|spend floor|unavailable' "$LOG" | tail -8
```
Paste to chat. Overruns are results, not failures — check they're stamped.

## Th2 — Grade + consolidate (CC, lane 1)
```
Grade the transfer-probe dataset: run the standard gates and quality extraction over
results/transfer-probe (offline, no model calls), then consolidate it as ITS OWN
dataset — it supersedes nothing and pools with nothing. Regenerate
report/findings/consolidated-table.* over ALL datasets including transfer-probe and
transfer-probe-calibration; every existing batch-1 figure must be numerically
unchanged (diff and prove it). Grade the transfer prereg: rank preservation of
{r9, r6, r0a-approx, r0b} per task on acceptance and $/accepted; break-even check
against the registered 44%. Emit per-run routing traces (which gate fired, on what
evidence) into report/findings/transfer-routing-traces.md. Branch
feat/transfer-consolidation; PR; no merge. Report: RANKS per task / BREAK-EVEN /
OVERRUNS / FAB-TAX inputs / calibration cross-ref / TESTS. Stop.
```

## Th3 — Stopwatch the probe artifacts (YOU, ~60 min)
Same protocol, new file `stopwatch-review-transfer-2026-08-27.md`: one accepted and
one rejected artifact per strategy per task (≈6), cold, timed. These minutes are the
HEAC inputs their repo structurally cannot produce about its own strategies.

## Th4 — The three numbers (YOU + CC assist)
1. **Review-rate threshold:** solve, from W6 cells + your minutes, for the reviewer
   $/h at which cheap-retry flips from winning to losing on $/accepted-with-review.
   One sentence: "above $X/h, the cheap tier is the expensive tier."
2. **Fabrication tax:** invented defects per accepted outcome per arm × your measured
   minutes-to-disprove (T3 artifact 5 + Th3).
3. **Rank-preservation verdict** per task, with delta decomposition: task difficulty
   vs oracle type vs review cost — attribute what traces, name what's confounded.

## Th5 — TRANSFER-PROTOCOL.md + CP-TRANSFER (YOU, 45 min) → **S7 first**
Paste the Th4 numbers to chat, then write both docs: the protocol (freeze → calibrate
→ pre-register → run → decompose → zone verdict) and a short CP-TRANSFER checkpoint
(inputs, prereg graded, blockers: calibration gate passed, batch-1 unchanged, traces
published, HEAC recorded). Sign. PR, merge.

---

# FRIDAY

## F1 — Final table + claims walk (YOU, 45 min)
Merge Th2's PR if not done. Claims walk on the full register (F-1…F-8 + the transfer
claims added at Th5): every displayed figure ↔ a register row, both directions.

## F2 — Dashboard re-point check (YOU, 15 min)
It reads the table's embedded sha, so it self-updates. `mkdocs build --strict`; read
the rendered page once, top to bottom, and open report/README.md — the dataset index
must read cleanly to a newcomer. Front page order: zone map → green-zone price
list (Sonnet 34–60% exact; Flash-Med ≥20% on W4) → review-rate threshold →
fabrication tax → transfer verdicts (whichever way) → frontier price list →
collaboration note crediting their repo as the screening layer.

## F3 — CP-PUBLISH (YOU, 45 min)
Flip PENDING per procedure, sign, deploy Pages, post — jointly with your teammate if
S2 landed warm. Strip any number not in the register from the post. → **S8** optional.

---

# PRE-COMMITTED CUTS (decide nothing on Thursday night)
Probe slip order: (1) W4 transplants, (2) the C3/C3-med exact-cost replication,
(3) r6 (keep r9 — it's the recommended default and the sharper prediction).
Side-work slip order: the dashboard can slip past Friday (publish renders from the
table without it); the CLEANUP and SPEC v3 do NOT slip — the clean repo and the
plain-language spec are part of what Friday ships.
**Hard floor: batch 1 publishes Friday regardless** — it was signed Tuesday and owes
the probe nothing. Calibration-gate FAIL converts the week's routing chapter into a
fidelity finding, which also publishes.
