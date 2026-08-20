# Provider-side usage collectors

Product B exposes no machine-readable usage in headless mode (SPEC §2.9 item 1),
so its token counts have to come from the provider's own metering surface.
`vertex_token_collector.py` reads Cloud Monitoring's

```
aiplatform.googleapis.com/publisher/online_serving/token_count
  on monitored resource aiplatform.googleapis.com/PublisherModel
```

attributes points to a run by time window, and backfills the run's telemetry.

It never invokes a model. Running it costs nothing against a model budget, and it
needs no CP-SPEND approval; it does read a Google Cloud project's metrics, so it
needs `gcloud` credentials with monitoring-viewer rights.

## Confidence tiers — two different tiers, on purpose

| What | Tier | Why |
|---|---|---|
| the token **counts** | `authoritative` | the provider's own meter — the surface the bill is computed from |
| the **attribution** of those counts to a run | `derived` | a point is assigned to the run whose `[start - guard, end + guard]` window contains it |

The summary field carries the **weaker** of the two (`derived`), because that is
what is true of the number as recorded against a run. The authoritative-count
claim, the metric type, the window, and the `model_user_id` are written into the
run's event log, which is where an auditor should look. Do not restate the counts
as authoritative in a report without also stating the attribution basis.

## Type mapping

| metric `type` label | schema usage field |
|---|---|
| `input` | `input_tokens` |
| `output` | `output_tokens` |
| `cache_read_input` | `cache_read_tokens` |
| `cache_write_1h_input` | `cache_creation_tokens` |

**Everything else is unmapped, and unmapped means loud.** An unrecognised `type`
is never dropped, never zero-filled, and never folded into a mapped class. It is
recorded verbatim in the run's `provider_usage_backfill` event under
`unmapped_types` and printed at the top of the backfill report, above the JSON.

A mapped class with no points in the window is simply **absent** from the backfill
event, so the deriver records it `unavailable` — never `0` (CLAUDE.md rule 3).

Totals are summed by `type`, but every contributing series' full label set
(`modality`, `request_type`, `explicit_caching`, `source`, `location`,
`model_version_id`, …) is preserved per run under `series_breakdown`, so a later
analysis can re-cost by modality or region without re-querying.

### Known unmapped type in live data: `cache_write_input`

`cache_write_input` (5-minute TTL cache write) is a real, separate type value from
`cache_write_1h_input`, and the two are **priced differently**. The pinned mapping
above names only the 1h class, so the 5m class shows up as unmapped. That is
deliberate: merging them would silently mis-cost. Background:
[`report/findings/vertex-token-metric-surface-2026-08-16.md`](../../report/findings/vertex-token-metric-surface-2026-08-16.md)
finding 3.

**Resolved 2026-08-16 (human decision), on the pricing side, not here.**
`pricing/prices-2026-08-16.json` now carries **both** write rates as separate keys
per Claude model — `cache_write_5m` (1.25× input) and `cache_write_1h` (2× input),
with the legacy single `cache_write` key removed — and `costing.py` prices
`cache_creation_tokens` at **`cache_write_1h`**, matching the
`cache_write_1h_input` traffic this collector maps into that field. Each derived
cost records the key it used under `rate_keys`.

The mapping table above is therefore **unchanged**: if a `cache_write_input` series
is ever observed it stays **unmapped-and-loud** — reported, never merged, never
zero-filled — until a priced mapping is human-approved. A rate existing for the 5m
class is not permission to map it.

## Effort-level attribution: `model_user_id` **collapses** effort levels

Observed 2026-08-16 in project `vital-octagon-19612`: every Google-publisher
series names the bare model with an empty `model_version_id` —
`gemini-3.7-flash`, `gemini-3.6-flash`. There is **no** `-high`/`-medium` suffix
and no other label that varies with the selector's effort suffix.

**Therefore C3 vs C3-med attribution rests on serialization windows alone.** That
is acceptable — subject runs are serialized — but it is a stated dependency, not
an assumption. If two effort arms ever overlap in time, their tokens are
unseparable and must be recorded `unavailable`, not split by guesswork.

(By contrast, C3 vs C3-prev *is* label-separable: `gemini-3.7-flash` and
`gemini-3.6-flash` are distinct `model_user_id`s.)

## Cache classes: the pre-gate passes for Anthropic, not for Google

Over 2026-07-17 → 2026-08-16 this project's Google-publisher series carried only
`input` and `output` — zero cache-class series, and no `explicit_caching` label at
all. The cache-class evidence that passed the SPEC §2.9 pre-build gate comes from
**Anthropic** rows. Full evidence and caveats: finding 2 of the findings doc
linked above.

### The decision: Product-B costing this window is cache-blind

**Human decision, 2026-08-16 — accepted, no probe run.** Product-B (Gemini)
costing for the screening window is cache-blind. Every Gemini leg — solo
C3/C3-med/C3-prev *and* the C5 executor — is declared

```
cost_basis:            marginal_api_cost        # frozen schema enum, unchanged
cost_basis_qualifier:  cache_blind_upper_bound  # additive; how that basis was derived
```

