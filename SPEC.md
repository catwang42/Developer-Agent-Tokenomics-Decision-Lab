# Measure Before You Route
## Developer-Agent Economics Decision Lab — Build Specification v2.1

**Version:** 2.1.1 — 2026-07-16 (final precision pass per external review; **FROZEN — next step is execution, not revision**)
**Purpose of this build:** a provider-independent measurement layer and half-day decision lab. Built vendor-agnostic first; the evidence it produces will subsequently be screened for workload classes where an Antigravity-positioned narrative is supportable (see §5, Workload Screening Program).

---

## 0. Artifact Hierarchy (what the workshop is, and is not)

The workshop is the *distribution layer* of a four-part structure. It is not the artifact.

1. **Core intellectual artifact — Developer-Agent Economics Methodology:** metric
   definitions, benchmark rules, telemetry schema, evaluation protocol, governance
   scenario method.
2A. **Evidence artifact — Balanced Reference Benchmark & Technical Report:** pinned
   experiments, results by task class, limitations, routing break-even analysis.
   Balanced by design; never tilted toward any provider narrative.
2B. **Positioning evidence screening (§5):** a transparently hypothesis-seeking program
   asking whether a provider-specific narrative is supportable — where it wins, where it
   loses, and whether findings are robust enough to validate in 2A. Screening data never
   substitutes for the balanced benchmark.
3. **Field delivery — Measure Before You Route Decision Lab:** teaches teams to apply
   the method (this curriculum).
4. **Commercial extension — Enterprise Developer-Agent Economics Assessment:** applies
   the method to a customer's internal workloads and governance constraints.

Any later positioned offering (e.g., an Antigravity-focused economics workshop) is an
additional field-delivery packaging of layer 2 evidence — it never modifies layers 1–2.

---

## 1. Positioning and Language Register

**Primary buyer:** Head of AI Platform; key partner Head of Developer Productivity.
**The buyer question the lab answers:** *Should we standardize on one developer-agent
configuration, use different models for different work, or test routing — and what
evidence would justify that choice?*

| Use | Do not use |
|---|---|
| "Provider-independent methodology and reference implementation; initial adapters support a declared set of products/providers, with telemetry limitations documented per configuration" | "Vendor-neutral" (reads as a certification claim) |
| "Reproducible, audit-ready measurement" | "Audit-grade" |
| "Cost per accepted engineering outcome" (front-stage); QA-ECST **by task class** (formal) | A single suite-wide QA-ECST without a declared task-mix weighting |
| "See how a large apparent per-token price advantage can shrink substantially once output volume, caching, failures and verification are included" (public material) | Exact pilot percentages in public material — exact figures live in facilitator material, case-study slides, and the technical report only |
| "~N cohort observations illustrating operational variance" | "n=N per arm" |
| "A pre-registered independent evaluation gate checks the attempt; the gate prioritizes deterministic tests and static checks; model-based review is supplementary and separately measured" | "Independent verifier checks" (undefined) |
| "Recommend a provisional admissible configuration and define the organization-specific evidence required to confirm or overturn it" (M4) | Presenting public-repo reference data as predictive of a private codebase |
| Human active/review/correction/blocked minutes; scenario-labeled capacity ranges | FTE savings derived from agent runtime |
| "These runs compare complete product configurations; they do not establish that one underlying model is more efficient than another" (every black-box slide) | Product-level efficiency attribution |

Command/capability classification (unchanged from v2): official product command ·
documented configuration · workshop-owned adapter · community-plugin command ·
experimental integration. The agy headless quirks are observed v1.x behavior wrapped by
a workshop-owned adapter whose exit codes and timeouts belong to the workshop, not the
vendor. Model names appear only in the dated delivery manifest
(`STRONG_MODEL_A`-style placeholders in permanent material).

---

## 2. Evaluation Architecture

### 2.1 The configuration matrix (five configurations, three views)

| # | Configuration | What actually varies | Evaluation view |
|---|---|---|---|
| C1 | Product A + strong model tier | — (baseline) | Within-product configuration comparison |
| C2 | Product A + economical model tier | Model tier, same product | Within-product configuration comparison |
| C3 | Product B + economical model tier | Product **and** model **and** provider path | Product black-box comparison |
| C4 | Product B + strong model tier | As C3, stronger tier | Product black-box comparison |
| C5 | Product A conductor → Product B executor (community plugin) | Product architecture, delegation interface, context transfer, tooling, two providers, two billing mechanisms, plugin implementation | Black-box integrated workflow experiment |

