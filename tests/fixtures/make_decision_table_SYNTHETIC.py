#!/usr/bin/env python3
"""Generate ``tests/fixtures/decision-table-SYNTHETIC.json`` — the report page's fixture.

The report page (`docs/assets/decision-report.js`) renders entirely from a
decision-table JSON. It is developed and tested against THIS file, which contains
**no measurements of anything**: every number below is fabricated by the arithmetic in
this script, and every run summary it builds carries a ``SYNTHETIC`` marker.

Why generate it rather than hand-write it: the fixture is produced by running the real
``harness.telemetry.summarize.build()`` over fabricated run directories in a tmpdir. So
the fixture cannot drift away from the emitter's actual output shape — if the summarizer
changes, ``tests/test_report_page.py`` regenerates and fails on the diff. A hand-written
fixture would let the page and the pipeline disagree silently, which is the exact bug
class the data contract exists to prevent.

What it deliberately exercises (the honest-gap paths, not a happy path):

  * a Product-B leg whose cost the CLI does not expose -> ``unavailable``, never 0
  * a cell that accepted nothing -> ECST ``undefined``, never a finite number
  * a registered arm with no runs -> coverage ``missing``, not a silent absence
  * a two-leg delegation bill with one leg priced and one unavailable
  * an escalation trace where the economical leg fails the gate and a strong leg follows
  * an effort-panel pair outside the registration's declared scope -> not graded

Nothing here may be copied into ``results/``: fabricated shapes live under
``tests/fixtures/`` only (CLAUDE.md rule 1).

Run::

    .venv/bin/python tests/fixtures/make_decision_table_SYNTHETIC.py
    .venv/bin/python tests/fixtures/make_decision_table_SYNTHETIC.py --check
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from harness.telemetry import summarize  # noqa: E402

OUT = os.path.join(HERE, "decision-table-SYNTHETIC.json")

SYNTHETIC_MARK = "SYNTHETIC — fabricated shapes for the report page. NOT a measurement."

#: Loaded rate for the HEAC term. A declared org input in the real manifest; fabricated
#: here so the fixture does not depend on the delivery manifest's value.
SYNTHETIC_RATE = 1.60

#: Deterministic per-repetition multipliers. Three reps with real spread, so the
#: min–max whiskers on the page have something to draw and the median is not the mean.
REP_FACTORS = [0.82, 1.0, 1.37]

PRODUCT_A = ("Product A", "STRONG_MODEL_A", "controlled_api", "marginal_api_cost")

#: arm -> (product, selector label, per-run base cost USD, usage tier, cost basis)
ARM_PROFILE: Dict[str, Dict[str, Any]] = {
    "P0": {"product": "Product A", "selector": "STRONG_MODEL_A",
           "base_usd": 0.3100, "tier": "authoritative", "basis": "marginal_api_cost"},
    "C2": {"product": "Product A", "selector": "ECONOMICAL_MODEL_A",
           "base_usd": 0.0620, "tier": "authoritative", "basis": "marginal_api_cost"},
    "C3": {"product": "Product B", "selector": "ECONOMICAL_MODEL_B_HIGH",
           "base_usd": 0.0930, "tier": "proxy_observed",
           "basis": "cache_blind_upper_bound"},
    "C3-med": {"product": "Product B", "selector": "ECONOMICAL_MODEL_B_MEDIUM",
               "base_usd": 0.0560, "tier": "proxy_observed",
               "basis": "cache_blind_upper_bound"},
    "C3-prev": {"product": "Product B", "selector": "ECONOMICAL_MODEL_B_PREV",
                "base_usd": 0.0810, "tier": "proxy_observed",
                "basis": "cache_blind_upper_bound"},
    "C5": {"product": "Product A -> Product B", "selector": "STRONG_MODEL_A",
           "base_usd": 0.1900, "tier": "authoritative", "basis": "marginal_api_cost"},
    "P1": {"product": "Product A", "selector": "ECONOMICAL_MODEL_A",
           "base_usd": 0.0700, "tier": "authoritative", "basis": "marginal_api_cost"},
    "P2": {"product": "Product A", "selector": "STRONG_MODEL_A",
           "base_usd": 0.2400, "tier": "authoritative", "basis": "marginal_api_cost"},
}

#: Per-task cost multiplier and the shape of the fabricated outcome. ``c3_med_factor``
#: sets what the effort panel will grade; ``notes`` says why each shape was chosen.
TASK_PROFILE: Dict[str, Dict[str, Any]] = {
    "pilot-realworld-draft-articles": {
        "scale": 1.00, "c3_med_factor": 0.60,
        "note": "in H-effort scope; ~40% reduction lands inside the registered band"},
    "w1-realworld-mapper-tests": {
        "scale": 1.45, "c3_med_factor": 0.82,
        "note": "in scope; ~18% reduction lands below the registered band"},
    "w1b-zarr-block-mask-properties": {
        "scale": 1.20, "c3_med_factor": 0.55, "c3_med_accept": 2,
        "note": "in scope; cheaper but fails a gate the other arm passed -> parity refuted"},
    "w3-sqlfluff-segment-method-migration": {
        "scale": 2.10, "c3_med_factor": 0.42,
        "note": "in scope; ~58% reduction lands above the registered band"},
    "w4-realworld-missing-user-id": {
        "scale": 1.80, "c3_med_factor": 0.70,
        "note": "complex_bugfix — outside the H-effort registration's scope"},
    "w4b-zarr-consolidated-order": {
        "scale": 1.65, "c3_med_factor": 0.66, "skip_arms": ["C3-prev"],
        "note": "complex_bugfix, outside scope; C3-prev registered but not run"},
    "w6-hono-router-review": {
        "scale": 1.30, "c3_med_factor": None,
        "note": "code_review — outside scope; C3-med cost unavailable (collector gap)"},
}

#: Tasks where the economical solo arm fails the gate on every run. The migration task
#: is the registered escalation probe: its C2 arm must fail for P1 to have anything to
#: escalate from, and that pairing is what the W3 registration predicted.
ECONOMICAL_FAILS = {"w3-sqlfluff-segment-method-migration"}

#: Arms whose executor-leg cost the product does not expose at the CLI surface.
EXECUTOR_UNPRICED_ARMS = {"C5"}


def _slot(value: Any, confidence: str, **extra: Any) -> Dict[str, Any]:
    return {"value": value, "confidence": confidence, **extra}


def _unavailable(reason: str) -> Dict[str, Any]:
    return {"value": None, "confidence": "unavailable", "reason": reason}


def _usage(scale: float, tier: str, product: str) -> Dict[str, Any]:
    """Token classes for one leg. Product B's collector reports totals but cannot
    separate cached input, so cache classes stay unavailable rather than 0."""
    out = int(900 * scale)
    fresh = int(4200 * scale)
    usage = {
        "input_tokens": _slot(fresh, tier),
        "output_tokens": _slot(out, tier),
        "reasoning_tokens": _unavailable("SYNTHETIC: not exposed by this configuration"),
        "tool_result_tokens": _unavailable("SYNTHETIC: not exposed by this configuration"),
    }
    if product.startswith("Product A"):
        usage["cache_creation_tokens"] = _slot(int(38000 * scale), tier)
        usage["cache_read_tokens"] = _slot(int(96000 * scale), tier)
    else:
        reason = ("SYNTHETIC: the billing-plane metric does not separate cached input "
                  "tokens, so cache classes cannot be reconstructed")
        usage["cache_creation_tokens"] = _unavailable(reason)
        usage["cache_read_tokens"] = _unavailable(reason)
    return usage


def _dark_usage(reason: str) -> Dict[str, Any]:
    """Usage for a leg the harness cannot see at all — every class unavailable."""
    return {key: _unavailable(reason) for key in
            ("input_tokens", "cache_creation_tokens", "cache_read_tokens",
             "output_tokens", "reasoning_tokens", "tool_result_tokens")}


def _leg(leg_id: str, role: str, product: str, selector: str, basis: str,
         cost: Optional[float], scale: float, tier: str) -> Dict[str, Any]:
    # A leg with no cost here is a leg the harness cannot see: no usage either. It
    # must not borrow the other leg's numbers, and it must not read as free.
    dark = "SYNTHETIC: the product exposes no machine-readable usage for this leg " \
           "at the CLI surface, and no provider-side collector window covers it"
    priced = (_slot(round(cost, 6), "derived", basis=basis) if cost is not None
              else _unavailable(dark))
    return {
        "leg_id": leg_id,
        "role": role,
        "cost_basis": basis,
        "model_or_selector": _slot(selector, "authoritative"),
        "provider": _slot("SYNTHETIC_PROVIDER", "authoritative"),
        "marginal_operating_usd": priced,
        "fully_allocated_usd": (_slot(round(cost * 1.18, 6), "derived", basis=basis)
                                if cost is not None else
                                _unavailable("SYNTHETIC: no marginal cost to allocate "
                                             "from")),
        "usage": (_usage(scale, tier, product) if cost is not None
                  else _dark_usage(dark)),
    }


def _sum_usage(legs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Roll per-leg usage up to the run. A class no leg exposes stays unavailable."""
    rolled: Dict[str, Any] = {}
    for key in ("input_tokens", "cache_creation_tokens", "cache_read_tokens",
                "output_tokens", "reasoning_tokens", "tool_result_tokens"):
        total, tiers, reason = 0, [], None
        for leg in legs:
            slot = leg["usage"][key]
            if slot["value"] is None:
                reason = reason or slot.get("reason")
            else:
                total += slot["value"]
                tiers.append(slot["confidence"])
        rolled[key] = (_slot(total, summarize._weakest(tiers)) if tiers
                       else _unavailable(reason or "SYNTHETIC: not exposed"))
    for key in ("search_ops", "search_charges_usd", "code_exec_usage",
                "code_exec_charges_usd"):
        rolled[key] = _unavailable("SYNTHETIC: not exposed by this configuration")
    return rolled


