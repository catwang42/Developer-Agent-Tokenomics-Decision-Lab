"""One row per archived run: what it is, whether it finished, how it was graded.

The backbone the re-grade sweep, the makeup enumeration and the final table all
read from. It answers three questions per run directory and nothing else:

  identity   — dataset, task, configuration, rep, timestamp
  substance  — did the agent actually produce work, or is the run TRUNCATED
               (a stop reason like claude_timeout, or a zero-byte diff)?
  grading    — the public checks and the sealed gate's verdict as recorded,
               plus the gate image tag that produced them where the run
               recorded one.

Truncation matters because a truncated run is not evidence about the model: the
harness stopped it. Grading such a cell as `rejected` would silently convert a
harness fault into a model result. So truncated runs are flagged here, refused
by the re-grade, and enumerated for makeup.

Read-only. Never opens ``tasks/*/hidden/``; the sealed *output* it reads is the
gate log the run itself archived under ``results/``.

Run:  python -m harness.analysis.archive results            # table
      python -m harness.analysis.archive results --json     # rows
      python -m harness.analysis.archive results --truncated
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

# `<task_id>__<configuration_id>__rep<n>__<UTC timestamp>`, the runner's layout.
RUN_DIR_RE = re.compile(
    r"^(?P<task>.+?)__(?P<config>[A-Za-z0-9-]+)__rep(?P<rep>\d+)__(?P<stamp>\d{8}T\d{6})$")

# A run whose agent leg ended for one of these reasons produced whatever it had
# got to, not an answer. Recorded by the adapter in the agent leg's stop reason.
TRUNCATING_STOP_REASONS = frozenset({
    "claude_timeout", "timeout", "wall_clock_exceeded", "budget_exhausted",
    "killed", "interrupted",
})


def parse_run_dir_name(name: str) -> Optional[Dict[str, Any]]:
    """Identity from the directory name, or None if it is not a run directory."""
    m = RUN_DIR_RE.match(name)
    if not m:
        return None
    return {"task_id": m.group("task"), "configuration_id": m.group("config"),
            "rep": int(m.group("rep")), "started_utc": m.group("stamp")}


def _load_json(path: str) -> Optional[Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _read_text(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _public_checks(run_dir: str, summary: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """{check id: status} from gate-public.json, else from the summary."""
    doc = _load_json(os.path.join(run_dir, "gate-public.json"))
    checks = (doc or {}).get("checks")
    if checks is None and summary:
        pub = summary.get("acceptance", {}).get("gate_checks", {}).get("public", {})
        checks = pub.get("checks")
    return {c["id"]: c.get("status", "?") for c in (checks or []) if "id" in c}


def _public_details(run_dir: str, summary: Optional[Dict[str, Any]]) -> Dict[str, str]:
    doc = _load_json(os.path.join(run_dir, "gate-public.json"))
    checks = (doc or {}).get("checks")
    if checks is None and summary:
        pub = summary.get("acceptance", {}).get("gate_checks", {}).get("public", {})
        checks = pub.get("checks")
    return {c["id"]: c.get("detail", "") for c in (checks or []) if "id" in c}


def _hidden(run_dir: str, summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    doc = _load_json(os.path.join(run_dir, "gate-hidden.json"))
    if doc is None and summary:
        doc = summary.get("acceptance", {}).get("gate_checks", {}).get("hidden")
    doc = doc or {}
    return {"status": doc.get("status"), "hash": doc.get("hash"),
            "version": doc.get("version")}


def _agent_legs(run_dir: str) -> List[Dict[str, Any]]:
    record = _load_json(os.path.join(run_dir, "result.json")) or {}
    legs = record.get("legs")
    if legs is None:
        summary = _load_json(os.path.join(run_dir, "summary.json")) or {}
        legs = summary.get("legs", [])
    return [leg for leg in legs or [] if str(leg.get("leg_id", "")).startswith("ma")
            or leg.get("role") in ("agent", "main")] or list(legs or [])


def _stop_reasons(run_dir: str) -> List[str]:
    """Every stop/termination reason the run recorded.

    Three places, because the harness records truncation in three shapes: a leg
    field, a `failure` event's ``category`` (this is where `claude_timeout`
    lives — the conductor emits it when the agent leg hits the wall clock), and
    the summary's rolled-up ``failures_by_category``.
    """
    reasons: List[str] = []
    for leg in _agent_legs(run_dir):
        for key in ("stop_reason", "termination_reason", "exit_reason", "status"):
            val = leg.get(key)
            if isinstance(val, dict):
                val = val.get("value")
            if isinstance(val, str) and val:
                reasons.append(val)

    events = os.path.join(run_dir, "events.jsonl")
    if os.path.isfile(events):
        for line in _read_text(events).splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
            if ev.get("event_type") == "failure":
                cat = ev.get("category") or data.get("category")
                if isinstance(cat, str) and cat:
                    reasons.append(cat)
            for key in ("stop_reason", "termination_reason", "reason"):
                val = ev.get(key) or data.get(key)
                if isinstance(val, str) and val:
                    reasons.append(val)

    summary = _load_json(os.path.join(run_dir, "summary.json")) or {}
    by_cat = (summary.get("behavior", {}).get("failures_by_category") or {}).get("value")
    if isinstance(by_cat, dict):
        reasons.extend(k for k, n in by_cat.items() if isinstance(k, str) and n)
    return sorted(set(reasons))


def _diff_bytes(run_dir: str) -> Optional[int]:
    path = os.path.join(run_dir, "agent-solution.diff")
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def truncation(run_dir: str) -> Optional[str]:
    """Why this run is not evidence about the model, or None if it is.

    Two independent signals, either sufficient: a truncating stop reason, or an
    absent/empty diff (the agent leg ran but delivered nothing to grade).
    """
    hits = [r for r in _stop_reasons(run_dir) if r in TRUNCATING_STOP_REASONS]
    if hits:
        return f"stop_reason={','.join(hits)}"
    size = _diff_bytes(run_dir)
    if size is None:
        return "no agent-solution.diff archived"
    if size == 0:
        return "zero-byte agent-solution.diff"
    return None


def _gate_image(run_dir: str) -> Optional[str]:
    """The gate image tag the run used, if it recorded one."""
    text = _read_text(os.path.join(run_dir, "invocation.txt")) + \
        _read_text(os.path.join(run_dir, "gate-public.log"))
    m = re.search(r"lab-subject/[A-Za-z0-9._/-]+:[A-Za-z0-9._-]+", text)
    return m.group(0) if m else None


def read_run(run_dir: str, dataset: str) -> Optional[Dict[str, Any]]:
    """One inventory row, or None if ``run_dir`` is not a run directory."""
    ident = parse_run_dir_name(os.path.basename(run_dir))
    if ident is None:
        return None
    summary = _load_json(os.path.join(run_dir, "summary.json"))
    record = _load_json(os.path.join(run_dir, "result.json")) or {}
    acceptance = (record.get("acceptance")
                  or (summary or {}).get("acceptance") or {})
    row = dict(ident)
    row.update({
        "dataset": dataset,
        "run_dir": run_dir,
        "cell": f"{ident['task_id']}::{ident['configuration_id']}",
        "acceptance": acceptance.get("result"),
        "public_checks": _public_checks(run_dir, summary),
        "public_details": _public_details(run_dir, summary),
        "hidden": _hidden(run_dir, summary),
        "diff_bytes": _diff_bytes(run_dir),
        "stop_reasons": _stop_reasons(run_dir),
        "truncated": truncation(run_dir),
        "gate_image": _gate_image(run_dir),
        "product": ((record.get("identity") or {}).get("product") or {}).get("value"),
        "selector": ((record.get("identity") or {}).get("model_or_selector")
                     or {}).get("value"),
    })
    return row


def scan(results_root: str) -> List[Dict[str, Any]]:
    """Every archived run under every dataset directory below ``results_root``."""
    rows: List[Dict[str, Any]] = []
    if not os.path.isdir(results_root):
        return rows
    for dataset in sorted(os.listdir(results_root)):
        dpath = os.path.join(results_root, dataset)
        if not os.path.isdir(dpath):
            continue
        for name in sorted(os.listdir(dpath)):
            row = read_run(os.path.join(dpath, name), dataset)
            if row is not None:
                rows.append(row)
    return rows


# Datasets that are not screening evidence: smoke runs of the harness itself and
# the batch that was HALTed mid-flight. A run in one of these neither counts as
# evidence nor supersedes a lost sample.
NON_EVIDENCE_PREFIXES = ("smoke", "pilot-reference", "revalidation",
                         "screening-batch1-aborted")


def is_evidence(dataset: str) -> bool:
    return not dataset.startswith(NON_EVIDENCE_PREFIXES)


def replacements(rows: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str, int], str]:
    """{(task, config, rep): dataset} — where a lost sample was later re-drawn.

    Per REP, not per cell. A cell with three reps and one truncated has lost one
    sample; the two survivors do not replace it, and reporting a median over two
    where the protocol pre-registered three is a quiet change to the design. Only
    a later untruncated run of that same rep restores it.
    """
    latest: Dict[Tuple[str, str, int], Tuple[str, str]] = {}
    for row in rows:
        if row["truncated"] or not is_evidence(row["dataset"]):
            continue
        key = (row["task_id"], row["configuration_id"], row["rep"])
        if key not in latest or row["started_utc"] > latest[key][0]:
            latest[key] = (row["started_utc"], row["dataset"])
    return {k: v[1] for k, v in latest.items()}


def needs_makeup(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Truncated evidence runs no later untruncated run of the same rep replaced."""
    covered = replacements(rows)
    out = []
    for row in rows:
        if not row["truncated"] or not is_evidence(row["dataset"]):
            continue
        key = (row["task_id"], row["configuration_id"], row["rep"])
        if key in covered:
            continue  # a later pass re-drew this sample
        out.append(row)
    return sorted(out, key=lambda r: (r["task_id"], r["configuration_id"], r["rep"]))


def _fmt_table(rows: List[Dict[str, Any]]) -> str:
    lines = [f"{'dataset':<38} {'task::config':<52} rep  {'accept':<9} "
             f"{'hidden':<8} {'diff':>7}  truncated"]
    for r in rows:
        lines.append(
            f"{r['dataset']:<38} {r['cell']:<52} {r['rep']:>3}  "
            f"{str(r['acceptance']):<9} {str(r['hidden']['status']):<8} "
            f"{'-' if r['diff_bytes'] is None else r['diff_bytes']:>7}  "
            f"{r['truncated'] or ''}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results_root", help="the results/ directory to scan")
    ap.add_argument("--json", action="store_true", help="emit rows as JSON")
    ap.add_argument("--truncated", action="store_true",
                    help="only truncated runs not superseded by a later complete run")
    args = ap.parse_args(argv)

    rows = scan(args.results_root)
    if args.truncated:
        rows = needs_makeup(rows)
    if args.json:
        json.dump(rows, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print(_fmt_table(rows))
        print(f"\n{len(rows)} run(s)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
