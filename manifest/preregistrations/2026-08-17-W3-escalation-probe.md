# W3 escalation probe — economical-tier failure prediction
**Registered:** 2026-08-17, before any screening-batch run. Human-authored.
**Task:** W3-migration (sqlfluff #7962 — dialect-dispatch extraction, +716/−348
across 12 files, ~30-dialect byte-identical parity gate).
**Arms concerned:** C2 (economical solo) and P1 (cheap-first escalation, run on
this task only as the designated probe).

Prediction: the economical tier (claude-sonnet-4-6) fails W3's full gate —
most likely on the parity requirement or the call-site-rewiring requirement —
causing P1 to escalate to the strong tier. This task was DELIBERATELY selected
as a difficulty probe under the anti-selection-bias protocol (SPEC v2.2 §5.1);
the selection rationale is recorded in PR #13/#14's mining table.

**Result published either way** — including the null result if the economical
tier passes and escalation never fires.
