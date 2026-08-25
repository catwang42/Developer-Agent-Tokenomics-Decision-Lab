"""The cross-dataset consolidator must supersede, not pool — and say what it lost.

Every fixture here is SYNTHETIC and lives only in a temp directory. The invariants
under test are the ones that would quietly corrupt the final table if they broke:

  * a slot is ``(task, arm, rep)``, and a later dataset replaces only the reps it
    actually re-ran — never a whole cell;
  * a truncated or voided run never fills a slot, and never supersedes a good one;
  * a slot with no filling run is a HOLE, reported with which kind it is;
  * a cost that is a floor is not entered into a median as if it were a total;
  * a run with no extractable quality score is absent from the median, not a zero.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.analysis import consolidate as C  # noqa: E402
from harness.collectors.vertex_token_collector import (  # noqa: E402
    ATTRIBUTION_METHOD_V2,
    ATTRIBUTION_METHOD_V3,
    BACKFILL_EVENT,
    BACKFILL_EVENT_V2,
    BACKFILL_EVENT_V3,
    REFUSAL_MARKERS,
)
from harness.telemetry.costing import CACHE_BLIND  # noqa: E402

SYNTHETIC = "SYNTHETIC test fixture — not a measurement"

#: Artifacts as each collector version ACTUALLY wrote them, which is what the reader
#: has to cope with — not a tidied-up common shape. v1 wrote no ownership statement at
#: all, v2 wrote one that predates the ``rule`` field, and only v3 names the rule.
_ATTRIBUTION_AS_WRITTEN = {
    "v1": {},
    "v2": {"attribution_rule": {"id": ATTRIBUTION_METHOD_V2}},
    "v3": {"attribution_rule": {"id": ATTRIBUTION_METHOD_V3, "rule": "v3"}},
}
_EVENT_TYPE = {"v1": BACKFILL_EVENT, "v2": BACKFILL_EVENT_V2, "v3": BACKFILL_EVENT_V3}
_MARKER = dict(REFUSAL_MARKERS)


def _as_rules(spec):
    return () if spec is None else ((spec,) if isinstance(spec, str) else tuple(spec))


def _slot(value, confidence="derived", **extra):
    return {"value": value, "confidence": confidence, **extra}


class _Lab:
    """A throwaway ``results/`` tree."""

    def __init__(self, root):
        self.root = root

    def run(self, dataset, task, config, rep, stamp, *, accepted=True,
            legs=((0.5,),), truncated=None, void=False, quality=None,
            product_b_legs=(), backfill=None, refusal=None):
        run_id = f"{task}__{config}__rep{rep}__{stamp}"
        run_dir = os.path.join(self.root, dataset, run_id)
        os.makedirs(run_dir)
        summary = {
            "SYNTHETIC": SYNTHETIC,
            "run_id": run_id, "task_id": task, "configuration_id": config,
            "acceptance": {"result": "accepted" if accepted else "rejected"},
            "economics": {"cost_basis": "marginal_api_cost",
                          "pricing_snapshot": "SYNTHETIC-prices.json"},
            "legs": [{"leg_id": f"leg{i}", "role": "solo",
                      "marginal_operating_usd": (
                          _slot(cost[0]) if cost[0] is not None
                          else _slot(None, "unavailable", reason=SYNTHETIC)),
                      "fully_allocated_usd": (
                          _slot(cost[0]) if cost[0] is not None
                          else _slot(None, "unavailable", reason=SYNTHETIC)),
                      # What marks a leg as Product B's, here and in recost.py alike.
                      **({"cost_basis_qualifier": CACHE_BLIND}
                         if i in product_b_legs else {})}
                     for i, cost in enumerate(legs)],
        }
        with open(os.path.join(run_dir, "summary.json"), "w", encoding="utf-8") as fh:
            json.dump(summary, fh)
        with open(os.path.join(run_dir, "events.jsonl"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"event": "start", "ts": "2026-08-20T10:00:00+00:00"})
                     + "\n")
            fh.write(json.dumps({"event": "acceptance",
                                 "ts": "2026-08-20T10:01:00+00:00",
                                 **({"stop_reason": truncated} if truncated else {})})
                     + "\n")
            for rule in _as_rules(backfill):
                fh.write(json.dumps({"event_type": _EVENT_TYPE[rule],
                                     "ts": "2026-08-20T11:00:00+00:00",
                                     **_ATTRIBUTION_AS_WRITTEN[rule]}) + "\n")
        for rule in _as_rules(refusal):
            with open(os.path.join(run_dir, _MARKER[rule]), "w",
                      encoding="utf-8") as fh:
                json.dump({"SYNTHETIC": SYNTHETIC, "refusal": "contaminated_window",
                           **_ATTRIBUTION_AS_WRITTEN[rule]}, fh)
        # Truncation is read from the archived product, not from a flag: an absent or
        # empty diff IS the signal, so the fixture writes what the harness would.
        with open(os.path.join(run_dir, "agent-solution.diff"), "w",
                  encoding="utf-8") as fh:
            fh.write("" if truncated else "--- a/x\n+++ b/x\n")
        if void:
            self.adjudicate(dataset, run_id)
        if quality is not None:
            with open(os.path.join(run_dir, C.QUALITY_FILE), "w",
                      encoding="utf-8") as fh:
                json.dump({"SYNTHETIC": SYNTHETIC, **quality}, fh)
        return run_dir

    def adjudicate(self, dataset, run_id):
        path = os.path.join(self.root, dataset, "adjudication.json")
        doc = {"documented_in": "SYNTHETIC", "entries": []}
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        doc["entries"].append({"scope": {"run_id": run_id}, "disposition": "void",
                               "label": "SYNTHETIC void", "reason": SYNTHETIC})
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)


def _scored(score, maximum=6, **detail):
    return {"available": True, "score": score, "max": maximum,
            "metric": "SYNTHETIC_metric", "detail": detail}


class Supersession(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="SYNTHETIC-consolidate-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.lab = _Lab(self.root)
        self.datasets = ["screening-batch1", "screening-batch1-makeup"]

    def slots(self):
        return C.collect_slots(self.root, self.datasets)

    def test_a_makeup_replaces_only_the_rep_it_re_ran(self):
        # The whole point of a per-rep slot. A makeup that re-ran rep 1 must not
        # displace reps 2 and 3, which were never lost.
        self.lab.run("screening-batch1", "t", "P0", 1, "20260818T000000",
                     truncated="claude_timeout")
        self.lab.run("screening-batch1", "t", "P0", 2, "20260818T010000")
        self.lab.run("screening-batch1", "t", "P0", 3, "20260818T020000")
        self.lab.run("screening-batch1-makeup", "t", "P0", 1, "20260820T000000")

        slots = self.slots()
        self.assertEqual(3, len(slots))
        filled = {key: slot["authoritative"]["dataset"]
                  for key, slot in slots.items() if slot["authoritative"]}
        self.assertEqual({("t", "P0", 1): "screening-batch1-makeup",
                          ("t", "P0", 2): "screening-batch1",
                          ("t", "P0", 3): "screening-batch1"}, filled)

    def test_a_truncated_makeup_does_not_displace_a_good_original(self):
        # Recency alone must not win. A re-run that the harness cut off is not a
        # newer measurement; it is not a measurement.
        self.lab.run("screening-batch1", "t", "P0", 1, "20260818T000000")
        self.lab.run("screening-batch1-makeup", "t", "P0", 1, "20260820T000000",
                     truncated="claude_timeout")
        slot = self.slots()[("t", "P0", 1)]
        self.assertEqual("screening-batch1", slot["authoritative"]["dataset"])
        self.assertIsNone(slot["hole"])

    def test_a_voided_run_does_not_fill_a_slot(self):
        self.lab.run("screening-batch1", "t", "P0", 1, "20260818T000000", void=True)
        slot = self.slots()[("t", "P0", 1)]
        self.assertIsNone(slot["authoritative"])
        self.assertEqual(C.UNREPLACED_LOSS, slot["hole"]["kind"])

    def test_one_truncated_attempt_is_a_loss_two_is_a_finding(self):
        # "Ran out of time once" is missing data. "Re-bought it and ran out again"
        # is the result — and the ledger must not round either into the other.
        self.lab.run("screening-batch1", "t", "P0", 1, "20260818T000000",
                     truncated="claude_timeout")
        self.lab.run("screening-batch1", "t", "P1", 1, "20260818T000000",
                     truncated="claude_timeout")
        self.lab.run("screening-batch1-makeup", "t", "P1", 1, "20260820T000000",
                     truncated="claude_timeout")
        slots = self.slots()
        self.assertEqual(C.UNREPLACED_LOSS, slots[("t", "P0", 1)]["hole"]["kind"])
        self.assertEqual(C.BUDGET_EXHAUSTION, slots[("t", "P1", 1)]["hole"]["kind"])

    def test_a_void_attempt_does_not_make_a_loss_look_like_exhaustion(self):
        # W6's batch-1 cells are void: the agent got no review_diff, so the run says
        # nothing about whether the budget was enough. Counting it as an attempt
        # would report one real timeout as "we bought it twice and it still failed",
        # and would then justify not re-buying a slot that has never had a fair go.
        self.lab.run("screening-batch1", "t", "C2", 2, "20260818T000000",
                     truncated="zero-byte", void=True)
        self.lab.run("screening-batch1-makeup", "t", "C2", 2, "20260820T000000",
                     truncated="claude_timeout")
        hole = self.slots()[("t", "C2", 2)]["hole"]
        self.assertEqual(C.UNREPLACED_LOSS, hole["kind"])
        # Both attempts are still named — the void one is provenance, not deleted.
        self.assertEqual(2, len(hole["attempts"]))

    def test_a_non_evidence_dataset_is_not_pooled_in(self):
        # A smoke run must never fill a slot a real run lost.
        self.lab.run("smoke-whatever", "t", "P0", 1, "20260820T000000")
        self.assertEqual({}, C.collect_slots(self.root, self.datasets + ["smoke-whatever"]))


class CellFigures(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="SYNTHETIC-consolidate-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.lab = _Lab(self.root)

    def _runs(self, dataset="screening-batch1"):
        slots = C.collect_slots(self.root, [dataset])
        return [s["authoritative"] for _, s in sorted(slots.items())
                if s["authoritative"]]

    def test_a_floor_is_not_entered_into_the_cost_median(self):
        # A dual-billed run whose conductor reported nothing sums to one leg's price.
        # Averaging that beside complete runs would report the cell as half its cost.
        self.lab.run("screening-batch1", "t", "C5", 1, "20260818T000000",
                     legs=((10.0,), (10.0,)))
        self.lab.run("screening-batch1", "t", "C5", 2, "20260818T010000",
                     legs=((10.0,), (10.0,)))
        self.lab.run("screening-batch1", "t", "C5", 3, "20260818T020000",
                     legs=((10.0,), (None,)))
        cost = C.cell_cost(self._runs())
        self.assertEqual(20.0, cost["median_usd"])
        self.assertEqual(2, cost["n"])
        self.assertEqual(3, cost["of_runs"])
        self.assertEqual(1, cost["runs_partially_costed"])

    def test_a_run_with_no_priced_leg_is_uncosted_not_zero(self):
        self.lab.run("screening-batch1", "t", "P0", 1, "20260818T000000",
                     legs=((None,),))
        cost = C.cell_cost(self._runs())
        self.assertIsNone(cost["median_usd"])
        self.assertEqual(1, cost["runs_uncosted"])
        self.assertEqual(0, cost["n"])

    def test_an_unscored_run_is_absent_from_the_quality_median_not_a_zero(self):
        self.lab.run("screening-batch1", "t", "P0", 1, "20260818T000000",
                     quality=_scored(6))
        self.lab.run("screening-batch1", "t", "P0", 2, "20260818T010000",
                     quality=_scored(4))
        self.lab.run("screening-batch1", "t", "P0", 3, "20260818T020000",
                     quality={"available": False, "score": None,
                              "reason": "SYNTHETIC: nothing extractable"})
        quality = C.cell_quality(self._runs())
        self.assertEqual(5, quality["median"])   # not (6+4+0)/3
        self.assertEqual(2, quality["n"])
        self.assertEqual(3, quality["of_runs"])

    def test_fabrications_are_counted_alongside_the_score_never_netted_off(self):
        self.lab.run("screening-batch1", "t", "P0", 1, "20260818T000000",
                     quality=_scored(6, fabrication_count=1))
        quality = C.cell_quality(self._runs())
        self.assertEqual(6, quality["median"])
        self.assertEqual(1, quality["fabrications_total"])

    def test_quality_declares_itself_secondary(self):
        self.assertIn("EXPLORATORY SECONDARY", C.cell_quality([])["status"])


class WhichWindowingRulePricedTheCell(unittest.TestCase):
    """A cost figure means nothing without the rule that drew its window.

    Batch 1's Product-B legs were attributed under v1 and v2, the confound makeup
    under v3. Two cells priced under two rules are two instruments, and a table that
    prints their costs side by side unlabelled manufactures the exact confound this
    repo exists to catch.
    """

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="SYNTHETIC-consolidate-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.lab = _Lab(self.root)
        self.datasets = ["screening-batch1", "screening-batch1-confound-makeup"]

    def _cell(self, task="t", config="C3"):
        cells = {(c["task_id"], c["configuration_or_policy"]): c
                 for c in C.build(self.root, self.datasets)["cells"]}
        return cells[(task, config)]

    def test_a_cell_under_one_rule_names_that_rule(self):
        for rep in (1, 2, 3):
            self.lab.run("screening-batch1-confound-makeup", "t", "C3", rep,
                         f"2026082{rep}T000000", product_b_legs=(0,), backfill="v3")
        cell = self._cell()
        self.assertEqual(["v3"], cell["attribution"]["rules"])
        self.assertFalse(cell["cost_rule_mixed"])
        self.assertEqual("v3", C._fmt_rules(cell))

    def test_a_cell_filled_from_two_datasets_declares_both_rules(self):
        # Exactly the shape supersession produces: reps 2 and 3 survive from batch 1
        # under v1, rep 1 was re-run in the confound makeup under v3. Both are the
        # cell's own reps; neither is dropped, and the median spans both instruments.
        self.lab.run("screening-batch1", "t", "C3", 2, "20260818T010000",
                     product_b_legs=(0,), backfill="v1")
        self.lab.run("screening-batch1", "t", "C3", 3, "20260818T020000",
                     product_b_legs=(0,), backfill="v1")
        self.lab.run("screening-batch1-confound-makeup", "t", "C3", 1,
                     "20260821T000000", product_b_legs=(0,), backfill="v3")
        cell = self._cell()
        self.assertEqual(["v1", "v3"], cell["attribution"]["rules"])
        self.assertTrue(cell["cost_rule_mixed"])
        # The mark is what tells a reader the median is not a like-for-like figure.
        self.assertEqual("v1,v3 ⚠", C._fmt_rules(cell))

    def test_a_v2_statement_predating_the_rule_field_is_read_from_its_method_id(self):
        # The archived v2 artifacts carry an ownership dict with an ``id`` and no
        # ``rule``. Reading only ``rule`` would render them unavailable; defaulting
        # them to v2 would be an inference. The method id IS the collector's own name
        # for the rule, so it is read, not guessed.
        self.lab.run("screening-batch1", "t", "C3", 1, "20260818T000000",
                     product_b_legs=(0,), backfill="v2")
        self.assertEqual(["v2"], self._cell()["attribution"]["rules"])

    def test_a_refusal_only_run_still_names_the_rule_it_was_refused_under(self):
        # A refused window means the tokens are unavailable. It does NOT mean no rule
        # was drawn — filing it as ruleless would read as though the cell had never
        # been put to the instrument at all.
        self.lab.run("screening-batch1-confound-makeup", "t", "C3", 1,
                     "20260821T000000", legs=((None,),), product_b_legs=(0,),
                     refusal="v3")
        cell = self._cell()
        self.assertEqual(["v3"], cell["attribution"]["rules"])
        self.assertEqual(["v3"], cell["attribution"]["refused"])
        self.assertEqual([], cell["attribution"]["attributed"])
        self.assertEqual("v3", C._fmt_rules(cell))

    def test_a_v1_refusal_beside_a_v2_attribution_keeps_both(self):
        # Four archived runs are in exactly this state. Both records stand: the two
        # rules draw different windows, so one refusing is not overturned by the
        # other attributing.
        self.lab.run("screening-batch1", "t", "C3", 1, "20260818T000000",
                     product_b_legs=(0,), backfill="v2", refusal="v1")
        cell = self._cell()
        self.assertEqual(["v1", "v2"], cell["attribution"]["rules"])
        self.assertEqual(["v2"], cell["attribution"]["attributed"])
        self.assertEqual(["v1"], cell["attribution"]["refused"])
        self.assertTrue(cell["cost_rule_mixed"])

    def test_an_arm_with_no_product_b_leg_reads_n_a_not_unavailable(self):
        # Nothing is missing for a Product-A-only arm: no provider window was ever
        # drawn for it. Printing "unavailable" would invent a gap in the record.
        self.lab.run("screening-batch1", "t", "P0", 1, "20260818T000000")
        cell = self._cell(config="P0")
        self.assertEqual([], cell["attribution"]["rules"])
        self.assertEqual(0, cell["attribution"]["product_b_runs"])
        self.assertEqual(C.RULE_NOT_APPLICABLE, C._fmt_rules(cell))
        self.assertFalse(cell["cost_rule_mixed"])

    def test_a_product_b_run_with_no_artifact_is_unavailable_never_a_siblings_rule(self):
        # CLAUDE.md rule 3. The other two reps ran under v3; that says nothing about
        # this one, and filling it in would fabricate a provenance.
        for rep in (1, 2):
            self.lab.run("screening-batch1-confound-makeup", "t", "C3", rep,
                         f"2026082{rep}T000000", product_b_legs=(0,), backfill="v3")
        self.lab.run("screening-batch1-confound-makeup", "t", "C3", 3,
                     "20260823T000000", product_b_legs=(0,))
        cell = self._cell()
        self.assertEqual(1, cell["attribution"]["product_b_runs_without_rule"])
        self.assertEqual(3, cell["attribution"]["product_b_runs"])
        self.assertEqual("v3,unavailable ⚠", C._fmt_rules(cell))
        # ...but the cell is not CLAIMED to span two rules. It might well be all v3;
        # what is true is that nobody knows, and the ⚠ says that much and no more.
        self.assertFalse(cell["cost_rule_mixed"])

    def test_a_cell_with_no_run_at_all_claims_neither_a_rule_nor_its_absence(self):
        for rep in (1, 2):
            self.lab.run("screening-batch1", "t", "C5", rep, f"2026081{rep}T000000",
                         truncated="claude_timeout")
        self.assertEqual("—", C._fmt_rules(self._cell(config="C5")))


class AnUnavailableCostSaysWhy(unittest.TestCase):
    """A bare "unavailable" is indistinguishable from "we did not look"."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="SYNTHETIC-consolidate-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.lab = _Lab(self.root)

    def _cell(self, task="t", config="C3"):
        cells = {(c["task_id"], c["configuration_or_policy"]): c
                 for c in C.build(self.root, ["screening-batch1"])["cells"]}
        return cells[(task, config)]

    def test_a_refused_window_is_named_with_the_rule_that_refused_it(self):
        self.lab.run("screening-batch1", "t", "C3", 1, "20260818T000000",
                     legs=((None,),), product_b_legs=(0,), refusal="v3")
        self.assertEqual("unavailable — no priced leg; provider window refused (v3)",
                         C._fmt_cost(self._cell()))

    def test_a_partly_priced_cell_says_how_many_legs_went_unpriced(self):
        # The run is excluded from the median for having an unpriced leg — that
        # exclusion is unchanged. What is new is that the row says so.
        self.lab.run("screening-batch1", "t", "C5", 1, "20260818T000000",
                     legs=((10.0,), (None,)), product_b_legs=(1,))
        self.assertEqual("unavailable — partial: 1 of 2 legs unpriced",
                         C._fmt_cost(self._cell(config="C5")))

    def test_no_usage_record_at_all_says_exactly_that(self):
        self.lab.run("screening-batch1", "t", "C3", 1, "20260818T000000",
                     legs=((None,),), product_b_legs=(0,))
        self.assertEqual("unavailable — no provider usage record",
                         C._fmt_cost(self._cell()))

    def test_a_cell_no_run_filled_is_not_dressed_up_as_a_missing_meter(self):
        for rep in (1, 2):
            self.lab.run("screening-batch1", "t", "C5", rep, f"2026081{rep}T000000",
                         truncated="claude_timeout")
        self.assertEqual("unavailable — no run filled this cell",
                         C._fmt_cost(self._cell(config="C5")))

    def test_a_priced_cell_renders_exactly_what_it_rendered_before(self):
        # The whole change is presentation on the unavailable path. A cell that has a
        # figure must render byte-for-byte what it did before, reason strings and all.
        for rep in (1, 2, 3):
            self.lab.run("screening-batch1", "t", "C3", rep, f"2026081{rep}T000000",
                         legs=((0.25,),), product_b_legs=(0,), backfill="v3")
        self.assertEqual("$0.2500", C._fmt_cost(self._cell()))

    def test_the_upper_bound_marker_still_rides_on_the_cell_not_the_run(self):
        # One cache-blind figure bounds the whole cell; it is not diluted by the
        # exactly-priced runs beside it. Marked from the cell's cost provenance, which
        # this pass does not touch.
        self.lab.run("screening-batch1", "t", "C3", 1, "20260818T000000",
                     legs=((0.25,),))
        cell = dict(self._cell(), cost_provenance={"any_upper_bound": True})
        self.assertTrue(C._has_upper_bound(cell))
        self.assertEqual("≤$0.2500", C._fmt_cost(cell))