def _gate(accepted: bool, failed_ids: List[str]) -> Dict[str, Any]:
    checks = [{"id": "P3-typecheck", "status": "pass", "detail": "SYNTHETIC"},
              {"id": "P6-diff-scope", "status": "pass", "detail": "SYNTHETIC"},
              {"id": "P1-public-test", "status": "pass", "detail": "SYNTHETIC"}]
    for check in checks:
        if check["id"] in failed_ids:
            check["status"] = "fail"
    return {
        "hidden": {"gate": "hidden", "version": "SYNTHETIC-sealed-v0",
                   "hash": "sha256:SYNTHETIC", "status": "pass" if accepted else "fail"},
        "public": {"gate": "public", "checks": checks},
    }


def _legs_for(arm: str, task_id: str, cost: float, scale: float,
              cheap_leg_failed: bool) -> List[Dict[str, Any]]:
    """Per-leg bill for one run. Delegation and escalation arms bill twice."""
    profile = ARM_PROFILE[arm]
    basis, tier = profile["basis"], profile["tier"]
    if arm == "C5":
        # conductor priced from Product A metadata; executor leg unavailable at the CLI
        return [
            _leg("conductor", "conductor", "Product A", "STRONG_MODEL_A", basis,
                 cost * 0.62, scale * 0.55, "authoritative"),
            _leg("executor", "executor", "Product B", "ECONOMICAL_MODEL_B_HIGH",
                 "cost_unavailable", None, scale * 0.75, "unavailable"),
        ]
    if arm == "P2":
        return [
            _leg("conductor", "conductor", "Product A", "STRONG_MODEL_A", basis,
                 cost * 0.40, scale * 0.45, tier),
            _leg("executor", "executor", "Product A", "ECONOMICAL_MODEL_A", basis,
                 cost * 0.60, scale * 0.80, tier),
        ]
    if arm == "P1":
        legs = [_leg("attempt-economical", "solver", "Product A", "ECONOMICAL_MODEL_A",
                     basis, cost * 0.28, scale * 0.60, tier)]
        if cheap_leg_failed:
            legs.append(_leg("escalation-strong", "solver-escalated", "Product A",
                             "STRONG_MODEL_A", basis, cost * 3.90, scale * 1.10, tier))
        return legs
    return [_leg("main", "solver", profile["product"], profile["selector"], basis,
                 cost, scale, tier)]


