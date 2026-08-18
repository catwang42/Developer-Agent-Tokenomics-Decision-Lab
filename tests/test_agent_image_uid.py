"""Regression tests for the agent image's baked uid (batch-1 halt at plan index 19).

Why this file exists: ``build-subject-image.sh`` passed ``SUBJECT_UID=$(id -u)``, but
the runner's mid-batch auto-build (``_ensure_image`` via ``_ensure_agent_launch``)
passed NO build args at all. Pre-built tasks were fine; the first task whose image the
runner built itself — W4, plan index 19 — fell through to the Dockerfile's
``ARG SUBJECT_UID=1001`` default. The 0600 credential mounts are owned by the host
user and a bind mount passes the numeric owner through untranslated, so the container
user could not read them; ``assert_image_uid_matches_host`` refused and the batch
stopped after 15 completed runs. The same auto-built image also labelled
``lab.cli.agy.version=unavailable`` while carrying the vendored binary — the uid guard
masked a second, quieter defect that would have written ``unavailable`` into the
identity of every billed Product-B leg.

The rule these tests encode: **whatever builds an agent image, the uid recorded in it
equals the invoking user's, and the CLI pins recorded in it come from the manifest.**

Offline: no docker, no build, no spend. ``build_subject_image`` is replaced by a
recorder, and the Dockerfile's own ``ARG``/``LABEL`` lines are parsed to model what a
real build would stamp — so the "recorded uid" asserted here is computed the way
Docker computes it, from the args the caller actually passes, rather than restated.
"""

from __future__ import annotations

import os
import pathlib
import re
import sys
import unittest
import unittest.mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness.container import agent_build_args  # noqa: E402
from harness.container import exec as container_exec  # noqa: E402
from harness.runner import run as runner  # noqa: E402

DOCKERFILE = ROOT / "harness" / "container" / "Dockerfile.subject"
BUILD_SCRIPT = ROOT / "harness" / "container" / "build-subject-image.sh"

MANIFEST = {
    "subject_isolation": {
        "agent_leg": {
            "claude_cli_version": "9.9.999-SYNTHETIC",
            "agy_version": "1.1.13-SYNTHETIC",
            "agy_sha256": "0" * 64,
        }
    }
}


def dockerfile_arg_default(name: str) -> str:
    """The ``ARG <name>=<default>`` value in the agent stage — what a caller that
    passes nothing gets. Read from the Dockerfile so this stays true if it changes."""
    stage = DOCKERFILE.read_text(encoding="utf-8").split("AS subject-agent", 1)[1]
    match = re.search(rf"^ARG {re.escape(name)}=(.*)$", stage, re.MULTILINE)
    assert match, f"no ARG {name} default in the subject-agent stage"
    return match.group(1).strip()


def label_from_build_args(build_args, label: str) -> str:
    """Model Docker: resolve the agent stage's LABEL for ``label`` against the args
    the caller passed, falling back to the stage's own ARG defaults."""
    stage = DOCKERFILE.read_text(encoding="utf-8").split("AS subject-agent", 1)[1]
    match = re.search(rf'{re.escape(label)}="([^"]*)"', stage)
    assert match, f"no {label} label in the subject-agent stage"
    value = match.group(1)
    for ref in re.findall(r"\$\{(\w+)\}", value):
        resolved = (build_args or {}).get(ref)
        if resolved is None:
            resolved = dockerfile_arg_default(ref)
        value = value.replace("${" + ref + "}", str(resolved))
    return value


class BuildArgsResolveToThisHost(unittest.TestCase):
    """The one resolver both builders call."""

    def test_uid_and_gid_are_the_invoking_user_s(self) -> None:
        args = agent_build_args(MANIFEST, str(ROOT))
        self.assertEqual(args["SUBJECT_UID"], str(os.getuid()))
        self.assertEqual(args["SUBJECT_GID"], str(os.getgid()))

    def test_it_never_returns_the_dockerfile_default_by_accident(self) -> None:
        # Guards the case that actually happened: a fixed 1001 that is nobody's uid.
        # Skipped rather than asserted-against if this host really is uid 1001 —
        # a literal comparison would then pass vacuously (the same trap noted in
        # tests/test_container.py::AgentImageUidMatchesHost).
        default = dockerfile_arg_default("SUBJECT_UID")
        if str(os.getuid()) == default:
            self.skipTest(f"this host is uid {default}; the check would self-match")
        self.assertNotEqual(agent_build_args(MANIFEST, str(ROOT))["SUBJECT_UID"], default)

    def test_the_product_cli_pins_come_from_the_manifest(self) -> None:
        args = agent_build_args(MANIFEST, str(ROOT))
        self.assertEqual(args["CLAUDE_CLI_VERSION"], "9.9.999-SYNTHETIC")
        self.assertEqual(args["AGY_VERSION"], "1.1.13-SYNTHETIC")
        self.assertEqual(args["AGY_SHA256"], "0" * 64)

    def test_a_pinned_product_b_makes_its_absence_a_build_failure(self) -> None:
        # AGY_REQUIRED=1 turns "vendor/agy is missing" into a failed build instead of
        # an image that runs but records agy as unavailable on a run that was billed.
        args = agent_build_args(MANIFEST, str(ROOT))
        self.assertEqual(args["AGY_REQUIRED"], "1")

    def test_no_product_b_pin_and_no_binary_leaves_it_optional(self) -> None:
        empty = {"subject_isolation": {"agent_leg": {"claude_cli_version": "1.0.0"}}}
        args = agent_build_args(empty, "/nonexistent-repo-root-SYNTHETIC")
        self.assertEqual(args["AGY_REQUIRED"], "0")
        self.assertEqual(args["AGY_VERSION"], "unavailable")

    def test_an_unpinned_product_a_cli_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            agent_build_args({"subject_isolation": {"agent_leg": {}}}, str(ROOT))


