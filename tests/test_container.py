"""Unit tests for the container-exec mechanism (offline; no Docker, no spend).

Every test asserts on PURE command construction — ``docker_run_argv``,
``subject_image_tag``, ``resolve_spawn`` — so what the runner/adapters will actually
exec is pinned without a Docker daemon or any model API call.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.container import exec as container_exec  # noqa: E402
from harness.container.exec import (  # noqa: E402
    CONTAINER_ADC_PATH,
    CONTAINER_AGY_CRED_DIR,
    CONTAINER_AGY_SETTINGS,
    CONTAINER_AGY_TOKEN,
    CONTAINER_GCLOUD_DIR,
    HOST_AGY_STATE_REL,
    NETWORK_NONE,
    TARGET_AGENT,
    TARGET_GATE,
    ContainerLaunch,
    agent_container_env,
    agent_credential_mounts,
    agent_image_tag,
    agent_volume_name,
    docker_run_argv,
    host_agy_state_dir,
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


class AgentImageRunsNonRoot(unittest.TestCase):
    """SMOKE-1: Product A's CLI refuses --dangerously-skip-permissions under uid 0.

    Asserted against the Dockerfile rather than a built image so the check runs in
    the offline gate: a rebuild that drops the USER line fails here, not three
    hours into a live batch.
    """

    DOCKERFILE = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "harness", "container", "Dockerfile.subject"))

    def setUp(self) -> None:
        with open(self.DOCKERFILE, encoding="utf-8") as fh:
            self.text = fh.read()
        self.agent_stage = self.text.split("AS subject-agent", 1)[1]

    def test_agent_stage_drops_to_a_non_root_user(self) -> None:
        self.assertIn("\nUSER lab\n", self.agent_stage)
        self.assertIn("--uid \"${SUBJECT_UID}\"", self.agent_stage)
        self.assertNotIn("SUBJECT_UID=0", self.agent_stage)

    def test_subject_tree_is_owned_by_that_user(self) -> None:
        # Docker seeds the per-run named volume from this path preserving
        # ownership; root-owned content would leave the agent unable to write.
        self.assertIn("--chown=lab:lab /export/subject /subject", self.agent_stage)

    def test_home_is_writable_by_that_user(self) -> None:
        self.assertIn("ENV HOME=/home/lab", self.agent_stage)

    def test_gate_stage_is_unaffected(self) -> None:
        # The gate grades as root on purpose: it mounts a volume whose files the
        # agent owns, and its posture (task material present, --network=none) is
        # the batch-2 recorded one. Only the agent stage changed.
        gate_stage = self.text.split("AS subject-gate", 1)[1].split("AS subject-export")[0]
        self.assertNotIn("USER ", gate_stage)

    def test_agy_is_reached_only_through_the_wrapper(self) -> None:
        # The vendored binary is installed OFF PATH, so no invocation route skips
        # the credential seeding and state isolation (SMOKE-2 / SMOKE-3).
        self.assertIn("/usr/local/lib/lab/agy.real", self.agent_stage)
        self.assertIn("COPY harness/container/agy-headless.sh /usr/local/bin/agy",
                      self.agent_stage)
        self.assertNotIn("/opt/lab-vendor/agy /usr/local/bin/agy", self.agent_stage)

    def test_the_uid_is_recorded_so_a_mismatch_is_detectable(self) -> None:
        # The tag pins task + commit, not the builder, so an image built by another
        # account is a legal cache hit. Without the label the runner cannot tell.
        self.assertIn('lab.image.subject_uid="${SUBJECT_UID}"', self.agent_stage)

    def test_the_build_script_matches_the_container_user_to_the_host(self) -> None:
        # Non-root (SMOKE-1) and reading 0600 credential mounts (SMOKE-2) are only
        # simultaneously satisfiable at the operator's own uid: a bind mount carries
        # the host's numeric owner through untranslated.
        script = os.path.join(os.path.dirname(self.DOCKERFILE), "build-subject-image.sh")
        with open(script, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn('--build-arg "SUBJECT_UID=$(id -u)"', text)
        self.assertIn('--build-arg "SUBJECT_GID=$(id -g)"', text)


class AgentImageUidMatchesHost(unittest.TestCase):
    """A mismatched image must be refused BEFORE a billed run, not during one."""

    def _with_labels(self, labels):
        original = container_exec.image_labels
        container_exec.image_labels = lambda tag: labels
        self.addCleanup(setattr, container_exec, "image_labels", original)

    def test_a_host_matched_image_is_accepted(self) -> None:
        self._with_labels({"lab.image.subject_uid": str(os.getuid())})
        container_exec.assert_image_uid_matches_host("SYNTHETIC-image")
        self.assertEqual(container_exec.image_subject_uid("SYNTHETIC-image"),
                         os.getuid())

    def test_a_foreign_uid_is_refused_with_both_uids_named(self) -> None:
        self._with_labels({"lab.image.subject_uid": "1001"})
        with self.assertRaises(PermissionError) as ctx:
            container_exec.assert_image_uid_matches_host("SYNTHETIC-image")
        self.assertIn("1001", str(ctx.exception))
        self.assertIn(str(os.getuid()), str(ctx.exception))
        self.assertIn("build-subject-image.sh", str(ctx.exception))

    def test_an_unlabelled_image_is_refused_as_stale(self) -> None:
        # Pre-fix images have no label at all; treating that as "probably fine"
        # would reintroduce the failure the label exists to catch.
        self._with_labels({"lab.cli.claude.version": "2.1.233"})
        with self.assertRaises(PermissionError):
            container_exec.assert_image_uid_matches_host("SYNTHETIC-image")
        self.assertIsNone(container_exec.image_subject_uid("SYNTHETIC-image"))


class AgyCredentialMounts(unittest.TestCase):
    """SMOKE-2/3: what of Product B's host state crosses into the container."""

    def test_state_dir_is_where_agy_actually_looks(self) -> None:
        # agy resolves its store from $HOME; there is no config-dir override in the
        # 1.1.13 binary, which is why the earlier ~/.gemini -> /creds/gemini mount
        # was invisible to it.
        self.assertEqual(HOST_AGY_STATE_REL, os.path.join(".gemini", "antigravity-cli"))
        self.assertTrue(host_agy_state_dir().endswith(HOST_AGY_STATE_REL))

    def test_only_named_files_are_mounted_never_the_state_tree(self) -> None:
        # The tree also holds brain/ (prior-session memory naming this repo's
        # absolute host path). Mounting it whole is what SMOKE-3 fed on.
        state_dir = host_agy_state_dir()
        for src, dst, mode in agent_credential_mounts():
            self.assertEqual(mode, "ro")
            if src.startswith(state_dir):
                self.assertNotEqual(os.path.normpath(src), os.path.normpath(state_dir))
                self.assertTrue(os.path.isfile(src))
                self.assertTrue(dst.startswith(CONTAINER_AGY_CRED_DIR + "/"))

    def test_mount_targets_are_the_paths_the_wrapper_reads(self) -> None:
        self.assertEqual(CONTAINER_AGY_TOKEN,
                         f"{CONTAINER_AGY_CRED_DIR}/antigravity-oauth-token")
        self.assertEqual(CONTAINER_AGY_SETTINGS,
                         f"{CONTAINER_AGY_CRED_DIR}/settings.json")


