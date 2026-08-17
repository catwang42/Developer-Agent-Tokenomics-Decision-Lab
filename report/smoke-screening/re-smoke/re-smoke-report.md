# Re-smoke — verification of the five smoke fixes (FIX-1 … FIX-5)

**STATUS: AUTHORITATIVE** for the four re-smoke runs listed in §1, inside
`results/smoke-screening/` (2026-08-17). It **supersedes nothing**: the original
`../smoke-report.md` stays AUTHORITATIVE for the eight original smoke runs and for the
defect findings themselves. This document reports only whether the fixes work.
**Feasibility evidence, not measurement.** No number here is a product comparison and
none may leave this file before CP-FINDINGS.

**Run under:** the human's pre-approved re-smoke grant — *cap $3, results to
`results/smoke-screening/`*, on top of the original `CHECKPOINT APPROVED: CP-SPEND
(screening smoke, hard cap $5)`.
**Re-smoke spend: $2.03 of the $3 grant** (known floor; the Product-B leg's cost is
`unavailable`, see §5). Cumulative in the dataset: $2.83.
**Both schedulers (`agy-agent-catalog-refresh`, `ta-daily-trigger`) remained PAUSED
throughout.**

## 0. Verdict in one paragraph

All five fixes work, and the re-smoke found and fixed a sixth defect that the first
smoke could not have seen. **Both products now run in the container**: Product A
accepts `--dangerously-skip-permissions` as a non-root user (FIX-1), and Product B
authenticates headlessly from read-only credential mounts with no interactive OAuth
path left anywhere (FIX-2) and no cross-run state (FIX-3) — verified by inspecting the
exact `$HOME` the product was handed. Product B **did not escape the subject tree this
time**; the lab working copy is clean. The collector's contamination guard passed a
genuinely quiet window and **refused** the original smoke's contaminated one on all
three of its criteria, writing nothing (FIX-4). FIX-5's probe was exercised twice for
real: NOISY at 03:49 UTC, QUIET at 04:08 UTC, and the run went ahead only on the
second. The sixth defect (§3) is the serious one: making the agent non-root made the
subject tree unreadable to git inside the root-run gate container, and because the gate
discards git's stderr, **its anti-gaming checks passed vacuously**. That is fixed and
tested; the two container P0 runs that preceded the fix are marked below as not
carrying a valid gate verdict.

## 1. The runs

| Run dir (`results/smoke-screening/`) | Proves | Result |
|---|---|---|
| `…__P0__rep1__20260817T035008` | FIX-1 | claude ran non-root in-container, exit 0. **Gate verdict void** (§3) and **no `agent-solution.diff`** (§4). |
| `…__P0__rep1__20260817T035330` | FIX-1 + diff artifact | exit 0, diff artifact written but **empty** — the git-ownership defect (§3). **Gate verdict void.** |
| `…__P0__rep1__20260817T040429` | FIX-1, clean | **The valid Product-A container run.** All 7 public checks pass, 44-line diff. |
| `…__C3__rep1__20260817T040821` | FIX-2, FIX-3, FIX-4, FIX-5 | **The valid Product-B container run.** agy 1.1.13, exit 0, all 7 public checks pass, 44-line diff, clean backfill. |

The first two P0 runs are retained (never deleted) as the provenance of the §3 finding.

Per-run detail, in the format requested:

| | valid P0 (`…040429`) | valid C3 (`…040821`) |
|---|---|---|
| user id in container | `uid=706335951(lab) gid=706335951(lab)` — non-root | same |
| staged path | `/subject` (per-run named Docker volume, seeded from the image) | same |
| credential source | `~/.config/gcloud` → `/creds/gcloud` (ro); ADC path in env | 3 files from `~/.gemini/antigravity-cli/` → `/creds/agy/*` (ro) |
| `agent-solution.diff` non-empty | **yes, 44 lines**, exactly the two allowed files | **yes, 44 lines**, exactly the two allowed files |
| gate verdict | public **PASS** (7/7, incl. the new G0); hidden `awaiting_human` | public **PASS** (7/7); hidden `awaiting_human` |
| exit code | 0 | 0 |
| backfill outcome | n/a (Product A telemetry is authoritative from the CLI) | **backfilled**, guard decision **clean** — see §5 |

`acceptance.result` is `error` on every run, correctly: the sealed hidden tests are
human-held, so no run can be *authoritatively* accepted. That is the stop point, not a
failure.

## 2. The five fixes

### FIX-1 — non-root agent (SMOKE-1)

`Dockerfile.subject` creates a `lab` user and ends the `subject-agent` stage with
`USER lab`, placed last so every build-time `RUN` (npm install, both CLI pin asserts,
`assert-no-task-material /`) still executes as root and the image content is fixed
before the drop. The no-task-material assertion was re-run at build and passes:

```
Step 41/44 : RUN assert-no-task-material /
assert-no-task-material: ok — no canonical/, hidden/ or task.yaml under '/'
```

`--dangerously-skip-permissions` is present in the recorded argv of every container P0
run and the CLI accepted it (exit 0, real usage returned).

**The uid is the host operator's, not a fixed 1001**, and this is the part worth
reading. Non-root and credential access pull in opposite directions: both products
authenticate from `0600` files owned by the invoking user, and a bind mount hands the
container the host's numeric owner untranslated — so *any* other uid gets `EACCES` and
SMOKE-2 comes straight back. `build-subject-image.sh` therefore passes
`SUBJECT_UID=$(id -u)`. Because the image tag pins task + commit and not the builder,
an image built under another account is a legal cache hit; the uid is recorded in the
`lab.image.subject_uid` label and `exec.assert_image_uid_matches_host` refuses such an
image in the runner **before** anything can spend.

### FIX-2 — headless credentials, or refusal (SMOKE-2)

**Where agy's credentials live on this host:**
`~/.gemini/antigravity-cli/` — resolved from `$HOME`, with no `AGY_CLI_*`/`XDG_*`
override in the 1.1.13 binary. That is why the original smoke's `~/.gemini →
/creds/gemini` mount was invisible to the product and it fell through to an OAuth URL.

**What crosses the boundary, exhaustively** (all read-only, all individual files):

| Host path | Container path | What it grants |
|---|---|---|
| `~/.gemini/antigravity-cli/antigravity-oauth-token` | `/creds/agy/antigravity-oauth-token` | **The whole of Product B's provider access** (`auth_method: gcp`). |
| `~/.gemini/antigravity-cli/settings.json` | `/creds/agy/settings.json` | Read **only** for its `gcp` `{project, location}` block, so the run bills the project the operator configured rather than one the harness guessed. Its `trustedWorkspaces` is discarded in-container (§FIX-3). |
| `~/.gemini/antigravity-cli/installation_id` | `/creds/agy/installation_id` | Non-secret install identifier; keeps a measured run from looking like a first-ever launch. |
| `~/.config/gcloud` | `/creds/gcloud` | Application-default credentials; mints Vertex tokens for the operator's project (Product A's Vertex path). |

**No interactive OAuth path remains.** `/usr/local/bin/agy` is now
`harness/container/agy-headless.sh`; the vendored binary is installed off `PATH` at
`/usr/local/lib/lab/agy.real`, so no invocation route — the adapter's, the version
probe's, a manual `docker exec` — bypasses it. Without a readable token the wrapper
**refuses with exit 42** and says why, rather than letting the product print a URL and
burn the timeout. Verified in the built image:

```
$ docker run --rm --network=none <agent-image> bash -lc 'agy -p hi; echo rc=$?'
agy-headless: FAIL (SMOKE-2) — no Product-B credential at /creds/agy/antigravity-oauth-token.
rc=42
```

`--version`/`--help` are the one credential-free path, deliberately: the build-time and
adapter pin checks must fail with *"version mismatch"*, not with a credential error
that hides it. The image build's `agy --version` assert now runs **through the wrapper**
(`agy pin ok: 1.1.13 (416b197e…)`), which is also the proof that the wrapper is
transparent.

### FIX-3 — Product-B state isolation, and host mode refused (SMOKE-3)

Two mechanisms.

**a) The runner refuses `--subject-isolation host` for any Product-B leg.**
`assert_product_b_isolation` raises a `RunnerError` naming the offending legs and citing
SMOKE-3. Container is the only admissible mode for agy. `--dry-run` is exempt (stub
adapter; never launches the product). Four unit tests cover C3, C5's executor leg, the
container-allowed case, and P0 being unaffected.

**b) Per-run state, verified by looking at what the product actually got.**
`~/.gemini/antigravity-cli/` on the host holds `brain/` (per-workspace memory written by
earlier interactive sessions, containing this repo's absolute host path) and a
`settings.json` whose `trustedWorkspaces` names the same path — two independent
redirect vectors. The wrapper therefore builds a **fresh `mktemp` `$HOME` per
invocation** holding only the token, the installation id, and a **synthesized**
`settings.json`. Observed inside the real image, with the real mounts, by pointing
`LAB_AGY_REAL` at a script that dumps what it was handed:

```
HOME=/tmp/agy-state.czcyhW1F
AUTOUPD=1
antigravity-oauth-token  installation_id  settings.json
--- settings.json seen by the product ---
{ "enableTelemetry": false,
  "trustedWorkspaces": [ "/subject" ],
  "gcp": { "project": "vital-octagon-19612", "location": "global" } }