class TheTableReportsWhatIsMissing(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="SYNTHETIC-consolidate-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.lab = _Lab(self.root)

    def _build(self):
        return C.build(self.root, ["screening-batch1", "screening-batch1-makeup"])

    def test_a_cell_every_rep_lost_still_appears_with_no_verdict(self):
        # The cells that failed hardest are exactly the ones a "skip the empties"
        # table would drop, so the reader would never learn they existed.
        for rep in (1, 2, 3):
            self.lab.run("screening-batch1", "t", "C5", rep, f"2026081{rep}T000000",
                         truncated="claude_timeout")
        table = self._build()
        cell = table["cells"][0]
        self.assertEqual("C5", cell["configuration_or_policy"])
        self.assertEqual(0, cell["reps_filled"])
        self.assertEqual(3, cell["reps_registered"])
        self.assertEqual("no gradable run", cell["acceptance"]["display"])
        self.assertIn("t::C5", table["ledger"]["cells_with_no_evidence"])

    def test_an_understrength_cell_is_named_with_its_n(self):
        self.lab.run("screening-batch1", "t", "P0", 1, "20260818T000000")
        self.lab.run("screening-batch1", "t", "P0", 2, "20260818T010000",
                     truncated="claude_timeout")
        entries = self._build()["ledger"]["cells_with_understrength_n"]
        self.assertEqual(["t::P0 (1/2)"], entries)

    def test_the_ledger_separates_a_finding_from_a_gap(self):
        self.lab.run("screening-batch1", "t", "P1", 1, "20260818T000000",
                     truncated="claude_timeout")
        self.lab.run("screening-batch1-makeup", "t", "P1", 1, "20260820T000000",
                     truncated="claude_timeout")
        self.lab.run("screening-batch1", "t", "P0", 1, "20260818T000000",
                     truncated="claude_timeout")
        led = self._build()["ledger"]
        self.assertEqual([("t", "P1", 1)],
                         [(e["task_id"], e["configuration_id"], e["rep"])
                          for e in led["budget_exhaustion"]])
        self.assertEqual([("t", "P0", 1)],
                         [(e["task_id"], e["configuration_id"], e["rep"])
                          for e in led["unreplaced_loss"]])
        # Both attempts are named, so the finding can be read without the archive.
        self.assertEqual(2, len(led["budget_exhaustion"][0]["attempts"]))

    def _defer(self, dataset, task, config, rep, stamp, slot_no=1):
        path = os.path.join(self.root, dataset, "deferred-contaminated.tsv")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{stamp}\t{slot_no}\t{task}\t{config}\trep{rep}\n")

    def test_a_deferred_rep_is_counted_in_the_denominator(self):
        # A rep the contamination guard refused leaves no run directory. Counting only
        # what ran would print "2/2" for a cell that is missing a third of its design,
        # and every median in that row would read as complete when it is not.
        for rep in (1, 2):
            self.lab.run("screening-batch1", "t", "C3", rep, f"2026081{rep}T000000")
        self._defer("screening-batch1", "t", "C3", 3, "20260818T021521")
        cell = self._build()["cells"][0]
        self.assertEqual(2, cell["reps_filled"])
        self.assertEqual(3, cell["reps_registered"])
        self.assertEqual([3], cell["reps_deferred_contaminated"])

    def test_a_refused_slot_is_not_filed_as_never_rebought(self):
        # The slot was lost in batch 1 AND re-bought; the guard then refused it. Filing
        # it under "never re-bought" would say we did not try, and would invite buying
        # a slot whose real blocker is the measurement window, not the budget.
        self.lab.run("screening-batch1", "t", "C5", 1, "20260818T000000",
                     truncated="claude_timeout")
        self._defer("screening-batch1-makeup", "t", "C5", 1, "20260821T100622")
        led = self._build()["ledger"]
        self.assertEqual([], led["unreplaced_loss"])
        self.assertEqual([("t", "C5", 1)],
                         [(e["task_id"], e["configuration_id"], e["rep"])
                          for e in led["deferred_contaminated"]])
        # The earlier truncation travels with it — the loss is still on the record.
        self.assertEqual(1, len(led["deferred_contaminated"][0]["attempts"]))

    def test_a_deferral_written_as_a_task_dir_lands_on_the_task_id(self):
        # Batch 1's driver wrote the task directory in this column; later drivers write
        # the task id. Left unmapped, the batch-1 rows would name a task that appears
        # nowhere else in the table and could never be reconciled with a cell.
        registry = {"pilot-realworld-draft-articles": {"task_dir": "tasks/pilot-realworld"}}
        self._defer("screening-batch1", "tasks/pilot-realworld", "C3", 3,
                    "20260818T021521")
        rows = C.deferred_contaminated(self.root, ["screening-batch1"], registry)
        self.assertEqual("pilot-realworld-draft-articles", rows[0]["task_id"])
        self.assertEqual("tasks/pilot-realworld", rows[0]["task_as_written"])

    def test_the_rendered_table_carries_the_pending_banner_and_the_cp_gate(self):
        self.lab.run("screening-batch1", "t", "P0", 1, "20260818T000000")
        table = self._build()
        md = C.render(table, generated_at="2026-08-21T00:00:00Z",
                      harness_head="SYNTHETIC")
        self.assertIn("STATUS: PENDING", md)
        self.assertIn("CP-FINDINGS", md)
        self.assertIn("EXPLORATORY SECONDARY", md)
        self.assertIn("Limitation ledger", md)

    def test_a_superseded_run_is_named_not_silently_dropped(self):
        self.lab.run("screening-batch1", "t", "P0", 1, "20260818T000000",
                     truncated="claude_timeout")
        self.lab.run("screening-batch1-makeup", "t", "P0", 1, "20260820T000000")
        table = self._build()
        self.assertEqual(1, table["n_runs_superseded"])
        self.assertEqual(["t__P0__rep1__20260818T000000"],
                         table["cells"][0]["superseded_runs"])


if __name__ == "__main__":
    unittest.main()
