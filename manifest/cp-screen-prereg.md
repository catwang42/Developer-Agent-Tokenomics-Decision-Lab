# Screening pre-registration package — the W1–W7 roster, arms and conditions (CP-SCREEN-PREREG)

Pre-registration package for the **Phase-4 screening window** (CLAUDE.md CP-SCREEN-PREREG;
SPEC v2.2 §5, §5.1, §5.2). This document is the anti-selection-bias artifact: it fixes the
task roster, the per-task arm matrix, the repetition plan and the pinned run conditions
**before any screening run exists**, so that git history proves the registration precedes
the data. **Approving this checkpoint registers the design in §2–§6 and authorizes no
spend whatsoever** — spend is gated separately by `manifest/cp-spend-screening-batch1.md`;
nothing runs before the human writes `CHECKPOINT APPROVED: CP-SCREEN-PREREG`.

**Status:** **NOT APPROVABLE AS IT STANDS.** Four sealed artifacts are `PENDING-FREEZE`
(§3). Prepared 2026-08-17 on branch `feat/screening-launch`. No model spend occurred in
preparing it.

**Update 2026-08-17 (human-directed, same branch).** Three of the four repo-side
prerequisites are cleared: §7.1 (W3 `task_id`), §7.2 (declared arms) and §7.4 (isolation
posture). §7.5 — the four `PENDING-FREEZE` artifacts — remains open and is the human's.
**The registration in §2–§6 is unchanged**; §4's matrix was not edited, it was
transcribed into the declarations and into the test that now enforces it. That direction
matters: the document is the authority and the code was moved to match it, never the
reverse.

**Package contents:**
- Roster + sealed-artifact status: §3 (7 tasks; 4 artifacts `PENDING-FREEZE`).
- Arm matrix and run count: §4 (44 cells, **132 runs** at 3 reps; 126 without optional P2).
- Registered hypotheses: §5 (both referenced by commit hash).
- Pinned run conditions: §6.
- Blocking prerequisites before approval: §7.
- Disclosures required by the anti-bias protocol: §8.

---

## 1. Transparency label (mandatory on all outputs, SPEC §5)

> This program is intentionally *hypothesis-seeking positioning evidence screening*. It
> must not be used to estimate overall product superiority or expected enterprise-wide
> savings, and it never substitutes for the balanced reference benchmark (layer 2A),
> which remains balanced independently of this program.

Every artifact derived from this batch — table, chart, slide, page — carries that label.
Screening results are **not independently publishable** as class-level conclusions
(SPEC §5.2); they identify hypotheses for the pilot reference dataset.

## 2. Anti-selection-bias protocol (SPEC §5)

1. Every task pre-registered before running — this document, committed before the batch.
2. All tested workload classes published, **including negative and null findings**.
3. **No task added or removed on the basis of interim results.** If the batch is halted
   part-way, the completed cells are published as a partial batch with the halt reason;
   the roster is not re-cut.
4. Screening data is never presented as a balanced market comparison.

## 3. Roster and sealed-artifact status

Seven tasks. `manifest_key` resolves the pins in `manifest/delivery-manifest.yaml`; the
sealed artifact is human-authored and human-held under `tasks/**/hidden/` (gitignored).

| # | Task | Task dir | Class / gate | Tier | Sealed artifact | Status |
|---|---|---|---|---|---|---|
| F1 | `pilot-realworld-draft-articles` | `tasks/pilot-realworld` | feature / solution | famous | `sealed-pilot-v1` `sha256:105c2418…b667abe2` | **FROZEN** (10/10) |
| F2 | `w4-realworld-missing-user-id` | `tasks/suite/W4-complex-bugfix` | complex_bugfix / solution | famous | `sealed-w4-v2` `sha256:3d6f8049…871886c2` | **FROZEN** (10/10) |
| F3 | `w1-realworld-mapper-tests` | `tasks/suite/W1-test-generation` | test_generation | famous | `sealed-w1-v1` `sha256:37f3acd6…c707c51f4e9` | **FROZEN** (10/10) |
| W4b | `w4b-zarr-consolidated-order` | `tasks/suite/W4b-zarr-consolidated-order` | complex_bugfix / solution | post_cutoff | sealed hidden test | **PENDING-FREEZE** |
| W3 | `w3-sqlfluff-segment-method-migration` | `tasks/suite/W3-migration` | migration / solution · **escalation probe** | post_cutoff | sealed hidden test | **PENDING-FREEZE** |
| W1b | `w1b-zarr-block-mask-properties` | `tasks/suite/W1b-zarr-block-mask-properties` | test_generation | post_cutoff | sealed mutation-catch runner | **PENDING-FREEZE** |
| W6 | `w6-hono-router-review` | `tasks/suite/W6-pr-review` | code_review / pr_review | post_cutoff | sealed **seeded-defect map** (+ `k`) | **PENDING-FREEZE** |

