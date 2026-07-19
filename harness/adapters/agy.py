"""Product B adapter (``agy``) — WORKSHOP-OWNED black-box wrapper (SPEC 1.3, 6.3).

Product B exposes limited telemetry. This wrapper is where its headless quirks
live: OUR exit codes and OUR timeout are authoritative (the workshop owns them),
the product **selector label is recorded verbatim** (we never infer the backend
model id — SPEC 6.3), and any usage the product does not expose is recorded
``unavailable``, never zero-filled. If the product exposes a cost figure it is
carried as a provider-reported (proxy_observed) cost.

Live execution is gated behind ``LAB_ALLOW_SPEND=1`` like every billing adapter.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List, Optional

from harness.telemetry.telemetry import tiered, unavailable

from .base import (
    SUBJECT_PERMISSION_PROFILE,
    Adapter,
    AttemptOutcome,
    AttemptSpec,
    EmitFn,
    leg_identity_payload,
    session_payload,
)

# Workshop-owned exit codes (SPEC 1.3 — ours, not the product's).
EXIT_OK = 0
EXIT_PRODUCT_ERROR = 40
EXIT_TIMEOUT = 41

DEFAULT_TIMEOUT_S = 1800


def build_command(prompt: str, selector_label: str) -> List[str]:
    """Build the headless ``agy`` command (pure; no execution).

    ``selector_label`` is passed through verbatim via ``--model`` (agy's model
    selector IS the human label, e.g. "Gemini 3.5 Flash (High)", per ``agy
    models``); we never translate it to a backend model id.
    ``--dangerously-skip-permissions`` auto-approves tool use so the headless agent
    can actually modify files (without it the agent cannot write — empty diff).
    ``--print`` runs a single prompt non-interactively.
    """
    return ["agy", "run", "--dangerously-skip-permissions",
            "--model", selector_label, "--print", prompt]


def usage_from_agy_json(obj: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Map any product-exposed usage to tiered fields; unexposed -> unavailable.

    Product B usage is captured as ``proxy_observed`` (product-reported, not an
    authoritative provider meter). Absent classes are unavailable, never 0.
    """
    raw = (obj or {}).get("usage") or {}
    usage: Dict[str, Any] = {}
    for cls in ("input_tokens", "cache_creation_tokens", "cache_read_tokens", "output_tokens",
                "reasoning_tokens", "tool_result_tokens"):
        val = raw.get(cls)
        usage[cls] = tiered(int(val), "proxy_observed") if isinstance(val, (int, float)) \
            else unavailable("Product B does not expose this token class")
    return usage


class AgyAdapter(Adapter):
    name = "agy"

    def run_attempt(self, spec: AttemptSpec, subject_dir: str, emit: EmitFn) -> AttemptOutcome:
        if os.environ.get("LAB_ALLOW_SPEND") != "1":
            raise RuntimeError(
                "AgyAdapter would incur live product spend; refused. Runs only "
                "under a CP-SPEND-approved runner (LAB_ALLOW_SPEND=1). Use --dry-run."
            )
        r = spec.resolved
        leg_meta = {"leg": spec.leg_id, "role": spec.role, **leg_identity_payload(r)}
        # Product B does not expose session/cache control, so we do NOT inject a
        # session flag into its command (never invent product flags). We DO record
        # the runner's cache-state intent + session id for traceability; freshness
        # for a black-box product is best-effort (a fresh process, no resume asked),
        # recorded and reported as such — never claimed as authoritative.
        emit("model_call_started", **leg_meta, **session_payload(spec))

        cmd = build_command(spec.prompt, r.model_or_selector)
        payload: Optional[Dict[str, Any]] = None
        try:
            proc = subprocess.run(  # noqa: S603 - workshop-owned command
                cmd, cwd=subject_dir, capture_output=True, text=True,
                check=False, timeout=DEFAULT_TIMEOUT_S,
            )
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError:
                payload = None
        except subprocess.TimeoutExpired:
            emit("failure", leg=spec.leg_id, category="agy_timeout", exit_code=EXIT_TIMEOUT)

        usage = usage_from_agy_json(payload)
        emit("model_call_completed", usage=usage, **leg_meta)

        leg_options: Dict[str, Any] = {}
        reported = (payload or {}).get("cost_usd") if isinstance(payload, dict) else None
        if isinstance(reported, (int, float)):
            leg_options["provider_reported_usd"] = float(reported)

        identity = {
            "product": tiered(r.product, "authoritative"),
            "provider": tiered(r.provider, "authoritative"),
            # Verbatim selector label; backend id NOT inferred (SPEC 6.3).
            "model_or_selector": tiered(r.model_or_selector, "proxy_observed"),
            "auth_billing_path": tiered("product_blackbox", "authoritative"),
            "permission_profile": tiered(SUBJECT_PERMISSION_PROFILE, "authoritative"),
        }
        return AttemptOutcome(identity=identity, leg_options=leg_options)
