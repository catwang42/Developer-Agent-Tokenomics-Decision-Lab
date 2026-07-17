# Controlled Runner (built in Phase 3)
Contract: run.sh --task <id> --config <C1|C2|P0|P1|...> --manifest <path> [--dry-run]
-> writes results/<phase>/<run_id>/{events.jsonl, summary.json}; exit 0 only when the
telemetry validator passes. --dry-run uses stub adapters (zero spend) for CI/tests.