**`PENDING-FREEZE` means exactly this:** the manifest records
`sealed_hidden_test.status: awaiting_human` with **no version and no hash**. No hash has
been invented, guessed or placeholder-filled (CLAUDE.md rule 1). The human authors the
four artifacts and fills `version` + `sha256`; this package becomes approvable only when
zero rows read `PENDING-FREEZE`, and `scripts/screening-batch1-driver.sh` refuses to
start while any remain (§7.4).

*Note on the count:* the brief anticipated **three** pending artifacts. Four rows are
pending because W6's artifact is a sealed **seeded-defect map**, not a sealed hidden
test — the manifest carries it under a different key (`sealed_defect_map`). All four are
listed rather than three; if W6's map is already authored, freeze it and the row clears.

**Class-claim pairing (SPEC §5.2).** Two classes carry the required second, materially
different task: W4 (famous) ↔ W4b (post_cutoff, Python/zarr), and W1 (famous) ↔ W1b
(post_cutoff, Python/Hypothesis). W3 and W6 have **one task each**, so any W3 or W6
result is a screening signal about *that task* and never a workload-class claim.

## 4. Arm matrix and run count

Arms are the `--config` ids the runner accepts. P3 is **not** a CLI id: it is the pinned
policy governing C5 (`routing_policies.P3`, hash-verified at run time), so the C5/P3 arm
is run as `--config C5`.

| Arm | `--config` | What it is | Applies to |
|---|---|---|---|
| P0 | `P0` | B1 static strong-tier baseline (STRONG_MODEL_A) | all 7 |
| C2 | `C2` | Product A economical tier | all 7 |
| C3 | `C3` | Product B, current Flash generation, High | all 7 |
| C3-med | `C3-med` | Product B, current generation, **Medium** effort | all 7 |
| C3-prev | `C3-prev` | Product B, **prior** Flash generation, High | all 7 |
| C5/P3 | `C5` | B4 policy-driven delegation (A conductor → B executor) | all except W6 |
| P1 | `P1` | B2 cheap-first escalation | **W3 only** (registered probe) |
| P2 | `P2` | B3 scripted delegation | **F1 and F3 only** (optional) |

| Task | P0 | C2 | C3 | C3-med | C3-prev | C5/P3 | P1 | P2 | Cells |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| F1 pilot | ● | ● | ● | ● | ● | ● | — | ○ | 6 (+1) |
| F2 W4 | ● | ● | ● | ● | ● | ● | — | — | 6 |
| F3 W1 | ● | ● | ● | ● | ● | ● | — | ○ | 6 (+1) |
| W4b-zarr | ● | ● | ● | ● | ● | ● | — | — | 6 |
| W3-migration | ● | ● | ● | ● | ● | ● | ● | — | 7 |
| W1b-zarr | ● | ● | ● | ● | ● | ● | — | — | 6 |
| W6-pr-review | ● | ● | ● | ● | ● | — | — | — | 5 |

● registered · ○ optional (P2) · — not run

| | Cells | × 3 reps |
|---|---:|---:|
| Solo arms P0/C2/C3/C3-med/C3-prev × 7 tasks | 35 | 105 |
| C5/P3 × 6 tasks (not W6) | 6 | 18 |
| P1 × W3 only | 1 | 3 |
| **Core subtotal** | **42** | **126** |
| P2 × F1, F3 (optional) | 2 | 6 |
| **Total with P2** | **44** | **132** |

**Registered run count: 132 runs** (126 if the optional P2 cells are not taken). The P2
decision is taken at approval time and recorded here; the driver reads it from a single
flag so the executed count always matches the registered one.

**Why C5 is not run on W6.** W6 is a review task: nothing is installed, built or executed
and the participant returns a defect list. Delegating a read-and-report task to an
executor changes what is being measured without a defined executor deliverable, so the
cell is not registered. This is a design exclusion fixed *before* any run, not a dropped
result.

**Why P0 rather than C1.** P0 is the B1 static-assignment policy resolving
`STRONG_MODEL_A`; running the baseline as a policy keeps the whole matrix on the
routing-policy ladder (SPEC §2.1b) and gives P0-vs-P1 on W3 a shared baseline arm.

