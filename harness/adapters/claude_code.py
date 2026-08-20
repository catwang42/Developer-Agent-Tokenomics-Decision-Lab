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
from typing import Any, Dict, List, Optional, Tuple

from harness.container.exec import leg_container_name, resolve_spawn, spawn_with_timeout
from harness.telemetry.telemetry import tiered, unavailable

from .base import (
    SUBJECT_PERMISSION_PROFILE,
    Adapter,
    AttemptOutcome,
    AttemptSpec,
    DelegatedLeg,
    EmitFn,
    ResolvedModel,
    agent_env,
    cli_version,
    leg_identity_payload,
    session_payload,
)

# Workshop-owned timeout (SPEC 1.3): our timeout bounds a hung agentic run so one
# leg cannot stall a batch. Generous — an agentic coding turn can legitimately run
# for minutes. On timeout usage is unavailable (never zero), like any lost telemetry.
#
# This is only the FALLBACK. The budget in force is per task, pinned in the task's
# task.yaml and mirrored in the manifest (`agent_timeout_s`) and carried here on
# ``AttemptSpec.timeout_s`` — a flat bound charged the same 1800s to a 12-file
# migration and a one-file mapper test, and screening batch 1 shows what that costs
# (every W3 attempt right-censored at 1800s). A spec with no pin falls back here.
DEFAULT_TIMEOUT_S = 1800

# claude -p JSON usage keys -> our token classes. Anything absent -> unavailable.
_USAGE_MAP = {
    "input_tokens": "input_tokens",
    "output_tokens": "output_tokens",
    "cache_creation_input_tokens": "cache_creation_tokens",
    "cache_read_input_tokens": "cache_read_tokens",
}

# The SAME token classes as reported inside the per-model ``modelUsage`` object,
# which uses camelCase keys (the top-level ``usage`` object uses snake_case). Both
# spellings are the product's own machine-readable metadata — authoritative tier.
_MODEL_USAGE_MAP = {
    "inputTokens": "input_tokens",
    "outputTokens": "output_tokens",
    "cacheCreationInputTokens": "cache_creation_tokens",
    "cacheReadInputTokens": "cache_read_tokens",
}


def build_command(prompt: str, model_id: str, *, session_id: Optional[str] = None,
                  resume: bool = False, agents_json: Optional[str] = None) -> List[str]:
    """Build the headless ``claude -p`` command (pure; no execution).

    Session flags implement the cache-protocol contract: a warm-series attempt
    resumes an existing session (``--resume <id>``) so the provider prompt-cache
    carries over; a cold attempt starts a fresh, explicitly-identified session
    (``--session-id <id>``) so freshness is provable from the id in the log. A
    resume without an id is a caller error (the runner guards this upstream).

    ``agents_json`` (scripted delegation, P2) defines the executor subagent and
    the model it is bound to. It is passed only when the runner supplies a pinned
    split file — the flag is never added speculatively, so a non-P2 command is
    byte-identical to what previous batches ran.
    """
    cmd = [
        "claude", "-p", prompt,
        "--model", model_id,
        "--output-format", "json",
        # Headless mode has no interactive approver, so the DEFAULT permission mode
        # silently denies Edit/Write/Bash — the agent can read+reason but cannot
        # modify files (empty diff -> every task fails). Auto-approve tools so the
        # agent has full agentic capability in the isolated, reset-per-run subject
        # repo (SPEC 1.3 — workshop-owned; sandboxed, so bypass is appropriate).
        "--dangerously-skip-permissions",
    ]
    if resume and session_id:
        cmd += ["--resume", session_id]
    elif session_id:
        cmd += ["--session-id", session_id]
    if agents_json:
        cmd += ["--agents", agents_json]
    return cmd


def _model_usage_keys(obj: Dict[str, Any]) -> List[str]:
    """Concrete model ids the product metered for this turn (``modelUsage`` keys).

    ``claude -p --output-format json`` reports a ``modelUsage`` object keyed by the
    concrete model ids that actually served the request (e.g.
    ``claude-sonnet-4-6@<concrete>``, plus any auxiliary model the harness used).
    """
    mu = (obj or {}).get("modelUsage")
    if not isinstance(mu, dict):
        return []
    return sorted(k for k in mu if isinstance(k, str) and k)


