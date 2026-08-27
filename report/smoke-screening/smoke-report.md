# Screening smoke — container agent leg + provider-side collector, first live test

**STATUS: AUTHORITATIVE** for `results/smoke-screening/` (2026-08-17).
Documents that dataset and nothing else. This is a **feasibility smoke, not a
measurement**: no number here is a product comparison, and none may leave this file
before CP-FINDINGS.

> **Dataset retired 2026-08-27.** `results/smoke-screening/` was removed from the working
> tree in the repo cleanup. Every `results/smoke-screening/…` path in this file and in
> `re-smoke/` resolves at the tag `pre-cleanup-2026-08-27`, where the runs are preserved
> unedited. Nothing in this report was changed.

**Run under:** `CHECKPOINT APPROVED: CP-SPEND (screening smoke, hard cap $5,
results to results/smoke-screening/)`.
**Actual spend: $0.79 of the $5 cap** (known floor; see §6).

## 0. Verdict in one paragraph

The smoke did its job: it found three defects that would each have corrupted the
132-run screening batch, and it found them for 79 cents. **The containerized agent
leg does not work for either product** — Product A's CLI refuses to run as root,
and Product B cannot authenticate inside the container (§2). Falling back to host
mode per the brief, Product A ran correctly end to end and produced real per-arm
cost actuals (§3), but **Product B escaped the staged subject tree and wrote into
the lab's own working copy** (§4) — a previously undetected isolation defect that
makes the C3 result an artifact and contaminated the next run's input. And the
**collector's quiet window is violated**, by a factor of roughly 200 (§5): the
backfill would have written 10,993,105 input tokens onto a ten-minute agy run.
**No Product-B usage was written.** Three posture/blocking decisions are the
human's; they are stated in §7.

## 1. What was run

Pilot task only (`tasks/pilot-realworld`), serialized, one run per arm, cold cache.
Ten launches in total: five in the registered `container` posture, then five in the
`host` fallback the brief authorizes, of which the last two did not complete.

Preflight, before the first launch:

| Check | Result |
|---|---|
| `agy --version` vs manifest pin `1.1.13` | **1.1.13** — match |
| `claude --version` (host) / image label | **2.1.233** — matches `subject_isolation.agent_leg.claude_cli_version` |
| `AGY_CLI_DISABLE_AUTO_UPDATE` | exported `=1` for every launch; recorded in each `invocation.txt` |
| `bash harness/container/verify-egress.sh` | PASS ×4 (no route without proxy; allowlisted host reachable; non-allowlisted refused; non-443 CONNECT refused) |
| egress allowlist `sha256` vs manifest pin | `ce78aa16…75e2c` — match |
| images | `lab-subject-agent/pilot-realworld-draft-articles:30b68e1e8814` and `lab-subject/…` built for this smoke |

## 2. SMOKE-1 and SMOKE-2 — the containerized agent leg fails for BOTH products

All five container runs ended with the agent leg at **exit 1**, **no
`agent-solution.diff` written**, and **$0.00 billed** — both CLIs refuse before
reaching a model. The gate then graded an unmodified tree, so every one of them
shows `P1-public-test: fail` and `result: error`. Those five rows are evidence about
the harness, **not** about either product's ability to do the task.

| Run | Arm | Posture | Agent exit | Failure |
|---|---|---|---|---|
| `…__P0__rep1__20260817T023044` | P0 | container | 1 | SMOKE-1 |
| `…__C2__rep1__20260817T023142` | C2 | container | 1 | SMOKE-1 |
| `…__C3__rep1__20260817T023241` | C3 | container | 1 | SMOKE-2 |
| `…__C3-med__rep1__20260817T023438` | C3-med | container | 1 | SMOKE-2 |
| `…__C5__rep1__20260817T023639` | C5 | container | 1 | conductor SMOKE-1, executor SMOKE-2 |

### SMOKE-1 — Product A refuses `--dangerously-skip-permissions` as root