**Repetition plan — a declared deviation from SPEC §5.1.** SPEC §5.1 asks for **≥5 reps
on strong-tier and cold-cache-sensitive cells** and 3 elsewhere. This batch registers
**3 reps on every cell, P0 included.** Rationale: screening is hypothesis-seeking and
explicitly *not publishable* (SPEC §5.2), and the ≥5-rep rule is what governs the pilot
reference dataset. Consequence, stated up front: **no P0 cell from this batch may be
cited as a stable cost estimate**, and any promising cell is re-run at ≥5 reps before it
appears in any deck (SPEC §5.1). Every point estimate travels with median, range and n
(SPEC §2.9 item 4).

**Cache state.** All 132 runs are `--cache-state cold`. No warm series in this batch.

## 5. Registered hypotheses

Both are human-authored and committed **before** any screening run. Referenced by commit
hash so the ordering is provable from git history:

| Hypothesis | File | Registering commit |
|---|---|---|
| H-effort — Gemini 3.7 Flash Medium vs High | `manifest/preregistrations/2026-08-16-H-effort.md` | `48e8f82c1887f54d7b9bfe96ae73782aa4670432` |
| W3 escalation probe — economical-tier failure | `manifest/preregistrations/2026-08-17-W3-escalation-probe.md` | `467d1c7d38bc8467d5110b7a20d15e1887178cb7` |

- **H-effort** predicts C3-med passes the same gates as C3 on routine tasks at materially
  fewer tokens (~30–50% lower cost-per-accepted-outcome), and explicitly registers **no**
  prediction for the harder tasks — those cells are exploratory.
- **W3 escalation probe** predicts the economical tier fails W3's gate, firing P1's
  escalation branch — the mechanism that finally exercises B2 (SPEC §2.9 item 3). P1 is
  registered on W3 **and nowhere else** for exactly this reason.

Both carry **"result published either way"**, including the null result.

## 6. Pinned run conditions

| Condition | Value | Enforced by |
|---|---|---|
| Cost basis, all Gemini legs | `marginal_api_cost` + `cost_basis_qualifier: cache_blind_upper_bound` | manifest per `PRODUCT_B_*`; runner stamps every leg |
| Effort attribution | serialization-window only — `model_user_id` collapses High/Medium | serialized batch; collector README |
| Product-B version | `agy` **1.1.13**, `agy_sha256 416b197e…ee920` | `run.py:preflight_product_versions`; adapter; image build |
| Product-B auto-update | disabled via `AGY_CLI_DISABLE_AUTO_UPDATE` | adapter sets it on every invocation |
| Product-B print timeout | `15m0s` | manifest → `agy --print-timeout` |
| Product-A CLI | `claude` **2.1.233** (baked into the agent image; read from the image label) | image label `lab.cli.*.version` |
| Pricing snapshot | `pricing/prices-2026-08-16.json` | `resolve_pricing` refuses if unresolved |
| Quiet window | **all** non-subject Gemini traffic in `vital-octagon-19612` paused for the whole batch **through the final backfill** | named and confirmed in the CP-SPEND package |
| Serialization | one run at a time, no overlap | driver runs strictly serially |
| Isolation posture | **per arm — see below** | recorded per run in `identity.permission_profile` + `identity.network_policy` |

**Cache-blindness consequences**, restated wherever a Product-B figure appears: Gemini
`cache_read_tokens`/`cache_creation_tokens` stay `unavailable` (never 0); the figure is an
**upper bound** (real spend can only be lower); cross-product cache comparisons are **out
of scope** (SPEC §2.9).

**Quiet window — this is the fragile condition.** `model_user_id` does not distinguish our
runs from any other workload on the same model, so *only* the time window separates them.
Verified live on 2026-08-17 while preparing this package: `gemini-3.7-flash` carried
**12,048,032 background input tokens in one hour**, from more than one source. Two
schedulers are now paused for the batch (`agy-agent-catalog-refresh`, `ta-daily-trigger`)
and a third interactive source was still active at package time (§7.3). A batch run under
a violated quiet window produces attributions that are wrong by orders of magnitude and
must not be recorded as usage.

**Isolation posture — stated per arm.** SPEC §5.1 makes the containerized agent leg with
endpoint-allowlist egress a *hard precondition* for screening. Enforcement is verified
(`harness/container/verify-egress.sh`, re-run 2026-08-17: no route without the proxy,
allowlisted host reachable, non-allowlisted refused, non-443 CONNECT refused).
**Sufficiency** for a live agentic run is what the Phase-1 smoke establishes, per product.
The posture table is filled from the smoke result and every run stamps the posture it
actually launched under:

