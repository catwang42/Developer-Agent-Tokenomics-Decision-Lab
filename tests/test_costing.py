"""Unit tests for harness/telemetry/costing.py.

All prices and usage are SYNTHETIC (tests/fixtures/prices-SYNTHETIC.json). The
numbers are chosen so the expected USD are exact and hand-checkable.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.telemetry import costing  # noqa: E402
from harness.telemetry.costing import (  # noqa: E402
    compute_cost_views,
    cost_for_legs,
    load_prices,
    token_cost_usd,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return json.load(fh)


class TokenCostTests(unittest.TestCase):
    def setUp(self):
        self.prices = load_prices(os.path.join(FIXTURES, "prices-SYNTHETIC.json"))

    def test_single_leg_cost(self):
        # STRONG_MODEL_A: input 10, cache_write 12.5, cache_read 1, output 50 (usd/Mtok)
        # 1500*10 + 200*12.5 + 5000*1 + 400*50  (all /1e6) = 0.0425
        usage = _load("summary-valid-SYNTHETIC.json")["usage"]
        cost = token_cost_usd(usage, "provider_a", "STRONG_MODEL_A", self.prices)
        self.assertEqual(cost["confidence"], "derived")
        self.assertAlmostEqual(cost["value"], 0.0425, places=10)
        self.assertIn("components", cost)

    def test_unavailable_class_makes_cost_unavailable(self):
        # Drop output_tokens -> cannot derive cost -> unavailable, NOT partial/zero.
        usage = dict(_load("summary-valid-SYNTHETIC.json")["usage"])
        usage["output_tokens"] = {"value": None, "confidence": "unavailable"}
        cost = token_cost_usd(usage, "provider_a", "STRONG_MODEL_A", self.prices)
        self.assertEqual(cost["confidence"], "unavailable")
        self.assertIsNone(cost["value"])
        self.assertIn("output_tokens", cost["reason"])

    def test_unknown_model_raises(self):
        with self.assertRaises(KeyError):
            token_cost_usd({}, "provider_a", "NO_SUCH_MODEL", self.prices)


class DualBillTests(unittest.TestCase):
    def setUp(self):
        self.prices = load_prices(os.path.join(FIXTURES, "prices-SYNTHETIC.json"))
        self.legs = _load("summary-dualbill-SYNTHETIC.json")["legs"]

    def test_dualbill_aggregates_both_legs(self):
        result = cost_for_legs(self.legs, self.prices)
        # conductor 0.02325 + executor 0.013125 = 0.036375
        self.assertAlmostEqual(result["marginal_operating_usd"]["value"], 0.036375, places=10)
        self.assertAlmostEqual(result["fully_allocated_usd"]["value"], 0.036375, places=10)
        self.assertEqual(len(result["legs"]), 2)
        by_leg = {leg["leg_id"]: leg for leg in result["legs"]}
        self.assertAlmostEqual(by_leg["conductor"]["marginal_operating_usd"]["value"], 0.02325, places=10)
        self.assertAlmostEqual(by_leg["executor"]["marginal_operating_usd"]["value"], 0.013125, places=10)

    def test_unavailable_leg_keeps_total_unavailable(self):
        # Executor loses output_tokens -> its cost unavailable -> total unavailable,
        # never the conductor-only figure zero-filled for the missing leg.
        legs = json.loads(json.dumps(self.legs))  # deep copy
        legs[1]["usage"]["output_tokens"] = {"value": None, "confidence": "unavailable"}
        result = cost_for_legs(legs, self.prices)
        self.assertEqual(result["marginal_operating_usd"]["confidence"], "unavailable")
        self.assertIsNone(result["marginal_operating_usd"]["value"])


class CostBasisViewTests(unittest.TestCase):
    def setUp(self):
        self.prices = load_prices(os.path.join(FIXTURES, "prices-SYNTHETIC.json"))
        self.usage = _load("summary-valid-SYNTHETIC.json")["usage"]

    def test_marginal_api_cost_view(self):
        views = compute_cost_views(
            self.usage, "provider_a", "STRONG_MODEL_A", self.prices,
            "marginal_api_cost", machine_cost_usd=0.01,
        )
        self.assertAlmostEqual(views["marginal_operating_usd"]["value"], 0.0425, places=10)
        # fully allocated adds machine cost
        self.assertAlmostEqual(views["fully_allocated_usd"]["value"], 0.0525, places=10)

    def test_subscription_view(self):
        views = compute_cost_views(
            self.usage, "provider_a", "STRONG_MODEL_A", self.prices,
            "allocated_subscription_cost", seat_allocation_usd=1.75,
        )
        # No observable marginal cost under a seat basis.
        self.assertEqual(views["marginal_operating_usd"]["confidence"], "unavailable")
        self.assertIsNone(views["marginal_operating_usd"]["value"])
        # Fully allocated uses the declared seat allocation.
        self.assertAlmostEqual(views["fully_allocated_usd"]["value"], 1.75, places=10)

    def test_subscription_view_without_allocation_is_unavailable(self):
        views = compute_cost_views(
            self.usage, "provider_a", "STRONG_MODEL_A", self.prices,
            "allocated_subscription_cost",
        )
        self.assertEqual(views["fully_allocated_usd"]["confidence"], "unavailable")
        self.assertIsNone(views["fully_allocated_usd"]["value"])

    def test_provider_reported_view(self):
        views = compute_cost_views(
            self.usage, "provider_b", "ECON_MODEL_B", self.prices,
            "provider_reported_cost", provider_reported_usd=0.02,
        )
        self.assertEqual(views["marginal_operating_usd"]["confidence"], "proxy_observed")
        self.assertAlmostEqual(views["marginal_operating_usd"]["value"], 0.02, places=10)

    def test_cost_unavailable_view(self):
        views = compute_cost_views(
            self.usage, "provider_a", "STRONG_MODEL_A", self.prices, "cost_unavailable",
        )
        self.assertEqual(views["marginal_operating_usd"]["confidence"], "unavailable")
        self.assertEqual(views["fully_allocated_usd"]["confidence"], "unavailable")

    def test_invalid_basis_raises(self):
        with self.assertRaises(ValueError):
            compute_cost_views(self.usage, "provider_a", "STRONG_MODEL_A", self.prices, "bogus")


if __name__ == "__main__":
    unittest.main()