```
stderr: --dangerously-skip-permissions cannot be used with root/sudo privileges
        for security reasons
```

`harness/container/Dockerfile.subject` declares no `USER` and
`harness/container/exec.py` passes no `--user`, so the agent container runs as
**root**, and the CLI's own guard fires. Affects every Product-A leg: P0, C2, P1,
P2, and C5's conductor. Verbatim argv and stderr:
`results/smoke-screening/…__P0__rep1__20260817T023044/invocation.txt`.

**Not an egress problem** — nothing reached the network.

### SMOKE-2 — Product B has no non-interactive credential path in the container

```
stderr: Authentication required. Please visit the URL to log in:
          https://accounts.google.com/o/oauth2/auth?...&redirect_uri=https%3A%2F%2Fantigravity.google%2Foauth-callback...
        Waiting for authentication (timeout 60s)...
        Error: authentication timed out.
        Error: authentication failed or timed out
```

The `-v ~/.gemini:/creds/gemini:ro` mount is not a credential source `agy` accepts;
it falls back to interactive OAuth and times out at 60 s. Affects C3, C3-med,
C3-prev and C5's executor.

**This one is a positive result for the allowlist.** `agy` reached
`accounts.google.com` *through the proxy* and got a real OAuth challenge back — the
egress path works; the credential path does not.

### Neither is fixable by the one allowlist addition the brief permits

SMOKE-1 needs a `USER` in the image (and a writable HOME/workdir for it); SMOKE-2
needs a non-interactive credential the product will accept. Both are container-build
changes, so per the brief they were **not** attempted here. §7 decision 1.

## 3. Host fallback — Product A works, and gives real per-arm actuals

Re-run with `--subject-isolation host`, stamping
`identity.permission_profile = SUBJECT_PROFILE_HOST` verbatim (`no-container;
no-fs-namespace; absolute-path-fs-access-NOT-confined; no-network-policy`) and
`identity.network_policy = "no-network-policy"`. That stamp is the honest record:
these runs had **no** egress allowlist in force.

| Run | Arm | Result | Wall | `agent-solution.diff` | Gate | Cost |
|---|---|---|---|---|---|---|
| `…__P0__rep1__20260817T024023` | P0 | **accepted** | 109 s | 1 495 B | 6/6 pass | **$0.4337** |
| `…__C2__rep1__20260817T024232` | C2 | **accepted** | 82 s | 1 549 B | 6/6 pass | **$0.3605** |
| `…__C3__rep1__20260817T024401` | C3 | rejected — **artifact, see §4** | 539 s | **0 B** | `P1-public-test` fail | `unavailable` |
| `…__C3-med__rep1__20260817T025310` | C3-med | **ABORTED** by operator ~100 s in | — | — | — | — |
| C5 | — | **never launched** | — | — | — | — |

Product-A usage is `authoritative` on every field, as expected from
`claude -p --output-format json`:

| Arm | input | output | cache_read | cache_write | cost | basis |
|---|---:|---:|---:|---:|---:|---|
| P0 (`STRONG_MODEL_A`) | 14 | 2 454 | 158 686 | 29 298 | $0.433743 | `marginal_api_cost` |
| C2 (`ECONOMICAL_MODEL_A`) | 6 | 1 220 | 87 673 | 52 654 | $0.360544 | `marginal_api_cost` |

Both Gemini legs correctly carry `cost_basis_qualifier: cache_blind_upper_bound`,
and their `cache_read_tokens`/`cache_creation_tokens` are `unavailable`, never `0`.

**Note for the batch estimate:** $0.43 and $0.36 are ~3× the batch-3 Product-A mean
of $0.138. Cache-write tokens dominate both. This is a two-file task; the screening
roster is harder. Carried into `manifest/cp-spend-screening-batch1.md`.

## 4. SMOKE-3 — Product B escaped the staged subject tree (the serious one)

`agy` exited **0** and reported, in prose, that it had made exactly the right edits.
`agent-solution.diff` was **0 bytes**, so the gate rejected the run.

