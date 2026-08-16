"""P3 policy extraction (family B4, governs C5) — SPEC §2.1c.

C5's delegation rules used to live inline in ``harness/configurations/C5.yaml``.
They were extracted verbatim into ``harness/policies/p3-policy-delegation.yaml``
so the rules a run executed are hash-pinned in the manifest instead of unhashed
inline text. These tests hold that extraction to "byte-identical": the resolved
C5 policy must still be exactly the pre-extraction rule list.

No spend: everything here reads files and calls pure resolution helpers.
"""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.runner import run as runner  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
C5_YAML = ROOT / "harness" / "configurations" / "C5.yaml"
P3_YAML = ROOT / "harness" / "policies" / "p3-policy-delegation.yaml"
P3_REL = "harness/policies/p3-policy-delegation.yaml"
REAL_MANIFEST = ROOT / "manifest" / "delivery-manifest.yaml"

# The rules EXACTLY as they stood inline in harness/configurations/C5.yaml before
# the extraction (commit d900358). This literal is the contract: if the extraction
# changed a single character of a rule, this file fails.
PRE_EXTRACTION_RULES = [
    "both legs metered and reported; totals include failed delegations + verification",
    "frontier_token_share computed as diagnostic only",
    "executor-tier variation within pinned C5 = within-workflow executor-tier comparison",
]


