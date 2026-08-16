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

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# Network modes we recognise. ``none`` = fully offline (the gate posture, always).
# Any other value is passed verbatim to ``docker run --network`` — the agent leg
# uses the egress-allowlist network from ``harness/container/egress.py``.
NETWORK_NONE = "none"

# Where the subject repo lives INSIDE the container (matches Dockerfile.subject).
CONTAINER_SUBJECT_ROOT = "/subject"

# Build targets in Dockerfile.subject. The gate keeps task.yaml (it cannot grade
# without it); the agent image has no task material in any layer.
TARGET_GATE = "subject-gate"
TARGET_AGENT = "subject-agent"

_SLUG_RE = re.compile(r"[^a-z0-9_.-]+")


def _slug(task_id: str) -> str:
    return _SLUG_RE.sub("-", (task_id or "task").lower()).strip("-") or "task"


def subject_image_tag(task_id: str, pin: str) -> str:
    """Deterministic per-task GATE image tag: ``lab-subject/<task_id>:<pin12>``.

    Task id is slugified to a Docker-safe repository name; the 12-char commit
    prefix pins the baked deps to the exact subject tree, so a re-pin yields a new
    tag (never a stale image silently reused).
    """
    return f"lab-subject/{_slug(task_id)}:{(pin or 'nopin')[:12]}"


def agent_image_tag(task_id: str, pin: str) -> str:
    """Deterministic per-task AGENT image tag: ``lab-subject-agent/<task_id>:<pin12>``.

    A separate repository name, not a separate tag on the same one: the two images
    have different contents and opposite task-material postures, and a tag collision
    between them would be the kind of mistake that silently hands an agent the
    answer patch.
    """
    return f"lab-subject-agent/{_slug(task_id)}:{(pin or 'nopin')[:12]}"


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
    """How to launch a subject command inside its container.

    Carried by the runner into an adapter (``Adapter.container``) so the agent leg
    execs inside the container instead of on the host.

    ``network`` defaults to ``none`` (offline) — the gate posture. The agent leg
    passes the egress-allowlist network name from ``harness/container/egress.py``;
    whatever value is used, the runner records the matching policy label verbatim in
    ``identity.network_policy``.

    ``env`` is the environment handed to the container. It is an explicit, small
    dict (credentials + provider routing), never the host environment: the agent
    must not receive harness path pointers (FIX B) and does not need the rest.

    ``agent_volume``, when set, is a named Docker volume mounted at the subject root
    so the agent's edits SURVIVE the container and can be graded by the gate
    container, which mounts the same volume at the path its image expects. Docker
    seeds an empty named volume from the image content on first mount, so the agent
    starts from the baked tree with no copy step on the host.
    """

    image: str
    network: str = NETWORK_NONE
    mounts: Tuple[Tuple[str, str, str], ...] = ()
    subject_root: str = CONTAINER_SUBJECT_ROOT
    env: Dict[str, str] = field(default_factory=dict)
    agent_volume: Optional[str] = None
    #: Free-text description of what this launch actually enforces, stamped into
    #: identity.permission_profile. Set by the runner, which knows the mode.
    profile: str = ""

    def all_mounts(self) -> List[Tuple[str, str, str]]:
        """Declared mounts plus the agent volume (if any), in a stable order."""
        mounts = list(self.mounts)
        if self.agent_volume:
            mounts.append((self.agent_volume, self.subject_root, "rw"))
        return mounts


def resolve_spawn(
    launch: Optional[ContainerLaunch], cmd: Sequence[str], subject_dir: str,
) -> Tuple[List[str], Optional[str]]:
    """Resolve ``(argv, cwd)`` for spawning a subject command.

    Host mode (``launch is None``) → run ``cmd`` with ``cwd=subject_dir``, exactly
    as before (dry-run/tests and batch-1 posture are unchanged). Container mode →
    wrap ``cmd`` in ``docker run`` (``cwd=None``; the container's ``-w`` sets the
    workdir), carrying the launch's mounts, network and environment. This is the
    single seam that routes the agent leg through the container; both branches are
    pure and unit-testable.
    """
    if launch is None:
        return list(cmd), subject_dir
    argv = docker_run_argv(
        launch.image, cmd, mounts=launch.all_mounts(),
        workdir=launch.subject_root, network=launch.network,
        env=launch.env or None,
    )
    return argv, None


# --------------------------------------------------------------------------- #
# Agent-leg credentials and provider routing
# --------------------------------------------------------------------------- #
# The agent container needs exactly two things from the host beyond the network:
# a credential to mint provider tokens, and the env that says which project/region
# to route to. Both are enumerated here rather than inherited, so nothing else — in
# particular no harness path pointer (FIX B) — crosses the boundary.

#: Provider-routing env forwarded from the host if present. Values are not secrets
#: (project id, region, routing flags); the credential itself is a MOUNT, not env.
AGENT_ENV_PASSTHROUGH: Tuple[str, ...] = (
    "CLAUDE_CODE_USE_VERTEX",
    "ANTHROPIC_VERTEX_PROJECT_ID",
    "ANTHROPIC_VERTEX_BASE_URL",
    "CLOUD_ML_REGION",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    "VERTEX_REGION_CLAUDE_HAIKU_4_5",
    "VERTEX_REGION_CLAUDE_SONNET_4_6",
)

