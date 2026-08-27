# MASTER PLAN — final. Supersedes every earlier plan file.

Replace both files on `doc-escalation-run` with this one
(`prompts/MASTER-PLAN.md`). One document, one sequence, three outcomes:

1. **One table** — new r9/r6/r10 runs consolidated with all 42 existing cells,
   plus one plain-language report (`report/FINDINGS.md`).
2. **Clean repo** — old batches, plans and junk deleted; matching names between
   every results/ dataset and its report/ folder; one index.
3. **Dashboard** — renders the final table so a newcomer sees the result.

## Where you are (verified against main)

DONE: PR #36 merged (table on main) · stopwatch review + adjudication merged ·
teammate confirmed r9/r6/r10.
NOT DONE: prereg · instrument · 27 runs · repo cleanup · CP-FINDINGS sign-off ·
one-table consolidation + FINDINGS.md · dashboard.
SLIPPED TO WEEKEND (deliberate): SPEC v3.

Two Claude Code lanes, never in the same tree:
- **Lane 1** = main tree, tmux session `token` → instrument, runs, consolidation
- **Lane 2** = `../lab-docs` worktree, tmux window `spec` → cleanup, dashboard

---

# TONIGHT (Thu) — your time ≈ 35 min, then both lanes work overnight

## N1 — Prereg freeze (YOU, 10 min)

```bash
cd ~/Developer-Agent-Tokenomics-Decision-Lab
git checkout main && git fetch origin --prune && git reset --hard origin/main
git checkout -b prereg/transfer-probe
nano manifest/preregistrations/2026-08-27-transfer-probe.md
# paste 2026-08-27-transfer-probe-FINAL.md (sha already baked in). Read the
# predictions once — they freeze on commit.
git add manifest/preregistrations/2026-08-27-transfer-probe.md
git commit -m "prereg: transfer probe — r9/r6/r10 on W6+W4b+W4, 27 cells, frozen"
git push -u origin prereg/transfer-probe
gh pr create --base main --head prereg/transfer-probe --title "prereg: transfer probe (frozen)" --body "Frozen before instrument work. W3 deferred."
gh pr merge --merge
```

## N2 — Spend note + instrument prompt into the repo (YOU, 10 min)

```bash
git checkout main && git fetch origin && git reset --hard origin/main
git checkout -b docs/transfer-setup
printf '%s\n' "# CP-SPEND — transfer probe" \
  "Approved 2026-08-27, Catherine. Cap: \$300 total (calibration + probe)." \
  "27 probe cells ({W6,W4b,W4} x {r9,r6,r10} x rep1-3) + ~15 calibration runs," \
  "per manifest/preregistrations/2026-08-27-transfer-probe.md." \
  "Run-to-completion budgets; overruns stamped; hard stop at 3x." \
  > manifest/cp-spend-transfer-probe.md
nano prompts/transfer-probe-instrument.md
# paste transfer-probe-instrument-FINAL.md (27-run task E, cap $300)
git add manifest/cp-spend-transfer-probe.md prompts/transfer-probe-instrument.md
git commit -m "cp-spend + prompt: transfer probe, 27 cells, cap \$300"
git push -u origin docs/transfer-setup
gh pr create --base main --head docs/transfer-setup --title "transfer probe: spend + instrument prompt" --body ""
gh pr merge --merge
git checkout main && git fetch origin && git reset --hard origin/main
```

## N3 — Lane 1: instrument build overnight (YOU 2 min)

```bash
tmux attach -t token
```

Paste into Claude Code:

```
Read prompts/transfer-probe-instrument.md and execute it on branch
feat/transfer-probe-instrument. Commit, push, open a PR, do not merge.
No spend, no agent runs, do not touch results/ or manifest/.
Stop and report in the file's format.
```

Ctrl-B then D.

## N4 — Lane 2: repo cleanup overnight (YOU 3 min)

```bash
tmux new-window -t token -n cleanup
cd ~/Developer-Agent-Tokenomics-Decision-Lab/../lab-docs && git checkout main && git pull && claude
```

Paste:

