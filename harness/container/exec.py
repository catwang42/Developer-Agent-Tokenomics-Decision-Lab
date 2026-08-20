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
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
    name: Optional[str] = None,
) -> List[str]:
    """Build a ``docker run`` argv (pure; no execution).

    ``mounts`` are ``(host_src, container_dst, mode)`` triples (mode e.g. ``"rw"``
    or ``"ro"``). ``network`` defaults to ``none`` (offline) — the recorded batch-2
    posture. ``env`` values are passed with ``-e KEY=VALUE`` in sorted order so the
    command is deterministic (stable across runs and easy to assert in tests).

    ``name`` gives the container a deterministic, addressable ``--name``. It is what
    makes a timeout ENFORCEABLE: ``docker run`` is a client attached to a daemon-side
    container, so killing the client (which is all ``subprocess.run(timeout=...)``
    can do) leaves the container running. Without a name there is no reliable handle
    to kill it with — see :func:`kill_container` and :func:`spawn_with_timeout`.
    """
    if not image:
        raise ValueError("docker_run_argv requires a non-empty image")
    argv: List[str] = ["docker", "run"]
    if remove:
        argv.append("--rm")
    if name:
        argv += ["--name", name]
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
    #: Run-scoped prefix for the container's ``--name``. The adapter appends the leg
    #: id (:func:`leg_container_name`) so every attempt of a run has its own handle
    #: and a timeout can kill the right container. Empty => unnamed (host mode, and
    #: any caller that has not opted in).
    name_prefix: str = ""

    def all_mounts(self) -> List[Tuple[str, str, str]]:
        """Declared mounts plus the agent volume (if any), in a stable order."""
        mounts = list(self.mounts)
        if self.agent_volume:
            mounts.append((self.agent_volume, self.subject_root, "rw"))
        return mounts


def leg_container_name(
    launch: Optional[ContainerLaunch], leg_id: str,
) -> Optional[str]:
    """Deterministic ``--name`` for one leg's agent container, or ``None``.

    ``None`` in host mode and for any launch without a ``name_prefix`` — those
    callers get the historical unnamed behaviour. Per LEG, not per run: a P1 run
    spawns an economical attempt and then a strong one, and a timeout must kill the
    container that is actually hung rather than a name shared with its sibling.
    """
    if launch is None or not launch.name_prefix:
        return None
    return f"{launch.name_prefix}-{_slug(leg_id)}"[:120]


def resolve_spawn(
    launch: Optional[ContainerLaunch], cmd: Sequence[str], subject_dir: str,
    *, name: Optional[str] = None,
) -> Tuple[List[str], Optional[str]]:
    """Resolve ``(argv, cwd)`` for spawning a subject command.

    Host mode (``launch is None``) → run ``cmd`` with ``cwd=subject_dir``, exactly
    as before (dry-run/tests and batch-1 posture are unchanged). Container mode →
    wrap ``cmd`` in ``docker run`` (``cwd=None``; the container's ``-w`` sets the
    workdir), carrying the launch's mounts, network and environment. This is the
    single seam that routes the agent leg through the container; both branches are
    pure and unit-testable.

    ``name`` is the container handle a timeout will kill (see
    :func:`leg_container_name`); it is ignored in host mode, where there is no
    container and ``subprocess`` already owns the process.
    """
    if launch is None:
        return list(cmd), subject_dir
    argv = docker_run_argv(
        launch.image, cmd, mounts=launch.all_mounts(),
        workdir=launch.subject_root, network=launch.network,
        env=launch.env or None, name=name,
    )
    return argv, None


# --------------------------------------------------------------------------- #
# Enforceable timeouts
# --------------------------------------------------------------------------- #
@dataclass
class SpawnResult:
    """Outcome of :func:`spawn_with_timeout` (mirrors what adapters read).

    ``timed_out`` distinguishes a workshop kill from a product exit; ``container``
    records what the kill actually achieved, so a run whose container could not be
    reaped says so in the event log instead of looking clean.
    """

    returncode: Optional[int]
    stdout: str
    stderr: str
    timed_out: bool = False
    #: ``None`` when nothing needed killing (no container, or it exited normally);
    #: else ``"killed"`` / ``"already_gone"`` / ``"kill_failed: <stderr>"``.
    container: Optional[str] = None