def resolved_model_version(obj: Dict[str, Any], requested: Optional[str] = None) -> Optional[str]:
    """Concrete model version the product reports actually served the request.

    Source of truth is ``modelUsage`` (keyed by concrete ids), with the top-level
    ``model`` string as a fallback. When ``requested`` is given and exactly one
    metered id shares its base name (the part before ``@``), that id is returned —
    the primary model, which pins a floating alias like ``@default`` to a concrete
    version. Otherwise all metered ids are returned (comma-joined), else the
    ``model`` fallback, else ``None`` (caller keeps the requested selector — a
    resolved id is never invented).
    """
    keys = _model_usage_keys(obj)
    if keys:
        if requested:
            base = requested.split("@", 1)[0]
            primary = [k for k in keys if k.split("@", 1)[0] == base]
            if len(primary) == 1:
                return primary[0]
        return keys[0] if len(keys) == 1 else ",".join(keys)
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


def usage_from_model_usage_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Map ONE ``modelUsage[<model>]`` entry to tiered usage (pure).

    Same rules as the top-level parser: a class the product does not report for
    that model is ``unavailable``, never 0 — a model that did no cache reads and a
    model whose cache reads were not reported must not look identical.
    """
    entry = entry or {}
    usage: Dict[str, Any] = {}
    for src_key, cls in _MODEL_USAGE_MAP.items():
        val = entry.get(src_key)
        usage[cls] = tiered(int(val), "authoritative") if isinstance(val, (int, float)) \
            and not isinstance(val, bool) \
            else unavailable(f"{src_key} not present in product modelUsage entry")
    for cls in ("reasoning_tokens", "tool_result_tokens"):
        usage[cls] = unavailable("not exposed separately by product JSON")
    return usage


def split_usage_by_model(obj: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Per-model tiered usage from ``modelUsage`` — the per-leg split for P2.

    Returns ``{}`` when the product reports no per-model breakdown. That is a
    meaningful answer, not an empty one: it means the run's bill cannot be
    attributed to legs, and the caller must record the total on one leg and say
    the attribution is unavailable rather than inventing a division.
    """
    mu = (obj or {}).get("modelUsage")
    if not isinstance(mu, dict):
        return {}
    return {
        key: usage_from_model_usage_entry(val)
        for key, val in sorted(mu.items())
        if isinstance(key, str) and key and isinstance(val, dict)
    }


