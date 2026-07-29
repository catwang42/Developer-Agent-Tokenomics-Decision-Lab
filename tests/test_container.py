"""Unit tests for the container-exec mechanism (offline; no Docker, no spend).

Every test asserts on PURE command construction — ``docker_run_argv``,
``subject_image_tag``, ``resolve_spawn`` — so what the runner/adapters will actually
exec is pinned without a Docker daemon or any model API call.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.container.exec import (  # noqa: E402
    NETWORK_NONE,
    ContainerLaunch,
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


if __name__ == "__main__":
    unittest.main()
