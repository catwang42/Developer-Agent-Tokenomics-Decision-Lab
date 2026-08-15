# Phase 4 — Positioning Evidence Screening (SPEC §5, v2.2)
**Goal:** pre-registered **W1–W7** screening under the anti-selection-bias protocol,
including the pre-registered escalation probe, plus the build items that gate it
(containerized agent leg, provider-side collector, P2/P3 policy files).
**Branch:** phase/4-screening

**Transparency label — mandatory verbatim on every Phase-4 output:** this program is
intentionally *hypothesis-seeking positioning evidence screening*. It must not be used
to estimate overall product superiority or expected enterprise-wide savings, and it
never substitutes for the balanced reference benchmark (layer 2A).

## 1. Workload roster (SPEC §5.1 v2.2)

Seven classes, spanning expected wins and expected losses. The one table of record is
[`tasks/suite/WORKLOADS.md`](../tasks/suite/WORKLOADS.md); per-task definitions live in
`tasks/suite/W*/workload.yaml`.

| ID | Class | Expectation going in |
|---|---|---|
| W1 | mass test generation (coverage lift on an under-tested service) | volume class |
| W2 | scaffold-heavy feature implementation | volume class |
| W3 | mechanical migration/refactor (e.g. JS→TS module) | volume class; **escalation-probe fallback** |
| W4 | complex bug repair | expected C1 favorite |
| W5 | small one-off edit | expected routing **loser** — the break-even control |
| W6 | PR review against a sealed seeded-defect map (precision-gated: ≥k−1 found, zero fabricated) | **escalation-probe candidate** |
| W7 | greenfield build from a PRD (long-horizon) | new in v2.2 |

**Escalation probe (pre-registered).** At least one workload is selected *because* the
economical tier is predicted to fail its gate. Candidate: **W6**; fallback: **W3**. The
prediction is recorded at CP-SCREEN-PREREG **before any run**, and the result is
published whichever way it lands. This is a deliberately selected difficulty probe under
the anti-selection-bias protocol, and it is the mechanism that finally exercises P1's
escalation-cost path — the branch has never fired on the current suite (SPEC §2.9
item 3), which is why B2 is demonstrated from a replay artifact until it does.

**Sourcing rule (SPEC §5.1).** New workloads are **commit-mined**: the agent starts at
commit N−1 and the merged PR's own tests seal the gate. Target contamination tiers are
`obscure` or `post_cutoff` per `tasks/WORKLOAD-SELECTION.md`. The Claude-authored pilot
task stays as the familiar teaching example, labeled high-contamination and **outside
any comparative claim**. A candidate whose pinned commits cannot be verified against the
real repository is not a task — see `tasks/proposals/` for proposals that have not
cleared this bar.

**Class-claim requirement.** One task per class is a screening signal only. Promoting a
signal to a workload-class claim needs a second, materially different task from that
class, preferably a different repository (SPEC §5.2).

## 2. Configurations (SPEC §5.1 v2.2)

- **C1, C2** — Product-A strong / economical tiers (the in-stack alternatives screening
  must beat).
- **C3 + C3-prev** — the Product-B **within-product generational panel**: current Flash
  generation vs the prior Flash generation, **same tier, one generation apart**. This
  replaced the economical-vs-strong panel.
- **C4 — dropped from this window by human decision (2026-08-15).** Never yet run; may
  be scheduled in a later window. No Phase-4 cell uses it.
- **C6 — excluded.** Declared, not scheduled; no gateway/router runs until the
  infrastructure exists and a CP-SPEND schedules it. It appears as one named slide only.
- **C5** core (the B4/P3 demo); **C5-Pro** only where core results are ambiguous.

## 3. Repetitions and isolation

- **Reps ≥5** on strong-tier and cold-cache-sensitive cells (batch-3 dispersion is
  material and tier-dependent — SPEC §2.9 item 4); **3 elsewhere** for screening.
  Screening ≠ publishable: any promising cell is re-run at ≥5 reps for the pilot
  reference dataset before it appears in any deck.
- **No point estimates.** Every screening figure travels with median, range and n.
- **Hard precondition — containerized agent leg with endpoint-allowlist egress.** No
  screening run happens on host-staged isolation; that posture is feasibility-only. The
  deterministic gate stays fully offline (`--network=none`).

## 4. Build items that gate the runs

1. **Containerized agent leg + egress allowlist** (SPEC §6 item 1) — image bakes both
   product CLIs; credentials mounted; `canonical/` excluded from the image; gate runs
   `--network=none`. **Hard precondition for every screening run.**
2. **Provider-side usage collector for Product B** (`harness/collectors/`, SPEC §2.9
   item 1). Product B exposes no machine-readable usage in headless mode, so every
   Product-B cost is `unavailable` at the CLI surface; the collector reads billing-plane
   token metrics (counts `authoritative`, per-run attribution `derived` by time window,
   runs serialized).
   **Pre-gate, before building:** confirm the provider metric **separates cached input
   tokens**. If it does not, cache-aware costing for Product B is impossible,
   cross-product cache comparisons are out of scope, and C3/C3-prev is reported under a
   declared **cache-blind upper-bound** cost basis (or stays in the black-box gallery
   with `unavailable` bills). Record the pre-gate answer at CP-SCREEN-PREREG either way.
3. **P2 scripted delegation** (`harness/policies/p2-delegation.yaml` + the
   `tasks/<task>/split.yaml` contract + per-leg usage split + tests) — prerequisite for
   ex220-B/B3. Two admissible stacks (SPEC §2.1b B3); the delivered one is **selected at
   CP-SCREEN-PREREG from whichever paths are verified by then**.