pinned in `manifest/delivery-manifest.yaml` (`notes.gemini_cache_blindness`, and
`cost_basis_qualifier` on each `PRODUCT_B_*` configuration). The runner stamps it
onto every leg it appears on, and a run whose legs are mixed (C5) inherits the
qualification at the run level — a total containing one upper bound is an upper
bound.

Three consequences to state wherever a Product-B figure appears:

- **`cache_read_tokens` and `cache_creation_tokens` stay `unavailable`** on a
  Gemini leg — no series exists to fill them. They are never `0` (CLAUDE.md
  rule 3), and a cache-blind figure is not evidence that no caching occurred.
- **The error has a known direction: the figure is an UPPER BOUND.** Implicit
  provider-side caching, if it happens, bills the cached share at the cheaper
  cache-read rate, so real Gemini spend can only be **lower** than computed —
  never higher. The basis name says exactly this; do not restate a cache-blind
  figure as an exact cost.
- **Cross-product cache comparisons remain out of scope** (SPEC §2.9). A
  Product-A vs Product-B cache-efficiency claim is not derivable from a
  cache-blind Product-B figure and must not be made.

`cost_basis` itself is unchanged because the telemetry schema's enum is frozen at
four values; widening it is a CP-SCHEMA decision that has **not** been taken.
`cost_basis_qualifier` is additive (`legs[]` and `economics` accept additional
properties), and the runner only accepts qualifiers from a closed list
(`run.py:COST_BASIS_QUALIFIERS`) so a new one stays a human decision.

## Serialization + quiet-window rule — CP-SPEND checklist line

> **Collector quiet window:** subject runs are serialized (one at a time, no
> overlap), and for the duration of every collection window every other
> Gemini-calling workload in project `vital-octagon-19612` — including the
> `ta-daily` Cloud Run job — is either **paused** or **provably on a different
> `model_user_id`** than the run's declared subject models. Confirmed by name in
> the batch's CP-SPEND request.

This is not theoretical: the project already runs unrelated Gemini traffic, and
`gemini-3.7-flash`/`gemini-3.6-flash` themselves had non-subject traffic in the
observed window. The `model_user_id` filter excludes anything on a *different*
model; nothing but the time window separates a subject run from a background job
on the *same* model.

## Attribution rules: v1 (silence), v2 (ownership), v3 (rate ceiling)

`--attribution-rule` selects how a run's window is drawn, what the quiet probe
looks at, and which plausibility ceiling judges the total. All three rules keep
the same confidence tiers: counts authoritative, per-run attribution derived.

**v1 — `time_window_serialized_runs`** (the default, unchanged). A run's window is
`[start - guard, end + guard]`, and the `baseline_seconds` either side of it must
be *silent* on the subject models. Simple, and wrong in one direction: Cloud
Monitoring ingests this metric with a delay, so a run deposits some of its **own**
last points after its own window closes. v1 cannot tell that tail from a third
party and refuses the run. In screening batch 1, 8 of 43 refusals were runs
refused for their own tail — the post-probe totals were a fraction of the run's
own, with a dead-quiet pre-window.

**v2 — `serialized_run_ownership_with_ingestion_tail`.** Uses the fact the
CP-SPEND line above already asserts: the batch is *serialized*. Then each run owns
the meter from its own start until the next subject run's window opens:

```
[start_i - guard,  min(end_i + guard + tail,  start_{i+1} - guard) )
```

The v1 window, extended by an ingestion `tail` (default 300s), never reaching into
the next run's guard band. The quiet probes are kept but moved to the only region
where a third party is still distinguishable — the no-man's-land between one run's
ownership window and its neighbours'. Traffic there still refuses the run; a probe
the neighbours squeeze to nothing is reported `not_applicable`, not as silence.

v2 needs the **whole serialized batch** in the plan, because a run's boundary is
its neighbour's start. Collecting a subset against a partial plan would hand each
run its neighbour's traffic. Passing the full batch is safe: runs already
backfilled are skipped by the idempotence guard.

Two ways the ownership premise fails, both refused rather than papered over:

- the runs **overlap** (`start_{i+1} < end_i`) — the batch was not serialized
  there and no boundary exists;
- the runs are **closer than the guard bands** — the boundary exists but leaves
  the run no tail, so its late points land in its neighbour's window. Both runs
  are refused, because the meter cannot say which produced them.

v2 writes `provider_usage_backfill_v2` events, a distinct type from v1's. The two
rules can disagree about which run a point belongs to, so an analysis must be able
to say which rule it is reading; and the distinct type keeps a v2 pass append-only
with respect to an earlier v1 one.

**v3 — `serialized_run_ownership_with_rate_ceiling`.** The v2 window, the v2
ownership boundaries and the v2 third-party probe, all unchanged. The single
difference is the plausibility test.

v1 and v2 apply `--ceiling-input-tokens`: a **fixed per-run constant** (3M
input-side tokens). That constant conflates two different things. A window can be
over it because a stranger was on the meter, or because the run was simply long —
and a long executor run legitimately produces more input-side tokens than any
per-run constant allows. In screening batch 1, 31 of the 35 windows v2 still
refused were this second case: long Gemini-executor runs (10–48 minutes) whose
totals scaled with duration, from 3.2M over 603s to 16.4M over 2836s. The constant
was refusing duration, not contamination.

