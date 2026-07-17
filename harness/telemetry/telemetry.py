"""Canonical telemetry: event log, run-summary derivation, and validation.

SPEC 2.7 requires telemetry to be captured as an *immutable event log* plus a
*derived run summary*. Every field carries a value and a source/confidence tier;
unavailable is recorded as unavailable and is **never** zero-filled (CLAUDE.md
rules 1 & 3). Structural validation uses ``jsonschema`` (a mandatory, pinned
dependency — see requirements.txt); there is no fallback validation path, so a
missing/mismatched environment fails loudly rather than silently degrading.

Nothing here makes network calls or invokes a model. It only records and derives
from telemetry that a caller (an adapter/runner) supplies.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import jsonschema
except ImportError as exc:  # pragma: no cover - environment guard
    raise ImportError(
        "jsonschema is a mandatory, pinned dependency of the telemetry validator "
        "(see requirements.txt). There is no fallback validation path. Install it "
        "into the project venv:\n    .venv/bin/pip install -r requirements.txt"
    ) from exc

CONFIDENCE_TIERS = ("authoritative", "derived", "proxy_observed", "unavailable")

# The immutable event vocabulary (SPEC 2.7, "Event-level storage").
EVENT_TYPES = (
    "model_call_started",
    "model_call_completed",
    "tool_invoked",
    "tool_completed",
    "file_read",
    "test_run",
    "retry",
    "escalation",
    "verifier_call",
    "subagent_call",
    "human_review_started",
    "human_review_completed",
    "correction",
    "failure",
    "acceptance",
)

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema-v2.json")

# Token classes summed from ``model_call_completed`` events into ``usage``.
_USAGE_TOKEN_CLASSES = (
    "input_tokens",
    "cache_creation_tokens",
    "cache_read_tokens",
    "output_tokens",
    "reasoning_tokens",
    "tool_result_tokens",
)


# --------------------------------------------------------------------------- #
# Tiered-value helpers
# --------------------------------------------------------------------------- #
def tiered(value: Any, confidence: str, **extra: Any) -> Dict[str, Any]:
    """Build a tiered field. Guards against silently mislabelling data.

    Enforces the two invariants the validator also checks, so that data is
    born correct: an ``unavailable`` field must carry ``value=None`` (no
    zero-fill), and an available field must carry a non-null value.
    """
    if confidence not in CONFIDENCE_TIERS:
        raise ValueError(f"unknown confidence tier: {confidence!r}")
    if confidence == "unavailable" and value is not None:
        raise ValueError("unavailable fields must have value=None (never zero-filled)")
    if confidence != "unavailable" and value is None:
        raise ValueError(f"{confidence} field must have a non-null value")
    field = {"value": value, "confidence": confidence}
    field.update(extra)
    return field


def unavailable(reason: str = "") -> Dict[str, Any]:
    """A field whose measurement is unavailable — recorded as such, not as 0."""
    field: Dict[str, Any] = {"value": None, "confidence": "unavailable"}
    if reason:
        field["reason"] = reason
    return field


def _is_tiered(obj: Any) -> bool:
    return isinstance(obj, dict) and "value" in obj and "confidence" in obj


# --------------------------------------------------------------------------- #
# Event log — append-only JSONL writer/reader
# --------------------------------------------------------------------------- #
class EventLog:
    """Append-only JSONL event log for a single run (SPEC 2.7).

    Immutability is enforced by contract: this writer only ever appends, and
    each ``append`` flushes a single JSON object on its own line. The file is
    the source of truth from which the run summary is derived.
    """

    def __init__(self, path: str):
        self.path = path
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)

    def append(self, event_type: str, ts: str, **payload: Any) -> Dict[str, Any]:
        """Append one event. ``ts`` is a caller-supplied timestamp (e.g. ISO8601).

        The caller owns the clock so runs are deterministic and replayable; this
        module never reads the wall clock itself.
        """
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event_type: {event_type!r}")
        if not ts:
            raise ValueError("event requires a caller-supplied 'ts'")
        event = {"event_type": event_type, "ts": ts}
        event.update(payload)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True) + "\n")
        return event

    def read(self) -> List[Dict[str, Any]]:
        return list(read_events(self.path))


def read_events(path: str) -> Iterable[Dict[str, Any]]:
    """Yield events from a JSONL log, skipping blank lines."""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


# --------------------------------------------------------------------------- #
# Run-summary derivation
# --------------------------------------------------------------------------- #
def _aggregate_token_class(contributions: List[Tuple[Any, str]]) -> Dict[str, Any]:
    """Sum a token class across events.

    ``contributions`` is a list of (value, confidence) pairs from events that
    reported this class. Events that did not report it (or reported it
    unavailable) are simply absent from the list. If nothing reported it, the
    aggregate is *unavailable* — never 0. Confidence stays ``authoritative``
    only if every contribution was authoritative; otherwise the aggregate is
    ``derived``.
    """
    usable = [(v, c) for (v, c) in contributions if c != "unavailable" and v is not None]
    if not usable:
        return unavailable("no event reported this token class")
    total = sum(v for v, _ in usable)
    all_auth = all(c == "authoritative" for _, c in usable)
    return tiered(total, "authoritative" if all_auth else "derived")


def _count_events(events: List[Dict[str, Any]], event_type: str) -> int:
    return sum(1 for e in events if e.get("event_type") == event_type)


def _leg_usage_from_events(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Aggregate token classes from ``model_call_completed`` events for one leg."""
    usage: Dict[str, Dict[str, Any]] = {}
    for cls in _USAGE_TOKEN_CLASSES:
        contribs: List[Tuple[Any, str]] = []
        for e in events:
            if e.get("event_type") != "model_call_completed":
                continue
            field = (e.get("usage") or {}).get(cls)
            if _is_tiered(field):
                contribs.append((field["value"], field["confidence"]))
        usage[cls] = _aggregate_token_class(contribs)
    return usage