| Arm | Product | Registered posture | Smoke result (2026-08-17) |
|---|---|---|---|
| P0, C2, P1, P2 | A (`claude`) | `container` + `--subject-egress allowlist` | **BLOCKED — SMOKE-1**: the image has no `USER`, so the agent runs as root and `claude` refuses `--dangerously-skip-permissions`. Agent exit 1, $0 billed, no diff. Host fallback works: P0 and C2 both `accepted`, all usage `authoritative`. |
| C3, C3-med, C3-prev | B (`agy`) | `container` + `--subject-egress allowlist` | **BLOCKED — SMOKE-2**: no credential `agy` accepts inside the container; falls to interactive OAuth, times out at 60 s. Agent exit 1, $0 billed. Host fallback is **UNSAFE — SMOKE-3**: `agy` wrote into the lab's own `.work/repo`, outside the staged tree → exit 0, empty diff, false reject, and the contamination leaked into the next run's staging. |
| C5/P3 | A + B | `container` + `--subject-egress allowlist` | **BLOCKED** — conductor hits SMOKE-1, executor hits SMOKE-2. Never completed in either posture. |

**The registered posture stands; it does not currently work.** No arm may run until
the human resolves this (`manifest/cp-spend-screening-batch1.md` §7). Running
containerized today yields 132 runs at exit 1 for $0; running on the host yields a
false rejection on all 63 Product-B legs, which is worse than no data. The one
positive: `agy` reached `accounts.google.com` *through the proxy* and got a real OAuth
challenge, so the egress allowlist itself is functional — SMOKE-2 is a credential
problem, not an egress one, and no allowlist addition fixes either defect.

Full evidence: `report/smoke-screening/smoke-report.md`.

## 7. Blocking prerequisites — open at the time of writing

### 7.1 W3's `task_id` disagrees between the manifest and the task — **RESOLVED 2026-08-17**
- `manifest/delivery-manifest.yaml:433` → `w3-sqlfluff-dialect-common-migration`
- `tasks/suite/W3-migration/task.yaml:22` → `w3-sqlfluff-segment-method-migration`

`tests/test_tasks.py` compares `repo` and `pinned_commit` but not `task_id`, so this
passes the gate today. It is not cosmetic: `task_id` is the first field of every run
directory name (`<task_id>__<CONFIG>__rep<N>__<stamp>`) and therefore the key every
downstream aggregation joins on. **Human decides which spelling is canonical**; the other
is corrected and the test extended to compare `task_id` too.

**Resolution.** Canonical id: **`w3-sqlfluff-segment-method-migration`** (the task.yaml
spelling). The manifest and `tests/fixtures/manifest-screening-SYNTHETIC.yaml` were
corrected to it. Three reasons for that direction: it is the only spelling that has ever
named anything at run time (the runner reads `task.yaml`, so the manifest spelling has
never appeared in a run-dir name); it names the *change* — segment methods → free
functions, matching PR #7962's title — where the other names only the destination
module; and it leaves the task dir, README and gate untouched. **No data exists under
either spelling** — W3 has never been run — so this is reversible with one commit if the
human prefers the other. `tests/test_tasks.py::test_manifest_entry_agrees_with_task` now
compares `task_id` alongside `repo` and `pinned_commit`, so the two cannot drift again.

### 7.2 Declared arms do not match the registered matrix — **RESOLVED 2026-08-17**
All four screening tasks declare `configurations: [C1, C2, C3, C5]` in `task.yaml`, and
`tests/test_tasks.py::test_screening_configurations_are_the_screening_arms` asserts
*exactly* that set. The three feasibility tasks declare `[P0, C2, P1]`. The registered
matrix (§4) is neither. Also, `tests/test_tasks.py` `VALID_CONFIGS = {C1,C2,C3,C4,C5,P0,P1}`
omits `C3-med`, `C3-prev` and `P2`, and `_RUN_DIR_RE`'s config token `[A-Z0-9]+` does not
match `C3-med` — run dirs for those arms would be silently skipped by the results checks.
(The telemetry schema enum is already correct; only the tests lag.)

**Deliberately not fixed in this PR.** Rewriting seven declarations and the test that
enforces them would encode this matrix as settled before the human has approved it. On
approval, §4 is synced into the declarations, `VALID_CONFIGS` and `_RUN_DIR_RE` are
widened, and the test asserts the registered per-task sets.

**Resolution (human-directed 2026-08-17).** Done exactly as described above.

- All seven `task.yaml` files declare their §4 arms: five solo arms everywhere; `C5`
  everywhere but W6; `P1` on W3 only; `P2` on F1 and F3 only.