def _run_summary(task_id: str, task_class: str, arm: str, rep: int,
                 accepted: bool, cost: Optional[float], scale: float,
                 escalated: bool, failed_ids: List[str],
                 human_effort: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    profile = ARM_PROFILE[arm]
    run_id = f"SYNTHETIC__{task_id}__{arm}__rep{rep}__20260101T000000"
    legs = _legs_for(arm, task_id, cost if cost is not None else 0.0, scale,
                     escalated)
    if cost is None:
        # Tokens are known for this cell but no price can be reconstructed for the
        # selector, so cost is unavailable while usage stays reported. The distinct
        # shape from a dark leg: known work, unknown bill.
        for leg in legs:
            leg["marginal_operating_usd"] = _unavailable(
                "SYNTHETIC: the pricing snapshot carries no entry for this selector, "
                "so tokens are known but cost cannot be reconstructed")
            leg["fully_allocated_usd"] = _unavailable(
                "SYNTHETIC: no marginal cost to allocate from")
            leg["cost_basis"] = "cost_unavailable"
    total, any_unavailable = 0.0, False
    for leg in legs:
        value = leg["marginal_operating_usd"]["value"]
        if value is None:
            any_unavailable = True
        else:
            total += value
    summary: Dict[str, Any] = {
        "SYNTHETIC": SYNTHETIC_MARK,
        "run_id": run_id,
        "task_id": task_id,
        "task_class": task_class,
        "task_suite_version": "SYNTHETIC-suite-v0",
        "hidden_test_hash": "sha256:SYNTHETIC",
        "manifest_ref": "tests/fixtures/manifest-SYNTHETIC.yaml",
        "configuration_id": arm,
        "acceptance": {
            "result": "accepted" if accepted else "rejected",
            "intention_to_route": ("economical" if arm == "P1" else None),
            "completed_route": (("strong" if escalated else "economical")
                                if arm == "P1" else None),
            "gate_checks": _gate(accepted, failed_ids),
        },
        "behavior": {
            "turns": _slot(4, "derived"),
            "retries": _slot(0, "derived"),
            "escalations": _slot(1 if escalated else 0, "derived"),
            "subagent_calls": _slot(1 if arm in ("C5", "P2") else 0, "derived"),
            "verifier_calls": _slot(1, "derived"),
            "failures_by_category": _slot({"gate_fail": 1} if not accepted else {},
                                          "derived"),
            "files_modified": _unavailable("SYNTHETIC: not tracked in the event log"),
            "file_reads": _unavailable("SYNTHETIC: no file_read events"),
            "file_read_bytes": _unavailable("SYNTHETIC: byte counts not measured"),
            "tool_calls_by_type": _unavailable("SYNTHETIC: no tool_invoked events"),
        },
        "identity": {
            "product": _slot(profile["product"], "authoritative"),
            "provider": _slot("SYNTHETIC_PROVIDER", "authoritative"),
            "model_or_selector": _slot(profile["selector"], "authoritative"),
            "product_version": _slot("SYNTHETIC-0.0.0", "authoritative"),
            "auth_billing_path": _slot("controlled_api", "authoritative"),
            "region": _slot("SYNTHETIC-region", "authoritative"),
            "reasoning_config": _slot(
                "medium" if arm == "C3-med" else "high" if arm == "C3" else "default",
                "authoritative"),
            "permission_profile": _slot("container; endpoint-allowlist egress",
                                        "authoritative"),
            "network_policy": _slot("endpoint-allowlist", "authoritative"),
            "session_state": _slot("fresh", "authoritative"),
            "cache_state": _slot("cold", "authoritative"),
            "contamination_tier": "SYNTHETIC",
        },
        "economics": {
            "cost_basis": legs[0]["cost_basis"],
            "pricing_snapshot": "prices-SYNTHETIC.json",
            "marginal_operating_usd": (_unavailable("SYNTHETIC: no priced leg")
                                       if not any(l["marginal_operating_usd"]["value"]
                                                  is not None for l in legs)
                                       else _slot(round(total, 6), "derived")),
            "fully_allocated_usd": (_unavailable("SYNTHETIC: no priced leg")
                                    if not any(l["fully_allocated_usd"]["value"]
                                               is not None for l in legs)
                                    else _slot(round(total * 1.18, 6), "derived")),
            "provider_cost_usd": _unavailable("SYNTHETIC: not supplied to deriver"),
            "machine_cost_usd": _unavailable("SYNTHETIC: not supplied to deriver"),
            "subscription_allocation_basis": _unavailable(
                "SYNTHETIC: not supplied to deriver"),
            "attempt_cost_is_floor": any_unavailable,
        },
        "usage": _sum_usage(legs),
        "legs": legs,
    }
    if human_effort:
        summary["human_effort"] = human_effort
    return summary


def _human_effort(verdict: str) -> Dict[str, Any]:
    return {
        "active_minutes": _slot(0.0, "authoritative"),
        "review_minutes": _slot(11.0, "authoritative"),
        "correction_minutes": _slot(4.0 if verdict == "would_not_merge" else 0.0,
                                    "authoritative"),
        "blocked_minutes": _slot(6.0, "authoritative"),
        "reviewer_verdict": _slot(verdict, "authoritative"),
        "reviewer": "SYNTHETIC-reviewer-1",
    }


def _write_run(batch_dir: str, summary: Dict[str, Any]) -> None:
    run_dir = os.path.join(batch_dir, summary["run_id"])
    os.makedirs(run_dir)
    with open(os.path.join(run_dir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1, sort_keys=True)
    seconds = 40 + (len(summary["legs"]) * 55)
    with open(os.path.join(run_dir, "events.jsonl"), "w", encoding="utf-8") as fh:
        for event, stamp in (("run_started", "2026-01-01T00:00:00+00:00"),
                             ("acceptance",
                              f"2026-01-01T00:{seconds // 60:02d}:{seconds % 60:02d}"
                              "+00:00")):
            fh.write(json.dumps({"event": event, "ts": stamp,
                                 "SYNTHETIC": True}) + "\n")


def _populate(batch_dir: str, registry: Dict[str, Dict[str, Any]]) -> None:
    for task_id, entry in sorted(registry.items()):
        profile = TASK_PROFILE.get(task_id)
        if profile is None:
            continue
        skip = set(profile.get("skip_arms") or [])
        for arm in entry["registered_arms"]:
            if arm in skip:
                continue
            for rep, factor in enumerate(REP_FACTORS, start=1):
                scale = profile["scale"] * factor
                cost: Optional[float] = ARM_PROFILE[arm]["base_usd"] * scale

                accepted = True
                failed_ids: List[str] = []
                escalated = False
                if arm in ("C2", "P1") and task_id in ECONOMICAL_FAILS:
                    # the economical tier misses the parity requirement on the probe
                    if arm == "C2":
                        accepted = False
                        failed_ids = ["P1-public-test"]
                    else:
                        escalated = True  # P1 retries on the strong tier and clears
                if arm == "C3-med":
                    factor_med = profile.get("c3_med_factor")
                    if factor_med is None:
                        cost = None  # collector window gap -> cost unavailable
                    else:
                        cost = (ARM_PROFILE["C3"]["base_usd"] * scale * factor_med)
                    if rep > profile.get("c3_med_accept", len(REP_FACTORS)):
                        accepted = False
                        failed_ids = ["P1-public-test"]

                human = None
                if rep == 1 and arm in ("P0", "C2") and \
                        entry["task_class"] == "test_generation":
                    human = _human_effort("would_not_merge" if arm == "C2"
                                          else "would_merge")
                _write_run(batch_dir, _run_summary(
                    task_id, entry["task_class"], arm, rep, accepted, cost, scale,
                    escalated, failed_ids, human))


def generate() -> Dict[str, Any]:
    """Build the table by running the real summarizer over fabricated run dirs."""
    registry = summarize.load_task_registry()
    with tempfile.TemporaryDirectory() as tmp:
        batch_dir = os.path.join(tmp, "screening-batch1")
        os.makedirs(batch_dir)
        _populate(batch_dir, registry)
        manifest = os.path.join(tmp, "manifest-SYNTHETIC.yaml")
        with open(manifest, "w", encoding="utf-8") as fh:
            fh.write("# SYNTHETIC manifest — fabricated declared inputs, not a "
                     "measurement.\nloaded_rate_per_minute:\n"
                     f"  value: {SYNTHETIC_RATE}\n  currency: USD\n"
                     "  basis: \"SYNTHETIC declared input\"\n")
        table = summarize.build(batch_dir, manifest, status="PENDING")

    # Nothing in the emitted table may point at a real dataset or manifest: this is a
    # fixture, and a reader who opens it must not be able to mistake it for a run.
    table["SYNTHETIC"] = SYNTHETIC_MARK
    table["synthetic"] = True
    table["synthetic_notice"] = (
        "SYNTHETIC FIXTURE — every figure on this page is fabricated by "
        "tests/fixtures/make_decision_table_SYNTHETIC.py to exercise the renderer. "
        "No run, token count, cost or verdict here is a measurement of anything.")
    table["source_dataset"] = "SYNTHETIC (no dataset — generated fixture)"
    table["manifest_ref"] = "SYNTHETIC (no manifest — generated fixture)"
    table["generator"] = "tests/fixtures/make_decision_table_SYNTHETIC.py"
    return table


def serialize(table: Dict[str, Any]) -> str:
    return json.dumps(table, indent=2, sort_keys=True) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if the committed fixture is stale")
    args = ap.parse_args(argv)
    payload = serialize(generate())
    if args.check:
        with open(OUT, encoding="utf-8") as fh:
            current = fh.read()
        if current != payload:
            print(f"STALE: {OUT} differs from a fresh generation — re-run this script",
                  file=sys.stderr)
            return 1
        print(f"ok {OUT} is current", file=sys.stderr)
        return 0
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(payload)
    print(f"wrote {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
