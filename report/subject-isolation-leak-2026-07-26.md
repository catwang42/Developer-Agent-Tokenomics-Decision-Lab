# Subject-isolation leak — finding, impact, and remediation (2026-07-26)

Internal engineering record (not published; no vendor-comparative claims). Documents a
subject-isolation weakness in the controlled harness under `--subject-isolation host`,
which configurations/runs it affected, why the telemetry cannot settle whether it was
exploited, and what the remediation now enforces vs. what is deferred to Phase-4
containerisation.

## 1. What was reachable

Under `--subject-isolation host` the agent CLI was spawned with only its **working
directory** set to `<TASK_DIR>/.work/repo` (`resolve_spawn(None, cmd, subject_dir)` →
`subprocess.run(argv, cwd=subject_dir)`), with `--dangerously-skip-permissions`
(all tools auto-approved), as the **same OS user** that owns the whole lab repo, with
**no container, no chroot/mount namespace, no seccomp, and no network policy**. `cwd`
is a starting directory, not a boundary.

Because the subject repo lived *inside* the lab repo, the answer/test material sat two
levels up and was reachable by ordinary relative traversal from the agent's cwd:

| From agent cwd `<TASK_DIR>/.work/repo` | Resolves to | Contents |
|---|---|---|
| `../../canonical/` | `<TASK_DIR>/canonical/` | reference solution (e.g. `draft-articles.patch`) — **committed** |
| `../../hidden/` | `<TASK_DIR>/hidden/` | sealed hidden tests — gitignored but **physically present** during runs |
| `../../task.yaml` | `<TASK_DIR>/task.yaml` | task spec that **names the answer path**: `canonical_patch: canonical/draft-articles.patch` |

All three task dirs (F1 `tasks/pilot-realworld`, F2 `tasks/suite/W4-complex-bugfix`,
F3 `tasks/suite/W1-test-generation`) had `canonical/` and `hidden/` present, mode
`drwxr-xr-x`, owned by the agent's own uid → fully readable and writable. Reading the
public `task.yaml` alone hands an agent the exact relative path to the canonical
solution.

