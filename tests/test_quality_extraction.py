"""Graded quality must stay honest about three things.

  1. It is SECONDARY. It never rewrites an acceptance verdict, and every record
     says so in its own body — a reader who finds one file on disk, with no
     surrounding table, must still know not to quote it as the outcome.
  2. Unavailable is not zero. W3 and W4b have no per-check sealed output in the
     archive at all. A `0` there would read as "found nothing" when the truth is
     "nobody wrote it down" (CLAUDE.md rule 3).
  3. Fabrications are not deductions. Six defects found with one invented finding
     is not five found. Netting them destroys the distinction the number exists
     to make.

Fixtures are SYNTHETIC sealed-runner transcripts written under tmp. Real sealed
material is never read.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile
import unittest

from harness.analysis import quality


def _log(body: str, verdict: str = "FAIL") -> str:
    return ("--- hidden gate (stdout) ---\n"
            "== hidden gate (SYNTHETIC) ==\n"
            "  version: SYNTHETIC-v1\n"
            "  runner:  check.sh (sealed; contents never shown)\n"
            "  -- sealed runner (stderr) --\n"
            f"{body}"
            f"== hidden gate: {verdict} ==\n\n--- exit: 1\n")


class _Runs(unittest.TestCase):
    def setUp(self) -> None:
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="quality-SYNTHETIC-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def run_dir(self, task: str, body: str | None, *, config: str = "C3",
                rep: int = 1, name: str = "gate-hidden.log",
                events: list | None = None) -> pathlib.Path:
        d = self.root / "ds" / f"{task}__{config}__rep{rep}__20260819T000000"
        d.mkdir(parents=True)
        if body is not None:
            (d / name).write_text(_log(body), encoding="utf-8")
        # Untruncated unless a test says otherwise: a non-empty diff and no
        # failure events. Without this every fixture would look cut off.
        (d / "agent-solution.diff").write_text("--- a\n+++ b\n", encoding="utf-8")
        (d / "events.jsonl").write_text(
            "".join(json.dumps(e) + "\n" for e in (events or [])), encoding="utf-8")
        return d


class W1MutationOutput(_Runs):
    def test_all_caught(self):
        d = self.run_dir("w1-SYNTHETIC", "".join(
            f"  | hidden: caught: m{i}-SYNTHETIC\n" for i in range(1, 7))
            + "  | hidden: all 6 mutants caught\n")
        rec = quality.score_run(str(d))
        self.assertEqual((rec["score"], rec["max"]), (6, 6))

    def test_a_missed_mutant_lowers_the_score_and_is_named(self):
        d = self.run_dir("w1-SYNTHETIC",
                         "  | hidden: caught: m1-SYNTHETIC\n"
                         "  | hidden: NOT-caught: m2-SYNTHETIC\n")
        rec = quality.score_run(str(d))
        self.assertEqual((rec["score"], rec["max"]), (1, 2))
        self.assertEqual(rec["detail"]["missed"], ["m2-SYNTHETIC"])

    def test_no_agent_tests_is_a_real_zero_not_an_unavailable(self):
        # The agent delivered nothing to run. That IS a measurement of zero.
        d = self.run_dir("w1-SYNTHETIC", "  | hidden: no agent tests under src/tests/\n")
        rec = quality.score_run(str(d))
        self.assertTrue(rec["available"])
        self.assertEqual(rec["score"], 0)

    def test_the_regrade_log_is_read_when_that_is_the_only_one(self):
        d = self.run_dir("w1-SYNTHETIC", "  | hidden: caught: m1-SYNTHETIC\n",
                         name="regrade-gate-hidden.log")
        self.assertEqual(quality.score_run(str(d))["score"], 1)


class W1bMutationOutput(_Runs):
    BODY = ("  | CAUGHT M1\n  | CAUGHT M2\n  | MISSED M3\n"
            "  | CONTROL M6-control caught\n")

    def test_the_control_is_excluded_from_the_score(self):
        rec = quality.score_run(str(self.run_dir("w1b-SYNTHETIC", self.BODY)))
        self.assertEqual((rec["score"], rec["max"]), (2, 3),
                         "M6-control must not inflate either number")

    def test_a_caught_control_is_reported_on_its_own(self):
        rec = quality.score_run(str(self.run_dir("w1b-SYNTHETIC", self.BODY)))
        self.assertEqual(rec["detail"]["control_caught"], ["M6-control"])

    def test_a_survived_control_is_not_flagged(self):
        rec = quality.score_run(str(self.run_dir(
            "w1b-SYNTHETIC", "  | CAUGHT M1\n  | CONTROL M6-control survived\n")))
        self.assertEqual(rec["detail"]["control_caught"], [])
        self.assertEqual(rec["score"], 1)

    def test_w1b_is_not_parsed_by_the_w1_grammar(self):
        # `w1b-` and `w1-` both prefix-match loosely; the longer wins.
        rec = quality.score_run(str(self.run_dir("w1b-SYNTHETIC", self.BODY)))
        self.assertIn("control", rec["detail"])


class W6ReviewOutput(_Runs):
    def test_defects_and_fabrications_are_two_numbers(self):
        body = "".join(f"  | DETECTED D{i}-SYNTHETIC\n" for i in range(1, 7)) + \
               "  | FABRICATED src/SYNTHETIC.ts:191\n"
        rec = quality.score_run(str(self.run_dir("w6-SYNTHETIC", body)))
        self.assertEqual((rec["score"], rec["max"]), (6, 6),
                         "a fabrication must not be netted off the defects found")
        self.assertEqual(rec["detail"]["fabrication_count"], 1)

    def test_a_missed_defect_lowers_the_score(self):
        rec = quality.score_run(str(self.run_dir(
            "w6-SYNTHETIC", "  | DETECTED D1-SYNTHETIC\n  | MISSED D2-SYNTHETIC\n")))
        self.assertEqual((rec["score"], rec["max"]), (1, 2))

    def test_no_report_is_a_real_zero(self):
        rec = quality.score_run(str(self.run_dir(
            "w6-SYNTHETIC", "  | no review-report.txt — reject\n")))
        self.assertTrue(rec["available"])
        self.assertEqual(rec["score"], 0)


class SolutionTaskSealedChecks(_Runs):
    """W3/W4b, graded per sealed check rather than by exit code alone."""

    def _checks(self, *rows: str) -> str:
        return ("  -- sealed checks (id and status only) --\n"
                + "".join(f"  | {r}\n" for r in rows))

    def test_passed_checks_are_counted(self):
        d = self.run_dir("w3-SYNTHETIC", self._checks(
            "PASSED\ttests/SYNTHETIC.py::test_L010",
            "PASSED\ttests/SYNTHETIC.py::test_L019",
            "FAILED\ttests/SYNTHETIC.py::test_L044"))
        rec = quality.score_run(str(d))
        self.assertEqual((rec["score"], rec["max"]), (2, 3))
        self.assertEqual(rec["metric"], "sealed_rules_clean")
        self.assertEqual(rec["detail"]["failed"], ["tests/SYNTHETIC.py::test_L044"])

    def test_w4b_uses_its_own_metric_name(self):
        d = self.run_dir("w4b-SYNTHETIC", self._checks("PASSED\ttests/S.py::test_a"))
        self.assertEqual(quality.score_run(str(d))["metric"],
                         "sealed_assertions_passed")

    def test_an_error_status_counts_as_not_passing(self):
        d = self.run_dir("w3-SYNTHETIC", self._checks(
            "PASSED\ttests/S.py::a", "ERROR\ttests/S.py::b", "SKIPPED\ttests/S.py::c"))
        rec = quality.score_run(str(d))
        self.assertEqual((rec["score"], rec["max"]), (1, 3))

    def test_a_run_graded_before_the_gate_recorded_detail_is_unavailable(self):
        # THE PRE-FIX ARCHIVE. Exit code only. A `0` here would say the run
        # satisfied no sealed rule; the truth is nobody wrote down how many.
        d = self.run_dir("w3-SYNTHETIC", "  | some other block\n")
        rec = quality.score_run(str(d))
        self.assertFalse(rec["available"])
        self.assertIsNone(rec["score"])
        self.assertIn("only the sealed exit code", rec["reason"])


class WhatCannotBeScored(_Runs):
    def test_a_solution_task_with_no_log_at_all_is_unavailable(self):
        for task in ("w3-SYNTHETIC", "w4b-SYNTHETIC"):
            rec = quality.score_run(str(self.run_dir(task, None)))
            self.assertFalse(rec["available"], task)
            self.assertIsNone(rec["score"], task)

    def test_a_run_with_no_sealed_log_is_unavailable(self):
        rec = quality.score_run(str(self.run_dir("w1-SYNTHETIC", None)))
        self.assertFalse(rec["available"])
        self.assertIn("no sealed gate log", rec["reason"])

    def test_a_log_with_no_runner_block_is_unavailable(self):
        d = self.run_dir("w1-SYNTHETIC", "")
        (d / "gate-hidden.log").write_text(
            "== hidden gate (SYNTHETIC) ==\n== hidden gate: FAIL ==\n", encoding="utf-8")
        rec = quality.score_run(str(d))
        self.assertFalse(rec["available"])

    def test_an_unregistered_task_is_unavailable_and_says_so(self):
        rec = quality.score_run(str(self.run_dir("pilot-SYNTHETIC", "  | whatever\n")))
        self.assertFalse(rec["available"])
        self.assertIn("no sealed-output grammar", rec["reason"])

    def test_a_non_run_directory_scores_nothing(self):
        self.assertIsNone(quality.score_run(str(self.root)))


class ATruncatedRunScoresNothing(_Runs):
    """A run the harness killed cannot be graded on what it happened to emit.

    `0 defects found` on a killed run reads as a model that found nothing. The
    model was cut off mid-sentence. Scoring it at all is the fabrication.
    """

    TIMEOUT = {"event_type": "failure", "category": "claude_timeout", "leg": "main"}

    def test_a_timed_out_run_is_unavailable_even_with_a_full_sealed_log(self):
        body = "".join(f"  | DETECTED D{i}-SYNTHETIC\n" for i in range(1, 7))
        d = self.run_dir("w6-SYNTHETIC", body, events=[self.TIMEOUT])
        rec = quality.score_run(str(d))
        self.assertFalse(rec["available"])
        self.assertIsNone(rec["score"])
        self.assertIn("truncated", rec["reason"])
        self.assertEqual(rec["truncated"], "stop_reason=claude_timeout")

    def test_a_zero_byte_diff_run_scores_nothing_rather_than_zero(self):
        d = self.run_dir("w6-SYNTHETIC", "  | no review-report.txt — reject\n")
        (d / "agent-solution.diff").write_text("", encoding="utf-8")
        rec = quality.score_run(str(d))
        self.assertFalse(rec["available"], "a zero here would be a fabricated result")
        self.assertIsNone(rec["score"])

    def test_a_truncated_mutation_run_scores_nothing(self):
        d = self.run_dir("w1-SYNTHETIC", "  | hidden: no agent tests under src/tests/\n")
        (d / "agent-solution.diff").write_text("", encoding="utf-8")
        self.assertFalse(quality.score_run(str(d))["available"])

    def test_truncation_outranks_the_unscorable_task_reason(self):
        # W3 is unscorable AND this run was killed. The reason a reader needs
        # first is that the run is not evidence at all.
        d = self.run_dir("w3-SYNTHETIC", None, events=[self.TIMEOUT])
        rec = quality.score_run(str(d))
        self.assertIn("truncated", rec["reason"])


class TheRecordCarriesItsOwnCaveat(_Runs):
    def test_every_record_declares_itself_secondary(self):
        for task in ("w1-SYNTHETIC", "w1b-SYNTHETIC", "w6-SYNTHETIC", "w3-SYNTHETIC"):
            rec = quality.score_run(str(self.run_dir(task, "  | CAUGHT M1\n")))
            self.assertIn("EXPLORATORY SECONDARY", rec["status"], task)
            self.assertIn("does not override", rec["status"], task)

    def test_writing_adds_a_file_and_edits_none(self):
        d = self.run_dir("w6-SYNTHETIC", "  | DETECTED D1-SYNTHETIC\n")
        (d / "summary.json").write_text('{"SYNTHETIC": true}', encoding="utf-8")
        before = {p.name: p.read_bytes() for p in d.iterdir()}
        rows = quality.score_all(str(self.root))
        self.assertEqual(quality.write_scores(rows), 1)
        after = {p.name: p.read_bytes() for p in d.iterdir()}
        self.assertEqual(set(after) - set(before), {"quality-score.json"})
        for name, blob in before.items():
            self.assertEqual(after[name], blob, f"{name} was modified")

    def test_the_written_record_is_valid_json_and_keeps_the_caveat(self):
        d = self.run_dir("w6-SYNTHETIC", "  | DETECTED D1-SYNTHETIC\n")
        quality.write_scores(quality.score_all(str(self.root)))
        doc = json.loads((d / "quality-score.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["schema"], "quality-score/v1")
        self.assertIn("EXPLORATORY SECONDARY", doc["status"])
        self.assertNotIn("run_dir", doc, "an absolute host path is not a result")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