v3 applies `--ceiling-input-tokens-per-second` instead — input-side tokens divided
by the length of the attributed window, default **25,000/s**. It *replaces* the
fixed ceiling rather than adding to it; applying both would keep exactly the
refusals v3 exists to stop making. Measured against batch 1: clean attributed
windows ran at 347–2,199 input-side tokens/s, and the 31 ceiling-refused windows
at 5,306–12,258/s — none of them near 25,000/s.

**KNOWN LIMIT.** 25,000/s is not a bound anyone published; it is a headroom
figure over the rates this project has actually observed, and it does not
dominate the fixed ceiling in every direction. The contaminated smoke-test window
that motivated the original guard ran at 16,693 input-side tokens/s (10,993,105
tokens over 658s) — **under** 25,000/s, so the rate ceiling alone would not have
refused it. What refuses it under v3 is the third-party baseline probe, which v3
leaves untouched: that window's probe saw 1,274,568 input tokens in the five
minutes after and 176,672 in the five minutes before. The probe, not the ceiling,
is v3's defence against a stranger working at a believable rate; a regression test
pins that (`test_the_third_party_probe_is_the_v2_one_unchanged`). Revisit the
number if a subject arm is ever observed above ~10,000/s.

v3 writes `provider_usage_backfill_v3` events and leaves `PROVIDER-BACKFILL-
REFUSED-v3.json` markers, for the same append-only reason: a v2 refusal and a v3
attribution of the same window are both true of their own rule, and the summarizer
reports that pair as a rule supersession rather than as a stale marker.

## How backfill works (and why it appends events)

`telemetry.validate` is audit-grade: it re-derives the summary from `events.jsonl`
and fails on **any** mismatch in the event-sourced fields. Hand-editing usage into
`summary.json` would therefore fail validation, correctly. The only honest
backfill is:

1. append one `provider_usage_backfill` event per leg to `events.jsonl`;
2. re-derive `summary.json` from the now-longer log;
3. re-run `validate(run_dir)` and record the verdict in the report.

`provider_usage_backfill` is a usage-bearing event type but **not a turn** —
`behavior.turns` still counts `model_call_completed` only, so a backfill adds
tokens and never inflates behaviour counts. The original `unavailable`
`model_call_completed` events are left exactly as recorded; the log stays
append-only.

Guards:

- **Idempotence** — a run that already has a `provider_usage_backfill`,
  `provider_usage_backfill_v2` **or** `provider_usage_backfill_v3` event is
  skipped, never double-counted. Re-running
  under a different attribution rule does not re-fill a leg; to change a leg's
  attribution, delete its backfill event first.
- **Ambiguity** — if two legs of a run declare the same `model_user_id`, the
  billing plane cannot separate them and the collector refuses to attribute.
- **No data** — an empty window fills nothing and says so; usage stays
  `unavailable`.

**Economics are not recomputed.** The collector fills usage only; costs stay as
the runner recorded them. Re-cost with `harness/runner/run.py`'s
`build_economics` against the pinned pricing snapshot once usage is filled — and
read the cache-blind caveat above before publishing any Product-B figure.

## Usage

Write a plan naming each run and which `model_user_id` each of its legs used
(the product's selector label is not the metered model id, so this mapping is
declared, not inferred):

```json
{
  "project": "vital-octagon-19612",
  "runs": [
    {"run_dir": "results/screening-batch4/run-0001",
     "legs": {"main": "gemini-3.7-flash"}},
    {"run_dir": "results/screening-batch4/run-0002",
     "legs": {"conductor": {"model_user_id": "claude-opus-5", "publisher": "anthropic"},
              "executor": "gemini-3.7-flash"}}
  ]
}
```

A leg is either a bare `model_user_id` string — publisher defaults to `google` —
or an object naming the publisher too. **A mixed-publisher run (C5: Anthropic
conductor, Google executor) must use the object form for its Anthropic leg**;
the publisher is declared by the operator, never inferred from the model name
(SPEC §6.3). Both spellings of this were broken until 2026-08-17 and are now
regression-tested:

- the multi-model filter emitted `one_of("a" OR "b")`, which Cloud Monitoring
  rejects with **HTTP 400 "Could not parse filter"** — the correct syntax is
  comma-separated, so *every* multi-model collection failed outright; and
- `publisher` was fixed at `google`, so the Anthropic conductor series above
  could never match — silently, returning nothing rather than erroring.

`start`/`end` may be given per run; the default is the run's first and last event
timestamp. Then:

```bash
# see what would be written, touch nothing
python3 -m harness.collectors.vertex_token_collector --plan plan.json --dry-run

# backfill for real, after the batch has finished (ingestion lag: give it minutes)
python3 -m harness.collectors.vertex_token_collector \
    --plan plan.json --guard-seconds 60 --report report/batch4/backfill.json
```

Exit code is non-zero if any run errored. Run it **after** a batch completes —
Cloud Monitoring ingestion lags, and a window queried too early under-reports.
