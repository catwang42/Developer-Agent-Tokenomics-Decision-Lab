# Model-pin resolution — Product A strong/economical pair (screening window)

**STATUS: AUTHORITATIVE** for the screening-window Product-A model pins (2026-08-16).
Supersedes nothing; the batch-1/2/3 pins remain authoritative for their own batches.

**Date:** 2026-08-16 · **Spend:** two pre-approved micro-invocations, **$0.2014 total**
against a $0.30 cap (human pre-approval, this session) · **Scope:** identity and usage-shape
resolution only. These are *smoke* invocations (`"say ok"`), **not** benchmark runs: they
produce no task, no gate, no run summary, and nothing here is a performance or cost
comparison between models.

## What was run (exactly once each, verbatim commands)

```
claude -p "say ok" --model claude-opus-5     --output-format json
claude -p "say ok" --model claude-sonnet-4-6 --output-format json
```

Environment: Product A CLI `2.1.233`, `CLAUDE_CODE_USE_VERTEX=1`, project
`vital-octagon-19612`, `CLOUD_ML_REGION=global`. The `claude-sonnet-4-6` fallback alias
(`sonnet`) was **not needed** — the explicit id resolved on the first attempt.

## Finding 1 — both models resolve; neither exposes a dated version

The product reports the model it served in two places, and both give the **bare id**:

| Requested `--model` | `modelUsage` key (verbatim) | `canonicalModel` | `provider` |
|---|---|---|---|
| `claude-opus-5` | `claude-opus-5` | `claude-opus-5` | `vertex` |
| `claude-sonnet-4-6` | `claude-sonnet-4-6` | `claude-sonnet-4-6` | `vertex` |

**No fully versioned ID exists to record.** Confirmed independently from the provider's
own metadata (a free `GET publishers/anthropic/models`, no inference):

```
publishers/anthropic/models/claude-opus-5      versionId=default    launchStage=GA
publishers/anthropic/models/claude-sonnet-4-6  versionId=default    launchStage=GA
publishers/anthropic/models/claude-haiku-4-5   versionId=20251001   launchStage=GA
```

Vertex publishes a dated snapshot for `claude-haiku-4-5` but only `@default` for the two
models pinned here. Per SPEC §6.3 we record the label the product guarantees and **do not
infer a backend version it does not** — so the manifest pins `claude-opus-5@default` and
`claude-sonnet-4-6@default`, carrying the same floating-alias reproducibility caveat
already recorded for `claude-sonnet-4-6@default` in batch 3: the build behind `@default`
is not guaranteed stable across a batch. Mitigation is unchanged — every run records the
concrete metered id from the product's `modelUsage` keys, so a run is reproducible
*post hoc* even though the alias is not stable *a priori*. If Vertex later publishes dated
snapshots for these models, re-pinning to them is a manifest change, not a code change.

## Finding 2 — both usage shapes carry the four billed token classes

`harness/telemetry/costing.py` bills exactly four classes (`input`, `cache_write`,
`cache_read`, `output`). Both models returned identical key sets, in both the top-level
`usage` object (snake_case) and the per-model `modelUsage` object (camelCase), and both
map cleanly onto `claude_code._USAGE_MAP` / `_MODEL_USAGE_MAP`:

| Costing class | top-level `usage` key | `modelUsage` key |
|---|---|---|
| `input_tokens` | `input_tokens` | `inputTokens` |
| `output_tokens` | `output_tokens` | `outputTokens` |
| `cache_creation_tokens` | `cache_creation_input_tokens` | `cacheCreationInputTokens` |
| `cache_read_tokens` | `cache_read_input_tokens` | `cacheReadInputTokens` |

No adaptation of costing was needed and none was made.

