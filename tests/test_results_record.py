"""Tests for the compact per-run result record (pure projection of a summary).

Asserts the record faithfully copies fields, preserves tiers, and never zero-fills
an unavailable field (CLAUDE.md rules 1 & 3).
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.results.record import RESULT_SCHEMA_VERSION, build_result_record  # noqa: E402


def _summary(**over):
    base = {
        "run_id": "T__P0__rep1__20260719T000000",
        "task_id": "T",
        "task_suite_version": "v1",
        "configuration_id": "P0",
        "manifest_ref": "manifest/delivery-manifest.yaml",
        "hidden_test_hash": "sha256:abc",
        "identity": {
            "product": {"value": "Product A", "confidence": "authoritative"},
            "provider": {"value": "google_vertex", "confidence": "authoritative"},
            "model_or_selector": {"value": "m@1", "confidence": "authoritative"},
            "permission_profile": {"value": "container-isolated", "confidence": "authoritative"},
            "network_policy": {"value": "none", "confidence": "authoritative"},
            "cache_state": {"value": "cold", "confidence": "authoritative"},
            "session_state": {"value": "fresh", "confidence": "authoritative"},
            "contamination_tier": "famous",
        },
        "acceptance": {
            "result": "accepted",
            "intention_to_route": "economical",
            "completed_route": "strong",
            "gate_checks": {"public": {"checks": [
                {"id": "T1", "status": "pass"}, {"id": "T2", "status": "pass"}]}},
        },
        "usage": {
            "input_tokens": {"value": 100, "confidence": "authoritative"},
            "output_tokens": {"value": 20, "confidence": "authoritative"},
            "reasoning_tokens": {"value": None, "confidence": "unavailable",
                                 "reason": "not exposed"},
            "cache_creation_tokens": {"value": 0, "confidence": "authoritative"},
            "cache_read_tokens": {"value": 0, "confidence": "authoritative"},
        },
        "behavior": {
            "turns": {"value": 5, "confidence": "derived"},
            "retries": {"value": 1, "confidence": "derived"},
            "escalations": {"value": 1, "confidence": "derived"},
            "subagent_calls": {"value": 0, "confidence": "derived"},
            "verifier_calls": {"value": 0, "confidence": "derived"},
        },
        "economics": {
            "cost_basis": "marginal_api_cost",
            "marginal_operating_usd": {"value": 0.42, "confidence": "derived"},
            "fully_allocated_usd": {"value": 0.42, "confidence": "derived"},
            "pricing_snapshot": "prices-2026-07-19.json",
        },
        "legs": [
            {"leg_id": "economical_attempt", "role": "economical",
             "cost_basis": "marginal_api_cost",
             "model_or_selector": {"value": "e@1", "confidence": "authoritative"},
             "marginal_operating_usd": {"value": 0.10, "confidence": "derived"}},
            {"leg_id": "strong_attempt", "role": "strong",
             "cost_basis": "marginal_api_cost",
             "model_or_selector": {"value": "s@1", "confidence": "authoritative"},
             "marginal_operating_usd": {"value": 0.32, "confidence": "derived"}},
        ],
    }
    base.update(over)
    return base


class ResultRecord(unittest.TestCase):
    def test_projects_core_fields(self) -> None:
        r = build_result_record(_summary())
        self.assertEqual(r["result_schema"], RESULT_SCHEMA_VERSION)
        self.assertEqual(r["task_id"], "T")
        self.assertEqual(r["configuration_id"], "P0")
        self.assertEqual(r["acceptance"]["result"], "accepted")
        self.assertEqual(r["acceptance"]["public_gate"], "pass")
        self.assertEqual(r["acceptance"]["completed_route"], "strong")
        self.assertEqual(r["hidden_test_hash"], "sha256:abc")

    def test_isolation_posture_preserved(self) -> None:
        r = build_result_record(_summary())
        self.assertEqual(r["isolation"]["permission_profile"]["value"], "container-isolated")
        self.assertEqual(r["isolation"]["network_policy"]["value"], "none")
        self.assertEqual(r["isolation"]["network_policy"]["confidence"], "authoritative")

    def test_unavailable_stays_null_with_reason(self) -> None:
        r = build_result_record(_summary())
        rt = r["usage"]["reasoning_tokens"]
        self.assertIsNone(rt["value"])
        self.assertEqual(rt["confidence"], "unavailable")
        self.assertEqual(rt["reason"], "not exposed")

    def test_legs_and_economics_copied(self) -> None:
        r = build_result_record(_summary())
        self.assertEqual([leg["leg_id"] for leg in r["legs"]],
                         ["economical_attempt", "strong_attempt"])
        self.assertEqual(r["economics"]["cost_basis"], "marginal_api_cost")
        self.assertEqual(r["economics"]["marginal_operating_usd"]["value"], 0.42)

    def test_public_gate_fail_when_any_check_fails(self) -> None:
        s = _summary()
        s["acceptance"]["gate_checks"]["public"]["checks"][1]["status"] = "fail"
        r = build_result_record(s)
        self.assertEqual(r["acceptance"]["public_gate"], "fail")

    def test_missing_public_gate_is_none(self) -> None:
        s = _summary()
        s["acceptance"]["gate_checks"] = {}
        self.assertIsNone(build_result_record(s)["acceptance"]["public_gate"])


if __name__ == "__main__":
    unittest.main()
