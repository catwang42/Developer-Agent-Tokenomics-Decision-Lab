"""Build a compact per-run ``result.json`` record from a run summary.

A PURE projection: `build_result_record` copies fields out of the canonical
``summary.json`` and never computes or fabricates a value. Tiered fields keep their
``{value, confidence}`` shape, so an unavailable field stays ``value=None`` (never
zero-filled — CLAUDE.md rules 1 & 3). ``summary.json`` remains the source of truth;
this record just makes per-run facts (gate verdict, tokens, cost, isolation posture)
easy to scan and aggregate without re-reading the full summary.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

RESULT_SCHEMA_VERSION = "result-v1"

# Token classes surfaced in the compact record (the billed classes + reasoning).
_USAGE_KEYS = (
    "input_tokens", "cache_creation_tokens", "cache_read_tokens", "output_tokens",
    "reasoning_tokens",
)
# Behaviour counts worth carrying per run for aggregation.
_BEHAVIOR_KEYS = ("turns", "retries", "escalations", "subagent_calls", "verifier_calls")


def _tiered_or_none(obj: Any) -> Optional[Dict[str, Any]]:
    """Return a tiered field verbatim (value+confidence[+reason]); None if absent."""
    if isinstance(obj, dict) and "value" in obj and "confidence" in obj:
        out = {"value": obj["value"], "confidence": obj["confidence"]}
        if "reason" in obj:
            out["reason"] = obj["reason"]
        return out
    return None


def _public_gate_verdict(gate_checks: Dict[str, Any]) -> Optional[str]:
    """'pass'/'fail' from the public gate report, if present (else None)."""
    pub = (gate_checks or {}).get("public") or {}
    checks = pub.get("checks")
    if not isinstance(checks, list) or not checks:
        return None
    return "pass" if all(c.get("status") == "pass" for c in checks) else "fail"


def build_result_record(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Project a run ``summary`` dict to a compact result record (pure)."""
    identity = summary.get("identity") or {}
    acceptance = summary.get("acceptance") or {}
    economics = summary.get("economics") or {}
    behavior = summary.get("behavior") or {}
    usage = summary.get("usage") or {}
    gate_checks = acceptance.get("gate_checks") or {}

    legs: List[Dict[str, Any]] = []
    for leg in summary.get("legs") or []:
        legs.append({
            "leg_id": leg.get("leg_id"),
            "role": leg.get("role"),
            "cost_basis": leg.get("cost_basis"),
            "model_or_selector": _tiered_or_none(leg.get("model_or_selector")),
            "marginal_operating_usd": _tiered_or_none(leg.get("marginal_operating_usd")),
        })

    record: Dict[str, Any] = {
        "result_schema": RESULT_SCHEMA_VERSION,
        "run_id": summary.get("run_id"),
        "task_id": summary.get("task_id"),
        "task_suite_version": summary.get("task_suite_version"),
        "configuration_id": summary.get("configuration_id"),
        "manifest_ref": summary.get("manifest_ref"),
        "hidden_test_hash": summary.get("hidden_test_hash"),
        # --- gate verdict (SPEC 2.6) ---
        "acceptance": {
            "result": acceptance.get("result"),
            "public_gate": _public_gate_verdict(gate_checks),
            "intention_to_route": acceptance.get("intention_to_route"),
            "completed_route": acceptance.get("completed_route"),
        },
        # --- subject isolation posture (authoritative; batch-2) ---
        "isolation": {
            "permission_profile": _tiered_or_none(identity.get("permission_profile")),
            "network_policy": _tiered_or_none(identity.get("network_policy")),
            "cache_state": _tiered_or_none(identity.get("cache_state")),
            "session_state": _tiered_or_none(identity.get("session_state")),
        },
        # --- identity (what served) ---
        "identity": {
            "product": _tiered_or_none(identity.get("product")),
            "provider": _tiered_or_none(identity.get("provider")),
            "model_or_selector": _tiered_or_none(identity.get("model_or_selector")),
            "contamination_tier": identity.get("contamination_tier"),
        },
        # --- telemetry (tiers preserved; unavailable stays null) ---
        "usage": {k: _tiered_or_none(usage.get(k)) for k in _USAGE_KEYS},
        "behavior": {k: _tiered_or_none(behavior.get(k)) for k in _BEHAVIOR_KEYS},
        "economics": {
            "cost_basis": economics.get("cost_basis"),
            "marginal_operating_usd": _tiered_or_none(economics.get("marginal_operating_usd")),
            "fully_allocated_usd": _tiered_or_none(economics.get("fully_allocated_usd")),
            "pricing_snapshot": economics.get("pricing_snapshot"),
        },
        "legs": legs,
    }
    if "frontier_token_share" in summary:
        record["frontier_token_share"] = _tiered_or_none(summary.get("frontier_token_share"))
    return record
