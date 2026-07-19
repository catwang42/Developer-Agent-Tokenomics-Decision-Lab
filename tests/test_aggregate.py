"""Tests for the non-comparative aggregation view (offline; seeded run dirs).

Covers: loading result.json, falling back to summary.json, per-cell grouping,
descriptive cost stats over KNOWN costs only, unavailable-cost legs counted (never
zero-imputed), and that the output carries the non-comparative banner.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.aggregate.aggregate import (  # noqa: E402
    NONCOMPARATIVE_BANNER,
    aggregate,
    load_records,
    render_table,
)


def _result(run_id, task, config, result, leg_costs, network="none"):
    legs = []
    for i, c in enumerate(leg_costs):
        mov = ({"value": None, "confidence": "unavailable", "reason": "x"}
               if c is None else {"value": c, "confidence": "derived"})
        legs.append({"leg_id": f"leg{i}", "role": "r", "cost_basis": "marginal_api_cost",
                     "model_or_selector": {"value": "m", "confidence": "authoritative"},
                     "marginal_operating_usd": mov})
    return {
        "result_schema": "result-v1", "run_id": run_id, "task_id": task,
        "configuration_id": config,
        "acceptance": {"result": result, "public_gate": None,
                       "intention_to_route": None, "completed_route": None},
        "isolation": {"network_policy": {"value": network, "confidence": "authoritative"},
                      "permission_profile": {"value": "container-isolated",
                                             "confidence": "authoritative"}},
        "legs": legs,
    }


def _seed(root, rec, *, as_summary=False):
    run_dir = os.path.join(root, rec["run_id"])
    os.makedirs(run_dir, exist_ok=True)
    name = "summary.json" if as_summary else "result.json"
    doc = rec
    if as_summary:
        # Minimal summary shape build_result_record can project from.
        doc = {
            "run_id": rec["run_id"], "task_id": rec["task_id"],
            "configuration_id": rec["configuration_id"],
            "identity": rec["isolation"], "acceptance": rec["acceptance"],
            "usage": {}, "behavior": {}, "economics": {"cost_basis": "marginal_api_cost"},
            "legs": rec["legs"],
        }
        # isolation nested under identity in a real summary; emulate that.
        doc["identity"] = {
            "network_policy": rec["isolation"]["network_policy"],
            "permission_profile": rec["isolation"]["permission_profile"],
        }
    with open(os.path.join(run_dir, name), "w", encoding="utf-8") as fh:
        json.dump(doc, fh)


class Aggregation(unittest.TestCase):
    def test_groups_by_cell_and_counts_acceptance(self) -> None:
        root = tempfile.mkdtemp(prefix="lab-agg-")
        _seed(root, _result("A__P0__r1", "A", "P0", "accepted", [0.10, 0.20]))
        _seed(root, _result("A__P0__r2", "A", "P0", "rejected", [0.30]))
        _seed(root, _result("B__C2__r1", "B", "C2", "error", [0.05]))
        agg = aggregate(load_records(root))
        self.assertEqual(agg["n_records"], 3)
        self.assertEqual(agg["n_cells"], 2)
        cell = next(c for c in agg["cells"] if c["task_id"] == "A")
        self.assertEqual(cell["n_runs"], 2)
        self.assertEqual(cell["acceptance"]["accepted"], 1)
        self.assertEqual(cell["acceptance"]["rejected"], 1)
        # cost median over KNOWN run costs: run1 sums 0.30, run2 0.30 -> median 0.30.
        self.assertAlmostEqual(cell["marginal_operating_usd"]["median"], 0.30)

    def test_unavailable_cost_legs_counted_not_zero_imputed(self) -> None:
        root = tempfile.mkdtemp(prefix="lab-agg-")
        _seed(root, _result("A__C3__r1", "A", "C3", "rejected", [None]))
        _seed(root, _result("A__C3__r2", "A", "C3", "rejected", [0.5, None]))
        cell = aggregate(load_records(root))["cells"][0]
        self.assertEqual(cell["cost_unavailable_legs"], 2)  # both unavailable legs counted
        self.assertEqual(cell["cost_known_runs"], 1)        # only r2 has a known cost
        self.assertAlmostEqual(cell["marginal_operating_usd"]["median"], 0.5)

    def test_falls_back_to_summary_json(self) -> None:
        root = tempfile.mkdtemp(prefix="lab-agg-")
        _seed(root, _result("A__P0__r1", "A", "P0", "accepted", [0.1]), as_summary=True)
        recs = load_records(root)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["task_id"], "A")

    def test_render_carries_noncomparative_banner(self) -> None:
        root = tempfile.mkdtemp(prefix="lab-agg-")
        _seed(root, _result("A__P0__r1", "A", "P0", "accepted", [0.1]))
        table = render_table(aggregate(load_records(root)))
        self.assertIn(NONCOMPARATIVE_BANNER, table)

    def test_empty_dir_is_empty_aggregate(self) -> None:
        agg = aggregate(load_records(tempfile.mkdtemp(prefix="lab-agg-")))
        self.assertEqual(agg["n_records"], 0)
        self.assertEqual(agg["cells"], [])


if __name__ == "__main__":
    unittest.main()
