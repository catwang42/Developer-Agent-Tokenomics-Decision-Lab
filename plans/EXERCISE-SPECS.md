# Exercise Content Specs (input to Phase 5)

Timings are the **SPEC v2.2 §3 curriculum**: 235-min core inside a 240-min room
(M0 20 · M1 45 · M2 75 · break 10 · M3 45 · M4 40; 5-min buffer). Where this file and
SPEC §3 disagree, **§3 wins** — update here, never there.

Each page: goal, timed parts, inputs, completion checklist. The claims register
(SPEC §1.2) applies to every page: placeholder model labels, no exact pilot
percentages in public material, no unscoped findings.

## Agenda (SPEC §3 v2.2)

| Time | Module | Duration | Exercises |
|---|---|---|---|
| 0:00 | M0 — The decision problem | 20 | (no participant exercise) |
| 0:20 | M1 — Audit the evidence | 45 | ex110 10 · ex120 10 · ex130 25 |
| 1:05 | M2 — One controlled experiment (M2A + M2B) | 75 | ex210 10 · ex220-A 20 · ex220-B 15 · ex230 30 |
| 2:20 | Break | 10 | — |
| 2:30 | M3 — Interpret the economics | 45 | ex310 25 · ex320 20 |
| 3:15 | M4 — Enterprise decision exercise | 40 | ex410 40 (peer audit doubles as the close) |
| | **Total** | **235** | |

## Exercise table

| ID | Module | Min | Participant does | Inputs | Completion checklist (min.) |
|---|---|---|---|---|---|
| ex110 | M1 | 10 | Dissect one real run summary: the 4 token classes at their 4 prices, then the costs the token meter never shows (retries, tool calls, verification runs, human review) | one pinned summary.json | names all 4 classes + 2 non-token costs; states which line items dominate without a calculator |
| ex120 | M1 | 10 | Recompute one **Product-A** reference run naive (total context × list input price) vs cache-aware (each class at its real rate); quantify the delta. A Product-B record sits beside it as the black-box contrast — a bill you cannot decompose | events.jsonl + pricing snapshot + calculator; pinned naive-method formula on the page | both figures computed; delta explained; scoped-claim sentence written; states the take-away rule ("N input tokens × $X/M — *at what cache rate?*") |
| ex130 | M1 | 25 | Cold team audit of a real, publicly circulated AI cost benchmark with **no checklist**; then map findings onto the canonical seven-point checklist | the unannotated document; [`docs/cheatsheet.md`](../docs/cheatsheet.md) (revealed after the cold pass) | >=5/7 flaws with evidence quotes; each mapped to a checklist point |
| ex210 | M2 | 10 | Read the delivery manifest (pinned model strings, dated rate card, repo commit, sealed-test sha256s; prompt hashes + P3 policy hash once §6 item 6 lands) and pre-register hypotheses before any run | manifest + RUN_TEMPLATE | template committed **before** any run; states why pre-registration is the anti-selection-bias mechanism |
| ex220-A | M2 | 20 | M2A: run the Product-A pair (strong vs economical tier — only the model string varies) on the pilot task. The Product-B **C3 vs C3-prev** generational pair appears beside it from the reference dataset, conditional on the provider-side collector | runner + creds or recorded run; reference C3/C3-prev panel | gate result + summary.json validated; states why this is the one comparison causally attributable to the model; answers "does the cheap tier hold gate quality — and when it fails, what does the failure cost?" |
| ex220-B | M2 | 15 | M2B: place the four routing-policy families (SPEC §2.1b) on the ladder — **B1** static assignment, named from ex220-A's own runs, no new spend; **B2** cheap-first escalation, facilitator demo with standby replay artifact; **B3** scripted delegation, participant-run on the per-leg-usage stack, both legs itemized on one bill; **B4** policy-driven delegation, the pinned C5/P3 demo, executor leg honestly `unavailable`. C6 gateway/router: one slide, named, not run | facilitator run + standby replay; P0/P1 policy files; the selected B3 stack; C5/P3 demo | places a vendor "intelligent routing" pitch on the B-ladder; for B2 names the three on-screen metrics (escalation rate; all-in cost per accepted task incl. failed attempts; delta vs static frontier-first); states why B4/C5 is **not** causally the controlled P0-vs-P1 comparison |
| ex230 | M2 | 30 | Submit your run; watch it land on the local workshop dashboard beside the precomputed reference distributions; grade the ex210 hypotheses against reference **medians**, not any single run | workshop-day dashboard (local) + submit-cohort.sh + reference dataset | names 2 operational-variance sources; states why cohort data is not benchmark data; writes the rule — **never accept a point estimate; demand median, range and n; budget with the band** |
| ex310 | M3 | 25 | Compute the decision metrics in order: (1) cost per accepted outcome (only gate-passing runs count as delivered; a failed run's cost is charged to its config, never averaged in); (2) quality-adjusted comparison by task class (a config failing non-inferiority is **eliminated**, not discounted); (3) HEAC — review minutes × declared loaded rate; (4) the honest counter-case where cheap-first escalation *loses* | reference summaries + methodology/metrics.md | per-class table; both cost views; counter-case written; states the lexicographic order (quality gate → all-in cost → stability) |
| ex320 | M3 | 20 | Break-even worksheet — find the flip points (task size where delegation overhead exceeds savings; cheap-tier success rate where escalation beats frontier-first; review cost where the cheap advantage vanishes) — then run each surviving config through the four-condition adoption gate | methodology/routing-policy.md + calculator | E[P1] formula applied; gate verdict justified per condition; states that a recommendation without its break-even conditions is an advertisement |
| ex410 | M4 | 40 | Governance scenario in order: (1) **eliminate first** — constraints strike inadmissible configs before any cost number; (2) rank the admissible remainder with M3's decision table, weighted by task mix and review cost, within the budget cap; (3) write the **PROVISIONAL** memo with break-even conditions; (4) state the evidence plan (the org-specific measurements that would confirm or overturn it); (5) peer audit | scenario pack + memo template + [`docs/cheatsheet.md`](../docs/cheatsheet.md) | memo audited by the room against the seven-point checklist, including anywhere it leaned on the lab's own numbers beyond their scope lines |

## Standing notes for every page

- **Scope note (SPEC §3).** The lab's tasks are representative probes, not a simulation
  of any fleet; per the two-task rule no class-level claim is made from them. What
  transfers is the method, not the numbers.
- **Gate note (M2 pages).** The acceptance gate is deterministic-first (SPEC §2.6):
  sealed hidden tests, type/lint, regression checks decide; a model never solely
  approves its own work.
- **Seven-point checklist.** One canonical wording, one canonical home:
  [`docs/cheatsheet.md`](../docs/cheatsheet.md). ex130 and ex410 link there; nothing
  restates it.
- **Fallback ladder (ex220-A / ex230, per cell).** live → facilitator
  shared-credential → pre-recorded + shipped telemetry. The black-box gallery
  (C3/C3-prev, plugin DEMO-KIT) is an optional add-on segment with the standing
  disclaimer.
- **Lightning variant (90 min).** M0 + M1 + guided reference-dataset walkthrough;
  no installs.