4. **P3 policy extraction** (`harness/policies/p3-policy-delegation.yaml`) — C5's
   delegation rules currently live inline in `harness/configurations/C5.yaml`. The
   policy hash must be in the manifest **before any C5 run is cited in workshop
   material**.
5. **W6 and W7 built and ten-point validated**; W6 pre-registered as the escalation
   probe.
6. **Pricing snapshot refresh** — add current Product-B tier selectors (including the
   newer economical tier) as a new dated file; verify selector labels verbatim against
   `agy models`.
7. **Manifest completions** — prompt hash per task; P3 policy hash; Product-B version
   pin + `--print-timeout` pin (the 5-min default was observed truncating a real attempt
   mid-task); cost-basis determination for the delivery org.
8. **Warm-series proxy question** — decide whether same-task/reset-tree resume
   adequately proxies multi-task warm sessions, or design a mixed-task warm protocol.

## 5. CP-SCREEN-PREREG gating checklist (SPEC §6 open items)

No screening run starts until every box is checked or explicitly waived in writing by
the human. Items 1–8 map to SPEC §6's open list.

- [ ] **§6.1** Containerized agent leg + egress allowlist built and demonstrated;
      `canonical/` excluded from the image; gate confirmed `--network=none`
- [ ] **§6.2** Provider-side collector pre-gate answered: **does the billing-plane
      metric separate cached input tokens?** Answer recorded (yes → build collector;
      no → C3/C3-prev under declared cache-blind upper bound, cross-product cache
      comparisons out of scope)
- [ ] **§6.3** P2 policy file + `split.yaml` contract + per-leg usage split + tests
      landed; the B3 delivery stack selected from the verified paths
- [ ] **§6.3** P3 extracted from `harness/configurations/C5.yaml`; policy hash pinned in
      the manifest
- [ ] **§6.4** W6 and W7 built, ten-point validated, commit-mined per §5.1; **W6
      pre-registered as the escalation probe with its prediction recorded**
- [ ] **§6.5** Pricing snapshot refreshed; Product-B selector labels verified verbatim
      against `agy models`
- [ ] **§6.6** Manifest completions: per-task prompt hashes · P3 policy hash · Product-B
      version pin · `--print-timeout` pin · cost-basis determination
- [ ] **§6.7** Warm-series proxy question decided (same-task resume vs mixed-task warm
      protocol)
- [ ] **§6.8** Rate limits checked against the live-run plan; facilitator fallback
      rehearsed
- [ ] **§6.9** Legal/attribution: community plugin credited (MIT, not vendor-endorsed);
      confidential-deck content excluded; disclosure slide ready
- [ ] All W1–W7 pre-registrations committed (git history proves they precede any run)
- [ ] Escalation-probe prediction recorded; publish-either-way commitment stated
- [ ] Prior feasibility use of the W4/W1 candidates (as F2/F3) disclosed in their
      screening pre-registrations
- [ ] Reps plan declared per cell (≥5 strong/cold-sensitive, 3 elsewhere)
- [ ] Transparency label present verbatim on every planned output

## 6. Task sequence

1. Build the §4 gating items; land the §5 checklist evidence.
2. Define `tasks/suite/W1..W7` — each with `workload.yaml` (pinned repo, commit, prompt,
   deterministic-first gate script, reset script, pre-modification failure proof) and a
   pre-registration doc from `manifest/RUN_TEMPLATE.md`.
3. **CP-SCREEN-PREREG** — all seven pre-registrations, the escalation-probe prediction,
   the §5 checklist and the transparency label reviewed **before any run**. No task
   additions or removals after this point.
4. **CP-SPEND** per batch. Run screening: W1–W7 × {C1, C2, C3, C3-prev, C5} × reps per
   §3 → `results/screening-batchN/`, labeled hypothesis-seeking, not publishable.
5. Summarize each batch with `harness/telemetry/summarize.py` into
   `report/screening-batchN/decision-table.{json,md}` (per task × configuration/policy;
   every figure with its confidence tier and n/scope line).
6. Screening report per SPEC §5.2 decision rules: candidate advantages only; two-task
   rule flagged; both cost views; the **C2** comparison mandatory; negative and null
   findings included. **CP-FINDINGS** before the report is referenced anywhere.

## Acceptance checklist

- [ ] containerized agent leg + egress allowlist in place before the first run
- [ ] collector cache-breakdown pre-gate answered and recorded
- [ ] all W1–W7 pre-registrations committed before runs (git history proves order)
- [ ] escalation probe pre-registered (W6, fallback W3) and its result published either way
- [ ] no C4 cell and no C6 run in this window
- [ ] reps ≥5 on strong/cold-sensitive cells; every figure carries median, range, n
- [ ] all classes reported incl. null/negative; both cost views present
- [ ] report carries the mandatory transparency label verbatim (SPEC §5)
- [ ] `results/screening-batchN/` listed in `results/README.md` and paired with its report

**Checkpoints: CP-SCREEN-PREREG (before any run), CP-SPEND (per batch), CP-FINDINGS
(before any number is referenced).**

**Inputs:** `tasks/suite/W*/workload.yaml` + `workload-TEMPLATE.yaml` (candidate stubs —
pin repos/commits at CP-SCREEN-PREREG) · `tasks/WORKLOAD-SELECTION.md` ·
`methodology/routing-policy.md` (B1–B4 taxonomy) · `harness/policies/README.md`
(artifact registry).

**Note:** F2/F3 feasibility usage of the W4/W1 candidates must be disclosed in their
screening pre-registrations.
