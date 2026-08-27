"""The calibration path: the source's oracle, and the gate built on top of it.

``harness/runner/transfer_calibration.py`` answers one question — do our
transplanted arms behave like the published ones when graded by the SOURCE's own
unit-test oracle? Grading is theirs; cost is ours. These tests cover the parts
that decide things:

  * the source's own text helpers (``extract_code``, the birth gate,
    ``tail_to_cap``) reproduce the source's behaviour, including the two places
    where a plausible rewrite gets it backwards;
  * the pinned slice's totals really are the sum of its own rows;
  * the criteria are evaluated as the prereg words them — in particular an
    unavailable cost FAILS and is never skipped or zero-filled;
  * ``calibration_is_clear``, which is the probe driver's gate, blocks on a
    missing report, a dry-run report, an incomplete run and a failing verdict.

Nothing here calls a model or reads ``results/``. Cells are constructed by hand
and labelled SYNTHETIC.
"""

import json
import os
import tempfile
import unittest

from harness.adapters.transfer_spec import load_spec
from harness.runner import transfer_calibration as C
from harness.telemetry.telemetry import tiered, unavailable

SYNTHETIC = "SYNTHETIC — constructed in tests/test_transfer_calibration.py"


def cell(task_id, *, passed, shape=("cheap",), cost=None, tokens=None,
         degraded=False, strategy_id="r9"):
    """A hand-built CellResult. SYNTHETIC: no model produced any of this."""
    attempts = [
        C.AttemptRecord(attempt=i, leg_id="frontier_strong" if s == "frontier" else "rung_1",
                        is_frontier=(s == "frontier"), why=None, passed=False,
                        birth_gate=False, timed_out=False, returncode=1,
                        response_chars=0, code_chars=0, evidence=SYNTHETIC)
        for i, s in enumerate(shape)
    ]
    if attempts:
        attempts[-1].passed = passed
    return C.CellResult(
        strategy_id=strategy_id, task_id=task_id, passed=passed, attempts=attempts,
        degraded=degraded,
        frontier_calls=sum(1 for s in shape if s == "frontier"),
        stop_reason=SYNTHETIC,
        cost=(tiered(cost, "derived") if cost is not None
              else unavailable("SYNTHETIC: no usage")),
        tokens=(tiered(tokens, "derived") if tokens is not None
                else unavailable("SYNTHETIC: no usage")),
        events_path="/dev/null",
    )


class SourceTextHelpers(unittest.TestCase):
    def test_extract_code_prefers_the_fenced_block(self) -> None:
        text = "Here you go:\n```python\ndef task_func():\n    return 1\n```\nDone."
        self.assertEqual(C.extract_code(text), "def task_func():\n    return 1")

    def test_extract_code_falls_back_to_the_whole_text(self) -> None:
        self.assertEqual(C.extract_code("def task_func(): return 1"),
                         "def task_func(): return 1")

    def test_extract_code_on_empty_input_is_empty_not_an_error(self) -> None:
        self.assertEqual(C.extract_code(""), "")

    def test_the_birth_gate_refuses_a_response_with_no_entry_point(self) -> None:
        self.assertIsNotNone(C.missing_code_error("print('hi')", "task_func"))
        self.assertIsNone(C.missing_code_error("def task_func(): pass", "task_func"))

    def test_tail_to_cap_keeps_the_END_of_a_traceback(self) -> None:
        """The information in a traceback is at the end; truncating from the front
        yields a digest containing only the import block."""
        text = "IMPORTS\n" + "x" * 100 + "\nAssertionError: 3 != 4"
        self.assertTrue(C.tail_to_cap(text, 30).endswith("AssertionError: 3 != 4"))
        self.assertNotIn("IMPORTS", C.tail_to_cap(text, 30))

    def test_tail_to_cap_leaves_short_text_alone(self) -> None:
        self.assertEqual(C.tail_to_cap("short", 2500), "short")


