"""Feasibility metric computability (SPEC §metrics; methodology/metrics.md).

Computes the study metrics END-TO-END from run summaries to prove the pipeline
works (feasibility criterion 5) — NOT to compare products. Every output here is
NON-COMPARATIVE, internal-only, and inherits the source runs' confidence tiers:
a metric derived from any ``unavailable`` cost is itself ``unavailable`` (never
zero-filled), and ECST over a cell with zero accepted tasks is ``undefined``
(never a fabricated finite number).

Metrics (both cost views: marginal_operating and fully_allocated):
  * ECST  = Σ(cost of ALL attempts, incl. failed + verification) / count(accepted)
  * QA-ECST = ECST grouped by task class
  * HEAC  = ECST + (active+review+correction minutes × loaded rate); the human
            term is ``unavailable`` until the human-effort subset is recorded.
Dispersion (median/IQR/min–max of per-run marginal cost and output tokens) feeds
the rep-count decision.
"""

from __future__ import annotations

import glob
import json
import os
import statistics as st
from typing import Any, Dict, List, Optional, Tuple

UNAVAILABLE = "unavailable"
UNDEFINED = "undefined"


def _leg_cost(leg: Dict[str, Any], view: str) -> Optional[float]:
    key = "marginal_operating_usd" if view == "marginal" else "fully_allocated_usd"
    v = (leg.get(key) or {}).get("value")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def run_total(summary: Dict[str, Any], view: str) -> Tuple[Optional[float], bool]:
    """(sum of per-leg cost, any_unavailable) for one run under a cost view.

    Sums numeric per-leg costs (all attempts, incl. failed escalation legs) and
    flags whether any leg's cost was unavailable — so the caller never mistakes a
    known-floor total for a complete one (CLAUDE.md rule 3).
    """
    total = 0.0
    any_unavail = False
    seen = False
    for leg in summary.get("legs", []):
        c = _leg_cost(leg, view)
        if c is None:
            any_unavail = True
        else:
            total += c
            seen = True
    return (total if seen else None), any_unavail


def _accepted(summary: Dict[str, Any]) -> bool:
    return summary.get("acceptance", {}).get("result") == "accepted"


def load_cells(feasibility_dir: str) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    """Group run summaries by (task_id, configuration_id)."""
    cells: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for path in sorted(glob.glob(os.path.join(feasibility_dir, "*", "summary.json"))):
        summary = json.load(open(path, encoding="utf-8"))
        key = (summary.get("task_id", "?"), summary.get("configuration_id", "?"))
        cells.setdefault(key, []).append(summary)
    return cells


def ecst(runs: List[Dict[str, Any]], view: str) -> Dict[str, Any]:
    """ECST for one cell under a cost view. Undefined if 0 accepted; unavailable
    (known floor) if any summed attempt cost was unavailable."""
    n_accepted = sum(1 for r in runs if _accepted(r))
    numerator = 0.0
    any_unavail = False
    have_number = False
    for r in runs:
        total, unavail = run_total(r, view)
        any_unavail = any_unavail or unavail
        if total is not None:
            numerator += total
            have_number = True
    if n_accepted == 0:
        return {"value": None, "status": UNDEFINED, "reason": "0 accepted tasks in cell",
                "attempt_cost_sum": (round(numerator, 6) if have_number else None),
                "attempt_cost_is_floor": any_unavail, "n_accepted": 0, "n_runs": len(runs)}
    if not have_number:
        return {"value": None, "status": UNAVAILABLE, "reason": "no attempt cost available",
                "n_accepted": n_accepted, "n_runs": len(runs)}
    return {"value": round(numerator / n_accepted, 6),
            "status": ("derived_floor" if any_unavail else "derived"),
            "attempt_cost_sum": round(numerator, 6), "attempt_cost_is_floor": any_unavail,
            "n_accepted": n_accepted, "n_runs": len(runs)}


def heac(ecst_result: Dict[str, Any], runs: List[Dict[str, Any]],
         loaded_rate_usd_per_min: Optional[float] = None) -> Dict[str, Any]:
    """HEAC = ECST + human-minutes × rate. The human term is unavailable until the
    human-effort subset is recorded; HEAC then reports its model component only."""
    mins = 0.0
    have_minutes = False
    for r in runs:
        he = r.get("human_effort", {})
        for k in ("active_minutes", "review_minutes", "correction_minutes"):
            v = (he.get(k) or {}).get("value")
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                mins += v
                have_minutes = True
    if not have_minutes or loaded_rate_usd_per_min is None:
        return {"value": None, "status": UNAVAILABLE,
                "reason": "human-effort minutes not recorded (or no rate supplied)",
                "model_component": ecst_result.get("value")}
    if ecst_result.get("value") is None:
        return {"value": None, "status": ecst_result.get("status", UNAVAILABLE),
                "reason": "ECST component not defined"}
    return {"value": round(ecst_result["value"] + mins * loaded_rate_usd_per_min, 6),
            "status": "derived", "human_minutes": mins}


def dispersion(values: List[float]) -> Dict[str, Any]:
    xs = sorted(v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool))
    if not xs:
        return {"n": 0, "median": None, "iqr": None, "min": None, "max": None}
    q = st.quantiles(xs, n=4) if len(xs) >= 2 else [xs[0], xs[0], xs[0]]
    return {"n": len(xs), "median": round(st.median(xs), 6),
            "iqr": round(q[2] - q[0], 6), "min": round(xs[0], 6), "max": round(xs[-1], 6)}


def compute(feasibility_dir: str) -> Dict[str, Any]:
    """Full NON-COMPARATIVE, internal-only metric bundle for the feasibility set."""
    cells = load_cells(feasibility_dir)
    out: Dict[str, Any] = {"note": "NON-COMPARATIVE, internal-only (feasibility criterion 5)",
                           "cells": {}, "qa_ecst_by_class": {}}
    class_runs: Dict[str, List[Dict[str, Any]]] = {}
    for (task, config), runs in sorted(cells.items()):
        marg_costs = [t for t in (run_total(r, "marginal")[0] for r in runs) if t is not None]
        out_toks = [ (r["usage"].get("output_tokens") or {}).get("value") for r in runs ]
        out_toks = [t for t in out_toks if isinstance(t, (int, float)) and not isinstance(t, bool)]
        e_marg = ecst(runs, "marginal")
        out["cells"][f"{task}|{config}"] = {
            "n_runs": len(runs),
            "n_accepted": sum(1 for r in runs if _accepted(r)),
            "ecst_marginal": e_marg,
            "ecst_fully_allocated": ecst(runs, "fully"),
            "heac_marginal": heac(e_marg, runs),
            "dispersion_marginal_cost_usd": dispersion(marg_costs),
            "dispersion_output_tokens": dispersion(out_toks),
        }
        # task_class isn't yet in the summary schema (CP-SCHEMA frozen), so group by
        # task_id — a 1:1 proxy for class in this set (pilot=feature, W4=bug_fix).
        cls = runs[0].get("task_class") or f"task:{task}"
        class_runs.setdefault(cls, []).extend(runs)
    for cls, runs in sorted(class_runs.items()):
        out["qa_ecst_by_class"][cls] = ecst(runs, "marginal")
    return out


if __name__ == "__main__":  # pragma: no cover - manual/reporting use
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "results/feasibility"
    print(json.dumps(compute(d), indent=2, sort_keys=True))