```

No `brain/`, no `conversations/`, no `history.jsonl`; `trustedWorkspaces` forced to the
container's subject root; the operator's gcp routing carried over rather than invented.
And in the live C3 run **the lab working copy stayed clean** — `git status` shows only
this branch's own edits and the new results directories.

One related fix worth naming: the adapter set `AGY_CLI_DISABLE_AUTO_UPDATE` on the
**docker CLI's** environment, not the container's, so it never reached the product in
container mode. It is now both an image `ENV` and an `export` in the wrapper;
`AUTOUPD=1` above is the product-side proof.

### FIX-4 — collector contamination guard

Before writing anything, `backfill_run` checks two things and merges the verdicts:

* **Plausibility ceiling** — input-side tokens (`input` + `cache_read_input` +
  `cache_write_1h_input`) per model against a configurable ceiling, default
  **3,000,000**. Cache reads count: a contaminated window can arrive entirely as cache
  reads, and checking only the plain input class would wave it through.
* **Baseline probe** — the 300 s immediately before and after the guarded window must
  contain **zero** points on the subject models. Steady background traffic is invisible
  to any ceiling; it looks exactly like a long run. A probe that *errors* is treated as
  contaminated: an unverifiable quiet window is not a quiet one.

Either trips → **nothing is written**. No event is appended, `usage` stays
`unavailable` (never zero), the run's status is `contaminated_window`, and
`PROVIDER-BACKFILL-REFUSED.json` is written beside the run carrying the full evidence,
explicitly labelled as **not** that run's usage. The collector exits **4** — distinct
from **1** (the collector broke), so the driver can tell "needs a quiet window" from
"needs a fix". Fifteen unit tests cover both criteria, the probe-error case, the
exit code, and that `events.jsonl` is byte-identical after a refusal.

Exercised against the original smoke's real contaminated window (§5).

### FIX-5 — driver defers a Gemini leg rather than running blind

`scripts/screening-batch1-driver.sh` gained `await_quiet`, called before every arm in
`GEMINI_ARMS="C3 C3-med C3-prev C5"`: probe the trailing 10 minutes; if third-party
series are present, wait and retry 3× at 5-minute spacing; if still noisy, mark the arm
`deferred-contaminated`, append it to `$BATCH_DIR/deferred-contaminated.tsv`, and
continue the batch. The end-of-run log dumps that file and says plainly that a deferred
cell is **a HOLE in the registered matrix** — never to be filled by widening a window or
a filter.

## 3. New defect found and fixed by the re-smoke: the gate was grading blind

**FIX-1 broke the deterministic gate, silently.** The agent's edits reach the gate
through a named Docker volume; that volume is now owned by the agent's uid, while the
gate image runs as root. Git's `safe.directory` guard then refuses the repo —
`fatal: detected dubious ownership` — and every git call in `check-public.sh` is written
with `2>/dev/null` or `|| true`. A refused repo therefore returns **empty**, which is
indistinguishable from a clean tree. Consequences:

* **P6-diff-scope passed vacuously.** The check that catches an agent editing tests or
  files outside its write scope reported "only allowed path(s) changed vs pin" for a
  tree it could not read.
* **The pristine-restore did nothing.** `git checkout -- .` and the per-path restores
  that neutralise test tampering before P1–P4 run were no-ops, so an agent that edited
  the tests would have been graded against its own edits.

Demonstrated directly: an agent-side edit to `src/tests/prisma-mock.ts`, graded by the
pre-fix gate → `P6-diff-scope pass`. Graded by the fixed gate → `P6-diff-scope fail:
unexpected changes (incl. any test-file edit): src/tests/prisma-mock.ts`, and
P2-regression back to pass because the restore now actually restores.

**The fix is a new first check, `G0-subject-readable`,** which runs *before* any
diff-scope judgement. It trusts this one path via `GIT_CONFIG_*` env (never by writing
`safe.directory` into the operator's gitconfig, which would silence the same guard for
every repo on the machine); if git still cannot read the tree it **fails the gate** and
emits a report saying `nothing was graded`, rather than passing. Three tests cover the
fail path, the ordering, and the env-not-gitconfig property.

**Scope of the damage:** only container-mode runs are affected, and only the two P0 runs
in §1 marked *gate verdict void*. Host-mode runs — every batch-1/2/3 result — are
unaffected: there the tree is owned by the same user that runs the gate, so git never
refused it. The valid runs in §1 all carry `G0-subject-readable pass`.

## 4. Second defect: container-mode runs had no provenance diff

`_archive_agent_diff` ran `git -C <subject_dir>` on the host. In container mode the tree
is a Docker volume with no host path, so `subject_dir` is empty and **no
`agent-solution.diff` was written at all** — the gate verdict was the only evidence the
agent had changed anything, which is exactly the evidence §3 had just shown could be
vacuous. `_archive_agent_diff_container` now takes the same snapshot inside the gate
image (offline, same pre-gate timing, same untracked-file handling), reading it from
stdout so the root-run gate cannot leave a root-owned file in the results dir.

## 5. Backfill, and the guard in both directions

**Clean window — the valid C3 run.** Probed QUIET at 04:08 UTC, ran 04:08:21–04:13:34,
backfilled with the guard enabled:

```
guard:  ceiling  1,253,485 input-side < 3,000,000            -> clean
        baseline pre  04:02:22–04:07:22  0 points            -> clean
                 post 04:14:34–04:19:34  0 points            -> clean
