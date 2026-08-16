"""Tests for the decision-table summarizer (harness/telemetry/summarize.py).

Two sources, deliberately:

  * **The real batch-3 dataset** (`results/feasibility-batch3/`, read-only) — the data
    contract has to hold against the shape the harness actually writes, including the
    C1 warm-series cell where two of three runs have no cost.
  * **SYNTHETIC in-memory fixtures** built in a tmpdir for the paths batch 3 does not
    exercise: zero accepted outcomes, a wholly unavailable token class, a missing event
    log, and a missing loaded rate.

The invariant every test defends: **unavailable is never zero** (CLAUDE.md rule 3). A
figure the data cannot support must come back `None` with a tier and a reason, or as an
explicit `derived_floor`, never as a plausible-looking number.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.telemetry.summarize import (  # noqa: E402
    SCHEMA,
    build,
    build_cell,
    default_out_dir,
    heac,
    load_runs,
    main,
    render_markdown,
    tokens_per_accepted,
    wallclock_seconds,
)

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BATCH3 = os.path.join(REPO, "results", "feasibility-batch3")


def _slot(value, confidence="derived", **extra):
    return {"value": value, "confidence": confidence, **extra}


def _synthetic_run(tmp, run_id, task, config, accepted, cost, usage, events=True):
    """Write one SYNTHETIC run directory. Not telemetry — fabricated shapes for edge
    cases only, never written under results/."""
    run_dir = os.path.join(tmp, run_id)
    os.makedirs(run_dir)
    summary = {
        "SYNTHETIC": "SYNTHETIC test fixture — not a measurement",
        "run_id": run_id, "task_id": task, "configuration_id": config,
        "acceptance": {"result": "accepted" if accepted else "rejected"},
        "identity": {"product": _slot("Product A", "authoritative"),
                     "model_or_selector": _slot("STRONG_MODEL_A", "authoritative"),
                     "cache_state": _slot("cold", "authoritative"),
                     "contamination_tier": "obscure"},
        "economics": {"cost_basis": "marginal_api_cost",
                      "pricing_snapshot": "SYNTHETIC-prices.json"},
        "usage": usage,
        "legs": [{"leg_id": "leg0", "role": "solo",
                  "marginal_operating_usd": (_slot(cost) if cost is not None
                                             else _slot(None, "unavailable",
                                                        reason="SYNTHETIC")),
                  "fully_allocated_usd": (_slot(cost) if cost is not None
                                          else _slot(None, "unavailable",
                                                     reason="SYNTHETIC"))}],
    }
    with open(os.path.join(run_dir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh)
    if events:
        with open(os.path.join(run_dir, "events.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "model_call_started",
                                 "ts": "2026-08-15T10:00:00+00:00"}) + "\n")
            fh.write(json.dumps({"event": "acceptance",
                                 "ts": "2026-08-15T10:00:42+00:00"}) + "\n")
    return run_dir


class TestBatch3(unittest.TestCase):
    """The real dataset. Read-only — nothing here writes into results/."""

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(BATCH3):
            raise unittest.SkipTest("results/feasibility-batch3 not present")
        cls.table = build(BATCH3)
        cls.cells = {(c["task_id"], c["configuration_or_policy"]): c
                     for c in cls.table["cells"]}

    def test_loads_every_run_and_groups_into_cells(self):
        self.assertEqual(self.table["schema"], SCHEMA)
        self.assertEqual(self.table["n_runs"], len(load_runs(BATCH3)))
        self.assertEqual(self.table["n_cells"], len(self.table["cells"]))
        # task × configuration/policy, not one row per run
        self.assertLess(self.table["n_cells"], self.table["n_runs"])
        for (task, config) in self.cells:
            self.assertTrue(task and task != "?")
            self.assertTrue(config and config != "?")

    def test_acceptance_is_n_over_n_and_authoritative(self):
        for cell in self.table["cells"]:
            acc = cell["acceptance"]
            self.assertEqual(acc["of"], cell["n_runs"])
            self.assertLessEqual(acc["accepted"], acc["of"])
            self.assertEqual(acc["display"], f"{acc['accepted']}/{acc['of']}")
            self.assertEqual(acc["confidence"], "authoritative")
            self.assertEqual(sum(acc["breakdown"].values()), cell["n_runs"])

    def test_c1_warm_cell_is_a_floor_not_a_complete_figure(self):
        """C1 in batch 3 has runs whose cost is unavailable. The cell must say
        `derived_floor` and must not silently average over the missing runs."""
        cell = self.cells[("pilot-realworld-draft-articles", "C1")]
        ecst = cell["ecst"]["marginal_operating_usd"]
        self.assertEqual(ecst["status"], "derived_floor")
        attempt = cell["ecst"]["attempt_cost_usd"]
        self.assertEqual(attempt["of_runs"], cell["n_runs"])
        self.assertGreater(attempt["runs_unavailable"], 0)
        self.assertLess(attempt["n"], attempt["of_runs"])
        # the partial n is visible in the rendered table, not buried in the JSON
        self.assertIn(f"n={attempt['n']} of {attempt['of_runs']}",
                      render_markdown(self.table))

    def test_every_figure_carries_a_confidence_tier(self):
        tiers = {"authoritative", "derived", "proxy_observed", "unavailable"}
        for cell in self.table["cells"]:
            self.assertIn(cell["acceptance"]["confidence"], tiers)
            self.assertIn(cell["ecst"]["attempt_cost_usd"]["confidence"], tiers)
            self.assertIn(cell["wallclock_s"]["confidence"], tiers)
            self.assertIn(cell["heac"]["confidence"], tiers)
            for slot in cell["tokens_per_accepted_outcome"].values():
                self.assertIn(slot["confidence"], tiers)

    def test_every_cell_carries_an_n_scope_line(self):
        for cell in self.table["cells"]:
            line = cell["scope_line"]
            self.assertIn(f"n={cell['n_runs']} run(s)", line)
            self.assertIn("accepted", line)
            self.assertIn("basis", line)
            self.assertTrue(cell["scope"]["pricing_snapshot"])
            self.assertTrue(cell["scope"]["cache_state"])

    def test_no_zero_fill_anywhere(self):
        """A missing figure is None with a reason — never 0.0, which would read as
        'this was free' (CLAUDE.md rule 3)."""
        def walk(node, path=""):
            if isinstance(node, dict):
                if node.get("confidence") == "unavailable" and "value" in node:
                    self.assertIsNone(node["value"], f"zero-filled at {path}")
                    self.assertTrue(node.get("reason"), f"no reason at {path}")
                for k, v in node.items():
                    walk(v, f"{path}.{k}")
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f"{path}[{i}]")
        walk(self.table)

    def test_tokens_per_accepted_charges_failed_attempts(self):
        """Tokens from ALL attempts land in the numerator — a cell that burned tokens
        failing must not look cheaper than one that did not."""
        cell = self.cells[("pilot-realworld-draft-articles", "C1")]
        slot = cell["tokens_per_accepted_outcome"]["cache_read_tokens"]
        self.assertEqual(slot["n_runs"], 3)
        self.assertEqual(slot["status"], "derived_floor")
        self.assertGreater(slot["total_tokens"], 0)
        self.assertAlmostEqual(slot["value"],
                               slot["total_tokens"] / slot["n_accepted"], places=1)

    def test_unexposed_token_class_stays_unavailable(self):
        """Product A does not expose reasoning/tool-result classes in this batch."""
        cell = self.cells[("pilot-realworld-draft-articles", "C2")]
        for key in ("reasoning_tokens", "tool_result_tokens"):
            slot = cell["tokens_per_accepted_outcome"][key]
            self.assertEqual(slot["status"], "unavailable")
            self.assertIsNone(slot["value"])
            self.assertIsNone(slot["total_tokens"])
            self.assertTrue(slot["reason"])

    def test_wallclock_is_derived_from_the_event_log(self):
        for cell in self.table["cells"]:
            wc = cell["wallclock_s"]
            if wc["median"] is None:
                continue
            self.assertEqual(wc["confidence"], "derived")
            self.assertGreater(wc["min"], 0)
            self.assertLessEqual(wc["min"], wc["median"])
            self.assertLessEqual(wc["median"], wc["max"])

    def test_heac_carries_reviewer_verdict_and_review_n(self):
        reviewed = [c for c in self.table["cells"] if c["heac"]["n_reviewed"] > 0]
        self.assertTrue(reviewed, "batch 3 has timed human review on rep-1 runs")
        for cell in reviewed:
            h = cell["heac"]
            self.assertIsNotNone(h["value"])
            self.assertEqual(h["loaded_rate_usd_per_min"],
                             self.table["loaded_rate_usd_per_min"])
            # HEAC = model component + human minutes × rate, and human dollars dominate
            self.assertAlmostEqual(
                h["value"],
                h["model_component"] + h["human_minutes"] * h["loaded_rate_usd_per_min"],
                places=4)
            self.assertLess(h["n_reviewed"], cell["n_runs"] + 1)
            self.assertTrue(h["reviewer_verdicts"])

    def test_would_not_merge_verdict_survives_gate_acceptance(self):
        """A gate-accepted cell can still be would_not_merge. The table must show both
        rather than let the gate speak for the reviewer."""
        cell = self.cells[("w1-realworld-mapper-tests", "C2")]
        self.assertEqual(cell["acceptance"]["accepted"], cell["acceptance"]["of"])
        self.assertIn("would_not_merge", cell["heac"]["reviewer_verdicts"])
        markdown = render_markdown(self.table)
        self.assertIn("would_not_merge", markdown)

    def test_markdown_opens_with_a_status_banner_and_the_claims_guards(self):
        markdown = render_markdown(self.table)
        head = markdown.splitlines()[:5]
        self.assertTrue(any("STATUS: PENDING" in ln for ln in head), head)
        self.assertIn("CP-FINDINGS", "\n".join(head))
        self.assertIn("NON-COMPARATIVE", markdown)
        self.assertIn("never ranks configurations", markdown)
        # no forbidden claim vocabulary (CLAUDE.md rule 4)
        for banned in ("audit-grade", "better than", "outperform", "FTE-equivalent"):
            self.assertNotIn(banned, markdown)
        self.assertIn("no FTE conversion", markdown)  # the prohibition, not a claim

    def test_exact_selectors_are_labelled_internal_provenance(self):
        """Rule 7: real selectors may be recorded, but the table must say they are
        replaced by placeholder labels before anything external."""
        markdown = render_markdown(self.table)
        self.assertIn("internal provenance", markdown)
        self.assertIn("STRONG_MODEL_A", markdown)
        self.assertIn("CLAUDE.md rule 7", markdown)

    def test_status_banner_is_selectable(self):
        table = build(BATCH3, status="AUTHORITATIVE")
        self.assertIn("STATUS: AUTHORITATIVE",
                      "\n".join(render_markdown(table).splitlines()[:5]))

    def test_cli_writes_both_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc = main([BATCH3, "--out-dir", tmp])
            self.assertEqual(rc, 0)
            with open(os.path.join(tmp, "decision-table.json"), encoding="utf-8") as fh:
                emitted = json.load(fh)
            self.assertEqual(emitted["schema"], SCHEMA)
            self.assertEqual(emitted["n_cells"], self.table["n_cells"])
            with open(os.path.join(tmp, "decision-table.md"), encoding="utf-8") as fh:
                self.assertIn("STATUS: PENDING", fh.read().splitlines()[0])


class TestEdgeCases(unittest.TestCase):
    """SYNTHETIC fixtures for the paths batch 3 does not reach."""

    def test_zero_accepted_is_undefined_not_infinite_and_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            _synthetic_run(tmp, "r1", "t", "C2", False, 0.5,
                           {"input_tokens": _slot(100, "authoritative")})
            runs = load_runs(tmp)
            slot = tokens_per_accepted(runs, "input_tokens")
            self.assertEqual(slot["status"], "undefined")
            self.assertIsNone(slot["value"])
            self.assertEqual(slot["total_tokens"], 100)  # spend still recorded
            cell = build_cell("t", "C2", runs, 1.6)
            self.assertEqual(cell["ecst"]["marginal_operating_usd"]["status"],
                             "undefined")

    def test_missing_event_log_is_unavailable_not_zero_seconds(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _synthetic_run(tmp, "r1", "t", "C2", True, 0.5,
                                     {"input_tokens": _slot(10, "authoritative")},
                                     events=False)
            wc = wallclock_seconds(run_dir)
            self.assertIsNone(wc["value"])
            self.assertEqual(wc["confidence"], "unavailable")
            self.assertTrue(wc["reason"])
            cell = build_cell("t", "C2", load_runs(tmp), 1.6)
            self.assertIsNone(cell["wallclock_s"]["median"])
            self.assertEqual(cell["wallclock_s"]["runs_unavailable"], 1)
            self.assertIn("unavailable (0 of 1 reporting)",
                          render_markdown({**build(tmp), "cells": [cell]}))

    def test_all_costs_unavailable_stays_unavailable(self):
        """The Product-B case: no machine-readable usage headless (SPEC §2.9). The
        cell must be unavailable, not $0.00."""
        with tempfile.TemporaryDirectory() as tmp:
            _synthetic_run(tmp, "r1", "t", "C3", True, None,
                           {"input_tokens": _slot(None, "unavailable",
                                                  reason="SYNTHETIC not exposed")})
            cell = build_cell("t", "C3", load_runs(tmp), 1.6)
            ecst = cell["ecst"]["marginal_operating_usd"]
            self.assertIsNone(ecst["value"])
            self.assertEqual(ecst["status"], "unavailable")
            slot = cell["tokens_per_accepted_outcome"]["input_tokens"]
            self.assertIsNone(slot["value"])
            self.assertEqual(slot["status"], "unavailable")
            self.assertIn("unavailable", render_markdown({**build(tmp),
                                                          "cells": [cell]}))

    def test_heac_without_a_declared_rate_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            _synthetic_run(tmp, "r1", "t", "C2", True, 0.5,
                           {"input_tokens": _slot(10, "authoritative")})
            runs = load_runs(tmp)
            runs[0]["summary"]["human_effort"] = {
                "review_minutes": _slot(5.0, "authoritative"),
                "reviewer_verdict": _slot("would_merge", "authoritative"),
                "reviewer": "human-1"}
            cell_ecst = {"value": 0.5, "status": "derived"}
            self.assertIsNone(heac(cell_ecst, runs, None)["value"])
            with_rate = heac(cell_ecst, runs, 1.6)
            self.assertAlmostEqual(with_rate["value"], 0.5 + 5.0 * 1.6, places=6)
            self.assertEqual(with_rate["reviewers"], ["human-1"])

    def test_blocked_minutes_are_reported_but_never_monetized(self):
        with tempfile.TemporaryDirectory() as tmp:
            _synthetic_run(tmp, "r1", "t", "C2", True, 0.5,
                           {"input_tokens": _slot(10, "authoritative")})
            runs = load_runs(tmp)
            runs[0]["summary"]["human_effort"] = {
                "review_minutes": _slot(2.0, "authoritative"),
                "blocked_minutes": _slot(30.0, "authoritative")}
            result = heac({"value": 0.5, "status": "derived"}, runs, 1.6)
            self.assertEqual(result["blocked_minutes_not_monetized"], 30.0)
            self.assertAlmostEqual(result["value"], 0.5 + 2.0 * 1.6, places=6)

    def test_out_dir_pairs_with_the_report_directory(self):
        """CLAUDE.md rule 8: report/batchN pairs with results/feasibility-batchN."""
        self.assertTrue(default_out_dir("results/feasibility-batch3")
                        .endswith(os.path.join("report", "batch3")))
        self.assertTrue(default_out_dir("results/screening-batch1/")
                        .endswith(os.path.join("report", "screening-batch1")))
        self.assertIsNone(default_out_dir("results/smoke"))

    def test_missing_batch_directory_fails_loudly(self):
        with self.assertRaises(FileNotFoundError):
            load_runs(os.path.join(REPO, "results", "no-such-batch"))


if __name__ == "__main__":
    unittest.main()
