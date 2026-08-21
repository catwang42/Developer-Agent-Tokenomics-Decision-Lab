"""Graded quality from the sealed output a run already archived.

EXPLORATORY SECONDARY. The pre-registered outcome is the binary gate and it does
not move: a run that the sealed gate rejected is rejected. What a binary verdict
cannot show is *how far off* a rejection was — W1b caught every real mutant in
every run and still failed, on a control; W6 found all six planted defects in
some runs and still failed, on one fabricated line. Those are different failures
wearing the same word, and the difference is in the log.

So this reads the sealed runner's own stderr, as archived under ``results/``, and
counts. It never re-runs anything, never opens ``tasks/*/hidden/``, and never
overrides an acceptance verdict.

WHAT IS EXTRACTABLE, AND WHAT IS NOT. The gate captures the sealed runner's
stderr for `test_generation` and `pr_review` tasks, whose runners print one
labelled line per mutant/defect by design, and — since the graded hidden gate
landed — a per-check id/status block for `solution` tasks. A run graded BEFORE
that change kept the exit code alone, so its detail is not in the archive to
extract and it returns `available: false` with the reason, never a zero
(CLAUDE.md rule 3). The remedy for those runs is the offline re-grade, not a
guess. Truncated runs are excluded outright, whatever their log contains.

Run:  python -m harness.analysis.quality results
      python -m harness.analysis.quality results --write   # per-run quality-score.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

from harness.analysis.archive import parse_run_dir_name, scan, truncation

SEALED_LOGS = ("gate-hidden.log", "regrade-gate-hidden.log")

# W1 (jest mutation): `hidden: caught: m3-some-predicate-flip`
W1_CAUGHT = re.compile(r"^\s*\|\s*hidden:\s*caught:\s*(?P<id>\S+)")
W1_MISSED = re.compile(r"^\s*\|\s*hidden:\s*(?:NOT[- ]caught|missed):\s*(?P<id>\S+)",
                       re.IGNORECASE)
W1_NO_TESTS = re.compile(r"^\s*\|\s*hidden:\s*no agent tests")

# W1b (pytest mutation): `CAUGHT M3`, `MISSED M3`, `CONTROL M6-control caught`
W1B_CAUGHT = re.compile(r"^\s*\|\s*CAUGHT\s+(?P<id>\S+)")
W1B_MISSED = re.compile(r"^\s*\|\s*MISSED\s+(?P<id>\S+)")
W1B_CONTROL = re.compile(r"^\s*\|\s*CONTROL\s+(?P<id>\S+)\s+(?P<state>caught|survived)")

# W6 (review): `DETECTED D2-inverted-guard`, `MISSED D2-…`, `FABRICATED path:191`
W6_DETECTED = re.compile(r"^\s*\|\s*DETECTED\s+(?P<id>\S+)")
W6_MISSED = re.compile(r"^\s*\|\s*MISSED\s+(?P<id>\S+)")
W6_FABRICATED = re.compile(r"^\s*\|\s*FABRICATED\s+(?P<ref>\S+)")
W6_NO_REPORT = re.compile(r"^\s*\|\s*no review-report\.txt")

# Solution tasks (W3, W4b): `  | PASSED<TAB>tests/test_rules.py::test_L010`.
# Written by the graded hidden gate; ids and statuses only, by construction.
SEALED_CHECK = re.compile(r"^\s*\|\s*(?P<status>[A-Z]+)\t(?P<id>\S+)")
SEALED_CHECK_HEADER = "-- sealed checks (id and status only) --"
PASSING_STATUSES = frozenset({"PASSED", "PASS", "XFAIL"})


def _sealed_block(run_dir: str, header: str) -> Optional[str]:
    """A named block of the archived hidden-gate log, "" if absent, None if no log."""
    for name in SEALED_LOGS:
        path = os.path.join(run_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        start = text.find(header)
        if start < 0:
            return ""  # a log exists but this block is not in it
        block = text[start:]
        end = block.find("== hidden gate:")
        return block if end < 0 else block[:end]
    return None


def sealed_stderr(run_dir: str) -> Optional[str]:
    """The archived sealed-runner stderr block, or None if the run has no log."""
    return _sealed_block(run_dir, "-- sealed runner (stderr) --")


def sealed_checks(run_dir: str) -> Optional[str]:
    """The archived per-check block a graded solution-task gate writes."""
    return _sealed_block(run_dir, SEALED_CHECK_HEADER)


def _unavailable(reason: str) -> Dict[str, Any]:
    return {"available": False, "reason": reason, "score": None, "max": None}


def score_w1(block: str) -> Dict[str, Any]:
    """Mutants caught out of the sealed set, jest flavour."""
    caught = sorted({m.group("id") for m in map(W1_CAUGHT.match, block.splitlines())
                     if m})
    missed = sorted({m.group("id") for m in map(W1_MISSED.match, block.splitlines())
                     if m})
    if not caught and not missed:
        if any(W1_NO_TESTS.match(l) for l in block.splitlines()):
            return {"available": True, "score": 0, "max": None,
                    "detail": {"caught": [], "missed": [],
                               "note": "no agent tests were present to run"}}
        return _unavailable("no per-mutant lines in the archived sealed stderr")
    return {"available": True, "score": len(caught), "max": len(caught) + len(missed),
            "detail": {"caught": caught, "missed": missed}}


def score_w1b(block: str) -> Dict[str, Any]:
    """Mutants caught, pytest flavour, with the control mutant separated out.

    The control is planted to be UNCATCHABLE by a correct test: catching it means
    the tests reject behaviour the library is entitled to have. It is excluded
    from the score and reported on its own, because a caught control is a
    quality signal pointing the opposite way from a caught mutant.
    """
    lines = block.splitlines()
    control = {m.group("id"): m.group("state")
               for m in map(W1B_CONTROL.match, lines) if m}
    caught = sorted({m.group("id") for m in map(W1B_CAUGHT.match, lines) if m}
                    - set(control))
    missed = sorted({m.group("id") for m in map(W1B_MISSED.match, lines) if m}
                    - set(control))
    if not caught and not missed and not control:
        return _unavailable("no per-mutant lines in the archived sealed stderr")
    return {"available": True, "score": len(caught), "max": len(caught) + len(missed),
            "detail": {"caught": caught, "missed": missed,
                       "control": control,
                       "control_caught": sorted(k for k, v in control.items()
                                                if v == "caught")}}


def score_w6(block: str) -> Dict[str, Any]:
    """Planted defects found, and fabrications — findings about code that is fine.

    Reported as two numbers, never netted into one. A review that finds all six
    defects and invents a seventh is not a five-out-of-six review; the two say
    different things to a reader deciding whether to trust the output.
    """
    lines = block.splitlines()
    detected = sorted({m.group("id") for m in map(W6_DETECTED.match, lines) if m})
    missed = sorted({m.group("id") for m in map(W6_MISSED.match, lines) if m})
    fabricated = sorted({m.group("ref") for m in map(W6_FABRICATED.match, lines) if m})
    if not detected and not missed:
        if any(W6_NO_REPORT.match(l) for l in lines):
            return {"available": True, "score": 0, "max": None,
                    "detail": {"detected": [], "missed": [], "fabricated": [],
                               "fabrication_count": 0,
                               "note": "no review-report.txt was produced"}}
        return _unavailable("no per-defect lines in the archived sealed stderr")
    return {"available": True, "score": len(detected),
            "max": len(detected) + len(missed),
            "detail": {"detected": detected, "missed": missed,
                       "fabricated": fabricated,
                       "fabrication_count": len(fabricated)}}


def score_sealed_checks(block: str) -> Dict[str, Any]:
    """Sealed checks passed, for a solution task graded per check.

    Only present in runs graded by a hidden gate carrying
    `stack_run_selected_graded`. Runs graded before that keep the exit code
    alone, and come back unavailable — the detail was never written down, and a
    zero would claim a measurement nobody made.
    """
    seen: Dict[str, str] = {}
    for line in block.splitlines():
        m = SEALED_CHECK.match(line)
        if m:
            seen[m.group("id")] = m.group("status")
    if not seen:
        return _unavailable(
            "this run was graded before the hidden gate recorded per-check "
            "results; only the sealed exit code is in the archive")
    passed = sorted(k for k, v in seen.items() if v in PASSING_STATUSES)
    failed = sorted(k for k, v in seen.items() if v not in PASSING_STATUSES)
    return {"available": True, "score": len(passed), "max": len(seen),
            "detail": {"passed": passed, "failed": failed}}


# Which parser a task's sealed output speaks. Keyed on the task id prefix because
# that is what the run directory carries; a task not listed is unscored, loudly.
# The reader column says which block of the hidden-gate log to hand the parser.
SCORERS = {
    "w1-": ("mutants_caught", score_w1, sealed_stderr),
    "w1b-": ("mutants_caught", score_w1b, sealed_stderr),
    "w6-": ("defects_found", score_w6, sealed_stderr),
    "w3-": ("sealed_rules_clean", score_sealed_checks, sealed_checks),
    "w4b-": ("sealed_assertions_passed", score_sealed_checks, sealed_checks),
}


def _scorer_for(task_id: str):
    for prefix in sorted(SCORERS, key=len, reverse=True):
        if task_id.startswith(prefix):
            return SCORERS[prefix]
    return None, None, None


def score_run(run_dir: str) -> Optional[Dict[str, Any]]:
    """A quality-score record for one archived run, or None if not a run dir."""
    ident = parse_run_dir_name(os.path.basename(run_dir))
    if ident is None:
        return None
    task_id = ident["task_id"]
    record: Dict[str, Any] = {
        "schema": "quality-score/v1",
        "status": "EXPLORATORY SECONDARY — the pre-registered outcome is the "
                  "binary sealed gate; this does not override it",
        "task_id": task_id,
        "configuration_id": ident["configuration_id"],
        "rep": ident["rep"],
        "source": "sealed runner stderr as archived by this run; nothing re-run, "
                  "no sealed material read",
    }
    # A run the harness cut off is not a measurement of the model, and a partial
    # score from one is worse than no score: `0 defects found` reads as a model
    # that found nothing when the truth is that it was killed mid-sentence. So a
    # truncated run scores nothing at all, whatever its log happens to contain.
    cut = truncation(run_dir)
    if cut:
        record["metric"] = None
        record.update(_unavailable(
            f"run truncated ({cut}); partial work is not a quality measurement"))
        record["truncated"] = cut
        return record

    metric, scorer, reader = _scorer_for(task_id)
    if scorer is None:
        record["metric"] = None
        record.update(_unavailable(f"no sealed-output grammar registered for {task_id}"))
        return record

    block = reader(run_dir)
    record["metric"] = metric
    if block is None:
        record.update(_unavailable("no sealed gate log archived for this run"))
    else:
        # An empty block goes to the scorer too: each one knows why ITS output
        # would be missing, and "the gate did not record per-check results" is a
        # more useful thing to read than "the block is empty".
        record.update(scorer(block))
    return record


def score_all(results_root: str) -> List[Dict[str, Any]]:
    rows = []
    for run in scan(results_root):
        rec = score_run(run["run_dir"])
        if rec is not None:
            rec["dataset"] = run["dataset"]
            rec["run_dir"] = run["run_dir"]
            rec["acceptance"] = run["acceptance"]
            rows.append(rec)
    return rows


def write_scores(rows: List[Dict[str, Any]]) -> int:
    """Write ``quality-score.json`` beside each run. Adds a file; edits none."""
    written = 0
    for rec in rows:
        payload = {k: v for k, v in rec.items() if k not in ("run_dir", "dataset")}
        path = os.path.join(rec["run_dir"], "quality-score.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        written += 1
    return written


def _fmt(rows: List[Dict[str, Any]]) -> str:
    out = [f"{'dataset':<28} {'task::config':<48} rep  {'metric':<15} "
           f"{'score':>7}  notes"]
    for r in rows:
        cell = f"{r['task_id']}::{r['configuration_id']}"
        if r["available"]:
            score = f"{r['score']}/{r['max']}" if r["max"] else str(r["score"])
            fab = r.get("detail", {}).get("fabrication_count")
            ctrl = r.get("detail", {}).get("control_caught")
            note = ""
            if fab:
                note = f"{fab} fabricated"
            elif ctrl:
                note = f"control caught: {','.join(ctrl)}"
            elif r.get("detail", {}).get("note"):
                note = r["detail"]["note"]
        else:
            score, note = "unavail", r["reason"]
        out.append(f"{r['dataset']:<28} {cell:<48} {r['rep']:>3}  "
                   f"{str(r['metric']):<15} {score:>7}  {note}")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results_root")
    ap.add_argument("--write", action="store_true",
                    help="write quality-score.json into each run directory")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    rows = score_all(args.results_root)
    if args.json:
        json.dump(rows, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print(_fmt(rows))
        avail = sum(1 for r in rows if r["available"])
        print(f"\n{len(rows)} run(s); {avail} scored, {len(rows) - avail} unavailable")
    if args.write:
        print(f"wrote quality-score.json for {write_scores(rows)} run(s)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
