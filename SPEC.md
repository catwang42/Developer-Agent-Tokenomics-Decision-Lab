# Measure Before You Route
## Developer-Agent Economics Decision Lab — Build Specification v2.2

**Version:** 2.2 — 2026-07-27 (first amendment after Phase-3 close; see Amendment Log. Frozen between amendments; amendments are human-authored, logged, and versioned — never silent edits.)
**Purpose of this build:** a provider-independent measurement layer and half-day decision lab. Built vendor-agnostic first; the evidence it produces will subsequently be screened for workload classes where an Antigravity-positioned narrative is supportable (see §5, Workload Screening Program).

### Amendment Log

**v2.2 (2026-07-27), human-authored after Phase-3 CP-DATA (batch 3, 7/7 criteria).**
Amends: §1 (claims-register additions), §2.1 (configuration matrix + routing-policy
taxonomy §2.1b), §2.2 (M2 panels), §2.3 (companion classes), new §2.9 (measured
product constraints), §3 (curriculum v4, 235-min agenda), §4.1 (scaffold delta), §5.1
(workload roster W1–W7 + escalation probe), §6 (open items refreshed).
Explicitly UNCHANGED: §0, §2.4, §2.5, §2.6, §2.7, §2.8, §4.2, §5.2, §5.3 — the
telemetry schema is untouched and **CP-SCHEMA remains frozen**; the existing per-leg
`legs[]` array already supports the new delegation arms without any schema change.
Rationale anchors: batch-3 feasibility dataset (27/27 controlled accepted), warm-series
revalidation, Product-B invocation verification of 2026-07-26, the subject-isolation
remediation, and the human decision of 2026-08-15 replacing the Product-B
economical-vs-strong panel with a generational same-tier panel (C3 vs C3-prev; C4
dropped from the current window). Where this amendment constrains the v4 curriculum
draft, the constraint is a measured product fact (§2.9), not a design preference.

**v2.1.1 (2026-07-16):** final precision pass per external review; frozen for the
Phase 0–3 build.

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
| M0 opening case told qualitatively in participant material ("a large per-token price advantage that mostly evaporates per task once verbosity is counted"); the exact pair of percentages lives on the facilitator case-study slide with pinned conditions | The exact M0 percentage pair in any public page, README, or site material |
| "Identical pinned runs spread by a task- and tier-dependent factor; budget with the band" (public); the measured per-cell spread table (facilitator key + technical report only) | Quoting the measured min–max spread multipliers on public pages before CP-FINDINGS |
| "The product exposes no machine-readable usage on a verified invocation; cost recorded as unavailable" (observed finding, dated) | "Product B hides its costs" or any intent-attributing phrasing |

The canonical **seven-point audit checklist** wording — referenced by ex130, ex410, the
cheatsheet, and the dashboard; one wording everywhere: **self-reported tokens ·
unmeasured claims · confounded variables · cache-blind math · no quality gate · n=1 ·
decorative extrapolation.**

Command/capability classification (unchanged from v2): official product command ·
documented configuration · workshop-owned adapter · community-plugin command ·
experimental integration. The agy headless quirks are observed v1.x behavior wrapped by
a workshop-owned adapter whose exit codes and timeouts belong to the workshop, not the
vendor. Model names appear only in the dated delivery manifest
(`STRONG_MODEL_A`-style placeholders in permanent material).

---

## 2. Evaluation Architecture

### 2.1 The configuration matrix (six declared configurations, three views)

