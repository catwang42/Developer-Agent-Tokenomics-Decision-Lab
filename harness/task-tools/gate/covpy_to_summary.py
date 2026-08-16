#!/usr/bin/env python3
"""Translate coverage.py's JSON report into the istanbul `coverage-summary.json`
shape, so the python stack and the node stack share ONE numeric threshold
evaluator (gate/coverage_eval.py) and therefore one definition of "meets the
declared per-file minimum".

Pure re-shaping of numbers coverage.py already produced — nothing is inferred,
nothing is filled in. A metric coverage.py did not measure (e.g. branches when the
run had no `--cov-branch`, or per-function coverage, which coverage.py does not
report) is OMITTED, so coverage_eval.py reports it as NOT MEASURED rather than
seeing a zero or an invented value (CLAUDE.md rule 3: unavailable != 0).

CLI:  covpy_to_summary.py <coverage.json> <coverage-summary.json>
  exit 0 = written; 2 = unreadable / unrecognised input.
"""
from __future__ import annotations

import json
import sys


def _metric(covered: int, total: int) -> dict:
    # istanbul reports 100% for an empty denominator; match that so a file with no
    # branches is not scored as a shortfall.
    pct = 100.0 if total == 0 else round(covered * 100.0 / total, 2)
    return {"total": total, "covered": covered, "skipped": 0, "pct": pct}


def convert(report: dict) -> dict:
    """coverage.py JSON -> istanbul coverage-summary.json."""
    out: dict = {}
    for path, entry in (report.get("files") or {}).items():
        summary = entry.get("summary") or {}
        rec: dict = {}
        if "num_statements" in summary:
            stmts = _metric(int(summary.get("covered_lines", 0)),
                            int(summary["num_statements"]))
            # coverage.py measures statements; istanbul's "lines" is the closest
            # equivalent and is populated from the same pair.
            rec["statements"] = stmts
            rec["lines"] = dict(stmts)
        if "num_branches" in summary:
            rec["branches"] = _metric(int(summary.get("covered_branches", 0)),
                                      int(summary["num_branches"]))
        # No "functions": coverage.py does not report per-function coverage.
        out[path] = rec

    totals = report.get("totals") or {}
    if totals:
        rec = {}
        if "num_statements" in totals:
            stmts = _metric(int(totals.get("covered_lines", 0)),
                            int(totals["num_statements"]))
            rec["statements"] = stmts
            rec["lines"] = dict(stmts)
        if "num_branches" in totals:
            rec["branches"] = _metric(int(totals.get("covered_branches", 0)),
                                      int(totals["num_branches"]))
        out["total"] = rec
    return out


def main(argv) -> int:
    if len(argv) != 3:
        print("usage: covpy_to_summary.py <coverage.json> <coverage-summary.json>",
              file=sys.stderr)
        return 2
    try:
        with open(argv[1], encoding="utf-8") as fh:
            report = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"coverage.py report unreadable ({argv[1]}): {exc}", file=sys.stderr)
        return 2
    if "files" not in report:
        print(f"not a coverage.py JSON report: {argv[1]}", file=sys.stderr)
        return 2
    with open(argv[2], "w", encoding="utf-8") as fh:
        json.dump(convert(report), fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