class PinnedSlice(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = C.load_slice()

    def test_the_slice_loads_and_declares_its_authority(self) -> None:
        self.assertTrue(self.doc["slice_id"])
        self.assertIn("transfer-probe", self.doc["gate"]["authority"])

    def test_it_pins_five_tasks(self) -> None:
        self.assertEqual(len(self.doc["tasks"]), 5)

    def test_every_task_carries_a_record_sha256(self) -> None:
        for task in self.doc["tasks"]:
            self.assertRegex(str(task["record_sha256"]).replace("sha256:", ""),
                             r"^[0-9a-f]{64}$")

    def test_the_declared_totals_are_the_sum_of_the_declared_rows(self) -> None:
        """An integrity check on the hand-transcribed reference itself."""
        for sid in C.STRATEGIES:
            result = C.reference_consistency(self.doc, sid)
            self.assertTrue(result["as_run_usd_total_matches_rows"],
                            f"{sid}: declared total {result['declared_total_usd']} != "
                            f"summed rows {result['summed_rows_usd']}")
            self.assertTrue(result["pass_vector_matches_rows"],
                            f"{sid}: the pass vector disagrees with the per-task rows")

    def test_the_oracle_extracts_are_pinned_and_still_hash_true(self) -> None:
        """Raises CalibrationError on drift; a clean return is the assertion."""
        tail = C.load_oracle_tail(self.doc)
        self.assertIn("unittest", tail)

    def test_the_grading_environment_precondition_is_recorded(self) -> None:
        env = self.doc["run_conditions"]["grading_environment"]
        self.assertIn("canonical_solution", env["preflight"])
        self.assertIn("_SHALLOW_CLASSES", env["why_it_is_a_refusal_not_a_warning"])

    def test_the_run_conditions_name_the_probe_profile(self) -> None:
        self.assertEqual(self.doc["run_conditions"]["driver_profile"], "transfer-probe")


class RoutingShape(unittest.TestCase):
    def test_published_rungs_reduce_to_a_model_free_shape(self) -> None:
        shape = C.routing_shape(
            ["gemini-lite", "gemini-3.7-low", "claude-opus-5"], "claude-opus-5")
        self.assertEqual(shape, ["cheap", "cheap", "frontier"])

    def test_it_does_not_fake_a_mismatch_from_rung_identity(self) -> None:
        """J-2: our rungs are Product A, theirs are Gemini. Shape must not care."""
        self.assertEqual(C.routing_shape(["gemini-lite"], "claude-opus-5"), ["cheap"])


class Criteria(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = C.load_slice()
        self.spec = load_spec("r9")
        self.task_ids = [t["task_id"] for t in self.doc["tasks"]]
        self.published = [bool(t["published"]["r9"]["passed"]) for t in self.doc["tasks"]]

    def _cells(self, results, costs=None):
        costs = costs or [0.0] * len(results)
        return [cell(tid, passed=p, cost=c)
                for tid, p, c in zip(self.task_ids, results, costs)]

    def test_a_perfect_pass_vector_passes_criterion_a(self) -> None:
        ev = C.evaluate_strategy(self.spec, self._cells(self.published), self.doc)
        crit = next(c for c in ev["criteria"] if c["id"] == "pass_match")
        self.assertEqual(crit["status"], "pass")
        self.assertEqual(crit["matches"], 5)

    def test_one_disagreement_still_passes_criterion_a(self) -> None:
        flipped = list(self.published)
        flipped[0] = not flipped[0]
        ev = C.evaluate_strategy(self.spec, self._cells(flipped), self.doc)
        crit = next(c for c in ev["criteria"] if c["id"] == "pass_match")
        self.assertEqual(crit["matches"], 4)
        self.assertEqual(crit["status"], "pass", "the registered threshold is >= 4/5")

    def test_two_disagreements_fail_criterion_a(self) -> None:
        flipped = list(self.published)
        flipped[0] = not flipped[0]
        flipped[1] = not flipped[1]
        ev = C.evaluate_strategy(self.spec, self._cells(flipped), self.doc)
        crit = next(c for c in ev["criteria"] if c["id"] == "pass_match")
        self.assertEqual(crit["status"], "fail")

    def test_an_unavailable_cost_fails_criterion_b_and_is_never_zero(self) -> None:
        """CLAUDE.md rule 3, at the one place where breaking it would be cheapest."""
        cells = self._cells(self.published)
        cells[2].cost = unavailable("SYNTHETIC: Product B exposed no usage")
        ev = C.evaluate_strategy(self.spec, cells, self.doc)
        crit = next(c for c in ev["criteria"] if c["id"] == "cost_within_30pct")
        self.assertEqual(crit["status"], "fail")
        self.assertIsNone(crit["measured_slice_usd"])
        self.assertIn("not zero", crit["detail"])

    def test_a_missing_cell_fails_criterion_b_rather_than_shrinking_the_slice(self) -> None:
        ev = C.evaluate_strategy(self.spec, self._cells(self.published)[:4], self.doc)
        crit = next(c for c in ev["criteria"] if c["id"] == "cost_within_30pct")
        self.assertEqual(crit["status"], "fail")

    def test_a_cost_inside_thirty_percent_passes(self) -> None:
        published = float(self.doc["published_slice_reference"]["r9"]["as_run_usd"])
        share = published * 1.2 / 5
        ev = C.evaluate_strategy(self.spec,
                                 self._cells(self.published, [share] * 5), self.doc)
        crit = next(c for c in ev["criteria"] if c["id"] == "cost_within_30pct")
        self.assertEqual(crit["status"], "pass")
        self.assertAlmostEqual(crit["relative_delta"], 0.2, places=5)

    def test_a_cost_outside_thirty_percent_fails_and_names_the_known_blocker(self) -> None:
        published = float(self.doc["published_slice_reference"]["r9"]["as_run_usd"])
        share = published * 4.0 / 5
        ev = C.evaluate_strategy(self.spec,
                                 self._cells(self.published, [share] * 5), self.doc)
        crit = next(c for c in ev["criteria"] if c["id"] == "cost_within_30pct")
        self.assertEqual(crit["status"], "fail")
        self.assertIn("cost_criterion_blocker", crit["detail"])
        self.assertIn("routing_shape_match", crit["detail"],
                      "a reader must be pointed at the diagnostic that does speak to "
                      "routing logic")

    def test_the_verdict_needs_both_gating_criteria(self) -> None:
        ev = C.evaluate_strategy(self.spec, self._cells(self.published), self.doc)
        self.assertEqual(ev["verdict"], "fail",
                         "criterion (b) fails on a zero-cost slice, so the verdict must")
        self.assertTrue(all(c["gating"] for c in ev["criteria"]))

    def test_a_calibration_in_which_the_frontier_never_fires_is_flagged(self) -> None:
        ev = C.evaluate_strategy(self.spec, self._cells(self.published), self.doc)
        diag = next(d for d in ev["diagnostics"] if d["id"] == "frontier_reachability")
        self.assertEqual(diag["status"], "fail")
        self.assertIn("void", diag["detail"])

    def test_degraded_cells_are_named_in_the_evaluation(self) -> None:
        cells = self._cells(self.published)
        cells[1].degraded = True
        ev = C.evaluate_strategy(self.spec, cells, self.doc)
        self.assertEqual(ev["degraded_cells"], [cells[1].task_id])

    def test_token_totals_go_unavailable_if_any_cell_is_unavailable(self) -> None:
        cells = self._cells(self.published)
        cells[0].tokens = tiered({"input_tokens": 10, "output_tokens": 5}, "derived")
        total = C._sum_tokens(cells)
        self.assertEqual(total["confidence"], "unavailable")


class Reports(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = C.load_slice()
        self.spec = load_spec("r9")
        self.task_ids = [t["task_id"] for t in self.doc["tasks"]]
        self.cells = [cell(t, passed=True, cost=0.1) for t in self.task_ids]

    def _report(self, **kw):
        params = dict(dry_run=False, provenance={"SYNTHETIC": True},
                      manifest_pricing="SYNTHETIC-prices.json")
        params.update(kw)
        return C.build_report(self.spec, self.cells, self.doc, **params)

    def test_a_dry_run_report_can_never_carry_a_pass_verdict(self) -> None:
        report = self._report(dry_run=True)
        self.assertEqual(report["verdict"], "fail")
        self.assertIn("NOT A MEASUREMENT", report["status_banner"])

    def test_a_live_report_carries_a_status_banner_naming_the_verdict(self) -> None:
        report = self._report()
        self.assertIn("STATUS:", report["status_banner"])
        self.assertIn(report["verdict"].upper(), report["status_banner"])

    def test_the_report_records_the_fidelity_caveats_it_cannot_fix(self) -> None:
        ids = " ".join(self._report()["fidelity_caveats"])
        for caveat in ("J-2", "J-11", "J-12", "cost_criterion_blocker"):
            self.assertIn(caveat, ids)

    def test_it_states_that_grading_was_the_sources_not_ours(self) -> None:
        self.assertIn("source's own", self._report()["grading"])
        self.assertIn("no lab gate ran", self._report()["grading"])


class ProbeGate(unittest.TestCase):
    """``calibration_is_clear`` — what the probe driver refuses on."""

    def _write(self, out_dir, sid, **fields):
        doc = {"strategy_id": sid, "verdict": "pass", "dry_run": False,
               "incomplete": None, "_SYNTHETIC": SYNTHETIC}
        doc.update(fields)
        path = os.path.join(out_dir, sid, "calibration-report.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

    def test_no_reports_at_all_blocks_and_names_every_strategy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ok, reasons = C.calibration_is_clear(tmp)
            self.assertFalse(ok)
            self.assertEqual(len(reasons), 3)

    def test_two_of_three_passing_still_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp, "r9")
            self._write(tmp, "r6")
            ok, reasons = C.calibration_is_clear(tmp)
            self.assertFalse(ok)
            self.assertTrue(any("r10" in r for r in reasons))

    def test_a_dry_run_report_does_not_count_as_calibration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for sid in C.STRATEGIES:
                self._write(tmp, sid, dry_run=True)
            ok, reasons = C.calibration_is_clear(tmp)
            self.assertFalse(ok)
            self.assertTrue(all("dry run" in r for r in reasons))

    def test_an_incomplete_run_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for sid in C.STRATEGIES:
                self._write(tmp, sid, incomplete="halted at the spend cap")
            ok, reasons = C.calibration_is_clear(tmp)
            self.assertFalse(ok)
            self.assertTrue(all("incomplete" in r for r in reasons))

    def test_a_failing_verdict_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for sid in C.STRATEGIES:
                self._write(tmp, sid, verdict="fail")
            ok, _ = C.calibration_is_clear(tmp)
            self.assertFalse(ok)

    def test_three_passing_live_reports_clear_the_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for sid in C.STRATEGIES:
                self._write(tmp, sid)
            ok, reasons = C.calibration_is_clear(tmp)
            self.assertTrue(ok, reasons)


class Refusals(unittest.TestCase):
    def test_a_drifted_pin_is_a_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "SYNTHETIC-pinned.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("SYNTHETIC content\n")
            with self.assertRaises(C.CalibrationError):
                C.verify_pinned_file(path, {"sha256": "0" * 64, "bytes": 18}, "SYNTHETIC")

    def test_a_matching_pin_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "SYNTHETIC-pinned.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("SYNTHETIC content\n")
            sha, nbytes = C.sha256_file(path)
            out = C.verify_pinned_file(path, {"sha256": sha, "bytes": nbytes},
                                       "SYNTHETIC")
            self.assertEqual(out["sha256"], sha)

    def test_the_exit_codes_are_distinct(self) -> None:
        """A dry run must not be reportable as a gate failure, or vice versa."""
        codes = [C.EXIT_PASS, C.EXIT_GATE_FAILED, C.EXIT_REFUSED, C.EXIT_DRY_RUN]
        self.assertEqual(len(set(codes)), 4)

    def test_a_live_run_without_a_source_root_is_refused(self) -> None:
        rc = C.main(["--live", "--out", tempfile.mkdtemp(prefix="lab-cal-SYNTHETIC-")])
        self.assertEqual(rc, C.EXIT_REFUSED)


if __name__ == "__main__":
    unittest.main()
