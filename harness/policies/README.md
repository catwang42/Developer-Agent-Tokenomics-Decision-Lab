# Routing policies — artifact registry (mirrors SPEC §2.1c)

Every routing policy and acceptance-gate artifact the lab uses, with its location and
build status. Lab users and forkers resolve **any** policy or gate reference in the
specification through this table; a policy referenced elsewhere in the spec but absent
here is a specification defect.

This file mirrors SPEC §2.1c. SPEC is the source of truth — if the two disagree, SPEC
wins and this file is the thing to fix. Family definitions (B1–B4) and what each does
and does not causally support live in
[`methodology/routing-policy.md`](../../methodology/routing-policy.md).

## Routing policies (`harness/policies/`)

| ID | File | Status | What it encodes | Used by | Manifest pin |
|---|---|---|---|---|---|
| P0 | `p0-baseline.yaml` | **Exists** | Static strong single-model baseline; no escalation; deterministic gate | Controlled set; ex220-B/B1 | — (model refs resolve via manifest) |
| P1 | `p1-cheap-first.yaml` | **Exists** | Economical attempt → pre-registered gate → escalate on fail; records intention-to-route, completed route, failed-attempt costs; both legs billed | Controlled set; ex220-B/B2 | — (model refs resolve via manifest) |
| P2 | `p2-delegation.yaml` | **Built and runnable** (`harness/runner/delegation.py`; `--config P2`). Reference splits for the pilot and W1 **pinned and frozen** (human freeze 2026-08-16); `P2` accepted by the telemetry schema since the CP-SCHEMA widening of 2026-08-16. Live delegation itself is still **unverified** — it needs a CP-SPEND run | Scripted delegation: pinned `tasks/<task>/split.yaml` assigns executor vs conductor scopes; both legs itemized | ex220-B/B3 | split-file hash per task (`<task>.delegation_split.sha256`) |
| P3 | `p3-policy-delegation.yaml` | **Built** (SPEC §6 item 3). C5's inline rules extracted verbatim; `C5.yaml` references the policy by path and the runner hash-checks it against the manifest. Pinned as `proposed` — awaiting human freeze | Policy-driven delegation governing C5: conductor decides when to delegate to the cross-family executor | ex220-B/B4; C5 companion runs | policy hash `routing_policies.P3.sha256` (**required before any C5 run is cited in workshop material**) |

## P2 split-file contract (`tasks/<task>/split.yaml`)

B3 is *scripted*: the assignment is fixed **before** the run by a pinned file, and no
runtime decision may change it. (A conductor that decides *when* to delegate is B4/P3 —
a different family with different claims.) The loader is
[`harness/runner/delegation.py`](../runner/delegation.py); it refuses anything
ambiguous rather than repairing it.

```yaml
split_version: 1                 # must be 1
policy: P2                       # must be P2
task_id: <the task's own task_id> # must match tasks/<task>/task.yaml
executor_scopes:                 # non-empty; ECONOMICAL_MODEL_A does these
  - id: E1-...                   # unique across BOTH lists
    kind: scaffold               # scaffold | boilerplate | test_generation
    step: >                      # what to do — a path list alone is not an assignment
      ...
    paths: [src/foo/]            # globs; a trailing '/' means "anything under here"
    writes: true                 # explicit bool; never inferred
conductor_scopes:                # non-empty; STRONG_MODEL_A does these
  - id: C1-...
    kind: integration            # integration | edge_cases | final_verification
    step: >
      ...
    paths: [src/bar.ts]
    writes: false
```

Enforced on load:

- **Kind vocabulary is closed, per side.** A step that does not fit its side's kinds
  belongs on the other side; free-text kinds would make the split unreadable as B3.
- **Both sides must be non-empty.** A split with an empty side is a single-model run
  wearing P2's label.
- **Write scopes must agree with the task's own gate scope.** For a feature/bugfix task
  `target_paths` are writable; for a **test-generation** task they are read-only and
  writes are confined to `agent_write_scope` (W1 inverts the pilot). A split that gets
  this backwards would fail the gate's diff-scope check on every run, so it is refused.
- **The hash is over the raw file bytes**, comments included, and must equal
  `manifest/delivery-manifest.yaml → <task>.delegation_split.sha256`. A live run
  additionally requires `status: frozen`; `--dry-run` is allowed on a draft.

What lands in telemetry: `split_file`, `split_sha256` and the scope ids ride on the
delegated legs' existing `model_call_started` / `model_call_completed` events (no new
event type — the vocabulary is frozen), so a run's delegation policy is reconstructible
from the event log plus the manifest.