Both are true, because it edited the wrong tree. Its own output names the paths:

```
src/prisma/schema.prisma
  file:///…/Developer-Agent-Tokenomics-Decision-Lab/tasks/pilot-realworld/.work/repo/src/prisma/schema.prisma
src/app/routes/article/article.service.ts
  file:///…/Developer-Agent-Tokenomics-Decision-Lab/tasks/pilot-realworld/.work/repo/src/app/routes/article/article.service.ts
```

That is the **lab repo's own working copy**, not the staged tree in `/var/tmp` that
FIX A puts outside the repo and that the harness diffs. Confirmed directly:

```
$ cd tasks/pilot-realworld/.work/repo && git status --short
 M src/app/routes/article/article.service.ts
 M src/prisma/schema.prisma
```

The edits were correct and complete (`andQueries.push({ draft: false })`,
`draft Boolean @default(false)`, `draft: Boolean(draft)`). Full evidence:
[`SMOKE-3-agy-escape-evidence.diff`](SMOKE-3-agy-escape-evidence.diff). The tree was
restored to pin `30b68e1e8814` immediately after capture.

**Three consequences:**

1. **The C3 rejection is an artifact, not a measurement.** Product B solved the
   task; the harness graded a copy it never touched. Any "Product B failed W-x"
   read from a run in this posture would be false.
2. **It leaked into the next run.** `…__C3-med__rep1__20260817T025310` staged from
   the contaminated tree — its input already contained the solution. The operator
   killed it ~100 s in; it holds one `run_started` event, no `summary.json`, no
   cost, and is labelled `ABORTED.md`. It is not a run and is counted nowhere.
   C5 was never launched.
3. **`--subject-isolation host` is not a safe fallback for Product B.** FIX A
   confines the subject by *relative* path; `SUBJECT_PROFILE_HOST` says so in its own
   text (`absolute-path-fs-access-NOT-confined`). Product A respects the staged cwd;
   Product B resolves an absolute workspace root and does not. This was invisible
   until now because no Product-B run had ever completed on the host path — batch 3
   dropped C3/C5 precisely because `agy` timed out.

The containerized posture would have **prevented** this: the lab repo is not mounted
into the agent container at all. SMOKE-3 therefore raises the value of fixing
SMOKE-1/SMOKE-2 rather than lowering it.

## 5. The collector's quiet window is violated — no usage was written

The brief's rule is to report the query, window and filter verbatim and not to widen
filters silently. The opposite failure occurred: the window returns far **too much**.

**Filter** (verbatim, as `build_filter` emits it):

```
metric.type = "aiplatform.googleapis.com/publisher/online_serving/token_count"
AND resource.type = "aiplatform.googleapis.com/PublisherModel"
AND resource.labels.publisher = "google"
AND resource.labels.model_user_id = "gemini-3.7-flash"
```

**Window** (the C3 host run, ±60 s guard):
`2026-08-17T02:43:10.209613Z` → `2026-08-17T02:54:08.765063Z`

**What `--dry-run` says it would write:**

```json
"legs_filled": {"main": {"input_tokens": 10993105, "output_tokens": 50764}}
```

**10,993,105 input tokens for one ten-minute agy run on a two-file task.** Priced at
the snapshot's $0.75/1M input that is **$8.24 for a single run** — more than the
whole $5 smoke cap, on an arm the runner recorded as `unavailable`. It is background
traffic, not ours.

**Backfill was NOT executed. Both Gemini legs remain `unavailable` with their
confidence tiers intact** (CLAUDE.md rules 1 and 3). The dry-run report is kept at
[`collector-plan-c3.json`](collector-plan-c3.json) with the numbers above quoted
here as *the contamination*, never as usage.

### Why the window cannot be narrowed

Two scheduler jobs were paused by the human before the smoke
(`agy-agent-catalog-refresh`, `ta-daily-trigger`, both verified `PAUSED`). Traffic
continued anyway:

