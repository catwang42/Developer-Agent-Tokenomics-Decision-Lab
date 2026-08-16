"""Adapter contract for the controlled runner (Phase 3, SPEC 2.1–2.3).

An adapter's sole job is to *execute one attempt* against the subject repo and
**emit telemetry events** into the run's event log via a caller-supplied ``emit``
callable (the runner owns the clock; see ``harness/telemetry`` — the module never
reads the wall clock). An adapter never:

  * writes the run summary (the runner derives it from the event log),
  * runs the acceptance gate (the runner does, deterministically — the generating
    model is never its own verifier, SPEC 2.6),
  * fabricates telemetry (missing usage is emitted as ``unavailable``, never 0).

Attempts map to billing *legs* (SPEC 2.7): a static single-model run has one leg
(``main``); a cheap-first policy (P1) that escalates has two legs
(``economical_attempt`` then ``strong_attempt``) so the failed attempt's cost is
recorded on every run; an integrated workflow (C5) has ``conductor`` + ``executor``
legs. Each leg is priced under its own model/selector and cost basis.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from harness.telemetry.telemetry import tiered, unavailable

# emit(event_type: str, **payload) -> None. The runner supplies the timestamp.
EmitFn = Callable[..., None]

# Benchmark-subject sandbox posture, recorded authoritatively in
# identity.permission_profile on EVERY real run (CP-SPEND mini-revalidation
# condition, 2026-07-19). Two declared postures — the runner selects one via
# --subject-isolation and stamps it (plus the matching network_policy)
# authoritatively into identity, overriding any adapter default (the runner, not
# the adapter, knows the actual mode it launched). See harness/container/README.md
# and manifest/delivery-manifest.yaml (subject_isolation).
#
#   HOST      — weak posture. ALL tool permissions are bypassed
#               (--dangerously-skip-permissions). What IS enforced (FIX A/B,
#               2026-07-26): the subject tree is staged in a temp dir OUTSIDE the lab
#               repo, so canonical/, hidden/ and task.yaml cannot be reached by
#               relative traversal from the agent's cwd, and harness path-pointer env
#               vars are scrubbed from the agent's environment. What is NOT enforced:
#               the agent runs same-uid on the bare dev VM with no container and no
#               filesystem namespace, so ABSOLUTE-path access to the wider filesystem
#               (including the lab repo) is still possible; there is no network
#               policy. Earlier material wrongly labelled this "cwd-confined-.work-repo"
#               — the batch-1/2 host runs had no such confinement (see
#               report/findings/subject-isolation-leak.md).
#   CONTAINER — the subject CLI execs inside a per-task Docker image. TWO variants,
#               because the gate and the agent leg enforce different things and one
#               stamp for both would overstate at least one of them:
#                 GATE  — subject-gate image, --network=none. Task material is
#                         PRESENT (the gate reads task.yaml to know what to grade),
#                         so this posture is about hermeticity, not answer-hiding.
#                 AGENT — subject-agent image. Task material absent from every layer
#                         (asserted at build), product CLIs baked at pinned versions,
#                         cwd /subject, credentials mounted read-only. Egress is
#                         allowlisted, NOT absent: the exact policy is recorded
#                         separately in identity.network_policy. Tool permissions
#                         are still bypassed inside the container.
#               See harness/container/README.md and Dockerfile.subject.
SUBJECT_PROFILE_HOST = (
    "skip-all-tools; subject-staged-in-temp-outside-lab-repo; "
    "no-relative-path-to-canonical|hidden|task.yaml; harness-env-pointers-scrubbed; "
    "same-uid; no-container; no-fs-namespace; absolute-path-fs-access-NOT-confined; "
    "no-network-policy"
)
SUBJECT_PROFILE_CONTAINER_GATE = (
    "deterministic-gate; container-isolated; image=subject-gate; network=none; "
    "no-egress; task-material-present-by-design(gate-reads-task.yaml); "
    "cwd-confined-/lab/<task>/.work/repo; root-in-container"
)
SUBJECT_PROFILE_CONTAINER_AGENT = (
    "skip-all-tools-inside-container; container-isolated; image=subject-agent; "
    "fs-namespace-confined; no-canonical|hidden|task.yaml-in-image(build-asserted); "
    "cwd-confined-/subject; harness-env-pointers-scrubbed; "
    "credentials-mounted-read-only; product-CLIs-baked-at-pinned-versions; "
    "egress-allowlisted-see-network_policy; root-in-container"
)

# Back-compat alias. Historical runs stamped one CONTAINER profile covering the gate
# only (the agent leg was host-mode), so the gate variant is what it meant.
SUBJECT_PROFILE_CONTAINER = SUBJECT_PROFILE_CONTAINER_GATE

# Back-compat default for adapters that stamp a posture directly; the runner
# overrides identity.permission_profile with the mode it actually launched.
SUBJECT_PERMISSION_PROFILE = SUBJECT_PROFILE_HOST


@dataclass
class ResolvedModel:
    """A model_ref resolved through the delivery manifest (SPEC 1.4).

    ``model_or_selector`` is an exact versioned model id for a controlled_api
    surface (confidence ``authoritative``) or a verbatim product selector label
    for a product_blackbox surface (confidence ``proxy_observed``; the backend id
    is never inferred — SPEC 6.3). ``provider``/``model_id`` index the pinned
    pricing snapshot; a product_blackbox leg may carry ``model_id=None`` and is
    costed only via a provider-reported figure.
    """

    provider: str
    model_or_selector: str
    model_id: Optional[str]
    cost_basis: str
    product: str
    product_surface: str
    region: Optional[str] = None
    model_confidence: str = "authoritative"
    # Delivery-declared costing inputs (never invented; absent => cost unavailable).
    seat_allocation_usd: Optional[float] = None


@dataclass
class AttemptSpec:
    """One execution attempt = one billing leg.

    ``cache_state``/``session_id``/``resume`` carry the runner's cache-protocol
    contract (methodology/cache-protocol.md rule 4) down to the adapter: a
    ``cold`` attempt runs in a fresh session (``resume=False``) and must prove it
    by emitting its ``session_id`` into the event log; a ``warm-series`` attempt
    continues an existing session (``resume=True``) so the provider prompt-cache
    carries over. The runner owns these values; the adapter only honours them.
    """

    leg_id: str
    role: str
    resolved: ResolvedModel
    prompt: str
    cache_state: str = "cold"
    session_id: Optional[str] = None
    resume: bool = False


def session_payload(spec: "AttemptSpec") -> Dict[str, Any]:
    """Session/cache fields an adapter stamps onto its ``model_call_started`` event.

    Carried in the existing event's payload (not a new event type — the event
    vocabulary is frozen, CP-SCHEMA) so the cold-freshness assertion can read the
    session id and resume flag straight from the immutable log.
    """
    return {"session_id": spec.session_id, "resumed": spec.resume,
            "cache_state": spec.cache_state}


@dataclass
class AttemptOutcome:
    """What an adapter reports back after emitting its events for an attempt.

    ``identity`` holds tiered identity fields the adapter observed (product,
    provider, auth/billing path, session/cache state, …); the runner merges these
    with task-derived identity (e.g. contamination_tier). ``leg_options`` holds
    per-leg costing kwargs the adapter measured — ``provider_reported_usd`` (for a
    product-reported basis) and/or ``machine_cost_usd`` — passed verbatim to the
    costing layer. ``invocation`` holds the exact CLI command the adapter executed
    for this leg (``leg``/``role``/``product_version``/``argv``/``cwd``) so the
    runner can record it in the per-run ``invocation.txt`` artifact — this is
    diagnostic provenance, NOT telemetry (never emitted to the event log or the
    schema-validated summary). All three default empty; nothing here is fabricated.
    """

    identity: Dict[str, Any] = field(default_factory=dict)
    leg_options: Dict[str, Any] = field(default_factory=dict)
    invocation: Dict[str, Any] = field(default_factory=dict)


class Adapter:
    """Protocol every adapter implements. Subclasses override :meth:`run_attempt`.

    ``container`` (a ``harness.container.exec.ContainerLaunch`` or ``None``) is set
    by the runner under ``--subject-isolation container`` so the subject CLI execs
    inside its offline container instead of on the host. ``None`` = the legacy host
    posture (dry-run, tests, batch-1). Adapters route their spawn through
    ``resolve_spawn`` so this is the only difference between the two modes.
    """

    name = "base"
    container = None  # Optional[ContainerLaunch]; set by the runner in container mode.

    def run_attempt(
        self, spec: AttemptSpec, subject_dir: str, emit: EmitFn
    ) -> AttemptOutcome:  # pragma: no cover - abstract
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Shared helpers for building event payloads
# --------------------------------------------------------------------------- #
def leg_identity_payload(resolved: ResolvedModel) -> Dict[str, Any]:
    """The leg-identifying fields a ``model_call_completed`` event must carry so
    the deriver can attribute per-leg provider/model/cost_basis (SPEC 2.7)."""
    return {
        "provider": tiered(resolved.provider, "authoritative"),
        "model_or_selector": tiered(resolved.model_or_selector, resolved.model_confidence),
        "cost_basis": resolved.cost_basis,
    }


def usage_field(value: Optional[int], confidence: str, reason: str = "") -> Dict[str, Any]:
    """A tiered usage field: a real count at ``confidence``, or ``unavailable``.

    A value of ``None`` is recorded as unavailable (never zero-filled), which is
    exactly how a product that does not expose a token class must be recorded.
    """
    if value is None:
        return unavailable(reason or "not exposed by this configuration")
    return tiered(value, confidence)


# Harness-internal env vars that point at lab/task material (the task dir, sealed
# hidden tests, gate report paths). Scrubbed from the agent subprocess environment so
# the agent is never handed a pointer to canonical/, hidden/ or the task dir
# (subject-isolation FIX B). Everything else (provider auth, PATH, HOME, …) is kept.
_HARNESS_ENV_KEYS = frozenset({
    "TASK_DIR", "TASK_WORKDIR", "TASK_YAML", "MANIFEST",
    "GATE_REPORT", "HIDDEN_REPORT", "HIDDEN_TESTS_DIR",
})


def agent_env() -> Dict[str, str]:
    """Environment for the agent subprocess: ``os.environ`` minus harness-internal keys.

    The agent must not receive any pointer to lab/task material (task dir, sealed
    hidden tests, gate report paths). Defensive: the runner does not export these
    today, but an outer shell or future code might — this guarantees the agent's
    view is clean regardless (subject-isolation FIX B). Paired with FIX A (cwd staged
    outside the lab repo), the agent has neither a relative path nor an env pointer to
    the answer/test material.
    """
    return {k: v for k, v in os.environ.items() if k not in _HARNESS_ENV_KEYS}


def cli_version(binary: str, container=None) -> str:
    """Product/CLI version string for the invocation.txt artifact and identity.

    In CONTAINER mode the version comes from the launched image's pinned label
    (``lab.cli.<product>.version``, asserted against the CLI at build time), because
    the host CLI is not the one that runs and the two drift. In HOST mode it runs
    ``<binary> --version`` (no model spend) and returns its first output line.
    Either way, ``"unavailable"`` when it cannot be established — never fabricated,
    never silently substituted from the other mode.
    """
    if container is not None and getattr(container, "image", None):
        from harness.container.exec import image_cli_version

        return image_cli_version(container.image, os.path.basename(binary))
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [binary, "--version"], capture_output=True, text=True,
            check=False, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    for line in (proc.stdout or proc.stderr or "").splitlines():
        if line.strip():
            return line.strip()
    return "unavailable"