status: backfilled
main:   input_tokens 1,253,485   output_tokens 17,379
```

Recorded as `confidence: derived` with `cost_basis_qualifier:
cache_blind_upper_bound` — the counts are authoritative meter readings, the
*attribution to this run* is derived from a serialized window, and the provider does not
expose a cache split so no cache discount can be claimed. `marginal_operating_usd`
stays `unavailable`: usage was backfilled, cost was not recomputed.

**Contaminated window — the original smoke's C3 run**, re-run through the same
collector at zero cost. All three criteria fired and the collector exited 4:

```
CONTAMINATED WINDOW — 1 run(s) NOT backfilled. The meter readings are real; they are not these runs'.
  pilot-realworld-draft-articles__C3__rep1__20260817T024401
    - gemini-3.7-flash: 10993105 input-side tokens exceeds the ceiling of 3000000
    - pre-run baseline 02:38:10–02:43:10 NOT quiet: 5 points, input 176,672 / output 4,554
    - post-run baseline 02:54:08–02:59:08 NOT quiet: 6 points, input 1,274,568 / output 13,846
  -> nothing was written; their Product-B usage stays 'unavailable', not zero.
```

Verified afterwards: `events.jsonl` has no backfill event, `usage.input_tokens` is still
`(None, unavailable)`, and `PROVIDER-BACKFILL-REFUSED.json` carries the evidence. This
is the number the original smoke would have written onto a ten-minute run — a factor of
roughly 200 too large.

## 6. Window state, for the record

* **03:18 UTC (human-reported, pre-re-smoke):** the only Gemini series in the project
  was a single **167-output-token** point — smoke-scale, not interactive. Both
  schedulers paused; the `StreamRawPredict` bursts had ceased.
* **03:49 UTC (FIX-5 probe, verbatim in `quiet-probe-pre.txt`):** **NOISY** — 721,068
  tokens in the trailing 10 minutes, ~120k input/minute of `gemini-3.7-flash`,
  continuous from ~03:34. Interactive third-party traffic had resumed. No Gemini leg was
  started.
* **04:08 UTC (FIX-5 probe, immediately before C3):** **QUIET** — 0 tokens in the
  trailing 10 minutes. The C3 leg ran only after this probe.

The 03:18 observation therefore did **not** hold through to the re-smoke, and FIX-5 is
the reason that mattered rather than corrupting a run: the probe caught the resumption
and the arm waited.

## 7. Spend

| Run | Marginal cost (known floor) |
|---|---|
| `…P0…035008` | $0.5665 |
| `…P0…035330` | $0.6482 |
| `…P0…040429` | $0.8169 |
| `…C3…040821` | `unavailable` (Product B; usage backfilled, cost not recomputed) |
| **Re-smoke total** | **$2.03 of the $3 grant** |
| Cumulative in `results/smoke-screening/` | $2.83 |

The runner's `--spend-cap-usd` counts all sibling runs under the output root, so the C3
leg was invoked with `3.79` = the original smoke's realized $0.79 plus the human's $3
re-smoke grant. That is the authorized ceiling expressed in the runner's units, not an
increase.

Two things to notice, neither of them a measurement: the three P0 costs **rise
monotonically** ($0.57 → $0.65 → $0.82) across identical cold reps of the same task, and
the Product-B leg's 1.25M input tokens for a ~5-minute run are cache-blind. Both are
reasons the screening batch needs its full rep count before anything is read as a
result.

## 8. What is NOT fixed here

Deliberately carried into the checkpoint packages rather than patched pre-approval:

1. W3 `task_id` mismatch — manifest `w3-sqlfluff-dialect-common-migration` vs task.yaml
   `w3-sqlfluff-segment-method-migration`.
2. Task `configurations:` lists diverge from the registered matrix.
3. `VALID_CONFIGS` lacks `C3-med`, `C3-prev`, `P2`; `_RUN_DIR_RE`'s `[A-Z0-9]+` will not
   match `C3-med`.
4. Four `PENDING-FREEZE` sealed artifacts.

Each blocks the screening batch and each is a human decision, not a fix to make quietly.