*Permanent labels only. The dated delivery manifest resolves Product A/B and tiers to the
exact product selector or versioned model ID available at delivery (current intended
mapping: Product A = Claude Code, Product B = Antigravity CLI).*

Rules that follow from the views:

- **C1 vs C2** is the cleanest *within-product model-tier comparison* in the lab. It
  reduces major product-level confounders and answers the in-stack rebuttal ("wouldn't
  the economical tier already solve this?"), but it does not establish a pure API-model
  effect unless the workshop-owned harness controls all relevant orchestration behavior.
- **C2 vs C3** is the strategically decisive comparison for any later Antigravity
  narrative, and it is a *black-box* comparison — product and model change together.
  Findings are reported as configuration outcomes, never as model-efficiency claims,
  and under both the *marginal operating* and *fully allocated* cost views (§2.7); a
  finding is robust only if its direction survives both.
- **C5** is a *black-box integrated hybrid workflow experiment*: product architecture,
  delegation interface, context transfer, tooling, provider paths and two billing
  mechanisms change together by design. Both bills counted, failed delegations and
  verification included, frontier-token share diagnostic only. C5 does not inherit the
  causal status of the controlled routing-policy comparison (P0 vs P1); varying the
  executor tier within pinned C5 is a *within-workflow executor-tier comparison*.
- Claude-through-agy and proxy-based cross-vendor harnesses are **out of scope** for
  this build.

### 2.2 M2 experimental split (review fix 1)

The live module contains two panels, run within one 75-minute block but never presented
as equivalent cells:

- **M2A — Controlled model comparison:** C1 vs C2. Same harness, same evaluation; only
  the model changes.
- **M2B — Controlled routing-policy comparison:** P0 (static strong baseline) vs P1
  (cheap-first escalation: economical attempt → pre-registered evaluation gate →
  escalate on failure), both on the controlled harness. C5 (the integrated hybrid
  workflow) is demonstrated separately as a black-box workflow — never presented as an
  equivalent cell to P0/P1.

C3/C4 appear in the product black-box gallery (facilitator-run or pre-recorded), not in
the live experiment.

### 2.3 Sample plan — three phases (review fix 3)

| Phase | Composition | Use | Explicitly not |
|---|---|---|---|
| **Feasibility dataset** | 3 tasks × 3 declared controlled configurations (P0 strong single-model · economical single-model · P1 cheap-first escalation) × 3 repetitions = **27 runs (9 task-configuration cells)** | Telemetry completeness and stability of the controlled harness | Comparative vendor claims |
| **Pilot reference dataset** | ≥5 repetitions per cell; repetition count adjusted after observing variance and failure rates | Scoped findings under pinned conditions; workshop reference data | Generalized rankings |
| **Expanded dataset** | 11 tasks stratified by language (TS/Python/Java), task class, complexity; repetitions per a pre-declared statistical plan | The technical report | — |

C3, C4 and C5 receive **separate** product/workflow telemetry feasibility runs; they are
not part of the controlled 27-run set (this keeps provider families and controlled
configurations from being conflated).

### 2.4 Metrics and aggregation policy (review fix 4)

**Formal primary:** QA-ECST — reported **by task, task class, complexity band, language,
and risk level first**. A suite-wide aggregate is published only with a declared,
defensible task-mix weighting model.
**Front-stage phrase:** cost per accepted engineering outcome.
**Supporting:** success rate · cost per attempt · human-effort-adjusted cost · cost per
accepted PR · P95 latency. **Diagnostic only:** frontier-token share, raw token deltas.
**Human effort:** active/review/correction/blocked minutes per accepted task. No FTE
conversion. *Tasks-per-developer-week* is excluded from the public benchmark and lab; it
appears only in the Enterprise Assessment, where actual organizational workflow data
exists.

**Statistical reporting (declared before data arrives):** success rate with an
uncertainty interval; median and IQR for cost; P95 latency only at sufficient sample
size; paired task-level comparisons where applicable; bootstrap confidence intervals for
cost differences when justified; failure categories reported separately; excluded or
missing-cost runs never averaged as zero; escalation policies reported under both
intention-to-route and completed-route analyses. At pilot scale, honest descriptive
statistics are preferred over elaborate significance testing.

### 2.5 Routing decision gate (review fix 8)

A routing policy proceeds only if **all four** hold — the fixed 10–15% gate is replaced:

1. **Quality non-inferiority** under a separately declared margin;
2. **Business-relevance threshold** exceeded — set by the organization (e.g., "≥15%
   expected economic improvement before we change architecture"), not by the benchmark;
3. The gain **survives verifier, retry, rework and human-review costs**;
4. The gain is **stable across tasks and repeated runs** (statistical confidence
   determined from observed variance, not assumed in advance).

### 2.6 Evaluation protocol (review fix 2)

The acceptance mechanism is a **pre-registered independent evaluation gate**, in
priority order: hidden deterministic tests → type checking and linting → regression
checks → security checks where relevant → a fixed human-review rubric (timed).
Model-based review may be included as an experimental component; it is supplementary,
separately measured, and never the authoritative acceptance mechanism. The generating
model is never the sole verifier of its own work.

**Sealed hidden-test policy (review fix 10):** publish the task specification, public
tests, and the evaluator version + hash; keep hidden tests sealed during an active
evaluation cycle; record the hidden-test version/hash in every result; rotate or release
after the cycle; maintain canonical-solution validation; prevent participant access
during workshop runs.

### 2.7 Telemetry schema v2 (review fixes 5–6)

Every field carries `value` **and** `source/confidence` ∈ {authoritative, derived,
proxy-observed, unavailable}. Unavailable is recorded as unavailable — **never zero.**

- **Identity & configuration:** run ID; task ID + task-suite version; product; provider;
  exact model ID or routed selector; product/CLI version; authentication and billing
  path; region; reasoning/effort configuration; permission profile; network-access
  policy; fresh vs resumed session; cold vs warm cache.
- **Usage:** input tokens; cache-creation tokens; cache-read tokens; output tokens;
  reasoning tokens where separately exposed; tool-result/feedback tokens where exposed;
  search operations and charges; code-execution usage and charges.
- **Agent behavior:** turns; tool calls by type; file reads (and bytes where
  measurable); files modified; retries; escalations; subagent calls; verifier calls;
  failures by category.
- **Economics & people:** provider cost; machine cost; **cost basis** ∈
  {marginal_api_cost, allocated_subscription_cost, provider_reported_cost,
  cost_unavailable}; subscription-allocation basis where used; active/review/correction/
  blocked human minutes; total end-to-end cost.

**Subscription cost-basis rule:** a marginal API cost is never placed beside an
allocated subscription cost without the basis declared. Black-box product views may
legitimately report "observed marginal cost: unavailable; subscription basis: licensed
seat, allocation not estimated" rather than fabricating a per-run dollar figure. This
applies directly to Product A subscription seats vs Product B PAYG in C1–C5.
Comparative findings are reported under two economic views — **marginal operating**
(additional observable cost incurred by the task) and **fully allocated** (task cost
under the declared seat/subscription/committed-spend allocation) — and no finding is
called economically robust unless it survives the relevant cost-basis sensitivity.

**Event-level storage:** telemetry is captured as an immutable event log (model call
started/completed; tool invoked/completed; file read; test run; retry; escalation;
verifier call; human review started/completed; correction; failure) plus a derived run
summary (aggregated token classes, total cost, QA-ECST inputs, retries, human effort,
acceptance result). Run summaries alone cannot audit subagents, retries, or dual-bill
hybrid workflows.

### 2.8 Reference vs cohort data; task suite

Unchanged from v2 in substance: reference data is produced centrally in pinned
containers with hidden tests; participant runs are cohort exercise data (operational
variance illustration), never merged. The RealWorld feature task remains the
*candidate pilot task* until the 10-point validation passes (commit, deps, paths, clean
install, baseline tests, pre-modification failure, hidden-test pass on canonical patch,
no leakage, clean-container build, deterministic reset). The 11-task expanded suite is
the roadmap (exploration, bug repair, feature implementation, test generation,
refactoring, CI/dependency repair, code review across TS/Python/Java).

---

## 3. Curriculum (half-day, 240 min — a clean 4-hour block)

| Time | Module | Duration |
|---|---|---|
| 0:00 | M0 — The decision problem | 20 min |
| 0:20 | M1 — Audit the evidence | 40 min |
| 1:00 | M2 — One controlled experiment (M2A + M2B) | 70 min |
| 2:10 | Break | 10 min |
| 2:20 | M3 — Interpret the economics | 40 min |
| 3:00 | M4 — Enterprise decision exercise & wrap-up | 60 min |
| **Total** | | **240 min** |

**M0 — The decision problem (20 min).** The buyer question; cost per accepted
engineering outcome; the three-views distinction; measured facts vs assumptions.
Opening case told qualitatively in participant material ("a model with a large per-token
price advantage that mostly evaporates per task once verbosity is counted"); exact
figures on the facilitator's case-study slide with pinned conditions.

**M1 — Audit the evidence (40 min).**
ex110 anatomy of a bill (10) · ex120 naive vs cache-aware recomputation of a pinned run —
participants *quantify* the difference themselves; the facilitator key carries the exact
observed range (10) · ex130 Spot the Flaws against the seven-point audit checklist (20).

**M2 — One controlled experiment (70 min).**
ex210 read the manifest, pre-register hypotheses (10) ·
**ex220-A (M2A panel):** participants run C1 or C2 on the pilot task — a controlled
model comparison (20) ·
**ex220-B (M2B panel):** facilitator (or volunteer pairs) runs the cheap-first
escalation policy and/or pinned C5 delegation — explicitly a workflow-policy experiment;
both bills on screen (15) ·
ex230 variance readout: cohort exercise data beside the pilot reference dataset;
operational variance forms live (25).
Fallback ladder per cell: live → facilitator shared-credential → pre-recorded + shipped
telemetry. Black-box gallery (C3/C4, plugin DEMO-KIT) is an optional add-on segment with
the standing disclaimer.

**M3 — Interpret the economics (40 min).**
ex310 compute QA-ECST *by task class* and human-effort-adjusted cost from the reference
dataset, including a worked case where cheap-first loses after failed attempts and
verification are priced (20) · ex320 break-even & sensitivity worksheet: task size,
success rate, review burden; the four-condition routing gate applied (20).

**M4 — Enterprise decision exercise & wrap-up (60 min: 40 + 20).**
ex410: governance scenario → eliminate inadmissible configurations → **recommend a
provisional admissible configuration and define the organization-specific evidence
required to confirm or overturn it** → one-page decision memo; room audit with the
checklist. The provisional framing is the bridge to the Enterprise Assessment.

**Lightning variant (90 min):** M0 + M1 + guided reference-dataset walkthrough; no
installs.

---

## 4. Build Instructions

### 4.1 Scaffold (delta from v2)

```
decision-lab/
├── methodology/                     # LAYER 1: metrics, benchmark rules, evaluation
│   │                                #   protocol, governance scenario method (versioned)
├── manifest/  (delivery-manifest.yaml, RUN_TEMPLATE.md)
├── harness/
│   ├── runner/                      # controlled runner (C1/C2, policies)
│   ├── adapters/                    # claude-code adapter; workshop-owned agy adapter;
│   │                                #   plugin-delegation adapter (C5, both bills tagged)
│   ├── policies/ (p0-baseline.yaml, p1-cheap-first.yaml, p2-delegation.yaml)
│   ├── evaluator/                   # deterministic-first gate + sealed hidden tests
│   │                                #   (spec+public tests+evaluator hash published;
│   │                                #    hidden tests hashed per result, rotated per cycle)
│   └── telemetry/schema-v2.json     # §2.7 field set, value+confidence, cost_basis
├── tasks/ (pilot-realworld/ + suite/)
├── results/ (feasibility/ pilot-reference/ cohort/)
├── report/                          # static parametrized report + calculator
├── pricing/prices-<date>.json
└── docs/ + tests/ + ci
```

### 4.2 Build sequence

1. **Telemetry proof** — schema v2 + adapters for C1/C2 (native), C3/C4 (product
   telemetry + external records, cost_basis declared), C5 (dual-bill). Confirm capture
   without model self-report; document per-configuration telemetry limitations.
2. **Pilot task validation** — 10-point script green in a clean container; hidden tests
   authored and sealed.
3. **Feasibility dataset** — 27 runs (9 cells × 3 reps): telemetry completeness and
   harness stability only. First publishable output: *telemetry completeness and
   methodology note* — no vendor rankings.
4. **Positioning Evidence Screening Program** (§5) — hypothesis-seeking evidence for
   any positioned narrative; promising findings are validated in the pilot reference
   dataset before appearing anywhere.
5. **Pilot reference dataset** — ≥5 reps/cell on the screened task set.
6. **Curriculum + static report + pilot delivery** (5–8 senior participants; success =
   participants can reject a misleading benchmark and construct a defensible evaluation
   plan).

---

## 5. Positioning Evidence Screening Program (layer 2B)

**Objective:** identify workload classes, if any, where Product-B-based configurations
(C3/C4) or the integrated hybrid workflow (C5) produce a defensible economic advantage
over the in-stack alternatives (C1/C2) — *before* any positioned narrative is written.
The screening runs under the provider-independent methodology; the narrative is chosen
by the data.

**Transparency label (mandatory on all outputs):** this program is intentionally
*hypothesis-seeking positioning evidence screening*. It must not be used to estimate
overall product superiority or expected enterprise-wide savings, and it never
substitutes for the balanced reference benchmark (layer 2A), which remains balanced
independently of this program.

**Anti-selection-bias protocol:** every task pre-registered before running; all tested
workload classes published, including negative and null findings; no tasks added or
removed based on interim results; screening data never presented as a balanced market
comparison.

### 5.1 Design

- **Workload classes (span expected wins and expected losses):**
  W1 mass test generation (coverage lift on an under-tested service) ·
  W2 scaffold-heavy feature implementation ·
  W3 mechanical migration/refactor (e.g., JS→TS module) ·
  W4 complex bug repair (expected C1 favorite) ·
  W5 small one-off edit (expected routing loser — the break-even control).
- **Configurations:** C1, C2, C3, C5 core; C4 and C5-Pro only where core results are
  ambiguous.
- **Repetitions:** 3 per cell for screening (screening ≠ publishable; any promising cell
  is re-run at ≥5 reps for the pilot reference dataset before appearing in any deck).
- **Class-claim requirement:** one task per class provides a screening signal only;
  promoting any finding to a workload-class claim requires a **second, materially
  different task** from that class, preferably a different repository (§5.2).
- **Scale:** 5 workloads × 4 configurations × 3 reps = 60 screening runs
  (+ re-runs of promising cells).
- Each workload needs: pinned repo/commit, prompt, deterministic-first gate, reset
  script, pre-modification failure proof.

### 5.2 Decision rules (pre-registered)

A configuration is a **candidate advantage** for a workload class only when it:
produces quality-non-inferior outcomes on **at least two independently validated tasks**
from that class (preferably different repositories) with the same direction of effect;
beats **C2** — not merely C1 — on QA-ECST for that class; improves QA-ECST under **both**
the marginal-operating and fully-allocated cost views relevant to the buyer; includes
all failed attempts, verification, rework and human review; and shows a stable cost
outcome across repeated runs. Screening results identify hypotheses for the pilot
reference dataset — they are **not independently publishable** as class-level
conclusions. All findings remain scoped: "for this workload class, under these pinned
conditions."

### 5.3 Outcomes → narrative mapping

- **Clear C3/C5 wins on volume classes (W1–W3):** an Antigravity-positioned field
  workshop (v3) becomes a thin packaging of evidence *validated in the pilot reference
  dataset (layer 2A)*, scoped to those classes, with W5 conceded openly (credibility
  asset).
- **Mixed:** v3 becomes a routing-pattern workshop featuring Antigravity as the
  executor for the classes it wins.
- **C2 dominates:** the vendor-agnostic decision lab stands alone; no positioned
  workshop is built on this evidence.

---

## 6. Open Items Before First Delivery

1. Feasibility dataset executed (build step 3) — gates everything downstream.
2. Pilot-task 10-point validation + sealed hidden tests.
3. Delivery manifest: record the exact versioned API model ID where a product exposes
   and guarantees one; otherwise record the exact product selector or routed label the
   product shows (e.g., Product B tiers via `agy models`), **without inferring the
   backend model version**; C5 plugin version pinned.
4. Cost-basis determination for the delivery org: Claude Code subscription seats vs API
   billing (affects C1/C2/C5 reporting); Vertex PAYG rates snapshot.
5. Rate limits vs the (small) live-run plan; facilitator fallback rehearsed.
6. Legal/attribution: community plugin credited (MIT, not vendor-endorsed);
   confidential-deck content excluded from external material; disclosure slide.
7. Human-review rubric written and timed on the canonical solutions (needed for HEAC).