- `VALID_CONFIGS` gained `C3-med`, `C3-prev` and `P2`, and `_RUN_DIR_RE`'s config token
  became `[A-Z][A-Za-z0-9-]*` so a hyphenated arm matches. A new test asserts
  `VALID_CONFIGS ⊇` the schema's `configuration_id` enum **and** that every enum member
  matches the run-dir regex, so the next additive widening cannot leave these lists
  behind — which is exactly how `C3-med`/`C3-prev`/`P2` runs came to be skipped rather
  than checked.
- `test_screening_configurations_are_the_screening_arms` and
  `test_configurations_is_the_controlled_feasibility_set` are replaced by one test over
  all seven tasks, driven by a table transcribed from §4.

**One thing this exposed.** `configurations` was doing two jobs: declaring the plan, and
recording what a feasibility batch actually ran. The batch-2 conformance check joins on
it to catch the out-of-plan F1·C3 and F1·C5 companion runs — so overwriting it with the
screening matrix (which *registers* C3 and C5 for F1) would have turned that check green
by erasing the finding. The historical set now lives in its own frozen key,
`feasibility_configurations: [P0, C2, P1]`, on F1/F2/F3 only, and the batch-2 check joins
on that. It still reports exactly `{F1·C3, F1·C5}`.

### 7.3 The quiet window is not yet established
A third `gemini-3.7-flash` consumer — principal `catwangzz@google.com`, method
`PredictionService.StreamRawPredict`, likely an interactive session — was still emitting
after both schedulers were paused (829,846 input tokens at 02:15:41Z). It must be stopped
and the metric observed quiet before the batch.

Measured today, not projected: the smoke's C3 run window would have been backfilled with
**10,993,105 input tokens** for a single ten-minute agy session on a two-file task —
about 200× plausible, and $8.24 at the pinned rate on an arm the runner recorded as
`unavailable`. Nothing was written. No label can narrow the query: every series on the
subject model carries an identical label set with an empty `model_version_id` and no
caller, job or session dimension. Evidence: `report/smoke-screening/smoke-report.md` §5.

### 7.4 The isolation posture does not currently work for either product — **RESOLVED 2026-08-17**
See §6's posture table. This is the largest of the four and is the human's decision.

**Resolution.** The human directed five fixes (SMOKE-1 non-root agent, SMOKE-2 read-only
credential mounts with a headless-or-refuse wrapper, SMOKE-3 container-only for Product B
plus per-run state, the collector contamination guard, the driver's quiet-window probe),
and a four-run re-smoke verified them live: **both products completed in container mode**,
all seven public gate checks passed on each, and no write escaped the staged tree. The
registered posture in §6 therefore now works and stands unchanged. Evidence:
`report/smoke-screening/re-smoke/re-smoke-report.md`. §6's posture table is left as
written — it records the smoke result of 2026-08-17 and is not rewritten after the fact.

### 7.5 Four sealed artifacts `PENDING-FREEZE` (§3)
The driver refuses to start while any remain.

## 8. Disclosures

- **Feasibility reuse.** F1, F2 and F3 were run in feasibility batches 1–3 under
  different model pins. Their screening runs are new data under the 2026-08-16 re-pin and
  are **never pooled** with feasibility runs on a shared `configuration_id`: the tier
  behind C1/C2/C3 changed on that date (manifest header).
- **Contamination.** F1/F2/F3 are tier `famous` and share one repository; the pilot is
  Claude-authored and stays outside any comparative claim. The four mined tasks are
  `post_cutoff`. Tier is model-relative (`tasks/WORKLOAD-SELECTION.md` §2).
- **Repository reuse.** W4b and W1b are both `zarr-python`; they are different modules and
  different gate types, and no claim treats them as independent repositories.
- **Classes not screened this window.** W2 (scaffold feature), W5 (small edit, the
  break-even control) and W7 (greenfield) are `status: candidate` with unpinned repos and
  are **not** in this batch. Their absence is registered here so it cannot later read as a
  silent drop. C4 is out of scope this window by human decision (2026-08-15) and is
  unpriced in the snapshot; C6 is declared, not scheduled.

## 9. What this package does NOT do

Authorizes no spend (that is `manifest/cp-spend-screening-batch1.md`). Freezes no sealed
artifact — four remain `PENDING-FREEZE`. Fixes no result in docs, site or report: every
number from this batch is gated by **CP-FINDINGS**, and anything external-facing by
**CP-PUBLISH**. Makes no comparative or vendor-superiority claim, and promotes nothing to
a workload-class claim.
