"""Telemetry foundation for the Developer-Agent Economics Decision Lab (SPEC 2.7).

Provides the canonical event log, the derived run-summary builder, and the
run-summary validator. Cost derivation lives in :mod:`costing`.

Design invariants (SPEC.md + CLAUDE.md non-negotiable rules):
  * Every telemetry field is a *tiered* value: ``{"value": ..., "confidence": ...}``
    where confidence in {authoritative, derived, proxy_observed, unavailable}.
  * Unavailable is recorded as unavailable, never zero-filled or imputed.
  * Summaries are *derived* from an immutable event log; missing inputs stay
    unavailable rather than defaulting to 0.
"""

from .telemetry import (  # noqa: F401
    CONFIDENCE_TIERS,
    EVENT_TYPES,
    EventLog,
    tiered,
    unavailable,
    derive_summary,
    validate,
    validate_summary,
)