class AgyHeadlessWrapper(unittest.TestCase):
    """The in-container agy entry point, exercised offline with a fake product.

    No Docker and no network: the script's two decisions (refuse without a
    credential; hand the product a throwaway HOME) are shell logic, and this is
    where they are pinned.
    """

    SCRIPT = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "harness", "container", "agy-headless.sh"))

    def _fake_product(self, tmp: str) -> str:
        """A stand-in that reports the environment it was exec'd with."""
        path = os.path.join(tmp, "agy.real")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write('#!/bin/sh\n'
                     'echo "HOME=$HOME"\n'
                     'echo "AUTOUPDATE=$AGY_CLI_DISABLE_AUTO_UPDATE"\n'
                     'echo "ARGS=$*"\n'
                     'cat "$HOME/.gemini/antigravity-cli/settings.json"\n'
                     'ls "$HOME/.gemini/antigravity-cli"\n')
        os.chmod(path, 0o755)
        return path

    def _run(self, tmp: str, args, *, with_token: bool = True,
             settings: str = None, real: bool = True):
        creds = os.path.join(tmp, "creds")
        os.makedirs(creds, exist_ok=True)
        if with_token:
            with open(os.path.join(creds, "antigravity-oauth-token"), "w",
                      encoding="utf-8") as fh:
                fh.write('{"auth_method": "gcp", "token": {"SYNTHETIC": true}}')
        if settings is not None:
            with open(os.path.join(creds, "settings.json"), "w", encoding="utf-8") as fh:
                fh.write(settings)
        env = dict(os.environ)
        env["LAB_AGY_CRED_DIR"] = creds
        env["LAB_AGY_REAL"] = (self._fake_product(tmp) if real
                               else os.path.join(tmp, "absent"))
        workspace = os.path.join(tmp, "subject")
        os.makedirs(workspace, exist_ok=True)
        return subprocess.run(["sh", self.SCRIPT, *args], capture_output=True,
                              text=True, check=False, env=env, cwd=workspace)

    def test_refuses_without_a_credential_instead_of_prompting(self) -> None:
        # The smoke's Product-B leg printed an OAuth URL and burned 60s waiting for
        # a browser. A refusal costs nothing and says what is missing.
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._run(tmp, ["--print", "solve it"], with_token=False)
            self.assertEqual(proc.returncode, 42)
            self.assertIn("SMOKE-2", proc.stderr)
            self.assertIn("antigravity-oauth-token", proc.stderr)

    def test_missing_product_binary_is_its_own_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._run(tmp, ["--print", "x"], real=False)
            self.assertEqual(proc.returncode, 44)

    def test_version_probe_needs_no_credential(self) -> None:
        # Otherwise a credential failure would surface as a version mismatch and
        # hide the real cause (and the image build's pin assert would break).
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._run(tmp, ["--version"], with_token=False)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("ARGS=--version", proc.stdout)

    def test_home_is_a_fresh_per_invocation_dir_holding_only_the_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = self._run(tmp, ["--print", "x"])
            second = self._run(tmp, ["--print", "x"])
            self.assertEqual(first.returncode, 0, first.stderr)
            homes = []
            for proc in (first, second):
                line = [ln for ln in proc.stdout.splitlines() if ln.startswith("HOME=")]
                homes.append(line[0])
                self.assertNotIn("brain", proc.stdout)
                self.assertNotIn("conversations", proc.stdout)
            self.assertNotEqual(homes[0], homes[1])   # no state shared between runs
            self.assertNotIn(os.path.expanduser("~"), homes[0].split("=", 1)[1])

    def test_host_trusted_workspaces_never_crosses_the_boundary(self) -> None:
        # The host settings.json names this repo's absolute path — the same path
        # the SMOKE-3 escape wrote into. Only the gcp block is carried over.
        host_settings = json.dumps({
            "gcp": {"project": "SYNTHETIC-project", "location": "global"},
            "trustedWorkspaces": ["/home/someone/Developer-Agent-Tokenomics-Decision-Lab"],
            "enableTelemetry": True,
        })
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._run(tmp, ["--print", "x"], settings=host_settings)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn("Developer-Agent-Tokenomics-Decision-Lab", proc.stdout)
            self.assertIn("SYNTHETIC-project", proc.stdout)   # routing preserved
            self.assertIn(os.path.join(tmp, "subject"), proc.stdout)  # workspace forced

    def test_updater_kill_switch_reaches_the_product(self) -> None:
        # The adapter sets it on the docker CLI's env, which is not the
        # container's; the wrapper and the image ENV are what actually deliver it.
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._run(tmp, ["--print", "x"])
            self.assertIn("AUTOUPDATE=1", proc.stdout)


if __name__ == "__main__":
    unittest.main()
