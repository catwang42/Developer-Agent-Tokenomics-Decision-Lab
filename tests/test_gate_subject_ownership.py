"""Regression tests for THE screening-batch-1 instrument defect: a gate that
cannot read the tree it is grading, and says "rejected" instead of saying so.

The arrangement that produced it is structural, not accidental. Under container
isolation the agent's edits live in a named Docker volume seeded from the AGENT
image, whose files are owned by the agent uid (`lab`, 706335951); the gate runs
from the GATE image as root. git's safe.directory guard refuses a repo it
considers dubiously owned:

    fatal: detected dubious ownership in repository at '/lab/.../.work/repo'

Every git call then fails, and the failure is silent in the worst way. A sealed
runner whose first move is "which test files did the agent add?" gets an EMPTY
list back, which reads exactly like "the agent added none" — so all 15
test_generation cells of batch 1 were graded `rejected` against a tree the
grader never saw. The batch-1 split is the fingerprint: gate_type `solution`
(no git discovery) 32/32 hidden-pass, `test_generation` (git discovery) 15/15
hidden-fail.

Two rules are encoded here, and they are separate:

  1. The gate TRUSTS this one path, through the environment so a sealed runner
     invoked as a child inherits it (the sealed runner is human-held and must
     not have to know about our uid arrangement).
  2. If git STILL cannot read the tree, a discovery-shaped gate reports
     `unavailable` (exit 2 -> acceptance.result "error"), never `fail`. A
     rejection we cannot justify is worse than an admitted hole; batch 1 is what
     that costs. The `solution` shape, which injects and runs sealed tests
     without ever asking git anything, must keep grading — the 32/32 that were
     never in doubt stay out of the blast radius.

Coverage is in two layers. The offline layer drives the REAL check-hidden.sh on
the host and simulates the refusal with GIT_TEST_ASSUME_DIFFERENT_OWNER=1 (git's
own hook for this; on the host's git 2.30.2 it refuses unconditionally, ignoring
the allowlist, so it can only stand in for the FAILURE half). The docker layer
reproduces the real arrangement byte for byte — volume seeded by the agent image,
graded by the gate image — and proves both halves, with a negative control
showing the pre-fix path finds nothing. Sealed material is never touched: the
runner here is the SYNTHETIC fixture (CLAUDE.md non-negotiable #1).
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
FIX = ROOT / "tests" / "fixtures" / "w1-hidden-runner-SYNTHETIC"
FIX_VERSION = (FIX / "VERSION").read_text(encoding="utf-8").strip()
LIB = ROOT / "harness" / "task-tools" / "lib.sh"
CHECK_HIDDEN = ROOT / "harness" / "task-tools" / "gate" / "check-hidden.sh"

GATE_IMAGE = "lab-subject/w1-realworld-mapper-tests:30b68e1e8814"
AGENT_IMAGE = "lab-subject-agent/w1-realworld-mapper-tests:30b68e1e8814"

GIT_ID = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
          "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

# git's own switch for "pretend this repo belongs to someone else" — the exact
# code path a foreign-uid volume takes, without needing a foreign uid.
FOREIGN = {"GIT_TEST_ASSUME_DIFFERENT_OWNER": "1"}


def _have(*argv: str) -> bool:
    try:
        return subprocess.run(argv, capture_output=True,  # noqa: S603 - fixed argv
                              check=False, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


HAVE_DOCKER = _have("docker", "info")
HAVE_IMAGES = HAVE_DOCKER and all(
    _have("docker", "image", "inspect", img) for img in (GATE_IMAGE, AGENT_IMAGE))


def _sh(script: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, test-owned script
        ["bash", "-c", script], capture_output=True, text=True, check=False,
        env={**os.environ, **env})


class _TaskFixture(unittest.TestCase):
    """A throwaway task dir + subject clone + SYNTHETIC sealed set."""

    gate_type = "test_generation"
    sealed_runner = "discovery-SYNTHETIC.sh"

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="gateowner-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.task = self.tmp / "task"
        (self.task / ".work").mkdir(parents=True)
        (self.task / "task.yaml").write_text(
            "task_id: synthetic-ownership\n"
            "task_suite_version: SYNTHETIC\n"
            f"gate_type: {self.gate_type}\n"
            "stack: none\n"
            "baseline_test_pattern: none\n",
            encoding="utf-8")

        self.subject = self.task / ".work" / "repo"
        self.subject.mkdir()
        (self.subject / "README.md").write_text("SYNTHETIC subject\n", encoding="utf-8")
        for argv in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "base"]):
            subprocess.run(["git", "-C", str(self.subject), *argv],  # noqa: S603
                           check=True, capture_output=True, env={**os.environ, **GIT_ID})
        # The agent's untracked contribution — what discovery must find.
        (self.subject / "src" / "tests").mkdir(parents=True)
        (self.subject / "src" / "tests" / "agent.test.ts").write_text(
            "// SYNTHETIC agent-authored test\n", encoding="utf-8")

        self.hidden = self.task / "hidden"
        self.hidden.mkdir()
        shutil.copy(FIX / self.sealed_runner, self.hidden / "check.sh")
        (self.hidden / "check.sh").chmod(0o755)
        (self.hidden / "VERSION").write_text(FIX_VERSION + "\n", encoding="utf-8")

        self.report = self.tmp / "gate-hidden.json"

    def _env(self, extra: dict) -> dict:
        return {"TASK_DIR": str(self.task), "TASK_WORKDIR": str(self.task / ".work"),
                "HIDDEN_TESTS_DIR": str(self.hidden),
                "HIDDEN_REPORT": str(self.report), **extra}

    def _hidden_gate(self, **extra) -> subprocess.CompletedProcess:
        return _sh(f'bash "{CHECK_HIDDEN}"', self._env(extra))

    def _report(self) -> dict:
        return json.loads(self.report.read_text(encoding="utf-8"))


class TrustHelperContract(_TaskFixture):
    """git_trust_subject: trust this one path, export it, and admit failure."""

    def _probe(self, extra: dict) -> subprocess.CompletedProcess:
        # Sources the real lib.sh, then reports what a CHILD process would see —
        # the sealed runner is a child, so an unexported trust is no trust at all.
        return _sh(
            f'. "{LIB}"\n'
            'if git_trust_subject; then echo VERDICT=trusted; '
            'else echo VERDICT=refused; fi\n'
            'echo "ERROR=$(git_subject_error)"\n'
            'bash -c \'echo "CHILD_SEES=${GIT_CONFIG_VALUE_0:-<unset>}"\'\n',
            self._env(extra))

    def test_a_readable_tree_is_left_alone(self) -> None:
        out = self._probe({}).stdout
        self.assertIn("VERDICT=trusted", out)
        self.assertIn("CHILD_SEES=<unset>", out,
                      "a tree git can already read must not have its config rewritten")

    def test_a_foreign_owned_tree_is_refused_not_silently_empty(self) -> None:
        proc = self._probe(FOREIGN)
        self.assertIn("VERDICT=refused", proc.stdout)
        self.assertIn("dubious ownership", proc.stdout,
                      "the gate must be able to say WHY, not just score zero")

    def test_the_trust_is_exported_so_the_sealed_runner_inherits_it(self) -> None:
        """The mechanism, asserted independently of whether git then relents.

        The host's git 2.30.2 refuses regardless once
        GIT_TEST_ASSUME_DIFFERENT_OWNER is set, so this asserts only what our code
        owns: that safe.directory reaches a child process, naming this exact path
        and no other. That it is SUFFICIENT is proven against the real images in
        TheRealArrangement below.
        """
        out = self._probe(FOREIGN).stdout
        self.assertIn(f"CHILD_SEES={self.subject}", out)


class DiscoveryGateRefusesToScoreWhatItCannotSee(_TaskFixture):
    """test_generation / pr_review: unreadable tree => unavailable, never fail."""

    def test_a_readable_tree_grades_normally(self) -> None:
        proc = self._hidden_gate()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("1 agent test file(s) found", proc.stdout)
        self.assertEqual(self._report()["status"], "pass")

    def test_an_unreadable_tree_is_unavailable_not_a_rejection(self) -> None:
        """The batch-1 verdict, inverted. Exit 2 -> acceptance.result "error"."""
        proc = self._hidden_gate(**FOREIGN)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertNotEqual(proc.returncode, 1,
                            "an ungradable tree must never be scored as a failing agent")
        self.assertIn("UNAVAILABLE", proc.stdout)
        self.assertEqual(self._report()["status"], "unavailable")

    def test_the_sealed_runner_is_not_even_invoked_on_an_unreadable_tree(self) -> None:
        """Nothing was graded, so nothing may claim to have been graded.

        Batch 1's rejects cited a real sealed hash over a tree the runner could
        not read. An `unavailable` report carries no hash and no version — there
        is no grading event to attribute.
        """
        proc = self._hidden_gate(**FOREIGN)
        self.assertNotIn("SYNTHETIC discovery", proc.stdout + proc.stderr)
        self.assertIsNone(self._report()["hash"])
        self.assertIsNone(self._report()["version"])


class SolutionGateIsOutOfTheBlastRadius(_TaskFixture):
    """The 32/32 that were never in doubt must keep grading."""

    gate_type = "solution"

    def setUp(self) -> None:
        super().setUp()
        # The `solution` shape injects sealed jest files and runs them; it never
        # asks git anything, so ownership is irrelevant to it. stack `none` makes
        # the run itself a no-op — this asserts the GUARD's reach, not jest.
        (self.hidden / "check.sh").unlink()
        (self.hidden / "sealed-SYNTHETIC.test.ts").write_text(
            "// SYNTHETIC sealed test\n", encoding="utf-8")

    def test_an_unreadable_tree_does_not_block_the_injection_path(self) -> None:
        proc = self._hidden_gate(**FOREIGN)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self._report()["status"], "pass")
        self.assertEqual(self._report()["version"], FIX_VERSION)


@unittest.skipUnless(HAVE_IMAGES, "needs docker and the built w1 gate/agent images")
class TheRealArrangement(unittest.TestCase):
    """The batch-1 arrangement, reproduced: agent-seeded volume, root-run gate.

    No simulation and no model spend — the images are already built, both
    containers are --network=none, and the only thing executed inside them is git
    and the SYNTHETIC runner.
    """

    VOLUME = "lab-gate-ownership-regression"

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="gateowner-docker-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        self._docker("volume", "rm", "-f", self.VOLUME, check=False)
        self._docker("volume", "create", self.VOLUME)
        self.addCleanup(self._docker, "volume", "rm", "-f", self.VOLUME, check=False)

        # Seeded by the AGENT image => owned by the agent uid, exactly as a run.
        seed = self._docker(
            "run", "--rm", "--network=none", "-v", f"{self.VOLUME}:/subject",
            "-w", "/subject",
            *[a for k, v in GIT_ID.items() for a in ("-e", f"{k}={v}")],
            AGENT_IMAGE, "sh", "-c",
            'git init -q . && echo base > README.md && git add -A '
            '&& git commit -qm base && mkdir -p src/tests '
            '&& echo "// SYNTHETIC agent test" > src/tests/agent.test.ts && id -u')
        self.agent_uid = seed.stdout.strip().splitlines()[-1]
        self.assertNotEqual(self.agent_uid, "0",
                            "the agent image must not run as root, or there is no bug to fix")

    def _docker(self, *argv: str, check: bool = True) -> subprocess.CompletedProcess:
        proc = subprocess.run(["docker", *argv],  # noqa: S603 - fixed argv
                              capture_output=True, text=True, check=False, timeout=300)
        if check:
            self.assertEqual(proc.returncode, 0, f"docker {argv[0]}: {proc.stderr}")
        return proc

    def test_the_pre_fix_path_scores_an_invisible_tree_as_an_empty_one(self) -> None:
        """Negative control: this is what produced batch 1's 15/15 rejects."""
        proc = self._docker(
            "run", "--rm", "--network=none", "-v", f"{self.VOLUME}:/subject",
            "-v", f"{FIX}:/fixture:ro", GATE_IMAGE,
            "sh", "-c", 'SUBJECT_DIR=/subject bash /fixture/discovery-SYNTHETIC.sh',
            check=False)
        self.assertEqual(proc.returncode, 1, "the arrangement must still be hostile")
        self.assertIn("0 agent test file(s) found", proc.stderr)
        self.assertIn("NOT-caught", proc.stderr)

    def test_the_gate_reads_the_agents_tree_and_the_sealed_runner_inherits_it(self) -> None:
        """The fix, end to end: same volume, same images, real check-hidden.sh."""
        task = self.tmp / "task"
        (task / ".work" / "repo").mkdir(parents=True)  # mount point for the volume
        (task / "task.yaml").write_text(
            "task_id: synthetic-ownership\ntask_suite_version: SYNTHETIC\n"
            "gate_type: test_generation\nstack: none\nbaseline_test_pattern: none\n",
            encoding="utf-8")
        hidden = task / "hidden"
        hidden.mkdir()
        shutil.copy(FIX / "discovery-SYNTHETIC.sh", hidden / "check.sh")
        (hidden / "check.sh").chmod(0o755)
        (hidden / "VERSION").write_text(FIX_VERSION + "\n", encoding="utf-8")
        out = self.tmp / "out"
        out.mkdir()

        proc = self._docker(
            "run", "--rm", "--network=none",
            "-v", f"{task}:/lab/task:rw",
            "-v", f"{self.VOLUME}:/lab/task/.work/repo:rw",
            "-v", f"{ROOT / 'harness'}:/lab/harness:ro",
            "-v", f"{out}:/out:rw",
            "-e", "TASK_DIR=/lab/task", "-e", "TASK_WORKDIR=/lab/task/.work",
            "-e", "HIDDEN_TESTS_DIR=/lab/task/hidden",
            "-e", "HIDDEN_REPORT=/out/gate-hidden.json",
            GATE_IMAGE, "bash", "/lab/harness/task-tools/gate/check-hidden.sh",
            check=False)

        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("== hidden gate: PASS ==", proc.stdout)
        self.assertIn("1 agent test file(s) found", proc.stdout,
                      "the sealed runner must inherit the trust, not just the gate")
        report = json.loads((out / "gate-hidden.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["version"], FIX_VERSION)


if __name__ == "__main__":
    unittest.main()