| # | Configuration | What actually varies | Evaluation view | Run status |
|---|---|---|---|---|
| C1 | Product A + strong model tier | — (baseline) | Within-product configuration comparison | Scheduled (controlled set + warm series) |
| C2 | Product A + economical model tier | Model tier, same product | Within-product configuration comparison | Scheduled (controlled set) |
| C3 | Product B + economical model tier (current Flash generation), with a declared companion **C3-prev** (prior Flash generation, same tier) | Product **and** model **and** provider path; C3 vs C3-prev varies **only the model generation** within one product and tier | Product black-box comparison; **C3 vs C3-prev is promotable to a within-product generational comparison when per-leg usage is captured via the provider-side collector (§2.9), or reported under a declared cache-blind upper-bound cost basis if the collector's cache breakdown is unavailable** | Scheduled for screening (both generations) |
| C4 | Product B + strong model tier | As C3, stronger tier | Same black-box view | Declared; **never yet run; dropped from the current screening window by human decision (2026-08-15)** — the Product-B within-product panel is C3 vs C3-prev (generational, same tier) rather than economical-vs-strong. C4 may be scheduled in a later window |
| C5 | Product A conductor → Product B executor (community plugin), governed by pinned policy **P3** | Product architecture, delegation interface, context transfer, tooling, two providers, two billing mechanisms, plugin implementation | Black-box integrated workflow experiment (the B4 demo) | Companion runs; executor-leg cost `unavailable` until collector exists |
| C6 | Cross-vendor stacks via a gateway/router layer (LiteLLM-style) | Router layer, credential path, proxy telemetry | Named illustration of the gateway/router family (§2.1b). Telemetry would be **proxy-observed** tier at best | **Declared, not scheduled.** No runs in feasibility or screening until router infrastructure exists and a CP-SPEND schedules it |

*Permanent labels only. The dated delivery manifest resolves Product A/B and tiers to
the exact product selector or versioned model ID available at delivery (current
intended mapping: Product A = Claude Code, Product B = Antigravity CLI). The C5
configuration ID is retained for provenance across existing datasets; its governing
policy file is P3 (§2.1b).*

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
- **C5** is a *black-box integrated hybrid workflow experiment*, now explicitly bound
  to pinned policy P3: product architecture, delegation interface, context transfer,
  tooling, provider paths and two billing mechanisms change together by design. Both
  bills counted, failed delegations and verification included, frontier-token share
  diagnostic only. C5 does not inherit the causal status of the controlled
  routing-policy comparison (P0 vs P1); varying the executor tier within pinned C5 is a
  *within-workflow executor-tier comparison*.
- **C6 amendment to the prior out-of-scope rule:** proxy-based cross-vendor harnesses
  remain out of *execution* scope for this build, but the configuration is now *named*
  (C6) so the curriculum can place the gateway/router family on the routing ladder
  without implying it was measured. Claude-through-agy harnesses remain out of scope.

### 2.1b Routing-policy taxonomy

Routing policies are classified into four families (the "B-ladder", taught in ex220-B).
Policies are P-labelled artifacts in `harness/policies/`; configurations execute them.

| Family | Name | Policy artifact | Status |
|---|---|---|---|
| B1 | Static assignment | P0 (`p0-baseline.yaml`) — and by construction every single-model configuration run | Implemented, measured |
| B2 | Escalation (cheap-first) | P1 (`p1-cheap-first.yaml`): economical attempt → pre-registered gate → escalate on fail → both legs billed | Implemented; **escalation branch unexercised on the current task suite (all cheap-tier attempts passed the gate in batches 2–3)** — see §2.9 and the W6 escalation probe (§5.1) |
| B3 | Scripted delegation | P2 (`p2-delegation.yaml`, to build): a pinned split file in the task directory assigns executor vs conductor scopes; both legs itemized on one bill | To build (Phase 4). **Capability requirement, not a product mandate: B3 runs on any stack that itemizes per-leg usage on one bill.** Two admissible paths: (a) Product A native — conductor + executor via product subagent, per-model usage split from product-authoritative metadata; (b) Product B via the provider-side collector (§2.9) — conductor and executor are *different models*, so billing-plane metrics grouped by model identity separate the legs (counts authoritative, per-run attribution derived). Path (b) additionally requires verifying Product B's delegation mechanism can follow a pinned split file. The delivered stack is selected at CP-SCREEN-PREREG from whichever paths are verified by then |
| B4 | Policy-driven delegation | P3 (pinned delegation policy governing C5; policy hash recorded in the delivery manifest) | Demonstrated as the C5 gallery item; no causal claims |

Panels never merge across products; policy comparisons never merge with product
black-box comparisons; the three views of §2.1 remain structurally distinct.

### 2.1c Policy and gate artifact registry

Every routing policy and acceptance-gate artifact the lab uses, with its location and
build status. Lab users and forkers resolve any policy or gate reference in this
specification through this table; a policy referenced anywhere else in this document
but absent here is a specification defect.

**Routing policies (`harness/policies/`):**

