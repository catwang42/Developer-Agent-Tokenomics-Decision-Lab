"""Unit tests for the container-exec mechanism (offline; no Docker, no spend).

Every test asserts on PURE command construction — ``docker_run_argv``,
``subject_image_tag``, ``resolve_spawn`` — so what the runner/adapters will actually
exec is pinned without a Docker daemon or any model API call.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.container.exec import (  # noqa: E402
    CONTAINER_ADC_PATH,
    CONTAINER_GCLOUD_DIR,
    NETWORK_NONE,
    TARGET_AGENT,
    TARGET_GATE,
    ContainerLaunch,
    agent_container_env,
    agent_image_tag,
    agent_volume_name,
    docker_run_argv,
    resolve_spawn,
    subject_image_tag,
)


class DockerRunArgv(unittest.TestCase):
    def test_defaults_to_offline_network(self) -> None:
        argv = docker_run_argv("img", ["bash", "x.sh"])
        self.assertEqual(argv[:5], ["docker", "run", "--rm", "--network", NETWORK_NONE])
        self.assertEqual(argv[-3:], ["img", "bash", "x.sh"])

    def test_mounts_workdir_and_sorted_env(self) -> None:
        argv = docker_run_argv(
            "img", ["run"], mounts=[("/h", "/out", "rw"), ("/a", "/b", "ro")],
            workdir="/subject", env={"B": "2", "A": "1"},
        )
        self.assertIn("-v", argv)
        self.assertEqual(argv[argv.index("/h:/out:rw") - 1], "-v")
        self.assertIn("/a:/b:ro", argv)
        self.assertEqual(["/subject"], argv[argv.index("-w") + 1: argv.index("-w") + 2])
        # env is emitted in sorted key order (deterministic command).
        self.assertLess(argv.index("A=1"), argv.index("B=2"))

    def test_explicit_network_is_passed_verbatim(self) -> None:
        # A CP-SPEND egress network name flows through unchanged.
        argv = docker_run_argv("img", ["c"], network="lab-egress-model-only")
        self.assertEqual(argv[argv.index("--network") + 1], "lab-egress-model-only")

    def test_empty_image_rejected(self) -> None:
        with self.assertRaises(ValueError):
            docker_run_argv("", ["c"])

    def test_no_remove_flag(self) -> None:
        self.assertNotIn("--rm", docker_run_argv("img", ["c"], remove=False))


class ImageTag(unittest.TestCase):
    def test_deterministic_and_pin_scoped(self) -> None:
        pin = "30b68e1e881462b2f4164ea09ab4c4f5699c7b0b"
        t1 = subject_image_tag("w1-realworld-mapper-tests", pin)
        t2 = subject_image_tag("w1-realworld-mapper-tests", pin)
        self.assertEqual(t1, t2)
        self.assertEqual(t1, "lab-subject/w1-realworld-mapper-tests:30b68e1e8814")

    def test_repin_changes_tag(self) -> None:
        a = subject_image_tag("t", "a" * 40)
        b = subject_image_tag("t", "b" * 40)
        self.assertNotEqual(a, b)

    def test_slugifies_unsafe_task_id(self) -> None:
        tag = subject_image_tag("Weird Task/ID!", "abcdef123456")
        repo = tag.split(":", 1)[0]
        self.assertTrue(repo.startswith("lab-subject/"))
        self.assertNotIn(" ", repo)
        self.assertNotIn("!", repo)


class ResolveSpawn(unittest.TestCase):
    def test_host_mode_runs_in_subject_dir(self) -> None:
        argv, cwd = resolve_spawn(None, ["claude", "-p", "hi"], "/subj")
        self.assertEqual(argv, ["claude", "-p", "hi"])
        self.assertEqual(cwd, "/subj")

    def test_container_mode_wraps_in_docker_run_offline(self) -> None:
        launch = ContainerLaunch(image="lab-subject/x:pin")
        argv, cwd = resolve_spawn(launch, ["claude", "-p", "hi"], "/subj")
        self.assertIsNone(cwd)  # docker -w sets the workdir; host cwd unused
        self.assertEqual(argv[:2], ["docker", "run"])
        self.assertEqual(argv[argv.index("--network") + 1], "none")
        self.assertEqual(argv[-4:], ["lab-subject/x:pin", "claude", "-p", "hi"])

    def test_container_mode_honours_egress_network(self) -> None:
        launch = ContainerLaunch(image="img", network="lab-egress")
        argv, _ = resolve_spawn(launch, ["agy", "run"], "/subj")
        self.assertEqual(argv[argv.index("--network") + 1], "lab-egress")


class AgentImageTag(unittest.TestCase):
    """The agent image is a DIFFERENT repository from the gate image (SPEC §6 item 1).

    Same tag on the same repo would let a task-material-bearing gate image be
    launched where an agent image was intended — i.e. hand the agent the answer.
    """

    def test_agent_and_gate_tags_never_collide(self) -> None:
        pin = "30b68e1e881462b2f4164ea09ab4c4f5699c7b0b"
        gate = subject_image_tag("w1-realworld-mapper-tests", pin)
        agent = agent_image_tag("w1-realworld-mapper-tests", pin)
        self.assertNotEqual(gate, agent)
        self.assertTrue(gate.startswith("lab-subject/"))
        self.assertTrue(agent.startswith("lab-subject-agent/"))
        self.assertEqual(gate.split(":")[1], agent.split(":")[1])  # same pin

    def test_build_targets_are_distinct(self) -> None:
        self.assertEqual(TARGET_GATE, "subject-gate")
        self.assertEqual(TARGET_AGENT, "subject-agent")


class AgentLaunchSpawn(unittest.TestCase):
    """What the agent container is actually launched with (pure argv; no daemon)."""

    def _launch(self) -> ContainerLaunch:
        return ContainerLaunch(
            image="lab-subject-agent/t:pin", network="lab-egress",
            mounts=(("/host/gcloud", CONTAINER_GCLOUD_DIR, "ro"),),
            env={"CLAUDE_CODE_USE_VERTEX": "1",
                 "GOOGLE_APPLICATION_CREDENTIALS": CONTAINER_ADC_PATH},
            agent_volume="lab-subject-work-run1",
        )

    def test_credentials_are_mounted_read_only(self) -> None:
        argv, _ = resolve_spawn(self._launch(), ["claude", "-p", "x"], "/subj")
        self.assertIn(f"/host/gcloud:{CONTAINER_GCLOUD_DIR}:ro", argv)

    def test_vertex_env_is_passed_through(self) -> None:
        argv, _ = resolve_spawn(self._launch(), ["claude", "-p", "x"], "/subj")
        self.assertIn("CLAUDE_CODE_USE_VERTEX=1", argv)
        self.assertIn(f"GOOGLE_APPLICATION_CREDENTIALS={CONTAINER_ADC_PATH}", argv)

    def test_agent_volume_mounted_rw_at_subject_root(self) -> None:
        # The agent's edits must survive the container so the GATE container can
        # grade them; a read-only or absent volume would silently grade the
        # pristine baked tree and score every run as a no-op.
        argv, _ = resolve_spawn(self._launch(), ["claude", "-p", "x"], "/subj")
        self.assertIn("lab-subject-work-run1:/subject:rw", argv)

    def test_no_harness_env_pointers_leak_into_the_container(self) -> None:
        # FIX B, enforced at the container boundary: the agent container's env is
        # ENUMERATED, so a harness pointer set in the parent shell cannot ride in.
        os.environ["TASK_DIR"] = "/lab/tasks/suite/W1-test-generation"
        os.environ["HIDDEN_TESTS_DIR"] = "/lab/tasks/suite/W1-test-generation/hidden"
        try:
            env = agent_container_env()
        finally:
            del os.environ["TASK_DIR"], os.environ["HIDDEN_TESTS_DIR"]
        self.assertNotIn("TASK_DIR", env)
        self.assertNotIn("HIDDEN_TESTS_DIR", env)

    def test_absent_routing_env_is_omitted_not_guessed(self) -> None:
        # CLAUDE.md rule 3 at the config layer: a missing project/region is absent,
        # never defaulted — a guessed value would bill and measure the wrong thing.
        saved = os.environ.pop("ANTHROPIC_VERTEX_PROJECT_ID", None)
        try:
            self.assertNotIn("ANTHROPIC_VERTEX_PROJECT_ID", agent_container_env())
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_VERTEX_PROJECT_ID"] = saved

    def test_volume_name_is_run_scoped(self) -> None:
        a = agent_volume_name("task__C1__rep1__20260816T000000")
        b = agent_volume_name("task__C1__rep2__20260816T000000")
        self.assertNotEqual(a, b)
        self.assertTrue(a.startswith("lab-subject-work-"))


class TaskMaterialAssertion(unittest.TestCase):
    """The build-time exclusion assertion (SPEC §6 item 1).

    Exercised directly against the script that is baked into the agent image, so
    these tests pin the same logic the ``docker build`` step runs.
    """

    SCRIPT = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "harness", "container",
        "assert-no-task-material.sh"))

    def _run(self, root: str):
        return subprocess.run(
            ["bash", self.SCRIPT, root], capture_output=True, text=True, check=False)

    def test_clean_tree_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "src", "tests"))
            with open(os.path.join(tmp, "package.json"), "w", encoding="utf-8") as fh:
                fh.write("{}")
            self.assertEqual(self._run(tmp).returncode, 0)

    def test_planted_canonical_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "canonical"))
            with open(os.path.join(tmp, "canonical", "answer.patch"), "w",
                      encoding="utf-8") as fh:
                fh.write("the reference solution")
            proc = self._run(tmp)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("canonical", proc.stderr)

    def test_planted_hidden_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "deep", "nest", "hidden"))
            self.assertEqual(self._run(tmp).returncode, 1)

    def test_planted_task_yaml_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "task.yaml"), "w", encoding="utf-8") as fh:
                fh.write("task_id: x")
            self.assertEqual(self._run(tmp).returncode, 1)

    def test_finds_material_anywhere_not_just_declared_paths(self) -> None:
        # The failure this exists to catch is material arriving somewhere nobody
        # expected — the 2026-07-19 W1 image shipped canonical/ past .dockerignore.
        with tempfile.TemporaryDirectory() as tmp:
            buried = os.path.join(tmp, "node_modules", "x", "share", "canonical")
            os.makedirs(buried)
            proc = self._run(tmp)
            self.assertEqual(proc.returncode, 1)
            self.assertIn("node_modules", proc.stderr)


if __name__ == "__main__":
    unittest.main()