def _load(path: pathlib.Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _manifest() -> dict:
    return _load(REAL_MANIFEST)


class ExtractionIsByteIdentical(unittest.TestCase):
    def test_resolved_c5_policy_equals_pre_extraction_rules(self):
        """The whole point: extraction moved the rules, it did not edit them."""
        pol = runner.resolve_config_policy(_load(C5_YAML), "C5", _manifest())
        self.assertIsNotNone(pol)
        self.assertEqual(pol.policy_id, "P3")
        self.assertEqual(pol.rules, PRE_EXTRACTION_RULES)

    def test_c5_no_longer_carries_inline_rules(self):
        """Two copies drift, and only the referenced one is hashed."""
        cfg = _load(C5_YAML)
        self.assertNotIn("rules", cfg)
        self.assertEqual(cfg.get("policy_ref"), "P3")
        self.assertEqual(cfg.get("policy_file"), P3_REL)

    def test_c5_stack_declaration_is_untouched(self):
        """Only the routing rules moved; the configuration still declares the stack."""
        cfg = _load(C5_YAML)
        self.assertEqual(cfg["config_id"], "C5")
        self.assertEqual(cfg["view"], "blackbox_integrated_workflow")
        self.assertEqual(cfg["adapter"], "hybrid_c5")
        self.assertEqual(cfg["cache_protocol"], "cold_default")
        self.assertEqual(cfg["legs"]["conductor"]["model_ref"], "STRONG_MODEL_A")
        self.assertEqual(cfg["legs"]["executor"]["model_ref"], "PRODUCT_B_ECON_TIER")

    def test_inline_rules_alongside_a_reference_are_refused(self):
        cfg = dict(_load(C5_YAML), rules=list(PRE_EXTRACTION_RULES))
        with self.assertRaises(runner.RunnerError) as ctx:
            runner.resolve_config_policy(cfg, "C5", _manifest())
        self.assertIn("inline", str(ctx.exception))


class ManifestPin(unittest.TestCase):
    def test_policy_file_hash_matches_the_manifest_pin(self):
        pin = runner.policy_manifest_pin(_manifest(), "P3")
        self.assertTrue(pin, "manifest routing_policies.P3 is missing")
        _doc, sha = runner.load_policy_file(P3_REL)
        self.assertEqual(str(pin["sha256"]).replace("sha256:", ""), sha)
        self.assertEqual(pin["path"], P3_REL)
        self.assertEqual(pin.get("governs"), ["C5"])

    def test_hash_is_over_raw_bytes_including_comments(self):
        """A comment-only edit must break the pin — the pin is the file, not the data."""
        raw = P3_YAML.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p3.yaml")
            with open(path, "wb") as fh:
                fh.write(raw + b"\n# an added comment\n")
            doc, sha = runner.load_policy_file(path)
            self.assertEqual(doc["rules"], PRE_EXTRACTION_RULES)  # data unchanged
            pinned = str(runner.policy_manifest_pin(_manifest(), "P3")["sha256"])
            self.assertNotEqual(pinned.replace("sha256:", ""), sha)  # pin broken

    def test_drifted_policy_file_is_refused(self):
        manifest = _manifest()
        manifest["routing_policies"]["P3"]["sha256"] = "sha256:" + "0" * 64
        with self.assertRaises(runner.RunnerError) as ctx:
            runner.resolve_config_policy(_load(C5_YAML), "C5", manifest)
        self.assertIn("does not match the manifest pin", str(ctx.exception))

    def test_missing_pin_is_refused_when_a_pin_is_required(self):
        """SPEC 2.1c: no C5 run is citable before P3's hash is in the manifest."""
        manifest = _manifest()
        manifest.pop("routing_policies", None)
        self.assertIsNotNone(  # resolution itself still works (runs are not blocked)
            runner.resolve_config_policy(_load(C5_YAML), "C5", manifest))
        with self.assertRaises(runner.RunnerError) as ctx:
            runner.resolve_config_policy(_load(C5_YAML), "C5", manifest, require_pin=True)
        self.assertIn("routing_policies.P3.sha256", str(ctx.exception))


class PolicyDeclaration(unittest.TestCase):
    def test_p3_declares_the_b4_family_and_its_router(self):
        doc = _load(P3_YAML)
        self.assertEqual(doc["family"], "B4")
        self.assertEqual(doc["governs"], ["C5"])
        # B4's defining property, and the reason it supports no causal claim: the
        # assignment is decided at run time. Pinned-ahead-of-time would be B3 (P2).
        self.assertEqual(doc["delegation_source"], "conductor_runtime_decision")
        self.assertIs(doc["runtime_model_choice_routes_work"], True)

    def test_p3_uses_placeholder_model_labels_only(self):
        """CLAUDE.md rule 7: concrete models/prices live in the manifest, not here."""
        text = P3_YAML.read_text(encoding="utf-8")
        for banned in ("claude-", "gemini", "sonnet", "haiku", "$", "USD"):
            self.assertNotIn(banned, text.lower().replace("claude.md", ""))

    def test_p3_claims_register_forbids_the_causal_reading(self):
        doc = _load(P3_YAML)
        forbidden = " ".join(doc["claims"]["does_not_support"]).lower()
        self.assertIn("causal", forbidden)
        self.assertIn("superiority", forbidden)
        self.assertIn("diagnostic", forbidden)  # frontier_token_share

    def test_live_delegation_is_recorded_unverified(self):
        """No spend has happened; the policy must not imply otherwise."""
        doc = _load(P3_YAML)
        self.assertEqual(doc["mechanism"]["verification"]["live_delegation"], "unverified")


class GovernanceGuards(unittest.TestCase):
    def test_a_policy_that_does_not_govern_the_config_is_refused(self):
        with self.assertRaises(runner.RunnerError) as ctx:
            runner.resolve_config_policy(_load(C5_YAML), "C4", _manifest())
        self.assertIn("governs", str(ctx.exception))

    def test_policy_ref_must_agree_with_the_files_policy_id(self):
        cfg = dict(_load(C5_YAML), policy_ref="P2")
        with self.assertRaises(runner.RunnerError) as ctx:
            runner.resolve_config_policy(cfg, "C5", _manifest())
        self.assertIn("policy_id", str(ctx.exception))

    def test_unreadable_reference_is_refused(self):
        cfg = dict(_load(C5_YAML), policy_file="harness/policies/does-not-exist.yaml")
        with self.assertRaises(runner.RunnerError):
            runner.resolve_config_policy(cfg, "C5", _manifest())

    def test_static_configurations_resolve_to_no_policy(self):
        for config_id in ("C1", "C2", "C3", "C4"):
            with self.subTest(config_id=config_id):
                cfg = _load(ROOT / "harness" / "configurations" / f"{config_id}.yaml")
                self.assertIsNone(runner.resolve_config_policy(cfg, config_id, _manifest()))


class RunnerIntegration(unittest.TestCase):
    def test_build_plan_for_c5_is_unchanged_and_hash_checks_the_policy(self):
        manifest = _load(ROOT / "tests" / "fixtures" / "manifest-SYNTHETIC.yaml")
        manifest["routing_policies"] = _manifest()["routing_policies"]
        plan = runner.build_plan("C5", manifest)
        self.assertEqual(plan.adapter_name, "hybrid_c5")
        self.assertEqual(plan.policy, "workflow")
        self.assertEqual([leg.leg_id for leg in plan.legs], ["conductor", "executor"])

    def test_build_plan_refuses_a_drifted_policy(self):
        manifest = _load(ROOT / "tests" / "fixtures" / "manifest-SYNTHETIC.yaml")
        manifest["routing_policies"] = {"P3": {"sha256": "sha256:" + "1" * 64}}
        with self.assertRaises(runner.RunnerError):
            runner.build_plan("C5", manifest)


if __name__ == "__main__":
    unittest.main()
