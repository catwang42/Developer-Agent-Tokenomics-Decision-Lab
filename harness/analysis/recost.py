"""Price the Product-B legs the provider-side backfill filled in. Zero spend.

WHY THIS EXISTS. A Product-B (Gemini) run reports no token counts of its own —
the product exposes none. ``harness/collectors/vertex_token_collector.py`` fills
them in afterwards from the provider meter and re-derives ``summary.json``, but
it deliberately does not recompute economics ("costs stay as the runner recorded
them"), so every Gemini leg in every dataset still carries
``marginal_operating_usd: unavailable`` even where its tokens are now known.

Two things had to be true before those legs could be priced at all:

1. **The counts had to exist.** They do, under collector rule v3 — provider-side
   counts (authoritative) attributed to a serialized run window (derived), so the
   priced figure inherits the weaker tier: **derived**, never authoritative.
2. **The cache classes had to be resolvable.** They are not measurable and never
   will be: the provider meter emits only ``type=input`` and ``type=output`` for
   ``publisher="google"`` on this project. The delivery manifest's human decision
   of 2026-08-16 (``notes.gemini_cache_blindness``) declares every Gemini leg
   ``cost_basis_qualifier: cache_blind_upper_bound`` — cache classes stay
   unavailable rather than zero, all input prices at the full input rate, and the
   result is an UPPER BOUND. Implicit caching can only make the real bill lower.

So this module prices exactly those legs, at exactly that bound, and writes the
result to a ``recost.json`` sidecar. It never edits ``summary.json``: the frozen
summary is what the instrument recorded, and a cost derived months later beside
it is a different kind of claim that has to stay separately labelled and
separately discardable. Same pattern as ``regrade-v2-summary.json``.

WHAT IT REFUSES. No pricing snapshot named in the run's economics; the snapshot
missing from ``pricing/``; no rate row for the leg's provider/selector; a leg
whose input or output is still unavailable. Each refusal is recorded with its
reason and the run keeps ``unavailable`` — never a partial or imputed figure
(CLAUDE.md rule 3).

Run:  python -m harness.analysis.recost results --dataset screening-batch1
      python -m harness.analysis.recost results --dataset screening-batch1 --write
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

from harness.telemetry.costing import (CACHE_BLIND, compute_cost_views,
                                       load_prices)

RECOST_FILE = "recost.json"

#: Only this qualifier turns cache-blind pricing on. An unrecognised qualifier is
#: a refusal, not a fallback: a figure derived under an unreviewed convention is
#: worse than no figure.
SUPPORTED_QUALIFIER = CACHE_BLIND

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _unwrap(field: Any) -> Any:
    return field["value"] if isinstance(field, dict) and "value" in field else field


def needs_recost(leg: Dict[str, Any]) -> bool:
    """A leg the runner left unpriced that a backfill has since given tokens.

    Both halves matter. A leg the runner already priced is not re-priced here —
    re-deriving a figure that already exists would quietly replace the runner's
    record with this module's, and the two are not the same provenance.
    """
    if leg.get("cost_basis_qualifier") != SUPPORTED_QUALIFIER:
        return False
    if (leg.get("marginal_operating_usd") or {}).get("value") is not None:
        return False
    usage = leg.get("usage") or {}
    return all((usage.get(k) or {}).get("value") is not None
               for k in ("input_tokens", "output_tokens"))


def prices_for(summary: Dict[str, Any], pricing_root: str
               ) -> Dict[str, Any]:
    """Load the snapshot the RUN was priced under — never a newer one.

    Re-pricing 2026-08-19 traffic against a snapshot collected later would report
    a cost that was never billable. The snapshot name is in the run's own
    economics block, and a run that names none is refused.
    """
    snapshot = (summary.get("economics") or {}).get("pricing_snapshot")
    if not snapshot:
        raise LookupError("run names no pricing_snapshot in its economics block")
    path = os.path.join(pricing_root, snapshot)
    if not os.path.isfile(path):
        raise LookupError(f"pinned pricing snapshot not on disk: {snapshot}")
    return {"snapshot": snapshot, "prices": load_prices(path)}


def recost_run(run_dir: str, pricing_root: str) -> Dict[str, Any]:
    """The priced record for one run — or a refusal carrying its reason."""
    summary = _load(os.path.join(run_dir, "summary.json"))
    run_id = (summary or {}).get("run_id") or os.path.basename(os.path.normpath(run_dir))
    record: Dict[str, Any] = {
        "run_id": run_id,
        "task_id": (summary or {}).get("task_id"),
        "configuration_id": (summary or {}).get("configuration_id"),
        "cost_basis": (summary or {}).get("economics", {}).get("cost_basis"),
        "cost_basis_qualifier": SUPPORTED_QUALIFIER,
        "bound": "upper",
        "source": "provider-side token backfill, priced offline; no model was invoked",
    }
    if summary is None:
        return dict(record, status="refused", reason="no readable summary.json")

    all_legs = summary.get("legs") or []
    targets = [leg for leg in all_legs if needs_recost(leg)]
    if not targets:
        return dict(record, status="skipped",
                    reason="no unpriced cache-blind leg with backfilled tokens")

    try:
        loaded = prices_for(summary, pricing_root)
    except LookupError as exc:
        return dict(record, status="refused", reason=str(exc))

    # EVERY leg, not only the re-costed ones. A C5 run bills a Claude conductor
    # beside its Gemini executor, and reporting the executor's figure as the run's
    # cost would understate a dual-billed run by a whole leg. Legs this pass does
    # not re-cost are priced from their own usage under the SAME pinned snapshot —
    # the same function the runner used, so the two cannot disagree.
    priced: List[Dict[str, Any]] = []
    for leg in all_legs:
        blind = leg in targets
        provider = _unwrap(leg.get("provider"))
        selector = _unwrap(leg.get("model_or_selector"))
        try:
            views = compute_cost_views(
                leg.get("usage") or {}, provider, selector, loaded["prices"],
                leg.get("cost_basis", "marginal_api_cost"), cache_blind=blind)
        except (KeyError, ValueError) as exc:
            return dict(record, status="refused",
                        reason=f"leg {leg.get('leg_id')}: {exc}")
        priced.append({
            "leg_id": leg.get("leg_id"),
            "role": leg.get("role"),
            "provider": provider,
            "model_or_selector": selector,
            "recosted_here": blind,
            "usage": {k: (leg.get("usage") or {}).get(k)
                      for k in ("input_tokens", "output_tokens")},
            **{k: views[k] for k in ("token_cost_usd", "marginal_operating_usd",
                                     "fully_allocated_usd")},
        })

    unpriced = [p["leg_id"] for p in priced
                if p["marginal_operating_usd"].get("value") is None]
    if unpriced:
        # The per-leg figures stand and are kept — a Gemini executor's cost is a
        # real derivation even when its conductor never reported tokens. What is
        # refused is the run-level TOTAL, which would be a partial sum.
        return dict(record, status="partial", legs=priced,
                    pricing_snapshot=loaded["snapshot"],
                    marginal_operating_usd={
                        "value": None, "confidence": "unavailable",
                        "reason": f"leg(s) {', '.join(unpriced)} report no usage; "
                                  "run total not zero-filled"},
                    reason=f"per-leg only: {', '.join(unpriced)} unpriceable")

    total = round(sum(p["marginal_operating_usd"]["value"] for p in priced), 10)
    return dict(record, status="priced", legs=priced,
                pricing_snapshot=loaded["snapshot"],
                marginal_operating_usd={
                    "value": total, "confidence": "derived",
                    "qualifier": SUPPORTED_QUALIFIER, "bound": "upper",
                    "reason": ("provider-side counts (authoritative) attributed to a "
                               "serialized run window (derived); cache classes not "
                               "metered by this publisher, so this is an upper bound")})


def scan(results_root: str, datasets: List[str], pricing_root: str
         ) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for dataset in datasets:
        ds_dir = os.path.join(results_root, dataset)
        if not os.path.isdir(ds_dir):
            continue
        for name in sorted(os.listdir(ds_dir)):
            run_dir = os.path.join(ds_dir, name)
            if not os.path.isfile(os.path.join(run_dir, "summary.json")):
                continue
            record = recost_run(run_dir, pricing_root)
            record["dataset"] = dataset
            record["run_dir"] = run_dir
            out.append(record)
    return out


def write_sidecars(records: List[Dict[str, Any]]) -> int:
    """Write ``recost.json`` beside every run that got a figure. Skips are silent.

    A skipped run gets no file: an empty sidecar on a Product-A run would read as
    "we looked and found nothing", when the truth is the runner already priced it.
    A REFUSAL does get one — that is a finding about this pass.
    """
    written = 0
    for record in records:
        if record["status"] == "skipped":
            continue
        payload = {k: v for k, v in record.items() if k != "run_dir"}
        with open(os.path.join(record["run_dir"], RECOST_FILE), "w",
                  encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        written += 1
    return written


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results", nargs="?", default="results")
    ap.add_argument("--dataset", action="append", required=True)
    ap.add_argument("--pricing-root", default=os.path.join(_REPO, "pricing"))
    ap.add_argument("--write", action="store_true",
                    help="write recost.json beside each priced or refused run")
    args = ap.parse_args(argv)

    records = scan(args.results, args.dataset, args.pricing_root)
    counts: Dict[str, int] = {}
    for record in records:
        counts[record["status"]] = counts.get(record["status"], 0) + 1
    total = sum(r["marginal_operating_usd"]["value"] for r in records
                if r["status"] == "priced")

    for record in records:
        if record["status"] == "skipped":
            continue
        if record["status"] == "priced":
            figure = "$%.6f" % record["marginal_operating_usd"]["value"]
        else:
            figure = record["reason"]
            legs = [f"{p['leg_id']} ${p['marginal_operating_usd']['value']:.6f}"
                    for p in record.get("legs", [])
                    if p["marginal_operating_usd"].get("value") is not None]
            if legs:
                figure += " | " + ", ".join(legs)
        print(f"  {record['status']:8s} {record['dataset']}/{record['run_id']}: {figure}")
    print(json.dumps({"counts": counts,
                      "priced_total_usd_upper_bound": round(total, 6)}, indent=2))
    if args.write:
        print(f"wrote {write_sidecars(records)} {RECOST_FILE} sidecar(s)")
    else:
        print("dry run — pass --write to record these beside the runs")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
