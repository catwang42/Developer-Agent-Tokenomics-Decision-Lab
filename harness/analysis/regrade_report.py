"""Report what the offline regrade-v2 sweep actually changed.

Read-only over ``results/``. Reads the records the sweep wrote and nothing else:
no container, no model, no sealed file.

THE ONE THING THIS MODULE EXISTS TO GET RIGHT. A ``regrade-v2-summary.json``
compares itself to the run's *original* archived verdict, because that is the
only baseline that is always present. But many runs were already re-graded once,
offline, by the v1 pass after the container gate's git-ownership defect — and v1
recorded its own amendment in ``regrade-summary.json``. Reading only v2's
``original -> amended`` therefore reports flips that v1 had already found, and a
sweep that re-confirms 17 known flips would read as a sweep that discovered 17.

So every cell is reported as a ladder:

    original  ->  v1 (if a v1 regrade exists)  ->  v2

with ``changed_by_this_pass`` computed against the NEWEST prior verdict, not the
original one. ``changed_vs_original`` is kept beside it, because that is the
number the individual run records carry and a reader comparing the two should
find both here rather than conclude they disagree.

Public checks are a different story: v1 never ran the public gate, so the only
before/after that exists for them is original -> v2, and that is what is
reported. Each check lands in exactly one bucket:

    cleared        the check failed under the old grader and passes under the
                   fixed one — an ARTIFACT of the grader, not of the agent
    still_failing  failed under both — a GENUINE failure, named
    newly_failing  passed under the old grader, fails under the fixed one — a
                   REGRESSION, and the reason to read this report before
                   trusting the sweep
    unchanged_pass passed under both
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

V2_SUMMARY = "regrade-v2-summary.json"
V1_SUMMARY = "regrade-summary.json"


def _load(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _verdict(record: Optional[Dict[str, Any]], key: str) -> Optional[str]:
    if not record:
        return None
    block = record.get(key) or {}
    return block.get("acceptance_result")


def read_cell(dataset: str, run_dir: str) -> Optional[Dict[str, Any]]:
    """One row of the ladder, or None if the sweep never touched this run."""
    v2 = _load(os.path.join(run_dir, V2_SUMMARY))
    if v2 is None:
        return None
    v1 = _load(os.path.join(run_dir, V1_SUMMARY))

    run_id = v2.get("run_id") or os.path.basename(run_dir)
    parts = run_id.split("__")
    config = parts[1] if len(parts) > 1 else "?"
    rep = parts[2][len("rep"):] if len(parts) > 2 and parts[2].startswith("rep") else "?"

    original = _verdict(v2, "original")
    after_v1 = _verdict(v1, "amended")
    after_v2 = _verdict(v2, "amended")
    prior = after_v1 if after_v1 is not None else original

    delta = v2.get("public_check_delta") or {}
    images = (v2.get("method") or {}).get("images") or {}

    row: Dict[str, Any] = {
        "dataset": dataset,
        "run_id": run_id,
        "task_id": v2.get("task_id"),
        "config": config,
        "rep": rep,
        "status": v2.get("status"),
        "gate_image": images.get("gate_image"),
        "gate_content_digest": images.get("gate_content_digest"),
        "gate_image_built_now": images.get("gate_image_built_now"),
        "verdict_original": original,
        "verdict_after_v1": after_v1,
        "verdict_after_v2": after_v2,
        "prior_verdict": prior,
        "changed_by_this_pass": after_v2 is not None and after_v2 != prior,
        "changed_vs_original": after_v2 is not None and after_v2 != original,
        "hidden_before": (v2.get("original") or {}).get("hidden_status"),
        "hidden_after": (v2.get("amended") or {}).get("hidden_status"),
        "sealed_set_changed": v2.get("sealed_set_changed"),
        "public_cleared": list(delta.get("cleared") or []),
        "public_still_failing": list(delta.get("still_failing") or []),
        "public_newly_failing": list(delta.get("newly_failing") or []),
        "public_unchanged_pass": list(delta.get("unchanged_pass") or []),
    }
    if v2.get("status") == "refused":
        row["refusal_reason"] = v2.get("reason")
    return row


def scan(results_root: str, datasets: List[str]) -> Dict[str, Any]:
    """Every run in `datasets`, whether or not the sweep reached it."""
    rows: List[Dict[str, Any]] = []
    untouched: List[Dict[str, str]] = []
    for dataset in datasets:
        ds_dir = os.path.join(results_root, dataset)
        if not os.path.isdir(ds_dir):
            continue
        for name in sorted(os.listdir(ds_dir)):
            run_dir = os.path.join(ds_dir, name)
            if not os.path.isfile(os.path.join(run_dir, "summary.json")):
                continue
            row = read_cell(dataset, run_dir)
            if row is None:
                # Named, not silently dropped: a run the sweep did not reach is
                # a hole in the sweep's coverage and has to show up as one.
                untouched.append({"dataset": dataset, "run_id": name})
            else:
                rows.append(row)
    return {"cells": rows, "not_regraded": untouched}


def tally(scanned: Dict[str, Any]) -> Dict[str, Any]:
    rows = scanned["cells"]
    graded = [r for r in rows if r["status"] == "graded"]
    return {
        "runs_in_scope": len(rows) + len(scanned["not_regraded"]),
        "regraded": len(rows),
        "graded": len(graded),
        "refused_truncated": sum(1 for r in rows if r["status"] == "refused"),
        "not_regraded": len(scanned["not_regraded"]),
        "changed_by_this_pass": sum(1 for r in graded if r["changed_by_this_pass"]),
        "changed_vs_original": sum(1 for r in graded if r["changed_vs_original"]),
        "already_found_by_v1": sum(
            1 for r in graded if r["changed_vs_original"] and not r["changed_by_this_pass"]
        ),
        "public_checks_cleared": sum(len(r["public_cleared"]) for r in graded),
        "public_checks_newly_failing": sum(len(r["public_newly_failing"]) for r in graded),
        "runs_with_a_newly_failing_check": sum(
            1 for r in graded if r["public_newly_failing"]
        ),
        "gate_images": sorted({r["gate_image"] for r in rows if r["gate_image"]}),
    }


def _cell_line(r: Dict[str, Any]) -> str:
    if r["status"] == "refused":
        return (f"| {r['dataset']} | {r['task_id']} | {r['config']} | {r['rep']} | "
                f"REFUSED | — | — | — | truncated: no completed agent product |")
    ladder = f"{r['verdict_original']}"
    if r["verdict_after_v1"] is not None:
        ladder += f" → {r['verdict_after_v1']} (v1)"
    ladder += f" → {r['verdict_after_v2']} (v2)"
    notes = []
    if r["public_cleared"]:
        notes.append("artifact flip, public: " + ", ".join(r["public_cleared"]))
    if r["public_newly_failing"]:
        notes.append("REGRESSION, public: " + ", ".join(r["public_newly_failing"]))
    if r["public_still_failing"]:
        notes.append("genuine failure, public: " + ", ".join(r["public_still_failing"]))
    if r["hidden_before"] != r["hidden_after"]:
        notes.append(f"hidden {r['hidden_before']} → {r['hidden_after']}")
    if r["sealed_set_changed"]:
        notes.append("SEALED SET MOVED — not a like-for-like correction")
    return (f"| {r['dataset']} | {r['task_id']} | {r['config']} | {r['rep']} | "
            f"{ladder} | {'yes' if r['changed_by_this_pass'] else 'no'} | "
            f"{'yes' if r['changed_vs_original'] else 'no'} | "
            f"{r['gate_image'] or 'unavailable'} | {'; '.join(notes) or '—'} |")


def render(scanned: Dict[str, Any], counts: Dict[str, Any], *, generated_at: str,
           harness_head: str) -> str:
    lines = [
        "# Offline regrade-v2 sweep — what it changed",
        "",
        "**STATUS: AUTHORITATIVE** for the regrade-v2 pass over the screening datasets.",
        f"Generated {generated_at} from the records the sweep wrote; harness {harness_head}.",
        "Zero model spend: both gates were re-run in `--network=none` containers against",
        "the archived `agent-solution.diff`. No sealed file is read here.",
        "",
        "## How to read a row",
        "",
        "`changed by this pass` compares v2 to the NEWEST prior verdict — for a run the",
        "v1 pass already amended, that is v1's verdict, not the original one.",
        "`changed vs original` is what the individual `regrade-v2-summary.json` records",
        "carry, and it double-counts flips v1 had already found. Both are shown so the",
        "two never look like a contradiction.",
        "",
        "## Counts",
        "",
        f"- runs in scope: **{counts['runs_in_scope']}**",
        f"- re-graded: **{counts['regraded']}** ({counts['graded']} graded, "
        f"{counts['refused_truncated']} refused as truncated)",
        f"- not reached by the sweep: **{counts['not_regraded']}**",
        f"- verdicts changed **by this pass**: **{counts['changed_by_this_pass']}**",
        f"- verdicts different from the original archive: {counts['changed_vs_original']} "
        f"(of which {counts['already_found_by_v1']} were already found by the v1 regrade)",
        f"- public checks cleared (grader artifacts): **{counts['public_checks_cleared']}**",
        f"- public checks newly failing (regressions): "
        f"**{counts['public_checks_newly_failing']}** across "
        f"{counts['runs_with_a_newly_failing_check']} run(s)",
        "",
        "## Gate images used",
        "",
        "Every tag carries the gate-content digest introduced in PR #27, so none of",
        "these could have been served from a pre-fix cache:",
        "",
    ]
    lines += [f"- `{tag}`" for tag in counts["gate_images"]]
    lines += [
        "",
        "## Per cell",
        "",
        "| dataset | task | arm | rep | verdict ladder | changed by this pass | "
        "changed vs original | gate image | public checks |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    lines += [_cell_line(r) for r in scanned["cells"]]
    if scanned["not_regraded"]:
        lines += ["", "## Runs the sweep did not reach", "",
                  "Listed rather than omitted — each is a hole in this pass's coverage.", ""]
        lines += [f"- `{u['dataset']}/{u['run_id']}`" for u in scanned["not_regraded"]]
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import subprocess

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results", default="results")
    ap.add_argument("--dataset", action="append", required=True)
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--generated-at", required=True,
                    help="UTC stamp; passed in so the report is reproducible")
    args = ap.parse_args(argv)

    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True, check=False).stdout.strip()
    scanned = scan(args.results, args.dataset)
    counts = tally(scanned)
    with open(args.out_json, "w", encoding="utf-8") as fh:
        json.dump({"generated_at": args.generated_at, "harness_head": head,
                   "datasets": args.dataset, "counts": counts, **scanned},
                  fh, indent=2, sort_keys=True)
        fh.write("\n")
    with open(args.out_md, "w", encoding="utf-8") as fh:
        fh.write(render(scanned, counts, generated_at=args.generated_at,
                        harness_head=head or "unavailable"))
    print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
