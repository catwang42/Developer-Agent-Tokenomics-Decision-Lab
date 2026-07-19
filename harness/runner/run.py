"""Controlled harness runner (SPEC 2.1–2.3, 2.7).

Turns ``(task, configuration/policy, manifest)`` into an immutable event log plus a
derived, validated run summary. Exit 0 only when the audit-grade telemetry
validator passes on the completed run directory.

Design (see plans/PHASE-3-harness-feasibility.md):
  * Adapters emit telemetry events; they never write the summary, run the gate, or
    fabricate usage (missing usage -> ``unavailable``, not 0).
  * The runner owns the clock, the acceptance gate (deterministic, independent of
    the generating model — SPEC 2.6), policy semantics (P0 static / P1 cheap-first
    escalation), and cost derivation under the declared cost basis.
  * ``--dry-run`` uses the synthetic :class:`StubAdapter` and a synthetic gate — no
    model spend, no clone, no network — and writes ONLY under ``--out-root`` (never
    ``results/``). A live run refuses to start unless ``LAB_ALLOW_SPEND=1`` (set
    only under a CP-SPEND-approved invocation).

Every volatile name/price resolves through the delivery manifest (SPEC 1.4); the
runner refuses to start if any required field is missing or still a placeholder.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import yaml

from harness.adapters import REAL_ADAPTERS, ResolvedModel, StubAdapter
from harness.adapters.base import AttemptSpec
from harness.telemetry.costing import cost_for_legs, load_prices
from harness.telemetry.telemetry import EventLog, derive_summary, tiered, unavailable, validate

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COST_BASES = ("marginal_api_cost", "allocated_subscription_cost",
              "provider_reported_cost", "cost_unavailable")

# Values that mean "not resolved yet" — a live run must not proceed on these.
_PLACEHOLDERS = {
    "TBD", "DECLARE_AT_DELIVERY", "EXACT-VERSIONED-ID", "YYYY-MM-DD",
    "verbatim label from product", "null", "None", "",
}
_PRODUCT_LABELS = {"PRODUCT_A": "Product A", "PRODUCT_B": "Product B"}
_POLICY_FILES = {"P0": "p0-baseline.yaml", "P1": "p1-cheap-first.yaml"}


class RunnerError(Exception):
    """A configuration/resolution problem that must stop the run before any work."""


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _is_placeholder(val: Any) -> bool:
    return val is None or str(val).strip() in _PLACEHOLDERS or "YYYY" in str(val)


def _require_resolved(field: str, val: Any, model_ref: str) -> Any:
    if _is_placeholder(val):
        raise RunnerError(
            f"manifest {model_ref}.{field} is unresolved ({val!r}); fill the delivery "
            f"manifest (CP-SPEND) before a live run, or use --dry-run with a synthetic manifest"
        )
    return val


# --------------------------------------------------------------------------- #
# Manifest resolution (SPEC 1.4)
# --------------------------------------------------------------------------- #
def resolve_model(manifest: Dict[str, Any], model_ref: str, product: str) -> ResolvedModel:
    """Resolve a model_ref to a concrete, priced model or verbatim selector.

    Refuses (RunnerError) on a missing entry, unresolved placeholder, or bad
    cost_basis — this is exactly what keeps live runs from starting before the
    manifest is filled at CP-SPEND.
    """
    entry = (manifest.get("configurations") or {}).get(model_ref)
    if not entry:
        raise RunnerError(f"manifest has no configuration for model_ref {model_ref!r}")

    provider = _require_resolved("provider", entry.get("provider"), model_ref)
    cost_basis = _require_resolved("cost_basis", entry.get("cost_basis"), model_ref)
    if cost_basis not in COST_BASES:
        raise RunnerError(f"{model_ref}.cost_basis {cost_basis!r} not in {COST_BASES}")
    surface = entry.get("product_surface")

    region = entry.get("region")
    region = None if _is_placeholder(region) else region
    seat = entry.get("seat_allocation_usd")
    seat = float(seat) if isinstance(seat, (int, float)) else None

    if surface == "controlled_api":
        model_id = _require_resolved("model_id", entry.get("model_id"), model_ref)
        return ResolvedModel(
            provider=provider, model_or_selector=model_id, model_id=model_id,
            cost_basis=cost_basis, product=product, product_surface=surface,
            region=region, model_confidence="authoritative", seat_allocation_usd=seat,
        )
    if surface == "product_blackbox":
        selector = _require_resolved("selector_label", entry.get("selector_label"), model_ref)
        # model_id stays None — the backend id is never inferred (SPEC 6.3).
        return ResolvedModel(
            provider=provider, model_or_selector=selector, model_id=None,
            cost_basis=cost_basis, product=product, product_surface=surface,
            region=region, model_confidence="proxy_observed", seat_allocation_usd=seat,
        )
    raise RunnerError(f"{model_ref}.product_surface {surface!r} unknown (controlled_api|product_blackbox)")


# --------------------------------------------------------------------------- #
# Run plan (which legs, which adapter, which policy)
# --------------------------------------------------------------------------- #
@dataclass
class LegPlan:
    leg_id: str
    role: str
    resolved: ResolvedModel


@dataclass
class RunPlan:
    adapter_name: str
    legs: List[LegPlan]
    policy: str  # "static" | "cheap_first" | "workflow"


def build_plan(config_id: str, manifest: Dict[str, Any]) -> RunPlan:
    cfg_dir = os.path.join(REPO_ROOT, "harness", "configurations")
    pol_dir = os.path.join(REPO_ROOT, "harness", "policies")

    if config_id in _POLICY_FILES:  # P0 / P1 run on the controlled harness (Product A).
        pol = _load_yaml(os.path.join(pol_dir, _POLICY_FILES[config_id]))
        product = _PRODUCT_LABELS["PRODUCT_A"]
        if config_id == "P0":
            r = resolve_model(manifest, pol["model_ref"], product)
            return RunPlan("claude_code", [LegPlan("main", "solver", r)], "static")
        econ = resolve_model(manifest, pol["attempt_model_ref"], product)
        strong = resolve_model(manifest, pol["escalate_to_model_ref"], product)
        return RunPlan("claude_code", [
            LegPlan("economical_attempt", "economical", econ),
            LegPlan("strong_attempt", "strong", strong),
        ], "cheap_first")

    cfg = _load_yaml(os.path.join(cfg_dir, f"{config_id}.yaml"))
    if not cfg:
        raise RunnerError(f"no configuration or policy named {config_id!r}")

    if config_id == "C5":  # integrated workflow: conductor + executor, both billed.
        legs_cfg = cfg.get("legs") or {}
        legs: List[LegPlan] = []
        for leg_id in ("conductor", "executor"):
            spec = legs_cfg.get(leg_id) or {}
            product = _PRODUCT_LABELS.get(spec.get("product_ref"), spec.get("product_ref", leg_id))
            legs.append(LegPlan(leg_id, leg_id, resolve_model(manifest, spec["model_ref"], product)))
        return RunPlan(cfg.get("adapter", "hybrid_c5"), legs, "workflow")

    # C1/C2/C3/C4: static single leg.
    product = _PRODUCT_LABELS.get(cfg.get("product_ref"), cfg.get("product_ref", "unknown"))
    r = resolve_model(manifest, cfg["model_ref"], product)
    return RunPlan(cfg.get("adapter", "claude_code"), [LegPlan("main", "solver", r)], "static")


# --------------------------------------------------------------------------- #
# Task
# --------------------------------------------------------------------------- #
@dataclass
class Task:
    task_dir: str
    task_id: str
    task_suite_version: str
    prompt: str
    contamination_tier: Optional[str]
    hidden_test_hash: Optional[str]


def load_task(task_arg: str, manifest: Dict[str, Any]) -> Task:
    task_dir = task_arg if os.path.isabs(task_arg) else os.path.join(REPO_ROOT, task_arg)
    ty_path = os.path.join(task_dir, "task.yaml")
    if not os.path.exists(ty_path):
        raise RunnerError(f"no task.yaml at {ty_path}")
    ty = _load_yaml(ty_path)
    mkey = ty.get("manifest_key")
    mentry = (manifest.get(mkey) or {}) if mkey else {}
    sealed = mentry.get("sealed_hidden_test") or {}
    return Task(
        task_dir=task_dir,
        task_id=ty["task_id"],
        task_suite_version=ty.get("task_suite_version", "unversioned"),
        prompt=ty.get("prompt", ""),
        contamination_tier=ty.get("contamination_tier"),
        hidden_test_hash=sealed.get("sha256"),
    )


# --------------------------------------------------------------------------- #
# Acceptance gate
# --------------------------------------------------------------------------- #
def synthetic_gate(scenario: str, leg_id: str) -> Tuple[bool, str, Dict[str, Any]]:
    """Deterministic dry-run gate. ``escalate`` fails only the economical attempt."""
    if scenario == "reject":
        passed = False
    elif scenario == "escalate":
        passed = "econ" not in leg_id  # economical_attempt fails; strong passes
    else:  # "accept"
        passed = True
    return passed, ("accepted" if passed else "rejected"), \
        {"synthetic_public_gate": "pass" if passed else "fail"}


def real_gate(task_dir: str, run_dir: str) -> Tuple[bool, str, Dict[str, Any]]:
    """Run the Phase 2 deterministic gate against the current subject tree.

    Hidden tests are authoritative (SPEC 2.6): accepted only if the public gate
    passes AND hidden passes; rejected if either fails; ``error`` if hidden tests
    are unavailable (cannot authoritatively accept).
    """
    gate_dir = os.path.join(REPO_ROOT, "harness", "task-tools", "gate")
    pub_report = os.path.join(run_dir, "gate-public.json")
    hid_report = os.path.join(run_dir, "gate-hidden.json")

    env = {**os.environ, "TASK_DIR": task_dir, "GATE_REPORT": pub_report}
    pub_rc = subprocess.run(  # noqa: S603
        ["bash", os.path.join(gate_dir, "check-public.sh")], env=env, check=False,
    ).returncode
    env_h = {**os.environ, "TASK_DIR": task_dir, "HIDDEN_REPORT": hid_report}
    hid_rc = subprocess.run(  # noqa: S603
        ["bash", os.path.join(gate_dir, "check-hidden.sh")], env=env_h, check=False,
    ).returncode

    checks: Dict[str, Any] = {}
    for key, path in (("public", pub_report), ("hidden", hid_report)):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                checks[key] = json.load(fh)

    public_pass = pub_rc == 0
    if hid_rc == 2:
        return False, "error", checks  # hidden unavailable — cannot authoritatively accept
    if hid_rc == 1 or not public_pass:
        return False, "rejected", checks
    return True, "accepted", checks


# --------------------------------------------------------------------------- #
# Cache-protocol contract (methodology/cache-protocol.md rule 4)
# --------------------------------------------------------------------------- #
def assert_cache_contract(events: List[Dict[str, Any]], cache_state: str) -> List[str]:
    """Verify the emitted event log honours the declared cache state.

    Freshness is proven from the immutable log, not asserted by the runner: every
    ``model_call_started`` event carries the ``session_id`` the adapter actually
    used and whether it ``resumed``. For ``cold`` every leg must be a fresh,
    identified session (a new id, ``resumed=False``); for ``warm-series`` every
    leg must resume an identified session. Returns a list of violations (empty =
    contract satisfied).
    """
    starts = [e for e in events if e.get("event_type") == "model_call_started"]
    reasons: List[str] = []
    if not starts:
        return ["cache-contract: no model_call_started event to prove session freshness"]
    for e in starts:
        leg = e.get("leg", "?")
        sid = e.get("session_id")
        resumed = e.get("resumed")
        if not sid:
            reasons.append(f"cache-contract: leg {leg!r} model_call_started has no session_id")
        if cache_state == "cold" and resumed:
            reasons.append(
                f"cache-contract: leg {leg!r} resumed a session under cold cache-state "
                f"(cold requires a fresh session — cache-protocol rule 1)"
            )
        if cache_state == "warm-series" and not resumed:
            reasons.append(
                f"cache-contract: leg {leg!r} did not resume a session under warm-series "
                f"(warm runs continue the cold run's session — cache-protocol rule 2)"
            )
    return reasons


# --------------------------------------------------------------------------- #
# Cumulative-spend kill-switch (CP-SPEND option a — batch cost ceiling)
# --------------------------------------------------------------------------- #
def cumulative_spend_usd(batch_dir: str) -> Tuple[float, int, int]:
    """Sum realized marginal operating USD across completed runs in ``batch_dir``.

    Reads every sibling ``summary.json`` (the event-log-derived cost artifact) and
    sums each leg's numeric ``marginal_operating_usd`` value. This is per-leg — so
    it captures both single-basis runs and mixed-basis workflows (C5), whose
    top-level cost is intentionally ``unavailable``. A leg whose cost is
    ``unavailable`` (e.g. Product B not exposing tokens) is COUNTED, never
    zero-imputed (CLAUDE.md rule 3): the returned total is therefore the
    KNOWN-spend floor, and the unavailable-leg count flags that real spend may be
    higher. Returns ``(total_usd, n_runs, n_unavailable_legs)``.
    """
    total = 0.0
    n_runs = 0
    n_unavailable = 0
    if not os.path.isdir(batch_dir):
        return 0.0, 0, 0
    for name in sorted(os.listdir(batch_dir)):
        summary_path = os.path.join(batch_dir, name, "summary.json")
        if not os.path.isfile(summary_path):
            continue
        try:
            with open(summary_path, encoding="utf-8") as fh:
                summary = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue  # a half-written or corrupt sibling never inflates/masks spend
        n_runs += 1
        for leg in summary.get("legs", []):
            value = (leg.get("marginal_operating_usd") or {}).get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                total += float(value)
            else:
                n_unavailable += 1
    return round(total, 6), n_runs, n_unavailable


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #
def _gate(dry_run: bool, scenario: str, leg_id: str, task_dir: str,
          run_dir: str) -> Tuple[bool, str, Dict[str, Any]]:
    if dry_run:
        return synthetic_gate(scenario, leg_id)
    return real_gate(task_dir, run_dir)


def execute(plan: RunPlan, task: Task, adapter, subject_dir: str, run_dir: str,
            emit, *, dry_run: bool, scenario: str,
            cache_state: str, base_session: str, resume: bool
            ) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    """Run the plan's policy, emitting events. Returns (identity, leg_options_by_id)."""
    identity: Dict[str, Any] = {}
    leg_options: Dict[str, Dict[str, Any]] = {}

    def run_leg(leg: LegPlan) -> None:
        # Cold: each leg is an independent fresh session (distinct id, no resume).
        # Warm-series: the (single) leg resumes the caller-supplied session id so
        # the provider prompt-cache carries over.
        leg_session = base_session if resume else f"{base_session}-{leg.leg_id}"
        spec = AttemptSpec(leg.leg_id, leg.role, leg.resolved, task.prompt,
                           cache_state=cache_state, session_id=leg_session, resume=resume)
        outcome = adapter.run_attempt(spec, subject_dir, emit)
        if not identity:  # top-level identity from the primary leg; legs[] hold per-leg detail
            identity.update(outcome.identity)
        opts = dict(outcome.leg_options)
        if leg.resolved.seat_allocation_usd is not None:
            opts.setdefault("seat_allocation_usd", leg.resolved.seat_allocation_usd)
        leg_options[leg.leg_id] = opts

    itr: Optional[str] = None
    cr: Optional[str] = None

    if plan.policy == "cheap_first":
        econ, strong = plan.legs
        itr = "economical"
        run_leg(econ)
        passed, result, checks = _gate(dry_run, scenario, econ.leg_id, task.task_dir, run_dir)
        if passed:
            cr = "economical"
        else:
            # Escalate: record the failed attempt explicitly (its cost lives on the
            # economical_attempt leg) so P1 cells record failed-attempt costs every run.
            emit("retry", leg=econ.leg_id, reason="gate_fail")
            emit("escalation", from_route="economical", to_route="strong",
                 reason="gate_fail", failed_leg=econ.leg_id)
            run_leg(strong)
            passed, result, checks = _gate(dry_run, scenario, strong.leg_id, task.task_dir, run_dir)
            cr = "strong"
    else:  # static | workflow
        for leg in plan.legs:
            run_leg(leg)
        passed, result, checks = _gate(dry_run, scenario, "main", task.task_dir, run_dir)

    emit("acceptance", result=result, gate_checks=checks,
         intention_to_route=itr, completed_route=cr)
    return identity, leg_options


