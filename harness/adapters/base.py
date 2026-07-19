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
#   HOST      — legacy weak posture: ALL tool permissions bypassed
#               (--dangerously-skip-permissions), confined ONLY by the throwaway
#               per-task .work/repo working directory on the bare dev VM. No
#               container, no network policy. Used by batch-1/revalidation.
#   CONTAINER — batch-2 posture (human decision 2026-07-19): the subject CLI execs
#               inside the task-tools Docker container with the network DISABLED
#               (--network=none), deps pre-baked into a per-task image, cwd-confined
#               to /subject. The deterministic gate runs offline in the same
#               posture. (The live agent leg's model-API egress allowlist is a
#               CP-SPEND finalization item; see harness/container/README.md.)
SUBJECT_PROFILE_HOST = "skip-all-tools; cwd-confined-.work-repo; dev-vm; no-container; no-network-policy"
SUBJECT_PROFILE_CONTAINER = "skip-all-tools; container-isolated; network=none; cwd-confined-/subject"

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
    costing layer. Both default empty; nothing here is fabricated.
    """

    identity: Dict[str, Any] = field(default_factory=dict)
    leg_options: Dict[str, Any] = field(default_factory=dict)


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
