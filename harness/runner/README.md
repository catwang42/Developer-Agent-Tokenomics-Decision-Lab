# Controlled Runner (built in Phase 3)
Contract: run.sh --task <id> --config <C1|C2|P0|P1|...> --cache-state <cold|warm-series>
--manifest <path> [--dry-run] [--session-id <id>] [--resume]
-> writes results/<phase>/<run_id>/{events.jsonl, summary.json}; exit 0 only when the
telemetry validator passes AND the cache-protocol contract holds. --dry-run uses stub
adapters (zero spend) for CI/tests.

--cache-state is REQUIRED (methodology/cache-protocol.md rule 4): `cold` runs a fresh,
identified session (freshness proven from the session_id in the event log); a
`warm-series` run continues a prior session (`--session-id <id> --resume`) so the
provider prompt-cache carries over (run 1 of the series is `cold`).
