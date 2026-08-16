"""Agreement tests between the delivery manifest, the pinned pricing snapshot and
the adapters' pinned run conditions.

These are REAL-artifact tests (no fixtures): they read manifest/delivery-manifest.yaml
and whatever pricing snapshot it pins. Their job is to make a screening-window re-pin
self-checking, because every failure mode here surfaces at the worst possible moment
otherwise — costing.py raises a bare KeyError mid-batch when a selector has no rate
row, and a version/effort pin that nothing enforces is just a comment.
"""

import os
import sys
import unittest

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.adapters import agy  # noqa: E402
from harness.telemetry.costing import load_prices, required_rate_keys  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MANIFEST = os.path.join(ROOT, "manifest", "delivery-manifest.yaml")

# Read from costing.py rather than restated here: a renamed or added rate key must
# fail as a missing row in the PINNED snapshot, not silently stop being checked.
# Currently ("input", "cache_write_1h", "cache_read", "output") — the cache-write
# key is TTL-specific since the 2026-08-16 split.
BILLED_CLASSES = required_rate_keys()
OUT_OF_SCOPE = "out_of_scope_this_window"


def _manifest():
    with open(MANIFEST, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _prices(manifest):
    return load_prices(os.path.join(ROOT, manifest["pricing_snapshot"]))


def _price_key(entry):
    """The key costing.py will look this entry up by (model id or verbatim label)."""
    return entry.get("model_id") or entry.get("selector_label")


class PricingCoverageTests(unittest.TestCase):
    """Every model_ref a run can resolve must have a rate row — or say why not."""

    def setUp(self):
        self.manifest = _manifest()
        self.prices = _prices(self.manifest)
        self.configs = self.manifest["configurations"]

    def test_every_in_scope_configuration_has_a_priced_row(self):
        providers = self.prices["providers"]
        for ref, entry in self.configs.items():
            if entry.get("screening_scope") == OUT_OF_SCOPE:
                continue
            with self.subTest(model_ref=ref):
                provider = entry["provider"]
                self.assertIn(provider, providers,
                              f"{ref}: provider {provider!r} absent from the snapshot")
                key = _price_key(entry)
                self.assertIn(key, providers[provider],
                              f"{ref}: {key!r} has no rate row — a live run would "
                              f"KeyError inside costing.py")

    def test_every_priced_row_carries_all_four_billed_classes(self):
        providers = self.prices["providers"]
        for ref, entry in self.configs.items():
            if entry.get("screening_scope") == OUT_OF_SCOPE:
                continue
            row = providers[entry["provider"]][_price_key(entry)]
            for cls in BILLED_CLASSES:
                with self.subTest(model_ref=ref, klass=cls):
                    self.assertIsInstance(row.get(cls), (int, float),
                                          f"{ref}.{cls} is not a number: {row.get(cls)!r}")

    def test_an_unpriced_entry_must_declare_itself_out_of_scope(self):
        """The escape hatch is allowed but must be EXPLICIT, never silence.

        PRODUCT_B_STRONG_TIER is unpriced this window on purpose; the point of this
        test is that dropping a row from the snapshot without saying so fails here.
        """
        providers = self.prices["providers"]
        for ref, entry in self.configs.items():
            key = _price_key(entry)
            priced = key in providers.get(entry["provider"], {})
            if not priced:
                with self.subTest(model_ref=ref):
                    self.assertEqual(
                        entry.get("screening_scope"), OUT_OF_SCOPE,
                        f"{ref} has no rate row and no screening_scope declaration")


class ProductBConditionTests(unittest.TestCase):
    """Pinned Product-B run conditions must be consistent and enforceable."""

    def setUp(self):
        self.manifest = _manifest()
        self.configs = self.manifest["configurations"]
        self.pinned = {ref: entry for ref, entry in self.configs.items()
                       if entry.get("conditions")}

    def test_product_b_selectors_carry_condition_pins(self):
        expected = {"PRODUCT_B_ECON_TIER", "PRODUCT_B_ECON_TIER_MED",
                    "PRODUCT_B_ECON_TIER_PREV"}
        self.assertLessEqual(expected, set(self.pinned))

    def test_one_agy_version_across_every_pin_including_the_image(self):
        """A per-selector pin that disagrees with the image pin enforces two
        different products depending on isolation mode."""
        versions = {ref: str(e["conditions"]["agy_version"])
                    for ref, e in self.pinned.items()
                    if "agy_version" in e["conditions"]}
        self.assertTrue(versions)
        image = str(self.manifest["subject_isolation"]["agent_leg"]["agy_version"])
        self.assertEqual(set(versions.values()), {image}, f"pins disagree: {versions} vs {image}")

    def test_print_timeout_is_raised_above_the_product_default(self):
        for ref, entry in self.pinned.items():
            value = entry["conditions"].get("print_timeout")
            with self.subTest(model_ref=ref):
                self.assertIsNotNone(value, f"{ref} pins no print_timeout")
                seconds = agy.print_timeout_seconds(str(value))
                self.assertGreater(seconds, 300, "not raised above agy's 5m0s default")
                self.assertLess(seconds, agy.DEFAULT_TIMEOUT_S,
                                "must stay below our own subprocess kill so the "
                                "product's timeout fires first")

    def test_pinned_effort_matches_the_selector_suffix(self):
        """Effort travels in the selector label; a pin that disagrees with the label
        would make the recorded condition a fiction."""
        for ref, entry in self.pinned.items():
            effort = entry["conditions"].get("effort")
            with self.subTest(model_ref=ref):
                self.assertIsNotNone(effort, f"{ref} pins no effort")
                self.assertTrue(
                    entry["selector_label"].endswith(f"({effort})"),
                    f"{ref}: effort {effort!r} not the suffix of "
                    f"{entry['selector_label']!r}")

    def test_every_gemini_arm_declares_the_cache_blind_qualifier(self):
        """Human decision 2026-08-16: Product-B costing this window is cache-blind.

        The qualifier is the only thing that stops a Gemini figure being read as an
        exact cost, so an arm that silently omits it publishes an unqualified number.
        Applies to the C5 executor too — it resolves through PRODUCT_B_ECON_TIER.
        """
        for ref in ("PRODUCT_B_ECON_TIER", "PRODUCT_B_ECON_TIER_MED",
                    "PRODUCT_B_ECON_TIER_PREV"):
            with self.subTest(model_ref=ref):
                self.assertEqual(self.configs[ref].get("cost_basis_qualifier"),
                                 "cache_blind_upper_bound")

    def test_no_product_a_entry_is_cache_blind(self):
        """Product A's cache classes ARE metered; qualifying them would be false."""
        for ref in ("STRONG_MODEL_A", "ECONOMICAL_MODEL_A"):
            with self.subTest(model_ref=ref):
                self.assertIsNone(self.configs[ref].get("cost_basis_qualifier"))

    def test_auto_update_is_a_pinned_condition_on_every_selector(self):
        """agy self-updates, so "which product did we measure" is only answerable if
        the updater state is a recorded condition rather than whatever the host did."""
        expected = agy.AUTO_UPDATE_CONDITION
        image = self.manifest["subject_isolation"]["agent_leg"]["agy_auto_update"]
        self.assertEqual(image, expected)
        for ref in ("PRODUCT_B_ECON_TIER", "PRODUCT_B_ECON_TIER_MED",
                    "PRODUCT_B_ECON_TIER_PREV"):
            with self.subTest(model_ref=ref):
                self.assertEqual(self.configs[ref]["conditions"].get("auto_update"),
                                 expected)

    def test_the_version_drift_is_resolved_not_still_open(self):
        """Left at pending_human, a CP-SPEND batch could start against an unsettled
        pin — the whole point of the pin being a condition."""
        drift = self.manifest["subject_isolation"]["agent_leg"]["agy_version_drift"]
        self.assertNotEqual(drift["resolution"], "pending_human")
        self.assertEqual(str(drift["host_today"]),
                         str(self.manifest["subject_isolation"]["agent_leg"]["agy_version"]))

    def test_the_recheck_covers_exactly_the_pinned_selector_labels(self):
        """A version pin only means something if the labels it resolves are the ones
        the manifest names; a recheck of some other set proves nothing."""
        recheck = self.manifest["subject_isolation"]["agent_leg"]["agy_models_recheck"]
        self.assertTrue(recheck["labels_unchanged"])
        self.assertEqual(str(recheck["under_version"]),
                         str(self.manifest["subject_isolation"]["agent_leg"]["agy_version"]))
        pinned_labels = {self.configs[r]["selector_label"] for r in
                         ("PRODUCT_B_ECON_TIER", "PRODUCT_B_ECON_TIER_MED",
                          "PRODUCT_B_ECON_TIER_PREV")}
        self.assertEqual(set(recheck["labels_verified"]), pinned_labels)

    def test_the_three_screening_selectors_are_distinct(self):
        labels = [self.configs[r]["selector_label"] for r in
                  ("PRODUCT_B_ECON_TIER", "PRODUCT_B_ECON_TIER_MED",
                   "PRODUCT_B_ECON_TIER_PREV")]
        self.assertEqual(len(set(labels)), 3, f"arms collapse onto each other: {labels}")


class EffortRuleTests(unittest.TestCase):
    """SPEC-side rule pinned in the manifest: C5 never mixes effort with routing."""

    def setUp(self):
        self.manifest = _manifest()
        self.configs = self.manifest["configurations"]

    def test_c5_executor_is_pinned_to_high_effort(self):
        with open(os.path.join(ROOT, "harness", "configurations", "C5.yaml"),
                  encoding="utf-8") as fh:
            c5 = yaml.safe_load(fh)
        ref = c5["legs"]["executor"]["model_ref"]
        label = self.configs[ref]["selector_label"]
        self.assertTrue(label.endswith("(High)"),
                        f"C5 executor {ref} -> {label!r}; a non-High executor would "
                        f"confound routing with effort level")

    def test_effort_level_does_not_change_the_rate_card(self):
        """C3 vs C3-med must be a CONSUMPTION comparison. Identical rates are what
        makes any observed cost delta attributable to tokens, not price."""
        prices = _prices(self.manifest)["providers"]
        high = prices[self.configs["PRODUCT_B_ECON_TIER"]["provider"]][
            self.configs["PRODUCT_B_ECON_TIER"]["selector_label"]]
        med = prices[self.configs["PRODUCT_B_ECON_TIER_MED"]["provider"]][
            self.configs["PRODUCT_B_ECON_TIER_MED"]["selector_label"]]
        for cls in BILLED_CLASSES:
            self.assertEqual(high[cls], med[cls], f"{cls} differs between effort arms")


class AgyCommandTests(unittest.TestCase):
    """The pinned conditions must actually reach the product's argv."""

    LABEL = "Gemini 3.7 Flash (High)"

    def test_print_timeout_is_passed_when_pinned(self):
        cmd = agy.build_command("do the thing", self.LABEL, "15m0s")
        self.assertIn("--print-timeout", cmd)
        self.assertEqual(cmd[cmd.index("--print-timeout") + 1], "15m0s")
        # --print must stay immediately before the prompt (value-vs-boolean is
        # unresolved from --help; this ordering is correct under either reading).
        self.assertEqual(cmd[-2:], ["--print", "do the thing"])

    def test_no_flag_is_invented_when_unpinned(self):
        self.assertNotIn("--print-timeout", agy.build_command("p", self.LABEL))

    def test_effort_flag_is_never_passed(self):
        """Effort has exactly one mechanism: the selector suffix."""
        self.assertNotIn("--effort", agy.build_command("p", self.LABEL, "15m0s"))

    def test_a_timeout_at_or_above_our_kill_is_refused(self):
        with self.assertRaises(ValueError):
            agy.build_command("p", self.LABEL, "30m0s")

    def test_go_duration_parsing(self):
        self.assertEqual(agy.print_timeout_seconds("5m0s"), 300)
        self.assertEqual(agy.print_timeout_seconds("15m0s"), 900)
        self.assertEqual(agy.print_timeout_seconds("1h30m0s"), 5400)
        for bad in ("15", "", "15 minutes", "m15s"):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                agy.print_timeout_seconds(bad)


if __name__ == "__main__":
    unittest.main()
