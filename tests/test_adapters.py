"""Pure-function tests for the Product A (claude_code) adapter — no spend.

The adapter's command construction, usage mapping, resolved-version extraction,
and identity assembly are pure given a parsed product-JSON payload, so they are
tested here without ever invoking ``claude -p`` (which would bill a real account).
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.adapters import claude_code as cc  # noqa: E402
from harness.adapters.base import ResolvedModel  # noqa: E402


def _resolved(selector: str = "claude-sonnet-4-6@default", confidence: str = "authoritative"):
    return ResolvedModel(
        product="Product A", product_surface="controlled_api", provider="google_vertex",
        model_or_selector=selector, model_confidence=confidence, model_id=selector,
        region="us-central1", cost_basis="marginal_api_cost",
    )


class ResolvedModelVersion(unittest.TestCase):
    def test_extracts_top_level_model_field(self) -> None:
        self.assertEqual(
            cc.resolved_model_version({"model": "claude-sonnet-4-6-20260130"}),
            "claude-sonnet-4-6-20260130",
        )

    def test_absent_or_blank_model_is_none(self) -> None:
        # None -> caller keeps the requested selector; never invents a version.
        self.assertIsNone(cc.resolved_model_version({}))
        self.assertIsNone(cc.resolved_model_version({"model": ""}))
        self.assertIsNone(cc.resolved_model_version({"model": None}))
        self.assertIsNone(cc.resolved_model_version(None))


class IdentityFloatingAliasMitigation(unittest.TestCase):
    def test_concrete_version_overrides_alias_authoritatively(self) -> None:
        ident = cc._identity(_resolved(), resolved_version="claude-sonnet-4-6-20260130")
        self.assertEqual(ident["model_or_selector"]["value"], "claude-sonnet-4-6-20260130")
        self.assertEqual(ident["model_or_selector"]["confidence"], "authoritative")

    def test_without_resolved_version_keeps_requested_selector(self) -> None:
        ident = cc._identity(_resolved(confidence="proxy_observed"), resolved_version=None)
        self.assertEqual(ident["model_or_selector"]["value"], "claude-sonnet-4-6@default")
        # Tier is the requested selector's declared confidence, not fabricated.
        self.assertEqual(ident["model_or_selector"]["confidence"], "proxy_observed")


class UsageMapping(unittest.TestCase):
    def test_missing_classes_unavailable_never_zero(self) -> None:
        usage = cc.usage_from_claude_json({"usage": {"input_tokens": 10, "output_tokens": 5}})
        self.assertEqual(usage["input_tokens"]["value"], 10)
        self.assertEqual(usage["input_tokens"]["confidence"], "authoritative")
        self.assertEqual(usage["cache_read_tokens"]["confidence"], "unavailable")
        self.assertIsNone(usage["cache_read_tokens"]["value"])


class CommandConstruction(unittest.TestCase):
    def test_cold_uses_session_id_warm_uses_resume(self) -> None:
        cold = cc.build_command("p", "m", session_id="s1", resume=False)
        self.assertIn("--session-id", cold)
        self.assertNotIn("--resume", cold)
        warm = cc.build_command("p", "m", session_id="s1", resume=True)
        self.assertIn("--resume", warm)
        self.assertNotIn("--session-id", warm)


if __name__ == "__main__":
    unittest.main()
