# transfer-probe, ABORTED 2026-08-30 — unauthenticated agent legs

**These are instrument failures, not measurements.** Nothing in this directory is a
result. No number here may be read, pooled, ranked, averaged or cited — not as an R9
figure, not as a zero, not as a bound. The runs completed and wrote `result.json`, but
the subject agent was never reached: every model call failed authentication before any
inference happened.

This dataset exists as provenance for eleven R9 run directories that were produced and
then quarantined the same night, following the precedent of
`screening-batch1-aborted-20260817-gatefix/`. Nothing was deleted and nothing was edited;
the directories are exactly as the runner wrote them.

## What happened

Every one of the 36 billing legs across all 11 runs returned, in roughly 300 ms:

```
"result": "Not logged in · Please run /login"
"terminal_reason": "api_error"     exit_code: 1
input_tokens: 0   output_tokens: 0   total_cost_usd: 0
```

**Known spend for this entire dataset: $0.0000.** Zero tokens were consumed. No request
reached a provider. The `agent-solution.diff` of every run is 0 bytes.

## Root cause

The launch environment lacked three provider-routing variables:

- `CLAUDE_CODE_USE_VERTEX`
- `ANTHROPIC_VERTEX_PROJECT_ID`
- `CLOUD_ML_REGION`

`harness/container/exec.py` (`AGENT_ENV_PASSTHROUGH`) forwards these from host to agent
container **only if they are present in the launching process's environment**; it does
not default them. The batch was launched from a detached shell that did not export them.
Without `CLAUDE_CODE_USE_VERTEX=1` the in-container `claude` CLI does not route to Vertex,
finds no consumer login inside the container, and exits immediately.

The credential *mounts* were correct and identical to the successful 2026-08-27 R6/R10
batch — the host gcloud ADC was mounted read-only at `/creds/gcloud` exactly as before.
Only the routing env differed. Comparing the container argv of
`w4-realworld-missing-user-id__R6__rep1__20260828T012505` (worked) against
`...__R9__rep1__20260830T141104` (this dataset) shows the three variables present in the
former and absent in the latter, with every other flag and mount identical.

Product version on every leg: `2.1.233`.

## Why this was not caught by validation

Each run passed `validate: PASS (audit-grade)`. That is correct behaviour and not a
defect: the validator checks schema conformance, and a run whose ladder exhausts is
schema-valid. The failure surfaces only in `acceptance.result: rejected` with
`failures_by_category: {ladder_exhausted: 1}`, and in the per-leg `invocation.txt`.

It also means the cells **settled**: `completed_cells()` in
`harness/runner/transfer_probe.py` treats any directory holding a `result.json` as bought
and never retries it. Leaving these directories in `results/transfer-probe/` would have
made all nine R9 slots permanently unrunnable, because that function does not read
`adjudication.json` — a void adjudication would not have freed them. Moving them out of
the dataset directory is what lets the slots be re-bought, which is why this quarantine
directory exists rather than an in-place void.

## The eleven runs

Three of the rep1 attempts are for the same slot (W4/R9/rep1). Two came from a false
start at ~22:04 SGT that was killed about two minutes in; the third came from the
relaunch, which re-ran that slot because the first two had been moved aside at the time
it took its settled-cells snapshot. All three failed identically, at $0.

| run dir | task | legs | exit | "Not logged in" | api_error | tokens | cost | acceptance |
|---|---|---|---|---|---|---|---|---|
| `w4-realworld-missing-user-id__R9__rep1__20260830T140447` | W4 | 3 | 1 | 3/3 | 3/3 | 0 | $0.00 | rejected |
| `w4-realworld-missing-user-id__R9__rep1__20260830T140548` | W4 | 3 | 1 | 3/3 | 3/3 | 0 | $0.00 | rejected |
| `w4-realworld-missing-user-id__R9__rep1__20260830T141104` | W4 | 3 | 1 | 3/3 | 3/3 | 0 | $0.00 | rejected |
| `w4-realworld-missing-user-id__R9__rep2__20260830T141336` | W4 | 3 | 1 | 3/3 | 3/3 | 0 | $0.00 | rejected |
| `w4-realworld-missing-user-id__R9__rep3__20260830T141634` | W4 | 3 | 1 | 3/3 | 3/3 | 0 | $0.00 | rejected |
| `w6-hono-router-review__R9__rep1__20260830T141919` | W6 | 4 | 1 | 4/4 | 4/4 | 0 | $0.00 | rejected |
| `w6-hono-router-review__R9__rep2__20260830T141943` | W6 | 4 | 1 | 4/4 | 4/4 | 0 | $0.00 | rejected |
| `w6-hono-router-review__R9__rep3__20260830T142010` | W6 | 4 | 1 | 4/4 | 4/4 | 0 | $0.00 | rejected |
| `w4b-zarr-consolidated-order__R9__rep1__20260830T142034` | W4b | 3 | 1 | 3/3 | 3/3 | 0 | $0.00 | rejected |
| `w4b-zarr-consolidated-order__R9__rep2__20260830T142110` | W4b | 3 | 1 | 3/3 | 3/3 | 0 | $0.00 | rejected |
| `w4b-zarr-consolidated-order__R9__rep3__20260830T142138` | W4b | 3 | 1 | 3/3 | 3/3 | 0 | $0.00 | rejected |

The W4b runs took roughly 30 seconds each against a 2700 s soft budget — a further sign,
had anyone been watching the clock, that no inference was happening.

## Ledger note

`results/transfer-probe/driver-ledger.jsonl` is append-only provenance and was **not**
edited. It therefore still carries the nine `"action": "ran"` lines this aborted batch
produced, interleaved with its 18 `"skipped-settled"` lines, followed by the lines from
the clean re-run. The nine aborted lines are identifiable by the run directories they
name, all of which now live here. An earlier false start also appended ledger lines that
were lost when the working tree was reset with `git reset --hard origin/main`; those
lines are not recoverable and are recorded as lost rather than reconstructed.

`results/transfer-probe/TIMING-PROFILE.md` was rewritten by this batch's timing marker.
Its content is correct for the re-run as well — same profile, same Amendment 5 override
reason — so it was left as written rather than edited.

## Relationship to the real R9 data

The nine R9 slots were re-bought after the environment was fixed. That data lives in
`results/transfer-probe/` and is the only R9 data. This directory is never pooled with
it, and the two are not two attempts at the same slot in the supersession sense: an
unauthenticated no-op is not an attempt at a measurement.
