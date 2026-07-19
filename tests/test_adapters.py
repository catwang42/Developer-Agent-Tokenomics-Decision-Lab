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
    def test_modelusage_single_key_is_concrete_version(self) -> None:
        obj = {"modelUsage": {"claude-haiku-4-5@20251001": {"inputTokens": 10}}}
        self.assertEqual(cc.resolved_model_version(obj), "claude-haiku-4-5@20251001")

    def test_floating_alias_pinned_to_matching_family(self) -> None:
        # Requested the floating '@default'; modelUsage meters the concrete version
        # plus an auxiliary haiku. The primary (same base name) pins the alias.
        obj = {"modelUsage": {
            "claude-sonnet-4-6@20260130": {"inputTokens": 5000},
            "claude-haiku-4-5@20251001": {"inputTokens": 20},
        }}
        self.assertEqual(
            cc.resolved_model_version(obj, requested="claude-sonnet-4-6@default"),
            "claude-sonnet-4-6@20260130",
        )

    def test_multiple_keys_without_match_joined(self) -> None:
        obj = {"modelUsage": {"a@1": {}, "b@2": {}}}
        self.assertEqual(cc.resolved_model_version(obj, requested="c@9"), "a@1,b@2")

    def test_falls_back_to_model_field_then_none(self) -> None:
        self.assertEqual(cc.resolved_model_version({"model": "x-1"}), "x-1")
        # None -> caller keeps the requested selector; never invents a version.
        self.assertIsNone(cc.resolved_model_version({}))
        self.assertIsNone(cc.resolved_model_version({"model": ""}))
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

    def test_permission_profile_recorded_authoritatively(self) -> None:
        # Sandbox posture must be on every run at authoritative tier (CP-SPEND cond.)
        ident = cc._identity(_resolved())
        self.assertEqual(ident["permission_profile"]["confidence"], "authoritative")
        self.assertIn("skip-all-tools", ident["permission_profile"]["value"])


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

    def test_auto_approves_tools_so_agent_can_write(self) -> None:
        # Without this flag the headless agent cannot Edit/Write (root cause of the
        # batch-1 0/25 no-write failures).
        self.assertIn("--dangerously-skip-permissions", cc.build_command("p", "m"))


class AgyCommandConstruction(unittest.TestCase):
    def test_model_is_verbatim_selector_and_tools_auto_approved(self) -> None:
        from harness.adapters import agy
        cmd = agy.build_command("do it", "Gemini 3.5 Flash (High)")
        self.assertIn("--dangerously-skip-permissions", cmd)
        # selector passed verbatim via --model (never a backend id), prompt via --print
        i = cmd.index("--model")
        self.assertEqual(cmd[i + 1], "Gemini 3.5 Flash (High)")
        self.assertNotIn("--select", cmd)


if __name__ == "__main__":
    unittest.main()
