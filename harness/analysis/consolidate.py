"""One table over every screening dataset — what survived, and what is missing.

Read-only over ``results/``. No container, no model, no sealed file, zero spend.

WHY A SEPARATE MODULE. ``harness/telemetry/summarize.py`` builds the decision
table for ONE dataset, which is the right unit while a batch is being collected
and the wrong one at the end. Batch 1 holds the original cells; three later
passes went back for specific slots it lost — to a delivery defect (W6), to a
flat agent budget (W3/W4b), and to the cells the confound makeup re-bought.
Those datasets must not be pooled. A cell run under batch 1's flat 1800s bound
and the same cell re-run under its own pinned budget are two different
instruments, and averaging them would report a number no run ever produced.

So this module SUPERSEDES rather than pools, and it does so PER REP:

    slot = (task_id, configuration_id, rep)

Each slot is filled by the LATEST attempt that is neither truncated nor
adjudicated void; earlier attempts at the same slot are superseded and drop out.
A slot no attempt fills is a **hole**, printed with the reason it is one — never
dropped, never averaged around. Two kinds, because they are different findings:

    budget exhaustion   every attempt ran out of wall-clock, including at least
                        one re-buy under a longer budget. "Does not complete
                        within the budget we bought" IS the result for that
                        slot; it is not missing data.
    unreplaced loss     the slot was lost (truncated or void) and no later pass
                        re-bought it. That one IS missing data, and says so.

Everything downstream of slot selection is the code the per-dataset table
already uses — ``summarize.load_run``, ``summarize.build_cell`` and both
pre-registration graders — so a figure here cannot drift from the same figure
computed per batch. What this module adds on top is the supersession above, the
median graded-quality column, and the limitation ledger.

WHAT A CELL CARRIES. The pre-registered outcome — the binary sealed gate — is
primary and is reported first. Median graded quality rides beside it as
EXPLORATORY SECONDARY (``harness/analysis/quality.py``) and never overrides a
verdict: a run that found 6 of 6 planted defects and fabricated a seventh is
still a rejected run, and the point of the pair is that the two columns can
disagree in a way one column cannot show. Product-B costs carry their bound —
every one is cache-blind (``harness/analysis/recost.py``), so ``≤`` — and beside
each one, the provider-window attribution rule it was drawn under, because a
cost is only as comparable as the rule that produced it (see the rule column's
own note below). A cost that has no figure at all says WHY it has none: a bare
"unavailable" cannot be told apart from "nobody looked".

Run:  python -m harness.analysis.consolidate results \\
        --out-md report/findings/consolidated-table.md \\
        --out-json report/findings/consolidated-table.json \\
        --generated-at 2026-08-21T00:00:00Z
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics as st
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from harness.analysis.archive import is_evidence, parse_run_dir_name, truncation
from harness.collectors.vertex_token_collector import (  # noqa: SLF001 — see below
    REFUSAL_MARKERS,
    _RULE_EVENT_TYPE,
    _RULE_METHOD,
)
from harness.evaluator.metrics import _leg_cost, run_total  # noqa: SLF001 — see cell_cost
from harness.telemetry import costing as C
from harness.telemetry import summarize as S

#: Every screening dataset, oldest first. Order is documentation only —
#: supersession is decided by each run's own start stamp, not by this list.
DEFAULT_DATASETS = (
    "screening-batch1",
    "screening-batch1-makeup",
    "screening-batch1-makeup-w6",
    "screening-batch1-confound-makeup",
)

#: The dataset every slot was first drawn from. Runs from any other dataset are
#: named in the provenance column, so a re-bought cell can never read as original.
ORIGINAL_DATASET = DEFAULT_DATASETS[0]

BUDGET_EXHAUSTION = "budget_exhaustion"
UNREPLACED_LOSS = "unreplaced_loss"

# --------------------------------------------------------- attribution-rule reading
#
# WHY THIS COLUMN EXISTS. A Product-B cost in this table is not a product self-report:
# it is provider-meter tokens assigned to a run by TIME WINDOW, and the collector has
# drawn that window three different ways. v1 bounded the window by silence; v2 gave a
# serialized run ownership of the meter until the next run's window opens, carrying its
# own ingestion tail; v3 draws the SAME window as v2 but checks it against a RATE
# ceiling (25k input tokens/s) instead of a fixed per-run token count. Batch 1's legs
# were attributed under v1 and v2; later passes ran v3.
#
# The rules are not interchangeable, and they do not merely disagree at the margin:
# four batch-1 runs carry a v1 REFUSAL and a v2 ATTRIBUTION at once, and both records
# stand, because the two rules drew different windows and honestly reached different
# answers (see summarize.usage_provenance). A cost column spanning four datasets
# therefore spans up to three windowing rules. Unlabelled, a reader comparing two cells
# would be comparing two instruments — exactly the confound class this repo exists to
# catch — so the rule rides beside the number.
#
# HOW THE RULE IS READ. The prompt for this pass assumed every artifact carries
# ``attribution_rule.rule``. The archive says otherwise, and the archive is
# authoritative: only v3 writes that key. A v1 pass has no ownership statement at all
# (``attribution_rule`` is absent from the event and null in the marker), and v2
# predates the ``rule`` field, so it writes an ownership dict whose ``id`` names the
# method but which has no ``rule`` key. Verified over all four datasets: 38 v1 events
# and 43 v1 markers carry no rule, 4 v2 events and 37 v2 markers carry a method id but
# no rule, and only the 39 v3 events and 8 v3 markers spell it out.
#
# So the rule is read from whichever of the collector's own writer-side identifiers the
# artifact carries, in this precedence:
#
#     1. ``attribution_rule.rule``      — the field, where the collector wrote it (v3)
#     2. ``attribution_rule.id``        — the method id, inverted through _RULE_METHOD
#     3. the event type / marker filename — inverted through the collector's own maps
#
# Every step is a READ of the writer's own vocabulary, not an inference: the maps below
# are inverted from the collector's constants at import time precisely so a rename on
# the writer side cannot leave this module quietly labelling runs with a stale name.
# What is NOT done, per CLAUDE.md rule 3: nothing is defaulted to v2, and no rule is
# taken from a sibling run. An artifact that matches none of the three renders
# ``unavailable``, the same as any other missing measurement.
_RULE_BY_METHOD = {method: rule for rule, method in _RULE_METHOD.items()}
_RULE_BY_EVENT = {event: rule for rule, event in _RULE_EVENT_TYPE.items()}
_RULE_BY_MARKER = {marker: rule for rule, marker in REFUSAL_MARKERS.items()}

#: No Product-B leg in the run, so no provider window was ever drawn for it. Distinct
#: from ``unavailable``: there is nothing missing, the question does not apply.
RULE_NOT_APPLICABLE = "n/a"

SCHEMA = "consolidated-table/v1"

QUALITY_FILE = "quality-score.json"

BANNER = (
    "NON-COMPARATIVE / INTERNAL — descriptive per-cell figures only. No cross-product "
    "or cross-configuration ranking, no vendor claim, no model-efficiency attribution "
    "(CLAUDE.md rule 4, SPEC §1.2). Nothing here may appear in docs, on the site, or in "
    "any external-facing report before **CP-FINDINGS**."
)


def _load(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------ slot selection

def _rule_from_statement(statement: Any) -> Optional[str]:
    """The rule named by an ``attribution_rule`` block, or None if it names none."""
    if not isinstance(statement, dict):
        return None
    rule = statement.get("rule")
    if isinstance(rule, str) and rule:
        return rule
    return _RULE_BY_METHOD.get(str(statement.get("id")))


def has_product_b_leg(summary: Dict[str, Any]) -> bool:
    """True if any billing leg is a Product-B one.

    Identified by ``cost_basis_qualifier``, which the manifest rides on every Gemini
    leg — solo C3/C3-med/C3-prev and the C5 executor alike — and which is also what
    ``recost.needs_recost`` keys on, so the two passes cannot disagree about which
    legs are Product B's.
    """
    return any(leg.get("cost_basis_qualifier") == C.CACHE_BLIND
               for leg in (summary.get("legs") or []))


def run_attribution(run_dir: str, summary: Dict[str, Any]) -> Dict[str, Any]:
    """Which windowing rule(s) touched this run, read from its own artifacts.

    Both kinds of artifact are read, and they are kept apart in the record because
    they mean different things. A backfill event ATTRIBUTED a window and produced the
    tokens a cost was priced from. A refusal marker means the guard would not attribute
    that window, so the leg's tokens stayed ``unavailable`` — but the rule was still
    applied, and dropping it would let a refused cell read as though no rule had ever
    been drawn against it. Both go into ``rules``; only the first produced a number.
    """
    attributed: set = set()
    refused: set = set()

    path = os.path.join(run_dir, "events.jsonl")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event_type = event.get("event_type")
                if event_type not in _RULE_BY_EVENT:
                    continue
                rule = (_rule_from_statement(event.get("attribution_rule"))
                        or _RULE_BY_EVENT[event_type])
                attributed.add(rule)

    for marker, marker_rule in _RULE_BY_MARKER.items():
        marker_path = os.path.join(run_dir, marker)
        if not os.path.isfile(marker_path):
            continue
        rule = _rule_from_statement((_load(marker_path) or {}).get("attribution_rule"))
        refused.add(rule or marker_rule)

    return {
        "product_b_leg": has_product_b_leg(summary),
        "attributed": sorted(attributed),
        "refused": sorted(refused),
        "rules": sorted(attributed | refused),
    }


def read_attempt(run_dir: str, dataset: str,
                 adjudication: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One attempt at one slot: the loaded run, plus whether it counts as evidence.

    The run itself is loaded by ``summarize.load_run`` — the same path the
    per-dataset table uses, including the in-memory offline re-cost — so the two
    tables cannot disagree about a run they both contain.
    """
    ident = parse_run_dir_name(os.path.basename(os.path.normpath(run_dir)))
    if ident is None:
        return None
    record = S.load_run(run_dir, adjudication)
    if record is None:
        return None
    quality = _load(os.path.join(run_dir, QUALITY_FILE)) or {}
    record.update({
        "dataset": dataset,
        "task_id": ident["task_id"],
        "configuration_id": ident["configuration_id"],
        "rep": ident["rep"],
        "started_utc": ident["started_utc"],
        "truncated": truncation(run_dir),
        "void": record["acceptance"].get("provenance") == S.VOIDED,
        "quality": quality,
        "attribution": run_attribution(run_dir, record["summary"]),
    })
    return record


