"""SYNTHETIC stub adapter — for ``--dry-run`` and unit tests ONLY (no spend).

Emits a deterministic, clearly-synthetic event stream for one attempt so the full
runner pipeline (event log -> derived summary -> costing -> validation) can be
exercised in CI without any model API call, clone, or network. It writes nothing
itself; the runner routes dry-run output to a caller-supplied out-root, never under
``results/`` (CLAUDE.md rule 1).

Usage realism mirrors the config surface, so the pipeline sees the same shapes it
will in production:
  * controlled_api leg  -> full authoritative token usage.
  * product_blackbox leg -> token usage ``unavailable`` (a black-box product need
    not expose tokens), plus a synthetic provider-reported cost so the
    provider_reported cost path is exercised.

Deterministic: token counts are a fixed function of the leg id, so a re-run
produces an identical tree (feasibility criterion 3 in spirit) and tests are stable.
"""

from __future__ import annotations

from typing import Dict

from harness.telemetry.telemetry import tiered

from .base import (
    Adapter,
    AttemptOutcome,
    AttemptSpec,
    EmitFn,
    leg_identity_payload,
    session_payload,
    usage_field,
)

# Fixed synthetic token profiles by role class. Round numbers, obviously not real.
_SYNTHETIC_PROFILE = {
    "economical": {"input_tokens": 4000, "cache_creation_tokens": 0,
                   "cache_read_tokens": 0, "output_tokens": 1200},
    "strong": {"input_tokens": 6000, "cache_creation_tokens": 500,
               "cache_read_tokens": 2000, "output_tokens": 1500},
}


def _profile_for(spec: AttemptSpec) -> Dict[str, int]:
    """Pick a synthetic token profile from the leg's economic role."""
    econ_like = ("econ" in spec.leg_id) or ("ECON" in (spec.resolved.model_or_selector or ""))
    return _SYNTHETIC_PROFILE["economical" if econ_like else "strong"]


class StubAdapter(Adapter):
    """Synthetic adapter used whenever the runner is in ``--dry-run`` mode."""

    name = "stub"

    def run_attempt(self, spec: AttemptSpec, subject_dir: str, emit: EmitFn) -> AttemptOutcome:
        r = spec.resolved
        leg_meta = {"leg": spec.leg_id, "role": spec.role, **leg_identity_payload(r)}

        emit("model_call_started", **leg_meta, **session_payload(spec))
        # A couple of representative behaviour events so the summary has content.
        emit("tool_invoked", leg=spec.leg_id, tool="Read")
        emit("file_read", leg=spec.leg_id, path="SYNTHETIC/src/example.ts", bytes=2048)
        emit("tool_invoked", leg=spec.leg_id, tool="Edit")
        emit("test_run", leg=spec.leg_id, suite="SYNTHETIC")

        leg_options: Dict[str, object] = {}
        if r.product_surface == "product_blackbox":
            # Black-box product: token usage unavailable (never zero-filled); a
            # synthetic provider-reported cost stands in for a product-exposed figure.
            usage = {
                cls: usage_field(None, "unavailable", "product does not expose token counts")
                for cls in ("input_tokens", "cache_creation_tokens",
                            "cache_read_tokens", "output_tokens")
            }
            leg_options["provider_reported_usd"] = 0.0137  # SYNTHETIC product-reported cost
        else:
            profile = _profile_for(spec)
            usage = {cls: tiered(val, "authoritative") for cls, val in profile.items()}

        emit("model_call_completed", usage=usage, **leg_meta)

        identity = {
            "product": tiered(r.product, "authoritative"),
            "provider": tiered(r.provider, "authoritative"),
            "model_or_selector": tiered(r.model_or_selector, r.model_confidence),
            "auth_billing_path": tiered("SYNTHETIC-dry-run", "authoritative"),
            "session_state": tiered("resumed" if spec.resume else "fresh", "authoritative"),
            "cache_state": tiered(spec.cache_state, "authoritative"),
            "network_policy": tiered("offline", "authoritative"),
        }
        if r.region:
            identity["region"] = tiered(r.region, "proxy_observed")
        return AttemptOutcome(identity=identity, leg_options=leg_options)
