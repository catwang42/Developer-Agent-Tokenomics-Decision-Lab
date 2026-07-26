# Warm-series revalidation — 3-run package (CP-SPEND)

CP-SPEND package for a **single 3-run warm-series** on the redesigned driver
(CLAUDE.md rule 5; SPEC §2.3; `methodology/cache-protocol.md` rule 2). Batch 3's
warm-series regressed (empty warm reps) because fresh-per-rep staging is incompatible
with `--resume` (`report/telemetry-completeness.md` §4.4). The redesign — stage ONCE
per series, reset the persisted tree between reps, path preserved, byte-identical
prompt — is **implemented as a no-spend change** (`harness/runner/warm_series.py`) and
covered by stub/dry-run tests. This package authorizes the **one live attempt** that
tells us whether reset+resume yields gradable warm work. **Approving this checkpoint
authorizes the spend in §3 under the §3 kill-switch and nothing else; nothing runs
before the human writes `CHECKPOINT APPROVED: CP-SPEND`.**

**Status:** awaiting approval. Prepared 2026-07-26 on branch `phase/3-harness`.
No model spend occurred in preparing it. This package does **not** approve CP-DATA;
criterion 7 stays PARTIAL until §4's stopping rule resolves it (§6).

**Package contents (CLAUDE.md CP-SPEND gate = budget + configs + manifest):**
- Budget & kill-switch: §3 (ceiling **$3**, `--spend-cap-usd 3`).
- Run matrix: §2 (3 runs, Product A only; F1 × C1, cold → resume ×2).
- Driver + config: `harness/runner/warm_series.py`; `harness/configurations/C1.yaml`.
- Manifest: `manifest/delivery-manifest.yaml` (F1 pin + pricing snapshot).
- Isolation posture: §5 (staged-subject **host** mode, `SUBJECT_PROFILE_HOST`; FIX A).
- Results directory: `results/feasibility-warm-series/` (§7 — batch 1/2/3 untouched).
- **Stopping rule, recorded BEFORE the run: §4 (ONE attempt; verbatim).**

## 1. What changed since batch 3 (no-spend)

The warm-series is now driven by `harness/runner/warm_series.py`, a single process
that owns the staging lifecycle:

- **Stage ONCE per series.** Rep 1 stages the subject tree via the existing FIX-A path
  (`_stage_subject_outside_repo`: a `mkdtemp` under `TMPDIR` outside the lab repo,
  refused if it resolves inside the repo, containing ONLY the subject repo). Reps 2..n
  reuse that same `/var/tmp/lab-subject-*/repo` path so `--resume`'s cwd matches.
- **Reset BETWEEN reps, in place.** Before each rep the staged tree is reset to the pin
  (`checkout --force <pin>` + `clean -ffd -e node_modules`), discarding the prior rep's
  solution, preserving `node_modules`, and recording the tree hash (`staged-reset.txt`);
  every rep must reset to the SAME hash (determinism, enforced in-driver).
- **Byte-identical prompt.** Every rep sends the exact same `task.prompt`. Warm reps are
  **not** given a "the tree was reset" hint — that would confound "cache is warm" with
  "prompt differs". Deliberately not hardened (see §4).
- **Clean up ONCE**, after the series.

**FIX-A isolation guarantee preserved, isolation-neutral.** Staged outside the lab repo;
no `../` chain from `<staged>/repo` reaches `canonical/`, `hidden/`, or `task.yaml`
(they are never staged); reusing the path and resetting in place introduces no new
relative-traversal path. Honest-scope caveat unchanged: same-uid, no container/fs
namespace, absolute-path FS access not confined — the Phase-4 container leg. No new
isolation claim is made.

## 2. Run matrix — 3 runs, **Product A only**

| Series | Task | Config | Reps | Cache |
|---|---|---|---|---|
| Warm-cache | F1 = pilot-realworld (feature, **pilot-v2**) | `C1.yaml` (strong) | 3 | rep 1 cold → reps 2–3 resume |

- One session id, minted once, shared by all three reps (rep 1 opens it; reps 2–3
  `--resume` it). Recorded authoritatively: `cache_state` = cold / warm-series /
  warm-series; `session_state` = fresh / resumed / resumed.
- Telemetry: `claude -p --output-format json` usage metadata, authoritative tier.
- **No Product B / `agy`, no other tasks, no other configs.**

**Command (run only after approval):**

```
LAB_ALLOW_SPEND=1 bash harness/runner/run-warm-series.sh \
  --task tasks/pilot-realworld --config C1 --reps 3 \
  --phase feasibility-warm-series --spend-cap-usd 3
```

## 3. Cost estimate & kill-switch — grounded in ACTUALS