| ID | File | Status | What it encodes | Used by | Manifest pin |
|---|---|---|---|---|---|
| P0 | `p0-baseline.yaml` | **Exists** | Static strong single-model baseline; no escalation; deterministic gate | Controlled set; ex220-B/B1 | — (model refs resolve via manifest) |
| P1 | `p1-cheap-first.yaml` | **Exists** | Economical attempt → pre-registered gate → escalate on fail; records intention-to-route, completed route, failed-attempt costs; both legs billed | Controlled set; ex220-B/B2 | — (model refs resolve via manifest) |
| P2 | `p2-delegation.yaml` | **To build (Phase 4, §6 item 3)** | Scripted delegation: pinned `tasks/<task>/split.yaml` assigns executor vs conductor scopes; both legs itemized | ex220-B/B3 | split-file hash per task |
| P3 | `p3-policy-delegation.yaml` | **To build (Phase 4, §6 item 3).** C5's delegation rules currently live inline in `harness/configurations/C5.yaml`; extracting them into P3 is the build step | Policy-driven delegation governing C5: conductor decides when to delegate to the cross-family executor | ex220-B/B4; C5 companion runs | policy hash (required before any C5 run is cited in workshop material) |

**Acceptance-gate artifacts (§2.6 priority order; per task):**

| Artifact | Location | Status |
|---|---|---|
| Deterministic public checks (typecheck, build, regression, diff-scope, no-leakage, public feature test) | `tasks/<task>/` gate scripts + public tests | **Exist** for the pilot, W4, W1 |
| Sealed hidden tests | `tasks/<task>/hidden/` (gitignored, human-authored) | **Exist and hashed in the manifest** for all three tasks: pilot-v2, sealed-w4-v2, w1-v1 (three sha256s recorded) |
| Human-review rubric (timed) | `report/batchN/human-effort-rubric.md` | **Exists**; executed for batch 3 (criterion 6) |
| Evaluator | `harness/evaluator/` | **Exists**; version and hash published per §2.6 |

*Not yet pinned in the manifest (open, §6 item 6): per-task prompt hashes; the P3
policy hash; Product-B version and `--print-timeout` pins.*

### 2.2 M2 experimental split

The live module contains two panels, run within one 75-minute block but never presented
as equivalent cells:

- **M2A — Controlled within-product model comparison.** Participants run the Product-A
  pair (strong vs economical tier; the manifest resolves exact strings) on the pilot
  task — two live runs per participant, only the model string varies. A Product-B
  within-product pair (**C3 vs C3-prev — same tier, one model generation apart**)
  appears **beside** it from the reference dataset, costed via the provider-side
  collector (§2.9) or, if the collector's cache breakdown is unavailable, under a
  declared cache-blind upper-bound basis; if no provider-side usage exists at all,
  the pair remains in the black-box gallery and the panel shows its bills as the
  honest `unavailable` contrast. The two product panels are displayed side by side,
  never merged into one chart.
- **M2B — Routing-policy panel (the four families, §2.1b).** B1 named from M2A's own
  runs (no new spend); B2 escalation demonstrated by the facilitator **with a pre-run
  replay artifact on standby as a standing requirement** (the escalation branch has
  never fired live on the current suite — §2.9); B3 scripted delegation run by
  participants on a stack satisfying the per-leg-usage requirement (§2.1c P2; stack
  selected at CP-SCREEN-PREREG). **Participant-run form constraint:** concurrent
  cohort runs against a shared billing project cannot be individually attributed by a
  provider-side collector — participant-run B3 on the collector path requires
  per-participant credentials/projects, otherwise that path is facilitator-demo only;
  B4 = the pinned C5/P3 demo, both bills on screen with the executor leg honestly
  `unavailable` until the collector exists. C6 (gateway/router) is one slide — named,
  not run.

### 2.3 Sample plan — three phases

| Phase | Composition | Use | Explicitly not |
|---|---|---|---|
| **Feasibility dataset** | 3 tasks × 3 declared controlled configurations (P0 strong single-model · economical single-model · P1 cheap-first escalation) × 3 repetitions = **27 runs (9 task-configuration cells)** | Telemetry completeness and stability of the controlled harness | Comparative vendor claims |
| **Pilot reference dataset** | ≥5 repetitions per cell; repetition count adjusted after observing variance and failure rates | Scoped findings under pinned conditions; workshop reference data | Generalized rankings |
| **Expanded dataset** | 11 tasks stratified by language (TS/Python/Java), task class, complexity; repetitions per a pre-declared statistical plan | The technical report | — |

