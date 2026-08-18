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
    PREREGISTRATIONS,
    SCHEMA,
    arm_coverage,
    arm_key_for,
    build,
    build_cell,
    default_out_dir,
    grade_h_effort,
    grade_w3_escalation,
    heac,
    leg_rows,
    load_runs,
    load_task_registry,
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


# ----------------------------------------------------- the screening-batch surface

def _registry(**tasks):
    """A registry in the shape load_task_registry() returns, for grading tests."""
    return {
        task_id: {
            "task_id": task_id,
            "label": task_id,
            "task_dir": f"tasks/suite/{task_id}",
            "task_class": spec.get("task_class", "feature_implementation"),
            "task_suite_version": "SYNTHETIC-v0",
            "contamination_tier": "SYNTHETIC",
            "registered_arms": spec.get("arms", []),
            "companion_arms": spec.get("companions", []),
            "arm_key": "configurations",
        }
        for task_id, spec in tasks.items()
    }


def _cell(tmp, task, arm, results, cost, task_class=None):
    """Build one cell from `results` (a list of accepted booleans), one run each."""
    for i, accepted in enumerate(results, start=1):
        _synthetic_run(tmp, f"{task}__{arm}__r{i}", task, arm, accepted,
                       None if cost is None else cost * i,
                       {"input_tokens": _slot(100 * i, "authoritative")})
    runs = [r for r in load_runs(tmp)
            if r["summary"]["task_id"] == task
            and r["summary"]["configuration_id"] == arm]
    return build_cell(task, arm, runs, 1.6, task_class=task_class)


class TestTaskRegistry(unittest.TestCase):
    """The arm map is read from tasks/**/task.yaml, never re-declared here."""

    def setUp(self):
        self.registry = load_task_registry()
        if not self.registry:
            self.skipTest("tasks/ not present")

    def test_the_registry_reads_the_registered_arms_from_the_task_files(self):
        for task_id, entry in self.registry.items():
            self.assertTrue(entry["registered_arms"], f"{task_id} declares no arms")
            self.assertTrue(entry["task_class"], f"{task_id} declares no class")

    def test_sealed_hidden_directories_are_never_descended_into(self):
        # A hidden/ dir holds human-held sealed tests; walking into one is a protocol
        # breach even if it happens to contain no task.yaml today.
        for entry in self.registry.values():
            self.assertNotIn("hidden", entry["task_dir"].split(os.sep))

    def test_the_yardstick_follows_the_batch_era(self):
        # Grading a feasibility batch against the screening matrix would invent gaps
        # that were never planned for it.
        self.assertEqual("feasibility_configurations",
                         arm_key_for("results/feasibility-batch3"))
        self.assertEqual("configurations", arm_key_for("results/screening-batch1"))
        self.assertEqual("configurations", arm_key_for("results/screening-batch1/"))

    def test_the_escalation_probe_is_derived_not_hardcoded(self):
        probe = [t for t, e in self.registry.items() if "P1" in e["registered_arms"]]
        self.assertEqual(1, len(probe),
                         "the registration designates exactly one escalation probe; "
                         f"the arm map names {probe}")


class TestArmCoverage(unittest.TestCase):
    def setUp(self):
        self.registry = _registry(
            alpha={"arms": ["P0", "C2", "C5"], "companions": ["C1"]},
            beta={"arms": ["P0", "C2"], "task_class": "code_review"},
        )

    def test_a_registered_arm_with_no_runs_is_missing_not_absent(self):
        cov = arm_coverage(self.registry, {"alpha": ["P0", "C2"]})
        self.assertEqual(["C5"], cov["by_task"]["alpha"]["missing"])
        self.assertFalse(cov["complete"])

    def test_a_companion_arm_is_not_a_protocol_violation(self):
        # C1 is the declared warm-series companion: observed-but-not-in-`configurations`
        # is expected for it, and reporting it as unregistered would cry wolf.
        cov = arm_coverage(self.registry, {"alpha": ["P0", "C2", "C5", "C1"]})
        self.assertEqual(["C1"], cov["by_task"]["alpha"]["companion_observed"])
        self.assertEqual([], cov["by_task"]["alpha"]["unregistered"])

    def test_an_unplanned_arm_is_named_loudly(self):
        cov = arm_coverage(self.registry, {"alpha": ["P0", "C2", "C5", "C9"]})
        self.assertEqual(["C9"], cov["by_task"]["alpha"]["unregistered"])
        self.assertFalse(cov["complete"])

    def test_runs_for_a_task_outside_the_registry_are_surfaced(self):
        cov = arm_coverage(self.registry, {"alpha": ["P0", "C2", "C5"], "gamma": ["P0"]})
        self.assertEqual(["gamma"], cov["tasks_not_in_registry"])
        self.assertFalse(cov["complete"])

    def test_a_task_with_no_runs_does_not_by_itself_fail_completeness(self):
        # beta simply has not run yet; that is visible in `missing`, and it should not
        # be conflated with a violation on a task that did run.
        cov = arm_coverage(self.registry, {"alpha": ["P0", "C2", "C5"]})
        self.assertTrue(cov["complete"])
        self.assertEqual(["P0", "C2"], cov["by_task"]["beta"]["missing"])


