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

Two declared postures (`base.py`: `SUBJECT_PROFILE_HOST` / `SUBJECT_PROFILE_CONTAINER`),
selected by the runner via `--subject-isolation` and stamped **authoritatively** into
`identity.permission_profile` + `identity.network_policy` (the runner knows the mode it
launched, so it overrides any adapter default — the adapters carry `SUBJECT_PROFILE_HOST`
only as a back-compat default):

- **HOST** (batch-1 / revalidation, superseded) — only confinement is the throwaway
  per-task `.work/repo` cwd on the dev VM: no container, no network policy.
- **CONTAINER** (batch-2, human decision 2026-07-19) — the subject execs inside the
  offline per-task image with `--network=none`; the deterministic gate runs offline in
  the same posture (`harness/container/`, `manifest` `subject_isolation`). Adapters
  route their spawn through `harness.container.exec.resolve_spawn` (host mode = run in
  `cwd`; container mode = wrap in `docker run`). The live agent leg's model-API egress
  allowlist is a **CP-SPEND finalization item** (it needs model spend to validate); the
  offline gate is fully verified this session. See `harness/container/README.md`.
