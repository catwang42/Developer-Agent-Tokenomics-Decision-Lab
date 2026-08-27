# RUNBOOK — tonight + Wednesday. Every command, every prompt, every check.

You are here: stopwatch review DONE and merged. Adjudication DONE and merged.
CP-FINDINGS not signed yet (that's fine — it no longer blocks the runs).

Order of everything left, and why: freeze the prereg (blocks instrument) → hand
Claude Code the instrument (blocks launch) → sleep → Wednesday: merge, launch,
sign CP-FINDINGS while runs execute, cleanup + spec + dashboard in the other lane.

---

# TONIGHT — ~40 minutes of your time

## STEP 1 — Freeze the prereg (YOU, 15 min)

### 1a. Get lexha's current commit sha (you need it for the file):

```bash
git ls-remote https://github.com/lexha-redstone/tokenomics-benchmark-multi-llms refs/heads/main
```

Copy the 40-character sha.

### 1b. Create the file:

```bash
cd ~/Developer-Agent-Tokenomics-Decision-Lab
git checkout main && git fetch origin && git reset --hard origin/main
git checkout -b prereg/transfer-probe
nano manifest/preregistrations/2026-08-26-transfer-probe.md
```

Paste the prereg file I gave you (`2026-08-26-transfer-probe.md`). Replace
`<commit-sha>` with the sha from 1a. Save.

### 1c. Read it once as its author. You are signing predictions. If you disagree
with any prediction, change it NOW — after this commit it is frozen.

### 1d. Commit, push, PR, merge:

```bash
git add manifest/preregistrations/2026-08-26-transfer-probe.md
git commit -m "prereg: transfer probe — r9/r6/r10 under a priced oracle, predictions frozen"
git push -u origin prereg/transfer-probe
gh pr create --base main --head prereg/transfer-probe \
  --title "prereg: transfer probe (frozen before instrument work)" \
  --body "Predictions frozen before any probe instrument merges. r9/r6/r10 + anchors."
gh pr merge --merge
```

If `gh pr merge` complains, merge in the browser. Verify:

```bash
git ls-remote origin refs/heads/main   # note the new sha
```

## STEP 2 — Commit the instrument prompt (YOU, 5 min)

```bash
git checkout main && git fetch origin && git reset --hard origin/main
git checkout -b prompts/transfer-instrument
nano prompts/transfer-probe-instrument.md
```

Paste EXACTLY this into the file:

```markdown
# Transfer-probe instrument. No spend. No agent runs. results/ and manifest/ read-only.

Prereg (authoritative for scope): manifest/preregistrations/2026-08-26-transfer-probe.md
Read it first. If anything below contradicts it, the prereg wins — stop and say so.

Tasks A and B are independent — run them as parallel subagents; C–F sequential after.

## A. Freeze the strategy specs (network: raw.githubusercontent.com allowed)
From lexha-redstone/tokenomics-benchmark-multi-llms at the commit sha named in the
prereg: extract THREE strategies verbatim into harness/policies/transfer/:
  r9-spec.yaml  — escalate-on-evidence: digest prompt, threshold, escalation rule
  r6-spec.yaml  — opus-after-ladder: rung order, failure-count trigger
  r10-spec.yaml — opus-fresh-solve: discard rule, what (if anything) carries over
Each spec records: source repo+sha, source file paths, sha256 of extracted content,
and every judgment call you had to make (list them; zero is suspicious). Do not
paraphrase prompts. Their solo baselines r0a/r0b map to our C2/P0 — record the
model-version mismatch on r0a (sonnet 4.6 here vs 5 there).

## B. Timeout parity re-pin + run-to-completion (probe profile ONLY)
New driver profile `transfer-probe`: per-task --print-timeout = the task's
agent_timeout_s (adapter requires print < kill; move both together). Batch-1 pins
untouched. Budgets warn-don't-kill: at task budget emit overrun_flag + warning and
continue; hard kill only at 3x budget (safety). Stamp overrun_s in the run record.
This is a NEW ARM condition; the dataset marker must say so.

## C. Strategy adapters
harness/adapters/transfer_r9.py, transfer_r6.py, transfer_r10.py, driven ONLY by
the spec yamls (no strategy logic hardcoded). Legs use existing claude_code.py /
agy.py adapters — JSON usage capture is live, so every leg reports product-side
usage; the provider-side collector still runs as cross-check. Emit routing events:
per attempt, which rung/gate fired, the gate's input evidence (verbatim), and the
decision. frontier_token_share computed per run.

## D. Calibration path — the gate is AUTOMATIC
A runner that executes a strategy over a 5-task BigCodeBench-Hard slice (their
public task jsonl, the 5 task ids pinned in the spec dir) under the source's own
unit-test oracle, into dataset results/transfer-probe-calibration. Grading = their
oracle, cost = our costing. It then evaluates the prereg criterion ITSELF —
per-task pass/fail match on >=4 of 5 AND arm cost within +-30% of published — and
exits non-zero on failure, writing a calibration report either way. The probe
driver (E) must refuse to start unless a passing calibration report exists for
EVERY strategy.

## E. Probe driver plan
Dataset results/transfer-probe. Cells:
  W6 x {r9, r6, r10} x rep1-3   (9 runs)
  W4 x {r9, r6, r10} x rep1-3   (9 runs)
  W4 x {C3, C3-med} x rep1-3    (6 runs — exact-cost model-tier replication under
                                  the fixed adapter)
24 runs. Spend cap $120. Print the two launch commands (calibration, then probe)
verbatim; do not launch either.

## F. Tests + report
Tests for: spec loading; each gate's logic (fixture evidence -> expected route,
including a fixture where the cheap report is fluent but wrong — r9 must NOT
escalate on it, that is the point); overrun stamping; calibration criterion
evaluation. bash tests/run-tests.sh green. Report format:
SPECS / REPIN / ADAPTERS / CALIB-PATH / PLAN / LAUNCH-CMDS / TESTS /
JUDGMENT-CALLS / SURPRISES. Stop after reporting. Do not merge, do not launch.
```

```bash
git add prompts/transfer-probe-instrument.md
git commit -m "prompts: transfer-probe instrument (r9/r6/r10, auto calibration gate)"
git push -u origin prompts/transfer-instrument
gh pr create --base main --head prompts/transfer-instrument --title "prompts: transfer-probe instrument" --body "Instrument build instruction; prereg already frozen."
gh pr merge --merge
```

## STEP 3 — Hand it to Claude Code (YOU, 2 min; CC runs 1–2 h unattended)

```bash
git checkout main && git fetch origin && git reset --hard origin/main
tmux attach -t token
```

Paste into the Claude Code session:

```
Read prompts/transfer-probe-instrument.md and execute it on branch
feat/transfer-probe-instrument. Commit, push, open a PR, do not merge.
No spend, no agent runs, do not touch results/ or manifest/.
Stop and report in the file's format.
```

Detach: Ctrl-B then D. Go to bed. It will be waiting with a report in the morning.

---

# WEDNESDAY

## STEP 4 — Review + merge the instrument PR (YOU, 45–60 min)

Read the report in tmux first, then the PR diff. Your checklist:

1. Open each spec yaml side-by-side with lexha's source file (the yaml names its
   source paths). The prompts must be VERBATIM. Paraphrase = do not merge.
