"""Delivery of the artifact a review task reviews (gate_type: pr_review).

THE DEFECT, from screening batch 1. `tasks/suite/W6-pr-review/task.yaml` declared
`review_diff: hidden/review-diff.patch`, and nothing in the harness ever read that
field. The agents were handed a bare pinned hono checkout and a prompt beginning
"Review the following diff" with no diff following it, and no file to write their
findings to. All 15 W6 cells landed a 0-byte `agent-solution.diff` and were voided
as unscoreable. Nothing failed; the batch simply measured silence for a whole
workload class.

Two things had to be true for a review run to mean anything, and neither was:

  1. the artifact under review is IN the subject tree the agent works in, and
  2. the agent is told its name, and the name of the report the gate reads.

A third fell out of fixing the first two: the public gate judges the changed-path
set against `target_paths`, so a review report at the subject root read as an
unexpected change and would have failed P6 on every makeup run — a clean sweep of
rejections that the sealed matcher's verdict could never have overturned
(`_gate_verdict` rejects when either gate fails).

And a hazard that had to be closed at the same time: `_archive_agent_diff` archives
the FULL CONTENT of every untracked file, and that archive is committed under
`results/`. Delivering the SEALED seeded diff without hiding it from git would
publish it next to the committed `review/base-diff.patch` — a two-way diff of the
two recovers the defect map, which is the same as publishing the map.

Hermetic: a throwaway task dir, a local git repo standing in for the pinned clone,
and a SYNTHETIC stand-in for the sealed diff. The real `tasks/*/hidden/` is never
read, and no container is launched (the container path is asserted through a
recording stand-in for the executor).
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.runner import run as runner  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
W6_TASK_YAML = ROOT / "tasks" / "suite" / "W6-pr-review" / "task.yaml"
CHECK_PUBLIC = ROOT / "harness" / "task-tools" / "gate" / "check-public.sh"
LIB = ROOT / "harness" / "task-tools" / "lib.sh"

#: Stands in for the sealed seeded diff. Labelled SYNTHETIC in its own bytes so a
#: leak into any artifact is unmistakable, and distinctive enough to grep for.
SYNTHETIC_REVIEW_DIFF = (
    "SYNTHETIC-SEALED-REVIEW-DIFF — not the real W6 seeded diff, not sealed\n"
    "--- a/src/router/reg-exp-router/node.ts\n"
    "+++ b/src/router/reg-exp-router/node.ts\n"
    "@@ -1 +1 @@\n"
    "-const SYNTHETIC = 0\n"
    "+const SYNTHETIC = 1\n"
)
LEAK_MARKER = "SYNTHETIC-SEALED-REVIEW-DIFF"

TARGET_PATHS = ["src/router/reg-exp-router/node.ts",
                "src/router/reg-exp-router/router.ts"]

TASK_YAML = """\
# SYNTHETIC task definition (tests/fixtures scope) — not a registered task, never
# run as a benchmark subject. Exists only to drive the review-delivery path.
task_id: synthetic-review-delivery-SYNTHETIC
manifest_key: synthetic_task_SYNTHETIC
task_suite_version: SYNTHETIC-v0
class: code_review
gate_type: {gate_type}
stack: none
repo: SYNTHETIC://no-such-repo
license: MIT
contamination_tier: SYNTHETIC
{review_diff}
review_report: review-report.txt
target_paths:
{target_paths}
tests_dir: src/router/reg-exp-router
prompt: |
  SYNTHETIC review prompt. Read review-diff.patch, write review-report.txt.
pass_condition: >
  SYNTHETIC: recalls the seeded defects with no fabrications.
