# Screening batch 1 — spend package (CP-SPEND)

CP-SPEND package for the **132-run screening batch 1** registered in
`manifest/cp-screen-prereg.md` (CLAUDE.md rule 5; SPEC §2.3, §5). **Approving this
checkpoint authorizes the spend in §3 under the §4 kill-switches and nothing else;
nothing runs before the human writes `CHECKPOINT APPROVED: CP-SPEND (screening
batch 1)`.**

**Status: APPROVABLE.** All four §6 blockers are cleared as of 2026-08-17: the sealed
artifacts are frozen (PR #19), the quiet window measures quiet, the isolation posture
was fixed and re-smoked, and the task declarations match the registered matrix.
CP-SCREEN-PREREG's mechanical gate — the driver's preflight 3 — now passes, and the
full `--dry-run` clears all nine preflight gates and completes 126/126 stub runs at
exit 0 (§8). Prepared 2026-08-17 on branch `feat/screening-launch`; refreshed
2026-08-17 on `docs/cp-spend-refresh`. Spend in preparing it: **$0.79**, under the
separately approved $5 smoke cap; refreshing it cost **$0**.

**Approving this package remains the only thing between the repo and a live batch:**
preflight 2 refuses without `LAB_ALLOW_SPEND=1`, and that variable is set by a human
after writing `CHECKPOINT APPROVED: CP-SPEND (screening batch 1)`.

**Package contents (CLAUDE.md CP-SPEND gate = budget + configs + manifest):**
- Budget & kill-switches: §3–§4 (ceiling **$75**, `--spend-cap-usd 75`).
- Run matrix: `manifest/cp-screen-prereg.md` §4 — 132 runs (126 without optional P2).
- Configs: `harness/configurations/{C2,C3,C3-med,C3-prev,C5}.yaml`; policies
  `harness/policies/{p0-baseline,p1-cheap-first,p2-delegation,p3-policy-delegation}.yaml`.
- Manifest: `manifest/delivery-manifest.yaml` (pins, pricing snapshot, **all seven
  sealed artifacts frozen** with version + sha256 — PR #19, 2026-08-17).
- Driver: `scripts/screening-batch1-driver.sh`.
- Results directory: `results/screening-batch1/` (§5).
- Isolation posture: §7 — **resolved 2026-08-17** and verified by a four-run re-smoke.

## 1. Where the estimate comes from

From **smoke actuals**, not from batch-3 history. `report/smoke-screening/` §3:

| Arm | Product | Task | Measured cost | Usage tier |
|---|---|---|---:|---|
| P0 (`STRONG_MODEL_A`) | A | pilot (2 files) | **$0.433743** | authoritative |
| C2 (`ECONOMICAL_MODEL_A`) | A | pilot (2 files) | **$0.360544** | authoritative |
| C3 / C3-med / C3-prev | B | pilot | **no actual** — §2 | unavailable |
| C5 | A + B | pilot | **no actual** — never completed | unavailable |

**Two honest limits on this basis, stated before the arithmetic:**

- **n = 1 per arm, one task, and the easiest one on the roster.** The pilot edits two
  files; W3 is a +716/−348 refactor across 12 with a ~30-dialect parity gate. These
  are floors for the roster, not means.
- **The smoke actuals are ~3× the batch-3 Product-A mean of $0.138** (batch-3 plan
  §3). Cache-write tokens dominate: P0 spent 29,298 and C2 52,654 cache-write tokens
  against 14 and 6 raw input tokens. The 2026-08-16 re-pin moved the tier behind each
  configuration, so batch-3 costs are not a usable baseline and are not used as one.

## 2. Product B has NO cost actual, and why that is not zero

No Gemini figure was measured. The product exposes no machine-readable headless
usage, and the provider-side collector — the only other instrument — is blocked by a
violated quiet window (`report/smoke-screening/` §5: the backfill would have written
10,993,105 input tokens onto one ten-minute run, ~200× plausible). Nothing was
written; both Gemini legs stay `unavailable`.

For **budgeting only**, Product-B arms are bounded from the pinned snapshot rather
than left blank — a blank line in a budget reads as free, and **unavailable ≠ 0**
(CLAUDE.md rule 3). `pricing/prices-2026-08-16.json` puts every Gemini selector at
$0.75/1M input and $3.75/1M output, versus $5.00/$25.00 for `claude-opus-5@default`
and $3.00/$15.00 for `claude-sonnet-4-6@default` — **6.7× and 4× cheaper per token
respectively**. A Gemini arm doing comparable token work therefore costs well under
C2's $0.36.

**The bound used below is C2's measured $0.36 for every Gemini arm.** It is
deliberately loose: it prices Product-B tokens as if they cost Product-A economical
rates, which they do not, and it absorbs Product B's longer sessions (the C3 host run
took 539 s against C2's 82 s). It is a **budget ceiling input, not an estimate**, and
it must never be quoted as a Product-B cost.

## 3. Cost estimate

Per-arm unit costs. "Basis" says exactly what each number is.

| Arm | Unit cost | Basis |
|---|---:|---|
| P0 | $0.44 | smoke actual, n=1, easiest task |
| C2 | $0.36 | smoke actual, n=1, easiest task |
| C3, C3-med, C3-prev | $0.36 | **bound**, not an actual (§2) |
| C5 | $0.80 | dual-bill: A conductor at P0 + B executor at the bound |
| P1 | $0.80 | escalation probe: economical attempt then strong retry, both billed |
| P2 | $0.44 | scripted delegation over a frozen split, priced at the strong arm |

| Arm | Runs | Unit | Subtotal |
|---|---:|---:|---:|
| P0 | 21 | $0.44 | $9.24 |
| C2 | 21 | $0.36 | $7.56 |
| C3 | 21 | $0.36 | $7.56 |
| C3-med | 21 | $0.36 | $7.56 |
| C3-prev | 21 | $0.36 | $7.56 |
| C5 | 18 | $0.80 | $14.40 |
| P1 | 3 | $0.80 | $2.40 |
| **Core (126 runs)** | **126** | | **$56.28** |
| P2 (optional) | 6 | $0.44 | $2.64 |
| **Total (132 runs)** | **132** | | **$58.92** |

**Ceiling: $75**, i.e. ~1.27× the point estimate. Deliberately tight rather than the
batch-3-style 7× multiple, because the estimate rests on two measured Product-A arms
rather than a full prior batch: a real overrun should **halt and be looked at**, not
be silently absorbed. If the roster's harder tasks cost materially more than the
pilot, the cap fires part-way, the completed cells are published as a partial batch
with the halt reason (`cp-screen-prereg.md` §2 rule 3), and the human re-approves a
raised cap with real evidence. That is the intended behaviour, not a failure mode.

**Known overrun risks, named up front:** every unit cost comes from the roster's
easiest task; W3, W4b and W1b are materially harder; Product-B costs are bounded, not
measured; and P1's escalation on W3 is *predicted* to fire, so its double-bill is
expected rather than exceptional.

## 4. Kill-switches — three, following the batch-3 semantics

1. **In-runner spend cap — `--spend-cap-usd 75`** (batch-3 plan §3). Before starting
   each run the runner sums completed siblings' realized per-leg
   `marginal_operating_usd` under `results/screening-batch1/`; at or over the cap it
   prints `SPEND CAP REACHED` and exits **3** *without starting the run*. Resumable:
   re-invoke with `--start-at N`, optionally with a raised, re-approved cap.
   **The sum is a known floor** — `unavailable` legs are counted as legs and never
   zero-imputed, so while a Gemini leg is uncostable the cap protects the Product-A
   share of spend accurately and the Product-B share not at all. *(§6 blocker 2
   cleared 2026-08-17: with the meter quiet the collector backfill can attribute
   Product-B spend at batch end. In-run the cap is still Product-A-accurate only —
   the backfill lands after the runs, so mid-batch the cap sees a floor that omits
   the Gemini legs. The $75 ceiling is set with that in mind.)*
2. **Halt on nonzero exit.** `scripts/screening-batch1-driver.sh` stops the batch at
   the first nonzero runner exit — 3 (cap), 1 (telemetry validation failed), or 2
   (runner error) — and logs which plan index halted it. A batch that continues past
   a validation failure produces a dataset nobody can trust.
3. **Operator kill switch.** `touch results/screening-batch1/HALT` stops the batch
   cleanly *between* runs, from any shell, without killing a run mid-flight (the
   smoke's mid-flight kill is exactly what produced the discarded `ABORTED` run dir).

Plus the standing gate: a live batch refuses to start without `LAB_ALLOW_SPEND=1`,
which only a human sets after approval.

## 5. Results directory

All output lands in **`results/screening-batch1/`**. Every earlier dataset is
untouched and unpooled (CLAUDE.md rule 8). Documented by `report/screening-batch1/`,
which pairs by name; the row is added to `results/README.md` when the directory is
created. Cost checkpoints every 10 completed runs, and the collector backfill at
batch end, both write into that pair.

## 6. Blockers — this package cannot be approved while any remain

1. ~~**Four sealed artifacts `PENDING-FREEZE`** (`cp-screen-prereg.md` §3). The driver
   refuses to start; verified — see §8.~~ **CLEARED 2026-08-17** (PR #19): W4b, W3,
   W1b and W6 are frozen with version + sha256, each hash re-derived on this host from
   a validator run against the merged #18 validator rather than copied forward. All
   seven roster artifacts are now frozen and preflight 3 reports
   `ok all 7 sealed artifacts frozen (version + sha256 in the manifest)`. One entry
   (W3) went through a hash reconciliation, recorded in `cp-screen-prereg.md` §7.5.
2. ~~**The quiet window is violated** (`cp-screen-prereg.md` §7.3;
   `report/smoke-screening/` §5). A third `gemini-3.7-flash` consumer, principal
   `catwangzz@google.com` via `StreamRawPredict`, was still emitting ~800k input
   tokens per burst after both schedulers were paused. Until it stops, **every
   Product-B leg in this batch — 63 of 132 runs — is uncostable**, and the batch's
   own spend accounting is blind to half its arms (§4.1). The driver refuses on a
   noisy window.~~ **CLEARED 2026-08-17**: the third consumer stopped. The driver's
   own probe — the same one that reported **NOISY, 6,591,081 tokens in 15 minutes**
   earlier in the day — now reports `QUIET 0 tokens in the last 15m` over the same
   filter, on two independent dry runs (15:51Z and 15:58Z), and preflight 8 passes on
   the measurement rather than on the `--dry-run` tolerance. **What this clears and
   what it does not:** with a quiet meter the collector backfill can attribute
   Product-B spend, so the 63 Gemini legs are no longer structurally uncostable. It
   does not make them *measured* — the product still exposes no machine-readable
   headless usage, so per-leg figures stay `unavailable` unless the backfill resolves
   them, and a window that is quiet now can be re-contaminated mid-batch. The driver
   re-probes per run for exactly that reason.
3. ~~**Isolation posture unresolved** — §7.~~ **CLEARED 2026-08-17**: the five
   human-directed fixes were implemented and verified live by a four-run re-smoke —
   both products complete in container mode, 7/7 public gate checks each, no write
   escaping the staged tree. Evidence:
   `report/smoke-screening/re-smoke/re-smoke-report.md`. §7's table below is left as
   written; it records what the smoke found and is not rewritten after the fact.
4. ~~**Task declarations diverge from the registered matrix**
   (`cp-screen-prereg.md` §7.2) and **W3's `task_id` disagrees with the manifest**
   (§7.1).~~ **CLEARED 2026-08-17** (human-directed): all seven declarations carry
   their registered arms, the config lists admit `C3-med`/`C3-prev`/`P2`, and the
   canonical id is `w3-sqlfluff-segment-method-migration`. See `cp-screen-prereg.md`
   §7.1/§7.2 for what changed and why that direction.

**No blockers remain.** All four are struck through above, each with the evidence that
cleared it. The driver no longer refuses in `--dry-run`: all nine preflight gates pass
and the 126-run plan completes on stub adapters (§8). The one remaining refusal is the
spend gate itself — preflight 2, which fails a **live** batch without
`LAB_ALLOW_SPEND=1` — and that is this package's own approval, not a blocker on it.

## 7. Isolation posture — **RESOLVED 2026-08-17**

SPEC §5.1 makes the containerized agent leg with allowlist egress a hard
precondition for screening. The first smoke found it non-functional for **both**
products, and the host fallback **unsafe for Product B**. That finding is recorded
below as written; the resolution follows it.

| Defect | Effect | Arms affected |
|---|---|---|
| SMOKE-1: image runs as root; `claude` refuses `--dangerously-skip-permissions` | agent exits 1, $0 billed, no diff | P0, C2, P1, P2, C5 conductor |
| SMOKE-2: `agy` finds no credential in the container, falls to interactive OAuth, times out at 60 s | agent exits 1, $0 billed, no diff | C3, C3-med, C3-prev, C5 executor |
| SMOKE-3: on the **host**, `agy` writes into the lab's own `.work/repo`, outside the staged tree | exit 0, empty diff, **false reject**, and the contaminated tree leaks into the next run's staging | every Product-B arm on host |

**Running batch 1 in either posture at that point would have produced a broken
dataset**: containerized, every run fails at exit 1 for $0; on the host, every
Product-B arm records a false rejection. The recommendation was to **fix the image**
(non-root `USER` with a writable HOME/workdir; a credential `agy` accepts
non-interactively), re-smoke five runs against the $5 cap, fill `cp-screen-prereg.md`
§6's per-arm posture table from that result, then approve. The brief reserved the
decision for the human, and the smoke was explicitly not allowed to attempt the fix.

**Resolution — the recommendation was carried out and is satisfied.** The human
directed five fixes (SMOKE-1 non-root agent, SMOKE-2 read-only credential mounts with
a headless-or-refuse wrapper, SMOKE-3 container-only for Product B plus per-run state,
the collector contamination guard, the driver's quiet-window probe). A **four-run**
re-smoke verified them live: both products completed in container mode, all seven
public gate checks passed on each, and no write escaped the staged tree. Evidence:
`report/smoke-screening/re-smoke/re-smoke-report.md`. `cp-screen-prereg.md` §6's
posture table is filled and §7.4 there records the same resolution. Two honest notes
on scope: the re-smoke was four runs, not the five the recommendation named, and it
ran the pilot task rather than the harder roster tasks — it demonstrates the posture
functions, not that every roster task runs cleanly in it. The table above is left as
written; it records what the first smoke found and is not rewritten after the fact.

## 8. Driver verification (no spend)

`scripts/screening-batch1-driver.sh`, tested 2026-08-17:

- `--list` → **126** runs (`--with-p2` → **132**), matching `cp-screen-prereg.md` §4.
- `--dry-run` → *(at the time)* refuses at preflight 3 with all four `PENDING-FREEZE`
  artifacts named. **Superseded — see the 15:58Z run below.**
- `--dry-run --manifest tests/fixtures/manifest-screening-SYNTHETIC.yaml` (dry-run
  only; refused live) → preflights 1–3 pass, preflight 4 refuses and names the
  §7.2 divergence: `tasks/pilot-realworld: declares ['C2','P0','P1'] but the
  registered matrix needs ['C3','C3-med','C3-prev','C5']`.

**Re-verified 2026-08-17 after the declaration fix.** The same dry run now clears
preflight 4 — `ok 7 tasks: task_id matches the manifest, declared arms cover the
registered matrix` — and completes the **full 132-run plan** end to end on stub
adapters, every run `validate: PASS`, 0 deferred. The per-task arms the driver emits
are exactly §4's: five solo arms on all seven, C5 on six (not W6), P1 on W3, P2 on F1
and F3. Two notes from that exercise:

- The dry run had been writing its stub run dirs into `results/` itself — `run.py`
  honours `--phase` only on a live run and uses `--out-root` verbatim otherwise, and
  the driver passed the real root. Stub output under `results/`, outside any dataset
  directory, breaks CLAUDE.md rules 1 and 8. Fixed: a dry run now goes to a `mktemp`
  root, named in the log, and both modes write where the driver's own spend tally
  reads.
- The dry run reports a `$4.5882` "known spend floor over 130 runs". That is
  **stub-adapter arithmetic, not money** — nothing was billed and no model was
  contacted. It is exercising the cost-checkpoint path, not estimating the batch.
- Preflights 5–8 verified standalone: agy `1.1.13` == pin; egress allowlist sha256 ==
  pin; docker reachable; quiet window correctly reports **NOISY, 6,591,081 tokens in
  15 minutes** — the guard working, and blocker 2 restated. *(That NOISY reading is
  the state at the time; the same probe reads QUIET later the same day — see below.
  Both are kept: the guard is only credible because it fired when the window was
  dirty.)*
- `shellcheck -x` clean.

**Re-verified 2026-08-17T15:58Z on merged `main` (722ecdf), real manifest, no
override.** Preflight now passes end to end:

```
2026-08-17T15:58:33Z  === preflight ===
2026-08-17T15:58:33Z  ok   plan: 126 runs (reps=3, optional P2 excluded)
2026-08-17T15:58:33Z  ok   spend authorization (dry-run, nothing bills)
2026-08-17T15:58:33Z  ok   all 7 sealed artifacts frozen (version + sha256 in the manifest)
2026-08-17T15:58:34Z  ok   7 tasks: task_id matches the manifest, declared arms cover the registered matrix
2026-08-17T15:58:34Z  ok   agy 1.1.13 == pin; AGY_CLI_DISABLE_AUTO_UPDATE=1 exported
2026-08-17T15:58:35Z  ok   egress allowlist matches the manifest pin
2026-08-17T15:58:35Z  ok   docker reachable
       QUIET 0 tokens in the last 15m
2026-08-17T15:58:36Z  ok   quiet window: no background traffic on the subject models
2026-08-17T15:58:36Z  ok   kill switch armed
2026-08-17T15:58:36Z  === preflight passed: 126 runs, cap $75 ===
...
2026-08-17T15:59:28Z  === execution finished: 126/126 runs completed, 0 deferred ===
=== exit: 0 ===
```

All nine gates pass on the real manifest, the quiet window on a **measurement** rather
than the `--dry-run` tolerance, and the stub batch runs to completion. Output went to a
`mktemp` root, not `results/`.

**What a dry run still cannot verify, stated so approval is not taken on false
comfort:** preflight 2 is vacuous under `--dry-run` — the guard reads
`if [ "$DRY_RUN" -eq 0 ] && [ "$LAB_ALLOW_SPEND" != "1" ]` (`driver:208`), so a dry run
prints `ok` without exercising it. Its live behaviour is asserted from the source, not
demonstrated, because demonstrating it means invoking live mode. Equally, stub adapters
prove the plan, the gates and the plumbing; they prove nothing about what the real
agents cost or whether the harder roster tasks behave. That is what the $75 cap and the
three kill-switches in §4 are for.

## 9. Sequence & downstream gates

1. ~~**(human)** freeze the four sealed artifacts; decide the §7 posture; stop the
   third Gemini consumer.~~ **DONE 2026-08-17**: artifacts frozen (PR #19), posture
   resolved and re-smoked, third Gemini consumer stopped and the window measured
   quiet.
2. ~~**(me, no spend)** fill `cp-screen-prereg.md` §3 and §6; sync task declarations and
   `tests/test_tasks.py` to the approved matrix; resolve the W3 `task_id`.~~
   **DONE 2026-08-17**, human-directed.
3. **CP-SCREEN-PREREG** *(its mechanical gate, preflight 3, passes as of 2026-08-17)*,
   then **CP-SPEND (screening batch 1)** ⬅ this package, **the only gate still closed**.
4. **(me)** run the batch under `--spend-cap-usd 75`; validate every run; collector
   backfill at batch end.
5. **(me, no spend)** `report/screening-batch1/` + `results/README.md` row → **CP-DATA**.
6. No result enters docs, site or report before **CP-FINDINGS**; nothing external
   before **CP-PUBLISH**.

## 10. What this package does NOT do

Authorizes no spend before approval. Freezes no sealed artifact. Makes no
comparative, vendor or class-level claim — the $0.36 Product-B figure in §3 is a
budget ceiling input and is not a Product-B cost. Publishes nothing: screening output
is hypothesis-seeking and non-comparative (SPEC §5.2).
