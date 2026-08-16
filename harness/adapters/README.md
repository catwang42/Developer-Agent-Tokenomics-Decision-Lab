# Adapters (built in Phase 3)
claude_code.py  - Product A; usage from claude -p --output-format json metadata (authoritative)
agy.py          - Product B; WORKSHOP-OWNED wrapper: our exit codes/timeouts; records the
                  product selector label verbatim; unexposed usage -> unavailable
hybrid_c5.py    - integrated workflow; two billing legs tagged; frontier-share diagnostic
stub_*.py       - synthetic-fixture adapters for tests ONLY (never write under results/)

## Subject sandbox posture (SPEC 1.3; recorded 2026-07-19)

Benchmark subjects run agentic, so the real CLIs are invoked with
`--dangerously-skip-permissions` (Product A `claude -p`, Product B `agy`): tool use
(Edit/Write/Bash) is **auto-approved**. Without this the headless agent can read but
cannot modify files — the root cause of the batch-1 0/25 no-write failures.

Three declared postures (`base.py`: `SUBJECT_PROFILE_HOST`,
`SUBJECT_PROFILE_CONTAINER_GATE`, `SUBJECT_PROFILE_CONTAINER_AGENT`), selected by the
runner via `--subject-isolation` / `--subject-egress` and stamped **authoritatively**
into `identity.permission_profile` + `identity.network_policy` (the runner knows the
mode it launched, so it overrides any adapter default — the adapters carry
`SUBJECT_PROFILE_HOST` only as a back-compat default). Each stamp states what is
*actually* enforced and nothing more (the FIX C lesson):

- **HOST** (batch-1 / revalidation, and still the supported feasibility fallback) —
  the subject tree is staged outside the lab repo and harness path pointers are
  scrubbed, so task material is unreachable by traversal or env pointer; but there is
  no container, no filesystem namespace and no network policy.
- **CONTAINER / gate** (batch-2, human decision 2026-07-19) — the deterministic gate
  execs inside the offline per-task image with `--network=none`. Task material is
  present *by design*: the gate reads `task.yaml` to know what to grade.
- **CONTAINER / agent leg** (SPEC §6 item 1) — a *separate* image
  (`lab-subject-agent/…`) with the product CLIs baked at build-asserted pinned
  versions, credentials mounted read-only, no `canonical/`/`hidden/`/`task.yaml` in
  any layer (asserted at build), and egress restricted to a hashed model-API
  allowlist recorded in `identity.network_policy`. The allowlist's **enforcement** is
  verified without spend (`harness/container/verify-egress.sh`); whether it is
  *sufficient* for a live agentic run stays open until a CP-SPEND-approved run.

Adapters route their spawn through `harness.container.exec.resolve_spawn` (host mode =
run in `cwd`; container mode = wrap in `docker run`) and are otherwise unaware of the
posture. See `harness/container/README.md` and `manifest` `subject_isolation`.

## Adding a benchmark subject (adapter contract — a supported extension point)

A new AI coding agent is added as a **benchmark subject** by writing an adapter — never
by editing the runner. The runner owns the clock, the deterministic gate, policy
semantics, cost derivation, and the authoritative identity/isolation stamps; an adapter's
sole job is to *execute one attempt* and *emit telemetry events*. Contract lives in
`base.py`; `claude_code.py` (Product A) and `agy.py` (Product B) are the reference
implementations.

### Required interface

Subclass `Adapter` (`base.py`) and implement one method:

```python
class MyAdapter(Adapter):
    name = "my_adapter"            # the `adapter:` value a config/policy references
    def run_attempt(self, spec: AttemptSpec, subject_dir: str, emit: EmitFn) -> AttemptOutcome:
        ...
```

- `spec: AttemptSpec` — one attempt = one billing **leg**: `leg_id`, `role`, `resolved`
  (a manifest-resolved `ResolvedModel`), `prompt`, and the cache-protocol contract
  (`cache_state`, `session_id`, `resume`). The runner owns these; the adapter only
  honours them (e.g. a `warm-series` attempt resumes `session_id`).
- `subject_dir: str` — the staged subject working tree (host mode) the CLI runs against.
- `emit: EmitFn` — `emit(event_type, **payload)`; the runner supplies the timestamp. At
  minimum emit `model_call_started` (with `**leg_identity_payload(resolved)` and
  `**session_payload(spec)`) and `model_call_completed` (with `usage=<tiered dict>` and
  the same leg meta). The event vocabulary is frozen (CP-SCHEMA) — carry new fields in
  existing events' payloads, don't invent event types.
- Return `AttemptOutcome(identity=…, leg_options=…, invocation=…)` — all optional, all
  defaulting empty. `invocation` (argv/cwd/exit_code/stdout/stderr) is diagnostic
  provenance for `invocation.txt`, **not** telemetry.

### Telemetry rule (non-negotiable — CLAUDE.md rules 1–3)

