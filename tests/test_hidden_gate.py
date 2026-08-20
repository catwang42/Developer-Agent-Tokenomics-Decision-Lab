"""Unit tests for the test-generation hidden gate (Phase 3, W1/F3).

check-hidden.sh grows a `gate_type=test_generation` branch: instead of injecting
sealed jest files, it discovers an EXECUTABLE sealed runner (convention: check.sh)
in HIDDEN_DIR, invokes it with SUBJECT_DIR exported, honors its exit contract
(0 accept / 1 reject / 2 unavailable), records version + a content hash over the
sealed set, and surfaces the runner's stderr into the gate log — WITHOUT ever
reading the sealed file contents itself (the mutant set is human-held).

These tests drive the bash gate end-to-end against a SYNTHETIC executable runner
(tests/fixtures/w1-hidden-runner-SYNTHETIC/*-SYNTHETIC.sh) copied into a throwaway
HIDDEN_DIR. No clone, no node, no model spend. The W1 task.yaml supplies the real
gate_type; nothing sealed or real is touched.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECK_HIDDEN = ROOT / "harness" / "task-tools" / "gate" / "check-hidden.sh"
W1_TASK_DIR = ROOT / "tasks" / "suite" / "W1-test-generation"
FIX = ROOT / "tests" / "fixtures" / "w1-hidden-runner-SYNTHETIC"
FIX_VERSION = (FIX / "VERSION").read_text(encoding="utf-8").strip()


class TestGenerationHiddenGate(unittest.TestCase):
    def _run(self, runner: str | None):
        """Run check-hidden.sh (gate_type=test_generation) with a throwaway
        HIDDEN_DIR. `runner` names a *-SYNTHETIC.sh fixture to install as check.sh,
        or None to leave the dir without an entrypoint (awaiting-human)."""
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="w1hidden-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        hidden = tmp / "hidden"
        hidden.mkdir()
        (hidden / "README-FOR-HUMAN.md").write_text("placeholder\n", encoding="utf-8")
        if runner is not None:
            entry = hidden / "check.sh"
            shutil.copy(FIX / runner, entry)
            entry.chmod(0o755)
            (hidden / "VERSION").write_text(FIX_VERSION + "\n", encoding="utf-8")
        # SUBJECT_DIR is derived by lib.sh from TASK_WORKDIR. Create it as a git
        # CLONE, which is what the gate is pointed at in every real run: the
        # executable-runner branch refuses to grade a tree git cannot read (see
        # tests/test_gate_subject_ownership.py), so a bare directory here would
        # exercise a state no batch produces.
        subject = tmp / "work" / "repo"
        subject.mkdir(parents=True)
        (subject / "README.md").write_text("SYNTHETIC subject tree\n", encoding="utf-8")
        gitenv = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                  "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        for argv in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "base"]):
            subprocess.run(["git", "-C", str(subject), *argv],
                           check=True, capture_output=True, env=gitenv)
        report = tmp / "gate-hidden.json"
        env = {
            **os.environ,
            "TASK_DIR": str(W1_TASK_DIR),
            "TASK_WORKDIR": str(tmp / "work"),
            "HIDDEN_TESTS_DIR": str(hidden),
            "HIDDEN_REPORT": str(report),
        }
        proc = subprocess.run(
            ["bash", str(CHECK_HIDDEN)],
            capture_output=True, text=True, env=env,
        )
        data = json.loads(report.read_text(encoding="utf-8")) if report.exists() else None
        return proc, data

    def test_accept_exit0_and_report(self) -> None:
        proc, data = self._run("accept-SYNTHETIC.sh")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(data["gate"], "hidden")
        self.assertEqual(data["status"], "pass")
        self.assertTrue(data["hash"].startswith("sha256:"))
        self.assertEqual(data["version"], FIX_VERSION)
        # runner stderr (per-mutant lines) surfaced into the gate log, prefixed.
        self.assertIn("caught", proc.stdout)
        self.assertIn("| ", proc.stdout)

    def test_reject_exit1_and_report(self) -> None:
        proc, data = self._run("reject-SYNTHETIC.sh")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(data["status"], "fail")
        self.assertTrue(data["hash"].startswith("sha256:"))
        self.assertIn("NOT caught", proc.stdout)

    def test_unavailable_runner_exit2(self) -> None:
        # entrypoint present but reports its own contents unavailable -> exit 2.
        proc, data = self._run("unavailable-SYNTHETIC.sh")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(data["status"], "unavailable")

    def test_no_entrypoint_is_awaiting_human(self) -> None:
        proc, data = self._run(None)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(data["status"], "awaiting_human")
        self.assertIsNone(data["hash"])
        self.assertIsNone(data["version"])
        self.assertIn("AWAITING_HUMAN", proc.stdout)

    def test_subject_dir_is_exported_to_runner(self) -> None:
        # The accept fixture hard-requires SUBJECT_DIR; a clean exit proves the
        # harness exported it to the sealed runner.
        proc, _ = self._run("accept-SYNTHETIC.sh")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_hash_is_deterministic_and_covers_all_files(self) -> None:
        # Same sealed set -> identical hash across runs.
        _, d1 = self._run("accept-SYNTHETIC.sh")
        _, d2 = self._run("accept-SYNTHETIC.sh")
        self.assertEqual(d1["hash"], d2["hash"])
        # A different entrypoint (different bytes) -> different hash: the hash
        # actually covers the sealed content, not just the filename.
        _, d3 = self._run("reject-SYNTHETIC.sh")
        self.assertNotEqual(d1["hash"], d3["hash"])

    def test_gate_never_prints_runner_source(self) -> None:
        # The harness must not echo the sealed script's contents. Our fixtures use
        # a unique marker in their bodies (a comment) that must never leak.
        proc, _ = self._run("accept-SYNTHETIC.sh")
        self.assertNotIn("NOT the real W1 mutant set", proc.stdout)
        self.assertNotIn("NOT the real W1 mutant set", proc.stderr)


class SyntheticRunnerLabelingTest(unittest.TestCase):
    def test_fixtures_are_labeled_synthetic(self) -> None:
        runners = list(FIX.glob("*.sh"))
        self.assertTrue(runners, "no synthetic runner fixtures found")
        for f in runners:
            self.assertIn("SYNTHETIC", f.name)
            self.assertIn("SYNTHETIC", f.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