def _container_ids(name: str, *, running_only: bool) -> str:
    argv = ["docker", "ps", "--quiet", "--filter", f"name=^{name}$"]
    if not running_only:
        argv.insert(2, "--all")
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)  # noqa: S603
    return proc.stdout.strip() if proc.returncode == 0 else ""


def container_is_running(name: str) -> bool:
    """True if a container called ``name`` exists and is running (no side effects)."""
    return bool(_container_ids(name, running_only=True))


def container_exists(name: str) -> bool:
    """True if a container called ``name`` exists in any state (no side effects)."""
    return bool(_container_ids(name, running_only=False))


def kill_container(name: str) -> str:
    """Force-remove the container called ``name``; report what happened.

    This is the other half of an enforceable timeout. ``subprocess.run(timeout=...)``
    kills the ``docker run`` CLI, which is only a client attached to a daemon-side
    container: the container keeps running, keeps its volume mounted, and — for a
    live agent leg — keeps spending. That is the orphan defect observed in screening
    batch 1, where a killed wait left a container running under the daemon's own
    name. ``docker rm -f`` addresses the container directly, so the kill lands.

    Never raises: it runs on the failure path, and a cleanup error must not replace
    the timeout as the reported cause. Returns ``"killed"``, ``"already_gone"``, or
    ``"kill_failed: <detail>"`` for the caller to record — the distinction matters,
    because "the timeout fired and the container was already gone" and "the timeout
    fired and we could not stop it" are different facts about a run.

    Existence is checked FIRST rather than inferred from the exit code: ``docker rm
    -f`` exits 0 on a container that never existed, so trusting rc alone would report
    a kill that did not happen.
    """
    if not container_exists(name):
        return "already_gone"
    proc = subprocess.run(  # noqa: S603 - fixed argv
        ["docker", "rm", "--force", "--volumes=false", name],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode == 0:
        return "killed"
    return f"kill_failed: {(proc.stderr or '').strip()[:200]}"


def spawn_with_timeout(
    argv: Sequence[str],
    *,
    cwd: Optional[str],
    env: Optional[Dict[str, str]],
    timeout_s: float,
    container_name: Optional[str] = None,
) -> SpawnResult:
    """Run ``argv`` under a workshop-owned timeout that actually stops the work.

    One seam for both product adapters, so "the timeout killed the agent" means the
    same thing for Product A and Product B. On expiry the child (the ``docker run``
    client, or the bare CLI in host mode) is terminated by ``subprocess``, and — when
    ``container_name`` is set — the container itself is force-removed, because
    killing the client does not stop the container (see :func:`kill_container`).

    Partial stdout/stderr from the killed child is preserved: for a timed-out attempt
    that output is often the only diagnosis there is.
    """
    try:
        proc = subprocess.run(  # noqa: S603 - workshop-owned command
            list(argv), cwd=cwd, capture_output=True, text=True, check=False,
            timeout=timeout_s, env=env,
        )
    except subprocess.TimeoutExpired as exc:
        killed = kill_container(container_name) if container_name else None
        return SpawnResult(
            returncode=None, stdout=exc.stdout or "", stderr=exc.stderr or "",
            timed_out=True, container=killed,
        )
    return SpawnResult(
        returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr,
    )


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

#: Product B's credentials, mounted read-only as INDIVIDUAL FILES (SMOKE-2).
#:
#: The earlier posture mounted the whole host ``~/.gemini`` at ``/creds/gemini``,
#: which was wrong twice over. It did nothing useful — agy resolves its store from
#: ``$HOME/.gemini/antigravity-cli/`` and has no config-dir override, so a tree
#: parked anywhere else is invisible to it, and the smoke's Product-B leg fell
#: through to an interactive OAuth prompt it could not answer. And it was too
#: wide: that tree also holds ``brain/`` (prior-session workspace memory naming
#: this repo's absolute path on the host) and a ``settings.json``
#: ``trustedWorkspaces`` entry doing the same — the SMOKE-3 material. Three files
#: cross the boundary now, and ``agy-headless.sh`` seeds a throwaway per-run HOME
#: from them inside the container.
CONTAINER_AGY_CRED_DIR = "/creds/agy"
CONTAINER_AGY_TOKEN = f"{CONTAINER_AGY_CRED_DIR}/antigravity-oauth-token"
CONTAINER_AGY_SETTINGS = f"{CONTAINER_AGY_CRED_DIR}/settings.json"
CONTAINER_AGY_INSTALL_ID = f"{CONTAINER_AGY_CRED_DIR}/installation_id"

#: Host location of Product B's state, relative to the operator's home.
HOST_AGY_STATE_REL = os.path.join(".gemini", "antigravity-cli")


def host_gcloud_dir() -> Optional[str]:
    """The host gcloud config dir holding ADC, or ``None`` if there is no ADC file."""
    base = os.environ.get("CLOUDSDK_CONFIG") or os.path.join(
        os.path.expanduser("~"), ".config", "gcloud")
    return base if os.path.isfile(
        os.path.join(base, "application_default_credentials.json")) else None


def host_agy_state_dir() -> str:
    """Where Product B keeps its state on the host (may not exist)."""
    return os.path.join(os.path.expanduser("~"), HOST_AGY_STATE_REL)


def host_agy_file(name: str) -> Optional[str]:
    """One file from Product B's host state dir, or ``None`` if it is not there."""
    path = os.path.join(host_agy_state_dir(), name)
    return path if os.path.isfile(path) else None


def agent_credential_mounts() -> List[Tuple[str, str, str]]:
    """Read-only credential mounts for the agent container (only what exists).

    Read-only is deliberate and has a cost: a CLI that wants to refresh a cached
    token on disk will fail rather than write. That failure is visible and
    diagnosable; a benchmark run silently mutating the operator's credential store
    is not. If a product turns out to require write access, that is a finding to
    record at CP-SPEND, not something to pre-emptively grant here. Product B is
    handed a writable COPY of its token in a per-run temp HOME by
    ``agy-headless.sh``, so read-only here costs it nothing.

    What each grant is, exactly:
      * gcloud config dir — application-default credentials; mints Vertex tokens
        for the operator's project. Product A's Vertex path needs it.
      * ``antigravity-oauth-token`` — Product B's OAuth token
        (``auth_method: gcp``); it is the whole of Product B's ability to call the
        provider. Absent it, ``agy-headless.sh`` refuses (exit 42).
      * ``settings.json`` — read ONLY for its ``gcp`` {project, location} block, so
        the run bills the project the operator actually configured rather than one
        this harness guessed. Its ``trustedWorkspaces`` is discarded in-container.
      * ``installation_id`` — a non-secret install identifier; keeps a measured run
        from looking like a first-ever launch.
    """
    mounts: List[Tuple[str, str, str]] = []
    gcloud = host_gcloud_dir()
    if gcloud:
        mounts.append((gcloud, CONTAINER_GCLOUD_DIR, "ro"))
    for name, dst in (
        ("antigravity-oauth-token", CONTAINER_AGY_TOKEN),
        ("settings.json", CONTAINER_AGY_SETTINGS),
        ("installation_id", CONTAINER_AGY_INSTALL_ID),
    ):
        src = host_agy_file(name)
        if src:
            mounts.append((src, dst, "ro"))
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


def image_subject_uid(tag: str) -> Optional[int]:
    """The uid the agent image drops to, from its label, or ``None`` if unlabelled."""
    raw = image_labels(tag).get("lab.image.subject_uid", "").strip()
    try:
        return int(raw)
    except ValueError:
        return None


def assert_image_uid_matches_host(tag: str) -> None:
    """Refuse an agent image whose non-root user cannot read this host's credentials.

    Both products authenticate from 0600 files owned by the invoking user, and a
    bind mount hands the container the host's numeric owner untranslated — so the
    container user's uid must equal the host user's or every provider call fails with
    a permission error that surfaces as an opaque auth failure mid-run. The image tag
    pins task + commit, not the builder, so an image built under another account is a
    legal cache hit; this check is what makes that loud instead of silent.

    Raises ``PermissionError`` (the runner turns it into a RunnerError) rather than
    proceeding, because the alternative is burning a live, billed run to discover it.
    """
    uid = image_subject_uid(tag)
    host_uid = os.getuid()
    if uid == host_uid:
        return
    if uid is None:
        raise PermissionError(
            f"agent image {tag} carries no lab.image.subject_uid label — it predates "
            f"the SMOKE-1/SMOKE-2 fix. Rebuild it: "
            f"bash harness/container/build-subject-image.sh <task_dir> agent"
        )
    raise PermissionError(
        f"agent image {tag} runs as uid {uid}, but this host's user is uid {host_uid}. "
        f"The read-only credential mounts (ADC, antigravity-oauth-token) are mode 0600 "
        f"owned by {host_uid}, so uid {uid} cannot read them and both products would "
        f"fail to authenticate. Rebuild the image as this user: "
        f"bash harness/container/build-subject-image.sh <task_dir> agent"
    )


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
        name: Optional[str] = None,
    ) -> ContainerResult:
        argv = docker_run_argv(
            self.image, cmd, mounts=mounts,
            workdir=workdir or self.subject_root, network=network, env=env,
            name=name,
        )
        try:
            proc = subprocess.run(  # noqa: S603 - workshop-owned command
                argv, capture_output=True, text=True, check=False, timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            # Same orphan hazard as the agent leg: the timeout kills the client, not
            # the container. A named gate container is reaped here so a hung grade
            # cannot hold its volume and outlive the batch.
            killed = kill_container(name) if name else None
            stderr = exc.stderr or ""
            if killed:
                stderr += f"\n[harness] container {name}: {killed}"
            return ContainerResult(
                returncode=124, stdout=exc.stdout or "", stderr=stderr,
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


def agent_build_args(manifest: Dict[str, Any], repo_root: str) -> Dict[str, str]:
    """The ``--build-arg`` set the ``subject-agent`` target needs, for EVERY builder.

    One resolver, two callers — ``build-subject-image.sh`` (operator, ahead of a
    batch) and ``_ensure_image`` in the runner (auto-build, mid-batch). They used to
    resolve these separately, and the runner resolved none of them: batch 1 halted at
    plan index 19 because the first mid-batch auto-build fell through to the
    Dockerfile's ARG defaults and produced an image running as uid 1001 against a
    host user of a different uid, so the 0600 credential mounts were unreadable and
    the uid guard refused. The same image also labelled ``lab.cli.agy.version`` as
    ``unavailable`` while carrying the vendored binary — a silent telemetry hole that
    the uid guard happened to mask. A default that is only correct for one caller is
    a defect waiting for the other, so neither caller computes these any more.

    ``SUBJECT_UID``/``SUBJECT_GID``: the invoking operator's, because non-root
    (SMOKE-1) and readable 0600 credential mounts (SMOKE-2) are only simultaneously
    satisfiable at the host user's own numeric id — a bind mount passes the owner
    through untranslated.

    ``AGY_REQUIRED``: 1 whenever Product B is expected — either its binary is
    vendored, or the manifest pins a real version. The second case is deliberately
    stricter than a warning: an agent image built without ``vendor/agy`` cannot run a
    Product-B leg at all, and the honest place to discover that is a failed build,
    not an arm that records ``unavailable`` for a run that was billed.

    Raises ``ValueError`` if the manifest pins no Product-A CLI version; baking an
    unpinned CLI would stamp whatever npm resolved into every run's
    ``identity.product_version``.
    """
    leg = ((manifest.get("subject_isolation") or {}).get("agent_leg") or {})

    claude_cli_version = str(leg.get("claude_cli_version") or "").strip()
    if not claude_cli_version:
        raise ValueError(
            "manifest subject_isolation.agent_leg.claude_cli_version is missing; "
            "refusing to bake an unpinned Product-A CLI into the agent image"
        )
    agy_version = str(leg.get("agy_version") or "").strip() or "unavailable"
    agy_sha256 = str(leg.get("agy_sha256") or "").strip() or "unavailable"

    vendored = os.path.join(repo_root, "vendor", "agy")
    agy_vendored = os.path.isfile(vendored) and os.access(vendored, os.X_OK)
    agy_required = "1" if (agy_vendored or agy_version != "unavailable") else "0"

    return {
        "CLAUDE_CLI_VERSION": claude_cli_version,
        "AGY_VERSION": agy_version,
        "AGY_SHA256": agy_sha256,
        "AGY_REQUIRED": agy_required,
        "SUBJECT_UID": str(os.getuid()),
        "SUBJECT_GID": str(os.getgid()),
    }


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
def agent_container_prefix(run_id: str) -> str:
    """Run-scoped ``--name`` prefix for this run's agent containers.

    Distinct from :func:`agent_volume_name` on purpose: the volume outlives the
    attempt (the gate grades it), the container must not.
    """
    return f"lab-agent-{_slug(run_id)}"[:100]


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
