"""The offline re-cost must price a cache-blind leg without inventing anything.

Every fixture here is SYNTHETIC and lives only in a temp directory.
"""

import json
import os
import shutil
import tempfile
import unittest

from harness.analysis import recost as R
from harness.telemetry.costing import token_cost_usd

SYNTHETIC_PRICES = {
    "SYNTHETIC": "SYNTHETIC test fixture — not a real rate card",
    "providers": {
        "google": {
            "SYNTHETIC Flash": {"input": 1.0, "cache_write_1h": 1.0,
                                "cache_read": 0.1, "output": 10.0,
                                "unit": "usd_per_mtok"},
        },
        "google_vertex": {
            "synthetic-strong@default": {"input": 5.0, "cache_write_1h": 10.0,
                                         "cache_read": 0.5, "output": 25.0,
                                         "unit": "usd_per_mtok"},
        },
    },
}


def _slot(value, confidence="derived"):
    return {"value": value, "confidence": confidence}


def _missing(reason="SYNTHETIC: no event reported this token class"):
    return {"value": None, "confidence": "unavailable", "reason": reason}


def _gemini_leg(leg_id="main", inp=1_000_000, out=100_000, qualifier=R.CACHE_BLIND):
    return {
        "leg_id": leg_id, "role": "solver", "cost_basis": "marginal_api_cost",
        "cost_basis_qualifier": qualifier,
        "provider": _slot("google", "authoritative"),
        "model_or_selector": _slot("SYNTHETIC Flash", "proxy_observed"),
        "usage": {"input_tokens": _slot(inp), "output_tokens": _slot(out),
                  "cache_creation_tokens": _missing(), "cache_read_tokens": _missing()},
    }


def _claude_leg(leg_id="conductor", usage=None):
    return {
        "leg_id": leg_id, "role": "conductor", "cost_basis": "marginal_api_cost",
        "provider": _slot("google_vertex", "authoritative"),
        "model_or_selector": _slot("synthetic-strong@default", "authoritative"),
        "usage": usage if usage is not None else {
            "input_tokens": _missing(), "output_tokens": _missing(),
            "cache_creation_tokens": _missing(), "cache_read_tokens": _missing()},
    }


class CacheBlindPricingIsOptInAndLabelled(unittest.TestCase):
    def test_without_the_flag_a_cache_blind_leg_stays_unavailable(self):
        # The default must not change: a missing class is a missing measurement.
        field = token_cost_usd(_gemini_leg()["usage"], "google", "SYNTHETIC Flash",
                               SYNTHETIC_PRICES)
        self.assertEqual("unavailable", field["confidence"])
        self.assertIn("cache_creation_tokens", field["reason"])

    def test_with_the_flag_the_figure_is_input_plus_output_and_says_it_is_a_bound(self):
        field = token_cost_usd(_gemini_leg()["usage"], "google", "SYNTHETIC Flash",
                               SYNTHETIC_PRICES, cache_blind=True)
        self.assertAlmostEqual(1.0 + 1.0, field["value"])  # 1M @ $1 + 100k @ $10
        self.assertEqual("upper", field["bound"])
        self.assertEqual(R.CACHE_BLIND, field["qualifier"])
        self.assertEqual(["cache_creation_tokens", "cache_read_tokens"],
                         field["cache_classes_excluded"])

    def test_the_flag_does_not_excuse_a_missing_output_count(self):
        # Only the cache classes are structurally absent. An unavailable OUTPUT is
        # still an unavailable measurement, and a cost derived without it would be
        # a partial sum wearing a total's name.
        leg = _gemini_leg()
        leg["usage"]["output_tokens"] = _missing()
        field = token_cost_usd(leg["usage"], "google", "SYNTHETIC Flash",
                               SYNTHETIC_PRICES, cache_blind=True)
        self.assertEqual("unavailable", field["confidence"])
        self.assertIn("output_tokens", field["reason"])