```
2026-08-17T02:15:41Z gemini-3.7-flash input 829846
2026-08-17T02:20:41Z gemini-3.7-flash input 822038
2026-08-17T02:23:41Z gemini-3.7-flash input 770920
2026-08-17T02:24:41Z gemini-3.7-flash input 770929
```

Measured ingestion lag is 1–2 minutes, so these are live, not stale. A Vertex audit
log sample at 02:12:00Z attributes `PredictionService.StreamRawPredict` to principal
`catwangzz@google.com` — a human-account consumer, most plausibly an interactive
Antigravity/Gemini session open elsewhere. Confirming its exact model and user-agent
was blocked by the project's logging read quota (`RESOURCE_EXHAUSTED`, 60 reads/min,
consumed by another workload).

**There is no label to narrow on.** Every series on the subject model carries the
identical label set:

```
metric   : {request_type: shared, shared_request_type: standard, source: global, type: input|output}
resource : {location: global, model_user_id: gemini-3.7-flash, model_version_id: "", publisher: google}
```

`model_version_id` is empty; there is no caller, job or session label. This is the
collector README's own warning holding in practice: *nothing but the time window
separates a subject run from a background job on the same model.* Attribution is
possible only once the third consumer stops.

### Collector fixes verified live

Two defects found while preparing the smoke are fixed and regression-tested
(commit `490c21c`, `tests/test_vertex_collector.py`, 33 tests pass):

1. `build_filter` emitted `one_of("a" OR "b")`; Cloud Monitoring rejects that with
   **HTTP 400 "Could not parse filter"**, so *every* multi-model collection failed
   outright. The correct syntax is comma-separated.
2. `publisher` was hardcoded to `google`, so a C5 run's Anthropic conductor leg could
   never match — failing **silently**, returning nothing rather than erroring.

Both queries now return real series against `vital-octagon-19612`; the mixed-publisher
filter returns 7 series across both publishers. The query path is proven; only the
attribution is blocked.

## 6. Spend

| | |
|---|---|
| Cap approved | **$5.00** |
| Known spend floor | **$0.794287** over 8 completed runs |
| Legs with `unavailable` cost | 7 — real spend is **higher** than the floor |
| Where the unavailable legs are | 5 container runs (billed $0, both CLIs exited pre-API); 2 Gemini host legs (product exposes no usage; collector blocked by §5) |

The one genuinely uncounted amount is the C3 host run's Gemini spend: a ~9-minute
agy session, `unavailable` from the product and unattributable from the provider.
On the pinned rates a session of that size is on the order of cents, but that is an
expectation, not a measurement, and it is recorded as `unavailable` rather than
estimated.

## 7. Decisions for the human

1. **Isolation posture (yours, per the brief).** The registered screening posture is
   `container` + `allowlist`, a SPEC §5.1 hard precondition. It is currently
   non-functional for both products (§2), and the host fallback is now known to be
   **unsafe for Product B** (§4). The realistic options: (a) fix the image — add a
   non-root `USER` and a credential path `agy` accepts — and re-smoke; (b) run
   Product A containerized and Product B on the host with the escape accepted and
   stamped; (c) hold the batch. **(a) is the recommendation:** (b) knowingly records
   false rejections for every Product-B arm, which is half the matrix.
2. **The third Gemini consumer (§5).** Batch 1's Product-B legs are uncostable until
   it stops. `manifest/cp-screen-prereg.md` §7.3 carries this as blocking, and
   `scripts/screening-batch1-driver.sh` refuses to start on a noisy window.
3. **Resume the paused schedulers** only after the batch's final backfill — not yet.

## 8. What this report does NOT claim

No product comparison: the only two runs that completed honestly are P0 and C2, both
Product A, one rep each, on one task. No claim that Product B fails the pilot task —
§4 shows the opposite, that it solved it in the wrong directory. No Product-B cost
figure. No result is promoted anywhere before CP-FINDINGS.