2. Read the JUDGMENT-CALLS list. Zero entries is suspicious; each entry should be
   small and defensible.
3. Confirm the re-pin and warn-don't-kill exist only in the `transfer-probe`
   profile — batch-1 pins untouched:
   grep -rn "print_timeout\|overrun" scripts/ harness/ | grep -v transfer | head
4. Confirm the probe driver actually checks for calibration reports before running.
5. Tests green in the report.

Merge on GitHub. Then paste me the report (S4) — I'll flag anything you should
re-check, but do not wait for me if it all reads clean.

## STEP 5 — Spend note + LAUNCH calibration (YOU, 10 min)

```bash
git checkout main && git fetch origin && git reset --hard origin/main
git checkout -b docs/cp-spend-transfer
nano manifest/cp-spend-transfer-probe.md
```

Paste:

```markdown
# CP-SPEND — transfer probe
Approved: 2026-08-27, Catherine. Cap: $120. ~30 runs: 15 calibration
(3 strategies x 5 BigCodeBench-Hard tasks) + 24 probe cells per
manifest/preregistrations/2026-08-26-transfer-probe.md. Purpose: pre-registered
transfer test of benchmark-winning routing strategies under a priced oracle.
```

```bash
git add manifest/cp-spend-transfer-probe.md
git commit -m "cp-spend: transfer probe, cap \$120"
git push -u origin docs/cp-spend-transfer
gh pr create --base main --head docs/cp-spend-transfer --title "cp-spend: transfer probe" --body "Cap \$120, prereg-scoped."
gh pr merge --merge
git checkout main && git fetch origin && git reset --hard origin/main
```

Then, in tmux, run the CALIBRATION launch command **from the instrument report**
(copy it exactly — do not type it from memory). Monitor:

```bash
LOG="$(ls -t results/transfer-probe-calibration/*.log | head -1)"
tail -f "$LOG"          # Ctrl-C to stop watching; the run continues
```

Calibration is short (their tasks are minutes each). The runner grades itself:
exit 0 = gate passed. If it FAILS: **stop, do not launch the probe** — paste me
the calibration report (S5). The fidelity finding becomes the deliverable.

## STEP 6 — LAUNCH the probe (YOU, 2 min, only after calibration passes)

In tmux, run the PROBE launch command from the instrument report. Verify it's
alive, then leave it:

```bash
LOG="$(ls -t results/transfer-probe/*.log | head -1)"
grep -E '\[[0-9]+/24\]' "$LOG" | tail -3
```

W6 runs are ~20 min each, W4 shorter; with spacing expect it to finish in the
evening. The tmux session keeps it alive if your SSH drops.