task_phase: screening
configurations: [P0]
companion_configurations: []
reps_screening: 1
"""


def _git(repo: pathlib.Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


class ReviewDeliveryHarness(unittest.TestCase):
    """A throwaway review task plus a local git repo as the subject tree."""

    def _task(self, *, gate_type: str = "pr_review",
              review_diff: str = "hidden/review-diff.patch",
              artifact_bytes: str = SYNTHETIC_REVIEW_DIFF,
              write_artifact: bool = True):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="w6delivery-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)

        task_dir = tmp / "task"
        task_dir.mkdir()
        decl = f"review_diff: {review_diff}" if review_diff else ""
        (task_dir / "task.yaml").write_text(
            TASK_YAML.format(
                gate_type=gate_type, review_diff=decl,
                target_paths="\n".join(f"  - {p}" for p in TARGET_PATHS)),
            encoding="utf-8")

        # The sealed dir is a throwaway under tmp, reached the way the gates reach
        # it (HIDDEN_TESTS_DIR). tasks/*/hidden is never touched by these tests.
        hidden = tmp / "hidden"
        hidden.mkdir()
        if write_artifact and review_diff:
            (hidden / os.path.basename(review_diff)).write_text(
                artifact_bytes, encoding="utf-8")
        os.environ["HIDDEN_TESTS_DIR"] = str(hidden)
        self.addCleanup(os.environ.pop, "HIDDEN_TESTS_DIR", None)

        task = runner.load_task(str(task_dir), {})
        return tmp, task

    def _subject(self, tmp: pathlib.Path) -> pathlib.Path:
        subject = tmp / "work" / "repo"
        subject.mkdir(parents=True)
        _git(subject, "init", "--quiet")
        _git(subject, "config", "user.email", "synthetic@example.invalid")
        _git(subject, "config", "user.name", "SYNTHETIC")
        for rel in TARGET_PATHS:
            path = subject / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("// SYNTHETIC subject file\n", encoding="utf-8")
        _git(subject, "add", "-A")
        _git(subject, "commit", "--quiet", "-m", "SYNTHETIC pinned commit")
        return subject


class TheArtifactReachesTheStagedTree(ReviewDeliveryHarness):
    """THE regression test: batch 1's staged tree had no artifact in it."""

    def test_it_is_present_and_non_empty_in_the_staged_tree(self):
        tmp, task = self._task()
        subject = self._subject(tmp)
        runner.stage_review_artifact(str(subject), task)
        delivered = subject / "review-diff.patch"
        self.assertTrue(delivered.is_file(),
                        "the agent's working tree has no artifact to review")
        self.assertGreater(delivered.stat().st_size, 0,
                           "the artifact was delivered empty, which scores as silence")

    def test_the_delivered_bytes_are_the_source_bytes(self):
        # A truncating or re-encoding copy would be a quieter version of the same
        # defect: an artifact that is present but not the one the map was built on.
        tmp, task = self._task()
        subject = self._subject(tmp)
        runner.stage_review_artifact(str(subject), task)
        self.assertEqual(SYNTHETIC_REVIEW_DIFF,
                         (subject / "review-diff.patch").read_text(encoding="utf-8"))

    def test_delivering_twice_leaves_one_exclude_line(self):
        tmp, task = self._task()
        subject = self._subject(tmp)
        runner.stage_review_artifact(str(subject), task)
        runner.stage_review_artifact(str(subject), task)
        exclude = (subject / ".git" / "info" / "exclude").read_text(encoding="utf-8")
        self.assertEqual(1, exclude.count("review-diff.patch"), exclude)


class TheSealedBytesDoNotReachResults(ReviewDeliveryHarness):
    """The delivered artifact is SEALED; `agent-solution.diff` is committed."""

    def test_the_archived_agent_diff_carries_the_report_but_not_the_diff(self):
        tmp, task = self._task()
        subject = self._subject(tmp)
        runner.stage_review_artifact(str(subject), task)
        # What the agent produces, and must be archived:
        (subject / "review-report.txt").write_text(
            "src/router/reg-exp-router/node.ts:12 — SYNTHETIC finding\n",
            encoding="utf-8")

        run_dir = tmp / "run"
        run_dir.mkdir()
        runner._archive_agent_diff(str(subject), str(run_dir))
        archived = (run_dir / "agent-solution.diff").read_text(encoding="utf-8")

        self.assertIn("SYNTHETIC finding", archived,
                      "the agent's report is the evidence; it must be archived")
        self.assertNotIn(LEAK_MARKER, archived,
                         "the SEALED artifact leaked into a committed run artifact")

    def test_git_does_not_see_the_delivered_artifact_at_all(self):
        # The mechanism, asserted directly: both archivers and the public gate ask
        # git with --exclude-standard, so one exclude line covers all of them.
        tmp, task = self._task()
        subject = self._subject(tmp)
        runner.stage_review_artifact(str(subject), task)
        others = _git(subject, "ls-files", "--others", "--exclude-standard")
        self.assertNotIn("review-diff.patch", others, others)