```
Repo cleanup, on branch chore/repo-cleanup. No spend, no agent runs.
1. Tag first: git tag pre-cleanup-2026-08-27 && git push origin pre-cleanup-2026-08-27
2. DELETE (git rm, not archive): plans/ entirely; report/batch1, report/batch2-quick,
   report/batch3; every results/ dataset that is NOT one of the four
   screening-batch1* datasets.
3. Fix every reference the deletions break — search the whole repo including
   harness/, manifest/, tests/, docs/, results/README.md. Zero broken paths; prove
   with grep.
4. Write report/README.md as one plain index table: each of the four datasets —
   name, one-line description, run count, which report its numbers feed. Top line:
   "122 planned boxes, 153 runs bought, 117 filled, 5 empty with reasons below."
   Note: transfer-probe datasets land Friday and will be added to this index.
5. Do NOT touch: results/screening-batch1*, report/screening-batch1*,
   report/findings/, manifest/, SPEC.md, methodology/.
6. bash tests/run-tests.sh and mkdocs build --strict must pass.
Commit, push, open a PR, do not merge. Report deletions + grep proof. Stop.
```

Ctrl-B then D. Sleep.

---

# FRIDAY MORNING — merge everything, launch (YOU ≈ 90 min)

## F1 — Merge the cleanup PR first (lane 2 output)
Checklist: tag `pre-cleanup-2026-08-27` on origin BEFORE any deletion commit; the
four screening datasets and report/findings untouched; read report/README.md as a
newcomer — it is the fix for "which run feeds which report"; grep proof clean.
Merge. Outcome 2 is now done except for Friday's dataset rows.

## F2 — Merge the instrument PR (lane 1 output)
Checklist: each spec yaml open side-by-side with lexha's source file — prompts
VERBATIM or no merge; JUDGMENT-CALLS list short and defensible; re-pin +
warn-don't-kill exist only in the `transfer-probe` profile
(`grep -rn "print_timeout\|overrun" scripts/ harness/ | grep -v transfer | head`
returns nothing new); probe driver refuses to start without calibration reports;
tests green. Merge. Paste me the report — do not wait on me if it reads clean.

## F3 — Calibration, then launch (YOU, 10 min)

```bash
git checkout main && git fetch origin && git reset --hard origin/main
tmux attach -t token
# run the CALIBRATION command from the instrument report, verbatim
```

The gate is automatic: exit 0 → continue. Non-zero → STOP, paste me the
calibration report; the fidelity finding becomes the deliverable and no probe runs.

Then run the PROBE command from the report, verbatim. Verify life and leave it:

```bash
LOG="$(ls -t results/transfer-probe/*.log | head -1)"
grep -E '\[[0-9]+/27\]' "$LOG" | tail -3
```

Run order is W4 → W6 → W4b; expect completion by evening. Ctrl-B, D.

## F4 — Sign CP-FINDINGS while the runs execute (YOU, 45 min)

First, lane 2 (read-only helper):

```
Read-only verification for the CP-FINDINGS claims walk. Do not edit any file.
For manifest/cp-findings.md's claims register (F-1..F-8) and
report/findings/consolidated-table.md: list every claim and the specific figures
that license it, then every figure category and which claim covers it. Report
orphans in both directions. Markdown table to stdout only. Stop.
```

Then in lane-1 tree, branch `chore/cp-findings-signoff`, edit
`manifest/cp-findings.md` — ten edits:

1. §2: sha256 `6a0e706260b2e8c49ed34bfd1f12bf63975ff248ac8c260f3c040e6277d6990b`,
   generated-at `2026-08-23T10:56:01Z`, harness `afcf79c`.
2. §6.1 → below-band verdict (parity holds; 13.7% / 28.0%; ratio-of-bounds caveat;
   sign robust; n=2 tasks).
3. F-5 → "Effort-level reduction is real but materially smaller than registered
   (13.7% / 28.0% vs 30–50%)".
