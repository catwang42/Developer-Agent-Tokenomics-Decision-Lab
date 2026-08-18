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
  * **per-leg rows** — one row per (leg, role, model) so a delegation or escalation
    arm shows an itemized bill instead of a single blended number

Screening batches additionally get (all three added for screening-batch1):

  * **the task registry and arm map** — task class and registered arms read from each
    ``tasks/**/task.yaml``, which is what CP-SCREEN-PREREG registered (P1 on W3 only,
    P2 on F1/F3, C5 everywhere but W6). Nothing here re-declares the matrix.
  * **arm coverage** — registered vs observed arms per task, so a missing cell reads
    as *not run* rather than silently vanishing, and an unregistered cell is named.
  * **pre-registration grading** — the H-effort C3 vs C3-med delta against the
    registered 30–50% band, and the W3 escalation outcome against its registered
    failure prediction. Both are graded from run data only, both publish either way,
    and a cell outside a registration's declared scope is reported as *exploratory,
    not graded* rather than folded into a score.

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

SCHEMA = "decision-table-v2"

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

SCREENING_NOTE = (
    "Screening is hypothesis-seeking positioning evidence (SPEC §5): one task is a "
    "signal about that task, never a workload-class claim. Promoting anything here to "
    "a class-level finding requires a second, materially different task from the same "
    "class (SPEC §5.2), and no screening result is independently publishable."
)

#: Structured parameters of each human-authored pre-registration under
#: ``manifest/preregistrations/``. Only the *machine-gradable* terms live here — the
#: prose registration is the authority and is never rewritten by this module.
#: ``tests/test_summarize.py`` asserts every value below still appears in its file, so
#: the constant cannot drift away from what was registered.
PREREGISTRATIONS: Dict[str, Dict[str, Any]] = {
    "h_effort": {
        "id": "H-effort",
        "file": "manifest/preregistrations/2026-08-16-H-effort.md",
        "registered": "2026-08-16",
        "arms": ["C3", "C3-med"],
        "prediction": (
            "The economical product's Medium effort level passes the same gates as "
            "High on routine tasks while consuming materially fewer tokens — expected "
            "cost-per-accepted-outcome reduction ~30-50%."),
        "predicted_reduction_pct": {"low": 30.0, "high": 50.0},
        "scope_excludes_task_classes": ["complex_bugfix", "code_review"],
        "scope_note": (
            "The prediction covers task classes comparable to prior informal use. No "
            "prediction is registered for the harder screening tasks (complex "
            "multi-file bugfix, W6 PR review) — those cells are exploratory for the "
            "effort panel and are reported without a verdict."),
        "attribution_note": (
            "Effort levels are not label-separable in provider telemetry; the C3 vs "
            "C3-med split rests on serialized run windows. Cost basis "
            "cache_blind_upper_bound on both arms — direction-neutral for this "
            "within-product comparison."),
        "publish_either_way": True,
    },
    "w3_escalation": {
        "id": "W3-escalation-probe",
        "file": "manifest/preregistrations/2026-08-17-W3-escalation-probe.md",
        "registered": "2026-08-17",
        "arms": ["C2", "P1"],
        "prediction": (
            "The economical tier fails the migration task's full gate — most likely on "
            "the parity or call-site-rewiring requirement — causing P1 to escalate to "
            "the strong tier, with both legs billed."),
        "probe_arm": "P1",
        "economical_arm": "C2",
        "selection_note": (
            "The task was DELIBERATELY selected as a difficulty probe under the "
            "anti-selection-bias protocol (SPEC §5.1). A pass refutes the prediction "
            "and is reported as such; a fail is reported without being retro-fitted "
            "into a capability or vendor-superiority claim."),
        "publish_either_way": True,
    },
}


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


# ------------------------------------------------- task registry and the arm map

#: directories never descended into when reading task definitions. ``hidden/`` holds
#: sealed human-held tests and is off limits to every tool in the harness.
_TASK_WALK_SKIP = {"hidden", ".work", "__pycache__", "node_modules", ".git"}


