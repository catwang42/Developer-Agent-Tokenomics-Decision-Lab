"""Aggregate per-run result records into a non-comparative per-cell view.

A *cell* is a (task_id, configuration_id) pair — the unit the feasibility protocol
reports dispersion over. For each cell we report descriptive statistics only
(counts, acceptance breakdown, cost median/min/max over the runs whose cost is
KNOWN, plus the count of unavailable-cost legs). This is deliberately NOT a
cross-product/cross-config ranking: no "A beats B", no vendor claim (CLAUDE.md
rule 4). Unavailable costs are surfaced, never zero-filled (rule 3).

Run:  python -m harness.aggregate.aggregate results/feasibility
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

from harness.results.record import build_result_record

NONCOMPARATIVE_BANNER = (
    "NON-COMPARATIVE / INTERNAL — descriptive per-cell stats only; no cross-product "
    "or cross-config ranking, no vendor claim (CLAUDE.md 1.2/rule 4)."
)


def _load_one(run_dir: str) -> Optional[Dict[str, Any]]:
    """Load a run's result record: prefer result.json, else derive from summary.json."""
    result_path = os.path.join(run_dir, "result.json")
    if os.path.isfile(result_path):
        try:
            with open(result_path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None
    summary_path = os.path.join(run_dir, "summary.json")
    if os.path.isfile(summary_path):
        try:
            with open(summary_path, encoding="utf-8") as fh:
                return build_result_record(json.load(fh))
        except (OSError, json.JSONDecodeError):
            return None
    return None


def load_records(results_dir: str) -> List[Dict[str, Any]]:
    """Load every run's result record under ``results_dir`` (sorted by run dir name)."""
    records: List[Dict[str, Any]] = []
    if not os.path.isdir(results_dir):
        return records
    for name in sorted(os.listdir(results_dir)):
        run_dir = os.path.join(results_dir, name)
        if os.path.isdir(run_dir):
            rec = _load_one(run_dir)
            if rec is not None:
                records.append(rec)
    return records


def _median(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else round((s[mid - 1] + s[mid]) / 2, 6)


def _run_known_cost(rec: Dict[str, Any]) -> Optional[float]:
    """Sum a run's KNOWN per-leg marginal cost; None if no leg has a numeric cost.

    A leg whose cost is unavailable is skipped from the sum (never zero-imputed) but
    flagged separately via ``_run_unavailable_legs``.
    """
    total: Optional[float] = None
    for leg in rec.get("legs") or []:
        mov = (leg.get("marginal_operating_usd") or {})
        v = mov.get("value")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            total = (total or 0.0) + float(v)
    return None if total is None else round(total, 6)


def _run_unavailable_legs(rec: Dict[str, Any]) -> int:
    n = 0
    for leg in rec.get("legs") or []:
        mov = (leg.get("marginal_operating_usd") or {})
        v = mov.get("value")
        if not (isinstance(v, (int, float)) and not isinstance(v, bool)):
            n += 1
    return n


def aggregate(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Group records into (task_id, configuration_id) cells with descriptive stats."""
    cells: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        task = rec.get("task_id") or "?"
        config = rec.get("configuration_id") or "?"
        key = f"{task}::{config}"
        cell = cells.setdefault(key, {
            "task_id": task, "configuration_id": config, "n_runs": 0,
            "acceptance": {"accepted": 0, "rejected": 0, "error": 0, "other": 0},
            "network_policies": {}, "permission_profiles": {},
            "_known_costs": [], "cost_unavailable_legs": 0,
        })
        cell["n_runs"] += 1
        res = ((rec.get("acceptance") or {}).get("result")) or "other"
        cell["acceptance"][res if res in cell["acceptance"] else "other"] += 1

        iso = rec.get("isolation") or {}
        for field, bucket in (("network_policy", "network_policies"),
                              ("permission_profile", "permission_profiles")):
            val = ((iso.get(field) or {}).get("value")) or "unrecorded"
            cell[bucket][val] = cell[bucket].get(val, 0) + 1

        known = _run_known_cost(rec)
        if known is not None:
            cell["_known_costs"].append(known)
        cell["cost_unavailable_legs"] += _run_unavailable_legs(rec)

    out_cells = []
    for key in sorted(cells):
        cell = cells[key]
        costs = cell.pop("_known_costs")
        cell["cost_known_runs"] = len(costs)
        cell["marginal_operating_usd"] = {
            "median": _median(costs),
            "min": min(costs) if costs else None,
            "max": max(costs) if costs else None,
        }
        out_cells.append(cell)

    return {
        "note": NONCOMPARATIVE_BANNER,
        "n_records": len(records),
        "n_cells": len(out_cells),
        "cells": out_cells,
    }


def _fmt_cost(c: Optional[float]) -> str:
    return "n/a" if c is None else f"{c:.4f}"


def render_table(agg: Dict[str, Any]) -> str:
    lines = [
        NONCOMPARATIVE_BANNER,
        "",
        f"{'task_id':<34} {'cfg':<4} {'n':>2} {'acc':>3} {'rej':>3} {'err':>3} "
        f"{'cost_n':>6} {'cost_med':>9} {'cost_min':>9} {'cost_max':>9}  net",
    ]
    for cell in agg["cells"]:
        acc = cell["acceptance"]
        mov = cell["marginal_operating_usd"]
        nets = ",".join(sorted(cell["network_policies"]))
        lines.append(
            f"{cell['task_id'][:34]:<34} {cell['configuration_id']:<4} "
            f"{cell['n_runs']:>2} {acc['accepted']:>3} {acc['rejected']:>3} {acc['error']:>3} "
            f"{cell['cost_known_runs']:>6} {_fmt_cost(mov['median']):>9} "
            f"{_fmt_cost(mov['min']):>9} {_fmt_cost(mov['max']):>9}  {nets}"
        )
    lines.append("")
    lines.append(f"{agg['n_records']} run(s) across {agg['n_cells']} cell(s).")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Non-comparative per-cell aggregation over run result records")
    ap.add_argument("results_dir", help="dir of run subdirs (e.g. results/feasibility)")
    ap.add_argument("--json-out", default=None,
                    help="also write the aggregate JSON to this path")
    args = ap.parse_args(argv)

    records = load_records(args.results_dir)
    agg = aggregate(records)
    print(render_table(agg))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(agg, fh, indent=2, sort_keys=True)
        print(f"\nwrote {args.json_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
