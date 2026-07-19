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
    """One execution attempt = one billing leg."""

    leg_id: str
    role: str
    resolved: ResolvedModel
    prompt: str


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
    """Protocol every adapter implements. Subclasses override :meth:`run_attempt`."""

    name = "base"

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
