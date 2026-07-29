"""Docker exec primitives for containerized, network-disabled subject isolation.

Design (see harness/container/README.md, manifest subject_isolation):
  * ``docker_run_argv`` is a PURE argv builder — it never touches Docker, so the
    exact command (network mode, mounts, workdir, env, image) is unit-testable with
    no daemon and no spend. The runner and the offline gate both build their
    commands through it, so what tests assert is what runs.
  * ``--network=none`` is the DEFAULT and the recorded batch-2 posture. A caller
    must pass a different network explicitly (the live agent leg's model-API egress
    allowlist is a CP-SPEND finalization item — never silently opened here).
  * ``ContainerExecutor.run`` is a thin ``subprocess.run`` wrapper; the workshop
    owns its timeout/return handling exactly as the direct-CLI adapters do.

No function here makes a model API call. ``build_subject_image`` shells out to
``docker build`` (network at BUILD time only, to clone + install deps); that is
tooling setup, not model spend (CLAUDE.md rule 5).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# Network modes we recognise. ``none`` = fully offline (batch-2 default posture).
# Any other value is passed verbatim to ``docker run --network`` so a CP-SPEND
# egress policy (a named docker network) can be selected later without code change.
NETWORK_NONE = "none"

# Where the subject repo lives INSIDE the container (matches Dockerfile.subject).
CONTAINER_SUBJECT_ROOT = "/subject"

_SLUG_RE = re.compile(r"[^a-z0-9_.-]+")


def subject_image_tag(task_id: str, pin: str) -> str:
    """Deterministic per-task image tag: ``lab-subject/<task_id>:<pin12>``.

    Task id is slugified to a Docker-safe repository name; the 12-char commit
    prefix pins the baked deps to the exact subject tree, so a re-pin yields a new
    tag (never a stale image silently reused).
    """
    slug = _SLUG_RE.sub("-", (task_id or "task").lower()).strip("-") or "task"
    pin12 = (pin or "nopin")[:12]
    return f"lab-subject/{slug}:{pin12}"


def docker_run_argv(
    image: str,
    cmd: Sequence[str],
    *,
    mounts: Optional[Sequence[Tuple[str, str, str]]] = None,
    workdir: str = CONTAINER_SUBJECT_ROOT,
    network: str = NETWORK_NONE,
    env: Optional[Dict[str, str]] = None,
    remove: bool = True,
) -> List[str]:
    """Build a ``docker run`` argv (pure; no execution).

    ``mounts`` are ``(host_src, container_dst, mode)`` triples (mode e.g. ``"rw"``
    or ``"ro"``). ``network`` defaults to ``none`` (offline) — the recorded batch-2
    posture. ``env`` values are passed with ``-e KEY=VALUE`` in sorted order so the
    command is deterministic (stable across runs and easy to assert in tests).
    """
    if not image:
        raise ValueError("docker_run_argv requires a non-empty image")
    argv: List[str] = ["docker", "run"]
    if remove:
        argv.append("--rm")
    argv += ["--network", network]
    for src, dst, mode in (mounts or []):
        argv += ["-v", f"{src}:{dst}:{mode}"]
    if workdir:
        argv += ["-w", workdir]
    for key in sorted(env or {}):
        argv += ["-e", f"{key}={env[key]}"]
    argv.append(image)
    argv += list(cmd)
    return argv


@dataclass
class ContainerResult:
    """Outcome of a container exec (mirrors the fields adapters read from
    ``subprocess.run``)."""

    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    argv: List[str] = field(default_factory=list)


@dataclass
class ContainerLaunch:
    """How to launch a subject command inside its offline container.

    Carried by the runner into an adapter (``Adapter.container``) so the live
    agent leg execs inside the container instead of on the host. ``network``
    defaults to ``none`` (offline); the live agent leg's model-API egress network
    is set here at CP-SPEND and recorded authoritatively in identity.network_policy.
    """

    image: str
    network: str = NETWORK_NONE
    mounts: Tuple[Tuple[str, str, str], ...] = ()
    subject_root: str = CONTAINER_SUBJECT_ROOT


def resolve_spawn(
    launch: Optional[ContainerLaunch], cmd: Sequence[str], subject_dir: str,
) -> Tuple[List[str], Optional[str]]:
    """Resolve ``(argv, cwd)`` for spawning a subject command.

    Host mode (``launch is None``) → run ``cmd`` with ``cwd=subject_dir``, exactly
    as before (dry-run/tests and batch-1 posture are unchanged). Container mode →
    wrap ``cmd`` in ``docker run`` (``cwd=None``; the container's ``-w`` sets the
    workdir). This is the single seam that routes the agent leg through the
    container; both branches are pure and unit-testable.
    """
    if launch is None:
        return list(cmd), subject_dir
    argv = docker_run_argv(
        launch.image, cmd, mounts=launch.mounts,
        workdir=launch.subject_root, network=launch.network,
    )
    return argv, None


class ContainerExecutor:
    """Runs a command inside a subject container (offline by default).

    Used by the runner for the deterministic gate (``--network=none``, verified
    offline) and — as a mechanism, its egress finalized at CP-SPEND — for the live
    agent leg. Construction never spends; ``run`` shells out to ``docker run``.
    """

    def __init__(self, image: str, *, subject_root: str = CONTAINER_SUBJECT_ROOT):
        self.image = image
        self.subject_root = subject_root

    def run(
        self,
        cmd: Sequence[str],
        *,
        mounts: Optional[Sequence[Tuple[str, str, str]]] = None,
        workdir: Optional[str] = None,
        network: str = NETWORK_NONE,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> ContainerResult:
        argv = docker_run_argv(
            self.image, cmd, mounts=mounts,
            workdir=workdir or self.subject_root, network=network, env=env,
        )
        try:
            proc = subprocess.run(  # noqa: S603 - workshop-owned command
                argv, capture_output=True, text=True, check=False, timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return ContainerResult(
                returncode=124, stdout=exc.stdout or "", stderr=exc.stderr or "",
                timed_out=True, argv=argv,
            )
        return ContainerResult(
            returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr,
            argv=argv,
        )


def image_exists(tag: str) -> bool:
    """True if a local Docker image with ``tag`` is present (no network)."""
    proc = subprocess.run(  # noqa: S603 - fixed argv
        ["docker", "image", "inspect", tag],
        capture_output=True, text=True, check=False,
    )
    return proc.returncode == 0


def build_subject_image(
    task_dir_rel: str, tag: str, repo_root: str, dockerfile: str,
    *, timeout: Optional[float] = 1800,
) -> subprocess.CompletedProcess:
    """Build the per-task offline image (network at BUILD time only; not spend).

    Bakes the subject repo + node_modules + generated Prisma client into the image
    for the CONTAINER platform via ``setup.sh`` at build time, so the graded run is
    fully offline. Returns the completed ``docker build`` process (caller checks rc).
    """
    argv = [
        "docker", "build",
        "-f", dockerfile,
        "--build-arg", f"BAKE_TASK_DIR={task_dir_rel}",
        "-t", tag,
        repo_root,
    ]
    return subprocess.run(  # noqa: S603 - workshop-owned command
        argv, check=False, timeout=timeout,
    )