4. §7, after timeout-parity, ADD the human-vs-gate paragraph:
   blind review disagreed with the sealed gate on 4 of 5; adjudication resolved
   both contested W6 claims against the sealed artifacts (D2 note miswritten;
   C2's FAIL turns on a 22-line offset scored as MISSED + FABRICATED); the
   gradient is a sealed-gate verdict under a ±3-line proximity scorer, not a
   merge-readiness result; "fabricated" in this batch means an off-map report.
5. B-6 += "Recorded in report/findings/stopwatch-review-2026-08-26.md."
6. B-9 restated: shared project, four enabled schedulers, two live workstations,
   20.7M third-party tokens in-window, source not identified;
   agy-agent-catalog-refresh is not a Cloud Scheduler job in this project.
7. Limitation ledger += run_budget line (empty in every archived run; per-slot
   uniqueness verified directly; batch-2 fix).
8. ADD B-13, ticked: contested claims adjudicated 2026-08-26, both resolved
   against the sealed artifacts; D2 note queued for correction at next reseal;
   W6 quality figures carry off-map language.
9. Tick B-1..B-12 against evidence; for B-7 use the claims-walk table and fix any
   orphan first.
10. Status → **Status: APPROVED.** Sign-off block: name, date, the §2 sha.

Commit, push, PR, merge. **Batch 1 signed.**

---

# FRIDAY EVENING — one table, one report, dashboard

## F5 — Confirm the probe finished (YOU, 2 min → paste me)

```bash
ls -d results/transfer-probe/*/ | wc -l          # expect 27
grep -E 'execution finished|overrun|spend floor' "$(ls -t results/transfer-probe/*.log | head -1)" | tail -6
```

## F6 — Consolidation: everything into ONE table + ONE report (lane 1 CC)

```
Close-out consolidation, branch feat/final-report. No spend, no agent runs.
1. Grade results/transfer-probe offline (standard gates + quality extraction);
   consolidate as its own dataset; regenerate report/findings/consolidated-table.*
   over ALL datasets including transfer-probe and transfer-probe-calibration.
   Every batch-1 figure numerically unchanged — diff and prove it. Add the new
   dataset rows to report/README.md's index.
2. Grade the transfer prereg on all three tasks: rank preservation of
   {r9, r6, r10, r0a≈C2, r0b=P0} on acceptance and cost-per-accepted for W6 and
   W4; the W4b cost-of-failure ordering (predicted r6 > r9 ≈ r10 at 0/3); the
   registered break-even; per-run routing traces (which gate fired, on what
   evidence, verbatim) into report/findings/transfer-routing-traces.md.
3. From report/findings/stopwatch-review-2026-08-26.md at the declared rate:
   cost per accepted outcome INCLUDING review minutes for every W6 arm; the
   reviewer hourly rate at which cheap-retry flips from winning to losing; the
   off-map-report tax (minutes to disprove per off-map claim). Show arithmetic.
4. Write ONE report at report/FINDINGS.md superseding the scattered ones:
   task zone map (green/yellow/red); green-zone exact savings (Sonnet 34–60%
   under Opus); H-effort below band; W6 gradient WITH off-map language and the
   B-13 adjudication; the 4-of-5 human-vs-gate disagreement as a headline
   finding; transfer verdicts on all three tasks whichever way they landed; the
   three step-3 numbers; limitations; claims register with every figure mapped
   to a table cell. Plain language — a new engineer understands every sentence.
   Existing findings files stay as receipts; FINDINGS.md links to them.
5. Tests green. PR, do not merge. Report: RANKS(W6/W4) / W4B-COST-ORDER /
   BREAK-EVEN / HEAC / OVERRUNS / diff-proof / SURPRISES. Stop.
6. Also reconcile the slot count: the table header says "117 of 122 slots" but
42 cells x 3 reps = 126 and the ledger accounts for 9 empty slots. Determine
which figure the code derives and correct the header (or the derivation) so the
table, its ledger, and report/README.md all agree. State in your report which
was wrong and why.
```

Review: the diff-proof (batch-1 unchanged), the three HEAC numbers' arithmetic,
and read FINDINGS.md top to bottom once. Merge. **Outcome 1 done.**

## F7 — Dashboard (lane 2 CC)

```
Point the dashboard from PR #17 at the final data. Check out PR #17's branch and
rebase onto main, or start feat/dashboard-live reusing its components if the
rebase is messy. Wire it to report/findings/consolidated-table.json, and display
the table's own embedded sha256 and generated_at fields — do not hardcode them.
Hard rules: the three comparison views (product-level, model-tier,
routing-policy) render separately and never share a chart, table, or ranking;
every figure carries its confidence tier and scope line; ≤ renders as ≤;
unavailable renders its reason and is never a zero or a blank; no figure appears
that is not in the table; link report/FINDINGS.md as the front page's "read the
findings" target. Verify by listing every displayed number beside its source
cell. mkdocs build --strict passes. Branch, commit, push, PR, do not merge. Stop.
```

Review the number-to-cell listing against the table. Merge. **Outcome 3 done.**
If the evening runs long, F7 alone may slip to Saturday morning — it renders
data that is already final.

---

# CUT LADDER (pre-decided; do not renegotiate at 9pm)
1. W4 transplant cells (prereg marks them gradable-if-run)
2. r6 on all tasks (keep r9 + r10 — the mechanism gradient)
3. Dashboard → Saturday morning
NEVER cut: calibration gate, W6 r9/r10, W4b cost-of-failure, CP-FINDINGS
sign-off, the F6 one-table + FINDINGS.md step.

# SYNC POINTS → paste to Claude (chat)
S-A instrument report (F2, before merge if anything reads odd)
S-B calibration report ONLY if the gate fails
S-C F5 output when the probe finishes
S-D F6 report before you merge the final PR