## STEP 7 — Sign CP-FINDINGS while it runs (YOU, 45 min)

```bash
git checkout main && git fetch origin && git reset --hard origin/main
git checkout -b chore/cp-findings-signoff
```

### 7a. First, have Claude Code produce the claims-walk evidence (read-only).
Open a SECOND tmux window (Ctrl-B then C), and in the ../lab-docs worktree:

```bash
cd ~/Developer-Agent-Tokenomics-Decision-Lab/../lab-docs && git checkout main && git pull && claude
```

Paste:

```
Read-only verification for the CP-FINDINGS claims walk. Do not edit any file.
For manifest/cp-findings.md's claims register (F-1..F-8) and
report/findings/consolidated-table.md: list every claim and the specific figures
in the table that license it, then every figure category in the table and which
claim covers it. Report orphans in both directions. Markdown table to stdout
only. Stop.
```

### 7b. While that runs, edit the doc in window 1:

```bash
nano manifest/cp-findings.md
```

Make these edits, top to bottom:

1. §2: sha256 -> 6a0e706260b2e8c49ed34bfd1f12bf63975ff248ac8c260f3c040e6277d6990b,
   generated-at -> 2026-08-23T10:56:01Z, harness -> afcf79c.
2. §6.1: replace verdict table + following paragraph with the below-band version
   (parity holds; 13.7% / 28.0%; ratio-of-bounds caveat; sign robust; n=2 tasks).
3. Claims register: F-5 row -> "Effort-level reduction is real but materially
   smaller than the registered expectation (13.7% / 28.0% vs 30-50%)".
4. §7, after the timeout-parity paragraph, ADD:

   **Human review disagreed with the sealed gate (B-13).** A blind stopwatch
   review of five artifacts (report/findings/stopwatch-review-2026-08-26.md)
   reached a different conclusion from the sealed gate on four of five.
   Adjudication of the two contested W6 claims resolved both against the sealed
   artifacts: the accepted cell's contested finding exposed a miswritten note in
   the sealed defect map (D2), and the rejected C2 report identified a real
   seeded defect 22 lines off, scoring as both MISSED and FABRICATED — the FAIL
   turns on that offset alone. The gradient in this section is therefore the
   sealed gate's verdict under a +-3-line proximity scorer, reported as such; it
   is not a merge-readiness result, and "fabricated" throughout this batch means
   an off-map report, not a false claim.

5. B-6: add "Recorded in report/findings/stopwatch-review-2026-08-26.md."
6. B-9: restate — shared project, four enabled schedulers, two live workstations,
   20.7M third-party tokens in-window, source not identified;
   agy-agent-catalog-refresh is not a Cloud Scheduler job in this project.
7. Limitation ledger: add the run_budget line (empty in every archived run;
   per-slot uniqueness verified directly; batch-2 fix).
8. ADD blocker:
   - [x] **B-13.** Contested W6 claims adjudicated 2026-08-26; both resolved
     against the sealed artifacts (D2 note miswritten; C2 fail turns on a
     22-line offset). Recorded in the stopwatch review file; W6 quality figures
     carry the off-map-report language and the D2 note is queued for a sealed-map
     correction in the next reseal.
9. Tick B-1..B-12 against their evidence. For B-7, use the claims-walk table from
   7a — fix any orphan it found before ticking.
10. Status -> **Status: APPROVED.** Fill the sign-off block: name, date, the sha
    from edit 1.

### 7c. Commit, PR, merge:

```bash
git add manifest/cp-findings.md
git commit -m "cp-findings: sign-off — H-effort below band, B-13 adjudicated, B-1..B-13 ticked"
git push -u origin chore/cp-findings-signoff
gh pr create --base main --head chore/cp-findings-signoff --title "cp-findings: APPROVED" --body "Batch-1 sign-off."
gh pr merge --merge
```

**Batch 1 is signed.**

## STEP 8 — Lane 2 while the probe runs (CC in ../lab-docs)

In the window-2 Claude Code session, after 7a's output is saved:

First the CLEANUP prompt (from your execution plan W5a — the one that tags
pre-cleanup, deletes plans/ + old batches, writes the report/README.md index).
Review its PR with the four-point checklist in the plan. Merge.

Then the SPEC v3 prompt (from your plan T7). Read the draft fully — it's your
document. Merge.

Then the DASHBOARD prompt (plan W5b — embedded-sha version). Review the
number-to-cell listing. Merge.

If time runs short, the dashboard is the one that slips. Cleanup and SPEC v3
do not slip.

## STEP 9 — End of day check (YOU, 5 min) -> paste me (S6)

```bash
ls -d results/transfer-probe/*/ | wc -l
LOG="$(ls -t results/transfer-probe/*.log | head -1)"
grep -E 'execution finished|overrun|spend floor' "$LOG" | tail -6
```

Thursday is grading + the three numbers + TRANSFER-PROTOCOL.md. Friday publishes.