def load_task_registry(tasks_root: Optional[str] = None,
                       arm_key: str = "configurations") -> Dict[str, Dict[str, Any]]:
    """``task_id -> {task_class, registered_arms, …}`` read from ``tasks/**/task.yaml``.

    Those files are the registered matrix: CP-SCREEN-PREREG registered the arms per
    *task* (P1 on the migration probe only, P2 on two tasks, C5 everywhere except the
    PR-review task), and ``tests/test_tasks.py`` pins each declaration to
    ``manifest/cp-screen-prereg.md``. This module therefore reads the arm map rather
    than re-declaring it — a second copy would be a second thing to drift.

    ``arm_key`` selects which declaration is the yardstick — see :func:`arm_key_for`.
    Sealed ``hidden/`` directories are never descended into.
    """
    import yaml
    root = tasks_root or os.path.join(_REPO, "tasks")
    registry: Dict[str, Dict[str, Any]] = {}
    if not os.path.isdir(root):
        return registry
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _TASK_WALK_SKIP]
        if "task.yaml" not in filenames:
            continue
        with open(os.path.join(dirpath, "task.yaml"), encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        task_id = doc.get("task_id")
        if not task_id:
            continue
        registry[task_id] = {
            "task_id": task_id,
            "label": os.path.basename(dirpath),
            "task_dir": os.path.relpath(dirpath, _REPO),
            "task_class": doc.get("class") or "unclassified",
            "task_suite_version": doc.get("task_suite_version"),
            "contamination_tier": doc.get("contamination_tier"),
            "registered_arms": [str(a) for a in (doc.get(arm_key) or [])],
            "companion_arms": [str(a) for a in
                               (doc.get("companion_configurations") or [])],
            "arm_key": arm_key,
        }
    return registry


def arm_key_for(batch_dir: str) -> str:
    """Which declaration in ``task.yaml`` is the yardstick for this batch.

    A feasibility dataset is measured against the controlled feasibility set it was
    actually planned under (``feasibility_configurations``); a screening dataset is
    measured against the CP-SCREEN-PREREG matrix (``configurations``). Grading a
    2026-07 feasibility batch against a 2026-08 screening registration would invent
    coverage gaps that were never planned — the same split ``tests/test_tasks.py``
    makes when it checks batch-2 undeclared runs.
    """
    name = os.path.basename(os.path.normpath(batch_dir))
    return "feasibility_configurations" if name.startswith("feasibility") \
        else "configurations"


def arm_coverage(registry: Dict[str, Dict[str, Any]],
                 observed: Dict[str, List[str]]) -> Dict[str, Any]:
    """Registered arms vs the arms this dataset actually contains.

    A registered arm with no runs is ``missing`` — *not run yet*, which is a different
    statement from "ran and produced nothing", and the report page must be able to say
    which. An arm present in the data but absent from the task's declaration is
    ``unregistered`` and named loudly: under the anti-selection-bias protocol
    (SPEC §5) an unplanned arm is a finding about the run, not a bonus data point.
    """
    by_task: Dict[str, Any] = {}
    for task_id, entry in sorted(registry.items()):
        seen = sorted(set(observed.get(task_id, [])))
        registered = entry["registered_arms"]
        companions = entry.get("companion_arms") or []
        by_task[task_id] = {
            "task_class": entry["task_class"],
            "registered": registered,
            "companion": companions,
            "observed": seen,
            "missing": [a for a in registered if a not in seen],
            "companion_observed": [a for a in seen if a in companions],
            "unregistered": [a for a in seen
                             if a not in registered and a not in companions],
        }
    unknown = sorted(t for t in observed if t not in registry)
    keys = sorted({e.get("arm_key", "configurations") for e in registry.values()})
    return {
        "source": "tasks/**/task.yaml: " + ", ".join(keys) if keys
                  else "tasks/**/task.yaml",
        "arm_key": keys[0] if len(keys) == 1 else None,
        "by_task": by_task,
        "tasks_not_in_registry": unknown,
        "complete": all(not v["missing"] and not v["unregistered"]
                        for v in by_task.values() if v["observed"]) and not unknown,
    }


# ------------------------------------------------------------------- per-leg rows

def leg_rows(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """One row per (leg, role) across the cell — the itemized bill.

    A delegation arm (conductor + executor) and an escalation arm (economical attempt
    + strong retry) both bill twice for one outcome. A single blended number hides
    exactly the thing those arms exist to measure, and it also hides the common honest
    case where one leg's cost is ``unavailable`` while the other's is known. Rows are
    emitted for every cell; single-leg cells simply have one row.
    """
    order: List[Tuple[str, str]] = []
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for r in runs:
        for leg in r["summary"].get("legs") or []:
            key = (str(leg.get("leg_id") or "?"), str(leg.get("role") or "?"))
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            grouped[key].append(leg)

    rows = []
    for key in order:
        legs = grouped[key]
        costs, tiers = [], []
        models: List[str] = []
        providers: List[str] = []
        bases: List[str] = []
        for leg in legs:
            value, tier, _ = _field(leg, "marginal_operating_usd")
            if value is None:
                tiers.append(UNAVAILABLE)
            else:
                costs.append(value)
                tiers.append(tier)
            for field, sink in (("model_or_selector", models), ("provider", providers)):
                slot = leg.get(field)
                got = slot.get("value") if isinstance(slot, dict) else slot
                if got and got not in sink:
                    sink.append(str(got))
            basis = leg.get("cost_basis")
            if basis and basis not in bases:
                bases.append(str(basis))
        usage_totals = {}
        for token_key, _ in TOKEN_CLASSES:
            total, known, unknown = 0.0, 0, 0
            for leg in legs:
                value, _, _ = _field(leg.get("usage") or {}, token_key)
                if value is None:
                    unknown += 1
                else:
                    total += value
                    known += 1
            usage_totals[token_key] = (
                {"value": None, "status": UNAVAILABLE, "confidence": UNAVAILABLE,
                 "legs_reporting": 0, "legs_unavailable": unknown,
                 "reason": "this leg does not expose this token class"}
                if known == 0 else
                {"value": int(total),
                 "status": ("derived_floor" if unknown else DERIVED),
                 "confidence": DERIVED,
                 "legs_reporting": known, "legs_unavailable": unknown})
        rows.append({
            "leg_id": key[0],
            "role": key[1],
            "n_legs": len(legs),
            "model_or_selector": models,
            "provider": providers,
            "cost_basis": bases,
            "marginal_operating_usd": _dist(costs, len(legs)),
            "legs_cost_unavailable": len(legs) - len(costs),
            "confidence": _weakest(tiers),
            "usage_totals": usage_totals,
        })
    return {
        "rows": rows,
        "is_multi_leg": len(rows) > 1,
        "basis": ("per-leg figures come from the run summary's `legs[]`; a leg whose "
                  "cost the product does not expose stays unavailable and is never "
                  "back-filled from the other leg"),
    }


# ------------------------------------------------------- pre-registration grading

def _cell_ecst_value(cell: Optional[Dict[str, Any]]) -> Tuple[Optional[float], str]:
    if not cell:
        return None, UNAVAILABLE
    slot = cell["ecst"]["marginal_operating_usd"]
    return slot.get("value"), slot.get("status", UNAVAILABLE)


def grade_h_effort(cells: Dict[Tuple[str, str], Dict[str, Any]],
                   registry: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """C3 vs C3-med cost-per-accepted-outcome delta against the registered band.

    Two things are graded, because the registration predicted two: that Medium passes
    *the same gates* (parity), and that it costs 30–50% less per accepted outcome. A
    cheaper arm that fails gates the other arm passed does not support the prediction,
    so parity is checked first and can refute on its own.

    Tasks in a class the registration explicitly excluded are reported as exploratory
    and carry no verdict — grading them anyway would silently widen a registration
    after the fact, which is the exact move the anti-selection-bias protocol forbids.
    """
    reg = PREREGISTRATIONS["h_effort"]
    low, high = (reg["predicted_reduction_pct"]["low"],
                 reg["predicted_reduction_pct"]["high"])
    strong_arm, cheap_arm = reg["arms"]

    by_task = []
    for task_id in sorted({t for (t, _) in cells}):
        entry = registry.get(task_id, {})
        task_class = entry.get("task_class", "unclassified")
        strong = cells.get((task_id, strong_arm))
        cheap = cells.get((task_id, cheap_arm))
        strong_v, strong_status = _cell_ecst_value(strong)
        cheap_v, cheap_status = _cell_ecst_value(cheap)

        def acc(cell):
            return (None if not cell else
                    {"accepted": cell["acceptance"]["accepted"],
                     "of": cell["acceptance"]["of"],
                     "display": cell["acceptance"]["display"]})

        row: Dict[str, Any] = {
            "task_id": task_id,
            "task_class": task_class,
            "in_registered_scope": task_class not in reg["scope_excludes_task_classes"],
            "arms": {strong_arm: {"ecst_usd": strong_v, "status": strong_status,
                                  "acceptance": acc(strong),
                                  "scope_line": strong["scope_line"] if strong else None},
                     cheap_arm: {"ecst_usd": cheap_v, "status": cheap_status,
                                 "acceptance": acc(cheap),
                                 "scope_line": cheap["scope_line"] if cheap else None}},
        }

        if not row["in_registered_scope"]:
            row["verdict"] = "exploratory_not_graded"
            row["reason"] = reg["scope_note"]
        elif strong is None or cheap is None:
            row["verdict"] = "not_gradable"
            row["reason"] = (f"the pair is incomplete in this dataset: "
                             f"{'no ' + strong_arm + ' runs; ' if strong is None else ''}"
                             f"{'no ' + cheap_arm + ' runs' if cheap is None else ''}"
                             .strip().rstrip(";"))
        elif strong_v is None or cheap_v is None:
            row["verdict"] = "not_gradable"
            row["reason"] = ("cost per accepted outcome is not available for both arms "
                             "— an unavailable cost is never treated as zero")
        else:
            reduction = (strong_v - cheap_v) / strong_v * 100.0 if strong_v else None
            row["delta"] = {
                "reduction_pct": None if reduction is None else round(reduction, 2),
                "predicted_band_pct": {"low": low, "high": high},
                "confidence": DERIVED,
                "basis": "ECST marginal-operating, both arms, same tasks and gates",
            }
            parity = (cheap["acceptance"]["accepted"] >= strong["acceptance"]["accepted"])
            row["gate_parity"] = {
                "holds": parity,
                "basis": f"{cheap_arm} accepted {cheap['acceptance']['display']} vs "
                         f"{strong_arm} {strong['acceptance']['display']}",
            }
            if not parity:
                row["verdict"] = "gate_parity_refuted"
            elif reduction is None:
                row["verdict"] = "not_gradable"
                row["reason"] = f"{strong_arm} cost per accepted outcome is 0 — no ratio"
            elif reduction < 0:
                row["verdict"] = "direction_refuted"
            elif reduction < low:
                row["verdict"] = "below_predicted_band"
            elif reduction <= high:
                row["verdict"] = "within_predicted_band"
            else:
                row["verdict"] = "above_predicted_band"
        by_task.append(row)

    tally: Dict[str, int] = {}
    for row in by_task:
        tally[row["verdict"]] = tally.get(row["verdict"], 0) + 1
    graded = [r for r in by_task if r["verdict"] not in
              ("exploratory_not_graded", "not_gradable")]
    return {
        "registration": reg,
        "arms": [strong_arm, cheap_arm],
        "by_task": by_task,
        "verdict_tally": tally,
        "n_graded": len(graded),
        "status": ("no_data" if not graded else
                   "partial" if len(graded) < len(by_task) else "complete"),
        "note": ("Published either way, per the registration. A per-task verdict is a "
                 "signal about that task under these pinned conditions; it is not a "
                 "workload-class claim and not a product claim."),
    }


def grade_w3_escalation(cells: Dict[Tuple[str, str], Dict[str, Any]],
                        runs_by_cell: Dict[Tuple[str, str], List[Dict[str, Any]]],
                        registry: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Did the economical tier fail the probe task's gate, and did P1 then escalate?

    The probe task is *derived* from the arm map — it is the task whose registered arms
    include the escalation policy — so this grader follows the registration instead of
    hardcoding a task id. Two independent observations are reported separately: whether
    the economical solo arm cleared the gate, and whether the escalation branch fired.
    They can disagree, and when they do the outcome is ``mixed``, never rounded to a
    tidy supported/refuted.
    """
    reg = PREREGISTRATIONS["w3_escalation"]
    probe_arm, cheap_arm = reg["probe_arm"], reg["economical_arm"]
    probe_tasks = sorted(t for t, e in registry.items()
                         if probe_arm in e["registered_arms"])

    base = {"registration": reg, "probe_arm": probe_arm,
            "economical_arm": cheap_arm, "probe_tasks": probe_tasks}
    if len(probe_tasks) != 1:
        return {**base, "outcome": "not_gradable",
                "reason": (f"the arm map names {len(probe_tasks)} task(s) carrying "
                           f"{probe_arm}; the registration designates exactly one probe")}
    task_id = probe_tasks[0]
    cheap_cell = cells.get((task_id, cheap_arm))
    probe_cell = cells.get((task_id, probe_arm))

    trace = []
    escalated_runs = 0
    for run in runs_by_cell.get((task_id, probe_arm), []):
        summary = run["summary"]
        escalations, esc_tier, esc_reason = _field(summary.get("behavior") or {},
                                                   "escalations")
        acceptance = summary.get("acceptance") or {}
        fired = bool(escalations)
        escalated_runs += 1 if fired else 0
        trace.append({
            "run_id": run["run_id"],
            "escalations": {"value": (None if escalations is None else int(escalations)),
                            "confidence": esc_tier,
                            **({"reason": esc_reason} if esc_reason else {})},
            "escalation_fired": (None if escalations is None else fired),
            "intention_to_route": acceptance.get("intention_to_route"),
            "completed_route": acceptance.get("completed_route"),
            "result": acceptance.get("result"),
            "gate_checks": _gate_digest(acceptance),
            "legs": leg_rows([run])["rows"],
        })

    economical_gate = "no_data"
    if cheap_cell:
        accepted, of = cheap_cell["acceptance"]["accepted"], cheap_cell["acceptance"]["of"]
        economical_gate = ("failed" if accepted == 0 else
                           "passed" if accepted == of else "mixed")
    escalation = ("no_data" if not trace else
                  "observed" if escalated_runs else "not_observed")

    if economical_gate == "no_data" and escalation == "no_data":
        outcome, why = "not_yet_run", "no runs of either arm in this dataset"
    elif economical_gate == "failed" and escalation == "observed":
        outcome, why = "prediction_supported", (
            "the economical solo arm cleared no run of the gate and the escalation "
            "branch fired")
    elif economical_gate == "passed" and escalation == "not_observed":
        outcome, why = "prediction_refuted", (
            "the economical tier passed the gate on every run and the escalation "
            "branch never fired — the registered null result")
    else:
        outcome, why = "mixed", (
            f"economical-tier gate: {economical_gate}; escalation branch: {escalation} "
            f"({escalated_runs} of {len(trace)} probe run(s)) — reported as observed, "
            f"not resolved to a single verdict")

    return {
        **base,
        "task_id": task_id,
        "task_class": registry[task_id]["task_class"],
        "economical_solo": (None if not cheap_cell else
                            {"acceptance": cheap_cell["acceptance"]["display"],
                             "ecst_usd": cheap_cell["ecst"]["marginal_operating_usd"],
                             "scope_line": cheap_cell["scope_line"]}),
        "economical_tier_gate": economical_gate,
        "escalation_branch": escalation,
        "n_probe_runs": len(trace),
        "n_escalated": escalated_runs,
        "probe_cell": (None if not probe_cell else
                       {"acceptance": probe_cell["acceptance"]["display"],
                        "ecst_usd": probe_cell["ecst"]["marginal_operating_usd"],
                        "legs": probe_cell["legs"],
                        "scope_line": probe_cell["scope_line"]}),
        "trace": trace,
        "outcome": outcome,
        "outcome_basis": why,
        "note": ("Published either way. SPEC §2.9 item 3 records that this branch had "
                 "never fired on the earlier suite; whichever way it lands here is a "
                 "statement about this task under these pinned conditions."),
    }


def _gate_digest(acceptance: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten ``acceptance.gate_checks`` into ``[{gate, status, failed:[ids]}]``.

    Hidden-gate *contents* are never touched — only the pass/fail the runner recorded.
    """
    digest = []
    for name, gate in sorted((acceptance.get("gate_checks") or {}).items()):
        if not isinstance(gate, dict):
            continue
        checks = gate.get("checks") or []
        failed = [c.get("id") for c in checks
                  if isinstance(c, dict) and c.get("status") not in (None, "pass")]
        status = gate.get("status")
        if status is None and checks:
            status = "fail" if failed else "pass"
        digest.append({"gate": name, "status": status or "unavailable",
                       "failed_checks": [f for f in failed if f]})
    return digest


def build_cell(task: str, config: str, runs: List[Dict[str, Any]],
               rate: Optional[float], task_class: Optional[str] = None,
               registered_arm: Optional[bool] = None) -> Dict[str, Any]:
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
        "task_class": task_class or "unclassified",
        "configuration_or_policy": config,
        "registered_arm": registered_arm,
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
        "legs": leg_rows(runs),
        "scope": scope,
        "scope_line": _scope_line(scope),
    }


def _task_class_index(cells: List[Dict[str, Any]],
                      registry: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cells grouped by task class — the unit the report page renders a card for.

    Task class is the reporting unit SPEC §2.4 requires (QA-ECST by task class, never
    one suite-wide aggregate without a declared task-mix weighting). Grouping stops at
    the class boundary: classes are listed, never ranked against each other.
    """
    index: Dict[str, Dict[str, Any]] = {}
    for cell in cells:
        klass = cell["task_class"]
        entry = index.setdefault(klass, {"task_class": klass, "tasks": [],
                                         "arms": [], "n_runs": 0, "n_cells": 0})
        if cell["task_id"] not in entry["tasks"]:
            entry["tasks"].append(cell["task_id"])
        if cell["configuration_or_policy"] not in entry["arms"]:
            entry["arms"].append(cell["configuration_or_policy"])
        entry["n_runs"] += cell["n_runs"]
        entry["n_cells"] += 1
    for entry in index.values():
        entry["tasks"].sort()
        entry["arms"].sort()
        entry["task_labels"] = {t: registry.get(t, {}).get("label", t)
                                for t in entry["tasks"]}
    return [index[k] for k in sorted(index)]


def build(batch_dir: str, manifest_path: Optional[str] = None,
          status: str = "PENDING", tasks_root: Optional[str] = None) -> Dict[str, Any]:
    """Build the full decision table for one batch directory."""
    runs = load_runs(batch_dir)
    manifest_path = manifest_path or os.path.join(_REPO, "manifest", "delivery-manifest.yaml")
    rate = loaded_rate_from_manifest(manifest_path)
    arm_key = arm_key_for(batch_dir)
    registry = load_task_registry(tasks_root, arm_key)

    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for r in runs:
        key = (r["summary"].get("task_id") or "?",
               r["summary"].get("configuration_id") or "?")
        grouped.setdefault(key, []).append(r)

    observed: Dict[str, List[str]] = {}
    for task, config in grouped:
        observed.setdefault(task, []).append(config)

    cells = []
    for (task, config), cell_runs in sorted(grouped.items()):
        entry = registry.get(task)
        cells.append(build_cell(
            task, config, cell_runs, rate,
            task_class=(entry or {}).get("task_class"),
            registered_arm=(None if entry is None
                            else config in entry["registered_arms"])))
    by_cell = {(c["task_id"], c["configuration_or_policy"]): c for c in cells}

    return {
        "schema": SCHEMA,
        "status": status,
        "note": BANNER,
        "cp_findings_gate": CP_FINDINGS_NOTE,
        "screening_note": SCREENING_NOTE,
        "source_dataset": os.path.relpath(os.path.abspath(batch_dir), _REPO),
        "manifest_ref": os.path.relpath(os.path.abspath(manifest_path), _REPO),
        "loaded_rate_usd_per_min": rate,
        "n_runs": len(runs),
        "n_cells": len(cells),
        "confidence_tiers": [AUTHORITATIVE, DERIVED, PROXY, UNAVAILABLE],
        "task_registry": registry,
        "arm_coverage": arm_coverage(registry, observed),
        "task_classes": _task_class_index(cells, registry),
        "prereg_grading": {
            "h_effort": grade_h_effort(by_cell, registry),
            "w3_escalation": grade_w3_escalation(by_cell, grouped, registry),
        },
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


def _render_coverage(table: Dict[str, Any]) -> List[str]:
    coverage = table.get("arm_coverage") or {}
    by_task = coverage.get("by_task") or {}
    covered = {t: v for t, v in by_task.items() if v["observed"]}
    if not covered and not coverage.get("tasks_not_in_registry"):
        return []
    L = ["## Arm coverage against the registered matrix", "",
         f"Registered arms come from `{coverage.get('source')}`. **Missing** means the "
         "cell has no runs in this dataset — not run, which is a different statement "
         "from ran-and-produced-nothing. **Unregistered** names an arm this dataset "
         "contains that the task never registered; under the anti-selection-bias "
         "protocol that is a finding about the run, not a bonus data point. "
         "**Companion** arms are declared separately and are not part of the "
         "registered matrix.", "",
         "| Task | Class | Registered | Observed | Missing | Companion | Unregistered |",
         "|---|---|---|---|---|---|---|"]
    for task_id, v in sorted(covered.items()):
        L.append(f"| `{task_id}` | {v['task_class']} "
                 f"| {' '.join(v['registered']) or '—'} "
                 f"| {' '.join(v['observed']) or '—'} "
                 f"| {' '.join(v['missing']) or '—'} "
                 f"| {' '.join(v['companion_observed']) or '—'} "
                 f"| {' '.join(v['unregistered']) or '—'} |")
    unknown = coverage.get("tasks_not_in_registry") or []
    if unknown:
        L.append("")
        L.append("**Not in the task registry** (no `tasks/**/task.yaml` declares them, "
                 f"so no arm map applies): {', '.join(f'`{t}`' for t in unknown)}.")
    L.append("")
    return L


def _render_legs(table: Dict[str, Any]) -> List[str]:
    multi = [c for c in table["cells"] if c["legs"]["is_multi_leg"]]
    if not multi:
        return []
    L = ["## Per-leg bills — delegation and escalation arms", "",
         "An arm that bills twice for one outcome is itemized. A leg whose cost the "
         "product does not expose stays `unavailable`; it is never inferred from the "
         "other leg, and the two legs are never merged into one number.", "",
         "| Task | Arm | Leg | Role | Model/selector | Legs | Cost median [min–max] "
         "| Cost unavailable | Tier |",
         "|---|---|---|---|---|---|---|---|---|"]
    for cell in multi:
        for row in cell["legs"]["rows"]:
            models = ", ".join(f"`{m}`" for m in row["model_or_selector"]) or "—"
            L.append(
                f"| `{cell['task_id']}` | **{cell['configuration_or_policy']}** "
                f"| {row['leg_id']} | {row['role']} | {models} | {row['n_legs']} "
                f"| {_fmt_dist(row['marginal_operating_usd'])} "
                f"| {row['legs_cost_unavailable']} | {row['confidence']} |")
    L.append("")
    return L


def _render_prereg(table: Dict[str, Any]) -> List[str]:
    grading = table.get("prereg_grading") or {}
    h = grading.get("h_effort") or {}
    w3 = grading.get("w3_escalation") or {}
    if not h and not w3:
        return []
    L = ["## Pre-registration grading", "",
         "Each registration below was written by the human **before** any run and is "
         "graded here from run data only. Both publish either way; a task outside a "
         "registration's declared scope carries no verdict rather than being folded "
         "into a score.", ""]

    reg = h.get("registration") or {}
    if reg:
        L.append(f"### {reg['id']} — registered {reg['registered']} "
                 f"(`{reg['file']}`)")
        L.append("")
        L.append(f"> {reg['prediction']}")
        L.append("")
        L.append(f"Out of registered scope: {', '.join(reg['scope_excludes_task_classes'])}. "
                 f"{reg['attribution_note']}")
        L.append("")
        strong, cheap = h["arms"]
        L.append(f"| Task | Class | {strong} cost/accepted | {cheap} cost/accepted | "
                 f"Reduction | Predicted band | Gate parity | Verdict |")
        L.append("|---|---|---|---|---|---|---|---|")
        for row in h.get("by_task", []):
            delta = row.get("delta") or {}
            red = delta.get("reduction_pct")
            band = delta.get("predicted_band_pct")
            parity = row.get("gate_parity") or {}
            def money(arm):
                v = row["arms"][arm]["ecst_usd"]
                acc = row["arms"][arm]["acceptance"]
                if v is None:
                    return "unavailable" if acc else "not run"
                return f"${v:.4f} ({acc['display']})"
            red_txt = "—" if red is None else f"{red:.1f}%"
            band_txt = "—" if not band else "{:.0f}–{:.0f}%".format(band["low"],
                                                                   band["high"])
            parity_txt = ("—" if "holds" not in parity
                          else "holds" if parity["holds"] else "refuted")
            L.append(
                f"| `{row['task_id']}` | {row['task_class']} "
                f"| {money(strong)} | {money(cheap)} "
                f"| {red_txt} | {band_txt} | {parity_txt} "
                f"| **{row['verdict']}** |")
        L.append("")
        L.append(f"Graded {h.get('n_graded', 0)} of {len(h.get('by_task', []))} task(s) "
                 f"({h.get('status')}). {h.get('note')}")
        L.append("")

    reg = w3.get("registration") or {}
    if reg:
        L.append(f"### {reg['id']} — registered {reg['registered']} (`{reg['file']}`)")
        L.append("")
        L.append(f"> {reg['prediction']}")
        L.append("")
        L.append(reg["selection_note"])
        L.append("")
        if w3.get("outcome") == "not_gradable":
            L.append(f"**Not gradable** — {w3.get('reason')}")
        else:
            L.append(f"- **Probe task:** `{w3.get('task_id')}` "
                     f"({w3.get('task_class')}), arm **{w3.get('probe_arm')}**")
            L.append(f"- **Economical-tier gate ({w3.get('economical_arm')} solo):** "
                     f"{w3.get('economical_tier_gate')}"
                     + (f" — accepted {w3['economical_solo']['acceptance']}"
                        if w3.get("economical_solo") else ""))
            L.append(f"- **Escalation branch:** {w3.get('escalation_branch')} "
                     f"({w3.get('n_escalated')} of {w3.get('n_probe_runs')} probe run(s) "
                     f"escalated)")
            L.append(f"- **Outcome:** **{w3.get('outcome')}** — {w3.get('outcome_basis')}")
        L.append("")
        L.append(w3.get("note", ""))
        L.append("")
    return L


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
    if table.get("screening_note"):
        L.append(table["screening_note"])
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

    L.extend(_render_coverage(table))
    L.extend(_render_legs(table))
    L.extend(_render_prereg(table))

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
    ap.add_argument("--tasks-root", default=None,
                    help="task definitions supplying the class + registered arm map "
                         "(default: tasks/)")
    ap.add_argument("--stdout", action="store_true",
                    help="print the markdown instead of writing files")
    args = ap.parse_args(argv)

    table = build(args.batch_dir, args.manifest, args.status, args.tasks_root)
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
