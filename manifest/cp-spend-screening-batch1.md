# Screening batch 1 — spend package (CP-SPEND)

CP-SPEND package for the **132-run screening batch 1** registered in
`manifest/cp-screen-prereg.md` (CLAUDE.md rule 5; SPEC §2.3, §5). **Approving this
checkpoint authorizes the spend in §3 under the §4 kill-switches and nothing else;
nothing runs before the human writes `CHECKPOINT APPROVED: CP-SPEND (screening
batch 1)`.**

**Status: NOT APPROVABLE YET.** It depends on CP-SCREEN-PREREG, which is itself
blocked on four `PENDING-FREEZE` sealed artifacts, and on three open blockers in §6
— two of which the smoke found today. Prepared 2026-08-17 on branch
`feat/screening-launch`. Spend in preparing it: **$0.79**, under the separately
approved $5 smoke cap.

**Package contents (CLAUDE.md CP-SPEND gate = budget + configs + manifest):**
- Budget & kill-switches: §3–§4 (ceiling **$75**, `--spend-cap-usd 75`).
- Run matrix: `manifest/cp-screen-prereg.md` §4 — 132 runs (126 without optional P2).
- Configs: `harness/configurations/{C2,C3,C3-med,C3-prev,C5}.yaml`; policies
  `harness/policies/{p0-baseline,p1-cheap-first,p2-delegation,p3-policy-delegation}.yaml`.
- Manifest: `manifest/delivery-manifest.yaml` (pins, pricing snapshot, all seven
  sealed artifacts — four not yet frozen).
- Driver: `scripts/screening-batch1-driver.sh`.
- Results directory: `results/screening-batch1/` (§5).
- Isolation posture: §7 — **unresolved, and the human's call.**

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
   zero-imputed, so with ~63 Gemini legs uncostable the cap protects the Product-A
   share of spend accurately and the Product-B share not at all. §6 blocker 2 is
   therefore also a spend-control blocker, not only a data one.
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

1. **Four sealed artifacts `PENDING-FREEZE`** (`cp-screen-prereg.md` §3). The driver
   refuses to start; verified — see §8.
2. **The quiet window is violated** (`cp-screen-prereg.md` §7.3;
   `report/smoke-screening/` §5). A third `gemini-3.7-flash` consumer, principal
   `catwangzz@google.com` via `StreamRawPredict`, was still emitting ~800k input
   tokens per burst after both schedulers were paused. Until it stops, **every
   Product-B leg in this batch — 63 of 132 runs — is uncostable**, and the batch's
   own spend accounting is blind to half its arms (§4.1). The driver refuses on a
   noisy window.
3. **Isolation posture unresolved** — §7.
4. **Task declarations diverge from the registered matrix**
   (`cp-screen-prereg.md` §7.2) and **W3's `task_id` disagrees with the manifest**
   (§7.1). Both are fixed on approval, not before; the driver refuses on either.

## 7. Isolation posture — the open question this package cannot answer

SPEC §5.1 makes the containerized agent leg with allowlist egress a hard
precondition for screening. Today's smoke found it non-functional for **both**
products, and the host fallback **unsafe for Product B**:

| Defect | Effect | Arms affected |
|---|---|---|
| SMOKE-1: image runs as root; `claude` refuses `--dangerously-skip-permissions` | agent exits 1, $0 billed, no diff | P0, C2, P1, P2, C5 conductor |
| SMOKE-2: `agy` finds no credential in the container, falls to interactive OAuth, times out at 60 s | agent exits 1, $0 billed, no diff | C3, C3-med, C3-prev, C5 executor |
| SMOKE-3: on the **host**, `agy` writes into the lab's own `.work/repo`, outside the staged tree | exit 0, empty diff, **false reject**, and the contaminated tree leaks into the next run's staging | every Product-B arm on host |

**Running batch 1 in either posture today produces a broken dataset**: containerized,
every run fails at exit 1 for $0; on the host, every Product-B arm records a false
rejection. Recommendation: **fix the image** (non-root `USER` with a writable
HOME/workdir; a credential `agy` accepts non-interactively), re-smoke five runs
against the $5 cap, fill `cp-screen-prereg.md` §6's per-arm posture table from that
result, then approve. The brief reserved this decision for the human, and the smoke
was explicitly not allowed to attempt the fix.

## 8. Driver verification (no spend)

`scripts/screening-batch1-driver.sh`, tested 2026-08-17:

- `--list` → **126** runs (`--with-p2` → **132**), matching `cp-screen-prereg.md` §4.
- `--dry-run` → refuses at preflight 3 with all four `PENDING-FREEZE` artifacts named.
- `--dry-run --manifest tests/fixtures/manifest-screening-SYNTHETIC.yaml` (dry-run
  only; refused live) → preflights 1–3 pass, preflight 4 refuses and names the
  §7.2 divergence: `tasks/pilot-realworld: declares ['C2','P0','P1'] but the
  registered matrix needs ['C3','C3-med','C3-prev','C5']`.
- Preflights 5–8 verified standalone: agy `1.1.13` == pin; egress allowlist sha256 ==
  pin; docker reachable; quiet window correctly reports **NOISY, 6,591,081 tokens in
  15 minutes** — the guard working, and blocker 2 restated.
- `shellcheck -x` clean.

The execution loop is not reachable end to end until blockers 1 and 4 clear, which is
the intended design: every guard fires in order before anything bills.

## 9. Sequence & downstream gates

1. **(human)** freeze the four sealed artifacts; decide the §7 posture; stop the
   third Gemini consumer.
2. **(me, no spend)** fill `cp-screen-prereg.md` §3 and §6; sync task declarations and
   `tests/test_tasks.py` to the approved matrix; resolve the W3 `task_id`.
3. **CP-SCREEN-PREREG**, then **CP-SPEND (screening batch 1)** ⬅ this package.
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