def _model_reported_cost(obj: Dict[str, Any], model_key: str) -> Optional[float]:
    """The product's own per-model ``costUSD``, if it reported one (diagnostic only).

    Recorded verbatim beside our derived cost; never used as the derived cost and
    never summed with one (SPEC 2.7 — a provider-reported figure is a separate
    basis, and this one is per-model on a run that may mix bases).
    """
    entry = ((obj or {}).get("modelUsage") or {}).get(model_key) or {}
    val = entry.get("costUSD")
    return float(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else None


_ALL_USAGE_CLASSES = tuple(_USAGE_MAP.values()) + ("reasoning_tokens", "tool_result_tokens")


def _unavailable_usage(reason: str) -> Dict[str, Any]:
    """Every token class recorded ``unavailable`` for ``reason`` — never zero-filled."""
    return {cls: unavailable(reason) for cls in _ALL_USAGE_CLASSES}


def _declared_legs(spec: AttemptSpec) -> List[Tuple[str, str, ResolvedModel]]:
    """The billing legs this attempt is *declared* to have (id, role, resolved).

    Under P2 one product invocation bills two models, so an attempt that loses its
    telemetry must still account for both legs — reporting only the conductor would
    silently drop the executor's spend from the run.
    """
    if spec.delegation:
        return [(leg.leg_id, leg.role, leg.resolved) for leg in spec.delegation.legs]
    return [(spec.leg_id, spec.role, spec.resolved)]


def _emit_lost_usage(emit: EmitFn, spec: AttemptSpec, reason: str) -> None:
    """Record every declared leg's usage as unavailable when the telemetry is lost."""
    for leg_id, role, resolved in _declared_legs(spec):
        emit("model_call_completed", usage=_unavailable_usage(reason),
             leg=leg_id, role=role, **leg_identity_payload(resolved))


def _delegated_leg_payload(leg: DelegatedLeg, metered_model: str) -> Dict[str, Any]:
    """Identity fields for a delegated leg whose usage came from ``modelUsage``.

    ``model_or_selector`` keeps the leg's MANIFEST-resolved model id, because that
    is the key the pinned pricing snapshot is indexed by; the concrete id the
    product metered is recorded separately in ``resolved_model_version``. Writing
    the metered id into ``model_or_selector`` would make an unpriced-but-real model
    crash costing instead of costing the leg it belongs to.
    """
    payload = dict(leg_identity_payload(leg.resolved))
    payload.update(leg=leg.leg_id, role=leg.role,
                   resolved_model_version=metered_model,
                   usage_source=f"modelUsage[{metered_model}]")
    return payload


def _unattributed_leg_payload(model_key: str) -> Dict[str, Any]:
    """Identity fields for a metered model that matches NO declared leg.

    Its tokens are real and stay on the bill, but we cannot say which side of the
    split spent them and the manifest does not price it — so the leg is explicitly
    ``cost_unavailable`` rather than being folded into whichever leg looks closest.
    """
    return {
        "leg": f"unattributed__{model_key}",
        "role": "unattributed",
        "provider": unavailable("metered model matches no declared delegation leg"),
        "model_or_selector": tiered(model_key, "authoritative"),
        "cost_basis": "cost_unavailable",
        "resolved_model_version": model_key,
        "usage_source": f"modelUsage[{model_key}]",
    }


def _emit_delegated_usage(emit: EmitFn, spec: AttemptSpec, payload: Dict[str, Any],
                          run_fields: Dict[str, Any]) -> None:
    """Split ONE product invocation's usage into the split's billing legs (P2).

    The product's own ``modelUsage`` metadata is the only admissible source: each
    declared leg gets the usage of the model it is bound to, matched on base model
    name (the manifest may pin a floating alias; the product meters the concrete
    version it served). Three cases are recorded honestly rather than smoothed over:

      * **No ``modelUsage`` at all** — the run's total lands on the conductor leg,
        the other legs are ``unavailable``, and a ``failure`` event says the
        attribution could not be made. The bill is never divided by guesswork.
      * **A declared leg the product never metered** — usage ``unavailable`` (not 0)
        plus a ``failure`` event, because "the executor did no work" and "delegation
        never happened" look identical in the tokens and only the second is a defect.
      * **A metered model matching no leg** — its own explicitly unattributed,
        ``cost_unavailable`` leg, so its tokens stay visible on the run.
    """
    dele = spec.delegation
    assert dele is not None  # caller checks; keeps the type checker honest
    per_model = split_usage_by_model(payload)
    provenance = dict(dele.provenance)
    conductor = dele.conductor

    if not per_model:
        head = dict(run_fields)
        head.update(leg_identity_payload(conductor.resolved))
        head.update(leg=conductor.leg_id, role=conductor.role,
                    usage_source="usage (run total; per-model split unavailable)",
                    delegation_attribution="unavailable")
        emit("model_call_completed", usage=usage_from_claude_json(payload),
             **head, **provenance)
        reason = ("product JSON reported no modelUsage object; this run's bill "
                  "cannot be attributed per leg")
        for leg in dele.legs[1:]:
            tail = dict(leg_identity_payload(leg.resolved))
            tail.update(leg=leg.leg_id, role=leg.role, delegation_attribution="unavailable")
            emit("model_call_completed", usage=_unavailable_usage(reason), **tail)
        emit("failure", leg=conductor.leg_id,
             category="delegation_attribution_unavailable", detail=reason)
        return

    # One event per declared leg, conductor first (so the run-level diagnostics and
    # the split provenance sit on a leg that always exists).
    matched: Dict[str, List[str]] = {}
    for model_key in per_model:
        leg = dele.leg_for_model(model_key)
        if leg is not None:
            matched.setdefault(leg.leg_id, []).append(model_key)

    for index, leg in enumerate(dele.legs):
        keys = matched.get(leg.leg_id, [])
        if not keys:
            # Declared but unmetered: unavailable, never 0, and flagged — under P2
            # an unmetered executor is evidence the delegation did not happen.
            fields = dict(run_fields) if index == 0 else {}
            fields.update(leg_identity_payload(leg.resolved))
            fields.update(leg=leg.leg_id, role=leg.role)
            if index == 0:
                fields.update(provenance)
            emit("model_call_completed",
                 usage=_unavailable_usage(
                     "product metered no usage for this leg's model in this run"),
                 **fields)
            emit("failure", leg=leg.leg_id, category="delegation_leg_unmetered",
                 detail=(f"leg {leg.leg_id!r} is declared by the pinned split but the "
                         f"product metered no usage for its model; the delegation may "
                         f"not have occurred"))
            continue
        for k_index, model_key in enumerate(sorted(keys)):
            fields = _delegated_leg_payload(leg, model_key)
            cost = _model_reported_cost(payload, model_key)
            if cost is not None:
                fields["model_reported_cost_usd"] = cost
            if index == 0 and k_index == 0:
                merged = dict(run_fields)
                merged.update(fields)
                merged.update(provenance)
                fields = merged
            emit("model_call_completed", usage=per_model[model_key], **fields)

    for model_key in sorted(per_model):
        if dele.leg_for_model(model_key) is not None:
            continue
        fields = _unattributed_leg_payload(model_key)
        cost = _model_reported_cost(payload, model_key)
        if cost is not None:
            fields["model_reported_cost_usd"] = cost
        emit("model_call_completed", usage=per_model[model_key], **fields)
        emit("failure", leg=fields["leg"], category="delegation_model_unattributed",
             detail=(f"the product metered {model_key!r}, which matches no leg declared "
                     f"by the pinned split; its tokens are recorded on their own leg "
                     f"with cost unavailable"))


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
        dele = spec.delegation
        leg_meta = {"leg": spec.leg_id, "role": spec.role, **leg_identity_payload(r)}
        # One product invocation either way. Under P2 it bills two models, so the
        # started event carries the split's provenance and the per-model completed
        # events below carry the legs.
        emit("model_call_started", **leg_meta, **session_payload(spec),
             **(dele.provenance if dele else {}))

        prompt = spec.prompt + dele.brief if dele else spec.prompt
        cmd = build_command(prompt, r.model_id or r.model_or_selector,
                            session_id=spec.session_id, resume=spec.resume,
                            agents_json=dele.agents_json if dele else None)
        # Host mode runs cmd in subject_dir; container mode wraps it in `docker run`
        # (offline by default). Only the argv/cwd differ — timeout, JSON parsing and
        # telemetry emission below are identical (the container leg's model-API
        # egress network is a CP-SPEND item; see harness/container/README.md).
        cname = leg_container_name(self.container, spec.leg_id)
        argv, cwd = resolve_spawn(self.container, cmd, subject_dir, name=cname)
        timeout_s = spec.timeout_s or DEFAULT_TIMEOUT_S
        # Exact command executed, for the per-run invocation.txt artifact (run
        # provenance, not telemetry). Full argv is recorded; the runner redacts any
        # credential-bearing environment values when it writes the file.
        invocation = {
            "leg": spec.leg_id, "role": spec.role,
            "product_version": cli_version("claude", self.container),
            "argv": list(argv), "cwd": cwd, "timeout_s": timeout_s,
            "container_name": cname or "host-mode",
        }
        proc = spawn_with_timeout(
            argv, cwd=cwd, env=agent_env(),  # scrub task pointers (FIX B)
            timeout_s=timeout_s, container_name=cname,
        )
        if proc.timed_out:
            # Record the CLI's exit/output (partial, if any) for invocation.txt — a
            # command that produced no output is itself the diagnosis (the runner
            # redacts credentials when writing the file).
            invocation.update(exit_code="timeout",
                              stdout=proc.stdout, stderr=proc.stderr,
                              container_disposition=proc.container or "no-container")
            emit("failure", leg=spec.leg_id, category="claude_timeout",
                 timeout_s=timeout_s, container_name=cname or "host-mode",
                 container_disposition=proc.container or "no-container")
            _emit_lost_usage(emit, spec, "run timed out before product JSON returned")
            return AttemptOutcome(identity=_identity(r), invocation=invocation)
        invocation.update(exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
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
            _emit_lost_usage(emit, spec, "product JSON unparseable")
            return AttemptOutcome(identity=_identity(r), invocation=invocation)

        resolved = resolved_model_version(payload, requested=r.model_or_selector)
        # Provenance + self-diagnosis in the immutable log: what we asked for vs what
        # served, plus the agentic-execution signals that distinguish a real coding
        # attempt from a no-write run (num_turns, permission_denials, is_error). All
        # on the existing completed event (no new event type — CP-SCHEMA respected).
        # Run-level (not per-leg): under P2 these describe the single invocation, so
        # they are stamped on the conductor's event only, never duplicated per leg.
        run_fields = {
            "requested_selector": r.model_or_selector,
            "resolved_model_version": resolved or "unavailable",
            "model_usage_keys": _model_usage_keys(payload),
            "num_turns": payload.get("num_turns"),
            "permission_denials": len(payload.get("permission_denials") or []),
            "is_error": payload.get("is_error"),
            "subtype": payload.get("subtype"),
            "result_chars": len(payload.get("result") or ""),
            "product_reported_cost_usd": payload.get("total_cost_usd"),
        }
        if dele:
            _emit_delegated_usage(emit, spec, payload, run_fields)
        else:
            emit("model_call_completed", usage=usage_from_claude_json(payload),
                 **run_fields, **leg_meta)
        return AttemptOutcome(identity=_identity(r, resolved_version=resolved),
                              invocation=invocation)


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
        "permission_profile": tiered(SUBJECT_PERMISSION_PROFILE, "authoritative"),
    }
    if r.region:
        ident["region"] = tiered(r.region, "proxy_observed")
    return ident