def derive_summary(
    events: List[Dict[str, Any]],
    *,
    run_id: str,
    task_id: str,
    task_suite_version: str,
    configuration_id: str,
    manifest_ref: str,
    identity: Optional[Dict[str, Any]] = None,
    economics: Optional[Dict[str, Any]] = None,
    human_effort: Optional[Dict[str, Any]] = None,
    hidden_test_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Derive a run summary from an event log (SPEC 2.7).

    Aggregation rules:
      * Token usage is summed across ``model_call_completed`` events. A leg is
        identified by an event's ``leg`` field (default ``"main"``); each leg
        gets its own usage block, and top-level ``usage`` is the sum across legs.
        This makes dual-bill (C5) workflows auditable.
      * Behaviour counts are event counts (turns, retries, tool calls, …).
      * Nothing is zero-filled: a class no event reported stays *unavailable*.
      * ``economics``/``human_effort``/``identity`` are supplied by the caller
        (an adapter knows the billing path, seat basis, and human timings); this
        function does not invent them. ``economics.cost_basis`` is required.
    """
    events = list(events)

    # Group model-call events by billing leg.
    legs_seen: List[str] = []
    for e in events:
        if e.get("event_type") == "model_call_completed":
            leg = e.get("leg", "main")
            if leg not in legs_seen:
                legs_seen.append(leg)
    if not legs_seen:
        legs_seen = ["main"]

    legs: List[Dict[str, Any]] = []
    for leg in legs_seen:
        leg_events = [
            e for e in events
            if e.get("event_type") == "model_call_completed" and e.get("leg", "main") == leg
        ]
        leg_meta_source = next((e for e in leg_events), {})
        legs.append({
            "leg_id": leg,
            "role": leg_meta_source.get("role", leg),
            "provider": leg_meta_source.get("provider", unavailable("not reported by adapter")),
            "model_or_selector": leg_meta_source.get(
                "model_or_selector", unavailable("not reported by adapter")),
            "cost_basis": leg_meta_source.get("cost_basis", "cost_unavailable"),
            "usage": _leg_usage_from_events(leg_events),
        })

    # Top-level usage = sum across all legs (dual-bill aggregation).
    usage: Dict[str, Any] = {}
    for cls in _USAGE_TOKEN_CLASSES:
        contribs: List[Tuple[Any, str]] = []
        for leg in legs:
            field = leg["usage"][cls]
            if _is_tiered(field):
                contribs.append((field["value"], field["confidence"]))
        usage[cls] = _aggregate_token_class(contribs)

    # Search/code-execution usage: only present if adapters emit them; else unavailable.
    for cls in ("search_ops", "search_charges_usd", "code_exec_usage", "code_exec_charges_usd"):
        usage[cls] = unavailable("not exposed by this configuration")

    # Behaviour: derived event counts.
    tool_calls = Counter(
        e.get("tool", "unknown") for e in events if e.get("event_type") == "tool_invoked"
    )
    failures = Counter(
        e.get("category", "uncategorized") for e in events if e.get("event_type") == "failure"
    )
    file_reads = _count_events(events, "file_read")
    byte_contribs = [
        (e["bytes"], "authoritative")
        for e in events
        if e.get("event_type") == "file_read" and isinstance(e.get("bytes"), (int, float))
    ]

    behavior = {
        "turns": tiered(_count_events(events, "model_call_completed"), "derived"),
        "tool_calls_by_type": (
            tiered(dict(tool_calls), "derived") if tool_calls
            else unavailable("no tool_invoked events")
        ),
        "file_reads": tiered(file_reads, "derived") if file_reads else unavailable("no file_read events"),
        "file_read_bytes": (
            tiered(sum(v for v, _ in byte_contribs), "derived") if byte_contribs
            else unavailable("byte counts not measured")
        ),
        "files_modified": (
            tiered(len({e["path"] for e in events
                        if e.get("event_type") == "correction" and e.get("path")}), "derived")
            if any(e.get("event_type") == "correction" and e.get("path") for e in events)
            else unavailable("file modifications not tracked in event log")
        ),
        "retries": tiered(_count_events(events, "retry"), "derived"),
        "escalations": tiered(_count_events(events, "escalation"), "derived"),
        "subagent_calls": tiered(_count_events(events, "subagent_call"), "derived"),
        "verifier_calls": tiered(_count_events(events, "verifier_call"), "derived"),
        "failures_by_category": (
            tiered(dict(failures), "derived") if failures
            else tiered({}, "derived")
        ),
    }

    # Acceptance: last acceptance event wins; else error.
    acc_events = [e for e in events if e.get("event_type") == "acceptance"]
    if acc_events:
        acc = acc_events[-1]
        acceptance = {
            "result": acc.get("result", "error"),
            "gate_checks": acc.get("gate_checks", {}),
            "intention_to_route": acc.get("intention_to_route"),
            "completed_route": acc.get("completed_route"),
        }
    else:
        acceptance = {
            "result": "error",
            "gate_checks": {},
            "intention_to_route": None,
            "completed_route": None,
        }

    # Economics: caller-supplied; cost_basis mandatory. Never fabricated here.
    econ = dict(economics or {})
    econ.setdefault("cost_basis", "cost_unavailable")
    for money in ("provider_cost_usd", "machine_cost_usd", "marginal_operating_usd",
                  "fully_allocated_usd", "total_cost_usd", "subscription_allocation_basis"):
        econ.setdefault(money, unavailable("not supplied to deriver"))

    human = dict(human_effort or {})
    for m in ("active_minutes", "review_minutes", "correction_minutes", "blocked_minutes"):
        human.setdefault(m, unavailable("not recorded"))

    ident = dict(identity or {})
    for f in ("product", "provider", "model_or_selector", "product_version",
              "auth_billing_path", "region", "reasoning_config", "permission_profile",
              "network_policy", "session_state", "cache_state"):
        ident.setdefault(f, unavailable("not supplied to deriver"))

    summary: Dict[str, Any] = {
        "run_id": run_id,
        "task_id": task_id,
        "task_suite_version": task_suite_version,
        "configuration_id": configuration_id,
        "manifest_ref": manifest_ref,
        "identity": ident,
        "usage": usage,
        "behavior": behavior,
        "economics": econ,
        "human_effort": human,
        "acceptance": acceptance,
        "legs": legs,
    }
    if hidden_test_hash is not None:
        summary["hidden_test_hash"] = hidden_test_hash
    return summary


# --------------------------------------------------------------------------- #
# Validation
#
# Two layers, no fallback:
#   1. Structural — jsonschema Draft-07 against schema-v2.json (mandatory dep).
#      Owns: required keys, types, enums (confidence tier, cost_basis,
#      configuration_id), and the {value, confidence} shape of every field.
#   2. Semantic — the domain invariant JSON Schema cannot express: a field is
#      never zero-filled/imputed when unavailable, and an available field is
#      never null (CLAUDE.md rules 1 & 3).
# --------------------------------------------------------------------------- #
_SCHEMA_VALIDATOR: Optional["jsonschema.Draft7Validator"] = None


def _schema_validator() -> "jsonschema.Draft7Validator":
    global _SCHEMA_VALIDATOR
    if _SCHEMA_VALIDATOR is None:
        with open(_SCHEMA_PATH, encoding="utf-8") as fh:
            schema = json.load(fh)
        jsonschema.Draft7Validator.check_schema(schema)
        _SCHEMA_VALIDATOR = jsonschema.Draft7Validator(schema)
    return _SCHEMA_VALIDATOR


def _schema_errors(summary: Dict[str, Any]) -> List[str]:
    validator = _schema_validator()
    errors = sorted(validator.iter_errors(summary), key=lambda e: list(e.absolute_path))
    out: List[str] = []
    for e in errors:
        loc = getattr(e, "json_path", None) or "$"
        out.append(f"schema: {loc}: {e.message}")
    return out


def _semantic_tiered_walk(obj: Any, path: str, reasons: List[str]) -> None:
    """Recursively enforce the no-zero-fill / no-null-available invariant.

    Applies only to well-formed tiered fields (valid tier + a value key);
    malformed tiered fields are already reported by the structural layer.
    """
    if isinstance(obj, dict):
        if "confidence" in obj and "value" in obj and obj["confidence"] in CONFIDENCE_TIERS:
            conf = obj["confidence"]
            if conf == "unavailable" and obj["value"] is not None:
                reasons.append(
                    f"{path}: zero-filled/imputed unavailable field "
                    f"(value={obj['value']!r}; must be null)"
                )
            elif conf != "unavailable" and obj["value"] is None:
                reasons.append(f"{path}: labelled {conf} but value is null")
        for key, val in obj.items():
            _semantic_tiered_walk(val, f"{path}.{key}", reasons)
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            _semantic_tiered_walk(val, f"{path}[{i}]", reasons)


def validate_summary(summary: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate a run summary. Returns (ok, reasons).

    Runs the structural (jsonschema) layer then the semantic (no-zero-fill)
    layer. jsonschema is mandatory; if it were missing this module would have
    failed to import.
    """
    if not isinstance(summary, dict):
        return False, ["summary is not a JSON object"]
    reasons = _schema_errors(summary)
    _semantic_tiered_walk(summary, "$", reasons)
    return (len(reasons) == 0), reasons


def validate(run_dir: str) -> Tuple[bool, List[str]]:
    """Validate a run directory containing ``summary.json`` (SPEC 2.7).

    If ``events.jsonl`` is present, its lines are checked for a known
    ``event_type``. Returns (ok, reasons).
    """
    reasons: List[str] = []
    summary_path = os.path.join(run_dir, "summary.json")
    if not os.path.exists(summary_path):
        return False, [f"missing summary.json in {run_dir}"]
    try:
        with open(summary_path, encoding="utf-8") as fh:
            summary = json.load(fh)
    except json.JSONDecodeError as exc:
        return False, [f"summary.json is not valid JSON: {exc}"]

    ok, summary_reasons = validate_summary(summary)
    reasons.extend(summary_reasons)

    events_path = os.path.join(run_dir, "events.jsonl")
    if os.path.exists(events_path):
        for i, event in enumerate(read_events(events_path)):
            et = event.get("event_type")
            if et not in EVENT_TYPES:
                reasons.append(f"events.jsonl line {i + 1}: unknown event_type {et!r}")
            if not event.get("ts"):
                reasons.append(f"events.jsonl line {i + 1}: missing ts")

    return (len(reasons) == 0), reasons
