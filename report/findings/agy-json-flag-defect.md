# The agy usage block was never requested — instrument defect 7 (2026-08-22)

**STATUS: AUTHORITATIVE** for what Product-B usage capture did and did not do
(2026-08-22). Supersedes nothing. Dataset-independent: this describes the
*instrument*, and it bears on every dataset that contains a Gemini leg.

**Date:** 2026-08-22 · **Spend:** none (a `--help` read and an offline archive scan;
no model was invoked, no run was re-executed, no file under `results/` was touched)
· **Scope:** `harness/adapters/agy.py` on agy 1.1.13. Nothing here compares products
or models. Self-caught: found by reading the adapter, not by a failing run.

## 1. The defect

`build_command` never passed `--output-format json`. Per `agy --help` (1.1.13) that
flag takes `text|json|stream-json` and **defaults to `text`**, so every headless agy
invocation the lab has ever made printed prose. `AgyAdapter.run_attempt` then did
`json.loads(proc.stdout)` inside a `try`, caught the inevitable `JSONDecodeError`,
set `payload = None`, and `usage_from_agy_json(None)` marked all six token classes
`unavailable`.

The failure was silent by construction: `unavailable` is the *correct* value for a
class a product does not expose, so a defect that made the product expose nothing
was indistinguishable, downstream, from a product that exposes nothing.

**Evidence, one line:** 0 of the 153 archived `invocation.txt` files across the four
screening datasets carries an agy usage block. (91 of those 153 contain an agy leg;
the 15 files in the set that do contain a `"usage"` object are all `__C5__` runs, and
in every case the block belongs to the Product-A planner leg, not to agy.)

**agy does expose usage.** Verified 2026-08-22 on 1.1.13 under `--output-format json`:

```json
"usage":{"input_tokens":12733,"output_tokens":31,"thinking_tokens":30,
         "cache_read_tokens":0,"total_tokens":12764}
```

### 1.1 The second defect, behind the first

`usage_from_agy_json` looked up the canonical schema name `reasoning_tokens`. agy
emits `thinking_tokens`. Passing the flag alone would have started capturing input
and output while still silently dropping the thinking class — a partial capture that
looks complete. The alias is now mapped, and the field records `source_key` so the
product key a number actually came from stays inspectable rather than being laundered
into our vocabulary. Any usage key that maps to no class of ours (today:
`total_tokens`) is preserved verbatim on the `model_call_completed` event under
`unmapped_usage_keys`, so the next rename shows up in the archive as itself.

Unchanged, deliberately: `cache_creation_tokens` has no alias — it is genuinely
absent from agy's block and stays `unavailable`, never 0. The tier stays
`proxy_observed`; a product's self-report is not an authoritative meter, whatever it
is spelled.

## 2. What was built on top of the silence

The absence of Product-B usage was read as a property of the product. It was a
property of our command line. Four pieces of machinery exist because of it:

- **The provider-side token collector** (`harness/collectors/vertex_token_collector.py`,
  SPEC 2.9 item 1). Its opening sentence is *"Product B exposes no machine-readable
  usage in headless mode, so its token counts have to come from the billing plane."*
  That premise is false as stated; it was true of our invocation. **This docstring is
  not corrected here** — whether the collector's rationale, or the collector, should
  change is a human decision, not an adapter fix.
- **The quiet-window protocol** — serializing subject runs so that a Cloud Monitoring
  time window can be attributed to exactly one run, with the batch's own tokens
  landing in the next probe's trailing window (the self-exhaust limitation on record).
- **The contamination guard** — the per-run plausibility ceiling plus the
  before/after baseline probe, which refuses to write a number when a window cannot
  support one. It refused 31 of 77 batch-1 runs under the v1 ceiling.
- **The v1 → v2 → v3 attribution rules** — `time_window_serialized_runs`, then
  `serialized_run_ownership_with_ingestion_tail`, then the same window under a
  rate ceiling (`serialized_run_ownership_with_rate_ceiling`). Three successive
  attempts to make a time-window inference carry a per-run cost.

None of that work is invalidated by this finding: the billing plane remains the only
*authoritative* meter, and a product self-report would have entered at
`proxy_observed` regardless. What changes is that the two sources would have been
independent and mutually checkable, and for the whole screening window there was only
one. That is the load-bearing consequence — a derived attribution that nothing could
corroborate.

