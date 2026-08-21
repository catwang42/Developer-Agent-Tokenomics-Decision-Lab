"""regrade-v2: both gates, a content-tagged image, and nothing overwritten.

Generation 1 re-ran the hidden gate and carried the public verdict over. Two
later defects broke that assumption — D1 put the grader's content in the image
tag (so a stale image can no longer answer for a fixed grader) and D2 changed a
PUBLIC check — so v2 re-runs both and reports each public check before and
after. These tests pin the three properties that make such a record trustworthy:
it refuses cells there is nothing to grade, it never overwrites an earlier
verdict, and it names the image that did the grading.

No test here launches a container. The docker-facing calls are substituted, and
one test asserts they are never reached at all.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness.runner import regrade  # noqa: E402


class _Task:
    task_id = "w6-hono-router-review"
    task_dir_rel = "tasks/suite/W6-pr-review"
    task_dir = str(ROOT / "tasks" / "suite" / "W6-pr-review")
    pinned_commit = "3feb3551d46d0000"
    gate_type = "pr_review"


class _RunDir(unittest.TestCase):
    """A run directory shaped like the archive's, complete unless asked otherwise."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.run_dir = os.path.join(
            self._tmp.name, "w6-hono-router-review__C2__rep1__20260820T210715")
        os.makedirs(self.run_dir)
        self.write("agent-solution.diff", "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n")
        self.write("events.jsonl", json.dumps({"event_type": "run_finished"}) + "\n")
        self.write_json("summary.json", {"acceptance": {"result": "rejected"}})
        self.write_json("gate-hidden.json", {"status": "fail", "hash": "sha256:aa",
                                             "version": "1"})
        self.write_json("gate-public.json", {"checks": [
            {"id": "P1-applies", "status": "pass"},
            {"id": "P5-no-leakage", "status": "fail"},
            {"id": "P6-diff-scope", "status": "fail"},
        ]})

    def write(self, name, text):
        with open(os.path.join(self.run_dir, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    def write_json(self, name, obj):
        self.write(name, json.dumps(obj))

    def summary(self):
        with open(os.path.join(self.run_dir, regrade.REGRADE_V2_SUMMARY),
                  encoding="utf-8") as fh:
            return json.load(fh)


class TheDeltaNamesEveryPublicCheck(unittest.TestCase):
    """"Report each public check before/after" — every check, in one of four buckets."""

    def test_a_check_that_started_failing_and_now_passes_is_cleared(self):
        d = regrade._check_delta({"P5": "fail"}, {"P5": "pass"})
        self.assertEqual(d["cleared"], ["P5"])
        self.assertEqual(d["still_failing"], [])
        self.assertEqual(d["newly_failing"], [])

    def test_a_check_that_fails_under_both_graders_is_a_genuine_failure(self):
        d = regrade._check_delta({"P5": "fail"}, {"P5": "fail"})
        self.assertEqual(d["still_failing"], ["P5"])
        self.assertEqual(d["cleared"], [])

    def test_a_check_the_fix_broke_is_reported_not_absorbed(self):
        d = regrade._check_delta({"P1": "pass"}, {"P1": "fail"})
        self.assertEqual(d["newly_failing"], ["P1"])

    def test_every_check_lands_in_exactly_one_bucket(self):
        before = {"a": "pass", "b": "fail", "c": "fail", "d": "pass"}
        after = {"a": "pass", "b": "pass", "c": "fail", "d": "fail"}
        d = regrade._check_delta(before, after)
        buckets = d["cleared"] + d["still_failing"] + d["newly_failing"] + d["unchanged_pass"]
        self.assertEqual(sorted(buckets), ["a", "b", "c", "d"])
        self.assertEqual(len(buckets), len(set(buckets)))

    def test_a_check_only_one_grader_ran_is_named_absent_not_dropped(self):
        d = regrade._check_delta({"old-only": "pass"}, {"new-only": "pass"})
        rows = {r["id"]: r for r in d["checks"]}
        self.assertEqual(rows["old-only"]["after"], "absent")
        self.assertEqual(rows["new-only"]["before"], "absent")

    def test_a_non_pass_status_that_is_not_fail_still_counts_as_not_passing(self):
        # `unavailable` is not a pass, and calling it one would launder a hole
        # into a green cell.
        d = regrade._check_delta({"P5": "unavailable"}, {"P5": "pass"})
        self.assertEqual(d["cleared"], ["P5"])


class ItRefusesWhatThereIsNothingToGrade(_RunDir):
    def _spy(self):
        """Substitute every docker-facing call so reaching one is a test failure."""
        boom = mock.Mock(side_effect=AssertionError("a container was launched"))
        return mock.patch.multiple(regrade, _apply_diff=boom, _gate_container=boom,
                                   create_volume=boom, remove_volume=boom)

    def test_a_timed_out_run_is_refused_and_says_so(self):
        self.write("events.jsonl", json.dumps(
            {"event_type": "failure", "category": "claude_timeout"}) + "\n")
        with self._spy():
            rec = regrade.regrade_run_v2(self.run_dir, _Task(), {})
        self.assertEqual(rec["status"], "refused")
        self.assertIn("claude_timeout", rec["reason"])
        self.assertIsNone(rec["amended"])

    def test_a_zero_byte_diff_is_refused(self):
        self.write("agent-solution.diff", "")
        with self._spy():
            rec = regrade.regrade_run_v2(self.run_dir, _Task(), {})
        self.assertEqual(rec["status"], "refused")
        self.assertIn("zero-byte", rec["reason"])

    def test_a_missing_diff_is_refused(self):
        os.unlink(os.path.join(self.run_dir, "agent-solution.diff"))
        with self._spy():
            rec = regrade.regrade_run_v2(self.run_dir, _Task(), {})
        self.assertEqual(rec["status"], "refused")

    def test_a_refusal_is_not_a_verdict(self):
        # The one thing a refused cell must never do is contribute a grade.
        self.write("agent-solution.diff", "")
        with self._spy():
            rec = regrade.regrade_run_v2(self.run_dir, _Task(), {})
        self.assertFalse(rec["changed"])
        self.assertEqual(self.summary()["status"], "refused")

    def test_the_refusal_keeps_the_original_verdict_visible(self):
        self.write("agent-solution.diff", "")
        with self._spy():
            rec = regrade.regrade_run_v2(self.run_dir, _Task(), {})
        self.assertEqual(rec["original"]["acceptance_result"], "rejected")


class ItNeverOverwritesAnEarlierVerdict(_RunDir):
    """Append-only, per CLAUDE.md rule 8: three generations must be able to coexist."""

    def test_an_existing_v2_record_is_left_alone(self):
        self.write_json(regrade.REGRADE_V2_SUMMARY, {"status": "graded", "mine": True})
        rec = regrade.regrade_run_v2(self.run_dir, _Task(), {})
        self.assertIn("_skipped", rec)
        self.assertTrue(self.summary()["mine"])

    def test_v2_writes_to_different_filenames_than_v1(self):
        names = {regrade.REGRADE_SUMMARY, regrade.REGRADE_LOG,
                 regrade.REGRADE_V2_SUMMARY, regrade.REGRADE_V2_PUBLIC_LOG,
                 regrade.REGRADE_V2_HIDDEN_LOG, regrade.REGRADE_V2_PUBLIC_REPORT,
                 regrade.REGRADE_V2_HIDDEN_REPORT}
        self.assertEqual(len(names), 7)

    def test_v2_does_not_touch_the_runs_own_gate_reports(self):
        self.write("agent-solution.diff", "")   # refused path: no containers
        original = open(os.path.join(self.run_dir, "gate-public.json"),
                        encoding="utf-8").read()
        regrade.regrade_run_v2(self.run_dir, _Task(), {})
        self.assertEqual(
            open(os.path.join(self.run_dir, "gate-public.json"), encoding="utf-8").read(),
            original)


class TheRecordNamesTheGraderThatMadeIt(_RunDir):
    """Condition (a) of the sweep: state the image tag; never a cached pre-fix one."""

    def test_ensure_images_tags_the_gate_image_with_the_gate_content(self):
        with mock.patch.object(regrade, "_ensure_image") as ensure, \
             mock.patch.object(regrade, "image_exists", return_value=False), \
             mock.patch.object(regrade, "agent_build_args", return_value={}):
            images = regrade.ensure_images(_Task(), {})
        digest = images["gate_content_digest"]
        self.assertRegex(digest, r"^[0-9a-f]{8}$")
        self.assertTrue(images["gate_image"].endswith("-" + digest))
        self.assertTrue(images["gate_image_built_now"])
        self.assertEqual(ensure.call_count, 2)   # gate and agent

    def test_an_image_that_was_already_present_is_not_reported_as_freshly_built(self):
        with mock.patch.object(regrade, "_ensure_image"), \
             mock.patch.object(regrade, "image_exists", return_value=True), \
             mock.patch.object(regrade, "agent_build_args", return_value={}):
            images = regrade.ensure_images(_Task(), {})
        self.assertFalse(images["gate_image_built_now"])
        self.assertFalse(images["agent_image_built_now"])

    def test_a_graded_record_carries_the_image_tags_and_both_gate_exit_codes(self):
        images = {"gate_image": "lab-subject/w6:pin-deadbeef",
                  "agent_image": "lab-subject-agent/w6:pin"}
        after = {"checks": [{"id": "P1-applies", "status": "pass"},
                            {"id": "P5-no-leakage", "status": "pass"},
                            {"id": "P6-diff-scope", "status": "pass"}]}

        def fake_gate(volume, tag, task, out_dir, script, env, name):
            with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
                json.dump(after if name == "gate-public.json"
                          else {"status": "fail", "hash": "sha256:aa", "version": "1"}, fh)
            return (0 if name == "gate-public.json" else 1), "out", ""

        with mock.patch.object(regrade, "create_volume"), \
             mock.patch.object(regrade, "remove_volume"), \
             mock.patch.object(regrade, "_apply_diff", return_value=(0, "", "")), \
             mock.patch.object(regrade, "_gate_container", side_effect=fake_gate):
            rec = regrade.regrade_run_v2(self.run_dir, _Task(), images)

        self.assertEqual(rec["status"], "graded")
        self.assertEqual(rec["method"]["images"]["gate_image"], images["gate_image"])
        self.assertEqual(rec["method"]["gates_re_run"], ["public", "hidden"])
        self.assertEqual(rec["method"]["model_spend"], "none")
        self.assertEqual(rec["amended"]["public_exit_code"], 0)
        self.assertEqual(rec["amended"]["gate_exit_code"], 1)
        # public passes, hidden fails -> rejected, and the two cleared public
        # checks are named even though the verdict did not move.
        self.assertEqual(rec["amended"]["acceptance_result"], "rejected")
        self.assertEqual(sorted(rec["public_check_delta"]["cleared"]),
                         ["P5-no-leakage", "P6-diff-scope"])
        self.assertFalse(rec["changed"])

    def test_a_verdict_that_moves_is_marked_changed(self):
        def fake_gate(volume, tag, task, out_dir, script, env, name):
            body = ({"checks": [{"id": "P5-no-leakage", "status": "pass"}]}
                    if name == "gate-public.json"
                    else {"status": "pass", "hash": "sha256:aa", "version": "1"})
            with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
                json.dump(body, fh)
            return 0, "out", ""

        with mock.patch.object(regrade, "create_volume"), \
             mock.patch.object(regrade, "remove_volume"), \
             mock.patch.object(regrade, "_apply_diff", return_value=(0, "", "")), \
             mock.patch.object(regrade, "_gate_container", side_effect=fake_gate):
            rec = regrade.regrade_run_v2(self.run_dir, _Task(), {"gate_image": "g",
                                                                 "agent_image": "a"})
        self.assertEqual(rec["amended"]["acceptance_result"], "accepted")
        self.assertTrue(rec["changed"])

    def test_a_sealed_set_that_moved_makes_the_record_say_so(self):
        def fake_gate(volume, tag, task, out_dir, script, env, name):
            body = ({"checks": [{"id": "P1", "status": "pass"}]}
                    if name == "gate-public.json"
                    else {"status": "fail", "hash": "sha256:DIFFERENT", "version": "2"})
            with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
                json.dump(body, fh)
            return 0 if name == "gate-public.json" else 1, "", ""

        with mock.patch.object(regrade, "create_volume"), \
             mock.patch.object(regrade, "remove_volume"), \
             mock.patch.object(regrade, "_apply_diff", return_value=(0, "", "")), \
             mock.patch.object(regrade, "_gate_container", side_effect=fake_gate):
            rec = regrade.regrade_run_v2(self.run_dir, _Task(), {"gate_image": "g",
                                                                 "agent_image": "a"})
        self.assertIn("NOT a like-for-like correction", rec["sealed_set_changed"])

    def test_a_diff_that_will_not_apply_is_refused_with_the_reason(self):
        with mock.patch.object(regrade, "create_volume"), \
             mock.patch.object(regrade, "remove_volume"), \
             mock.patch.object(regrade, "_apply_diff",
                               return_value=(1, "", "error: patch does not apply")), \
             mock.patch.object(regrade, "_gate_container") as gate:
            rec = regrade.regrade_run_v2(self.run_dir, _Task(), {"gate_image": "g",
                                                                 "agent_image": "a"})
        self.assertEqual(rec["status"], "refused")
        self.assertIn("patch does not apply", rec["reason"])
        gate.assert_not_called()


class TheV1PathIsUnchanged(unittest.TestCase):
    """v2 is added beside v1, not on top of it: v1's contract must still hold."""

    def test_v1_still_declares_generation_one(self):
        self.assertEqual(regrade.REGRADE_VERSION, "1")
        self.assertEqual(regrade.REGRADE_V2_VERSION, "2")

    def test_v1_still_carries_the_public_gate_over_rather_than_re_running_it(self):
        src = (ROOT / "harness" / "runner" / "regrade.py").read_text(encoding="utf-8")
        _, _, tail = src.partition("def regrade_run(")
        body = tail.split("\ndef ")[0]
        self.assertIn("_public_rc", body)
        self.assertNotIn("check-public.sh", body)


if __name__ == "__main__":
    unittest.main()
