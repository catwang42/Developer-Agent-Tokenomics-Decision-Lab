"""Per-run results emission (compact, derived from the canonical summary).

``summary.json`` (SPEC 2.7, validated) stays the authoritative audit artifact.
``result.json`` is a small, flat PROJECTION of it — task, config, gate verdict,
telemetry, isolation posture — for quick scanning and aggregation. It invents no
numbers: every value is copied from the summary (tiers preserved), so it can be
regenerated from ``summary.json`` at any time.
"""

from .record import RESULT_SCHEMA_VERSION, build_result_record

__all__ = ["RESULT_SCHEMA_VERSION", "build_result_record"]