class AMissingArtifactStopsTheRun(ReviewDeliveryHarness):
    """Fail closed. Batch 1's cost was 15 runs that scored silence."""

    def test_an_absent_sealed_artifact_is_refused(self):
        tmp, task = self._task(write_artifact=False)
        subject = self._subject(tmp)
        with self.assertRaises(runner.RunnerError) as ctx:
            runner.stage_review_artifact(str(subject), task)
        self.assertIn("review-diff.patch", str(ctx.exception))

    def test_an_empty_sealed_artifact_is_refused(self):
        tmp, task = self._task(artifact_bytes="")
        subject = self._subject(tmp)
        with self.assertRaises(runner.RunnerError):
            runner.stage_review_artifact(str(subject), task)

    def test_a_review_task_declaring_no_artifact_is_refused(self):
        tmp, task = self._task(review_diff="")
        subject = self._subject(tmp)
        with self.assertRaises(runner.RunnerError) as ctx:
            runner.stage_review_artifact(str(subject), task)
        self.assertIn("review_diff", str(ctx.exception))


class TheContainerPathDeliversTheSameWay(ReviewDeliveryHarness):
    """Container mode seeds the per-run volume before the agent's first mount."""

    def _seed(self, returncode: int = 0):
        captured = {}

        class Result:
            def __init__(self, rc):
                self.returncode = rc
                self.stdout = ""
                self.stderr = "SYNTHETIC seed failure" if rc else ""

        class Recorder:
            def __init__(self, image, subject_root="/subject"):
                captured["image"] = image
                captured["subject_root"] = subject_root

            def run(self, cmd, **kw):
                captured["cmd"] = cmd
                captured["kw"] = kw
                return Result(returncode)

        real = runner.ContainerExecutor
        runner.ContainerExecutor = Recorder
        self.addCleanup(setattr, runner, "ContainerExecutor", real)
        return captured

    def test_the_volume_and_the_sealed_source_are_both_mounted(self):
        tmp, task = self._task()
        captured = self._seed()
        runner.stage_review_artifact_container(
            "lab-subject-agent/synthetic:SYNTHETIC", "lab-subject-work-SYNTHETIC", task)

        mounts = dict((dst, (src, mode)) for src, dst, mode in captured["kw"]["mounts"])
        self.assertEqual(("lab-subject-work-SYNTHETIC", "rw"), mounts["/subject"])
        src, mode = mounts[runner.CONTAINER_REVIEW_SRC]
        self.assertEqual("ro", mode, "the sealed source is mounted read-only")
        self.assertTrue(src.endswith("review-diff.patch"), src)
        self.assertEqual("none", captured["kw"]["network"],
                         "seeding must not reach the network")

    def test_both_postures_run_the_same_script(self):
        # Host and container delivery share one script on purpose: two copies drift,
        # and a drift here is invisible until a batch comes back empty.
        tmp, task = self._task()
        captured = self._seed()
        runner.stage_review_artifact_container("img", "vol", task)
        self.assertEqual(["bash", "-c", runner.REVIEW_SEED_SCRIPT], captured["cmd"])

    def test_a_failed_seed_stops_the_run(self):
        tmp, task = self._task()
        self._seed(returncode=1)
        with self.assertRaises(runner.RunnerError) as ctx:
            runner.stage_review_artifact_container("img", "vol", task)
        self.assertIn("SYNTHETIC seed failure", str(ctx.exception))

    def test_a_missing_artifact_is_refused_before_any_container_starts(self):
        tmp, task = self._task(write_artifact=False)
        captured = self._seed()
        with self.assertRaises(runner.RunnerError):
            runner.stage_review_artifact_container("img", "vol", task)
        self.assertNotIn("cmd", captured, "a container was launched for a run that "
                                          "cannot produce a reviewable result")


