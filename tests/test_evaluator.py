"""Tests for the feasibility metric evaluator — SYNTHETIC data, no spend.

Proves the metrics compute end-to-end (feasibility criterion 5) and, critically,
that they never fabricate: ECST is ``undefined`` with zero accepted tasks and
``derived_floor``/``unavailable`` when any attempt cost is unavailable — never
zero-filled (CLAUDE.md rule 3).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.evaluator import metrics  # noqa: E402


def _summary(task, config, result, leg_costs, output_tokens=100):
    """Minimal SYNTHETIC summary. leg_costs: list of float|None (None=unavailable)."""
    legs = []
    for i, c in enumerate(leg_costs):
        mov = ({"value": c, "confidence": "derived"} if c is not None
               else {"value": None, "confidence": "unavailable", "reason": "SYNTHETIC"})
        legs.append({"leg_id": f"leg{i}", "marginal_operating_usd": mov,
                     "fully_allocated_usd": mov})
    return {"task_id": task, "configuration_id": config,
            "acceptance": {"result": result},
            "usage": {"output_tokens": {"value": output_tokens, "confidence": "authoritative"}},
            "human_effort": {}, "legs": legs}


def _write(dirpath, name, summary):
    rd = os.path.join(dirpath, name)
    os.makedirs(rd, exist_ok=True)
    with open(os.path.join(rd, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh)


class EcstComputability(unittest.TestCase):
    def test_undefined_when_zero_accepted(self) -> None:
        runs = [_summary("t", "P0", "rejected", [0.5]),
                _summary("t", "P0", "rejected", [0.3])]
        r = metrics.ecst(runs, "marginal")
        self.assertEqual(r["status"], "undefined")
        self.assertIsNone(r["value"])
        self.assertEqual(r["attempt_cost_sum"], 0.8)   # sum still reported

    def test_finite_when_accepted(self) -> None:
        runs = [_summary("t", "P0", "accepted", [0.4]),
                _summary("t", "P0", "rejected", [0.2])]   # both attempts count, 1 accepted
        r = metrics.ecst(runs, "marginal")
        self.assertEqual(r["status"], "derived")
        self.assertAlmostEqual(r["value"], 0.6)          # (0.4+0.2)/1

    def test_floor_when_any_leg_unavailable(self) -> None:
        runs = [_summary("t", "C5", "accepted", [0.3, None])]  # executor unavailable
        r = metrics.ecst(runs, "marginal")
        self.assertEqual(r["status"], "derived_floor")
        self.assertTrue(r["attempt_cost_is_floor"])
        self.assertAlmostEqual(r["value"], 0.3)          # known floor, not zero-filled


class HeacAndDispersion(unittest.TestCase):
    def test_heac_unavailable_without_human_minutes(self) -> None:
        runs = [_summary("t", "P0", "accepted", [0.4])]
        e = metrics.ecst(runs, "marginal")
        h = metrics.heac(e, runs, loaded_rate_usd_per_min=2.0)
        self.assertEqual(h["status"], "unavailable")     # no minutes recorded

    def test_dispersion(self) -> None:
        d = metrics.dispersion([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(d["n"], 4)
        self.assertEqual(d["min"], 1.0)
        self.assertEqual(d["max"], 4.0)


class ComputeEndToEnd(unittest.TestCase):
    def test_compute_bundle(self) -> None:
        d = tempfile.mkdtemp(prefix="lab-eval-")
        _write(d, "t__P0__rep1__x", _summary("t", "P0", "rejected", [0.5], 200))
        _write(d, "t__P0__rep2__x", _summary("t", "P0", "accepted", [0.3], 100))
        bundle = metrics.compute(d)
        cell = bundle["cells"]["t|P0"]
        self.assertEqual(cell["n_runs"], 2)
        self.assertEqual(cell["n_accepted"], 1)
        self.assertEqual(cell["ecst_marginal"]["status"], "derived")
        self.assertIn("task:t", bundle["qa_ecst_by_class"])
        self.assertEqual(cell["dispersion_output_tokens"]["n"], 2)


if __name__ == "__main__":
    unittest.main()
