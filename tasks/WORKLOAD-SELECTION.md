# Workload Selection Criteria

How benchmark repositories and tasks are chosen for the suite (pilot, F1–F3
feasibility, W1–W7 screening). This document sets the gate a candidate must pass
*before* it can be pinned at pre-registration. It extends — never overrides —
SPEC §2.6, §2.8, and §5.2. If anything here conflicts with SPEC.md, SPEC.md wins.

Nothing here authorizes a live benchmark run. Selecting and pinning a task is a
paper exercise; running it against any product still requires CP-SPEND.

## 1. Selection criteria (all must hold before a task is pinned)

A candidate repository/task is admissible only if **every** criterion below is
satisfied and demonstrated (not asserted):

1. **Deterministic gate is feasible.** The acceptance decision can be reduced to
   hidden deterministic tests plus static checks (types, lint, regression), in the
   priority order of SPEC §2.6. If the only credible acceptance signal is human
   judgment, the task is a poor benchmark candidate — model-based review is
   supplementary and separately measured, never the authoritative gate.
2. **Pinnable and container-reproducible.** A specific commit can be pinned, all
   dependencies resolve from that pin, and a clean-container build + baseline test
   pass is reproducible from scratch. No floating tags, no network-dependent build
   steps that are not themselves pinned.
3. **Realistic size for the class.** Large enough to exercise the class as a real
   engineering task (multi-file where the class implies it), small enough to run
   and reset deterministically inside the harness time/cost envelope. Trivial size
   is acceptable *only* for the W5 break-even control, where it is the point.
4. **License OK.** The repository license permits us to clone, modify, run, and
   redistribute derived fixtures/telemetry for workshop and report use. Record the
   license in the workload definition; exclude anything ambiguous or non-permissive.
5. **Task fails pre-modification.** Before any agent touches it, the task's gate
   must FAIL (the failing repro test, the missing coverage, the absent feature).
   A task that already passes measures nothing. This is the pre-modification
   failure proof required at pre-registration.

These extend the pilot 10-point validation (SPEC §2.8): a task that passes the
10-point script has, by construction, satisfied criteria 1–5 for the pilot class;
suite candidates are held to the same bar via the same script.

## 2. Contamination tiers

Every task's source repository is assigned a **contamination_tier** — an estimate
of how heavily the repo (and canonical solutions to the task) are likely present in
model training data. The tier is resolved from the workload definition and recorded
per run in telemetry (`identity.contamination_tier`, schema-v2 enum). It is a
declared property of the *task source*, not a measurement of any model.

| Tier | Definition |
|---|---|
| `famous` | Widely known, widely forked/blogged repo or canonical reference app. Task and likely its solution are strongly represented in training data (e.g. a well-known reference/starter application). Memorization is a live confound. |
| `moderate` | Real project with meaningful public presence but not a canonical teaching example. Some representation plausible; whole-solution recall less likely. |
| `obscure` | Low-visibility repository: few forks/stars, little derivative writing, not a common tutorial subject. Solution recall unlikely, though incidental exposure cannot be excluded. |
| `post_cutoff` | Task content created (or the specific change authored) after the subject model's training cutoff — e.g. a PR merged after cutoff, or a freshly authored task. Direct memorization of the solution is excluded by construction for that model; record the cutoff basis and date. |

Tiers are estimates, declared before running and never revised based on results
(anti-bias protocol, SPEC §5). `post_cutoff` is model-relative: a task can be
`post_cutoff` for one subject and `moderate` for another, so record the cutoff
basis alongside the tier, not just the label.

## 3. Contamination rule for class-level claims (extends SPEC §5.2)

SPEC §5.2 already requires that promoting a screening signal to a **workload-class
claim** needs a *second, materially different task* from that class (preferably a
different repository), with the same direction of effect, surviving both cost
views.

This document adds one requirement on top:

> **The second task must be tier `obscure` or `post_cutoff`.**

Rationale: a class-level claim built on two `famous`/`moderate` tasks cannot
distinguish an economic effect from shared training-data memorization. Requiring
the corroborating task to be low-contamination forces the claim to hold on at
least one task where solution recall is not a plausible explanation. The first
task in a class may be any tier (it is only a screening signal); the *promotion*
of that signal to a class claim is what this rule gates.

This does not weaken any SPEC §5.2 condition — all of them still apply
(beats C2, both cost views, all failed attempts/verification/rework/human review
included, stable across repeated runs). It adds a contamination constraint the
existing text left implicit. All findings remain scoped: "for this workload class,
under these pinned conditions."

## 4. Commit-mining: the preferred sourcing method for second tasks

For the low-contamination second task a class claim requires (§3), the preferred
sourcing pattern is **commit mining**:

- Pick a real merged pull request at commit **N** in a suitable repository.
- The task is: **re-implement the change introduced by that PR, starting from the
  parent commit N−1.** The agent works from N−1 and must reproduce the effect of N.
- The **gate is that PR's own tests** — the tests added or modified by the PR —
  extracted and **held as hidden tests** (SPEC §2.6 sealed-hidden-test policy).
  Public material publishes the task spec, any pre-existing public tests, and the
  evaluator hash; the PR's own tests stay sealed during the evaluation cycle.
- The **pre-modification failure proof** is free: at N−1 the PR's tests fail by
  construction (the change that makes them pass has not been applied yet).

Why this is preferred for second tasks:

- **Contamination control.** Choosing a PR merged **after** a subject model's
  training cutoff yields a `post_cutoff` task directly; an older PR in a
  low-visibility repo yields `obscure`. Either satisfies §3.
- **Authentic, self-validating gate.** The tests were written by the project's own
  maintainers for exactly this change, so the gate reflects real acceptance
  criteria rather than tests we authored to match a solution we already saw.
- **Deterministic and pinnable.** N and N−1 are exact commits; reset is a checkout.

Constraints when mining commits: verify the PR's tests actually fail at N−1 and
pass at N in a clean container (criteria 1, 2, 5); exclude PRs whose tests are
flaky or environment-dependent; strip any commit message / PR description leakage
from participant-visible material; record the repo, PR number, N, N−1, license,
and the sealed-test hash in the workload definition and per-run telemetry.

## 5. Where selections are recorded

- Per-task definition: `tasks/suite/W*/workload.yaml` (and `workload-TEMPLATE.yaml`).
- Consolidated view of the whole suite: `tasks/suite/WORKLOADS.md`.
- Final pins, tiers, and cutoff bases are frozen at **CP-SCREEN-PREREG**; until
  then repos read `CHOOSE-AT-CP-SCREEN-PREREG` and tiers read `TBD-AT-PREREG`.