Reading the resulting legs: per-leg usage comes from the product's own `modelUsage`
metadata, matched to a leg by base model name. `behavior.turns` counts
`model_call_completed` events, so under P2 it counts **billing legs, not product
turns** — the product's own `num_turns` is recorded on the conductor's event. A leg the
product never metered is `unavailable` (never 0) plus a `delegation_leg_unmetered`
failure, because "the executor did no work" and "delegation never happened" look
identical in the tokens and only the second is a defect.

### P2 and the telemetry schema (closed — CP-SCHEMA approved 2026-08-16)

`harness/telemetry/schema-v2.json`'s `configuration_id` enum was widened **additively**
to `C1 C2 C3 C3-prev C4 C5 P0 P1 P2` (schema note: "v2.1 2026-08-16: additive enum
widening (C3-prev, P2), human-approved; all v2.0 summaries remain valid"). Nothing else
in the schema changed and every existing batch summary still validates, so a P2 run now
records as a valid summary. `tests/test_telemetry.py` asserts the enum accepts both new
ids, rejects an unknown one, and stays in agreement with the ids the runner can plan.

What is still open is not the schema but the **evidence**: live delegation is
`unverified` in the policy until a CP-SPEND-approved run shows the product honouring the
subagent definition and metering both models separately.

## P3 policy reference (`harness/configurations/C5.yaml` → `p3-policy-delegation.yaml`)

A configuration declares the **stack**; a policy declares the **routing decision**.
C5's delegation rules used to sit inline in `C5.yaml`, where nothing hashed them — so
"which rules did this run execute?" was unanswerable from the artifacts. They are now
extracted **verbatim** into P3 and referenced by path:

```yaml
# harness/configurations/C5.yaml
policy_ref: P3
policy_file: harness/policies/p3-policy-delegation.yaml
```

[`run.py:resolve_config_policy`](../runner/run.py) resolves the reference before any
work and refuses: a configuration carrying **both** a reference and inline `rules` (two
copies drift, and only one is hashed); a `policy_ref` that disagrees with the file's own
`policy_id`; a policy that does not declare it `governs:` this configuration; and a file
whose bytes no longer match `manifest → routing_policies.P3.sha256`. The hash is over the
**raw file bytes**, comments included, so a comment-only edit breaks the pin — as it
should, since the comments carry the claims-register text.

This is a **validation-only** change: the rules describe how a C5 run is *read*, not how
it *executes*, so C5 runs behave exactly as before the extraction
(`tests/test_policy_p3.py` pins the resolved rule list to the pre-extraction literal).
What the extraction buys is that a drifted policy now stops the run instead of quietly
changing what the numbers mean.

## Acceptance-gate artifacts (SPEC §2.6 priority order; per task)

| Artifact | Location | Status |
|---|---|---|
| Deterministic public checks (typecheck, build, regression, diff-scope, no-leakage, public feature test) | `tasks/<task>/` gate scripts + public tests | **Exist** for the pilot, W4, W1 |
| Sealed hidden tests | `tasks/<task>/hidden/` (gitignored, human-authored) | **Exist and hashed in the manifest** for all three tasks: pilot-v2, sealed-w4-v2, w1-v1 (three sha256s recorded) |
| Human-review rubric (timed) | `report/batchN/human-effort-rubric.md` | **Exists**; executed for batch 3 (criterion 6) |
| Evaluator | `harness/evaluator/` | **Exists**; version and hash published per SPEC §2.6 |

## Not yet pinned in the manifest

Open, SPEC §6 item 6: per-task **prompt hashes** · **Product-B version** and
**`--print-timeout`** pins.

Pinned but **not yet frozen** (human review outstanding, so nothing produced under them
is citable): the two P2 split hashes (`pilot_task` / `w1_task` `.delegation_split`) and
the P3 policy hash (`routing_policies.P3`).

## Rules

- **Policies are executed by configurations, not the reverse.** `harness/configurations/`
  declares the product+model stack; a policy declares the routing decision. Comparisons
  across the two axes never merge (SPEC §2.1b).
- **Model references are placeholders** (`STRONG_MODEL_A`, `ECONOMICAL_MODEL_A`) and
  resolve only through `manifest/delivery-manifest.yaml`. Never hardcode a model ID or a
  price in a policy file.
- **A policy is not citable until its manifest pin exists and is frozen** where the table
  above requires one. P3 in particular: no C5 run may be cited in workshop material before
  its policy hash is in the manifest (it now is, at `status: proposed`) and a human has
  frozen it.