def collect_slots(results_root: str,
                  datasets: List[str]) -> Dict[Tuple[str, str, int], Dict[str, Any]]:
    """``{(task, config, rep): slot}`` across every dataset, superseded per rep."""
    slots: Dict[Tuple[str, str, int], Dict[str, Any]] = {}
    for dataset in datasets:
        ds_dir = os.path.join(results_root, dataset)
        if not os.path.isdir(ds_dir):
            continue
        if not is_evidence(dataset):
            # A smoke or HALTed dataset neither counts as evidence nor supersedes a
            # lost sample. Silently pooling one would fill a hole with a non-run.
            continue
        adjudication = S.load_adjudication(ds_dir)
        for name in sorted(os.listdir(ds_dir)):
            attempt = read_attempt(os.path.join(ds_dir, name), dataset, adjudication)
            if attempt is None:
                continue
            key = (attempt["task_id"], attempt["configuration_id"], attempt["rep"])
            slots.setdefault(key, {"key": key, "attempts": []})["attempts"].append(attempt)

    for slot in slots.values():
        slot["attempts"].sort(key=lambda a: a["started_utc"])
        usable = [a for a in slot["attempts"] if not a["truncated"] and not a["void"]]
        slot["authoritative"] = usable[-1] if usable else None
        slot["superseded"] = [a["run_id"] for a in slot["attempts"]
                              if a is not slot["authoritative"]]
        slot["hole"] = None if usable else _hole(slot["attempts"])
    return slots