#: Where the host's gcloud config (holding application-default credentials) is
#: mounted READ-ONLY inside the agent container.
CONTAINER_GCLOUD_DIR = "/creds/gcloud"
CONTAINER_ADC_PATH = f"{CONTAINER_GCLOUD_DIR}/application_default_credentials.json"
#: Product B's auth/config state, mounted read-only when present.
CONTAINER_AGY_DIR = "/creds/gemini"


def host_gcloud_dir() -> Optional[str]:
    """The host gcloud config dir holding ADC, or ``None`` if there is no ADC file."""
    base = os.environ.get("CLOUDSDK_CONFIG") or os.path.join(
        os.path.expanduser("~"), ".config", "gcloud")
    return base if os.path.isfile(
        os.path.join(base, "application_default_credentials.json")) else None


def host_agy_dir() -> Optional[str]:
    """Product B's host auth/config dir, or ``None`` if absent."""
    path = os.path.join(os.path.expanduser("~"), ".gemini")
    return path if os.path.isdir(path) else None


def agent_credential_mounts() -> List[Tuple[str, str, str]]:
    """Read-only credential mounts for the agent container (only what exists).

    Read-only is deliberate and has a cost: a CLI that wants to refresh a cached
    token on disk will fail rather than write. That failure is visible and
    diagnosable; a benchmark run silently mutating the operator's credential store
    is not. If a product turns out to require write access, that is a finding to
    record at CP-SPEND, not something to pre-emptively grant here.
    """
    mounts: List[Tuple[str, str, str]] = []
    gcloud = host_gcloud_dir()
    if gcloud:
        mounts.append((gcloud, CONTAINER_GCLOUD_DIR, "ro"))
    agy = host_agy_dir()
    if agy:
        mounts.append((agy, CONTAINER_AGY_DIR, "ro"))
    return mounts


def agent_container_env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Environment for the agent container: routing passthrough + credential paths.

    Enumerated, not inherited. Absent host vars are simply omitted — never
    defaulted to a guess, because a wrong project or region would silently bill and
    measure the wrong thing.
    """
    env: Dict[str, str] = {
        key: os.environ[key] for key in AGENT_ENV_PASSTHROUGH if os.environ.get(key)
    }
    if host_gcloud_dir():
        env["GOOGLE_APPLICATION_CREDENTIALS"] = CONTAINER_ADC_PATH
        env["CLOUDSDK_CONFIG"] = CONTAINER_GCLOUD_DIR
    env.update(extra or {})
    return env


def image_labels(tag: str) -> Dict[str, str]:
    """Labels baked into ``tag`` (CLI version pins), or ``{}`` if unreadable.

    Read from the image the run actually launches, so ``identity.product_version``
    describes the CLI inside the container rather than whatever is installed on the
    host — the two drift, and the host's is irrelevant to a containerized leg.
    """
    proc = subprocess.run(  # noqa: S603 - fixed argv
        ["docker", "image", "inspect", "-f", "{{json .Config.Labels}}", tag],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        return {}
    try:
        labels = json.loads(proc.stdout.strip() or "null")
    except json.JSONDecodeError:
        return {}
    return {str(k): str(v) for k, v in (labels or {}).items()}


def image_cli_version(tag: str, product: str) -> str:
    """CLI version baked into ``tag`` for ``product`` (``claude``/``agy``).

    Returns ``"unavailable"`` when the label is missing or the image records the CLI
    as absent — never a host fallback and never a guess (CLAUDE.md rule 3).
    """
    value = image_labels(tag).get(f"lab.cli.{product}.version", "").strip()
    return value if value and value != "unavailable" else "unavailable"


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
    *, target: str = TARGET_GATE, build_args: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = 1800,
) -> subprocess.CompletedProcess:
    """Build a per-task subject image (network at BUILD time only; not spend).

    Bakes the subject repo + node_modules + generated Prisma client into the image
    for the CONTAINER platform via ``setup.sh`` at build time, so the graded run is
    fully offline. ``target`` selects ``subject-gate`` (task material intact, the
    grader) or ``subject-agent`` (product CLIs baked, task material asserted absent).
    Returns the completed ``docker build`` process (caller checks rc).
    """
    argv = [
        "docker", "build",
        "-f", dockerfile,
        "--target", target,
        "--build-arg", f"BAKE_TASK_DIR={task_dir_rel}",
    ]
    for key in sorted(build_args or {}):
        argv += ["--build-arg", f"{key}={build_args[key]}"]
    argv += ["-t", tag, repo_root]
    return subprocess.run(  # noqa: S603 - workshop-owned command
        argv, check=False, timeout=timeout,
    )


# --------------------------------------------------------------------------- #
# Agent -> gate handoff volume
# --------------------------------------------------------------------------- #
def agent_volume_name(run_id: str) -> str:
    """Per-run named volume carrying the agent's edits to the gate container.

    Scoped to the run id so two runs never share a tree — the whole point of
    ``cold`` reps is that each starts from the pristine baked state.
    """
    return f"lab-subject-work-{_slug(run_id)}"[:120]


def create_volume(name: str) -> None:
    subprocess.run(  # noqa: S603 - fixed argv
        ["docker", "volume", "create", name],
        capture_output=True, text=True, check=False,
    )


def remove_volume(name: str) -> None:
    """Best-effort volume cleanup; the run's provenance lives under ``run_dir``."""
    subprocess.run(  # noqa: S603 - fixed argv
        ["docker", "volume", "rm", "-f", name],
        capture_output=True, text=True, check=False,
    )