class OnlyReviewTasksAreTouched(ReviewDeliveryHarness):
    def test_a_solution_task_is_not_a_review_task(self):
        _, task = self._task(gate_type="solution")
        self.assertFalse(runner.is_review_task(task))

    def test_a_review_task_is(self):
        _, task = self._task()
        self.assertTrue(runner.is_review_task(task))

    def test_a_hidden_relative_declaration_follows_the_gates_sealed_dir(self):
        # Same rule as hidden_tests_dir(): the sealed set moves as one thing.
        tmp, task = self._task()
        self.assertEqual(str(tmp / "hidden" / "review-diff.patch"),
                         runner.review_artifact_source(task))


class TheNamesAgreeWithTheRealTask(unittest.TestCase):
    """The prompt, the delivered name and the graded name are one set of names."""

    @staticmethod
    def _w6():
        import yaml
        with open(W6_TASK_YAML, encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    def test_the_w6_prompt_names_the_file_the_harness_delivers(self):
        ty = self._w6()
        task = runner.Task(task_dir=str(W6_TASK_YAML.parent), task_id=ty["task_id"],
                           task_suite_version="", prompt=ty["prompt"],
                           contamination_tier=None, hidden_test_hash=None,
                           gate_type=ty["gate_type"], task_yaml=ty)
        self.assertIn(runner.review_artifact_name(task), task.prompt,
                      "the agent is not told what to read")

    def test_the_w6_prompt_names_the_file_the_gate_reads(self):
        # validate.sh and the sealed matcher both resolve `review_report`. A prompt
        # that names a different file is batch 1 again: work done, nowhere to put it.
        ty = self._w6()
        task = runner.Task(task_dir=str(W6_TASK_YAML.parent), task_id=ty["task_id"],
                           task_suite_version="", prompt=ty["prompt"],
                           contamination_tier=None, hidden_test_hash=None,
                           gate_type=ty["gate_type"], task_yaml=ty)
        self.assertIn(runner.review_report_name(task), task.prompt,
                      "the agent is not told where to write")

    def test_w6_still_declares_a_sealed_artifact_to_deliver(self):
        self.assertEqual("hidden/review-diff.patch", self._w6()["review_diff"])


class ThePublicGateExpectsTheReviewFiles(ReviewDeliveryHarness):
    """P6 diff-scope: the report is the deliverable, not an unexpected change."""

    def _p6(self, subject: pathlib.Path, task_dir: pathlib.Path, tmp: pathlib.Path):
        env = {**os.environ, "TASK_DIR": str(task_dir),
               "TASK_WORKDIR": str(tmp / "work")}
        proc = subprocess.run(["bash", str(CHECK_PUBLIC)],
                              capture_output=True, text=True, env=env)
        line = [ln for ln in proc.stdout.splitlines() if "P6-diff-scope" in ln]
        self.assertTrue(line, proc.stdout + proc.stderr)
        return line[0]

    def test_a_delivered_diff_and_a_written_report_pass_diff_scope(self):
        tmp, task = self._task()
        subject = self._subject(tmp)
        runner.stage_review_artifact(str(subject), task)
        (subject / "review-report.txt").write_text(
            "src/router/reg-exp-router/node.ts:12 — SYNTHETIC finding\n",
            encoding="utf-8")
        self.assertIn("[pass]", self._p6(subject, tmp / "task", tmp))

    def test_an_unrelated_new_file_still_fails_diff_scope(self):
        # The allowance is two named files, not an amnesty: a review run that
        # rewrites the repo must still be caught.
        tmp, task = self._task()
        subject = self._subject(tmp)
        runner.stage_review_artifact(str(subject), task)
        (subject / "SYNTHETIC-stray.txt").write_text("x\n", encoding="utf-8")
        self.assertIn("[fail]", self._p6(subject, tmp / "task", tmp))


class TheLeakScanToleratesTheArtifactTheHarnessDelivers(ReviewDeliveryHarness):
    """P5 no-leakage vs the delivered review diff.

    THE SECOND SWEEP. Fixing P6 was not enough: `leak_found` fails any subject
    tree containing a `*.patch` anywhere, and delivery puts one there by design.
    So the W6 makeup pass of 2026-08-20 was rejected 15 times out of 15 — this
    time for the very file the harness had staged — and `.git/info/exclude` was
    no help, because the scan uses `find`, not git. Rebuilding the stale gate
    image would NOT have fixed it; the rule itself had to learn the difference.

    The rule it must not lose: a canonical answer patch smuggled in beside the
    work is still leakage. The exemption is one declared path, at the subject
    root, on the one gate type that delivers it.
    """

    def _leak(self, task_dir: pathlib.Path, tmp: pathlib.Path) -> bool:
        """True when leak_found() reports leakage (it returns 0 on a find)."""
        proc = subprocess.run(
            ["bash", "-c", f'. "{LIB}"\nif leak_found; then echo LEAK; '
                           f'else echo CLEAN; fi'],
            capture_output=True, text=True,
            env={**os.environ, "TASK_DIR": str(task_dir),
                 "TASK_WORKDIR": str(tmp / "work")})
        self.assertIn(proc.stdout.strip().splitlines()[-1] if proc.stdout else "",
                      ("LEAK", "CLEAN"), proc.stdout + proc.stderr)
        return proc.stdout.strip().splitlines()[-1] == "LEAK"

    def test_the_delivered_artifact_is_not_leakage(self):
        tmp, task = self._task()
        subject = self._subject(tmp)
        runner.stage_review_artifact(str(subject), task)
        self.assertFalse(
            self._leak(tmp / "task", tmp),
            "the gate rejected the review task for containing the artifact the "
            "harness delivered to it — the 15/15 sweep of the W6 makeup pass")

    def test_a_second_stray_patch_is_still_leakage(self):
        tmp, task = self._task()
        subject = self._subject(tmp)
        runner.stage_review_artifact(str(subject), task)
        (subject / "canonical-solution.patch").write_text(
            "SYNTHETIC stray patch\n", encoding="utf-8")
        self.assertTrue(self._leak(tmp / "task", tmp),
                        "the exemption is one named path, not an amnesty on patches")

    def test_the_same_name_somewhere_else_in_the_tree_is_still_leakage(self):
        tmp, task = self._task()
        subject = self._subject(tmp)
        runner.stage_review_artifact(str(subject), task)
        nested = subject / "src" / "review-diff.patch"
        nested.parent.mkdir(parents=True, exist_ok=True)
        nested.write_text("SYNTHETIC copy in the wrong place\n", encoding="utf-8")
        self.assertTrue(
            self._leak(tmp / "task", tmp),
            "only the subject-root path the runner stages is exempt; the name "
            "alone must not buy passage anywhere in the tree")

    def test_a_solution_task_gets_no_exemption(self):
        # Same bytes, same filename, non-review gate type: still leakage. The
        # exemption follows the gate type that delivers the artifact.
        tmp, _ = self._task(gate_type="solution")
        subject = self._subject(tmp)
        (subject / "review-diff.patch").write_text("SYNTHETIC\n", encoding="utf-8")
        self.assertTrue(self._leak(tmp / "task", tmp))

    def test_a_planted_answer_marker_is_still_leakage_on_a_review_task(self):
        # The other half of leak_found must survive the change untouched.
        tmp, task = self._task()
        subject = self._subject(tmp)
        runner.stage_review_artifact(str(subject), task)
        marked = subject / "src" / "router" / "reg-exp-router" / "node.ts"
        marked.write_text("// CANONICAL SOLUTION\n", encoding="utf-8")
        self.assertTrue(self._leak(tmp / "task", tmp))

    def test_the_public_gate_now_passes_p5_on_a_delivered_review(self):
        # End to end through the real gate script, not just the helper.
        tmp, task = self._task()
        subject = self._subject(tmp)
        runner.stage_review_artifact(str(subject), task)
        (subject / "review-report.txt").write_text(
            "src/router/reg-exp-router/node.ts:12 — SYNTHETIC finding\n",
            encoding="utf-8")
        proc = subprocess.run(
            ["bash", str(CHECK_PUBLIC)], capture_output=True, text=True,
            env={**os.environ, "TASK_DIR": str(tmp / "task"),
                 "TASK_WORKDIR": str(tmp / "work")})
        p5 = [ln for ln in proc.stdout.splitlines() if "P5-no-leakage" in ln]
        self.assertTrue(p5, proc.stdout + proc.stderr)
        self.assertIn("[pass]", p5[0])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
