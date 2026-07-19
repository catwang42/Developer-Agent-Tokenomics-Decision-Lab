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

**Isolation is currently WEAK:** the only confinement is the throwaway per-task
`.work/repo` working directory (`cwd`) on this dev VM — **no container, no network
policy**. This is acceptable for feasibility/revalidation only. The posture is
recorded authoritatively on every run in `identity.permission_profile`
(`SUBJECT_PERMISSION_PROFILE` in `base.py`).

⚠️ **MANDATORY Phase-4 screening CP-SPEND item:** a subject-isolation decision
(containerized subject runs, network policy) must be made and recorded before
screening runs execute. Skipping permissions outside a real sandbox does not scale
to a larger, longer screening batch.