# --------------------------------------------------------------------------- #
# Cost + summary assembly
# --------------------------------------------------------------------------- #
def _leg_billed_tokens(usage: Dict[str, Any]) -> Optional[int]:
    """Sum a leg's available billed token classes; None if none are available."""
    total, any_avail = 0, False
    for cls in ("input_tokens", "cache_creation_tokens", "cache_read_tokens", "output_tokens"):
        field = usage.get(cls) or {}
        if field.get("confidence") != "unavailable" and field.get("value") is not None:
            total += field["value"]
            any_avail = True
    return total if any_avail else None


def _frontier_token_share(legs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Conductor share of tokens across legs — a C5 diagnostic only (never a claim)."""
    per_leg = {leg["leg_id"]: _leg_billed_tokens(leg.get("usage") or {}) for leg in legs}
    if any(v is None for v in per_leg.values()) or "conductor" not in per_leg:
        return unavailable("token counts unavailable on one or more legs")
    total = sum(per_leg.values())
    if total == 0:
        return unavailable("zero total tokens")
    return tiered(round(per_leg["conductor"] / total, 6), "derived")


def build_economics(legs: List[Dict[str, Any]], prices: Dict[str, Any],
                    leg_options: Dict[str, Dict[str, Any]], pricing_snapshot: str
                    ) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    """Cost every leg under its own basis and aggregate (SPEC 2.7 two views).

    A single-basis run reports the aggregate under that basis. A mixed-basis
    workflow (e.g. C5 conductor subscription + executor provider-reported) does
    NOT get a single-basis aggregate placed beside incompatible bases — the top
    level is marked ``cost_unavailable`` and per-leg costs (precise, available)
    are the source of truth.
    """
    agg = cost_for_legs(legs, prices, leg_options=leg_options)
    per_leg_views = {v["leg_id"]: v for v in agg["legs"]}

    bases = {leg["cost_basis"] for leg in legs}
    uniform = next(iter(bases)) if len(bases) == 1 else None

    econ: Dict[str, Any] = {"pricing_snapshot": os.path.basename(pricing_snapshot)}
    if uniform:
        econ["cost_basis"] = uniform
        econ["marginal_operating_usd"] = agg["marginal_operating_usd"]
        econ["fully_allocated_usd"] = agg["fully_allocated_usd"]
        econ["total_cost_usd"] = agg["fully_allocated_usd"]
    else:
        econ["cost_basis"] = "cost_unavailable"
        econ["marginal_operating_usd"] = unavailable("mixed cost bases across legs; see per-leg")
        econ["fully_allocated_usd"] = unavailable("mixed cost bases across legs; see per-leg")
    return econ, per_leg_views


def assemble_and_validate(events: List[Dict[str, Any]], *, run_id: str, task: Task,
                          config_id: str, manifest_ref: str, identity: Dict[str, Any],
                          plan: RunPlan, prices: Dict[str, Any],
                          leg_options: Dict[str, Dict[str, Any]], pricing_snapshot: str,
                          run_dir: str) -> Tuple[bool, List[str]]:
    """Two-pass derive (usage -> cost -> final summary), write, and audit-validate."""
    ident = dict(identity)
    if task.contamination_tier:
        ident["contamination_tier"] = task.contamination_tier

    common = dict(
        run_id=run_id, task_id=task.task_id, task_suite_version=task.task_suite_version,
        configuration_id=config_id, manifest_ref=manifest_ref, identity=ident,
        hidden_test_hash=task.hidden_test_hash,
    )
    # Pass 1: derive event-sourced legs/usage (economics defaulted) to cost from.
    base = derive_summary(events, **common)
    econ, per_leg_views = build_economics(base["legs"], prices, leg_options, pricing_snapshot)

    # Pass 2: final summary with computed economics (deterministic; event-sourced
    # fields are identical to pass 1, so validate() re-derivation still corroborates).
    summary = derive_summary(events, economics=econ, **common)

    # Enrich per-leg cost views + C5 frontier diagnostic (not event-corroborated fields).
    for leg in summary["legs"]:
        view = per_leg_views.get(leg["leg_id"])
        if view:
            leg["marginal_operating_usd"] = view["marginal_operating_usd"]
            leg["fully_allocated_usd"] = view["fully_allocated_usd"]
    if plan.policy == "workflow":
        summary["frontier_token_share"] = _frontier_token_share(summary["legs"])

    with open(os.path.join(run_dir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
    return validate(run_dir)


# --------------------------------------------------------------------------- #
# Subject repo setup (live runs only)
# --------------------------------------------------------------------------- #
def _setup_subject(task_dir: str, run_dir: str) -> str:
    tt = os.path.join(REPO_ROOT, "harness", "task-tools")
    env = {**os.environ, "TASK_DIR": task_dir}
    subprocess.run(["bash", os.path.join(tt, "setup.sh")], env=env, check=True)  # noqa: S603
    reset = subprocess.run(  # noqa: S603
        ["bash", os.path.join(tt, "reset.sh")], env=env, check=True,
        capture_output=True, text=True,
    )
    with open(os.path.join(run_dir, "reset.txt"), "w", encoding="utf-8") as fh:
        fh.write(reset.stdout)  # records the reset tree hash (determinism check input)
    return os.path.join(task_dir, ".work", "repo")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _make_run_id(task: Task, config_id: str, rep: int) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{task.task_id}__{config_id}__rep{rep}__{stamp}"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Controlled harness runner (SPEC 2.1–2.3, 2.7)")
    ap.add_argument("--task", required=True, help="task dir (e.g. tasks/pilot-realworld)")
    ap.add_argument("--config", required=True,
                    help="configuration or policy id: C1|C2|C3|C4|C5|P0|P1")
    ap.add_argument("--manifest", default=os.path.join(REPO_ROOT, "manifest", "delivery-manifest.yaml"))
    ap.add_argument("--phase", default="feasibility", help="results/<phase>/ for live runs")
    ap.add_argument("--rep", type=int, default=1)
    ap.add_argument("--cache-state", required=True, choices=("cold", "warm-series"),
                    help="cache-protocol contract (methodology/cache-protocol.md rule 4): "
                         "cold = fresh session, no carried cache; warm-series = resume a "
                         "prior session so provider prompt-cache carries over")
    ap.add_argument("--session-id", default=None,
                    help="explicit session id (required to --resume a warm-series run)")
    ap.add_argument("--resume", action="store_true",
                    help="continue --session-id (warm-series runs 2..n)")
    ap.add_argument("--spend-cap-usd", type=float, default=60.0,
                    help="cumulative batch spend ceiling (CP-SPEND option a). Before "
                         "starting a run, the summed realized marginal cost of completed "
                         "sibling runs under the same output root is checked; at/over the "
                         "cap the runner halts (exit 3) without starting. Resumable: "
                         "re-invoke (optionally with a raised cap) to continue.")
    ap.add_argument("--dry-run", action="store_true",
                    help="synthetic adapters + gate; no spend/clone/network")
    ap.add_argument("--out-root", default=None,
                    help="output root for --dry-run (default: a temp dir; never results/)")
    ap.add_argument("--stub-scenario", choices=("accept", "escalate", "reject"), default="accept",
                    help="dry-run gate outcome to simulate")
    args = ap.parse_args(argv)

    try:
        # Cache-protocol contract (methodology/cache-protocol.md rule 4).
        if args.resume and not args.session_id:
            raise RunnerError("--resume requires --session-id (the session to continue)")
        if args.cache_state == "cold" and args.resume:
            raise RunnerError(
                "cold cache-state cannot --resume a session (cold = fresh session, "
                "cache-protocol rule 1); drop --resume or use --cache-state warm-series"
            )
        if args.cache_state == "warm-series" and not args.resume:
            raise RunnerError(
                "warm-series continues the cold run's session; pass --session-id <id> "
                "--resume (cache-protocol rule 2). Run 1 of the series uses --cache-state cold"
            )
        base_session = args.session_id or f"lab-{uuid.uuid4()}"

        manifest = _load_yaml(args.manifest)
        if not args.dry_run and os.environ.get("LAB_ALLOW_SPEND") != "1":
            raise RunnerError(
                "a live run bills a real account and requires CP-SPEND approval; set "
                "LAB_ALLOW_SPEND=1 for an approved run, or pass --dry-run"
            )
        task = load_task(args.task, manifest)
        plan = build_plan(args.config, manifest)

        pricing_snapshot = manifest.get("pricing_snapshot") or ""
        prices: Dict[str, Any] = {}
        if not _is_placeholder(pricing_snapshot):
            price_path = pricing_snapshot if os.path.isabs(pricing_snapshot) \
                else os.path.join(REPO_ROOT, pricing_snapshot)
            if os.path.exists(price_path):
                prices = load_prices(price_path)
        if not prices and any(leg.resolved.cost_basis in ("marginal_api_cost",
                              "allocated_subscription_cost") for leg in plan.legs):
            raise RunnerError(
                f"pricing snapshot {pricing_snapshot!r} missing/unresolved but a leg "
                f"needs token-based pricing; fill pricing at CP-SPEND or use --dry-run"
            )

        run_id = _make_run_id(task, args.config, args.rep)
        if args.dry_run:
            batch_dir = args.out_root or tempfile.mkdtemp(prefix="lab-dryrun-")
        else:
            batch_dir = os.path.join(REPO_ROOT, "results", args.phase)
        run_dir = os.path.join(batch_dir, run_id)

        # Cumulative-spend kill-switch (CP-SPEND option a). Enforced from the
        # realized, event-log-derived cost of runs already completed in this batch
        # directory — checked BEFORE this run starts, so once known spend reaches
        # the cap no further run begins. A stopped batch resumes by re-invoking
        # (optionally with a raised --spend-cap-usd); prior results are untouched.
        spent, n_prior, n_unavail = cumulative_spend_usd(batch_dir)
        if spent >= args.spend_cap_usd:
            floor_note = (f" (plus {n_unavail} prior leg(s) with unavailable cost — "
                          f"actual spend may exceed this known floor)") if n_unavail else ""
            print(
                f"runner: SPEND CAP REACHED — ${spent:.2f} known spend across {n_prior} "
                f"completed run(s){floor_note} >= ${args.spend_cap_usd:.2f} cap; halting "
                f"before this run starts. Raise --spend-cap-usd to resume the batch.",
                file=sys.stderr,
            )
            return 3

        os.makedirs(run_dir, exist_ok=True)

        if args.dry_run:
            adapter: Any = StubAdapter()
            subject_dir = os.path.join(run_dir, "SYNTHETIC-subject")  # unused by stub
        else:
            adapter = REAL_ADAPTERS[plan.adapter_name]()
            subject_dir = _setup_subject(task.task_dir, run_dir)

        log = EventLog(os.path.join(run_dir, "events.jsonl"))

        def emit(event_type: str, **payload: Any) -> None:
            log.append(event_type, ts=_now_iso(), **payload)

        identity, leg_options = execute(
            plan, task, adapter, subject_dir, run_dir, emit,
            dry_run=args.dry_run, scenario=args.stub_scenario,
            cache_state=args.cache_state, base_session=base_session, resume=args.resume,
        )
        # Cache state is a runner-controlled experimental variable — stamped
        # authoritatively here (overriding any adapter default) and proven against
        # the event log below.
        identity["cache_state"] = tiered(args.cache_state, "authoritative")
        identity["session_state"] = tiered(
            "resumed" if args.resume else "fresh", "authoritative")

        events = log.read()
        cache_reasons = assert_cache_contract(events, args.cache_state)

        ok, reasons = assemble_and_validate(
            events, run_id=run_id, task=task, config_id=args.config,
            manifest_ref=os.path.relpath(args.manifest, REPO_ROOT), identity=identity,
            plan=plan, prices=prices, leg_options=leg_options,
            pricing_snapshot=pricing_snapshot or "unavailable", run_dir=run_dir,
        )
        ok = ok and not cache_reasons
        reasons = list(reasons) + cache_reasons
    except RunnerError as exc:
        print(f"runner: {exc}", file=sys.stderr)
        return 2

    print(f"run_dir: {run_dir}")
    if ok:
        print("validate: PASS (audit-grade)")
        return 0
    print("validate: FAIL", file=sys.stderr)
    for r in reasons:
        print(f"  - {r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
