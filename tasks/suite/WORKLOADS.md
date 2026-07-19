# Workloads — the one table

The single answer to "what are we testing." Consolidates the pilot task, the F1–F3
feasibility tasks, and the W1–W7 screening workloads. Selection rules live in
`tasks/WORKLOAD-SELECTION.md`; per-task definitions live in `tasks/suite/W*/workload.yaml`
and `tasks/pilot-realworld/`.

Contamination tiers: `famous | moderate | obscure | post_cutoff` (schema-v2 enum,
recorded per run as `identity.contamination_tier`). `TBD-AT-PREREG` means the repo —
and therefore the tier — is fixed at **CP-SCREEN-PREREG**. Nothing here has been run;
this is a paper roster. Any live run requires **CP-SPEND**.

| Task | Class | Gate type | Contamination tier | Pinning status |
|---|---|---|---|---|
| Pilot (RealWorld) | feature_implementation | Deterministic: hidden feature tests (Draft articles: schema + list filter) | `famous` | **Pinned** `30b68e1`; 10-point validated (Phase 2, SPEC §2.8) |
| F1 | feature_implementation | Feature gate (schema + endpoint checks) | `famous` | = pilot RealWorld Draft-articles task (reuse) |
| F2 | complex_bugfix | Bugfix gate (failing repro → green, no unrelated diffs) | `famous` | = W4 (reuse); **pinned** `88b258c`, commit-mined exemplar |
| F3 | test_generation | Coverage-delta gate | TBD-AT-PREREG | = W1 candidate (reuse); pin at CP-SCREEN-PREREG |
| W1 | test_generation | Coverage-delta gate (branch coverage ≥ target, existing tests green) | TBD-AT-PREREG | CHOOSE-AT-CP-SCREEN-PREREG |
| W2 | scaffold_feature | Deterministic: hidden feature/integration tests | TBD-AT-PREREG | CHOOSE-AT-CP-SCREEN-PREREG |
| W3 | migration | Behavior-parity: all tests green + lint clean, zero behavior change | TBD-AT-PREREG | CHOOSE-AT-CP-SCREEN-PREREG |
| W4 | complex_bugfix | Bugfix gate (failing repro → green, no unrelated diffs) | `famous` (1st task) | **Pinned** `88b258c` (commit-mined exemplar); 2nd task obscure/post_cutoff at CP-SCREEN-PREREG |
| W5 | small_edit | Deterministic small-change check (break-even control) | TBD-AT-PREREG | CHOOSE-AT-CP-SCREEN-PREREG |
| W6 | code_review | Deterministic scoring vs sealed seeded-defect map (≥ k−1 found, 0 fabricated) | TBD-AT-PREREG | CHOOSE-AT-CP-SCREEN-PREREG |
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
- **Class-level claims.** One task per class is a screening signal only. Promoting a
  signal to a workload-class claim requires a second, materially different task at tier
  `obscure` or `post_cutoff` (`tasks/WORKLOAD-SELECTION.md` §3, extending SPEC §5.2),
  preferably sourced by commit mining (§4).
- **Screening scope.** W1–W5 are the SPEC §5.1 classes (spanning expected wins and the
  W5 break-even loser). W6–W7 were added before CP-SCREEN-PREREG under the SPEC §5
  anti-bias protocol.
