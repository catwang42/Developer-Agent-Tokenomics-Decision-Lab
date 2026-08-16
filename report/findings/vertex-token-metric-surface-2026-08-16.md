# Vertex token-count metric surface — what the billing plane actually exposes

**STATUS: AUTHORITATIVE** for the provider-side collector's design assumptions
(2026-08-16). Supersedes nothing. Dataset-independent: this describes the
*measurement surface*, not any run.

**Date:** 2026-08-16 · **Spend:** none (Cloud Monitoring reads only; no model was
invoked) · **Scope:** the labels and type values of one metric in one project.
Nothing here compares products or models; it records what can and cannot be
measured.

## What was queried

Read-only Cloud Monitoring v3, project `vital-octagon-19612`:

```
GET /v3/projects/vital-octagon-19612/metricDescriptors/
      aiplatform.googleapis.com/publisher/online_serving/token_count
GET /v3/projects/vital-octagon-19612/monitoredResourceDescriptors/
      aiplatform.googleapis.com/PublisherModel
GET /v3/projects/vital-octagon-19612/timeSeries
      ?filter=metric.type="…/token_count" AND resource.type="…/PublisherModel"
      &interval=2026-07-17T08:28:00Z .. 2026-08-16T08:28:00Z
      &view=HEADERS            # series labels only, no points
```

164 series returned, one page. `view=HEADERS` means no token values were read —
only which label combinations exist. Counts below are **series counts**, not
tokens.

## Metric and resource shape

`token_count` is `DELTA` / `INT64`, launch stage BETA, on the single monitored
resource `aiplatform.googleapis.com/PublisherModel`.

| Where | Label keys (descriptor) |
|---|---|
| resource | `resource_container`, `location`, `publisher`, `model_user_id`, `model_version_id` |
| metric | `type`, `modality`, `request_type`, `shared_request_type`, `explicit_caching`, `accounting_resource`, `max_token_size`, `source` |

Observed series carry `project_id` where the descriptor documents
`resource_container`; the collector reads `model_user_id` and does not depend on
that key.

## Finding 1 — `model_user_id` collapses effort levels (answers the item-E check)

Every Google-publisher series names the **bare model**, with an empty
`model_version_id`:

```
publisher=google  model_user_id="gemini-3.7-flash"  model_version_id=""  location=global
publisher=google  model_user_id="gemini-3.6-flash"  model_version_id=""  location=global
```

No `-high`/`-medium` suffix, no version, nothing else that varies with the
selector's effort suffix. **C3 vs C3-med cannot be separated by any label on this
metric.** Their attribution rests entirely on the runs being serialized into
disjoint time windows. That is acceptable — runs *are* serialized — but it is now
a stated dependency, not an assumption, and it is why the quiet-window rule below
is a CP-SPEND checklist line rather than advice.

By contrast Anthropic-publisher series do carry a version
(`claude-opus-5` / `model_version_id="default"`), which independently corroborates
the item-A pin result that only `@default` resolves for the current pair.

## Finding 2 — the cache pre-gate passes for Anthropic and **fails for Google**

Type values observed, split by publisher (series counts over 30 days):

| publisher | `input` | `output` | `cache_read_input` | `cache_write_input` | `cache_write_1h_input` |
|---|---|---|---|---|---|
| anthropic | 19 | 19 | 18 | 18 | 18 |
| google | 36 | 36 | **0** | **0** | **0** |

The `explicit_caching` label tells the same story: present on 90 Anthropic series,
present on **0** Google series.

The item-E brief recorded the pre-gate as PASSED because the type label carries
`cache_read_input` and `cache_write_1h_input`. That evidence is real — but it comes
from **Anthropic** rows. For the **Google** publisher, i.e. for Product B, this
project's billing plane emitted only `input` and `output` for the whole 30-day
window. This is the exact condition SPEC §2.9 item 1's pre-build gate names:
*"verify whether the provider metric separates cached input tokens; if it does
not, cache-aware costing for Product B is impossible and cross-product cache
comparisons are out of scope."*

**What is established:** over 2026-07-17 → 2026-08-16, no Gemini traffic in this
project produced a cache-class series.
**What is not established:** whether Gemini traffic that *did* hit a cache would
emit one. No explicit-caching Gemini request is known to have run in the window,
and Gemini's implicit caching may simply not be broken out on this metric. Absence
of the label over an unrepresentative window is not proof the label can never
appear.

**Consequence for the screening window** (human decision, flagged not taken):

- Product-B Gemini costing is **cache-blind** unless a screening run demonstrably
  produces a cache-class series. Under the SPEC's own wording that means the
  declared **cache-blind upper-bound cost basis** (all input billed at the
  uncached rate), stated as such wherever the number appears.
- **Cross-product cache comparisons (Product A cache behaviour vs Product B cache
  behaviour) are out of scope this window** unless the first live batch changes
  the picture.
- The collector still maps all four classes. Nothing needs to change if Gemini
  starts emitting them; the collector will pick them up and the report will show
  it.

## Finding 3 — a fifth type exists: `cache_write_input` (5-minute TTL)

`cache_write_input` and `cache_write_1h_input` are **separate** type values and
both appear on every Anthropic model. The item-E mapping names only the 1h class,
so `cache_write_input` lands in the collector's `unmapped_types` bucket and is
reported loudly rather than merged — which is the correct default, because the two
are **priced differently**: `pricing/prices-2026-08-16.json` prices the base
`cache_write` class at the 5-minute rate (1.25× input) and carries the 1-hour rate
(2× input) only as a `cache_write_1h_note`.

So the pinned mapping is, strictly, inverted relative to the priced class: the
schema field `cache_creation_tokens` is costed at the 5m rate but is being fed
from the 1h series. **Do not resolve this silently** — it is a costing decision.
The two admissible fixes are (a) map `cache_write_input -> cache_creation_tokens`
and cost `cache_write_1h_input` separately at the 1h rate, or (b) keep the current
mapping and change the priced `cache_write` rate to the 1h rate. Either way it
only bites Product A, and only when 1h caching is actually used.

This finding matters mostly as evidence that the never-drop rule works: a real,
priced, previously-unnamed class surfaced the first time the collector met live
labels.

## Finding 4 — no thinking/reasoning type exists on this metric

The brief anticipated a thinking-flavoured type ("surfacing it is an analysis
win"). There is none — not for Google, not for Anthropic. Thinking tokens are not
separable on the billing plane; for Gemini they are presumably inside `output`.
The thinking-share-of-bill analysis is therefore **not available from this
surface**. Product A's own `usage.output_tokens_details.thinking_tokens` (item A)
remains the only place thinking tokens are visible, and only for Product A.

## Finding 5 — the quiet-window requirement is concrete, not theoretical

This project already runs unrelated Gemini traffic: `gemini-3.5-flash`
(asia-south1 and global), `gemini-flash-latest`, `gemini-3.1-pro-preview`, TTS and
video models, plus `gemini-3.7-flash` and `gemini-3.6-flash` themselves — the two
screening models had traffic during the observed window. The `model_user_id`
filter excludes everything on a *different* model, but nothing separates a subject
run from a background job on the *same* model except the time window. Hence the
CP-SPEND checklist line in `harness/collectors/README.md`.

## Reproducing this

`harness/collectors/vertex_token_collector.py` builds the same filter; the raw
enumeration above is a `view=HEADERS` `timeSeries.list`, which reads no token
values and costs nothing. Re-run it before the first screening batch — findings 1
and 2 are the ones that would change a costing decision if the surface moves.
