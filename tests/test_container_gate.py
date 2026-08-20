"""Regression tests for the CONTAINERIZED acceptance gate (run.py container_gate).

Why this file exists: container_gate() shipped with no test coverage and no mount
for the sealed hidden set. Because .dockerignore excludes ``**/hidden/`` from every
build context, the sealed tests are absent from the gate image, so check-hidden.sh
found nothing, wrote ``awaiting_human``, exited 2, and _gate_verdict turned EVERY
containerized run into ``acceptance.result: error``. Screening batch 1 was halted at
5/126 runs on exactly this: real spend, no gradable outcome. The rule these tests
encode: under isolation=container, a task with a present sealed set must grade
``accepted`` or ``rejected`` — never ``error`` — and an unreachable sealed set must
be caught here rather than by a live batch.

Offline: no docker, no node, no model spend. A fake ContainerExecutor stands in for
``docker run`` by doing the one thing docker does that matters here — translating
container paths to host paths through the mount table — and then executing the REAL
check-hidden.sh on the host. So the gate script, its exit contract, its report and
container_gate's own wiring (mounts, env, report path) are all exercised for real;
only the namespace is simulated. The sealed runner is the SYNTHETIC fixture from
tests/fixtures/ (CLAUDE.md non-negotiable #1); no real sealed material is touched.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.container import ContainerLaunch  # noqa: E402
from harness.runner import run as runner  # noqa: E402

CONTAINER_LAB_ROOT = runner.CONTAINER_LAB_ROOT

W1_TASK_DIR = ROOT / "tasks" / "suite" / "W1-test-generation"
TASK_DIR_REL = "tasks/suite/W1-test-generation"
FIX = ROOT / "tests" / "fixtures" / "w1-hidden-runner-SYNTHETIC"
FIX_VERSION = (FIX / "VERSION").read_text(encoding="utf-8").strip()
CHECK_HIDDEN = "check-hidden.sh"


def _git_repo(path: pathlib.Path) -> pathlib.Path:
    """A minimal committed git repo, standing in for the subject clone."""
    path.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    (path / "README.md").write_text("SYNTHETIC subject tree\n", encoding="utf-8")
    for argv in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "base"]):
        subprocess.run(["git", "-C", str(path), *argv],  # noqa: S603 - fixed argv
                       check=True, capture_output=True, env=env)
    return path


class FakeExecutor:
    """Stands in for ``docker run``: resolves container paths, then execs on the host.

    Records every ``run`` call (cmd, mounts, network, env, workdir) for assertions.
    ``check-public.sh`` is short-circuited to a pass — the public gate needs node and
    a real subject tree, and these tests are about the hidden path; the verdict logic
    combining the two is asserted from the recorded exit codes.
    """

    calls: list = []
    image_root: str = ""

    def __init__(self, image: str) -> None:
        self.image = image

    def _resolve(self, value: str, mounts) -> str:
        # Longest destination first, so /out and a nested task path can coexist.
        for src, dst, _mode in sorted(mounts or [], key=lambda m: -len(m[1])):
            if value == dst or value.startswith(dst.rstrip("/") + "/"):
                return src + value[len(dst):]
        if value == CONTAINER_LAB_ROOT or value.startswith(CONTAINER_LAB_ROOT + "/"):
            return FakeExecutor.image_root + value[len(CONTAINER_LAB_ROOT):]
        return value

    def run(self, cmd, *, mounts=None, workdir=None, network="none", env=None,
            timeout=None):
        FakeExecutor.calls.append({
            "image": self.image, "cmd": list(cmd), "mounts": list(mounts or []),
            "network": network, "env": dict(env or {}), "workdir": workdir,
        })
        host_cmd = [self._resolve(c, mounts) for c in cmd]
        host_env = {k: self._resolve(v, mounts) for k, v in (env or {}).items()}

        if CHECK_HIDDEN not in host_cmd[-1]:  # public gate — see docstring
            report = host_env.get("GATE_REPORT")
            if report:
                with open(report, "w", encoding="utf-8") as fh:
                    json.dump({"gate": "public", "checks": [
                        {"id": "SYNTHETIC-public", "status": "pass",
                         "detail": "public gate stubbed offline (tests only)"}]}, fh)
            return _Result(0)

        proc = subprocess.run(  # noqa: S603 - fixed argv, test-owned
            host_cmd, capture_output=True, text=True, check=False,
            env={**os.environ, **host_env},
        )
        return _Result(proc.returncode, proc.stdout, proc.stderr)


class _Result:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class ContainerGateHiddenMount(unittest.TestCase):
    """container_gate() must reach the sealed set the image deliberately lacks."""

    def setUp(self) -> None:
        FakeExecutor.calls = []
        self._real_executor = runner.ContainerExecutor
        runner.ContainerExecutor = FakeExecutor
        self.addCleanup(setattr, runner, "ContainerExecutor", self._real_executor)
        # HIDDEN_TESTS_DIR in the ambient environment would override the task-relative
        # resolution under test; a run must not depend on the operator's shell.
        self._saved_override = os.environ.pop("HIDDEN_TESTS_DIR", None)
        if self._saved_override is not None:
            self.addCleanup(os.environ.__setitem__, "HIDDEN_TESTS_DIR",
                            self._saved_override)

        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="containergate-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

        # The IMAGE: task material intact, hidden/ absent — what .dockerignore
        # (**/hidden/) actually produces, verified against the real gate image.
        FakeExecutor.image_root = str(self.tmp / "image")
        image_task = self.tmp / "image" / TASK_DIR_REL
        image_task.parent.mkdir(parents=True)
        shutil.copytree(W1_TASK_DIR, image_task,
                        ignore=shutil.ignore_patterns("hidden", ".work"))
        # The subject tree is always a git CLONE in a real run, and both gates run
        # git against it (discovery for test_generation, the G0/H0 readability guard
        # for every shape). An empty directory would exercise a tree no batch ever
        # sees; make the fixture what the gate is actually pointed at.
        _git_repo(image_task / ".work" / "repo")
        (self.tmp / "image" / "harness").symlink_to(ROOT / "harness")
        self.assertFalse((image_task / "hidden").exists(),
                         "the gate image must not carry the sealed set")

        # The HOST task dir: task.yaml plus a SYNTHETIC sealed set standing in for
        # the human-held one. Never the real tasks/suite/*/hidden/.
        self.host_task = self.tmp / "host-task"
        self.host_task.mkdir()
        shutil.copy(W1_TASK_DIR / "task.yaml", self.host_task / "task.yaml")

        self.run_dir = self.tmp / "run"
        self.run_dir.mkdir()

    def _seal(self, runner_fixture: str) -> pathlib.Path:
        hidden = self.host_task / "hidden"
        hidden.mkdir(exist_ok=True)
        entry = hidden / "check.sh"
        shutil.copy(FIX / runner_fixture, entry)
        entry.chmod(0o755)
        (hidden / "VERSION").write_text(FIX_VERSION + "\n", encoding="utf-8")
        return hidden

    def _gate(self):
        task = runner.Task(
            task_dir=str(self.host_task), task_id="w1-test-generation",
            task_suite_version="test", prompt="", contamination_tier=None,
            hidden_test_hash=None, gate_type="test_generation",
            task_dir_rel=TASK_DIR_REL,
        )
        launch = ContainerLaunch(image="lab-subject/test:0000")
        return runner.container_gate(launch, task, str(self.run_dir))

    def _hidden_call(self) -> dict:
        return [c for c in FakeExecutor.calls if CHECK_HIDDEN in c["cmd"][-1]][0]

    # -- the mount itself ---------------------------------------------------- #
    def test_sealed_set_is_mounted_read_only_at_the_task_hidden_path(self) -> None:
        hidden = self._seal("accept-SYNTHETIC.sh")
        self._gate()
        call = self._hidden_call()
        expected = (str(hidden), f"{CONTAINER_LAB_ROOT}/{TASK_DIR_REL}/hidden", "ro")
        self.assertIn(expected, call["mounts"],
                      "the sealed set must be mounted read-only into the gate container")
        self.assertEqual(call["env"]["HIDDEN_TESTS_DIR"], expected[1])

    def test_gate_container_stays_offline(self) -> None:
        self._seal("accept-SYNTHETIC.sh")
        self._gate()
        for call in FakeExecutor.calls:
            self.assertEqual(call["network"], "none",
                             "mounting sealed material must not relax the gate's network posture")

    # -- the outcome the batch needs ----------------------------------------- #
    def test_present_sealed_set_grades_accepted_never_error(self) -> None:
        self._seal("accept-SYNTHETIC.sh")
        passed, result, checks = self._gate()
        self.assertTrue(passed)
        self.assertEqual(result, "accepted")
        self.assertEqual(checks["hidden"]["status"], "pass")

    def test_present_sealed_set_grades_rejected_never_error(self) -> None:
        self._seal("reject-SYNTHETIC.sh")
        passed, result, checks = self._gate()
        self.assertFalse(passed)
        self.assertEqual(result, "rejected")
        self.assertEqual(checks["hidden"]["status"], "fail")

    def test_the_report_cites_the_sealed_version_and_hash(self) -> None:
        self._seal("accept-SYNTHETIC.sh")
        _, _, checks = self._gate()
        self.assertEqual(checks["hidden"]["version"], FIX_VERSION)
        self.assertTrue(checks["hidden"]["hash"].startswith("sha256:"),
                        "every graded run must cite which sealed bytes judged it")

    # -- the regression, stated as a failure mode ---------------------------- #
    def test_an_unreachable_sealed_set_is_error_and_the_mount_is_what_prevents_it(self) -> None:
        """Reproduces the batch-1 halt: no reachable sealed set => every run errors.

        With no hidden/ on the host there is nothing to mount, the image has none
        either, and the verdict is `error` — billed, ungradable. The paired
        assertion is that the ONLY difference from the accepted case above is the
        mount, so deleting it can never again pass CI.
        """
        self.assertFalse((self.host_task / "hidden").exists())
        _, result, checks = self._gate()
        self.assertEqual(result, "error")
        self.assertEqual(checks["hidden"]["status"], "awaiting_human")
        self.assertIsNone(checks["hidden"]["hash"])
        mounted = [m for m in self._hidden_call()["mounts"] if m[1].endswith("/hidden")]
        self.assertEqual(mounted, [], "nothing to mount when nothing is sealed")

        FakeExecutor.calls = []
        self._seal("accept-SYNTHETIC.sh")
        _, result_after, _ = self._gate()
        self.assertEqual(result_after, "accepted")

    def test_a_missing_sealed_dir_is_never_created_on_the_host(self) -> None:
        """docker -v creates a missing source; that would plant a root-owned empty
        hidden/ in the task dir and quietly make the task look sealed-but-empty."""
        self._gate()
        self.assertFalse((self.host_task / "hidden").exists())
        for call in FakeExecutor.calls:
            for src, _dst, _mode in call["mounts"]:
                self.assertTrue(os.path.exists(src), f"mounted a non-existent source: {src}")


class HiddenTestsDirResolution(unittest.TestCase):
    """The host and container gates must resolve the same sealed directory."""

    def test_defaults_to_task_relative_hidden(self) -> None:
        saved = os.environ.pop("HIDDEN_TESTS_DIR", None)
        try:
            self.assertEqual(runner.hidden_tests_dir("/x/task"), "/x/task/hidden")
        finally:
            if saved is not None:
                os.environ["HIDDEN_TESTS_DIR"] = saved

    def test_env_override_wins_as_it_does_in_check_hidden_sh(self) -> None:
        saved = os.environ.get("HIDDEN_TESTS_DIR")
        os.environ["HIDDEN_TESTS_DIR"] = "/sealed/elsewhere"
        try:
            self.assertEqual(runner.hidden_tests_dir("/x/task"), "/sealed/elsewhere")
        finally:
            if saved is None:
                os.environ.pop("HIDDEN_TESTS_DIR", None)
            else:
                os.environ["HIDDEN_TESTS_DIR"] = saved


if __name__ == "__main__":
    unittest.main()
