#!/usr/bin/env python3
"""Coverage-threshold evaluator for the test-generation gate (check T3), split out
of the bash gate so the numeric decision is unit-testable offline
(tests/test_gate_logic.py). Pure arithmetic over the jest coverage-summary.json that
jest already produced — no network, no node.

Reads a task's `coverage_target` (metric + per-file min_pct) and a jest
`coverage-summary.json`, and requires EACH declared file to meet its per-file
minimum for the chosen metric (default: branches). Per-file thresholds let a task
gate on an honest reachable ceiling (e.g. author.mapper 83.33%) rather than an
impossible flat 100% — see report/w1-coverage-analysis.md.

CLI:  coverage_eval.py <coverage-summary.json> <task.yaml>
  stdout: one-line human detail; exit 0 = all files meet minimum, 1 = shortfall,
  2 = usage / unreadable input / missing coverage_target.
"""
from __future__ import annotations

import json
import sys

# istanbul reports pct rounded to 2 decimals; allow that much slack so a config that
# says 83.33 accepts a measured 83.33 without a floating-point miss.
_EPS = 0.01


def _match(summary: dict, path: str):
    """Find a coverage-summary entry for a repo-relative path. Summary keys are
    absolute paths; match by exact key or path suffix (prefer a '/'-boundary match)."""
    if path in summary:
        return summary[path]
    boundary = "/" + path
    best = None
    for key, val in summary.items():
        if key == "total":
            continue
        if key.endswith(boundary):
            return val
        if key.endswith(path):
            best = val
    return best


def evaluate(summary: dict, coverage_target: dict):
    """Return (ok: bool, detail: str)."""
    metric = (coverage_target or {}).get("metric", "branches")
    files = (coverage_target or {}).get("files") or []
    if not files:
        return False, "coverage_target.files is empty"
    ok, parts = True, []
    for f in files:
        path = f["path"]
        minp = float(f["min_pct"])
        entry = _match(summary, path)
        if entry is None or metric not in entry:
            ok = False
            parts.append(f"{path}: {metric} NOT MEASURED")
            continue
        m = entry[metric]
        pct = float(m["pct"])
        passed = pct + _EPS >= minp
        ok = ok and passed
        parts.append(
            f"{path} {metric} {m['covered']}/{m['total']}={pct}% "
            f"(min {minp}%){'' if passed else ' SHORTFALL'}"
        )
    return ok, "; ".join(parts)


def main(argv) -> int:
    if len(argv) != 3:
        print("usage: coverage_eval.py <coverage-summary.json> <task.yaml>",
              file=sys.stderr)
        return 2
    try:
        with open(argv[1], encoding="utf-8") as fh:
            summary = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"coverage summary unreadable ({argv[1]}): {exc}", file=sys.stderr)
        return 2
    try:
        import yaml
        with open(argv[2], encoding="utf-8") as fh:
            task = yaml.safe_load(fh) or {}
    except (OSError, ValueError) as exc:
        print(f"task.yaml unreadable ({argv[2]}): {exc}", file=sys.stderr)
        return 2
    ct = task.get("coverage_target")
    if not ct:
        print("task.yaml has no coverage_target", file=sys.stderr)
        return 2
    ok, detail = evaluate(summary, ct)
    print(detail)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
