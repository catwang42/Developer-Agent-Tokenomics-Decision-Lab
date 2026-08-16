"""Decision table: per task × configuration/policy summary for one results batch.

Reads a batch directory of run records (``results/feasibility-batchN/``, and any future
``results/screening-batchN/``) and emits the pair that the Phase-5 report page consumes:

    <out-dir>/decision-table.json    the data contract (stable keys, machine-readable)
    <out-dir>/decision-table.md      the same content as a reviewable table

For every (task_id, configuration_id) cell it reports:

  * **acceptance** — accepted/n from the pre-registered gate (SPEC §2.6)
  * **ECST** under both cost views, plus the per-run attempt-cost median [min–max]
  * **tokens per accepted outcome, by token class** — fresh input, cache-write,
    cache-read, output, reasoning, tool-result
  * **wall-clock** median [min–max], derived from the event log
  * **HEAC** with the reviewer verdict where a timed review exists

Rules this module enforces (CLAUDE.md rules 1–4, SPEC §2.7):

  * **No zero-fills.** A missing field is ``unavailable`` with a reason, never 0.
  * **Every figure carries a confidence tier** — authoritative / derived /
    proxy_observed / unavailable — and a derived figure inherits the weakest tier of
    its inputs. A sum over a cell where some runs lack the field is a ``*_floor``:
    a known lower bound, explicitly labelled, never presented as complete.
  * **Every figure carries an n/scope line** — n runs, n accepted, cost basis, pricing
    snapshot, cache state, task-suite version. A number without its scope line is not
    portable.
  * **Nothing here is a vendor claim.** Cells sit side by side; the table never ranks
    configurations, never merges the three views of SPEC §2.1, and never crosses a
    product boundary in one figure.

Governance: the emitted STATUS banner is ``PENDING`` unless told otherwise. No figure
produced here may appear in docs, on the site, or in an external-facing report before
**CP-FINDINGS** (CLAUDE.md checkpoint table).

Run::

    python -m harness.telemetry.summarize results/feasibility-batch3
    python -m harness.telemetry.summarize results/feasibility-batch3 --out-dir /tmp/dt
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics as st
import sys
from typing import Any, Dict, List, Optional, Tuple

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:  # allow `python harness/telemetry/summarize.py` as well
    sys.path.insert(0, _REPO)

from harness.evaluator.metrics import (  # noqa: E402
    ecst as cell_ecst,
    loaded_rate_from_manifest,
    run_total,
)

SCHEMA = "decision-table-v1"

AUTHORITATIVE, DERIVED, PROXY, UNAVAILABLE = (
    "authoritative", "derived", "proxy_observed", "unavailable")
UNDEFINED = "undefined"

#: weakest-wins ordering for inherited confidence tiers
_TIER_RANK = {AUTHORITATIVE: 0, DERIVED: 1, PROXY: 2, UNAVAILABLE: 3}

TOKEN_CLASSES = [
    ("input_tokens", "fresh input"),
    ("cache_creation_tokens", "cache write"),
    ("cache_read_tokens", "cache read"),
    ("output_tokens", "output"),
    ("reasoning_tokens", "reasoning"),
    ("tool_result_tokens", "tool result"),
]

BANNER = (
    "NON-COMPARATIVE / INTERNAL — descriptive per-cell figures only. No cross-product "
    "or cross-configuration ranking, no vendor claim, no model-efficiency attribution "
    "(CLAUDE.md rule 4, SPEC §1.2). Cells from different products are different views "
    "(SPEC §2.1) and never merge into one comparison."
)

CP_FINDINGS_NOTE = (
    "No figure in this table may appear in docs, on the site, or in any external-facing "
    "report before **CP-FINDINGS**."
)


# --------------------------------------------------------------------------- helpers

def _num(v: Any) -> Optional[float]:
    """Return v as a float if it is a real number (bools are not numbers)."""
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _weakest(tiers: List[str]) -> str:
    return max(tiers, key=lambda t: _TIER_RANK.get(t, _TIER_RANK[UNAVAILABLE])) \
        if tiers else UNAVAILABLE


def _field(container: Dict[str, Any], key: str) -> Tuple[Optional[float], str, Optional[str]]:
    """Unpack a telemetry ``{value, confidence, reason}`` slot -> (value, tier, reason)."""
    slot = container.get(key)
    if not isinstance(slot, dict):
        return _num(slot), (AUTHORITATIVE if _num(slot) is not None else UNAVAILABLE), None
    return _num(slot.get("value")), slot.get("confidence") or UNAVAILABLE, slot.get("reason")


def _dist(values: List[float], of_runs: int) -> Dict[str, Any]:
    """median [min–max] with "n reporting of n runs". Empty input stays empty — never
    0-filled, and a partial n is always visible next to the total."""
    xs = sorted(v for v in values if v is not None)
    base = {"of_runs": of_runs, "runs_unavailable": of_runs - len(xs)}
    if not xs:
        return {**base, "n": 0, "median": None, "min": None, "max": None,
                "confidence": UNAVAILABLE, "reason": "no run in this cell reported it"}
    return {**base, "n": len(xs), "median": round(st.median(xs), 6),
            "min": round(xs[0], 6), "max": round(xs[-1], 6), "confidence": DERIVED}


def _accepted(summary: Dict[str, Any]) -> bool:
    return (summary.get("acceptance") or {}).get("result") == "accepted"


# ------------------------------------------------------------------------- loading

def load_runs(batch_dir: str) -> List[Dict[str, Any]]:
    """Load ``{summary, wallclock, run_dir}`` for every run directory in the batch.

    Non-directory entries (a batch's own aggregate JSON files) are skipped, as is any
    directory without a ``summary.json``.
    """
    runs: List[Dict[str, Any]] = []
    if not os.path.isdir(batch_dir):
        raise FileNotFoundError(f"batch directory not found: {batch_dir}")
    for name in sorted(os.listdir(batch_dir)):
        run_dir = os.path.join(batch_dir, name)
        summary_path = os.path.join(run_dir, "summary.json")
        if not os.path.isfile(summary_path):
            continue
        with open(summary_path, encoding="utf-8") as fh:
            summary = json.load(fh)
        runs.append({"run_dir": run_dir, "run_id": name, "summary": summary,
                     "wallclock_s": wallclock_seconds(run_dir)})
    return runs


def wallclock_seconds(run_dir: str) -> Dict[str, Any]:
    """End-to-end wall-clock for one run, derived from the event log's timestamps.

    First to last event in ``events.jsonl``. Derived tier: the harness stamps the
    events, so the span is a real observation, but it is computed rather than reported
    by the product. No event log, or fewer than two timestamps, is ``unavailable``.
    """
    path = os.path.join(run_dir, "events.jsonl")
    if not os.path.isfile(path):
        return {"value": None, "confidence": UNAVAILABLE, "reason": "no events.jsonl"}
    stamps: List[dt.datetime] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ts = json.loads(line).get("ts")
                if ts:
                    stamps.append(dt.datetime.fromisoformat(ts))
            except (json.JSONDecodeError, ValueError):
                continue
    if len(stamps) < 2:
        return {"value": None, "confidence": UNAVAILABLE,
                "reason": "fewer than two timestamped events"}
    return {"value": round((max(stamps) - min(stamps)).total_seconds(), 3),
            "confidence": DERIVED, "basis": "first to last event timestamp"}


# ------------------------------------------------------------------------- metrics

def tokens_per_accepted(runs: List[Dict[str, Any]], token_key: str) -> Dict[str, Any]:
    """Tokens of one class across ALL attempts, divided by accepted outcomes.

    All attempts count — a failed attempt's tokens are charged to the cell that spent
    them, never dropped. If some runs expose the class and others do not, the numerator
    is a known floor (``derived_floor``); if none expose it, the figure is
    ``unavailable``; if the cell accepted nothing, it is ``undefined`` (dividing by zero
    accepted outcomes has no honest value).
    """
    n_accepted = sum(1 for r in runs if _accepted(r["summary"]))
    total = 0.0
    tiers: List[str] = []
    n_known = 0
    n_unavail = 0
    for r in runs:
        value, tier, _ = _field(r["summary"].get("usage") or {}, token_key)
        if value is None:
            n_unavail += 1
        else:
            total += value
            n_known += 1
            tiers.append(tier)
    base = {"n_runs": len(runs), "n_accepted": n_accepted,
            "runs_reporting": n_known, "runs_unavailable": n_unavail}
    if n_known == 0:
        return {**base, "value": None, "total_tokens": None, "status": UNAVAILABLE,
                "confidence": UNAVAILABLE,
                "reason": "this token class is not exposed by this configuration"}
    if n_accepted == 0:
        return {**base, "value": None, "total_tokens": int(total), "status": UNDEFINED,
                "confidence": _weakest(tiers),
                "reason": "0 accepted outcomes in cell — no per-accepted figure exists"}
    return {**base, "value": round(total / n_accepted, 1), "total_tokens": int(total),
            "status": ("derived_floor" if n_unavail else DERIVED),
            "confidence": _weakest(tiers + [DERIVED]),
            **({"reason": f"{n_unavail} of {len(runs)} run(s) do not expose this class — "
                          f"the figure is a known floor"} if n_unavail else {})}


def heac(cell_ecst_result: Dict[str, Any], runs: List[Dict[str, Any]],
         rate: Optional[float]) -> Dict[str, Any]:
    """HEAC = ECST + (active + review + correction minutes × declared loaded rate).

    Blocked minutes are reported separately and never monetized (SPEC §2.4, no FTE
    conversion). Reviewer verdicts travel with the figure: the gate and the reviewer are
    different judgments, and a cell can be gate-accepted and would-not-merge at once.
    """
    minutes = 0.0
    blocked = 0.0
    reviewed: List[str] = []
    verdicts: Dict[str, int] = {}
    reviewers: List[str] = []
    for r in runs:
        he = r["summary"].get("human_effort") or {}
        got = False
        for key in ("active_minutes", "review_minutes", "correction_minutes"):
            value, _, _ = _field(he, key)
            if value is not None:
                minutes += value
                got = True
        blocked_v, _, _ = _field(he, "blocked_minutes")
        if blocked_v is not None:
            blocked += blocked_v
        verdict_slot = he.get("reviewer_verdict")
        verdict = verdict_slot.get("value") if isinstance(verdict_slot, dict) else verdict_slot
        if verdict:
            verdicts[verdict] = verdicts.get(verdict, 0) + 1
        reviewer_slot = he.get("reviewer")
        reviewer = reviewer_slot.get("value") if isinstance(reviewer_slot, dict) else reviewer_slot
        if reviewer and reviewer not in reviewers:
            reviewers.append(reviewer)
        if got:
            reviewed.append(r["run_id"])
    base = {"n_runs": len(runs), "n_reviewed": len(reviewed),
            "reviewer_verdicts": verdicts or None,
            "reviewers": reviewers or None,
            "human_minutes": round(minutes, 3) if reviewed else None,
            "blocked_minutes_not_monetized": round(blocked, 3) if reviewed else None}
    if not reviewed:
        return {**base, "value": None, "status": UNAVAILABLE, "confidence": UNAVAILABLE,
                "reason": "no timed human review recorded for this cell",
                "model_component": cell_ecst_result.get("value")}
    if rate is None:
        return {**base, "value": None, "status": UNAVAILABLE, "confidence": UNAVAILABLE,
                "reason": "loaded_rate_per_minute not declared in the manifest",
                "model_component": cell_ecst_result.get("value")}
    if cell_ecst_result.get("value") is None:
        return {**base, "value": None, "status": cell_ecst_result.get("status", UNAVAILABLE),
                "confidence": UNAVAILABLE, "reason": "ECST component not defined"}
    return {**base,
            "value": round(cell_ecst_result["value"] + minutes * rate, 6),
            "status": ("derived_floor" if cell_ecst_result.get("attempt_cost_is_floor")
                       else DERIVED),
            "confidence": DERIVED,
            "loaded_rate_usd_per_min": rate,
            "model_component": cell_ecst_result.get("value")}


def _scope(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The n/scope line: what these figures are conditioned on."""
    def collect(getter) -> List[str]:
        seen: List[str] = []
        for r in runs:
            try:
                v = getter(r["summary"])
            except (AttributeError, KeyError, TypeError):
                v = None
            if v and v not in seen:
                seen.append(str(v))
        return seen

    n_accepted = sum(1 for r in runs if _accepted(r["summary"]))
    return {
        "n_runs": len(runs),
        "n_accepted": n_accepted,
        "model_or_selector": collect(lambda s: (s["identity"]["model_or_selector"] or {}).get("value")),
        "product": collect(lambda s: (s["identity"]["product"] or {}).get("value")),
        "cache_state": collect(lambda s: (s["identity"]["cache_state"] or {}).get("value")),
        "contamination_tier": collect(lambda s: s["identity"].get("contamination_tier")),
        "task_suite_version": collect(lambda s: s.get("task_suite_version")),
        "cost_basis": collect(lambda s: s["economics"].get("cost_basis")),
        "pricing_snapshot": collect(lambda s: s["economics"].get("pricing_snapshot")),
        "hidden_test_hash": collect(lambda s: s.get("hidden_test_hash")),
        "manifest_ref": collect(lambda s: s.get("manifest_ref")),
    }


def _scope_line(scope: Dict[str, Any]) -> str:
    def one(key: str, label: str) -> Optional[str]:
        vals = scope.get(key) or []
        return f"{label} {'/'.join(vals)}" if vals else None
    parts = [f"n={scope['n_runs']} run(s), {scope['n_accepted']} accepted"]
    for key, label in (("cache_state", "cache"), ("cost_basis", "basis"),
                       ("pricing_snapshot", "prices"), ("task_suite_version", "suite"),
                       ("contamination_tier", "contamination")):
        got = one(key, label)
        if got:
            parts.append(got)
    return "; ".join(parts)


def build_cell(task: str, config: str, runs: List[Dict[str, Any]],
               rate: Optional[float]) -> Dict[str, Any]:
    summaries = [r["summary"] for r in runs]
    n_accepted = sum(1 for s in summaries if _accepted(s))
    acceptance_breakdown: Dict[str, int] = {}
    for s in summaries:
        res = (s.get("acceptance") or {}).get("result") or "other"
        acceptance_breakdown[res] = acceptance_breakdown.get(res, 0) + 1

    e_marginal = cell_ecst(summaries, "marginal")
    e_allocated = cell_ecst(summaries, "fully")

    attempt_costs = [t for t in (run_total(s, "marginal")[0] for s in summaries)
                     if t is not None]
    wallclocks = [r["wallclock_s"]["value"] for r in runs
                  if r["wallclock_s"]["value"] is not None]

    scope = _scope(runs)
    return {
        "task_id": task,
        "configuration_or_policy": config,
        "n_runs": len(runs),
        "acceptance": {
            "accepted": n_accepted,
            "of": len(runs),
            "display": f"{n_accepted}/{len(runs)}",
            "breakdown": acceptance_breakdown,
            "confidence": AUTHORITATIVE,
            "basis": "pre-registered deterministic-first gate (SPEC §2.6)",
        },
        "ecst": {
            "marginal_operating_usd": e_marginal,
            "fully_allocated_usd": e_allocated,
            "attempt_cost_usd": _dist(attempt_costs, len(runs)),
        },
        "tokens_per_accepted_outcome": {
            key: tokens_per_accepted(runs, key) for key, _ in TOKEN_CLASSES
        },
        "wallclock_s": {
            **_dist(wallclocks, len(runs)),
            "basis": "first to last event-log timestamp",
        },
        "heac": heac(e_marginal, runs, rate),
        "scope": scope,
        "scope_line": _scope_line(scope),
    }


def build(batch_dir: str, manifest_path: Optional[str] = None,
          status: str = "PENDING") -> Dict[str, Any]:
    """Build the full decision table for one batch directory."""
    runs = load_runs(batch_dir)
    manifest_path = manifest_path or os.path.join(_REPO, "manifest", "delivery-manifest.yaml")
    rate = loaded_rate_from_manifest(manifest_path)

    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for r in runs:
        key = (r["summary"].get("task_id") or "?",
               r["summary"].get("configuration_id") or "?")
        grouped.setdefault(key, []).append(r)

    cells = [build_cell(task, config, cell_runs, rate)
             for (task, config), cell_runs in sorted(grouped.items())]

    return {
        "schema": SCHEMA,
        "status": status,
        "note": BANNER,
        "cp_findings_gate": CP_FINDINGS_NOTE,
        "source_dataset": os.path.relpath(os.path.abspath(batch_dir), _REPO),
        "manifest_ref": os.path.relpath(os.path.abspath(manifest_path), _REPO),
        "loaded_rate_usd_per_min": rate,
        "n_runs": len(runs),
        "n_cells": len(cells),
        "confidence_tiers": [AUTHORITATIVE, DERIVED, PROXY, UNAVAILABLE],
        "cells": cells,
    }


# ------------------------------------------------------------------------ rendering

def _fmt_usd(slot: Dict[str, Any], key: str = "value") -> str:
    v = slot.get(key)
    return "unavailable" if v is None else f"${v:.4f}"


def _fmt_dist(dist: Dict[str, Any], unit: str = "") -> str:
    """Never hide a partial n: `n=1 of 3` says two runs did not report the field."""
    of_runs = dist.get("of_runs")
    if dist.get("median") is None:
        return f"unavailable (0 of {of_runs} reporting)"
    n_txt = f"n={dist['n']}" if dist["n"] == of_runs else f"n={dist['n']} of {of_runs}"
    return (f"{dist['median']:g}{unit} [{dist['min']:g}–{dist['max']:g}{unit}] "
            f"({n_txt})")


def _fmt_tokens(slot: Dict[str, Any]) -> str:
    if slot.get("value") is None:
        return UNDEFINED if slot.get("status") == UNDEFINED else "unavailable"
    floor = "≥" if slot.get("status") == "derived_floor" else ""
    return f"{floor}{slot['value']:,.0f}"


def render_markdown(table: Dict[str, Any]) -> str:
    L: List[str] = []
    status = table["status"]
    L.append(f"> **STATUS: {status}** — decision table generated by "
             f"`harness/telemetry/summarize.py` from `{table['source_dataset']}`.")
    L.append(f"> {CP_FINDINGS_NOTE}")
    L.append("> NON-COMPARATIVE / INTERNAL: cells sit side by side; this table never "
             "ranks configurations,")
    L.append("> never merges the three views of SPEC §2.1, and makes no vendor or "
             "model-efficiency claim.")
    L.append("")
    L.append("# Decision table")
    L.append("")
    L.append(table["note"])
    L.append("")
    L.append(f"- **Source dataset:** `{table['source_dataset']}` — "
             f"{table['n_runs']} run(s) across {table['n_cells']} cell(s)")
    L.append(f"- **Manifest:** `{table['manifest_ref']}`")
    rate = table["loaded_rate_usd_per_min"]
    L.append(f"- **Loaded rate (HEAC input, declared not measured):** "
             f"{'unavailable' if rate is None else f'${rate:.2f}/min'}")
    L.append("- **Confidence tiers:** authoritative · derived · proxy_observed · "
             "unavailable. A derived figure inherits the weakest tier of its inputs; "
             "`≥` marks a known floor (some runs did not expose the field). "
             "**Unavailable is never zero.**")
    L.append("")

    L.append("## Acceptance, ECST and wall-clock")
    L.append("")
    L.append("| Task | Config/policy | Accepted | ECST marginal | ECST allocated | "
             "Attempt cost median [min–max] | Wall-clock s median [min–max] |")
    L.append("|---|---|---|---|---|---|---|")
    for c in table["cells"]:
        em, ea = c["ecst"]["marginal_operating_usd"], c["ecst"]["fully_allocated_usd"]
        L.append(
            f"| `{c['task_id']}` | **{c['configuration_or_policy']}** "
            f"| {c['acceptance']['display']} "
            f"| {_fmt_usd(em)} ({em['status']}) "
            f"| {_fmt_usd(ea)} ({ea['status']}) "
            f"| {_fmt_dist(c['ecst']['attempt_cost_usd'])} "
            f"| {_fmt_dist(c['wallclock_s'])} |"
        )
    L.append("")

    L.append("## Tokens per accepted outcome, by token class")
    L.append("")
    L.append("All attempts count — a failed attempt's tokens are charged to the cell "
             "that spent them. `≥` is a known floor; `unavailable` means the "
             "configuration does not expose that class.")
    L.append("")
    header = " | ".join(label for _, label in TOKEN_CLASSES)
    L.append(f"| Task | Config/policy | {header} |")
    L.append("|---|---|" + "---|" * len(TOKEN_CLASSES))
    for c in table["cells"]:
        cells_txt = " | ".join(_fmt_tokens(c["tokens_per_accepted_outcome"][key])
                               for key, _ in TOKEN_CLASSES)
        L.append(f"| `{c['task_id']}` | **{c['configuration_or_policy']}** | {cells_txt} |")
    L.append("")

    L.append("## HEAC (human-effort-adjusted cost)")
    L.append("")
    L.append("HEAC = ECST + (active + review + correction minutes × declared loaded "
             "rate). Blocked minutes are reported separately and never monetized; no "
             "FTE conversion (SPEC §2.4). The **gate and the reviewer are different "
             "judgments** — a cell can be gate-accepted and would-not-merge at once.")
    L.append("")
    L.append("| Task | Config/policy | HEAC | Model component | Human min | "
             "Reviewed | Reviewer verdict | Tier |")
    L.append("|---|---|---|---|---|---|---|---|")
    for c in table["cells"]:
        h = c["heac"]
        verdicts = h.get("reviewer_verdicts")
        verdict_txt = ", ".join(f"{k} ×{v}" for k, v in sorted(verdicts.items())) \
            if verdicts else "—"
        mc = h.get("model_component")
        L.append(
            f"| `{c['task_id']}` | **{c['configuration_or_policy']}** "
            f"| {_fmt_usd(h)} "
            f"| {'unavailable' if mc is None else f'${mc:.4f}'} "
            f"| {h.get('human_minutes') if h.get('human_minutes') is not None else '—'} "
            f"| {h.get('n_reviewed', 0)}/{h.get('n_runs', 0)} "
            f"| {verdict_txt} "
            f"| {h.get('confidence')} |"
        )
    L.append("")

    L.append("## Scope lines")
    L.append("")
    L.append("Every figure above is conditioned on these. A number without its scope "
             "line is not portable — including ours.")
    L.append("")
    L.append("The exact selectors below are **internal provenance** (SPEC §6.3 requires "
             "recording what was actually invoked). Replace them with the placeholder "
             "labels — Product A/B, STRONG_MODEL_A… — in any external-facing render "
             "(CLAUDE.md rule 7).")
    L.append("")
    for c in table["cells"]:
        L.append(f"- **`{c['task_id']}` · {c['configuration_or_policy']}** — "
                 f"{c['scope_line']}")
        models = c["scope"].get("model_or_selector") or []
        if models:
            L.append(f"  - selector: {', '.join(f'`{m}`' for m in models)}")
    L.append("")
    return "\n".join(L)


# ------------------------------------------------------------------------------ CLI

def default_out_dir(batch_dir: str) -> Optional[str]:
    """``results/feasibility-batch3`` -> ``report/batch3``; ``results/screening-batch1``
    -> ``report/screening-batch1`` (CLAUDE.md rule 8 pairing)."""
    name = os.path.basename(os.path.normpath(batch_dir))
    if name.startswith("feasibility-batch"):
        return os.path.join(_REPO, "report", name[len("feasibility-"):])
    if name.startswith("screening-batch"):
        return os.path.join(_REPO, "report", name)
    return None


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Emit decision-table.json + decision-table.md for one results batch")
    ap.add_argument("batch_dir", help="e.g. results/feasibility-batch3")
    ap.add_argument("--out-dir", default=None,
                    help="output directory (default: the paired report/ directory)")
    ap.add_argument("--manifest", default=None,
                    help="delivery manifest supplying the HEAC loaded rate")
    ap.add_argument("--status", default="PENDING",
                    choices=["PENDING", "AUTHORITATIVE", "SUPERSEDED"],
                    help="STATUS banner for the emitted report (default: PENDING)")
    ap.add_argument("--stdout", action="store_true",
                    help="print the markdown instead of writing files")
    args = ap.parse_args(argv)

    table = build(args.batch_dir, args.manifest, args.status)
    markdown = render_markdown(table)

    if args.stdout:
        print(markdown)
        return 0

    out_dir = args.out_dir or default_out_dir(args.batch_dir)
    if not out_dir:
        ap.error(f"cannot derive a paired report directory for {args.batch_dir!r} — "
                 f"pass --out-dir explicitly")
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "decision-table.json")
    md_path = os.path.join(out_dir, "decision-table.md")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(table, fh, indent=2, sort_keys=True)
        fh.write("\n")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(markdown)
    print(f"wrote {json_path}", file=sys.stderr)
    print(f"wrote {md_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