def _hole(attempts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Why this slot is empty — a finding or a gap, and never rounded into the other."""
    # A VOID attempt is not an attempt at the question. It was run on a broken
    # instrument — W6's batch-1 cells got no review_diff at all — so it says nothing
    # about whether the budget was enough, and counting it toward exhaustion would
    # turn one real timeout into a fabricated "we bought it twice".
    real = [a for a in attempts if not a["void"]]
    truncated = [a for a in real if a["truncated"]]
    # Re-bought and cut off again: the slot is not missing, the answer is "not within
    # the budget we bought". One truncated attempt is a loss; two is a measurement.
    exhausted = bool(real) and len(truncated) == len(real) and len(truncated) > 1
    return {
        "kind": BUDGET_EXHAUSTION if exhausted else UNREPLACED_LOSS,
        "attempts": [{"dataset": a["dataset"], "run_id": a["run_id"],
                      "truncated": a["truncated"], "void": a["void"],
                      "wallclock_s": a["wallclock_s"].get("value"),
                      "budget_s": (a.get("run_budget") or {}).get("agent_budget_s")}
                     for a in attempts],
    }


# --------------------------------------------------------------- graded quality

def cell_quality(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Median graded quality over a cell's authoritative runs. Secondary, always.

    A run with no extractable score is absent from the median and counted in
    ``of_runs`` — never scored zero. ``quality.py`` refuses truncated runs outright,
    and those never reach here anyway: a truncated run cannot fill a slot.
    """
    scored = [r for r in runs
              if (r.get("quality") or {}).get("available")
              and r["quality"].get("score") is not None]
    scores = [r["quality"]["score"] for r in scored]
    fabrications = [r["quality"].get("detail", {}).get("fabrication_count")
                    for r in scored]
    fabrications = [f for f in fabrications if isinstance(f, int)]
    return {
        "metric": next((r["quality"].get("metric") for r in scored), None),
        "median": st.median(scores) if scores else None,
        "min": min(scores) if scores else None,
        "max_observed": max(scores) if scores else None,
        "max_possible": next((r["quality"].get("max") for r in scored), None),
        "scores": scores,
        "n": len(scored),
        "of_runs": len(runs),
        "fabrications_total": sum(fabrications) if fabrications else None,
        "status": ("EXPLORATORY SECONDARY — extracted from archived sealed output. "
                   "The pre-registered outcome is the binary gate and this does not "
                   "override it."),
    }


# ------------------------------------------------------------ attribution per cell

def cell_attribution(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Which provider-window rule(s) the cell's filled reps were priced under.

    A sorted set, never a single value: a cell may be filled from more than one
    dataset, and the datasets were attributed under different rules. Runs with no
    Product-B leg contribute nothing — for them the question does not arise, and
    counting them would make an all-Product-A arm look rule-mixed.

    A Product-B run whose artifacts name no rule is counted in
    ``product_b_runs_without_rule`` and left out of ``rules``. It is not filled in
    from the rule a sibling rep ran under (CLAUDE.md rule 3).
    """
    attributed: set = set()
    refused: set = set()
    product_b = 0
    without = 0
    for run in runs:
        a = run.get("attribution") or {}
        if not a.get("product_b_leg"):
            continue
        product_b += 1
        if not a.get("rules"):
            without += 1
            continue
        attributed.update(a.get("attributed") or [])
        refused.update(a.get("refused") or [])
    rules = sorted(attributed | refused)
    return {
        "rules": rules,
        "attributed": sorted(attributed),
        "refused": sorted(refused),
        "product_b_runs": product_b,
        "product_b_runs_without_rule": without,
        "of_runs": len(runs),
        "mixed": len(rules) > 1,
    }


# ----------------------------------------------------------------------- building

def build(results_root: str, datasets: List[str],
          manifest_path: Optional[str] = None,
          tasks_root: Optional[str] = None) -> Dict[str, Any]:
    slots = collect_slots(results_root, datasets)

    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    slots_by_cell: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for key, slot in sorted(slots.items()):
        cell_key = (key[0], key[1])
        slots_by_cell.setdefault(cell_key, []).append(slot)
        if slot["authoritative"]:
            grouped.setdefault(cell_key, []).append(slot["authoritative"])

    manifest_path = manifest_path or os.path.join(
        S._REPO, "manifest", "delivery-manifest.yaml")  # noqa: SLF001 — same default
    rate = S.loaded_rate_from_manifest(manifest_path)
    registry = S.load_task_registry(tasks_root, "configurations")

    cells = []
    for cell_key, cell_runs in sorted(grouped.items()):
        task, config = cell_key
        entry = registry.get(task)
        cell = S.build_cell(task, config, cell_runs, rate,
                            task_class=(entry or {}).get("task_class"),
                            registered_arm=(None if entry is None
                                            else config in entry["registered_arms"]))
        cell["quality"] = cell_quality(cell_runs)
        cell["cost"] = cell_cost(cell_runs)
        cell["attribution"] = cell_attribution(cell_runs)
        # Hoisted to the cell so a consumer that reads only the cost block still sees
        # that the figures under it were drawn by more than one windowing rule.
        cell["cost_rule_mixed"] = cell["attribution"]["mixed"]
        cell["cost_provenance"] = S._cost_provenance(cell_runs)  # noqa: SLF001
        cell["source_datasets"] = _dataset_tally(cell_runs)
        cell["reps_registered"] = len(slots_by_cell[cell_key])
        cell["reps_filled"] = len(cell_runs)
        cell["holes"] = [dict(s["hole"], rep=s["key"][2])
                         for s in slots_by_cell[cell_key] if s["hole"]]
        cell["superseded_runs"] = [rid for s in slots_by_cell[cell_key]
                                   for rid in s["superseded"]]
        cells.append(cell)

    # A cell every attempt lost has no runs and so no build_cell row. It still has to
    # appear, or the table would silently be missing the cells that failed hardest.
    for cell_key, cell_slots in sorted(slots_by_cell.items()):
        if cell_key in grouped:
            continue
        task, config = cell_key
        cells.append(_empty_cell(task, config, cell_slots, registry.get(task)))
    # A rep the contamination guard refused leaves no run directory, so nothing above
    # this line can see it and the cell's denominator quietly shrinks to the reps that
    # did run — a cell that lost a rep would print a confident "3/3". Count them back
    # in: the design registered the rep, we bought it, and it did not happen.
    deferred = deferred_contaminated(results_root, datasets, registry)
    for cell in cells:
        key = (cell["task_id"], cell["configuration_or_policy"])
        extra = {d["rep"] for d in deferred
                 if (d["task_id"], d["configuration_id"]) == key}
        extra -= {s["key"][2] for s in slots_by_cell.get(key, [])}
        if extra:
            cell["reps_registered"] += len(extra)
            cell["reps_deferred_contaminated"] = sorted(extra)
    cells.sort(key=lambda c: (c["task_id"], c["configuration_or_policy"]))

    by_cell = {(c["task_id"], c["configuration_or_policy"]): c for c in cells}
    observed: Dict[str, List[str]] = {}
    for task, config in grouped:
        observed.setdefault(task, []).append(config)

    all_runs = [r for runs in grouped.values() for r in runs]
    return {
        "schema": SCHEMA,
        "status": "PENDING",
        "note": BANNER,
        "cp_findings_gate": S.CP_FINDINGS_NOTE,
        "screening_note": S.SCREENING_NOTE,
        "datasets": datasets,
        "manifest_ref": os.path.relpath(os.path.abspath(manifest_path), S._REPO),
        "loaded_rate_usd_per_min": rate,
        "n_slots": len(slots),
        "n_slots_filled": len(all_runs),
        "n_runs_superseded": sum(len(s["superseded"]) for s in slots.values()),
        "n_cells": len(cells),
        "supersession": {
            "unit": "(task_id, configuration_id, rep)",
            "rule": ("the latest attempt that is neither truncated nor adjudicated "
                     "void fills the slot; earlier attempts at the same slot are "
                     "superseded, not averaged in"),
        },
        "dataset_provenance": S._dataset_provenance(all_runs, {}),  # noqa: SLF001
        "task_registry": registry,
        "arm_coverage": S.arm_coverage(registry, observed),
        "prereg_grading": {
            "h_effort": S.grade_h_effort(by_cell, registry),
            "w3_escalation": S.grade_w3_escalation(by_cell, grouped, registry),
        },
        "cells": cells,
        "ledger": ledger(cells, deferred),
    }


def cell_cost(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Median attempt cost over the runs whose cost is COMPLETE.

    ``metrics.run_total`` still returns a sum when one leg's cost is unavailable, and
    that sum is a known floor, not a total. A floor entered into a median beside
    complete runs would report a dual-billed run at one leg's price, so runs with any
    unpriced leg are excluded and counted separately instead (CLAUDE.md rule 3).
    """
    complete: List[float] = []
    partial = 0
    unavailable = 0
    legs_total = 0
    legs_unpriced = 0
    for run in runs:
        total, any_unavailable = run_total(run["summary"], "marginal")
        if total is None:
            unavailable += 1
        elif any_unavailable:
            partial += 1
        else:
            complete.append(total)
        # Counted for the renderer only — which legs went unpriced is what turns a
        # bare "unavailable" into a stated reason. The selection above is untouched.
        for leg in (run["summary"].get("legs") or []):
            legs_total += 1
            legs_unpriced += _leg_cost(leg, "marginal") is None
    return {
        "median_usd": st.median(complete) if complete else None,
        "min_usd": min(complete) if complete else None,
        "max_usd": max(complete) if complete else None,
        "n": len(complete),
        "of_runs": len(runs),
        "runs_partially_costed": partial,
        "runs_uncosted": unavailable,
        "legs": legs_total,
        "legs_unpriced": legs_unpriced,
        "basis": "sum of per-leg marginal_operating_usd over all attempts in the run",
    }


def _dataset_tally(runs: List[Dict[str, Any]]) -> Dict[str, int]:
    tally: Dict[str, int] = {}
    for run in runs:
        tally[run["dataset"]] = tally.get(run["dataset"], 0) + 1
    return tally


def _empty_cell(task: str, config: str, cell_slots: List[Dict[str, Any]],
                entry: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """A cell no attempt filled. Reported as absent evidence, never as a rejection."""
    return {
        "task_id": task,
        "task_class": (entry or {}).get("task_class") or "unclassified",
        "configuration_or_policy": config,
        "registered_arm": (None if entry is None
                           else config in entry["registered_arms"]),
        "n_runs": 0,
        "acceptance": {"accepted": 0, "of": 0, "gradable": 0,
                       "display": "no gradable run",
                       "breakdown": {}, "confidence": S.UNAVAILABLE,
                       "provenance": {"all_original": True, "n_runs": 0},
                       "basis": "every attempt at every rep was truncated or voided"},
        "quality": cell_quality([]),
        "cost": cell_cost([]),
        "attribution": cell_attribution([]),
        "cost_rule_mixed": False,
        "ecst": {"marginal_operating_usd": {"value": None, "status": S.UNAVAILABLE},
                 "attempt_cost_usd": {"median": None, "n": 0, "of_runs": 0}},
        "wallclock_s": {"median": None, "n": 0, "of_runs": 0},
        "source_datasets": {},
        "reps_registered": len(cell_slots),
        "reps_filled": 0,
        "holes": [dict(s["hole"], rep=s["key"][2]) for s in cell_slots if s["hole"]],
        "superseded_runs": [rid for s in cell_slots for rid in s["superseded"]],
    }


# --------------------------------------------------------------- limitation ledger

def deferred_contaminated(results_root: str, datasets: List[str],
                          registry: Optional[Dict[str, Any]] = None,
                          ) -> List[Dict[str, Any]]:
    """Slots a driver was told to buy and did not run, per `deferred-contaminated.tsv`.

    These leave no run directory, so nothing downstream of `scan()` can see them, and
    without this they read in the ledger as "lost to truncation and never re-bought" —
    which is the opposite of what happened. The slot WAS re-bought under an approved
    CP-SPEND; the collector's contamination guard then refused to start it because
    background traffic on the subject model would have made the attribution
    meaningless. Nothing was billed and nothing was measured. It is still a hole, but
    it is a hole with a named cause and a cheap remedy (re-run in a quiet window), and
    a reader deciding whether to buy the slot again needs to know which kind it is.
    """
    # Batch 1's driver wrote the task DIRECTORY in this column and later drivers write
    # the task id. Both are the same slot and must land on the same key, or a deferral
    # would be filed against a task that appears nowhere else in the table.
    by_dir = {e["task_dir"]: tid for tid, e in (registry or {}).items()}

    out: List[Dict[str, Any]] = []
    for dataset in datasets:
        path = os.path.join(results_root, dataset, "deferred-contaminated.tsv")
        try:
            with open(path, encoding="utf-8") as fh:
                rows = fh.read().splitlines()
        except OSError:
            continue
        for line in rows:
            parts = line.split("\t")
            if len(parts) < 5 or parts[0].startswith("#"):
                continue
            stamp, _slot_no, task, config, rep = parts[:5]
            out.append({"dataset": dataset,
                        "task_id": by_dir.get(task, task),
                        "task_as_written": task,
                        "configuration_id": config,
                        "rep": int(re.sub(r"\D", "", rep) or 0),
                        "deferred_at": stamp})
    return sorted(out, key=lambda r: (r["task_id"], r["configuration_id"], r["rep"]))


def ledger(cells: List[Dict[str, Any]],
           deferred: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Everything a reader must know before quoting a number from the table.

    Assembled FROM the cells rather than hand-written, so it cannot fall out of date
    with them: a hole that appears in the data appears here.
    """
    exhausted: List[Dict[str, Any]] = []
    lost: List[Dict[str, Any]] = []
    for cell in cells:
        for hole in cell["holes"]:
            entry = {"task_id": cell["task_id"],
                     "configuration_id": cell["configuration_or_policy"],
                     "rep": hole["rep"], "attempts": hole["attempts"]}
            (exhausted if hole["kind"] == BUDGET_EXHAUSTION else lost).append(entry)

    # A slot that was re-bought and then refused by the contamination guard belongs in
    # exactly one place, and it is not "never re-bought". Move it, carrying its earlier
    # attempts with it, so the reader sees both the loss and why the replacement never
    # ran without the two facts being filed as separate holes.
    by_slot = {(d["task_id"], d["configuration_id"], d["rep"]): d
               for d in (deferred or [])}
    still_lost, refused = [], []
    for entry in lost:
        key = (entry["task_id"], entry["configuration_id"], entry["rep"])
        if key in by_slot:
            refused.append({**by_slot[key], "attempts": entry["attempts"]})
        else:
            still_lost.append(entry)
    for key, d in sorted(by_slot.items()):
        if not any(key == (r["task_id"], r["configuration_id"], r["rep"])
                   for r in refused):
            refused.append({**d, "attempts": []})
    lost = still_lost

    def named(predicate) -> List[str]:
        return [f"{c['task_id']}::{c['configuration_or_policy']}"
                for c in cells if predicate(c)]

    return {
        "budget_exhaustion": exhausted,
        "unreplaced_loss": lost,
        "deferred_contaminated": sorted(
            refused, key=lambda r: (r["task_id"], r["configuration_id"], r["rep"])),
        "cells_with_no_evidence": named(lambda c: c["reps_filled"] == 0),
        "cells_with_understrength_n": [
            f"{c['task_id']}::{c['configuration_or_policy']} "
            f"({c['reps_filled']}/{c['reps_registered']})"
            for c in cells if 0 < c["reps_filled"] < c["reps_registered"]],
        "cells_costed_at_an_upper_bound": named(_has_upper_bound),
        "cells_costed_under_more_than_one_rule": [
            f"{c['task_id']}::{c['configuration_or_policy']} "
            f"({','.join(c['attribution']['rules'])})"
            for c in cells if c.get("cost_rule_mixed")],
        "cells_with_an_unattested_attribution_rule": named(
            lambda c: (c.get("attribution") or {}).get(
                "product_b_runs_without_rule")),
        "cells_with_a_partially_costed_run": named(
            lambda c: (c.get("cost") or {}).get("runs_partially_costed")),
        "cells_with_an_uncosted_run": named(
            lambda c: (c.get("cost") or {}).get("runs_uncosted")),
        "cells_with_no_graded_quality": named(
            lambda c: c["reps_filled"] and c["quality"]["n"] == 0),
        "cells_with_partial_graded_quality": named(
            lambda c: 0 < c["quality"]["n"] < c["reps_filled"]),
        "standing": [
            "Screening is hypothesis-seeking positioning evidence (SPEC §5): a result "
            "on one task is a signal about that task under these pinned conditions, "
            "never a workload-class or product claim.",
            "Every Product-B cost is a cache-blind UPPER BOUND, never an exact cost "
            "(manifest notes.gemini_cache_blindness); it is printed with a ≤.",
            "Product-B token counts are provider-side (authoritative) attributed to a "
            "serialized run window (derived), so the derived figures inherit the "
            "weaker tier. Never authoritative end to end.",
            "Graded quality is EXPLORATORY SECONDARY, extracted from archived sealed "
            "output. The pre-registered outcome is the binary gate and does not move.",
            "Truncated runs are excluded from quality extraction entirely: a partial "
            "score from a run the harness cut off reads as a model that found little, "
            "when the truth is that it was stopped.",
            "Datasets are superseded per rep, never pooled. Reps run under different "
            "agent budgets are different instruments.",
            "The same applies to the money: a Product-B cost is only as comparable as "
            "the rule that drew its provider window, which is why the rule is printed "
            "beside the figure and a cell spanning two of them is marked.",
            "W3 and W4b have no graded quality on any run: the python stack's "
            "per-check capture came back empty for every one of them, and W3's sealed "
            "suite never executed at all (pytest usage error, exit 4, in all three "
            "grading generations — original, regrade-v2, and the confound makeup's "
            "live grading under a gate that does carry the per-check step). No verdict "
            "depends on it — see report/findings/graded-quality-extraction.md.",
            "No W3 or W4b run in any arm passed the public checks (0 of 32 and 0 of 20 "
            "runs carrying a public gate), so neither task discriminates between arms "
            "and no comparative reading may be taken from either.",
        ],
    }


def _has_upper_bound(cell: Dict[str, Any]) -> bool:
    """True if ANY run in the cell contributed a cache-blind figure.

    One upper-bound leg makes the cell's median an upper bound: it is not diluted
    by the exactly-priced runs beside it.
    """
    return bool((cell.get("cost_provenance") or {}).get("any_upper_bound"))


# ------------------------------------------------------------------------ rendering

def _fmt_quality(q: Dict[str, Any]) -> str:
    if q["median"] is None:
        return "—"
    out = f"{q['median']:g}"
    if q["max_possible"] is not None:
        out += f"/{q['max_possible']}"
    if q["n"] != q["of_runs"]:
        out += f" (n={q['n']} of {q['of_runs']})"
    if q["fabrications_total"]:
        out += f", {q['fabrications_total']} fabricated"
    return out


def _cost_unavailable_reason(cell: Dict[str, Any]) -> str:
    """Why this cell has no median — read off the record, not keyed to the arm.

    Reached only when no run in the cell was completely priced, so "some legs
    priced" here means priced in runs that were nonetheless excluded from the
    median for having an unpriced leg beside them.
    """
    c = cell.get("cost") or {}
    if not c.get("of_runs"):
        return "no run filled this cell"
    unpriced, legs = c.get("legs_unpriced") or 0, c.get("legs") or 0
    if unpriced and unpriced < legs:
        return f"partial: {unpriced} of {legs} legs unpriced"
    refused = (cell.get("attribution") or {}).get("refused") or []
    if unpriced and refused:
        return f"no priced leg; provider window refused ({','.join(refused)})"
    return "no provider usage record"


def _fmt_cost(cell: Dict[str, Any]) -> str:
    c = cell.get("cost") or {}
    if c.get("median_usd") is None:
        return f"unavailable — {_cost_unavailable_reason(cell)}"
    out = f"{'≤' if _has_upper_bound(cell) else ''}${c['median_usd']:.4f}"
    if c["n"] != c["of_runs"]:
        out += f" (n={c['n']} of {c['of_runs']})"
    return out


def _fmt_rules(cell: Dict[str, Any]) -> str:
    """The provider-window rule(s) behind this cell's cost figure."""
    a = cell.get("attribution") or {}
    if not a.get("of_runs"):
        return "—"
    if not a.get("product_b_runs"):
        return RULE_NOT_APPLICABLE
    parts = list(a.get("rules") or [])
    if a.get("product_b_runs_without_rule"):
        parts.append("unavailable")
    out = ",".join(parts)
    # Marked when the cell's reps are not ESTABLISHED to be like-for-like — either
    # because they demonstrably span two windowing rules, or because one rep's rule
    # is unattested. An unknown rule is no more comparable than a different one, and
    # assuming it matches its siblings is the inference this column exists to refuse.
    unattested = a.get("mixed") or a.get("product_b_runs_without_rule")
    return f"{out} ⚠" if unattested else out


def _fmt_provenance(cell: Dict[str, Any]) -> str:
    if not cell["reps_filled"]:
        return "—"
    parts = [S._fmt_provenance((cell["acceptance"] or {}).get("provenance") or {})]
    makeup = {k: n for k, n in (cell.get("source_datasets") or {}).items()
              if k != ORIGINAL_DATASET}
    parts += [f"{n} from `{k}`" for k, n in sorted(makeup.items())]
    return "; ".join(p for p in parts if p) or "—"


def _fmt_wall(cell: Dict[str, Any]) -> str:
    median = (cell.get("wallclock_s") or {}).get("median")
    return "—" if median is None else f"{median:.0f}"


def render(table: Dict[str, Any], *, generated_at: str, harness_head: str) -> str:
    L = [
        "# Consolidated screening table — every dataset, one row per cell",
        "",
        "**STATUS: PENDING** — this document opens at **CP-FINDINGS**.",
        "",
        f"Generated {generated_at} from `results/`; harness `{harness_head}`. "
        "Zero model spend: nothing here re-runs an agent or a gate.",
        "",
        BANNER,
        "",
        "## How a cell was filled",
        "",
        "Datasets are **superseded per rep**, never pooled. A slot is "
        f"`{table['supersession']['unit']}`, and {table['supersession']['rule']}. "
        "A cell run under batch 1's flat bound and the same cell re-run under its own "
        "pinned budget are two instruments; averaging them would report a number no "
        "run produced.",
        "",
        f"{table['n_slots_filled']} of {table['n_slots']} slots filled across "
        f"{table['n_cells']} cells; {table['n_runs_superseded']} run(s) superseded. "
        f"Datasets in scope: {', '.join('`%s`' % d for d in table['datasets'])}.",
        "",
        "**Accepted** is the pre-registered outcome and the only primary one. "
        "**Quality** is exploratory secondary, extracted from archived sealed output; "
        "it never overrides a verdict, and the two columns are expected to disagree — "
        "that disagreement is the point. A cost printed `≤` is a cache-blind upper "
        "bound on Product-B spend, not an exact figure.",
        "",
        "**Cost rule** names the provider-window attribution rule each cell's "
        "Product-B tokens were drawn under — `v1` a silence-bounded window, `v2` "
        "serialized run ownership with an ingestion tail, `v3` the same window under "
        "a rate ceiling. A refused window still names its rule: the rule was applied, "
        "the tokens were withheld. Arms with no Product-B leg read `n/a`, because for "
        "them no window was ever drawn — that is not a missing measurement. A cell "
        "marked ⚠ spans more than one rule, so its reps were priced on more than one "
        "instrument and its median is not a like-for-like figure.",
        "",
        "## Cells",
        "",
        "| Task | Arm | Accepted | Quality (median) | Attempt cost (median) | "
        "Cost rule | Wall-clock s | Reps | Provenance |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c in table["cells"]:
        reps = f"{c['reps_filled']}/{c['reps_registered']}"
        # Mark on the arithmetic, not on the hole list: a rep the contamination guard
        # refused never became a slot, so it has no hole entry, and marking only holes
        # would let a short cell print an unmarked denominator.
        if c["holes"] or c["reps_filled"] < c["reps_registered"]:
            reps += " ⚠"
        L.append(
            f"| `{c['task_id']}` | **{c['configuration_or_policy']}** | "
            f"{c['acceptance']['display']} | {_fmt_quality(c['quality'])} | "
            f"{_fmt_cost(c)} | {_fmt_rules(c)} | {_fmt_wall(c)} | {reps} | "
            f"{_fmt_provenance(c)} |")

    L += ["", "Quality metrics by task family: W1/W1b mutants caught, W3 sealed rules "
          "clean, W4b sealed assertions passed, W6 planted defects found (with "
          "fabrications counted separately and never netted off).", ""]

    L += _render_prereg(table)
    L += _render_ledger(table["ledger"])
    return "\n".join(L)


def _render_prereg(table: Dict[str, Any]) -> List[str]:
    """Both registrations, graded over the superseded set. Published either way."""
    L = ["## Pre-registrations, graded", "",
         "Graded over the superseded set above — the same graders the per-dataset "
         "table uses, given the runs that survived supersession. Published whichever "
         "way they come out, per the registration (CP-SCREEN-PREREG).", ""]

    h = table["prereg_grading"]["h_effort"]
    L += [f"### H-effort ({' vs '.join(h['arms'])}) — status: `{h['status']}`, "
          f"{h['n_graded']} task(s) graded", ""]
    L += ["| Task | In scope | Verdict | Reduction | Gate parity |", "|---|---|---|---|---|"]
    for row in h["by_task"]:
        delta = row.get("delta") or {}
        pct = delta.get("reduction_pct")
        parity = row.get("gate_parity") or {}
        L.append(f"| `{row['task_id']}` | {'yes' if row['in_registered_scope'] else 'no'} "
                 f"| `{row['verdict']}` | "
                 f"{'—' if pct is None else f'{pct:.1f}%'} | "
                 f"{'—' if not parity else ('holds' if parity['holds'] else 'REFUTED')} |")
    L += ["", f"Predicted band: {h['registration']['predicted_reduction_pct']['low']}–"
          f"{h['registration']['predicted_reduction_pct']['high']}% reduction in cost "
          f"per accepted outcome. {h['note']}", ""]

    w = table["prereg_grading"]["w3_escalation"]
    L += [f"### W3 escalation ({w['probe_arm']} vs {w['economical_arm']}) — outcome: "
          f"`{w.get('outcome')}`", ""]
    if w.get("reason"):
        L += [w["reason"], ""]
    L += [f"- Probe task(s): {', '.join('`%s`' % t for t in w['probe_tasks']) or 'none'}",
          f"- Economical arm ({w['economical_arm']}) at the gate: "
          f"`{w.get('economical_tier_gate')}`"
          + (f" — accepted {w['economical_solo']['acceptance']}"
             if w.get("economical_solo") else ""),
          f"- Escalation branch: `{w.get('escalation_branch')}` "
          f"({w.get('n_escalated')} of {w.get('n_probe_runs')} probe run(s))"]
    if w.get("outcome_basis"):
        L += [f"- Basis: {w['outcome_basis']}"]
    if w.get("confound"):
        L += [f"- Confound: {w['confound']['statement']}"]
    # The grader reads whatever survived supersession. If either arm is short of the
    # registered reps, the verdict rests on fewer runs than the design bought, and a
    # reader who cannot see that from this section would over-read it.
    for label, cell in (("economical", w.get("economical_solo")),
                        ("probe", w.get("probe_cell"))):
        acc = (cell or {}).get("acceptance") or ""
        if "/" in acc and acc.split("/")[1].isdigit() and int(acc.split("/")[1]) < 3:
            L += [f"- **Understrength:** the {label} arm is graded on {acc.split('/')[1]} "
                  f"run(s), not the registered 3 — see the limitation ledger."]
    L += [""]
    return L


def _render_ledger(led: Dict[str, Any]) -> List[str]:
    L = ["## Limitation ledger", "",
         "### Slots that are a finding, not a hole", ""]
    if led["budget_exhaustion"]:
        L += ["Every attempt at these slots ran out of wall-clock, and the slot was "
              "re-bought at least once under a longer budget before being cut off "
              "again. *Does not complete within the budget we bought* is the result "
              "for that slot — it is not missing data.", ""]
        for e in led["budget_exhaustion"]:
            L.append(f"- `{e['task_id']}` **{e['configuration_id']}** rep {e['rep']} — "
                     f"{len(e['attempts'])} attempt(s): {_attempts(e['attempts'])}")
    else:
        L.append("None.")
    L += ["", "### Slots that ARE missing data", ""]
    if led["unreplaced_loss"]:
        L += ["Lost to truncation or adjudicated void, and never re-bought. Every "
              "median over the surviving reps of these cells is over fewer reps than "
              "the design registered.", ""]
        for e in led["unreplaced_loss"]:
            L.append(f"- `{e['task_id']}` **{e['configuration_id']}** rep {e['rep']} — "
                     f"{_attempts(e['attempts'])}")
    else:
        L.append("None.")
    L.append("")

    L += ["### Slots re-bought, then refused by the contamination guard", ""]
    if led.get("deferred_contaminated"):
        L += ["These slots WERE re-bought under an approved CP-SPEND. The collector "
              "then measured background traffic on the subject model and refused to "
              "start the run, because a cost attributed across someone else's traffic "
              "is not a measurement. **Nothing was billed and nothing was run.** They "
              "are holes, but the cause is the measurement window, not the model or "
              "the budget, and the remedy is to re-run them in a quiet window.", ""]
        for e in led["deferred_contaminated"]:
            prior = (f" Earlier attempt(s): {_attempts(e['attempts'])}"
                     if e.get("attempts") else "")
            L.append(f"- `{e['task_id']}` **{e['configuration_id']}** rep {e['rep']} — "
                     f"deferred {e['deferred_at']} in `{e['dataset']}`.{prior}")
    else:
        L.append("None.")
    L.append("")

    for title, key, gloss in (
        ("Cells with no evidence at all", "cells_with_no_evidence",
         "Every rep was truncated or voided. The cell is reported with no verdict — "
         "which is not the same statement as a rejection."),
        ("Cells running below their registered n", "cells_with_understrength_n",
         "Every figure in these rows is over fewer reps than the design registered."),
        ("Cells costed at an upper bound", "cells_costed_at_an_upper_bound",
         "Product-B spend, priced cache-blind. Never restate one of these as an "
         "exact cost."),
        ("Cells costed under more than one attribution rule",
         "cells_costed_under_more_than_one_rule",
         "The reps in these cells had their Product-B tokens drawn from the provider "
         "meter under different windowing rules, so the cell's median is taken over "
         "figures produced by more than one instrument. Marked ⚠ in the Cost rule "
         "column. The rules are not a ranking and one does not correct another; they "
         "are successive answers to *which slice of the meter is this run's*."),
        ("Cells with an unattested attribution rule",
         "cells_with_an_unattested_attribution_rule",
         "A Product-B run in the cell carries no artifact naming the rule its window "
         "was drawn under. Recorded `unavailable` and NOT filled in from the rule its "
         "sibling reps ran under."),
        ("Cells with a partially costed run", "cells_with_a_partially_costed_run",
         "A dual-billed run whose second leg reported no usage. Its per-leg figures "
         "stand; its run total does not, and it is left out of the cell's median "
         "rather than entered as a floor."),
        ("Cells with an uncosted run", "cells_with_an_uncosted_run",
         "No leg of the run reported a priceable cost. Recorded `unavailable`, never "
         "zero."),
        ("Cells with no graded quality", "cells_with_no_graded_quality",
         "The archived gate log carries no extractable per-check detail, so there is "
         "no secondary measure for the cell — which is not a score of zero."),
        ("Cells with partial graded quality", "cells_with_partial_graded_quality",
         "The median is over a subset of the cell's runs; the n is printed in the "
         "cell."),
    ):
        L += [f"### {title}", ""]
        if led[key]:
            L += [gloss, ""] + [f"- `{item}`" for item in led[key]]
        else:
            L.append("None.")
        L.append("")

    L += ["### Standing limitations", ""]
    L += [f"- {item}" for item in led["standing"]]
    L.append("")
    return L


def _attempts(attempts: List[Dict[str, Any]]) -> str:
    out = []
    for a in attempts:
        bit = f"`{a['dataset']}` {a['truncated'] or 'void'}"
        if a.get("wallclock_s"):
            bit += f" after {a['wallclock_s']:.0f}s"
        if a.get("budget_s"):
            bit += f" (budget {a['budget_s']}s)"
        out.append(bit)
    return "; ".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Consolidated table over all datasets")
    ap.add_argument("results", nargs="?", default="results")
    ap.add_argument("--dataset", action="append", default=None,
                    help="repeatable; defaults to every screening dataset")
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--tasks-root", default=None)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--out-json", default=None)
    ap.add_argument("--generated-at", required=True,
                    help="UTC stamp, passed in so the report is reproducible")
    args = ap.parse_args(argv)

    datasets = args.dataset or [d for d in DEFAULT_DATASETS
                                if os.path.isdir(os.path.join(args.results, d))]
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True, check=False).stdout.strip()
    table = build(args.results, datasets, args.manifest, args.tasks_root)
    table["generated_at"] = args.generated_at
    table["harness_head"] = head or "unavailable"

    md = render(table, generated_at=args.generated_at,
                harness_head=head or "unavailable")
    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as fh:
            json.dump(table, fh, indent=2, sort_keys=True, default=str)
            fh.write("\n")
    if args.out_md:
        with open(args.out_md, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"wrote {args.out_md}")
    else:
        sys.stdout.write(md)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
