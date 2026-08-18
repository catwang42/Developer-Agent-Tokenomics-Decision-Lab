"""Containerized subject isolation for the controlled runner (Phase 3–4).

Two postures, deliberately different:

  * the deterministic GATE runs ``--network=none`` in the ``subject-gate`` image,
    which keeps the task material it needs to grade;
  * the AGENT leg runs in the ``subject-agent`` image — product CLIs baked, no task
    material in any layer — on an egress-allowlist network (``egress.py``), the
    SPEC §6 item 1 hard gate for screening runs.

Recorded in ``manifest/delivery-manifest.yaml`` (``subject_isolation``) and per run
in ``identity.permission_profile`` + ``identity.network_policy``.

Nothing here spends on a model API. ``docker build`` uses network at build time to
clone the subject repo, ``npm ci`` and install the product CLIs; that is tooling
setup (CLAUDE.md rule 5).
"""

from .egress import EgressPolicy, load_policy
from .exec import (
    TARGET_AGENT,
    TARGET_GATE,
    ContainerExecutor,
    ContainerLaunch,
    ContainerResult,
    agent_build_args,
    agent_container_env,
    agent_credential_mounts,
    agent_image_tag,
    agent_volume_name,
    docker_run_argv,
    image_cli_version,
    image_exists,
    image_labels,
    subject_image_tag,
)

__all__ = [
    "TARGET_AGENT",
    "TARGET_GATE",
    "ContainerExecutor",
    "ContainerLaunch",
    "ContainerResult",
    "EgressPolicy",
    "agent_build_args",
    "agent_container_env",
    "agent_credential_mounts",
    "agent_image_tag",
    "agent_volume_name",
    "docker_run_argv",
    "image_cli_version",
    "image_exists",
    "image_labels",
    "load_policy",
    "subject_image_tag",
]