## 3. Bearing on the 2026-08-16 cache-blindness decision — for human review

`manifest/delivery-manifest.yaml` `notes.gemini_cache_blindness` records a HUMAN
DECISION of 2026-08-16, **accepted with no probe run**, that Product-B costing for
the screening window is cache-blind: every Gemini leg carries
`cost_basis_qualifier: cache_blind_upper_bound`, on the basis that the provider-side
metric emits only `type=input` and `type=output` for `publisher="google"` and that
`explicit_caching` appears on zero google series
(`report/findings/vertex-token-metric-surface-2026-08-16.md` finding 2).

That evidence is about the **provider metric surface** and remains true of it. What
is new is that **the product itself exposes `cache_read_tokens`** — a second surface
the decision did not consider, because at the time we had no reason to think the
product exposed anything. The decision's own scope note says a Gemini leg's
`cache_read_tokens` "have no provider-side series to fill them"; that remains
accurate, and is now not the whole picture.

Three things follow, and all three are the human's:

1. Whether `cache_blind_upper_bound` is still the right qualifier for **future**
   Gemini legs, now that a product-reported cache-read count is available at
   `proxy_observed`.
2. Whether a product-reported `cache_read_tokens` may price a leg at all, given the
   rule that a self-report is not an authoritative meter — the direction of the error
   also flips: a cache-blind figure is an upper bound, and pricing cached input at
   the cache-read rate is only sound if the self-report is trusted.
3. Nothing at all for **past** legs, which have no such number and never will (§4).

**No pin is changed by this finding.** The manifest, `manifest/cp-findings.md`, and
every `cost_basis_qualifier` are untouched. This section is a flag, not an amendment.

## 4. Recovery from the archives is impossible

There is nothing to re-parse. The archived `invocation.txt` files hold agy's prose
stdout verbatim, and prose is what the product was asked for — the usage block was
never generated, so it is not hiding anywhere in the artifacts, the event logs, or
the run summaries. No offline pass can recover it, the way the offline regrade
recovered gate verdicts from archived diffs.

Consequently: **pricing any Gemini cell from the product's own report requires
re-running that cell.** Every existing Gemini number stays exactly as the archive
records it — provider-side, `derived` attribution, cache-blind, or `unavailable`
where the guard refused. This finding licenses no re-statement of any of them.

## 5. Sequence

Numbered **7** in the lab's self-caught instrument defects, after:

| # | Defect | Recorded in |
|---|---|---|
| 1 | Untracked files missing from the archived agent diff | `manifest/cp-spend-batch3-plan.md` §1 |
| 2 | No per-leg `invocation.txt` (raw provenance not inspectable) | *ibid.* |
| 3 | Bogus `run` positional in the agy invocation | *ibid.* |
| 4 | Task config declarations not reconciled against the runner | *ibid.* |
| 5 | Agent diff archived *after* the gate could mutate the subject | *ibid.* |
| 6 | Gate grading blind — dubious-ownership git refusal read as a clean tree | `report/smoke-screening/re-smoke/re-smoke-report.md` §3 |
| **7** | **agy never asked for JSON, so no product usage was ever captured** | **this document** |

(The re-smoke also fixed the missing container-mode provenance diff in the same pass,
§4 of that report; it is folded into row 6 rather than numbered separately. If the
human's ledger counts it on its own, this defect is 8 — the ordinal is the only thing
that moves.)

Defects 1–6 were found by running the instrument. This one was found by reading it,
which is the only way a defect whose symptom is a correctly-spelled `unavailable`
was ever going to be found.

## 6. What changed in this pass

| Change | File |
|---|---|
| `--output-format json` on every agy invocation; docstring records why, and why `stream-json` is a human decision | `harness/adapters/agy.py` |
| `thinking_tokens` accepted as an alias for `reasoning_tokens`, with `source_key` provenance | *ibid.* |
| `unmapped_usage_keys` preserved verbatim on `model_call_completed` | *ibid.* |
| 15 regression tests: the flag, both spellings, neither spelling, unmapped keys, the no-output path | `tests/test_agy_adapter.py` |

Not changed: any manifest pin, `manifest/cp-findings.md`, the collector, any file
under `results/`. No run was executed.