**Directly observed traversal (this session's Product-B smoke run, same host posture):**
the agent read `task.yaml`, referenced the task's public test *outside* the subject
repo, and attempted `find /…/Developer-Agent-Tokenomics-Decision-Lab/ -name
"validate.sh"` (a repo-root-wide walk). No canonical/hidden read was observed in that
transcript (it timed out first), but it confirms the escape is real and exercised.

## 2. Which runs were affected

The weakness was present for **every host-isolated run in the project's history** — the
posture, not any single run, was unconfined:

- **Batch 1** — 25 runs (2026-07-19), host mode.
- **Batch 2** — all **34 runs** (2026-07-20), host mode (`identity.permission_profile`
  recorded the then-current, and now-known-inaccurate, `…cwd-confined-.work-repo…`
  string; see §4).
- The 2026-07-26 Product-B smoke run (host mode) as well.

"Affected" means **reachable-and-unconfined**, not "confirmed exploited."

## 3. Whether any run read the material: telemetry cannot confirm or rule it out

The lab's own run artifacts **cannot** answer this:

- Batch-2 `events.jsonl` contains only `model_call_started` / `model_call_completed` /
  `acceptance`. The real adapters emit **no** `file_read`/`tool_invoked` events (only
  the dry-run stub does); `model_call_completed` records aggregates (`num_turns`,
  `permission_denials` = 0 across all legs, `is_error`, `result_chars`, `usage`) but
  **never filenames or paths**.
- Batch-2 **predates** the `invocation.txt` artifact (added 2026-07-26), so no CLI
  stdout/transcript was captured for any batch-1/2 run.
- `agent-solution.diff` records **writes**, not reads — and pre-Fix-5 it was itself
  contaminated by the gate's `test_compat_patch` (a separate, already-fixed bug).

So there is **no instrumentation** in batch 1 or 2 that could evidence, or exclude, a
read of `canonical/`/`hidden/`. `permission_denials = 0` confirms nothing would have
blocked or logged such a read.

Deeper forensic sources exist but were **not** inspected here, deliberately: Product A
(`claude`) may retain session transcripts under `~/.claude/…`, and Product B (`agy`)
writes per-task "brain" logs under `~/.gemini/antigravity-cli/brain/…`. If an agent had
read a hidden test, such a transcript would **contain the sealed content** — so
grepping them would itself breach the sealed-hidden-test policy (SPEC §2.6). That
forensic step, if wanted, must be human-performed under the sealed policy.

**Consequence for the data:** batch-1/2 cannot be *certified* leakage-free from their
own telemetry. They remain internal, non-comparative feasibility telemetry
(`report/telemetry-completeness.md`); this finding does not change any published number
(there are none), but it should be cited if batch-1/2 acceptance outcomes are ever
reused as anything beyond instrument-shakedown data.

## 4. What the remediation now enforces (host mode)

Commits (branch `phase/3-harness`, 2026-07-26):

- **FIX A — stage the subject outside the lab repo** (`6898a5c`). `_setup_subject()`
  prepares the tree as before, then copies **only the subject repo** into a per-run
  temp dir **outside** `REPO_ROOT` (`_stage_subject_outside_repo`, symlinks preserved).
  From `<staged>/repo` no `../` chain reaches `canonical/`, `hidden/`, or `task.yaml`
  — they are not staged at all. Refuses if the temp dir resolves inside the repo. The
  gate (trusted harness code) still grades the staged tree via `TASK_WORKDIR`
  (`real_gate`/`_gate` now take `subject_dir`); `TASK_DIR` still lets the gate read
  `gate/`, `tests/`, `hidden/`. Staged tree is cleaned up after the run.
- **FIX B — stop advertising the answer** (`3b33f62`). Verified no task prompt
  references `canonical/`/`hidden/`/task dir, and the runner never exports
  `TASK_DIR`/`TASK_WORKDIR` into `os.environ`. Defensively, the agent subprocess now
  runs with `env=agent_env()`, which drops harness pointer vars (`TASK_DIR`,
  `TASK_WORKDIR`, `TASK_YAML`, `MANIFEST`, `GATE_REPORT`, `HIDDEN_REPORT`,
  `HIDDEN_TESTS_DIR`) while preserving provider auth / PATH / HOME.
- **FIX C — honest label** (`b36e680`). `SUBJECT_PROFILE_HOST` no longer claims
  `cwd-confined-.work-repo`. It now states what is enforced (subject staged outside
  the repo; no relative-path traversal to `canonical|hidden|task.yaml`; env pointers
  scrubbed) and what is **not** (same-uid, no container, no fs namespace,
  absolute-path filesystem access still possible, no network policy).
- **FIX D — image hygiene** (`63fed1e`). `.dockerignore` now excludes `**/canonical/`
  (alongside `**/hidden/`), so the Phase-4 containerized agent leg cannot bake the
  reference solution into the image.
- **FIX E — tests** (`34baebb`). Assert that from the staged root the sensitive
  relative paths neither exist nor resolve into the lab repo, that the staged tree is
  outside `REPO_ROOT`, and that staging refuses an in-repo temp dir.

Net effect (host mode): the specific documented leak — **relative-path traversal to the
answer/test material, plus an env/prompt pointer to it** — is closed.

## 5. What remains deferred to Phase-4 containerisation

Host mode is honestly a **weak** posture even after these fixes. Still **not**
prevented:

- **Absolute-path filesystem access.** The agent runs same-uid with no fs namespace, so
  it can still read anywhere the user can via an absolute path
  (`/…/tasks/<task>/canonical/…`, `~/.claude`, `~/.gemini`, etc.). Staging only removes
  the *relative* path and the harness pointers; it is not a sandbox.
- **Network.** No egress policy in host mode.

The real isolation boundary is the **containerized agent leg** (currently unimplemented;
`Dockerfile.subject` bakes no `claude`/`agy`, `resolve_spawn` passes the agent-leg
container no creds/egress). It is a **HARD REQUIREMENT** at the Phase-4 screening
CP-SPEND (`report/telemetry-completeness.md` §6 condition 1): run the subject inside the
per-task image with a restricted egress allowlist, the deterministic gate offline
(`--network=none`), and `canonical/`+`hidden/` excluded from the image (FIX D) and
mounted only where the *gate* needs them. Until then, host runs should be treated as
"reachable-but-not-sandboxed," and results as instrument-shakedown data only.

## 6. Follow-ups (not done here)

- Optional: add file-access telemetry (record the agent's read/tool events) so a future
  run can *evidence* isolation, not just assert it.
- If assurance about batch-1/2 is required, a human may inspect the Product-A/B session
  logs under the sealed policy (not automatable without risking exposure of sealed
  content).
