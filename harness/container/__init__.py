"""Containerized subject isolation for the controlled runner (Phase 3, batch-2).

Benchmark subjects run inside the task-tools Docker container with the network
DISABLED (``--network=none``) — the human isolation decision recorded in
``manifest/delivery-manifest.yaml`` (``subject_isolation``) and
``manifest/cp-spend-batch2-plan.md`` §3.1. Deps are pre-baked into a per-task image
(build-time network only — never model spend) so the runtime is fully offline.

Nothing here spends on a model API. ``docker build`` uses network at build time to
clone the subject repo + ``npm ci``; the graded run is offline.
"""

from .exec import (
    ContainerExecutor,
    ContainerResult,
    docker_run_argv,
    image_exists,
    subject_image_tag,
)

__all__ = [
    "ContainerExecutor",
    "ContainerResult",
    "docker_run_argv",
    "image_exists",
    "subject_image_tag",
]
