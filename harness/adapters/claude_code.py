"""Product A adapter — drives ``claude -p --output-format json`` (SPEC 1.3).

Telemetry policy (non-negotiable):
  * Token usage comes from the CLI's JSON ``usage`` metadata (authoritative tier)
    — NEVER parsed from response prose, and the model is NEVER asked to report its
    own usage (CLAUDE.md rules 1 & 2).
  * A usage class the JSON does not report is recorded ``unavailable``, not 0.

Live execution bills a real account, so it is gated behind ``LAB_ALLOW_SPEND=1``
(the runner sets this only under a CP-SPEND-approved invocation). Command
construction and usage parsing are pure functions so they can be unit-tested
without spending.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List, Optional

from harness.telemetry.telemetry import tiered, unavailable

from .base import (
    Adapter,
    AttemptOutcome,
    AttemptSpec,
    EmitFn,
    leg_identity_payload,
    session_payload,
)

# claude -p JSON usage keys -> our token classes. Anything absent -> unavailable.
_USAGE_MAP = {
    "input_tokens": "input_tokens",
    "output_tokens": "output_tokens",
    "cache_creation_input_tokens": "cache_creation_tokens",
    "cache_read_input_tokens": "cache_read_tokens",
}


def build_command(prompt: str, model_id: str, *, session_id: Optional[str] = None,
                  resume: bool = False) -> List[str]:
    """Build the headless ``claude -p`` command (pure; no execution).

    Session flags implement the cache-protocol contract: a warm-series attempt
    resumes an existing session (``--resume <id>``) so the provider prompt-cache
    carries over; a cold attempt starts a fresh, explicitly-identified session
    (``--session-id <id>``) so freshness is provable from the id in the log. A
    resume without an id is a caller error (the runner guards this upstream).
    """
    cmd = [
        "claude", "-p", prompt,
        "--model", model_id,
        "--output-format", "json",
    ]
    if resume and session_id:
        cmd += ["--resume", session_id]
    elif session_id:
        cmd += ["--session-id", session_id]
    return cmd


def resolved_model_version(obj: Dict[str, Any]) -> Optional[str]:
    """Concrete model version the product reports actually served the request.

    ``claude -p --output-format json`` echoes the resolved model in the top-level
    ``model`` field (e.g. a dated ``claude-sonnet-4-6-YYYYMMDD``) — distinct from
    the alias we requested via ``--model`` (which may float, e.g. ``@default``).
    Returns that string, or ``None`` if the product exposes no concrete version
    (caller then keeps the requested selector — a resolved id is never invented).
    """
    model = (obj or {}).get("model")
    return model if isinstance(model, str) and model else None


def usage_from_claude_json(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Map ``claude -p --output-format json`` usage metadata to tiered usage.

    Reads only the structured ``usage`` object (authoritative). Missing classes
    are ``unavailable`` — never zero-filled. reasoning/tool_result tokens are not
    separately exposed here and are recorded unavailable.
    """
    raw = (obj or {}).get("usage") or {}
    usage: Dict[str, Any] = {}
    for src_key, cls in _USAGE_MAP.items():
        val = raw.get(src_key)
        usage[cls] = tiered(int(val), "authoritative") if isinstance(val, (int, float)) \
            else unavailable(f"{src_key} not present in product JSON usage")
    for cls in ("reasoning_tokens", "tool_result_tokens"):
        usage[cls] = unavailable("not exposed separately by product JSON")
    return usage


class ClaudeCodeAdapter(Adapter):
    name = "claude_code"

    def run_attempt(self, spec: AttemptSpec, subject_dir: str, emit: EmitFn) -> AttemptOutcome:
        if os.environ.get("LAB_ALLOW_SPEND") != "1":
            raise RuntimeError(
                "ClaudeCodeAdapter would incur live API spend; refused. This path "
                "runs only under a CP-SPEND-approved runner (LAB_ALLOW_SPEND=1). "
                "Use --dry-run for tests."
            )
        r = spec.resolved
        leg_meta = {"leg": spec.leg_id, "role": spec.role, **leg_identity_payload(r)}
        emit("model_call_started", **leg_meta, **session_payload(spec))

        cmd = build_command(spec.prompt, r.model_id or r.model_or_selector,
                            session_id=spec.session_id, resume=spec.resume)
        proc = subprocess.run(  # noqa: S603 - workshop-owned command
            cmd, cwd=subject_dir, capture_output=True, text=True, check=False,
        )
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            # Capture a bounded diagnostic so a non-JSON product response (e.g. a
            # CLI usage/validation error printed to stderr) is debuggable from the
            # event log instead of vanishing into all-unavailable usage.
            emit("failure", leg=spec.leg_id, category="adapter_json_parse",
                 returncode=proc.returncode,
                 stderr_snippet=(proc.stderr or "")[:500],
                 stdout_snippet=(proc.stdout or "")[:200])
            usage = {c: unavailable("product JSON unparseable") for c in _USAGE_MAP.values()}
            usage.update({c: unavailable("product JSON unparseable")
                          for c in ("reasoning_tokens", "tool_result_tokens")})
            emit("model_call_completed", usage=usage, **leg_meta)
            return AttemptOutcome(identity=_identity(r))

        resolved = resolved_model_version(payload)
        # Provenance in the immutable log: what we asked for vs what actually
        # served, stamped on the existing completed event (no new event type —
        # CP-SCHEMA respected). unavailable, never zero/blank, if not exposed.
        emit("model_call_completed", usage=usage_from_claude_json(payload),
             requested_selector=r.model_or_selector,
             resolved_model_version=resolved or "unavailable", **leg_meta)
        return AttemptOutcome(identity=_identity(r, resolved_version=resolved))


def _identity(r, resolved_version: Optional[str] = None) -> Dict[str, Any]:
    # model_or_selector records the CONCRETE resolved model version the product
    # reported (authoritative) in preference to the requested selector/alias — this
    # pins per-run reproducibility even when the manifest holds a floating alias
    # like '@default' (CP-SPEND floating-alias mitigation, 2026-07-19). If the
    # product exposes no concrete version, the requested selector is kept at its
    # declared tier; a resolved id is never invented (SPEC 6.3, CLAUDE.md rule 1).
    model_or_selector = tiered(resolved_version, "authoritative") if resolved_version \
        else tiered(r.model_or_selector, r.model_confidence)
    ident = {
        "product": tiered(r.product, "authoritative"),
        "provider": tiered(r.provider, "authoritative"),
        "model_or_selector": model_or_selector,
        "auth_billing_path": tiered("controlled_api", "authoritative"),
    }
    if r.region:
        ident["region"] = tiered(r.region, "proxy_observed")
    return ident