Full verbatim key set of the top-level `usage` object (both models identical):
`input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `output_tokens`,
`output_tokens_details` (`{thinking_tokens}`), `server_tool_use`
(`{web_search_requests, web_fetch_requests}`), `service_tier`, `cache_creation`
(`{ephemeral_1h_input_tokens, ephemeral_5m_input_tokens}`), `inference_geo`, `iterations`,
`speed`.

Full verbatim key set of each `modelUsage` entry (both models identical): `inputTokens`,
`outputTokens`, `cacheReadInputTokens`, `cacheCreationInputTokens`, `webSearchRequests`,
`costUSD`, `contextWindow`, `maxOutputTokens`, `canonicalModel`, `provider`.

Two fields worth naming for later work, neither of which changes the shape:

- `output_tokens_details.thinking_tokens` — reported (`0` on both smokes, which say
  nothing about behaviour on real tasks) and **not currently mapped** into our schema's
  `reasoning_tokens` class. Wiring it is a separate change, out of scope here.
- `cache_creation.{ephemeral_5m_input_tokens, ephemeral_1h_input_tokens}` — the product
  splits cache writes by TTL, while our schema and the Vertex list rate card have a single
  cache-write class. Both smokes wrote 5m-TTL cache only. If a 1h-TTL write ever appears
  at a different rate, cache-write costing needs a TTL split; recorded here so it is not
  discovered inside a priced batch.

## Verbatim JSON (evidence)

`claude-opus-5`:

```json
{"is_error":false,"duration_api_ms":1836,"num_turns":1,"stop_reason":"end_turn","session_id":"0dbde385-b0cb-4a69-b842-35bb28258395","total_cost_usd":0.1185225,"usage":{"input_tokens":2,"cache_creation_input_tokens":18946,"cache_read_input_tokens":0,"output_tokens":4,"output_tokens_details":{"thinking_tokens":0},"server_tool_use":{"web_search_requests":0,"web_fetch_requests":0},"service_tier":"standard","cache_creation":{"ephemeral_1h_input_tokens":0,"ephemeral_5m_input_tokens":18946},"inference_geo":"","iterations":[],"speed":"standard"},"modelUsage":{"claude-opus-5":{"inputTokens":2,"outputTokens":4,"cacheReadInputTokens":0,"cacheCreationInputTokens":18946,"webSearchRequests":0,"costUSD":0.1185225,"contextWindow":200000,"maxOutputTokens":64000,"canonicalModel":"claude-opus-5","provider":"vertex"}},"permission_denials":[],"terminal_reason":"completed","subtype":"success","api_error_status":null,"result":"ok","ttft_ms":2130,"type":"result","duration_ms":2181}
```

`claude-sonnet-4-6`:

```json
{"is_error":false,"duration_api_ms":3725,"num_turns":1,"stop_reason":"end_turn","session_id":"c436382d-aebc-41a2-8cd7-28a049ed0b59","total_cost_usd":0.08282025,"usage":{"input_tokens":3,"cache_creation_input_tokens":22067,"cache_read_input_tokens":0,"output_tokens":4,"output_tokens_details":{"thinking_tokens":0},"server_tool_use":{"web_search_requests":0,"web_fetch_requests":0},"service_tier":"standard","cache_creation":{"ephemeral_1h_input_tokens":0,"ephemeral_5m_input_tokens":22067},"inference_geo":"","iterations":[],"speed":"standard"},"modelUsage":{"claude-sonnet-4-6":{"inputTokens":3,"outputTokens":4,"cacheReadInputTokens":0,"cacheCreationInputTokens":22067,"webSearchRequests":0,"costUSD":0.08282025,"contextWindow":200000,"maxOutputTokens":32000,"canonicalModel":"claude-sonnet-4-6","provider":"vertex"}},"permission_denials":[],"terminal_reason":"completed","subtype":"success","api_error_status":null,"result":"ok","ttft_ms":4037,"type":"result","duration_ms":4066}
```

The `total_cost_usd` / `costUSD` figures above are the **product's own** cost report, kept
as spend provenance against the approved cap. They are not our derived cost and are not a
price source; rates come from the pinned pricing snapshot only.

## What this does NOT establish

- Nothing about either model's quality, speed or cost on real work. A 4-token reply is a
  connectivity check, not a measurement.
- Nothing about `@default` stability across the screening window (unknowable a priori).
- Nothing about Product B: no `agy` invocation was made this session.
