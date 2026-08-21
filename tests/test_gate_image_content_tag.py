"""The stale-gate guard: an image tag that changes when the GRADER changes.

THE DEFECT, from the W6 makeup pass of 2026-08-20. `_ensure_gate_launch` tagged
the gate image `subject_image_tag(task_id, pinned_commit)` and `_ensure_image`
builds only when that tag is absent locally. Both inputs describe the SUBJECT.
Neither describes the grader. So the two fixes merged that day — the pr_review
diff-scope allowance and the git-ownership repair — left the tag untouched, the
image built two days earlier was served from cache, and all 15 cells were graded
by the pre-fix scripts. Every one came back `rejected`, including five whose
sealed hidden gate had passed.

Nothing in the run record said so. The old tag's own docstring promised "never a
stale image silently reused", and it was true of a re-pin and false of everything
else. The failure mode is the worst kind: no error, no warning, a full set of
plausible verdicts measuring an instrument nobody knew was old.

So the tag now carries a digest of what the image bakes and what decides a
verdict: the task-tools tree, the Dockerfile, and the task directory whose
task.yaml the in-container gate reads. Change any of it and the tag moves, the
cache misses, and the image is rebuilt.

Hermetic: every digest here is taken over throwaway trees under tmp. The one test
that touches the real repository only reads it. `tasks/*/hidden/` is never read —
one test exists to prove exactly that.
"""

from __future__ import annotations

import pathlib
import shutil
import tempfile
import unittest

from harness.container.exec import (
    GATE_CONTENT_PATHS,
    gate_image_content_digest,
    subject_image_tag,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]


class _FakeRepo(unittest.TestCase):
    """A miniature repo carrying every path the digest is defined over."""

    def setUp(self) -> None:
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="gatedigest-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        for rel in GATE_CONTENT_PATHS:
            path = self.root / rel
            if path.suffix:  # a file root (the Dockerfile, the assert script)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"# SYNTHETIC {rel}\n", encoding="utf-8")
            else:            # a directory root (harness/task-tools)
                path.mkdir(parents=True, exist_ok=True)
                (path / "lib.sh").write_text("# SYNTHETIC lib\n", encoding="utf-8")
                (path / "gate").mkdir(exist_ok=True)
                (path / "gate" / "check-public.sh").write_text(
                    "# SYNTHETIC public gate\n", encoding="utf-8")

        self.task_rel = "tasks/suite/SYNTHETIC-task"
        self.task_dir = self.root / self.task_rel
        self.task_dir.mkdir(parents=True)
        (self.task_dir / "task.yaml").write_text(
            "task_id: synthetic-SYNTHETIC\ngate_type: pr_review\n", encoding="utf-8")

    def digest(self) -> str:
        return gate_image_content_digest(str(self.root), self.task_rel)


class TheDigestMovesWhenTheGraderMoves(_FakeRepo):
    """Each of these is a change that silently kept the old tag before."""

    def test_a_gate_script_edit_changes_it(self):
        before = self.digest()
        (self.root / "harness" / "task-tools" / "gate" / "check-public.sh").write_text(
            "# SYNTHETIC public gate, with the pr_review allowance\n", encoding="utf-8")
        self.assertNotEqual(before, self.digest(),
                            "the exact change that was served from cache on 2026-08-20")

    def test_a_lib_edit_changes_it(self):
        before = self.digest()
        (self.root / "harness" / "task-tools" / "lib.sh").write_text(
            "# SYNTHETIC lib, with the leak exemption\n", encoding="utf-8")
        self.assertNotEqual(before, self.digest())

    def test_a_new_gate_script_changes_it(self):
        before = self.digest()
        (self.root / "harness" / "task-tools" / "gate" / "check-hidden.sh").write_text(
            "# SYNTHETIC hidden gate\n", encoding="utf-8")
        self.assertNotEqual(before, self.digest())

    def test_a_dockerfile_edit_changes_it(self):
        before = self.digest()
        (self.root / "harness" / "container" / "Dockerfile.subject").write_text(
            "# SYNTHETIC Dockerfile, one more COPY\n", encoding="utf-8")
        self.assertNotEqual(before, self.digest())

    def test_a_task_yaml_edit_changes_it(self):
        # check-public.sh reads /lab/tasks/<task>/task.yaml from INSIDE the image,
        # so baked task material decides verdicts exactly as gate scripts do. #25
        # changed W6's task.yaml and the tag did not move.
        before = self.digest()
        (self.task_dir / "task.yaml").write_text(
            "task_id: synthetic-SYNTHETIC\ngate_type: pr_review\n"
            "review_report: review-report.txt\n", encoding="utf-8")
        self.assertNotEqual(before, self.digest())

    def test_losing_an_execute_bit_changes_it(self):
        # A gate script that stops being executable changes behaviour without
        # changing a byte of text.
        script = self.root / "harness" / "task-tools" / "gate" / "check-public.sh"
        script.chmod(0o755)
        before = self.digest()
        script.chmod(0o644)
        self.assertNotEqual(before, self.digest())

    def test_a_deleted_root_changes_it(self):
        before = self.digest()
        (self.root / "harness" / "container" / "Dockerfile.subject").unlink()
        self.assertNotEqual(before, self.digest(),
                            "an absent root must not hash like an empty one")