Every usage class is **either** emitted from the product's own machine-readable usage
metadata (authoritative tier) **or** recorded `unavailable` — **never `0`, never parsed
from model prose, never model-self-reported.** Use `usage_field(value, confidence, reason)`
/ `tiered(...)` / `unavailable(...)` from `base.py`/`telemetry.py`; a `None` count becomes
`unavailable`, not zero. Keep usage parsing a **pure function** of the product's output so
it is unit-testable without spending (see `usage_from_claude_json`).

### Identity stamping & the runner's authoritative override

Return the tiered identity fields you *observed* (product, provider, auth/billing path,
region, and the resolved model — see below) in `AttemptOutcome.identity`. **Do not try to
own the isolation posture:** the runner authoritatively overrides
`identity.permission_profile` and `identity.network_policy` (and `cache_state` /
`session_state`) with the mode it actually launched via `--subject-isolation`. Adapters
carry `SUBJECT_PROFILE_HOST` only as a back-compat default; the runner's stamp wins.

### Exit codes & timeouts (workshop-owned wrappers)

The adapter owns its own timeout (`DEFAULT_TIMEOUT_S`) and exit-code interpretation — a
subject CLI's headless quirks are the *workshop's* to bound, not the product's (SPEC §1.3;
`agy.py` even defines its own `EXIT_TIMEOUT`). On timeout or an unparseable response:
record every usage class `unavailable` (never zero), `emit("failure", …)` with a category,
still emit `model_call_completed`, and capture `exit_code`/`stdout`/`stderr` into the
`invocation` dict so a no-output run is itself diagnosable. Never let a hung leg stall the
batch.

### Container spawn

Route the subject command through `resolve_spawn` so host vs container is the *only*
difference:

```python
argv, cwd = resolve_spawn(self.container, cmd, subject_dir)
proc = subprocess.run(argv, cwd=cwd, env=agent_env(), timeout=DEFAULT_TIMEOUT_S,
                      capture_output=True, text=True, check=False)
```

`self.container` is `None` in host/dry-run/test mode (runs `cmd` in `subject_dir`) and a
`ContainerLaunch` under `--subject-isolation container` (wraps `cmd` in `docker run`,
offline by default; the launch carries the credential mounts, the enumerated env and the
per-run handoff volume). Always spawn with `agent_env()` — it strips harness/task pointers
from the environment so the subject never receives a path to `canonical/`, `hidden/`, or
the task dir (isolation FIX B).

Report the CLI version with `cli_version("claude", self.container)`: in host mode it
execs `--version`, in container mode it reads the version **label the build asserted**,
so the stamp describes the binary that actually ran rather than the one on the host.

### Verbatim model-selector label

Record the product's selector **verbatim** (`tiered(resolved.model_or_selector, …)`);
**never infer a backend model version the product does not guarantee** (SPEC §6.3). If —
and only if — the product reports the concrete version it actually served, record that at
`authoritative` in preference to the requested selector (as `claude_code.py` does from
`modelUsage`); otherwise keep the requested selector at its declared tier. A resolved id
is never invented.

### Registration & spend gate

Add the class to `REAL_ADAPTERS` in `harness/adapters/__init__.py` (keyed by `name`) and
point a configuration/policy's `adapter:` field at that name. Guard live execution behind
`LAB_ALLOW_SPEND=1` at the top of `run_attempt` (raise otherwise), exactly like the
existing adapters — `--dry-run` uses `StubAdapter` and never reaches your code.

### Worked outline — a hypothetical `codex` adapter (outline only, no code here)

To add a `codex`-style CLI subject you would, in a new `harness/adapters/codex.py`:

1. **`build_command(prompt, selector, …)` — pure.** Assemble the headless invocation
   (its non-interactive/print flag, its model/selector flag set to the manifest selector
   verbatim, its JSON-output flag, and whatever auto-approves tool use so the agent can
   actually edit files). No execution here — keep it unit-testable.
2. **`usage_from_codex_json(obj)` — pure.** Map the product's JSON usage keys to our token
   classes via `usage_field`; any class the product omits → `unavailable`. If it exposes a
   cost figure, pass it through `leg_options["provider_reported_usd"]`; do not derive it.
3. **`run_attempt`.** Refuse unless `LAB_ALLOW_SPEND=1`; `emit("model_call_started", …)`;
   `resolve_spawn(self.container, cmd, subject_dir)`; run with `agent_env()` + a
   workshop-owned timeout; on timeout/parse-failure record usage `unavailable` + a
   `failure` event; `emit("model_call_completed", usage=…, **leg_meta)`; return
   `AttemptOutcome` with observed identity (verbatim selector; resolved version only if the
   product reports it), `leg_options`, and the `invocation` record.
4. **Register** `CodexAdapter.name = "codex"` in `REAL_ADAPTERS`, add a `configurations/`
   entry with `adapter: codex` and a `manifest` model_ref, and add stub-adapter dry-run
   tests. No runner change is needed — that is the point of the contract.
