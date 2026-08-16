# Workloads — the one table

The single answer to "what are we testing." Consolidates the pilot task, the F1–F3
feasibility tasks, and the W1–W7 screening workloads. Selection rules live in
`tasks/WORKLOAD-SELECTION.md`; per-task definitions live in `tasks/suite/W*/workload.yaml`
and `tasks/pilot-realworld/`.

Contamination tiers: `famous | moderate | obscure | post_cutoff` (schema-v2 enum,
recorded per run as `identity.contamination_tier`). `TBD-AT-PREREG` means the repo —
and therefore the tier — is fixed at **CP-SCREEN-PREREG**. Nothing here has been run;
this is a paper roster. Any live run requires **CP-SPEND**.

Rows in **bold** were commit-mined and pinned on 2026-08-16 to break batch 3's ceiling
effect (27/27 controlled runs accepted, zero escalations — the roster could not separate
configurations on quality). The full 8-candidate register, including the three deferred
candidates and the one rejected, is `tasks/proposals/2026-08-commit-mined-candidates.md`.
Their remaining `awaiting_human` checks are the human-held sealed sets; the per-task
`hidden/README-FOR-HUMAN.md` says exactly what each needs.

| Task | Class | Gate type | Contamination tier | Pinning status |
|---|---|---|---|---|
| Pilot (RealWorld) | feature_implementation | Deterministic: hidden feature tests (Draft articles: schema + list filter) | `famous` | **Pinned** `30b68e1`; 10-point validated (Phase 2, SPEC §2.8) |
| F1 | feature_implementation | Feature gate (schema + endpoint checks) | `famous` | = pilot RealWorld Draft-articles task (reuse) |
| F2 | complex_bugfix | Bugfix gate (failing repro → green, no unrelated diffs) | `famous` | = W4 (reuse); **pinned** `88b258c`, commit-mined exemplar |
| F3 | test_generation | Coverage-delta gate | TBD-AT-PREREG | = W1 candidate (reuse); pin at CP-SCREEN-PREREG |
| W1 | test_generation | Coverage-delta gate (branch coverage ≥ target, existing tests green) | TBD-AT-PREREG | CHOOSE-AT-CP-SCREEN-PREREG |
| **W1b** | test_generation | Test-generation gate T1–T4 + sealed mutation-catch (Hypothesis property tests, numpy oracle) | `post_cutoff` | **Pinned** `b9d3964` (zarr-python#4054); 9/10 + 1 awaiting_human. W1's 2nd task |
| W2 | scaffold_feature | Deterministic: hidden feature/integration tests | TBD-AT-PREREG | CHOOSE-AT-CP-SCREEN-PREREG |
| **W3** | migration | Behavior-parity: PR's own tests green + hermetic baseline green, zero behaviour change | `post_cutoff` | **Pinned** `7700446` (sqlfluff#7962); 9/10 + 1 awaiting_human. **Escalation probe** |
| W4 | complex_bugfix | Bugfix gate (failing repro → green, no unrelated diffs) | `famous` (1st task) | **Pinned** `88b258c` (commit-mined exemplar); 2nd task = W1b's sibling W4b |
| **W4b** | complex_bugfix | Bugfix gate (order-independence repro → green, no unrelated diffs) | `post_cutoff` | **Pinned** `a994a4f` (zarr-python#4227); 9/10 + 1 awaiting_human. W4's 2nd task |
| W5 | small_edit | Deterministic small-change check (break-even control) | TBD-AT-PREREG | CHOOSE-AT-CP-SCREEN-PREREG |
| **W6** | code_review | Deterministic scoring vs sealed seeded-defect map (≥ k−1 found, 0 fabricated) | `post_cutoff` | **Pinned** `3feb355` (hono#5171); 4 pass / 2 awaiting_human / 4 n/a |
| W7 | greenfield_build | Deterministic: clean build + sealed PRD acceptance tests | TBD-AT-PREREG | CHOOSE-AT-CP-SCREEN-PREREG |

## Notes

- **F1–F3 double-use.** F1 is the pilot task; F2/F3 reuse the W4/W1 candidates. The
  feasibility dataset makes **no** comparative claims (SPEC §2.3); screening
  pre-registration must disclose this prior feasibility use
  (`methodology/feasibility-protocol.md`).
- **Gate priority.** Every gate above is deterministic-first (hidden tests → static
  checks → regression), per SPEC §2.6. W6's gate scores against a known seeded-defect
  ground truth, so it is deterministic despite being a "review" task; model-based
  review is never the authoritative gate.
- **Hidden tests & grading integrity.** Why the sealed sets exist, who holds them, what
  the per-result hidden-test hash proves, the rotation/release lifecycle, and how a fork
  operator authors their own set: [`docs/sealed-evaluation.md`](../../docs/sealed-evaluation.md).
- **Class-level claims.** One task per class is a screening signal only. Promoting a
  signal to a workload-class claim requires a second, materially different task at tier
  `obscure` or `post_cutoff` (`tasks/WORKLOAD-SELECTION.md` §3, extending SPEC §5.2),
  preferably sourced by commit mining (§4).
- **Screening scope.** W1–W7 is the SPEC §5.1 v2.2 roster (spanning expected wins and
  the W5 break-even loser). W6 and W7 joined it in SPEC v2.2, before CP-SCREEN-PREREG,
  under the SPEC §5 anti-bias protocol.
- **Escalation probe.** A workload selected *because* the economical tier is predicted
  to fail its gate; the prediction is recorded at CP-SCREEN-PREREG and the result
  published either way. It is the mechanism that finally exercises P1's escalation-cost
  path (SPEC §2.9 item 3, §5.1). SPEC names W6 primary and W3 fallback; for the
  screening batch the human designated **W3** as the probe, and it carries the
  registered prediction. W6 may additionally carry one if registered before any run.
- **W1b / W4b are tasks, not workloads.** They are the second tasks that let W1 and W4
  make class-level claims, so they have no `workload.yaml` of their own — the parent
  workload names them under `second_task_for_class_claim`. W3 and W6 still have exactly
  one task each, so any W3/W6 result stays a screening signal about that task.