class AutoBuildStampsTheHostUid(unittest.TestCase):
    """The runner's own build path — the one that had no args at all."""

    def setUp(self) -> None:
        self.builds: list = []
        for name, stub in (
            ("image_exists", lambda tag: False),   # force the auto-build path
            ("build_subject_image", self._record),
            ("create_volume", lambda name: None),  # offline: no stray docker volume
        ):
            patch = unittest.mock.patch.object(runner, name, stub)
            patch.start()
            self.addCleanup(patch.stop)

    def _record(self, task_dir_rel, tag, repo_root, dockerfile, *, target,
                build_args=None, **kwargs):
        self.builds.append({"tag": tag, "target": target,
                            "build_args": dict(build_args or {})})

        class _Proc:
            returncode = 0
        return _Proc()

    def _task(self) -> runner.Task:
        return runner.Task(
            task_dir=str(ROOT / "tasks" / "suite" / "W4-complex-bugfix"),
            task_id="w4-realworld-missing-user-id", task_suite_version="test",
            prompt="", contamination_tier=None, hidden_test_hash=None,
            gate_type="solution", task_dir_rel="tasks/suite/W4-complex-bugfix",
            pinned_commit="88b258ce54aa0000000000000000000000000000",
        )

    def _agent_build(self) -> dict:
        with unittest.mock.patch.object(
            container_exec, "image_labels",
            lambda tag: {"lab.image.subject_uid": str(os.getuid())},
        ):
            runner._ensure_agent_launch(self._task(), "run-SYNTHETIC", None, MANIFEST)
        return [b for b in self.builds if b["target"] == runner.TARGET_AGENT][0]

    def test_the_recorded_uid_equals_the_invoking_user(self) -> None:
        """The batch-1 regression, stated as the invariant it broke."""
        build = self._agent_build()
        recorded = label_from_build_args(build["build_args"], "lab.image.subject_uid")
        self.assertEqual(recorded, str(os.getuid()))
        gid = label_from_build_args(build["build_args"], "lab.image.subject_gid")
        self.assertEqual(gid, str(os.getgid()))

    def test_an_image_built_this_way_passes_the_guard_that_halted_the_batch(self) -> None:
        build = self._agent_build()
        labels = {
            "lab.image.subject_uid": label_from_build_args(
                build["build_args"], "lab.image.subject_uid"),
        }
        with unittest.mock.patch.object(container_exec, "image_labels",
                                        lambda tag: labels):
            container_exec.assert_image_uid_matches_host(build["tag"])  # must not raise

    def test_passing_no_build_args_is_what_used_to_fail_and_still_would(self) -> None:
        """The paired negative: the ONLY difference is the build args, so deleting
        them can never again reach a live batch un-caught."""
        default_uid = dockerfile_arg_default("SUBJECT_UID")
        if str(os.getuid()) == default_uid:
            self.skipTest(f"this host is uid {default_uid}; the check would self-match")
        labels = {"lab.image.subject_uid": label_from_build_args(None,
                                                                "lab.image.subject_uid")}
        self.assertEqual(labels["lab.image.subject_uid"], default_uid)
        with unittest.mock.patch.object(container_exec, "image_labels",
                                        lambda tag: labels):
            with self.assertRaises(PermissionError):
                container_exec.assert_image_uid_matches_host("SYNTHETIC-image")

    def test_the_cli_pins_reach_the_auto_build_too(self) -> None:
        # The second defect the uid guard masked: an auto-built image labelled
        # agy unavailable would have stamped that into every Product-B leg.
        build = self._agent_build()
        self.assertEqual(build["build_args"]["AGY_VERSION"], "1.1.13-SYNTHETIC")
        self.assertEqual(build["build_args"]["CLAUDE_CLI_VERSION"], "9.9.999-SYNTHETIC")
        agy_label = label_from_build_args(build["build_args"], "lab.cli.agy.version")
        self.assertEqual(agy_label, "1.1.13-SYNTHETIC")

    def test_the_gate_image_is_unaffected(self) -> None:
        # The gate grades as root by design; only the agent stage takes a uid.
        runner._ensure_gate_launch(self._task())
        gate = [b for b in self.builds if b["target"] == runner.TARGET_GATE][0]
        self.assertNotIn("SUBJECT_UID", gate["build_args"])

    def test_an_unpinned_manifest_refuses_before_the_build(self) -> None:
        with self.assertRaises(runner.RunnerError):
            runner._ensure_agent_launch(self._task(), "run-SYNTHETIC", None,
                                        {"subject_isolation": {"agent_leg": {}}})
        self.assertEqual(self.builds, [])


class BothBuildersUseTheSameResolver(unittest.TestCase):
    """Drift between the two callers IS the defect; no test can allow a second copy."""

    def test_the_shell_script_calls_the_shared_resolver(self) -> None:
        text = BUILD_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("from harness.container import agent_build_args", text)

    def test_the_shell_script_computes_no_build_args_of_its_own(self) -> None:
        text = BUILD_SCRIPT.read_text(encoding="utf-8")
        for stale in ("SUBJECT_UID=$(id -u)", "SUBJECT_GID=$(id -g)",
                      "AGY_REQUIRED=0", "AGY_REQUIRED=1"):
            self.assertNotIn(stale, text,
                             f"{stale!r} is a second source of truth for a build arg")


if __name__ == "__main__":
    unittest.main()
