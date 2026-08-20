"""Per-task agent budgets, and timeouts that actually stop the agent.

Two defects are pinned down here, both observed in screening batch 1:

  1. A FLAT 1800s bound across a suite whose tasks are not the same size. W1b's
     slowest COMPLETED attempt (1815s) was already past the bound, and only 9 of 21
     W3 attempts finished at all — so for the two biggest tasks the harness was
     measuring its own timeout rather than the product. The budget is now pinned per
     task in task.yaml and mirrored in the manifest, and the runner refuses to start
     when the two disagree.

  2. The ORPHAN: ``subprocess.run(timeout=...)`` around ``docker run`` kills the
     docker CLI *client*, not the container. The container kept running, kept its
     volume, and (on a live leg) kept spending. ``spawn_with_timeout`` names the
     container and force-removes it, and ``test_the_container_actually_dies`` proves
     it against a real long-running container — including the negative control that
     shows the old code path leaves one alive.

No model spend: the docker test runs ``sleep`` in an already-built local gate image
with ``--network=none``. Everything else is pure/offline.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import unittest

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from harness.adapters.base import AttemptSpec, ResolvedModel  # noqa: E402
from harness.container import exec as cexec  # noqa: E402
from harness.runner import run as runner  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifest" / "delivery-manifest.yaml"

# The pinned budgets, task dir -> (manifest key, seconds). Duplicated here on
# purpose: this is the human-approved decision, and a test that read the value from
# the file it is checking would assert nothing.
BUDGETS = {
    "tasks/pilot-realworld": ("pilot_task", 1200),
    "tasks/suite/W1-test-generation": ("w1_task", 1200),
    "tasks/suite/W4-complex-bugfix": ("w4_task", 1200),
    "tasks/suite/W6-pr-review": ("w6_task", 1200),
    "tasks/suite/W1b-zarr-block-mask-properties": ("w1b_task", 2700),
    "tasks/suite/W4b-zarr-consolidated-order": ("w4b_task", 2700),
    "tasks/suite/W3-migration": ("w3_task", 7200),
}


def _docker_ok() -> bool:
    try:
        proc = subprocess.run(["docker", "info"], capture_output=True,
                              text=True, check=False, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _a_local_gate_image() -> str:
    """Any already-built local gate image; '' if none (the test then skips).

    Deliberately not built here: a build is minutes of network and disk, and the
    thing under test is timeout/kill behaviour, which any image with ``sleep``
    exercises identically.
    """
    proc = subprocess.run(
        ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}",
         "--filter", "reference=lab-subject/*"],
        capture_output=True, text=True, check=False,
    )
    return next((ln for ln in proc.stdout.splitlines() if ln.strip()), "")


class PinnedBudgets(unittest.TestCase):
    """Every roster task pins its budget in BOTH places, at the approved value."""

    def test_task_yaml_and_manifest_carry_the_approved_value(self) -> None:
        manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
        for task_dir, (mkey, expected) in BUDGETS.items():
            with self.subTest(task=task_dir):
                ty = yaml.safe_load((ROOT / task_dir / "task.yaml").read_text(encoding="utf-8"))
                self.assertEqual(ty.get("agent_timeout_s"), expected,
                                 f"{task_dir}/task.yaml agent_timeout_s")
                self.assertEqual(manifest[mkey].get("agent_timeout_s"), expected,
                                 f"manifest {mkey}.agent_timeout_s")

    def test_the_runner_reads_the_pin(self) -> None:
        manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
        for task_dir, (_mkey, expected) in BUDGETS.items():
            with self.subTest(task=task_dir):
                task = runner.load_task(task_dir, manifest)
                self.assertEqual(task.agent_timeout_s, expected)

    def test_every_budget_clears_product_bs_own_timeout(self) -> None:
        """No pin may sit below agy's pinned --print-timeout.

        Otherwise our kill fires first and destroys the product's own diagnosable
        error — the invariant agy.build_command enforces per attempt.
        """
        from harness.adapters.agy import print_timeout_seconds

        manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
        pins = {
            cfg["conditions"]["print_timeout"]
            for cfg in manifest["configurations"].values()
            if isinstance(cfg, dict) and (cfg.get("conditions") or {}).get("print_timeout")
        }
        self.assertTrue(pins, "no --print-timeout pinned anywhere in the manifest")
        worst = max(print_timeout_seconds(p) for p in pins)
        for task_dir, (_mkey, secs) in BUDGETS.items():
            with self.subTest(task=task_dir):
                self.assertGreater(secs, worst)


class BudgetResolution(unittest.TestCase):
    """resolve_agent_timeout: agree, refuse, or fall back — never guess."""

    def test_agreeing_declarations_resolve(self) -> None:
        self.assertEqual(
            runner.resolve_agent_timeout("t", {"agent_timeout_s": 2700},
                                         {"agent_timeout_s": 2700}), 2700)

    def test_one_sided_declaration_resolves(self) -> None:
        self.assertEqual(
            runner.resolve_agent_timeout("t", {"agent_timeout_s": 900}, {}), 900)
        self.assertEqual(
            runner.resolve_agent_timeout("t", {}, {"agent_timeout_s": 900}), 900)

    def test_absent_from_both_falls_back_to_the_adapter_default(self) -> None:
        self.assertEqual(runner.resolve_agent_timeout("t", {}, {}),
                         runner.DEFAULT_AGENT_TIMEOUT_S)

    def test_a_disagreement_is_refused_not_resolved_by_precedence(self) -> None:
        with self.assertRaises(runner.RunnerError) as ctx:
            runner.resolve_agent_timeout("t", {"agent_timeout_s": 1200},
                                         {"agent_timeout_s": 7200})
        self.assertIn("disagrees", str(ctx.exception))

    def test_a_nonsense_value_is_refused(self) -> None:
        for bad in (0, -1, "1200", 12.5, True):
            with self.subTest(value=bad):
                with self.assertRaises(runner.RunnerError):
                    runner.resolve_agent_timeout("t", {"agent_timeout_s": bad}, {})


class ContainerNaming(unittest.TestCase):
    """A container you cannot address is a container you cannot kill."""

    def test_argv_carries_the_name(self) -> None:
        argv = cexec.docker_run_argv("img", ["true"], name="lab-agent-x-main")
        self.assertIn("--name", argv)
        self.assertEqual(argv[argv.index("--name") + 1], "lab-agent-x-main")
        self.assertLess(argv.index("--name"), argv.index("img"))

    def test_no_name_means_no_flag(self) -> None:
        self.assertNotIn("--name", cexec.docker_run_argv("img", ["true"]))

    def test_host_mode_has_no_container_to_name(self) -> None:
        self.assertIsNone(cexec.leg_container_name(None, "main"))

    def test_each_leg_gets_its_own_handle(self) -> None:
        launch = cexec.ContainerLaunch(
            image="img", name_prefix=cexec.agent_container_prefix(
                "w3-sqlfluff__P1__rep1__20260820T101010"))
        econ = cexec.leg_container_name(launch, "economical_attempt")
        strong = cexec.leg_container_name(launch, "strong_attempt")
        self.assertNotEqual(econ, strong)
        for name in (econ, strong):
            self.assertTrue(name.startswith("lab-agent-w3-sqlfluff"))
            self.assertLessEqual(len(name), 120)


class _StubSpawn:
    """Captures how the adapter called spawn_with_timeout, and times out."""

    def __init__(self) -> None:
        self.kwargs = None

    def __call__(self, argv, **kwargs):
        self.kwargs = dict(kwargs, argv=list(argv))
        return cexec.SpawnResult(returncode=None, stdout="", stderr="",
                                 timed_out=True, container="killed")


class AdaptersHonourTheBudget(unittest.TestCase):
    """Both adapters pass the task's budget and the leg's container to the kill seam."""

    def setUp(self) -> None:
        self.events = []
        self.launch = cexec.ContainerLaunch(
            image="lab-subject-agent/x:abc",
            name_prefix=cexec.agent_container_prefix("w3__P0__rep1__20260820T0000"))
        os.environ["LAB_ALLOW_SPEND"] = "1"
        self.addCleanup(os.environ.pop, "LAB_ALLOW_SPEND", None)

    def _emit(self, event_type, **payload):
        self.events.append((event_type, payload))

    def _failure(self):
        return next(p for t, p in self.events if t == "failure")

    def test_claude_adapter(self) -> None:
        from harness.adapters import claude_code

        stub = _StubSpawn()
        orig, claude_code.spawn_with_timeout = claude_code.spawn_with_timeout, stub
        self.addCleanup(setattr, claude_code, "spawn_with_timeout", orig)

        adapter = claude_code.ClaudeCodeAdapter()
        adapter.container = self.launch
        spec = AttemptSpec("main", "solver", ResolvedModel(
            provider="google_vertex", model_or_selector="m", model_id="m",
            cost_basis="marginal_api_cost", product="A",
            product_surface="controlled_api"), "prompt", timeout_s=7200)
        adapter.run_attempt(spec, "/nonexistent", self._emit)

        self.assertEqual(stub.kwargs["timeout_s"], 7200)
        self.assertEqual(stub.kwargs["container_name"], "lab-agent-w3__p0__rep1__20260820t0000-main")
        fail = self._failure()
        self.assertEqual(fail["category"], "claude_timeout")
        self.assertEqual(fail["timeout_s"], 7200)
        self.assertEqual(fail["container_disposition"], "killed")

    def test_agy_adapter(self) -> None:
        from harness.adapters import agy

        stub = _StubSpawn()
        orig, agy.spawn_with_timeout = agy.spawn_with_timeout, stub
        self.addCleanup(setattr, agy, "spawn_with_timeout", orig)
        orig_ver, agy.cli_version = agy.cli_version, lambda *a, **k: "1.1.13"
        self.addCleanup(setattr, agy, "cli_version", orig_ver)

        adapter = agy.AgyAdapter()
        adapter.container = self.launch
        spec = AttemptSpec("main", "solver", ResolvedModel(
            provider="google", model_or_selector="Gemini 3.7 Flash (High)",
            model_id=None, cost_basis="marginal_api_cost", product="B",
            product_surface="product_blackbox", print_timeout="15m0s"),
            "prompt", timeout_s=2700)
        adapter.run_attempt(spec, "/nonexistent", self._emit)

        self.assertEqual(stub.kwargs["timeout_s"], 2700)
        self.assertEqual(stub.kwargs["container_name"], "lab-agent-w3__p0__rep1__20260820t0000-main")
        fail = self._failure()
        self.assertEqual(fail["category"], "agy_timeout")
        self.assertEqual(fail["container_disposition"], "killed")

    def test_agy_refuses_a_budget_under_the_products_own_timeout(self) -> None:
        """The invariant follows the EFFECTIVE budget, not the module default."""
        from harness.adapters.agy import build_command

        build_command("p", "sel", "15m0s", kill_timeout_s=1200)  # 900 < 1200: fine
        with self.assertRaises(ValueError):
            build_command("p", "sel", "15m0s", kill_timeout_s=600)


@unittest.skipUnless(_docker_ok(), "docker daemon unavailable")
class TheContainerActuallyDies(unittest.TestCase):
    """The regression test for the orphan: a real long-running container is killed.

    The fake long-running agent is ``sleep 600`` in an already-built local gate
    image, offline (``--network=none``). No product CLI runs and nothing can spend.
    """

    NAME = "lab-test-orphan-probe"

    def setUp(self) -> None:
        self.image = _a_local_gate_image()
        if not self.image:
            self.skipTest("no local lab-subject/* image to run a sleep in")
        self.addCleanup(cexec.kill_container, self.NAME)
        self.addCleanup(cexec.kill_container, self.NAME + "-control")

    def test_the_container_actually_dies(self) -> None:
        argv = cexec.docker_run_argv(
            self.image, ["sleep", "600"], workdir="/", name=self.NAME)
        result = cexec.spawn_with_timeout(
            argv, cwd=None, env=dict(os.environ), timeout_s=8,
            container_name=self.NAME)

        self.assertTrue(result.timed_out, "the probe should have hit the timeout")
        self.assertEqual(result.container, "killed",
                         f"kill_container did not reap {self.NAME}")
        self.assertFalse(cexec.container_is_running(self.NAME),
                         "the container OUTLIVED its timeout — the orphan is back")

    def test_negative_control_the_old_path_leaves_an_orphan(self) -> None:
        """Without the kill, the container survives — i.e. the bug was real.

        This is what ``subprocess.run(timeout=...)`` alone did: the ``docker run``
        client dies, the daemon-side container does not. If this test ever fails,
        the fix above has stopped proving anything and both should be re-examined.
        """
        name = self.NAME + "-control"
        argv = cexec.docker_run_argv(
            self.image, ["sleep", "600"], workdir="/", name=name)
        with self.assertRaises(subprocess.TimeoutExpired):
            subprocess.run(argv, capture_output=True, text=True,  # noqa: S603
                           check=False, timeout=8)
        self.assertTrue(cexec.container_is_running(name),
                        "expected the unkilled container to still be running")
        self.assertEqual(cexec.kill_container(name), "killed")
        self.assertFalse(cexec.container_is_running(name))

    def test_killing_something_already_gone_is_not_an_error(self) -> None:
        self.assertEqual(cexec.kill_container("lab-test-no-such-container"),
                         "already_gone")


if __name__ == "__main__":
    unittest.main()