| Source | Value |
|---|---|
| Batch-2 warm-series (F1·C1, 3 runs), total | **$0.3031** (0.1145 + 0.0817 + 0.1069) |
| Batch-3 C1 rep1 (F1·C1 cold), marginal | **$0.3219** |
| **Estimate for this 3-run series** | **~$0.50–0.65** (rep 1 cold ≈ batch-3 C1 rep1; reps 2–3 warm collapse toward batch-2 warm reps) |

**Ceiling: $3**, enforced by the in-runner kill-switch **`--spend-cap-usd 3`** (runner
default is $60; this lowers it). The switch is checked **before each rep** from the
realized, event-log-derived cost of completed reps in the batch dir, and halts (exit 3)
without starting a further rep once known spend reaches the cap. $3 is ~5× the estimate.

## 4. Stopping rule — ONE attempt (recorded BEFORE the run)

This is a **single-attempt** validation. It is recorded here, before any spend, so the
outcome cannot be re-litigated after the fact:

1. **ONE attempt only.** Run the 3-run series exactly once under the $3 cap.
2. **If reset+resume yields gradable work** (reps 2–3 produce non-empty diffs the gate
   grades, with authoritative warm `cache_read` / `cache_creation` and a costed warm
   delta): **criterion 7 returns to full PASS**, and this series becomes the standing
   warm-cache evidence (replacing the batch-2 carry-forward in §4.4 of the report).
3. **If it no-ops again** (reps 2–3 empty diff / `unavailable` usage, as in batch 3):
   record it as a **methodology finding — session resume and tree reset are
   incompatible**. Criterion 7 stays **PARTIAL** with the limitation documented, and
   warm-cache measurement **design moves to Phase 4**.
4. **No second attempt. No prompt modification to force success.** Appending a
   "the tree was reset" hint to the warm reps would make them run a different prompt
   than the cold rep, confounding "cache is warm" with "prompt differs" — explicitly
   out of scope. The byte-identical prompt is a fixed condition of this test.

Either outcome is a valid feasibility result. The point of the attempt is to *learn*
whether the redesign works, not to make it pass.

## 5. Isolation posture

Identical to batch 3: `--subject-isolation host` (the driver runs host-staged), stamping
`identity.permission_profile = SUBJECT_PROFILE_HOST` verbatim (authoritative) and
`network_policy = no-network-policy`. Staged outside the lab repo (FIX A); not
containerized; absolute-path FS access not confined. The containerized live-agent leg +
egress allowlist remain **Phase-4 screening CP-SPEND** requirements, not satisfied or
claimed here. The deterministic gate continues to run containerized under `--network=none`.

## 6. Bearing on CP-DATA (not approved here)

This package does not approve CP-DATA. Criterion 7 (cache) remains **PARTIAL** until the
§4 attempt resolves it. CP-DATA is a single full-strength approval taken after the human
review, not split across partial approvals. Provenance discipline: this series is its
own dataset (§7); it is **not** pooled with batch-3 controlled runs (mixed provenance
inside the authoritative dataset is exactly what our ex130 checklist flags).

## 7. Results directory

All output lands in **`results/feasibility-warm-series/`** — a self-contained dataset
with its own spend-cap accounting. Batch 1 (`results/feasibility/`), batch 2
(`results/feasibility-batch2/`), and batch 3 (`results/feasibility-batch3/`) are **not**
overwritten or aggregated into it.

## 8. Sequence & downstream gates

1. **(me, no spend)** implement driver + tests + docs ✅ → **CP-SPEND (warm-series)**
   ⬅ **awaiting approval now**.
2. **(me)** on approval, run the single 3-run series under `--spend-cap-usd 3` →
   validate each `events.jsonl` + `summary.json` → apply the §4 stopping rule.
3. **(me, no spend)** record the outcome in `report/telemetry-completeness.md`
   (criterion 7 → PASS or documented PARTIAL) as part of the **CP-DATA (final)** review
   the human runs at full strength.
4. No result enters docs/site/report before **CP-FINDINGS**.

## 9. Open design question (flag for SPEC amendment — Phase 4; NOT resolved here)

Repeating the same task three times against a reset tree may not be the right proxy for
warm-cache economics — a developer's real warm context accrues from working through
**different** tasks in one session. This series measures the provider prompt-cache
carry-over mechanics honestly, but its external validity as a model of real warm-session
cost is unestablished. Recorded as an **open design question for Phase 4**
(`methodology/cache-protocol.md`); not resolved by this package.

## 10. What this plan does NOT do

No spend before approval; no second attempt; no prompt modification to force success; no
Product-B / `agy` runs (Phase 4); no containerized agent leg (Phase 4); no CP-DATA
approval; no comparative or vendor claims. All metric outputs remain NON-COMPARATIVE and
internal-only.