class TheDigestHoldsStillOtherwise(_FakeRepo):
    """A tag that churns is as useless as one that never moves: it would rebuild
    every image on every run, and the operator would learn to ignore it."""

    def test_it_is_deterministic_across_calls(self):
        self.assertEqual(self.digest(), self.digest())

    def test_an_unrelated_repo_file_does_not_change_it(self):
        before = self.digest()
        (self.root / "README.md").write_text("SYNTHETIC\n", encoding="utf-8")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "index.md").write_text("SYNTHETIC\n", encoding="utf-8")
        self.assertEqual(before, self.digest())

    def test_another_task_does_not_change_this_tasks_digest(self):
        before = self.digest()
        other = self.root / "tasks" / "suite" / "SYNTHETIC-other"
        other.mkdir(parents=True)
        (other / "task.yaml").write_text("task_id: other-SYNTHETIC\n", encoding="utf-8")
        self.assertEqual(before, self.digest(),
                         "the tag is per-task; an unrelated task must not "
                         "invalidate this one's image")

    def test_pycache_does_not_change_it(self):
        before = self.digest()
        cache = self.root / "harness" / "task-tools" / "__pycache__"
        cache.mkdir()
        (cache / "x.pyc").write_bytes(b"\x00SYNTHETIC")
        self.assertEqual(before, self.digest())


class TheSealedSetIsNotRead(_FakeRepo):
    """CLAUDE.md: `tasks/*/hidden/` is human-held. The digest must not read it —
    and it does not need to: the sealed set is MOUNTED at grade time, never baked,
    and the gates already fingerprint it separately in every run record."""

    def test_sealed_content_does_not_change_the_digest(self):
        before = self.digest()
        hidden = self.task_dir / "hidden"
        hidden.mkdir()
        (hidden / "check.sh").write_text("# SYNTHETIC sealed runner\n", encoding="utf-8")
        (hidden / "VERSION").write_text("SYNTHETIC\n", encoding="utf-8")
        self.assertEqual(
            before, self.digest(),
            "a digest that moves with sealed content is a digest that read it")

    def test_an_unreadable_sealed_dir_does_not_break_the_digest(self):
        hidden = self.task_dir / "hidden"
        hidden.mkdir()
        (hidden / "check.sh").write_text("# SYNTHETIC\n", encoding="utf-8")
        hidden.chmod(0o000)
        self.addCleanup(hidden.chmod, 0o755)
        self.digest()  # must not raise


class TheTagCarriesIt(_FakeRepo):
    def test_the_digest_is_in_the_tag(self):
        digest = self.digest()
        tag = subject_image_tag("w6-hono-router-review", "3feb3551d46d" * 4, digest)
        self.assertTrue(tag.endswith(f"-{digest}"), tag)

    def test_two_graders_yield_two_tags_for_the_same_subject(self):
        task_id, pin = "w6-hono-router-review", "3feb3551d46d" * 4
        before = subject_image_tag(task_id, pin, self.digest())
        (self.root / "harness" / "task-tools" / "gate" / "check-public.sh").write_text(
            "# SYNTHETIC public gate, fixed\n", encoding="utf-8")
        after = subject_image_tag(task_id, pin, self.digest())
        self.assertNotEqual(before, after,
                            "same task, same subject commit, different grader — "
                            "the cache must miss")

    def test_the_tag_is_a_valid_docker_reference(self):
        tag = subject_image_tag("W6/PR review!", "3feb3551d46d" * 4, self.digest())
        repo, _, ref = tag.partition(":")
        self.assertRegex(repo, r"^[a-z0-9._/-]+$")
        self.assertRegex(ref, r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
        self.assertLessEqual(len(ref), 128)

    def test_an_omitted_digest_leaves_the_old_shape(self):
        # Callers that only want the tag SHAPE (and the tags already recorded in
        # the manifest) keep working; the runner always passes a digest.
        self.assertEqual(subject_image_tag("t", "0123456789abcdef"),
                         "lab-subject/t:0123456789ab")


class TheRealRepositoryIsCovered(unittest.TestCase):
    """The digest is only a guard if it is defined over paths that exist here."""

    def test_every_declared_root_exists(self):
        for rel in GATE_CONTENT_PATHS:
            self.assertTrue((ROOT / rel).exists(), f"{rel} is declared but absent")

    def test_the_real_w6_task_digests(self):
        digest = gate_image_content_digest(str(ROOT), "tasks/suite/W6-pr-review")
        self.assertRegex(digest, r"^[0-9a-f]{8}$")

    def test_the_runner_passes_a_digest(self):
        # The guard is worthless if _ensure_gate_launch forgets to use it.
        src = (ROOT / "harness" / "runner" / "run.py").read_text(encoding="utf-8")
        _, _, tail = src.partition("def _ensure_gate_launch")
        self.assertTrue(tail, "_ensure_gate_launch not found")
        body = tail.split("\ndef ")[0]
        self.assertIn("gate_image_content_digest", body)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