C3, C4 and C5 receive **separate** product/workflow telemetry feasibility runs; they are
not part of the controlled 27-run set (this keeps provider families and controlled
configurations from being conflated).

Two companion classes are additionally declared:

- **Warm-cache series:** strong-tier pilot cell, one cold + N resumed repetitions on a
  persisted staged tree (series-scoped staging; byte-identical prompt across reps).
  Standing evidence for the cache-economics exercise. Open design question carried in
  §6: same-task/reset-tree resume is a *proxy* for real multi-task warm sessions and
  may understate or overstate real-world cache benefit.
- **Product-B verification runs:** minimal smoke/companion runs whose purpose is
  invocation and telemetry-surface verification, not comparison; all usage classes
  recorded `unavailable` unless the provider-side collector supplies them.

### 2.4 Metrics and aggregation policy

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

### 2.5 Routing decision gate

A routing policy proceeds only if **all four** hold — the fixed 10–15% gate is replaced:

1. **Quality non-inferiority** under a separately declared margin;
2. **Business-relevance threshold** exceeded — set by the organization (e.g., "≥15%
   expected economic improvement before we change architecture"), not by the benchmark;
3. The gain **survives verifier, retry, rework and human-review costs**;
4. The gain is **stable across tasks and repeated runs** (statistical confidence
   determined from observed variance, not assumed in advance).

### 2.6 Evaluation protocol

The acceptance mechanism is a **pre-registered independent evaluation gate**, in
priority order: hidden deterministic tests → type checking and linting → regression
checks → security checks where relevant → a fixed human-review rubric (timed).
Model-based review may be included as an experimental component; it is supplementary,
separately measured, and never the authoritative acceptance mechanism. The generating
model is never the sole verifier of its own work.

**Sealed hidden-test policy:** publish the task specification, public tests, and the
evaluator version + hash; keep hidden tests sealed during an active evaluation cycle;
record the hidden-test version/hash in every result; rotate or release after the cycle;
maintain canonical-solution validation; prevent participant access during workshop runs.

### 2.7 Telemetry schema v2

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

### 2.9 Measured product constraints (observed; curriculum and screening must respect these)

Recorded findings from verified invocations, with dates. These are facts about the
measurement surface, not vendor judgments; each carries its evidence location in the
repo's reports.

1. **Product B exposes no machine-readable usage in headless mode** (observed
   2026-07-26 on a verified invocation; transcript-only stdout, no usage object, no
   JSON output flag). All Product-B cost fields are `unavailable` at the CLI surface.
   Consequence: any Product-B cost figure requires the **provider-side collector**
   (billing-plane token metrics via the provider's monitoring/audit-log surface), with
   counts recorded `authoritative` and per-run attribution recorded `derived`
   (time-window attribution; runs serialized). **Pre-build gate: verify whether the
   provider metric separates cached input tokens; if it does not, cache-aware costing
   for Product B is impossible and cross-product cache comparisons are out of scope.**
2. **Product-B version drift observed** (v1.1.4 → v1.1.7 between sessions).
   Consequence: the adapter records the product version per run and fails loudly on
   mismatch with the manifest pin; the headless timeout (`--print-timeout`, default
   5 min — observed to truncate a real attempt mid-task) is pinned in the manifest
   like any other condition.
3. **The escalation branch of P1 has never fired** on the current three-task suite
   (the economical tier passed the gate in every batch-2/3 attempt). Consequence: B2
   is demonstrated from a replay artifact until a pre-registered escalation probe
   (§5.1) produces a live failure→escalation trace; the probe's prediction is recorded
   at CP-SCREEN-PREREG and its result published either way.
4. **Per-cell cost dispersion on identical pinned runs is material and tier-dependent**
   (batch 3: widest cells are strong-tier; warm cache markedly narrows strong-tier
   spread). Consequence: screening repetitions ≥5 for strong/cold-sensitive cells;
   point estimates are never published without median, range, and n.
5. **Human review dollars can dominate model cents** (batch-3 criterion 6: on the
   test-generation class, reviewer time priced at the declared loaded rate exceeded the
   model bill by two orders of magnitude on the would-not-merge cells; scope: n=1
   reviewer, n=1 rep, non-comparative). Consequence: HEAC is a first-class decision
   metric in M3, and every HEAC figure travels with its scope line.

---

## 3. Curriculum (half-day; 235 min core within a 240-min block)

| Time | Module | Duration |
|---|---|---|
| 0:00 | M0 — The decision problem | 20 min |
| 0:20 | M1 — Audit the evidence | 45 min |
| 1:05 | M2 — One controlled experiment (M2A + M2B) | 75 min |
| 2:20 | Break | 10 min |
| 2:30 | M3 — Interpret the economics | 45 min |
| 3:15 | M4 — Enterprise decision exercise (peer audit doubles as close) | 40 min |
| **Total** | | **235 min** (5-min buffer in a 4-hour room) |

**Standing scope note (appears on the site and in every module):** the lab's tasks are
representative probes, not a simulation of any fleet; per the two-task rule no
class-level claim is made from them. What transfers is the method — the measurement
harness and the decision logic — not the specific numbers. M4 shows how to replicate
against your own task mix.

**M0 — The decision problem (20 min).** The buyer question; cost per accepted
engineering outcome as the unit; the three-views distinction (products, models, routing
policies — three comparisons that never mix); measured facts vs assumptions. Opening
case told qualitatively in participant material ("a model with a large per-token price
advantage that mostly evaporates per task once verbosity is counted"); exact figures on
the facilitator's case-study slide with pinned conditions (§1).

**M1 — Audit the evidence (45 min).**
ex110 anatomy of a bill (10) — dissect one real telemetry record from the reference
dataset: the four token classes (fresh input, output, cache-write, cache-read) and
their four prices, then the costs the token meter never shows (retries, tool calls,
verification runs, human review time). Result: read a raw record and state, without a
calculator, which line items dominate and which prices apply. ·
ex120 naive vs cache-aware (10) — recompute one **Product-A** reference run both ways:
Method 1 (naive): total context tokens × list input price; Method 2 (cache-aware):
each token class at its real rate. The cache-aware decomposition requires the four
billed token classes, which only Product A exposes today; a Product-B record appears as
the black-box contrast — what a bill you cannot decompose looks like. The naive-method
formula is pinned on the exercise page so every participant computes the same thing;
the facilitator key carries the exact observed overstatement range. Note for
participants: caching is not a knob toggled for a fair test — Product A applies prompt
caching automatically, so the cache-aware figure *is* the honest cost; the naive column
exists only as the audit comparison. Take-away rule: when shown "N input tokens ×
$X/M," always ask *at what cache rate?* ·
ex130 Spot the Flaws (25) — cold team audit of a real, publicly circulated AI cost
benchmark, no checklist; then map findings to the canonical seven-point checklist (§1).
The checklist returns in ex410's peer audit, where the lab's own outputs are fair game.

**M2 — One controlled experiment (75 min).** Gate note: the acceptance gate is
deterministic-first (§2.6) — sealed hidden tests, type/lint, regression checks decide;
a model never solely approves its own work.
ex210 pre-register (10) — read the delivery manifest: pinned model strings, dated rate
card, repo commit, and the sealed-test sha256s (present today); prompt hashes and the
P3 policy hash join them per §6 item 6 and are required in the manifest **before first
delivery** — the exercise reads whatever the manifest pins at delivery time; write
hypotheses (which config wins, by how much) before any run.
Pre-registration is the anti-selection-bias mechanism: recorded predictions cannot be
quietly revised after results land. ·
ex220-A model-comparison panel (20) — per §2.2 M2A: participants run the Product-A
pair; the Product-B pair appears beside it conditional on the collector. The one
comparison where a cost difference is causally attributable to the model itself. Core
question: does the cheap tier hold gate quality — and when it fails, what does the
failure cost? ·
ex220-B routing-policy panel (15) — the four families per §2.1b/§2.2 M2B: B1 static
assignment, named from ex220-A's own runs (no new spend; the null hypothesis every
dynamic policy must beat); B2 cheap-first escalation, facilitator demo with standby
replay, three metrics on screen (escalation rate; all-in cost per accepted task with
failed attempts included; delta vs static frontier-first) — if the delta goes positive
the policy just lost in public, which is the point: negative findings are published
here; B3 scripted delegation, participant-run on the per-leg-usage stack, both legs
itemized on one bill; B4 policy-driven delegation, the pinned C5/P3 demo, both bills on
screen with the executor leg honestly `unavailable` until the collector exists,
frontier-token share diagnostic only; C6 gateway/router — one slide, named, not run.
Result: participants can place any vendor's "intelligent routing" pitch on this ladder,
and hold a bill for a delegation run where both legs are itemized — which almost no
published benchmark provides. ·
ex230 variance readout (30) — cohort runs post beside the precomputed reference dataset
(centrally run, repeated trials, sealed acceptance tests); watch operational variance
form live, then grade the ex210 hypotheses against reference medians, not any single
run. Real teams draw from this distribution constantly; a manager who watches config X
cost less than config Y on one run each concludes wrongly — and that is how enterprise
POCs get decided today, off n=1. Rule for life: **never accept a point estimate —
demand the median, the range, and n; budget with the band, not the point.** Fallback
ladder per cell: live → facilitator shared-credential → pre-recorded + shipped
telemetry. Black-box gallery (C3/C4, plugin DEMO-KIT) remains an optional add-on
segment with the standing disclaimer.

**M3 — Interpret the economics (45 min).** M1 asked *is the number real?* M3 asks
*given real numbers, what should we do?* All inputs are reference-dataset telemetry;
live M2 runs were the variance object lesson, not analyzable data.
ex310 compute the decision metrics (25) — in order: (1) cost per accepted outcome —
only gate-passing runs count as delivered; a failed run's cost is charged to its
configuration or policy, never averaged in as if it delivered value; (2)
quality-adjusted comparison by task class — configs compared only where gate quality is
non-inferior; a cheaper config that fails non-inferiority is *eliminated*, not
discounted; (3) human-effort-adjusted cost — review burden (minutes × declared loaded
rate) added to each config's cost; watch cheap configs with higher review burden lose
ground; (4) the honest counter-case — the scenario where cheap-first escalation
*loses* once failed attempts and verification are priced; the methodology requires
publishing this case. The ordering is lexicographic: quality gates first, then all-in
cost, then stability (ex320). Cost never buys back quality. ·
ex320 break-even & sensitivity (20) — find the flip points (task size at which
delegation's round-trip overhead exceeds its savings; cheap-tier success rate at which
escalation beats frontier-first; review cost at which the cheap advantage vanishes),
then pass each surviving configuration through the four-condition adoption gate (§2.5).
The honest answer to "which config wins?" is always *it depends* — this exercise makes
the dependence quantitative. A recommendation without its break-even conditions is an
advertisement.

**M4 — Enterprise decision exercise (40 min; peer audit doubles as the close).**
ex410: each team receives a governance scenario (repository sensitivity class;
provider allowlist; data-residency requirement; task mix; review cost; budget cap).
In order: (1) eliminate first — constraints strike inadmissible configurations before
any cost number is consulted; governance is lexicographically prior to economics;
(2) rank the admissible remainder using M3's decision table and break-even logic,
weighted by the scenario's task mix and review cost, within the budget cap; (3) write
the memo — a **provisional** recommended configuration and routing policy with its
break-even conditions stated; (4) state the evidence plan — the organization-specific
measurements (own task mix, failure rates, review costs, collected with this same
harness) that would confirm or overturn the recommendation: the transfer mechanism;
(5) peer audit — the room audits each memo against the seven-point checklist from
ex130, including anywhere a memo leaned on the lab's own numbers beyond their scope
lines. The provisional framing is the bridge to the Enterprise Assessment.

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
│   ├── runner/                      # controlled runner (C1/C2, policies);
│   │                                #   warm-series driver (series-scoped staging)
│   ├── adapters/                    # claude-code adapter; workshop-owned agy adapter;
│   │                                #   plugin-delegation adapter (C5, both bills tagged)
│   ├── policies/ (p0-baseline.yaml, p1-cheap-first.yaml, p2-delegation.yaml,
│   │              p3-policy-delegation.yaml)   # P2's split-file contract lives in
│   │                                           #   tasks/<task>/split.yaml
│   ├── collectors/                  # provider-side usage collector
│   │                                #   (Product B billing-plane; §2.9 item 1)
│   ├── evaluator/                   # deterministic-first gate + sealed hidden tests
│   │                                #   (spec+public tests+evaluator hash published;
│   │                                #    hidden tests hashed per result, rotated per cycle)
│   └── telemetry/schema-v2.json     # §2.7 field set, value+confidence, cost_basis
│                                    #   (FROZEN — unchanged by v2.2)
├── tasks/ (pilot-realworld/ + suite/)
├── results/ (feasibility batches / pilot-reference/ cohort/ — per results/README.md;
│             report/batchN pairs with results/feasibility-batchN, CLAUDE.md rule 8)
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
  W5 small one-off edit (expected routing loser — the break-even control) ·
  **W6 PR review against a sealed seeded-defect map (precision-gated: ≥k−1 found,
  zero fabricated)** ·
  **W7 greenfield build from a PRD (long-horizon).**
- **Escalation probe (pre-registered):** at least one screening workload is selected
  *because* the economical tier is predicted to fail its gate (candidate: W6; fallback:
  W3). The prediction is recorded at CP-SCREEN-PREREG before any run; the result is
  published whichever way it lands. This is a deliberately selected difficulty probe
  under the anti-selection-bias protocol, and it is the mechanism that finally
  exercises P1's escalation-cost path (§2.9 item 3).
- **Sourcing rule:** new workloads are commit-mined (agent starts at commit N−1; the
  merged PR's own tests seal the gate), targeting `obscure` or `post_cutoff`
  contamination tiers per the workload-selection method. The Claude-authored pilot
  task remains the familiar teaching example, labeled high-contamination, outside any
  comparative claim.
- **Configurations:** C1, C2, C3 + C3-prev (generational Flash pair), C5 core; C4
  dropped from this window by human decision (2026-08-15; §2.1); C6 excluded
  (declared, not scheduled). C5-Pro only where core results are ambiguous.
- **Repetitions:** ≥5 per cell for strong-tier and cold-cache-sensitive cells (§2.9
  item 4); 3 elsewhere for screening (screening ≠ publishable; any promising cell is
  re-run at ≥5 reps for the pilot reference dataset before appearing in any deck).
- **Isolation:** containerized agent leg with endpoint-allowlist egress is a hard
  precondition for screening runs (the deterministic gate remains fully offline);
  host-staged isolation is a feasibility-only posture.
- **Class-claim requirement:** one task per class provides a screening signal only;
  promoting any finding to a workload-class claim requires a **second, materially
  different task** from that class, preferably a different repository (§5.2).
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

**Done and evidenced (Phase 3):** feasibility dataset executed (batch 3, 27/27
controlled accepted, CP-DATA 7/7) · pilot-task 10-point validation + three sealed
hidden test sets (pilot-v2, sealed-w4-v2, w1-v1), sha256s in the manifest ·
human-review rubric written, timed, and folded into HEAC at the declared loaded rate ·
warm-series protocol implemented and revalidated (persisted staged tree; cold→warm
delta captured).

**Open:**

1. **Containerized agent leg + egress allowlist** — hard gate for screening runs
   (image bakes both product CLIs; credentials mounted; `canonical/` excluded from the
   image; the deterministic gate stays `--network=none`).
2. **Provider-side usage collector for Product B** — pre-build gate: confirm the
   billing-plane metric separates cached input tokens (§2.9 item 1). Determines
   whether C3/C4 ever leave the black-box tier.
3. **P2 scripted delegation** — policy file, `split.yaml` contract, per-leg usage
   split in the Product-A adapter, tests. Prerequisite for ex220-B/B3.
4. **W6 + W7 built and ten-point validated;** W6 pre-registered as the escalation
   probe. New workloads commit-mined per §5.1.
5. **Pricing snapshot refresh** — add the current Product-B tier selectors (including
   the newer economical tier named in the curriculum draft) as a new dated file;
   verify selector labels verbatim against `agy models`.
6. **Manifest completions** — prompt hash per task; P3 policy hash; Product-B version
   pin + `--print-timeout` pin; cost-basis determination for the delivery org
   (subscription seats vs API billing; Vertex PAYG snapshot) carried from v2.1.1.
7. **Warm-series proxy question** — decide in Phase 4 whether same-task/reset-tree
   resume adequately proxies multi-task warm sessions, or design a mixed-task warm
   protocol.
8. Rate limits vs the (small) live-run plan; facilitator fallback rehearsed (carried).
9. Legal/attribution: community plugin credited (MIT, not vendor-endorsed);
   confidential-deck content excluded from external material; disclosure slide
   (carried).
