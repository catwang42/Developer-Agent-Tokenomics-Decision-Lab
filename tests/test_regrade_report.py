"""The regrade-v2 report must not claim credit for flips the v1 pass found.

Every fixture here is SYNTHETIC and lives only in a temp directory.
"""

import json
import os
import shutil
import tempfile
import unittest

from harness.analysis import regrade_report as R


def _write(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)


def _v2(run_id, *, original, amended, cleared=(), still=(), newly=(), unchanged=(),
        status="graded", hidden_before="fail", hidden_after="pass"):
    return {
        "run_id": run_id,
        "task_id": run_id.split("__")[0],
        "status": status,
        "regrade_version": "2",
        "original": {"acceptance_result": original, "hidden_status": hidden_before},
        "amended": {"acceptance_result": amended, "hidden_status": hidden_after},
        "public_check_delta": {
            "cleared": list(cleared), "still_failing": list(still),
            "newly_failing": list(newly), "unchanged_pass": list(unchanged),
        },
        "method": {"images": {"gate_image": "lab-subject/SYNTHETIC:abc-def",
                              "gate_content_digest": "def",
                              "gate_image_built_now": True}},
    }


class TheLadderNamesWhoFoundWhat(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="SYNTHETIC-regrade-report-")
        self.ds = os.path.join(self.root, "screening-batch1")
        self.addCleanup(shutil.rmtree, self.root, True)

    def _run(self, run_id, v2, v1=None):
        run_dir = os.path.join(self.ds, run_id)
        _write(os.path.join(run_dir, "summary.json"), {})
        _write(os.path.join(run_dir, R.V2_SUMMARY), v2)
        if v1 is not None:
            _write(os.path.join(run_dir, R.V1_SUMMARY), v1)
        return run_dir

    def test_a_flip_the_v1_pass_already_found_is_not_credited_to_this_pass(self):
        self._run(
            "w1__P0__rep1__T",
            _v2("w1__P0__rep1__T", original="rejected", amended="accepted"),
            v1={"original": {"acceptance_result": "rejected"},
                "amended": {"acceptance_result": "accepted"}},
        )
        counts = R.tally(R.scan(self.root, ["screening-batch1"]))
        self.assertEqual(counts["changed_by_this_pass"], 0)
        self.assertEqual(counts["changed_vs_original"], 1)
        self.assertEqual(counts["already_found_by_v1"], 1)

    def test_a_flip_with_no_v1_regrade_is_credited_to_this_pass(self):
        self._run("w6__C2__rep1__T",
                  _v2("w6__C2__rep1__T", original="rejected", amended="accepted"))
        counts = R.tally(R.scan(self.root, ["screening-batch1"]))
        self.assertEqual(counts["changed_by_this_pass"], 1)
        self.assertEqual(counts["already_found_by_v1"], 0)

    def test_this_pass_reversing_a_v1_amendment_counts_as_a_change(self):
        self._run(
            "w4__P1__rep2__T",
            _v2("w4__P1__rep2__T", original="rejected", amended="rejected",
                hidden_after="fail"),
            v1={"original": {"acceptance_result": "rejected"},
                "amended": {"acceptance_result": "accepted"}},
        )
        counts = R.tally(R.scan(self.root, ["screening-batch1"]))
        self.assertEqual(counts["changed_by_this_pass"], 1)
        self.assertEqual(counts["changed_vs_original"], 0)

    def test_a_refused_truncated_run_is_counted_but_never_graded(self):
        self._run("w3__C5__rep1__T",
                  dict(_v2("w3__C5__rep1__T", original="rejected", amended=None,
                           status="refused"), reason="run truncated"))
        counts = R.tally(R.scan(self.root, ["screening-batch1"]))
        self.assertEqual(counts["refused_truncated"], 1)
        self.assertEqual(counts["graded"], 0)
        self.assertEqual(counts["changed_by_this_pass"], 0)


class ItNamesWhatItDidNotCover(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="SYNTHETIC-regrade-report-")
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_a_run_the_sweep_never_reached_is_listed_not_dropped(self):
        run_dir = os.path.join(self.root, "screening-batch1", "w7__P0__rep1__T")
        _write(os.path.join(run_dir, "summary.json"), {})
        scanned = R.scan(self.root, ["screening-batch1"])
        self.assertEqual(scanned["cells"], [])
        self.assertEqual(scanned["not_regraded"],
                         [{"dataset": "screening-batch1", "run_id": "w7__P0__rep1__T"}])
        self.assertEqual(R.tally(scanned)["runs_in_scope"], 1)

    def test_a_directory_that_is_not_a_run_is_ignored_entirely(self):
        os.makedirs(os.path.join(self.root, "screening-batch1", ".regrade-v2-out"))
        scanned = R.scan(self.root, ["screening-batch1"])
        self.assertEqual(scanned["cells"], [])
        self.assertEqual(scanned["not_regraded"], [])


class TheProseSeparatesArtifactsFromFailures(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="SYNTHETIC-regrade-report-")
        self.addCleanup(shutil.rmtree, self.root, True)
        run_dir = os.path.join(self.root, "screening-batch1", "w6__C2__rep1__T")
        _write(os.path.join(run_dir, "summary.json"), {})
        _write(os.path.join(run_dir, R.V2_SUMMARY),
               _v2("w6__C2__rep1__T", original="rejected", amended="rejected",
                   cleared=["P5-no-leakage"], still=["P2-findings-present"],
                   hidden_after="fail"))
        self.scanned = R.scan(self.root, ["screening-batch1"])

    def test_a_cleared_check_is_called_an_artifact_and_a_failing_one_is_not(self):
        md = R.render(self.scanned, R.tally(self.scanned),
                      generated_at="SYNTHETIC", harness_head="SYNTHETIC")
        self.assertIn("artifact flip, public: P5-no-leakage", md)
        self.assertIn("genuine failure, public: P2-findings-present", md)

    def test_a_regression_is_shouted_not_buried(self):
        self.scanned["cells"][0]["public_newly_failing"] = ["P9-something"]
        md = R.render(self.scanned, R.tally(self.scanned),
                      generated_at="SYNTHETIC", harness_head="SYNTHETIC")
        self.assertIn("REGRESSION, public: P9-something", md)


if __name__ == "__main__":
    unittest.main()