class TheRecostPassPricesOnlyWhatItMay(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="SYNTHETIC-recost-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.pricing = os.path.join(self.root, "pricing")
        os.makedirs(self.pricing)
        with open(os.path.join(self.pricing, "prices-SYNTHETIC.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(SYNTHETIC_PRICES, fh)

    def _run(self, run_id, legs, snapshot="prices-SYNTHETIC.json"):
        run_dir = os.path.join(self.root, "results", "SYNTHETIC-dataset", run_id)
        os.makedirs(run_dir)
        economics = {"cost_basis": "marginal_api_cost",
                     "marginal_operating_usd": _missing("SYNTHETIC")}
        if snapshot:
            economics["pricing_snapshot"] = snapshot
        with open(os.path.join(run_dir, "summary.json"), "w", encoding="utf-8") as fh:
            json.dump({"SYNTHETIC": "SYNTHETIC test fixture — not a measurement",
                       "run_id": run_id, "task_id": "SYNTHETIC-task",
                       "configuration_id": "C3", "legs": legs,
                       "economics": economics}, fh)
        return run_dir

    def test_a_solo_gemini_run_is_priced_at_the_upper_bound(self):
        run_dir = self._run("solo", [_gemini_leg()])
        record = R.recost_run(run_dir, self.pricing)
        self.assertEqual("priced", record["status"])
        self.assertAlmostEqual(2.0, record["marginal_operating_usd"]["value"])
        self.assertEqual("upper", record["marginal_operating_usd"]["bound"])
        self.assertEqual("derived", record["marginal_operating_usd"]["confidence"])

    def test_a_dual_billed_run_missing_its_conductor_reports_no_run_total(self):
        # The executor figure is real and kept; presenting it AS the run's cost
        # would understate a two-leg bill by a whole leg.
        run_dir = self._run("dual", [_claude_leg(), _gemini_leg("executor")])
        record = R.recost_run(run_dir, self.pricing)
        self.assertEqual("partial", record["status"])
        self.assertIsNone(record["marginal_operating_usd"]["value"])
        by_leg = {leg["leg_id"]: leg for leg in record["legs"]}
        self.assertAlmostEqual(2.0, by_leg["executor"]["marginal_operating_usd"]["value"])
        self.assertIsNone(by_leg["conductor"]["marginal_operating_usd"]["value"])

    def test_a_dual_billed_run_with_both_legs_metered_sums_them(self):
        conductor = _claude_leg(usage={
            "input_tokens": _slot(1_000_000, "authoritative"),
            "output_tokens": _slot(100_000, "authoritative"),
            "cache_creation_tokens": _slot(0, "authoritative"),
            "cache_read_tokens": _slot(0, "authoritative")})
        run_dir = self._run("both", [conductor, _gemini_leg("executor")])
        record = R.recost_run(run_dir, self.pricing)
        self.assertEqual("priced", record["status"])
        # conductor 1M@$5 + 100k@$25 = 7.50; executor 2.00
        self.assertAlmostEqual(9.5, record["marginal_operating_usd"]["value"])

    def test_a_product_a_only_run_is_skipped_not_repriced(self):
        # Re-deriving a figure the runner already owns would silently swap its
        # provenance for this module's.
        run_dir = self._run("claude-only", [_claude_leg()])
        self.assertEqual("skipped", R.recost_run(run_dir, self.pricing)["status"])

    def test_a_run_naming_no_pricing_snapshot_is_refused(self):
        run_dir = self._run("nosnapshot", [_gemini_leg()], snapshot=None)
        record = R.recost_run(run_dir, self.pricing)
        self.assertEqual("refused", record["status"])
        self.assertIn("pricing_snapshot", record["reason"])

    def test_a_snapshot_that_is_not_on_disk_is_refused_not_substituted(self):
        # Pricing 2026-08 traffic against whatever snapshot happens to be newest
        # would report a cost that was never billable.
        run_dir = self._run("gone", [_gemini_leg()], snapshot="prices-MISSING.json")
        record = R.recost_run(run_dir, self.pricing)
        self.assertEqual("refused", record["status"])
        self.assertIn("prices-MISSING.json", record["reason"])

    def test_a_leg_the_runner_already_priced_is_left_alone(self):
        # Re-deriving over the runner's own figure would swap its provenance for
        # this module's without anything on disk saying so.
        leg = _gemini_leg()
        leg["marginal_operating_usd"] = _slot(0.42)
        run_dir = self._run("already", [leg])
        self.assertEqual("skipped", R.recost_run(run_dir, self.pricing)["status"])

    def test_an_unrecognised_qualifier_is_not_treated_as_cache_blind(self):
        run_dir = self._run("odd", [_gemini_leg(qualifier="SYNTHETIC-unreviewed")])
        self.assertEqual("skipped", R.recost_run(run_dir, self.pricing)["status"])

    def test_a_selector_with_no_rate_row_is_refused(self):
        leg = _gemini_leg()
        leg["model_or_selector"] = _slot("SYNTHETIC Unpriced Model", "proxy_observed")
        run_dir = self._run("norate", [leg])
        record = R.recost_run(run_dir, self.pricing)
        self.assertEqual("refused", record["status"])
        self.assertIn("no pricing", record["reason"])

    def test_a_skipped_run_gets_no_sidecar_and_a_refusal_does(self):
        priced = self._run("solo", [_gemini_leg()])
        skipped = self._run("claude-only", [_claude_leg()])
        records = R.scan(os.path.join(self.root, "results"), ["SYNTHETIC-dataset"],
                         self.pricing)
        self.assertEqual(1, R.write_sidecars(records))  # the priced run only
        self.assertTrue(os.path.isfile(os.path.join(priced, R.RECOST_FILE)))
        self.assertFalse(os.path.isfile(os.path.join(skipped, R.RECOST_FILE)))


if __name__ == "__main__":
    unittest.main()