class TestLegRows(unittest.TestCase):
    """Delegation and escalation arms bill twice; the bill must stay itemized."""

    def _two_leg_run(self, tmp, run_id, executor_cost):
        run_dir = os.path.join(tmp, run_id)
        os.makedirs(run_dir)
        unavailable = {"value": None, "confidence": "unavailable",
                       "reason": "SYNTHETIC: not exposed at the CLI surface"}
        summary = {
            "SYNTHETIC": "SYNTHETIC test fixture — not a measurement",
            "run_id": run_id, "task_id": "t", "configuration_id": "C5",
            "acceptance": {"result": "accepted"},
            "identity": {"product": _slot("Product A -> Product B", "authoritative"),
                         "cache_state": _slot("cold", "authoritative")},
            "economics": {"cost_basis": "marginal_api_cost"},
            "usage": {"input_tokens": _slot(10, "authoritative")},
            "legs": [
                {"leg_id": "conductor", "role": "conductor", "cost_basis": "marginal_api_cost",
                 "model_or_selector": _slot("STRONG_MODEL_A", "authoritative"),
                 "provider": _slot("SYNTHETIC_PROVIDER", "authoritative"),
                 "marginal_operating_usd": _slot(0.20),
                 "usage": {"input_tokens": _slot(7, "authoritative")}},
                {"leg_id": "executor", "role": "executor", "cost_basis": "cost_unavailable",
                 "model_or_selector": _slot("ECONOMICAL_MODEL_B", "authoritative"),
                 "provider": _slot("SYNTHETIC_PROVIDER", "authoritative"),
                 "marginal_operating_usd": (_slot(executor_cost) if executor_cost is not None
                                            else dict(unavailable)),
                 "usage": {"input_tokens": dict(unavailable)}},
            ],
        }
        with open(os.path.join(run_dir, "summary.json"), "w", encoding="utf-8") as fh:
            json.dump(summary, fh)

    def test_one_row_per_leg_with_its_own_selector_and_basis(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._two_leg_run(tmp, "r1", 0.05)
            self._two_leg_run(tmp, "r2", 0.07)
            legs = leg_rows(load_runs(tmp))
            self.assertTrue(legs["is_multi_leg"])
            self.assertEqual(["conductor", "executor"], [r["leg_id"] for r in legs["rows"]])
            conductor = legs["rows"][0]
            self.assertEqual(2, conductor["n_legs"])
            self.assertEqual(["STRONG_MODEL_A"], conductor["model_or_selector"])
            self.assertEqual(["marginal_api_cost"], conductor["cost_basis"])

    def test_an_unpriced_leg_is_never_back_filled_from_the_priced_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._two_leg_run(tmp, "r1", None)
            legs = leg_rows(load_runs(tmp))
            executor = legs["rows"][1]
            self.assertIsNone(executor["marginal_operating_usd"]["median"])
            self.assertEqual("unavailable",
                             executor["marginal_operating_usd"]["confidence"])
            self.assertEqual(1, executor["legs_cost_unavailable"])
            self.assertEqual("unavailable", executor["confidence"])
            # and its token classes stay unavailable rather than inheriting the other leg
            self.assertIsNone(executor["usage_totals"]["input_tokens"]["value"])
            self.assertEqual("unavailable",
                             executor["usage_totals"]["input_tokens"]["status"])

    def test_a_partly_priced_leg_row_reports_how_many_runs_are_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._two_leg_run(tmp, "r1", 0.05)
            self._two_leg_run(tmp, "r2", None)
            executor = leg_rows(load_runs(tmp))["rows"][1]
            self.assertAlmostEqual(0.05, executor["marginal_operating_usd"]["median"])
            self.assertEqual(1, executor["marginal_operating_usd"]["runs_unavailable"])
            self.assertEqual(1, executor["legs_cost_unavailable"])

    def test_a_single_leg_cell_still_gets_a_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            _synthetic_run(tmp, "r1", "t", "C2", True, 0.4,
                           {"input_tokens": _slot(10, "authoritative")})
            legs = leg_rows(load_runs(tmp))
            self.assertFalse(legs["is_multi_leg"])
            self.assertEqual(1, len(legs["rows"]))


class TestGradeHEffort(unittest.TestCase):
    """The registered high-vs-medium prediction, graded — including when it is wrong."""

    def _grade(self, tmp, cheap_cost, cheap_results=(True, True), task_class=None,
               strong_cost=1.0):
        task_class = task_class or "feature_implementation"
        cells = {
            ("t", "C3"): _cell(tmp, "t", "C3", (True, True), strong_cost, task_class),
            ("t", "C3-med"): _cell(tmp, "t", "C3-med", cheap_results, cheap_cost, task_class),
        }
        return grade_h_effort(cells, _registry(t={"task_class": task_class}))["by_task"][0]

    def test_a_reduction_inside_the_band_supports_the_prediction(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = self._grade(tmp, 0.6)  # 40% cheaper
            self.assertEqual("within_predicted_band", row["verdict"])
            self.assertAlmostEqual(40.0, row["delta"]["reduction_pct"], places=6)
            self.assertEqual({"low": 30.0, "high": 50.0}, row["delta"]["predicted_band_pct"])

    def test_a_smaller_reduction_than_registered_is_reported_as_a_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual("below_predicted_band", self._grade(tmp, 0.9)["verdict"])

    def test_a_larger_reduction_than_registered_is_also_a_miss(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual("above_predicted_band", self._grade(tmp, 0.2)["verdict"])

    def test_a_more_expensive_cheap_arm_refutes_the_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual("direction_refuted", self._grade(tmp, 1.4)["verdict"])

    def test_cheaper_but_failing_a_gate_the_other_arm_passed_refutes_parity(self):
        # The registration predicted the same gates AND a lower cost. Cost alone is not
        # the prediction, so parity is checked first and can refute on its own.
        with tempfile.TemporaryDirectory() as tmp:
            row = self._grade(tmp, 0.4, cheap_results=(True, False))
            self.assertEqual("gate_parity_refuted", row["verdict"])
            self.assertFalse(row["gate_parity"]["holds"])

    def test_an_out_of_scope_task_class_is_shown_but_never_graded(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = self._grade(tmp, 0.4, task_class="complex_bugfix")
            self.assertEqual("exploratory_not_graded", row["verdict"])
            self.assertFalse(row["in_registered_scope"])
            self.assertNotIn("delta", row)

    def test_an_unavailable_cost_is_not_gradable_and_is_not_treated_as_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            cells = {
                ("t", "C3"): _cell(tmp, "t", "C3", (True, True), 1.0),
                ("t", "C3-med"): _cell(tmp, "t", "C3-med", (True, True), None),
            }
            row = grade_h_effort(cells, _registry(t={}))["by_task"][0]
            self.assertEqual("not_gradable", row["verdict"])
            self.assertIn("never treated as zero", row["reason"])
            self.assertIsNone(row["arms"]["C3-med"]["ecst_usd"])

    def test_a_missing_arm_is_not_gradable_rather_than_a_free_win(self):
        with tempfile.TemporaryDirectory() as tmp:
            cells = {("t", "C3"): _cell(tmp, "t", "C3", (True,), 1.0)}
            row = grade_h_effort(cells, _registry(t={}))["by_task"][0]
            self.assertEqual("not_gradable", row["verdict"])
            self.assertIn("C3-med", row["reason"])

    def test_status_is_no_data_when_nothing_could_be_graded(self):
        with tempfile.TemporaryDirectory() as tmp:
            cells = {("t", "C3"): _cell(tmp, "t", "C3", (True,), 1.0)}
            grading = grade_h_effort(cells, _registry(t={}))
            self.assertEqual("no_data", grading["status"])
            self.assertEqual(0, grading["n_graded"])


class TestGradeW3Escalation(unittest.TestCase):
    """The escalation probe: the gate result and the branch are graded separately."""

    def _probe_run(self, tmp, run_id, accepted, escalations, cheap_arm=False):
        run_dir = os.path.join(tmp, run_id)
        os.makedirs(run_dir)
        arm = "C2" if cheap_arm else "P1"
        legs = [{"leg_id": "attempt-economical", "role": "solver",
                 "cost_basis": "marginal_api_cost",
                 "model_or_selector": _slot("ECONOMICAL_MODEL_A", "authoritative"),
                 "marginal_operating_usd": _slot(0.05),
                 "usage": {"input_tokens": _slot(10, "authoritative")}}]
        if escalations:
            legs.append({"leg_id": "escalation-strong", "role": "solver-escalated",
                         "cost_basis": "marginal_api_cost",
                         "model_or_selector": _slot("STRONG_MODEL_A", "authoritative"),
                         "marginal_operating_usd": _slot(0.60),
                         "usage": {"input_tokens": _slot(40, "authoritative")}})
        summary = {
            "SYNTHETIC": "SYNTHETIC test fixture — not a measurement",
            "run_id": run_id, "task_id": "probe", "configuration_id": arm,
            "acceptance": {
                "result": "accepted" if accepted else "rejected",
                "intention_to_route": "economical",
                "completed_route": "strong" if escalations else "economical",
                "gate_checks": {"public": {"gate": "public", "checks": [
                    {"id": "P1-parity", "status": "pass" if accepted else "fail"}]}},
            },
            "behavior": {"escalations": _slot(1 if escalations else 0)},
            "identity": {"product": _slot("Product A", "authoritative"),
                         "cache_state": _slot("cold", "authoritative")},
            "economics": {"cost_basis": "marginal_api_cost"},
            "usage": {"input_tokens": _slot(10, "authoritative")},
            "legs": legs,
        }
        with open(os.path.join(run_dir, "summary.json"), "w", encoding="utf-8") as fh:
            json.dump(summary, fh)

    def _grade(self, tmp, cheap_accepts, probe_escalations):
        for i, accepted in enumerate(cheap_accepts, start=1):
            self._probe_run(tmp, f"c{i}", accepted, False, cheap_arm=True)
        for i, escalated in enumerate(probe_escalations, start=1):
            self._probe_run(tmp, f"p{i}", True, escalated)
        runs = load_runs(tmp)
        by_cell = {}
        for run in runs:
            key = (run["summary"]["task_id"], run["summary"]["configuration_id"])
            by_cell.setdefault(key, []).append(run)
        cells = {key: build_cell(key[0], key[1], group, 1.6, task_class="migration")
                 for key, group in by_cell.items()}
        registry = _registry(probe={"task_class": "migration",
                                    "arms": ["C2", "P1"]})
        return grade_w3_escalation(cells, by_cell, registry)

    def test_the_registered_prediction_is_supported_when_both_halves_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            grading = self._grade(tmp, [False, False], [True, True])
            self.assertEqual("failed", grading["economical_tier_gate"])
            self.assertEqual("observed", grading["escalation_branch"])
            self.assertEqual("prediction_supported", grading["outcome"])
            self.assertEqual(2, grading["n_escalated"])

    def test_the_registered_null_result_is_reported_as_a_refutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            grading = self._grade(tmp, [True, True], [False, False])
            self.assertEqual("prediction_refuted", grading["outcome"])
            self.assertIn("null", grading["outcome_basis"])

    def test_a_split_result_is_mixed_rather_than_rounded_to_a_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            grading = self._grade(tmp, [True, False], [True, False])
            self.assertEqual("mixed", grading["economical_tier_gate"])
            self.assertEqual("mixed", grading["outcome"])

    def test_no_runs_is_not_yet_run_rather_than_a_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            grading = self._grade(tmp, [], [])
            self.assertEqual("not_yet_run", grading["outcome"])

    def test_each_traced_run_carries_its_route_gates_and_legs(self):
        with tempfile.TemporaryDirectory() as tmp:
            grading = self._grade(tmp, [False], [True])
            run = grading["trace"][0]
            self.assertEqual("economical", run["intention_to_route"])
            self.assertEqual("strong", run["completed_route"])
            self.assertTrue(run["escalation_fired"])
            self.assertEqual(2, len(run["legs"]))
            self.assertEqual(["public"], [g["gate"] for g in run["gate_checks"]])

    def test_a_failed_gate_names_the_check_without_reading_the_sealed_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            grading = self._grade(tmp, [False], [True])
            cheap_line = grading["economical_solo"]
            self.assertEqual("0/1", cheap_line["acceptance"])
            self.assertTrue(cheap_line["scope_line"])

    def test_the_probe_task_comes_from_the_arm_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            grading = self._grade(tmp, [False], [True])
            self.assertEqual("probe", grading["task_id"])
            self.assertEqual(["probe"], grading["probe_tasks"])

    def test_an_ambiguous_arm_map_refuses_to_grade(self):
        registry = _registry(one={"arms": ["P1"]}, two={"arms": ["P1"]})
        grading = grade_w3_escalation({}, {}, registry)
        self.assertEqual("not_gradable", grading["outcome"])
        self.assertIn("exactly one probe", grading["reason"])


class TestPreregistrationsDoNotDrift(unittest.TestCase):
    """The prose registrations are authoritative; the constant must still match them.

    ``PREREGISTRATIONS`` holds only the machine-gradable terms. If someone edits a
    threshold here to fit a result, or edits a registration file after the fact, these
    assertions fail — which is the whole point of registering a prediction in writing.
    """

    def _text(self, rel_path):
        path = os.path.join(REPO, rel_path)
        self.assertTrue(os.path.isfile(path), f"registration missing: {rel_path}")
        with open(path, encoding="utf-8") as fh:
            # Registrations are hand-wrapped prose; compare on normalized whitespace so
            # a re-wrap is not mistaken for a change of terms.
            return " ".join(fh.read().replace("–", "-").split())

    def test_every_registration_file_referenced_exists(self):
        for reg in PREREGISTRATIONS.values():
            self._text(reg["file"])

    def test_the_h_effort_terms_still_match_the_registration(self):
        reg = PREREGISTRATIONS["h_effort"]
        text = self._text(reg["file"])
        self.assertIn(reg["registered"], text)
        for arm in reg["arms"]:
            self.assertIn(arm, text)
        self.assertIn("30-50%", text, "the predicted band is not the one registered")
        self.assertEqual(30.0, reg["predicted_reduction_pct"]["low"])
        self.assertEqual(50.0, reg["predicted_reduction_pct"]["high"])
        self.assertIn("complex multi-file bugfix", text,
                      "the excluded scope is not the one registered")
        self.assertIn("published either way", text.lower())
        self.assertTrue(reg["publish_either_way"])

    def test_the_escalation_terms_still_match_the_registration(self):
        reg = PREREGISTRATIONS["w3_escalation"]
        text = self._text(reg["file"])
        self.assertIn(reg["registered"], text)
        for arm in reg["arms"]:
            self.assertIn(arm, text)
        self.assertIn(reg["probe_arm"], text)
        self.assertIn(reg["economical_arm"], text)
        self.assertIn("DELIBERATELY selected", text)
        self.assertIn("published either way", text.lower())
        self.assertTrue(reg["publish_either_way"])

    def test_the_constant_uses_placeholder_labels_only(self):
        # CLAUDE.md rule 7: permanent material never names a real model. The prose
        # registration may (it is internal); the emitted table must not.
        blob = json.dumps(PREREGISTRATIONS).lower()
        for identifier in ("gemini", "claude", "sonnet", "flash", "anthropic", "vertex"):
            self.assertNotIn(identifier, blob,
                             f"{identifier!r} leaked into the emitted decision table")


class TestScreeningTableSurface(unittest.TestCase):
    """build() emits the screening sections the report page renders."""

    def test_a_screening_batch_gets_coverage_grading_and_a_scoping_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch = os.path.join(tmp, "screening-batchX")
            os.makedirs(batch)
            _synthetic_run(batch, "r1", "t", "C2", True, 0.4,
                           {"input_tokens": _slot(10, "authoritative")})
            table = build(batch)
            self.assertIn("screening_note", table)
            self.assertIn("SPEC §5", table["screening_note"])
            self.assertIn("arm_coverage", table)
            self.assertIn("prereg_grading", table)
            self.assertIn("task_classes", table)
            for cell in table["cells"]:
                self.assertIn("legs", cell)
                self.assertIn("task_class", cell)

    def test_the_markdown_reports_coverage_and_grading(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch = os.path.join(tmp, "screening-batchX")
            os.makedirs(batch)
            _synthetic_run(batch, "r1", "t", "C2", True, 0.4,
                           {"input_tokens": _slot(10, "authoritative")})
            md = render_markdown(build(batch))
            self.assertIn("Arm coverage", md)
            self.assertIn("Pre-registration grading", md)
            self.assertIn("H-effort", md)


if __name__ == "__main__":
    unittest.main()
