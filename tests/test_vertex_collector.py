"""Tests for the provider-side Vertex token collector.

Everything here runs offline: the monitoring client is a fake that replays
SYNTHETIC time-series fixtures, and every run directory is built in a tempdir.
No network, no credentials, no model call, no spend.

The invariants under test are the ones that would quietly corrupt a cost figure:
window attribution, per-model leg split, backfill after ingestion lag,
unmapped-type flagging, and — the load-bearing one — that a class nobody reported
stays *unavailable* rather than becoming 0.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.collectors import vertex_token_collector as vtc  # noqa: E402
from harness.telemetry.telemetry import (  # noqa: E402
    EventLog,
    derive_summary,
    read_events,
    tiered,
    unavailable,
    validate,
)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures",
                       "vertex-timeseries-SYNTHETIC.json")

RUN_START = "2026-08-16T10:00:00Z"
RUN_END = "2026-08-16T10:05:00Z"
COLLECTED_AT = "2026-08-16T10:30:00Z"

GEMINI = "SYNTHETIC-gemini-flash"
CLAUDE = "SYNTHETIC-claude-strong"


def _fixture(scenario):
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)[scenario]


class FakeMonitoringClient(vtc.MonitoringClient):
    """Replays a fixture scenario and records what it was asked for."""

    def __init__(self, series):
        self.series = series
        self.calls = []

    def list_time_series(self, project, filter_str, window):
        self.calls.append({"project": project, "filter": filter_str, "window": window})
        return self.series


def _aggregate(scenario, guard=vtc.DEFAULT_GUARD_SECONDS):
    window = vtc.build_window(RUN_START, RUN_END, guard)
    return vtc.aggregate_series(_fixture(scenario), window, guard)


class RunDirMixin:
    """Builds a SYNTHETIC run directory whose Product-B usage is unavailable."""

    def make_run(self, legs=("main",), config_id="C3"):
        run_dir = tempfile.mkdtemp(prefix="SYNTHETIC-run-")
        self.addCleanup(shutil.rmtree, run_dir, True)
        log = EventLog(os.path.join(run_dir, "events.jsonl"))
        for i, leg in enumerate(legs):
            log.append("model_call_started", RUN_START, leg=leg)
            log.append(
                "model_call_completed", f"2026-08-16T10:0{i + 1}:00Z", leg=leg,
                role=leg,
                provider=tiered("SYNTHETIC-provider", "authoritative"),
                model_or_selector=tiered(f"SYNTHETIC-selector-{leg}", "authoritative"),
                cost_basis="provider_reported_cost",
                usage={cls: unavailable("product exposes no usage headless")
                       for cls in ("input_tokens", "output_tokens",
                                   "cache_read_tokens", "cache_creation_tokens")},
            )
        log.append("acceptance", RUN_END, result="accepted", gate_checks={})
        events = list(read_events(log.path))
        summary = derive_summary(
            events, run_id="SYNTHETIC-run-0001", task_id="SYNTHETIC-task",
            task_suite_version="SYNTHETIC", configuration_id=config_id,
            manifest_ref="tests/fixtures/manifest-SYNTHETIC.yaml",
            economics={"cost_basis": "cost_unavailable"},
        )
        with open(os.path.join(run_dir, "summary.json"), "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, sort_keys=True)
        ok, reasons = validate(run_dir)
        assert ok, f"fixture run is not audit-grade before backfill: {reasons}"
        return run_dir

    @staticmethod
    def summary_of(run_dir):
        with open(os.path.join(run_dir, "summary.json"), encoding="utf-8") as fh:
            return json.load(fh)


# --------------------------------------------------------------------------- #
class QueryConstructionTests(unittest.TestCase):

    def test_filter_names_the_metric_resource_publisher_and_models(self):
        f = vtc.build_filter([GEMINI])
        self.assertIn(f'metric.type = "{vtc.METRIC_TYPE}"', f)
        self.assertIn(f'resource.type = "{vtc.MONITORED_RESOURCE}"', f)
        self.assertIn('resource.labels.publisher = "google"', f)
        self.assertIn(f'resource.labels.model_user_id = "{GEMINI}"', f)

    def test_multiple_models_use_one_of(self):
        f = vtc.build_filter([CLAUDE, GEMINI])
        self.assertIn("one_of(", f)
        self.assertIn(f'"{CLAUDE}"', f)
        self.assertIn(f'"{GEMINI}"', f)

    def test_one_of_is_comma_separated_not_or_separated(self):
        """Regression, observed live 2026-08-17.

        ``one_of("a" OR "b")`` is not a laxer spelling of ``one_of("a","b")`` —
        the Monitoring API rejects the entire filter with HTTP 400 "Could not
        parse filter", so every multi-model run (i.e. every C5) failed collection
        outright. The old assertions passed on the broken form because they only
        checked for substrings, so this test pins the separator itself.
        """
        f = vtc.build_filter([CLAUDE, GEMINI])
        self.assertIn(f'one_of("{CLAUDE}","{GEMINI}")', f)
        self.assertNotIn(" OR ", f)

    def test_a_mixed_publisher_run_queries_both_publishers(self):
        """A C5 conductor is an Anthropic publisher model and its executor a
        Google one. Pinning the filter to publisher="google" returns nothing for
        the conductor — silently, which is the dangerous kind of nothing."""
        f = vtc.build_filter([CLAUDE, GEMINI], {"anthropic", "google"})
        self.assertIn('resource.labels.publisher = one_of("anthropic","google")', f)

    def test_a_publisher_is_declared_per_leg_and_never_inferred(self):
        plan = vtc.RunPlan.from_dict({
            "run_dir": "results/x/run",
            "legs": {"conductor": {"model_user_id": CLAUDE, "publisher": "anthropic"},
                     "executor": GEMINI},
        })
        self.assertEqual(plan.legs, {"conductor": CLAUDE, "executor": GEMINI})
        self.assertEqual(plan.publisher_for("conductor"), "anthropic")
        # a bare string leg keeps the historical default rather than guessing
        self.assertEqual(plan.publisher_for("executor"), vtc.DEFAULT_PUBLISHER)

    def test_a_leg_object_without_a_model_is_refused(self):
        with self.assertRaises(vtc.CollectorError):
            vtc.RunPlan.from_dict({"run_dir": "results/x/run",
                                   "legs": {"main": {"publisher": "google"}}})

    def test_an_unfiltered_query_is_refused(self):
        """Without a model filter the query would sweep up every workload in the
        project — the exact failure the quiet-window rule exists to prevent."""
        with self.assertRaises(vtc.CollectorError):
            vtc.build_filter([])

    def test_window_applies_the_guard_on_both_sides(self):
        lo, hi = vtc.build_window(RUN_START, RUN_END, 60)
        self.assertEqual(vtc.format_ts(lo)[:19], "2026-08-16T09:59:00")
        self.assertEqual(vtc.format_ts(hi)[:19], "2026-08-16T10:06:00")

    def test_a_naive_timestamp_is_refused_rather_than_assumed_utc(self):
        with self.assertRaises(vtc.CollectorError):
            vtc.parse_ts("2026-08-16T10:00:00")

    def test_a_backwards_window_is_refused(self):
        with self.assertRaises(vtc.CollectorError):
            vtc.build_window(RUN_END, RUN_START, 60)


class WindowAttributionTests(unittest.TestCase):

    def test_points_outside_the_guarded_window_are_excluded_and_counted(self):
        result = _aggregate("window_edges")
        self.assertEqual(result.by_model[GEMINI].totals_by_type, {"input": 250},
                         "only the point inside the guard tail may be counted")
        self.assertEqual(result.points_outside_window, 2)
        self.assertEqual(result.points_in_window, 1)

    def test_a_zero_guard_excludes_the_guard_band_point(self):
        result = _aggregate("window_edges", guard=0)
        self.assertNotIn(GEMINI, result.by_model)
        self.assertEqual(result.points_outside_window, 3)

    def test_a_point_with_no_readable_value_raises_rather_than_counting_zero(self):
        with self.assertRaises(vtc.CollectorError):
            _aggregate("unreadable_point")


class MultiModelSplitTests(unittest.TestCase):

    def test_conductor_and_executor_split_by_model_user_id(self):
        result = _aggregate("two_models")
        self.assertEqual(result.by_model[GEMINI].totals_by_type,
                         {"input": 1500, "output": 300})
        self.assertEqual(result.by_model[CLAUDE].totals_by_type,
                         {"input": 2000, "cache_read_input": 800,
                          "cache_write_1h_input": 400, "output": 600})

    def test_the_full_label_set_of_each_contributing_series_is_preserved(self):
        result = _aggregate("two_models")
        breakdown = result.by_model[CLAUDE].series_breakdown
        writes = [b for b in breakdown if b["labels"]["type"] == "cache_write_1h_input"]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]["labels"]["explicit_caching"], "true")
        self.assertEqual(writes[0]["labels"]["model_version_id"], "default")
        self.assertEqual(writes[0]["tokens"], 400)

    def test_type_mapping_is_exactly_the_four_pinned_classes(self):
        mapped, unmapped = vtc.usage_fields(
            _aggregate("two_models").by_model[CLAUDE].totals_by_type)
        self.assertEqual(mapped, {"input_tokens": 2000, "output_tokens": 600,
                                  "cache_read_tokens": 800,
                                  "cache_creation_tokens": 400})
        self.assertEqual(unmapped, {})


class UnmappedTypeTests(unittest.TestCase):
    """Never drop, never zero, never fold into a mapped class."""

    def test_unmapped_types_are_reported_and_never_counted(self):
        result = _aggregate("unmapped_types")
        mapped, unmapped = vtc.usage_fields(result.by_model[GEMINI].totals_by_type)
        self.assertEqual(mapped, {"input_tokens": 1000},
                         "an unmapped type must not be folded into a token class")
        self.assertEqual(unmapped, {"SYNTHETIC-thinking": 123, "cache_write_input": 700})
        self.assertEqual(result.unmapped_types(),
                         {GEMINI: {"SYNTHETIC-thinking": 123, "cache_write_input": 700}})

    def test_the_report_surfaces_unmapped_types_at_the_top_level(self):
        report = vtc.build_report("SYNTHETIC-project", COLLECTED_AT, 60, [
            vtc.BackfillOutcome("run", "id", "backfilled",
                                unmapped_types={f"main/{GEMINI}": {"cache_write_input": 700}})])
        self.assertEqual(report["unmapped_types_observed"],
                         {f"main/{GEMINI}": {"cache_write_input": 700}})
        self.assertIn("thinking", report["unmapped_types_note"])

    def test_a_series_with_no_type_label_raises(self):
        series = json.loads(json.dumps(_fixture("two_models")[:1]))
        del series[0]["metric"]["labels"]["type"]
        with self.assertRaises(vtc.CollectorError):
            vtc.aggregate_series(series, vtc.build_window(RUN_START, RUN_END, 60), 60)


class BackfillTests(RunDirMixin, unittest.TestCase):

    def test_lag_backfill_fills_usage_and_stays_audit_grade(self):
        run_dir = self.make_run()
        before = self.summary_of(run_dir)
        self.assertIsNone(before["usage"]["input_tokens"]["value"])

        client = FakeMonitoringClient(_fixture("two_models"))
        plan = vtc.RunPlan(run_dir=run_dir, legs={"main": GEMINI},
                           start=RUN_START, end=RUN_END)
        report = vtc.run_backfill(client, "SYNTHETIC-project", [plan], COLLECTED_AT)

        self.assertEqual(report["status_counts"], {"backfilled": 1}, report["runs"])
        after = self.summary_of(run_dir)
        self.assertEqual(after["usage"]["input_tokens"]["value"], 1500)
        self.assertEqual(after["usage"]["output_tokens"]["value"], 300)
        self.assertEqual(after["usage"]["input_tokens"]["confidence"], "derived",
                         "attribution is time-window, so the field is derived")
        ok, reasons = validate(run_dir)
        self.assertTrue(ok, reasons)

    def test_backfill_adds_tokens_but_not_a_turn(self):
        run_dir = self.make_run()
        turns_before = self.summary_of(run_dir)["behavior"]["turns"]["value"]
        client = FakeMonitoringClient(_fixture("two_models"))
        vtc.run_backfill(client, "SYNTHETIC-project", [
            vtc.RunPlan(run_dir, {"main": GEMINI}, RUN_START, RUN_END)], COLLECTED_AT)
        self.assertEqual(self.summary_of(run_dir)["behavior"]["turns"]["value"],
                         turns_before)

    def test_the_original_events_are_untouched_and_provenance_is_appended(self):
        run_dir = self.make_run()
        path = os.path.join(run_dir, "events.jsonl")
        with open(path, encoding="utf-8") as fh:
            original = fh.read()
        client = FakeMonitoringClient(_fixture("two_models"))
        vtc.run_backfill(client, "SYNTHETIC-project", [
            vtc.RunPlan(run_dir, {"main": GEMINI}, RUN_START, RUN_END)], COLLECTED_AT)
        with open(path, encoding="utf-8") as fh:
            after = fh.read()
        self.assertTrue(after.startswith(original), "the event log must stay append-only")
        appended = [e for e in read_events(path)
                    if e["event_type"] == vtc.BACKFILL_EVENT]
        self.assertEqual(len(appended), 1)
        self.assertEqual(appended[0]["counts_confidence"], "authoritative")
        self.assertEqual(appended[0]["attribution_confidence"], "derived")
        self.assertEqual(appended[0]["model_user_id"], GEMINI)
        self.assertEqual(appended[0]["metric_type"], vtc.METRIC_TYPE)

    def test_two_legs_are_filled_from_their_own_models(self):
        run_dir = self.make_run(legs=("conductor", "executor"), config_id="C5")
        client = FakeMonitoringClient(_fixture("two_models"))
        vtc.run_backfill(client, "SYNTHETIC-project", [
            vtc.RunPlan(run_dir, {"conductor": CLAUDE, "executor": GEMINI},
                        RUN_START, RUN_END)], COLLECTED_AT)
        legs = {leg["leg_id"]: leg for leg in self.summary_of(run_dir)["legs"]}
        self.assertEqual(legs["conductor"]["usage"]["input_tokens"]["value"], 2000)
        self.assertEqual(legs["executor"]["usage"]["input_tokens"]["value"], 1500)
        self.assertEqual(legs["conductor"]["usage"]["cache_read_tokens"]["value"], 800)
        # Top-level usage is the sum across legs.
        self.assertEqual(self.summary_of(run_dir)["usage"]["input_tokens"]["value"], 3500)
        ok, reasons = validate(run_dir)
        self.assertTrue(ok, reasons)

    def test_legs_sharing_one_model_are_refused_not_guessed(self):
        run_dir = self.make_run(legs=("conductor", "executor"), config_id="C5")
        client = FakeMonitoringClient(_fixture("two_models"))
        report = vtc.run_backfill(client, "SYNTHETIC-project", [
            vtc.RunPlan(run_dir, {"conductor": GEMINI, "executor": GEMINI},
                        RUN_START, RUN_END)], COLLECTED_AT)
        self.assertEqual(report["status_counts"], {"error": 1})
        self.assertIn("share a model_user_id", report["runs"][0]["detail"])
        self.assertIsNone(self.summary_of(run_dir)["usage"]["input_tokens"]["value"])

    def test_backfill_is_idempotent(self):
        run_dir = self.make_run()
        plan = vtc.RunPlan(run_dir, {"main": GEMINI}, RUN_START, RUN_END)
        client = FakeMonitoringClient(_fixture("two_models"))
        vtc.run_backfill(client, "SYNTHETIC-project", [plan], COLLECTED_AT)
        second = vtc.run_backfill(client, "SYNTHETIC-project", [plan], COLLECTED_AT)
        self.assertEqual(second["status_counts"], {"skipped": 1})
        self.assertEqual(self.summary_of(run_dir)["usage"]["input_tokens"]["value"], 1500,
                         "a second pass must not double-count")

    def test_dry_run_writes_nothing(self):
        run_dir = self.make_run()
        client = FakeMonitoringClient(_fixture("two_models"))
        report = vtc.run_backfill(client, "SYNTHETIC-project", [
            vtc.RunPlan(run_dir, {"main": GEMINI}, RUN_START, RUN_END)],
            COLLECTED_AT, dry_run=True)
        self.assertEqual(report["status_counts"], {"dry_run": 1})
        self.assertIsNone(self.summary_of(run_dir)["usage"]["input_tokens"]["value"])
        self.assertEqual([e for e in read_events(os.path.join(run_dir, "events.jsonl"))
                          if e["event_type"] == vtc.BACKFILL_EVENT], [])

    def test_the_unmapped_type_reaches_the_run_event_and_the_report(self):
        run_dir = self.make_run()
        client = FakeMonitoringClient(_fixture("unmapped_types"))
        report = vtc.run_backfill(client, "SYNTHETIC-project", [
            vtc.RunPlan(run_dir, {"main": GEMINI}, RUN_START, RUN_END)], COLLECTED_AT)
        self.assertEqual(report["unmapped_types_observed"],
                         {f"main/{GEMINI}": {"SYNTHETIC-thinking": 123,
                                             "cache_write_input": 700}})
        event = [e for e in read_events(os.path.join(run_dir, "events.jsonl"))
                 if e["event_type"] == vtc.BACKFILL_EVENT][0]
        self.assertEqual(event["unmapped_types"],
                         {"SYNTHETIC-thinking": 123, "cache_write_input": 700})
        summary = self.summary_of(run_dir)
        self.assertEqual(summary["usage"]["input_tokens"]["value"], 1000)
        # 123 + 700 went nowhere near a token class, and nothing was zero-filled.
        self.assertIsNone(summary["usage"]["cache_creation_tokens"]["value"])
        self.assertEqual(summary["usage"]["cache_creation_tokens"]["confidence"],
                         "unavailable")


class NeverZeroFillTests(RunDirMixin, unittest.TestCase):
    """CLAUDE.md rule 3: unavailable is unavailable, not 0."""

    def test_an_empty_window_fills_nothing_and_says_so(self):
        run_dir = self.make_run()
        client = FakeMonitoringClient(_fixture("no_data"))
        report = vtc.run_backfill(client, "SYNTHETIC-project", [
            vtc.RunPlan(run_dir, {"main": GEMINI}, RUN_START, RUN_END)], COLLECTED_AT)
        self.assertEqual(report["status_counts"], {"no_data": 1})
        self.assertIn("not zero", report["runs"][0]["detail"])
        summary = self.summary_of(run_dir)
        for cls in ("input_tokens", "output_tokens", "cache_read_tokens",
                    "cache_creation_tokens"):
            with self.subTest(token_class=cls):
                self.assertIsNone(summary["usage"][cls]["value"])
                self.assertEqual(summary["usage"][cls]["confidence"], "unavailable")

    def test_a_class_the_metric_never_reported_stays_unavailable(self):
        """Gemini emits no cache classes; those fields must not become 0."""
        run_dir = self.make_run()
        client = FakeMonitoringClient(_fixture("two_models"))
        vtc.run_backfill(client, "SYNTHETIC-project", [
            vtc.RunPlan(run_dir, {"main": GEMINI}, RUN_START, RUN_END)], COLLECTED_AT)
        summary = self.summary_of(run_dir)
        for cls in ("cache_read_tokens", "cache_creation_tokens", "reasoning_tokens"):
            with self.subTest(token_class=cls):
                self.assertIsNone(summary["usage"][cls]["value"])
                self.assertEqual(summary["usage"][cls]["confidence"], "unavailable")

    def test_a_missing_run_directory_is_an_error_not_a_silent_pass(self):
        report = vtc.run_backfill(FakeMonitoringClient([]), "SYNTHETIC-project", [
            vtc.RunPlan("/nonexistent/SYNTHETIC-run", {"main": GEMINI},
                        RUN_START, RUN_END)], COLLECTED_AT)
        self.assertEqual(report["status_counts"], {"error": 1})


class ReportTests(unittest.TestCase):

    def test_the_report_states_both_confidence_tiers_and_the_economics_limit(self):
        report = vtc.build_report("SYNTHETIC-project", COLLECTED_AT, 60, [])
        self.assertEqual(report["attribution"]["counts_confidence"], "authoritative")
        self.assertEqual(report["attribution"]["per_run_attribution_confidence"], "derived")
        self.assertIn("does not recompute economics", report["economics_note"])


class WindowFromEventsTests(RunDirMixin, unittest.TestCase):

    def test_the_default_window_is_the_first_and_last_event(self):
        run_dir = self.make_run()
        start, end = vtc.run_window_from_events(run_dir)
        self.assertEqual(start[:19], "2026-08-16T10:00:00")
        self.assertEqual(end[:19], "2026-08-16T10:05:00")

    def test_a_run_with_no_event_log_cannot_be_windowed(self):
        empty = tempfile.mkdtemp(prefix="SYNTHETIC-run-")
        self.addCleanup(shutil.rmtree, empty, True)
        with self.assertRaises(vtc.CollectorError):
            vtc.run_window_from_events(empty)


if __name__ == "__main__":
    unittest.main()
