"""The inventory has one job it must not get wrong: naming truncated runs.

A run the harness killed is not evidence about a model. If the inventory misses
one, the final table reports a `rejected` that the wall clock caused; if it
invents one, a real rejection gets excused and re-run at cost. Both are wrong in
the direction that matters, so the truncation signals get a test each.

Every fixture here is SYNTHETIC and built under tmp. Nothing reads results/.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import tempfile
import unittest

from harness.analysis import archive


class _Archive(unittest.TestCase):
    """A SYNTHETIC results/ tree, one run directory at a time."""

    def setUp(self) -> None:
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="archive-SYNTHETIC-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def run_dir(self, dataset: str, task: str, config: str, rep: int,
                stamp: str = "20260819T000000", *, diff: str = "--- a\n+++ b\n",
                events: list | None = None, acceptance: str = "rejected",
                hidden: str = "fail", public: list | None = None,
                summary_extra: dict | None = None) -> pathlib.Path:
        d = self.root / dataset / f"{task}__{config}__rep{rep}__{stamp}"
        d.mkdir(parents=True)
        if diff is not None:
            (d / "agent-solution.diff").write_text(diff, encoding="utf-8")
        (d / "events.jsonl").write_text(
            "".join(json.dumps(e) + "\n" for e in (events or [])), encoding="utf-8")
        (d / "gate-hidden.json").write_text(json.dumps(
            {"gate": "hidden", "status": hidden, "hash": "sha256:SYNTHETIC",
             "version": "SYNTHETIC-v1"}), encoding="utf-8")
        (d / "gate-public.json").write_text(json.dumps(
            {"gate": "public", "checks": public if public is not None
             else [{"id": "P1-public-test", "status": "pass", "detail": ""}]}),
            encoding="utf-8")
        summary = {"acceptance": {"result": acceptance}, "behavior": {}}
        summary.update(summary_extra or {})
        (d / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        (d / "result.json").write_text(json.dumps(
            {"acceptance": {"result": acceptance},
             "identity": {"product": {"value": "Product A"},
                          "model_or_selector": {"value": "STRONG_MODEL_A"}}}),
            encoding="utf-8")
        return d


class ItReadsWhatARunIs(_Archive):
    def test_it_parses_the_run_directory_name(self):
        got = archive.parse_run_dir_name("w3-some-task__C3-med__rep2__20260819T061257")
        self.assertEqual(got, {"task_id": "w3-some-task", "configuration_id": "C3-med",
                               "rep": 2, "started_utc": "20260819T061257"})

    def test_a_task_id_containing_underscores_still_parses(self):
        got = archive.parse_run_dir_name("a_b_c__P0__rep1__20260819T061257")
        self.assertEqual(got["task_id"], "a_b_c")
        self.assertEqual(got["configuration_id"], "P0")

    def test_a_non_run_directory_is_not_a_run(self):
        for name in ("collector-plan.json", "batch1.log", "HALT", "MAKEUP-BATCH.json"):
            self.assertIsNone(archive.parse_run_dir_name(name), name)

    def test_it_picks_up_the_public_checks_and_the_sealed_verdict(self):
        d = self.run_dir("ds", "w6-SYNTHETIC", "C3", 1, hidden="pass",
                         public=[{"id": "P5-no-leakage", "status": "fail",
                                  "detail": "SYNTHETIC"},
                                 {"id": "P1-public-test", "status": "pass",
                                  "detail": ""}])
        row = archive.read_run(str(d), "ds")
        self.assertEqual(row["public_checks"],
                         {"P5-no-leakage": "fail", "P1-public-test": "pass"})
        self.assertEqual(row["hidden"]["status"], "pass")
        self.assertEqual(row["cell"], "w6-SYNTHETIC::C3")

    def test_non_run_entries_are_skipped_by_the_scan(self):
        self.run_dir("ds", "w1-SYNTHETIC", "P0", 1)
        (self.root / "ds" / "collector-plan.json").write_text("{}", encoding="utf-8")
        (self.root / "ds" / "batch.log").write_text("SYNTHETIC", encoding="utf-8")
        self.assertEqual(len(archive.scan(str(self.root))), 1)


class ItNamesTruncation(_Archive):
    TIMEOUT = {"event_type": "failure", "category": "claude_timeout", "leg": "main",
               "timeout_s": 1800, "container_disposition": "killed"}

    def test_a_complete_run_is_not_truncated(self):
        d = self.run_dir("ds", "w3-SYNTHETIC", "C3", 1)
        self.assertIsNone(archive.truncation(str(d)))

    def test_a_timeout_event_truncates_even_with_a_large_diff(self):
        # THE ONE THAT NEARLY GOT MISSED. W3 runs were killed at the wall clock
        # after writing 60-70 KB of partial work. Sizeable output is not evidence
        # that the agent finished.
        d = self.run_dir("ds", "w3-SYNTHETIC", "C5", 1, diff="x" * 70000,
                         events=[self.TIMEOUT])
        self.assertEqual(archive.truncation(str(d)), "stop_reason=claude_timeout")

    def test_a_zero_byte_diff_truncates(self):
        d = self.run_dir("ds", "w6-SYNTHETIC", "C2", 2, diff="")
        self.assertEqual(archive.truncation(str(d)), "zero-byte agent-solution.diff")

    def test_an_absent_diff_truncates(self):
        d = self.run_dir("ds", "w6-SYNTHETIC", "C2", 2, diff=None)
        self.assertEqual(archive.truncation(str(d)), "no agent-solution.diff archived")

    def test_the_rolled_up_failure_category_also_truncates(self):
        # Some runs carry the category only in the summary's rollup.
        d = self.run_dir("ds", "w3-SYNTHETIC", "P1", 3, diff="x" * 1000,
                         summary_extra={"behavior": {"failures_by_category": {
                             "value": {"claude_timeout": 1}}}})
        self.assertEqual(archive.truncation(str(d)), "stop_reason=claude_timeout")

    def test_an_unrelated_failure_event_does_not_truncate(self):
        d = self.run_dir("ds", "w3-SYNTHETIC", "C3", 1, events=[
            {"event_type": "failure", "category": "typecheck_error", "leg": "main"}])
        self.assertIsNone(archive.truncation(str(d)))

    def test_a_zero_count_in_the_rollup_does_not_truncate(self):
        d = self.run_dir("ds", "w3-SYNTHETIC", "C3", 1, summary_extra={
            "behavior": {"failures_by_category": {"value": {"claude_timeout": 0}}}})
        self.assertIsNone(archive.truncation(str(d)))

    def test_a_corrupt_event_line_does_not_hide_a_later_timeout(self):
        d = self.run_dir("ds", "w3-SYNTHETIC", "C3", 1, diff="x" * 100)
        (d / "events.jsonl").write_text(
            "{not json\n" + json.dumps(self.TIMEOUT) + "\n", encoding="utf-8")
        self.assertEqual(archive.truncation(str(d)), "stop_reason=claude_timeout")


class ItKnowsWhatStillNeedsMakeup(_Archive):
    TIMEOUT = ItNamesTruncation.TIMEOUT

    def test_a_lost_rep_is_enumerated(self):
        self.run_dir("screening-batch1", "w3-SYNTHETIC", "C5", 1, diff="x" * 900,
                     events=[self.TIMEOUT])
        out = archive.needs_makeup(archive.scan(str(self.root)))
        self.assertEqual([(r["task_id"], r["rep"]) for r in out],
                         [("w3-SYNTHETIC", 1)])

    def test_a_later_complete_run_of_the_same_rep_supersedes_it(self):
        self.run_dir("screening-batch1", "w3-SYNTHETIC", "C5", 1, "20260819T000000",
                     diff="x" * 900, events=[self.TIMEOUT])
        self.run_dir("screening-batch1-makeup", "w3-SYNTHETIC", "C5", 1,
                     "20260820T000000")
        self.assertEqual(archive.needs_makeup(archive.scan(str(self.root))), [])

    def test_a_surviving_SIBLING_rep_does_not_supersede_it(self):
        # Reps are samples, not retries. Two of three surviving is a cell with a
        # missing sample; reporting a median over two where three were
        # pre-registered would change the design without saying so.
        self.run_dir("screening-batch1", "w3-SYNTHETIC", "C5", 1, diff="x" * 900,
                     events=[self.TIMEOUT])
        self.run_dir("screening-batch1", "w3-SYNTHETIC", "C5", 2)
        self.run_dir("screening-batch1", "w3-SYNTHETIC", "C5", 3)
        out = archive.needs_makeup(archive.scan(str(self.root)))
        self.assertEqual([r["rep"] for r in out], [1])

    def test_a_makeup_run_that_timed_out_AGAIN_stays_enumerated(self):
        self.run_dir("screening-batch1", "w3-SYNTHETIC", "P0", 1, "20260819T000000",
                     diff="x" * 900, events=[self.TIMEOUT])
        self.run_dir("screening-batch1-makeup", "w3-SYNTHETIC", "P0", 1,
                     "20260820T000000", diff="x" * 900, events=[self.TIMEOUT])
        out = archive.needs_makeup(archive.scan(str(self.root)))
        self.assertEqual(len(out), 2, "both attempts are lost samples")

    def test_a_smoke_run_neither_counts_nor_supersedes(self):
        self.run_dir("smoke-screening", "w3-SYNTHETIC", "C5", 1, "20260820T000000")
        self.run_dir("screening-batch1", "w3-SYNTHETIC", "C5", 1, "20260819T000000",
                     diff="x" * 900, events=[self.TIMEOUT])
        out = archive.needs_makeup(archive.scan(str(self.root)))
        self.assertEqual([r["dataset"] for r in out], ["screening-batch1"])

    def test_a_truncated_smoke_run_is_not_enumerated(self):
        self.run_dir("smoke", "w3-SYNTHETIC", "C5", 1, diff="")
        self.assertEqual(archive.needs_makeup(archive.scan(str(self.root))), [])

    def test_the_halted_batch_is_not_evidence(self):
        self.assertFalse(archive.is_evidence("screening-batch1-aborted-20260817-gatefix"))
        self.assertTrue(archive.is_evidence("screening-batch1"))
        self.assertTrue(archive.is_evidence("screening-batch1-makeup-w6"))


class ItDoesNotTouchSealedMaterial(_Archive):
    def test_the_scan_opens_nothing_named_hidden(self):
        d = self.run_dir("ds", "w6-SYNTHETIC", "C3", 1)
        opened = []
        real_open = open

        def spy(path, *a, **k):
            opened.append(str(path))
            return real_open(path, *a, **k)

        import builtins
        builtins.open = spy
        try:
            archive.read_run(str(d), "ds")
        finally:
            builtins.open = real_open
        self.assertTrue(opened)
        self.assertFalse([p for p in opened if f"{os.sep}hidden{os.sep}" in p], opened)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
