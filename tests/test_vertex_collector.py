"""Tests for the provider-side Vertex token collector.

Everything here runs offline: the monitoring client is a fake that replays
SYNTHETIC time-series fixtures, and every run directory is built in a tempdir.
No network, no credentials, no model call, no spend.

The invariants under test are the ones that would quietly corrupt a cost figure:
window attribution, per-model leg split, backfill after ingestion lag,
unmapped-type flagging, and — the load-bearing one — that a class nobody reported
stays *unavailable* rather than becoming 0.
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import urllib.error

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


class TransportRetryTests(unittest.TestCase):
    """The HTTP layer of the real client. No network: ``urlopen`` is stubbed.

    Batch 1's v2 backfill died mid-pass on a bare socket ``TimeoutError``, which
    is not a ``URLError`` and so escaped the per-run ``CollectorError`` handler and
    took the whole 77-run batch with it. Widening the attribution window made the
    pages bigger and the stalls more likely, so the transport has to survive one.
    """

    def _client(self, responses):
        """responses: a list of exceptions to raise / dicts to return, in order."""
        calls = []
        client = vtc.GcloudMonitoringClient(access_token="t", sleep=lambda _s: None)

        def fake_urlopen(req, timeout=None):  # noqa: ARG001
            outcome = responses[len(calls)]
            calls.append(req.full_url)
            if isinstance(outcome, Exception):
                raise outcome
            return _FakeResponse(outcome)

        return client, calls, fake_urlopen

    def _run(self, client, fake_urlopen):
        original = vtc.urllib.request.urlopen
        vtc.urllib.request.urlopen = fake_urlopen
        try:
            return client.list_time_series(
                "p", vtc.build_filter([GEMINI]),
                (vtc.parse_ts(RUN_START), vtc.parse_ts(RUN_END)))
        finally:
            vtc.urllib.request.urlopen = original

    def test_a_read_timeout_is_retried_and_then_succeeds(self):
        client, calls, fake = self._client([
            TimeoutError("The read operation timed out"),
            {"timeSeries": [{"points": []}]},
        ])
        series = self._run(client, fake)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(series), 1)

    def test_a_read_timeout_that_never_clears_raises_a_collector_error(self):
        """One run degrades to ``error`` — the batch keeps going. What must NOT
        happen is a bare TimeoutError escaping to the top of the process."""
        client, calls, fake = self._client([TimeoutError("timed out")] * 4)
        with self.assertRaises(vtc.CollectorError) as caught:
            self._run(client, fake)
        self.assertEqual(len(calls), vtc.MONITORING_ATTEMPTS)
        self.assertIn("gave up after", str(caught.exception))

    def test_a_503_is_retried_but_a_401_is_not(self):
        client, calls, fake = self._client([
            urllib.error.HTTPError("u", 503, "unavailable", {}, io.BytesIO(b"busy")),
            {"timeSeries": []},
        ])
        self._run(client, fake)
        self.assertEqual(len(calls), 2)

        client, calls, fake = self._client([
            urllib.error.HTTPError("u", 401, "denied", {}, io.BytesIO(b"nope")),
            {"timeSeries": []},
        ])
        with self.assertRaises(vtc.CollectorError):
            self._run(client, fake)
        self.assertEqual(len(calls), 1, "a credential failure must not be retried")

    def test_a_400_bad_filter_fails_immediately(self):
        """A malformed filter returns 400 forever; retrying it just wastes the
        batch's wall clock and buries the real message four attempts deep."""
        client, calls, fake = self._client([
            urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO(b"Could not parse filter")),
        ] * 4)
        with self.assertRaises(vtc.CollectorError) as caught:
            self._run(client, fake)
        self.assertEqual(len(calls), 1)
        self.assertIn("Could not parse filter", str(caught.exception))


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


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

    def test_a_backfill_event_does_not_stretch_the_window_to_collection_time(self):
        # Regression: a backfill event carries the COLLECTION timestamp, not a
        # moment of the run. Counting it made every already-collected run in
        # screening batch 1 look hours long and overlapping with its neighbours,
        # which the ownership rule then refused as "not serialized".
        run_dir = self.make_run()
        EventLog(os.path.join(run_dir, "events.jsonl")).append(
            vtc.BACKFILL_EVENT, "2026-08-16T23:15:09Z", leg="main")
        EventLog(os.path.join(run_dir, "events.jsonl")).append(
            vtc.BACKFILL_EVENT_V2, "2026-08-17T04:37:27Z", leg="main")
        self.assertEqual(vtc.run_window_from_events(run_dir)[1],
                         vtc.format_ts(vtc.parse_ts(RUN_END)))

    def test_a_run_with_no_event_log_cannot_be_windowed(self):
        empty = tempfile.mkdtemp(prefix="SYNTHETIC-run-")
        self.addCleanup(shutil.rmtree, empty, True)
        with self.assertRaises(vtc.CollectorError):
            vtc.run_window_from_events(empty)


# --------------------------------------------------------------------------- #
# Contamination guard
#
# The defect these tests exist for: a ~10-minute Product-B run's window returned
# 10,993,105 input tokens because an unrelated interactive workload was hitting
# the same publisher model. The counts were authoritative and the attribution was
# nonsense, and nothing in the collector would have stopped the write.
# --------------------------------------------------------------------------- #
def _series(model, type_label, tokens, end_ts):
    """One SYNTHETIC time series with a single point."""
    return {
        "resource": {"labels": {"model_user_id": model, "publisher": "google"}},
        "metric": {"labels": {"type": type_label}},
        "points": [{"interval": {"endTime": end_ts},
                    "value": {"int64Value": str(tokens)}}],
    }


class WindowedFakeClient(vtc.MonitoringClient):
    """Returns only the series whose point falls in the requested interval.

    The plain fake replays one fixture for every query, which cannot express "the
    run window is busy but the minutes either side are quiet" — the exact
    distinction the baseline probe is built on.
    """

    def __init__(self, series):
        self.series = series
        self.windows = []

    def list_time_series(self, project, filter_str, window):
        lo, hi = window
        self.windows.append((vtc.format_ts(lo), vtc.format_ts(hi)))
        out = []
        for s in self.series:
            points = [p for p in s["points"]
                      if lo <= vtc.parse_ts(p["interval"]["endTime"]) <= hi]
            if points:
                out.append({**s, "points": points})
        return out


class ContaminationCeilingTests(unittest.TestCase):

    def test_a_window_over_the_ceiling_is_contaminated(self):
        collection = vtc.aggregate_series(
            [_series(GEMINI, "input", 10_993_105, "2026-08-16T10:02:00Z")],
            vtc.build_window(RUN_START, RUN_END), vtc.DEFAULT_GUARD_SECONDS)
        verdict = vtc.check_ceiling(collection, 3_000_000)
        self.assertTrue(verdict.contaminated)
        self.assertIn("10993105", verdict.reasons[0])
        self.assertIn("ceiling", verdict.evidence)

    def test_a_plausible_window_passes(self):
        verdict = vtc.check_ceiling(_aggregate("two_models"), 3_000_000)
        self.assertFalse(verdict.contaminated)
        self.assertEqual(verdict.reasons, [])

    def test_cache_read_counts_toward_the_ceiling(self):
        # A contaminated window can arrive entirely as cache reads; checking only
        # the plain input class would wave it through.
        collection = vtc.aggregate_series(
            [_series(GEMINI, "cache_read_input", 9_000_000, "2026-08-16T10:02:00Z")],
            vtc.build_window(RUN_START, RUN_END), vtc.DEFAULT_GUARD_SECONDS)
        self.assertTrue(vtc.check_ceiling(collection, 3_000_000).contaminated)

    def test_output_tokens_do_not_trip_the_input_side_ceiling(self):
        collection = vtc.aggregate_series(
            [_series(GEMINI, "output", 9_000_000, "2026-08-16T10:02:00Z")],
            vtc.build_window(RUN_START, RUN_END), vtc.DEFAULT_GUARD_SECONDS)
        self.assertFalse(vtc.check_ceiling(collection, 3_000_000).contaminated)

    def test_zero_disables_the_check_and_says_so(self):
        verdict = vtc.check_ceiling(_aggregate("two_models"), 0)
        self.assertFalse(verdict.contaminated)
        self.assertEqual(verdict.evidence["ceiling"], "disabled")


class RateCeilingTests(unittest.TestCase):
    """The v3 plausibility check: tokens per second, not tokens per run.

    A fixed per-run constant cannot tell a long run from a contaminated window —
    a 47-minute executor run and a 4-minute run sharing the meter with a stranger
    both land above 3M. The quantity that separates them is the rate.
    """

    @staticmethod
    def _collect(series, start, end):
        return vtc.aggregate_series(series, vtc.build_window(start, end),
                                    vtc.DEFAULT_GUARD_SECONDS)

    #: 50 minutes of one agent's own work. Batch 1's Gemini-executor arms are
    #: this shape: totals scaling with duration, well over the fixed ceiling.
    LONG_RUN = ("2026-08-16T10:00:00Z", "2026-08-16T10:50:00Z")
    #: Four minutes. With the guard band either side the window is 360s.
    SHORT_RUN = ("2026-08-16T10:00:00Z", "2026-08-16T10:04:00Z")
    #: The real reading from the smoke-test contamination this guard was built
    #: after. Over 360s it is 30,536 input-side tokens/s.
    BURST = 10_993_105

    def test_a_long_run_over_the_fixed_ceiling_is_plausible_by_rate(self):
        collection = self._collect(
            [_series(GEMINI, "input", 4_000_000, "2026-08-16T10:25:00Z")], *self.LONG_RUN)
        # The negative control: this is exactly what v1/v2 refused.
        self.assertTrue(vtc.check_ceiling(collection, 3_000_000).contaminated)
        verdict = vtc.check_rate_ceiling(collection, 25_000)
        self.assertFalse(verdict.contaminated, verdict.reasons)
        self.assertEqual(verdict.reasons, [])

    def test_a_burst_packed_into_four_minutes_is_refused(self):
        collection = self._collect(
            [_series(GEMINI, "input", self.BURST, "2026-08-16T10:02:00Z")],
            *self.SHORT_RUN)
        verdict = vtc.check_rate_ceiling(collection, 25_000)
        self.assertTrue(verdict.contaminated)
        self.assertIn("per second", verdict.reasons[0])
        self.assertIn(GEMINI, verdict.reasons[0])

    def test_the_evidence_records_the_rate_it_measured_not_just_the_verdict(self):
        collection = self._collect(
            [_series(GEMINI, "input", 4_000_000, "2026-08-16T10:25:00Z")], *self.LONG_RUN)
        evidence = vtc.check_rate_ceiling(collection, 25_000).evidence["rate_ceiling"]
        self.assertEqual(evidence["input_side_tokens_per_second_ceiling"], 25_000)
        # 10:00:00 to 10:50:00 plus a 60s guard band either side.
        self.assertEqual(evidence["window_seconds"], 3120.0)
        self.assertEqual(evidence["observed_input_side_tokens"][GEMINI], 4_000_000)
        self.assertAlmostEqual(
            evidence["observed_input_side_tokens_per_second"][GEMINI],
            4_000_000 / 3120, places=2)

    def test_cache_reads_count_toward_the_rate(self):
        collection = self._collect(
            [_series(GEMINI, "cache_read_input", self.BURST, "2026-08-16T10:02:00Z")],
            *self.SHORT_RUN)
        self.assertTrue(vtc.check_rate_ceiling(collection, 25_000).contaminated)

    def test_output_tokens_do_not_trip_the_input_side_rate(self):
        collection = self._collect(
            [_series(GEMINI, "output", self.BURST, "2026-08-16T10:02:00Z")],
            *self.SHORT_RUN)
        self.assertFalse(vtc.check_rate_ceiling(collection, 25_000).contaminated)

    def test_zero_disables_the_check_and_says_so(self):
        collection = self._collect(
            [_series(GEMINI, "input", self.BURST, "2026-08-16T10:02:00Z")],
            *self.SHORT_RUN)
        verdict = vtc.check_rate_ceiling(collection, 0)
        self.assertFalse(verdict.contaminated)
        self.assertEqual(verdict.evidence["rate_ceiling"], "disabled")

    def test_a_window_of_no_duration_is_refused_rather_than_divided_by(self):
        # Not reachable through the guard band, but a rate over a zero window has
        # no value, and inventing one (or waving the window through) would be the
        # fabrication this whole check exists to prevent.
        collection = self._collect(
            [_series(GEMINI, "input", 1_000, "2026-08-16T10:02:00Z")],
            *self.SHORT_RUN)
        collection.window_end = collection.window_start
        verdict = vtc.check_rate_ceiling(collection, 25_000)
        self.assertTrue(verdict.contaminated)
        self.assertIsNone(
            verdict.evidence["rate_ceiling"]["observed_input_side_tokens_per_second"][GEMINI])


class BaselineProbeTests(unittest.TestCase):

    def _probe(self, series, baseline=300):
        window = vtc.build_window(RUN_START, RUN_END)
        client = WindowedFakeClient(series)
        return client, vtc.probe_baseline(client, "SYNTHETIC-project",
                                          vtc.build_filter([GEMINI]), window, baseline)

    def test_a_quiet_run_window_passes(self):
        _, verdict = self._probe([_series(GEMINI, "input", 1500, "2026-08-16T10:02:00Z")])
        self.assertFalse(verdict.contaminated)
        self.assertEqual(verdict.evidence["baseline"]["windows"]["pre"]["points"], 0)
        self.assertEqual(verdict.evidence["baseline"]["windows"]["post"]["points"], 0)

    def test_traffic_before_the_run_contaminates_it(self):
        # Steady background traffic is invisible to any ceiling: it looks exactly
        # like a long run. Only the quiet-either-side check catches it.
        _, verdict = self._probe([
            _series(GEMINI, "input", 1500, "2026-08-16T10:02:00Z"),
            _series(GEMINI, "input", 800, "2026-08-16T09:57:00Z"),
        ])
        self.assertTrue(verdict.contaminated)
        self.assertIn("pre-run baseline window", verdict.reasons[0])

    def test_traffic_after_the_run_contaminates_it(self):
        _, verdict = self._probe([
            _series(GEMINI, "input", 1500, "2026-08-16T10:02:00Z"),
            _series(GEMINI, "input", 800, "2026-08-16T10:08:00Z"),
        ])
        self.assertTrue(verdict.contaminated)
        self.assertTrue(any("post-run" in r for r in verdict.reasons))

    def test_the_probes_sit_outside_the_guarded_window(self):
        client, _ = self._probe([_series(GEMINI, "input", 1500, "2026-08-16T10:02:00Z")])
        lo, hi = vtc.build_window(RUN_START, RUN_END)
        (pre_lo, pre_hi), (post_lo, post_hi) = client.windows
        self.assertLess(vtc.parse_ts(pre_hi), lo + vtc.timedelta(seconds=1))
        self.assertGreater(vtc.parse_ts(post_lo), hi - vtc.timedelta(seconds=1))
        self.assertLess(vtc.parse_ts(pre_lo), vtc.parse_ts(pre_hi))
        self.assertLess(vtc.parse_ts(post_lo), vtc.parse_ts(post_hi))

    def test_an_unverifiable_probe_is_not_a_quiet_window(self):
        class Broken(vtc.MonitoringClient):
            def list_time_series(self, project, filter_str, window):
                raise vtc.CollectorError("SYNTHETIC monitoring outage")

        verdict = vtc.probe_baseline(Broken(), "SYNTHETIC-project",
                                     vtc.build_filter([GEMINI]),
                                     vtc.build_window(RUN_START, RUN_END), 300)
        self.assertTrue(verdict.contaminated)
        self.assertIn("SYNTHETIC monitoring outage", verdict.reasons[0])

    def test_zero_disables_the_probe_and_says_so(self):
        verdict = vtc.probe_baseline(WindowedFakeClient([]), "SYNTHETIC-project",
                                     vtc.build_filter([GEMINI]),
                                     vtc.build_window(RUN_START, RUN_END), 0)
        self.assertFalse(verdict.contaminated)
        self.assertEqual(verdict.evidence["baseline"], "disabled")


class ContaminationRefusalTests(RunDirMixin, unittest.TestCase):
    """A contaminated window writes NOTHING. That is the whole point."""

    CONTAMINATED = [_series(GEMINI, "input", 10_993_105, "2026-08-16T10:02:00Z")]

    def _backfill(self, run_dir, series):
        client = WindowedFakeClient(series)
        plan = vtc.RunPlan(run_dir=run_dir, legs={"main": GEMINI},
                           start=RUN_START, end=RUN_END)
        return vtc.run_backfill(client, "SYNTHETIC-project", [plan], COLLECTED_AT)

    def test_an_over_ceiling_window_is_refused_and_nothing_is_written(self):
        run_dir = self.make_run()
        events_path = os.path.join(run_dir, "events.jsonl")
        with open(events_path, encoding="utf-8") as fh:
            before = fh.read()

        report = self._backfill(run_dir, self.CONTAMINATED)

        self.assertEqual(report["status_counts"], {vtc.CONTAMINATED_STATUS: 1})
        with open(events_path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before, "no event may be appended")
        after = self.summary_of(run_dir)
        self.assertIsNone(after["usage"]["input_tokens"]["value"],
                          "usage stays unavailable, never the contaminated number")
        self.assertEqual(after["usage"]["input_tokens"]["confidence"], "unavailable")

    def test_the_refusal_and_its_evidence_are_recorded_beside_the_run(self):
        run_dir = self.make_run()
        report = self._backfill(run_dir, self.CONTAMINATED)
        marker = os.path.join(run_dir, "PROVIDER-BACKFILL-REFUSED.json")
        self.assertTrue(os.path.isfile(marker))
        with open(marker, encoding="utf-8") as fh:
            payload = json.load(fh)
        self.assertEqual(payload["refusal"], vtc.CONTAMINATED_STATUS)
        self.assertTrue(payload["guard"]["contaminated"])
        self.assertIn("NOT this run's usage", payload["note"])
        # The refused totals are kept as evidence, clearly labelled as not-a-measurement.
        self.assertEqual(payload["window_totals_refused"]["by_model"][GEMINI]["input"],
                         10_993_105)
        run = report["runs"][0]
        self.assertEqual(run["status"], vtc.CONTAMINATED_STATUS)
        self.assertTrue(run["contamination"]["contaminated"])

    def test_a_later_pass_that_succeeds_removes_the_marker_it_falsified(self):
        """A marker means "nothing was written under this rule". Leaving one next
        to an event written under that same rule is the self-contradiction four
        batch-1 runs carry from the v1 pass — a reader cannot tell which is true.
        """
        run_dir = self.make_run()
        self._backfill(run_dir, self.CONTAMINATED)
        marker = os.path.join(run_dir, "PROVIDER-BACKFILL-REFUSED.json")
        self.assertTrue(os.path.isfile(marker))

        clean = [_series(GEMINI, "input", 4_101, "2026-08-16T10:02:00Z")]
        report = self._backfill(run_dir, clean)

        self.assertEqual(report["runs"][0]["status"], "backfilled")
        self.assertFalse(os.path.exists(marker), "the falsified marker must go")
        self.assertEqual(report["runs"][0]["superseded_marker"],
                         "PROVIDER-BACKFILL-REFUSED.json",
                         "and the report must say it was removed")

    def test_a_dry_run_refusal_writes_no_marker_either(self):
        run_dir = self.make_run()
        client = WindowedFakeClient(self.CONTAMINATED)
        plan = vtc.RunPlan(run_dir, {"main": GEMINI}, RUN_START, RUN_END)
        vtc.run_backfill(client, "SYNTHETIC-project", [plan], COLLECTED_AT, dry_run=True)
        self.assertFalse(os.path.isfile(
            os.path.join(run_dir, "PROVIDER-BACKFILL-REFUSED.json")))

    def test_a_clean_window_still_backfills_and_records_why_it_was_clean(self):
        run_dir = self.make_run()
        report = self._backfill(
            run_dir, [_series(GEMINI, "input", 1500, "2026-08-16T10:02:00Z"),
                      _series(GEMINI, "output", 300, "2026-08-16T10:02:00Z")])
        self.assertEqual(report["status_counts"], {"backfilled": 1}, report["runs"])
        self.assertEqual(self.summary_of(run_dir)["usage"]["input_tokens"]["value"], 1500)
        guard = report["runs"][0]["contamination"]
        self.assertFalse(guard["contaminated"])
        self.assertIn("baseline", guard["evidence"])
        self.assertIn("ceiling", guard["evidence"])

    def test_an_already_filled_run_is_skipped_rather_than_re_refused(self):
        # Regression: the guard used to speak before the idempotence check, so a
        # second pass over an already-collected batch stamped a refusal marker on
        # runs whose earlier attribution stands — a refusal about a write that was
        # never going to happen, overwriting whatever marker was already there.
        run_dir = self.make_run()
        self._backfill(run_dir, [_series(GEMINI, "input", 1500,
                                         "2026-08-16T10:02:00Z")])
        report = self._backfill(run_dir, self.CONTAMINATED)
        self.assertEqual(report["runs"][0]["status"], "skipped")
        self.assertFalse(os.path.isfile(
            os.path.join(run_dir, "PROVIDER-BACKFILL-REFUSED.json")))
        self.assertEqual(self.summary_of(run_dir)["usage"]["input_tokens"]["value"],
                         1500)

    def test_the_report_names_the_refused_runs_and_the_thresholds(self):
        run_dir = self.make_run()
        report = self._backfill(run_dir, self.CONTAMINATED)
        guard = report["contamination_guard"]
        self.assertEqual(guard["runs_refused"], [run_dir])
        self.assertEqual(guard["input_side_ceiling_tokens"],
                         vtc.DEFAULT_CEILING_INPUT_TOKENS)
        self.assertEqual(guard["baseline_probe_seconds"], vtc.DEFAULT_BASELINE_SECONDS)

    def test_refusal_exits_nonzero_with_its_own_code(self):
        # The driver must be able to tell "guard refused" from "collector broke":
        # one needs a quiet window, the other needs a fix.
        run_dir = self.make_run()
        plan_path = os.path.join(run_dir, "SYNTHETIC-plan.json")
        with open(plan_path, "w", encoding="utf-8") as fh:
            json.dump({"project": "SYNTHETIC-project",
                       "runs": [{"run_dir": run_dir, "legs": {"main": GEMINI},
                                 "start": RUN_START, "end": RUN_END}]}, fh)
        client = WindowedFakeClient(self.CONTAMINATED)
        original = vtc.GcloudMonitoringClient
        vtc.GcloudMonitoringClient = lambda *a, **k: client
        printed = io.StringIO()
        try:
            with contextlib.redirect_stdout(printed):
                rc = vtc.main(["--plan", plan_path, "--collected-at", COLLECTED_AT])
        finally:
            vtc.GcloudMonitoringClient = original
        self.assertEqual(rc, 4)
        self.assertIn("CONTAMINATED WINDOW", printed.getvalue())


# --------------------------------------------------------------------------- #
# Serialized-run ownership (attribution rule v2)
#
# The defect these tests exist for is the mirror image of the one above. Rule v1
# demands silence either side of a run's window, but Cloud Monitoring ingests this
# metric with a delay, so a run deposits its OWN last points after its own window
# closes. v1 read that as a third party and refused: 8 of batch 1's 43 refusals
# were runs refused for their own tail. v2 says a serialized run owns the meter
# until the next subject run's window opens, which makes the tail attributable
# WITHOUT making a genuine third-party burst attributable.
#
# Both halves are tested here, because a rule that only did the first half would
# be a licence to attribute anything at all.
# --------------------------------------------------------------------------- #
A_START, A_END = "2026-08-16T10:00:00Z", "2026-08-16T10:05:00Z"
B_START, B_END = "2026-08-16T10:30:00Z", "2026-08-16T10:35:00Z"

#: A_END + 120s: after run A's guarded window closes (10:06:00), inside the tail.
A_OWN_TAIL = "2026-08-16T10:07:00Z"
#: After A's ownership window closes (10:11:00) and long before B's opens
#: (10:29:00) — no subject run owns this instant.
THIRD_PARTY = "2026-08-16T10:13:00Z"


class OwnershipWindowTests(unittest.TestCase):
    """The boundary arithmetic, with no client and no run directories."""

    def _own(self, *windows, guard=60, tail=300):
        plans = [vtc.RunPlan(run_dir=f"/SYNTHETIC/run-{i}", legs={"main": GEMINI},
                             start=s, end=e) for i, (s, e) in enumerate(windows)]
        return plans, vtc.plan_ownership(plans, guard, tail)

    def test_a_lone_run_gets_the_full_ingestion_tail(self):
        plans, owned = self._own((A_START, A_END))
        entry = owned[plans[0].run_dir]
        self.assertEqual(vtc.format_ts(entry.hi), "2026-08-16T10:11:00.000000Z")
        self.assertEqual(entry.bounded_by, "ingestion_tail")
        self.assertEqual(entry.tail_granted_seconds(), 300)
        self.assertIsNone(entry.inseparable)

    def test_a_clipped_tail_is_recorded_as_the_residual_risk_it_is(self):
        # 200s apart, 60s of guard each side: the run keeps 80s of tail and the
        # neighbour takes the rest. Attributable, but the shortfall must be
        # visible in the record rather than left to be reconstructed.
        plans, owned = self._own((A_START, A_END), ("2026-08-16T10:08:20Z",
                                                    "2026-08-16T10:12:00Z"))
        entry = owned[plans[0].run_dir]
        self.assertAlmostEqual(entry.tail_granted_seconds(), 80, places=3)
        self.assertLess(entry.as_dict()["tail_granted_seconds"],
                        entry.as_dict()["tail_seconds"])

    def test_the_window_stops_where_the_next_runs_window_opens(self):
        # A neighbour 200s later cannot be given away 300s of tail.
        plans, owned = self._own((A_START, A_END), ("2026-08-16T10:08:20Z",
                                                    "2026-08-16T10:12:00Z"))
        first = owned[plans[0].run_dir]
        self.assertEqual(first.bounded_by, "next_subject_run")
        self.assertLess(first.hi, vtc.parse_ts("2026-08-16T10:07:20Z"))
        self.assertIsNone(first.inseparable, "200s apart is still separable")
        # No overlap: one run's window ends strictly before the next one's opens.
        self.assertLess(first.hi, owned[plans[1].run_dir].lo)

    def test_runs_closer_than_the_guard_bands_are_inseparable_not_attributed(self):
        # 30s apart: A's tail lands inside B's window and the meter cannot say
        # which run produced it. Refusing both is the only honest answer.
        plans, owned = self._own((A_START, A_END), ("2026-08-16T10:05:30Z",
                                                    "2026-08-16T10:09:00Z"))
        self.assertIn("guard band", owned[plans[0].run_dir].inseparable)
        self.assertIn("preceding subject run", owned[plans[1].run_dir].inseparable)

    def test_inseparability_travels_one_hop_and_stops(self):
        """Regression: batch 1's first v2 pass refused 14 runs off tight gaps.

        A and B are 30s apart, so A's tail lands in B's window — B is refused.
        C is half an hour after B, so B's OWN tail is separable from C's window
        and nothing about the A/B boundary bears on C. Propagating transitively
        (reading the flag while writing it) poisons every run to the end of the
        batch from a single tight gap, which is a claim the meter never made.
        """
        plans, owned = self._own((A_START, A_END),
                                 ("2026-08-16T10:05:30Z", "2026-08-16T10:09:00Z"),
                                 ("2026-08-16T10:40:00Z", "2026-08-16T10:45:00Z"))
        self.assertIn("guard band", owned[plans[0].run_dir].inseparable)
        self.assertIn("preceding subject run", owned[plans[1].run_dir].inseparable)
        self.assertIsNone(owned[plans[2].run_dir].inseparable,
                          "C's boundaries are its own; A/B's ambiguity is not C's")

    def test_a_run_of_tight_gaps_flags_each_pair_on_its_own_evidence(self):
        """Every gap here is tight, so every run really is flagged — but each on
        the boundary it actually has, not on an inherited one four runs back."""
        plans, owned = self._own((A_START, A_END),
                                 ("2026-08-16T10:05:30Z", "2026-08-16T10:09:00Z"),
                                 ("2026-08-16T10:09:30Z", "2026-08-16T10:12:00Z"))
        for plan in plans[:2]:
            self.assertIn("guard band", owned[plan.run_dir].inseparable)
        # The last run has no successor, so it can only inherit — one hop.
        last = owned[plans[2].run_dir].inseparable
        self.assertIn("preceding subject run", last)
        self.assertEqual(last.count("preceding subject run"), 1,
                         "an inherited reason must not stack up the whole chain")

    def test_overlapping_runs_are_refused_as_not_serialized(self):
        plans, owned = self._own((A_START, A_END), ("2026-08-16T10:04:00Z",
                                                    "2026-08-16T10:09:00Z"))
        self.assertIn("not serialized", owned[plans[0].run_dir].inseparable)

    def test_boundaries_do_not_depend_on_the_order_the_plans_arrive_in(self):
        forward, owned_f = self._own((A_START, A_END), (B_START, B_END))
        backward, owned_b = self._own((B_START, B_END), (A_START, A_END))
        self.assertEqual(vtc.format_ts(owned_f[forward[0].run_dir].hi),
                         vtc.format_ts(owned_b[backward[1].run_dir].hi))

    def test_a_zero_tail_reduces_the_window_to_the_v1_one(self):
        plans, owned = self._own((A_START, A_END), tail=0)
        self.assertEqual(owned[plans[0].run_dir].window(),
                         vtc.build_window(A_START, A_END, 60))

    def test_the_probes_are_the_region_no_subject_run_owns(self):
        plans, owned = self._own((A_START, A_END), (B_START, B_END))
        first, second = owned[plans[0].run_dir], owned[plans[1].run_dir]
        # A's post probe starts at its boundary and stops before B's window.
        post = first.post_probe(300)
        self.assertEqual(vtc.format_ts(post[0]), "2026-08-16T10:11:00.000001Z")
        self.assertLess(post[1], second.lo)
        # B's pre probe never reaches back into A's ownership.
        self.assertGreater(second.pre_probe(300)[0], first.hi)

    def test_a_probe_the_neighbour_squeezes_to_nothing_is_absent(self):
        plans, owned = self._own((A_START, A_END), ("2026-08-16T10:08:20Z",
                                                    "2026-08-16T10:12:00Z"))
        self.assertIsNone(owned[plans[0].run_dir].post_probe(300))
        self.assertIsNone(owned[plans[1].run_dir].pre_probe(300))


class ResolvedTailTests(unittest.TestCase):
    """The tail is measured against the meter, not granted by configuration.

    The first v2 pass over batch 1 handed every run a flat 300s tail and still
    refused 37 of 43 legs: querying the meter around one of them showed its own
    points arriving in an unbroken chain until 482s after its last event, then
    nothing for twenty minutes. A fixed tail is a guess at an undocumented
    ingestion delay, and a guess that is too short reproduces v1's defect exactly.
    These tests pin the replacement — extend while points keep coming, stop at the
    first silence, refuse a tail that never stops.

    All series here are SYNTHETIC.
    """

    def _entry(self, *, tail=900, guard=60, next_start=None):
        plans = [vtc.RunPlan(run_dir="/SYNTHETIC/run-0", legs={"main": GEMINI},
                             start=A_START, end=A_END)]
        if next_start is not None:
            plans.append(vtc.RunPlan(run_dir="/SYNTHETIC/run-1",
                                     legs={"main": GEMINI}, start=next_start,
                                     end="2026-08-16T11:30:00Z"))
        return vtc.plan_ownership(plans, guard, tail)["/SYNTHETIC/run-0"]

    @staticmethod
    def _times(*stamps):
        return [vtc.parse_ts(s) for s in stamps]

    def test_a_run_with_no_points_after_it_keeps_the_v1_window(self):
        resolved = vtc.resolve_tail(self._entry(), self._times("2026-08-16T10:02:00Z"))
        self.assertEqual(resolved.tail_ended_by, "no_points")
        self.assertEqual(vtc.format_ts(resolved.hi), "2026-08-16T10:06:00.000000Z")
        self.assertEqual(resolved.tail_granted_seconds(), 0)

    def test_a_chain_of_points_extends_the_tail_past_a_fixed_300s(self):
        # 10:05 end; points at +2m, +4m, +6m, +8m — each within the silence
        # threshold of the last. A flat 300s tail would have stopped at 10:11 and
        # refused the run for the two points it left outside.
        resolved = vtc.resolve_tail(self._entry(), self._times(
            "2026-08-16T10:07:00Z", "2026-08-16T10:09:00Z",
            "2026-08-16T10:11:00Z", "2026-08-16T10:13:00Z"))
        self.assertEqual(resolved.tail_ended_by, "silence")
        self.assertEqual(vtc.format_ts(resolved.hi), "2026-08-16T10:14:00.000000Z")
        self.assertEqual(resolved.tail_granted_seconds(), 480)

    def test_the_tail_stops_at_the_first_silence_not_at_the_last_point(self):
        # A gap of exactly the silence threshold ends it: the point after the gap
        # is not ours, however much it looks like more of the same.
        resolved = vtc.resolve_tail(self._entry(), self._times(
            "2026-08-16T10:07:00Z", "2026-08-16T10:12:00Z"))
        self.assertEqual(resolved.tail_ended_by, "silence")
        self.assertEqual(vtc.format_ts(resolved.last_point),
                         "2026-08-16T10:07:00.000000Z")
        self.assertLess(resolved.hi, vtc.parse_ts("2026-08-16T10:12:00Z"))

    def test_a_tail_that_never_stops_is_refused_not_credited(self):
        # Points every two minutes for twenty. An ingestion tail decays; this is
        # someone else working, so the run is refused rather than handed the lot.
        forever = self._times(*[f"2026-08-16T10:{m:02d}:00Z"
                                for m in range(7, 30, 2)])
        resolved = vtc.resolve_tail(self._entry(tail=600), forever)
        self.assertEqual(resolved.tail_ended_by, "tail_cap")
        self.assertIsNotNone(resolved.inseparable)
        self.assertIn("cannot be called this run's", resolved.inseparable)

    def test_a_tail_still_running_when_the_neighbour_opens_is_clipped_not_refused(self):
        entry = self._entry(next_start="2026-08-16T10:20:00Z")
        resolved = vtc.resolve_tail(entry, self._times(
            "2026-08-16T10:07:00Z", "2026-08-16T10:09:00Z",
            "2026-08-16T10:11:00Z", "2026-08-16T10:13:00Z",
            "2026-08-16T10:15:00Z", "2026-08-16T10:17:00Z"))
        self.assertEqual(resolved.tail_ended_by, "next_subject_run")
        self.assertIsNone(resolved.inseparable, "clipping is a risk, not a refusal")
        self.assertLess(resolved.hi, entry.next_lo)

    def test_the_probe_after_a_silenced_tail_covers_the_whole_no_mans_land(self):
        # Nothing between the tail's end and the next run belongs to any subject
        # run, so all of it is probed — not just the first baseline slice.
        entry = self._entry(next_start="2026-08-16T11:00:00Z")
        resolved = vtc.resolve_tail(entry, self._times("2026-08-16T10:07:00Z"))
        probe = resolved.post_probe(300)
        self.assertEqual(vtc.format_ts(probe[0]), "2026-08-16T10:08:00.000001Z")
        self.assertEqual(probe[1], resolved.next_lo - vtc._TICK)

    def test_points_before_the_run_ends_never_shorten_the_window(self):
        resolved = vtc.resolve_tail(self._entry(), self._times(
            "2026-08-16T10:00:30Z", "2026-08-16T10:04:00Z"))
        self.assertGreaterEqual(resolved.hi, vtc.parse_ts(A_END))
        self.assertEqual(resolved.tail_ended_by, "no_points")

    def test_a_negative_silence_is_refused_rather_than_clamped(self):
        with self.assertRaises(vtc.CollectorError):
            vtc.resolve_tail(self._entry(), [], silence_seconds=-1)


class SerializedOwnershipBackfillTests(RunDirMixin, unittest.TestCase):
    """The rule end to end: own tail attributed, third party still refused."""

    def _plans(self, run_dir, neighbour_dir):
        return [vtc.RunPlan(run_dir=run_dir, legs={"main": GEMINI},
                            start=A_START, end=A_END),
                vtc.RunPlan(run_dir=neighbour_dir, legs={"main": GEMINI},
                            start=B_START, end=B_END)]

    def _backfill(self, series, rule="v2", **kwargs):
        run_dir, neighbour = self.make_run(), self.make_run()
        report = vtc.run_backfill(WindowedFakeClient(series), "SYNTHETIC-project",
                                  self._plans(run_dir, neighbour), COLLECTED_AT,
                                  attribution_rule=rule, **kwargs)
        return run_dir, report, report["runs"][0]

    #: The run's own calls, plus two points ingested after its window closed.
    OWN_TAIL = [
        _series(GEMINI, "input", 251_259, "2026-08-16T10:02:00Z"),
        _series(GEMINI, "output", 4_100, "2026-08-16T10:02:00Z"),
        _series(GEMINI, "input", 25_871, A_OWN_TAIL),
    ]

    def test_the_old_rule_refuses_the_run_for_its_own_tail(self):
        # The negative control. Without this, the v2 test below proves nothing.
        _, report, run = self._backfill(self.OWN_TAIL, rule="v1")
        self.assertEqual(run["status"], vtc.CONTAMINATED_STATUS)
        self.assertTrue(any("post-run" in r for r in run["contamination"]["reasons"]))

    def test_the_new_rule_attributes_the_tail_to_the_run_that_produced_it(self):
        run_dir, report, run = self._backfill(self.OWN_TAIL)
        self.assertEqual(run["status"], "backfilled", run.get("detail"))
        usage = self.summary_of(run_dir)["usage"]
        self.assertEqual(usage["input_tokens"]["value"], 251_259 + 25_871)
        self.assertEqual(usage["input_tokens"]["confidence"], "derived")
        self.assertEqual(usage["output_tokens"]["value"], 4_100)

    def test_the_post_probe_says_the_neighbour_owns_the_rest(self):
        _, _, run = self._backfill(self.OWN_TAIL)
        probes = run["contamination"]["evidence"]["baseline"]["windows"]
        self.assertEqual(probes["post"]["points"], 0)
        self.assertEqual(probes["pre"]["points"], 0)

    #: The batch-1 shape: a tail that keeps arriving past the 300s a fixed setting
    #: would have granted. Every gap here is under the silence threshold.
    LONG_TAIL = OWN_TAIL + [
        _series(GEMINI, "input", 31_004, "2026-08-16T10:09:30Z"),
        _series(GEMINI, "input", 12_880, "2026-08-16T10:12:00Z"),
    ]

    def test_a_tail_longer_than_a_fixed_300s_is_attributed_end_to_end(self):
        # The regression the second v2 pass exists for. Under a flat 300s tail the
        # window closed at 10:11:00, the 10:12:00 point fell in the post probe, and
        # the run was refused for its own late ingestion — 37 of batch 1's 43
        # refused legs looked exactly like this.
        run_dir, _, run = self._backfill(self.LONG_TAIL)
        self.assertEqual(run["status"], "backfilled", run.get("detail"))
        usage = self.summary_of(run_dir)["usage"]
        self.assertEqual(usage["input_tokens"]["value"],
                         251_259 + 25_871 + 31_004 + 12_880)
        events = [e for e in read_events(os.path.join(run_dir, "events.jsonl"))
                  if e["event_type"] == vtc.BACKFILL_EVENT_V2]
        rule = events[0]["attribution_rule"]
        self.assertEqual(rule["tail_ended_by"], "silence")
        self.assertEqual(rule["tail_granted_seconds"], 420)
        self.assertEqual(rule["attribution_window"]["end"],
                         "2026-08-16T10:13:00.000000Z")

    def test_a_third_party_burst_after_the_tail_still_refuses(self):
        # The load-bearing half: widening the window must not have widened it to
        # everything. This point is past the run's ownership and before the next
        # run's — nobody in the batch can have produced it.
        _, _, run = self._backfill(
            self.OWN_TAIL + [_series(GEMINI, "input", 800, THIRD_PARTY)])
        self.assertEqual(run["status"], vtc.CONTAMINATED_STATUS)
        self.assertTrue(any("post-run" in r for r in run["contamination"]["reasons"]))

    def test_a_third_party_burst_before_the_run_still_refuses(self):
        _, _, run = self._backfill(
            self.OWN_TAIL + [_series(GEMINI, "input", 800, "2026-08-16T09:56:00Z")])
        self.assertEqual(run["status"], vtc.CONTAMINATED_STATUS)
        self.assertTrue(any("pre-run" in r for r in run["contamination"]["reasons"]))

    def test_the_plausibility_ceiling_is_untouched_by_the_new_rule(self):
        _, _, run = self._backfill(
            [_series(GEMINI, "input", 10_993_105, "2026-08-16T10:02:00Z")])
        self.assertEqual(run["status"], vtc.CONTAMINATED_STATUS)
        self.assertTrue(any("ceiling" in r for r in run["contamination"]["reasons"]))

    def test_nothing_is_written_when_the_run_is_refused(self):
        run_dir, _, _ = self._backfill(
            self.OWN_TAIL + [_series(GEMINI, "input", 800, THIRD_PARTY)])
        self.assertIsNone(self.summary_of(run_dir)["usage"]["input_tokens"]["value"])

    def test_the_event_names_the_rule_that_attributed_it(self):
        run_dir, _, _ = self._backfill(self.OWN_TAIL)
        events = [e for e in read_events(os.path.join(run_dir, "events.jsonl"))
                  if e["event_type"] == vtc.BACKFILL_EVENT_V2]
        self.assertEqual(len(events), 1)
        rule = events[0]["attribution_rule"]
        self.assertEqual(events[0]["attribution_method"], vtc.ATTRIBUTION_METHOD_V2)
        self.assertEqual(events[0]["attribution_confidence"], "derived")
        self.assertEqual(events[0]["counts_confidence"], "authoritative")
        self.assertEqual(rule["bounded_by"], "ingestion_tail")
        self.assertEqual(rule["tail_cap_seconds"], vtc.DEFAULT_TAIL_SECONDS)
        self.assertEqual(rule["tail_silence_seconds"],
                         vtc.DEFAULT_TAIL_SILENCE_SECONDS)
        # The window ends a guard band after the last point the run actually
        # deposited (10:07:00), not at the cap: the tail is measured, so the record
        # says how far the meter really ran on rather than how far it was allowed to.
        self.assertEqual(rule["tail_ended_by"], "silence")
        self.assertEqual(rule["last_point_attributed"],
                         vtc.format_ts(vtc.parse_ts(A_OWN_TAIL)))
        self.assertEqual(rule["attribution_window"]["end"],
                         "2026-08-16T10:08:00.000000Z")
        self.assertEqual(rule["next_run_window_opens"], "2026-08-16T10:29:00.000000Z")

    def test_a_v2_backfill_does_not_count_as_a_turn(self):
        # The new event type has to be usage-bearing without being a turn, exactly
        # as v1 is: adding it to _USAGE_EVENT_TYPES must not inflate behaviour.
        run_dir, neighbour = self.make_run(), self.make_run()
        before = self.summary_of(run_dir)["behavior"]["turns"]["value"]
        vtc.run_backfill(WindowedFakeClient(self.OWN_TAIL), "SYNTHETIC-project",
                         self._plans(run_dir, neighbour), COLLECTED_AT,
                         attribution_rule="v2")
        after = self.summary_of(run_dir)
        self.assertEqual(after["behavior"]["turns"]["value"], before)
        self.assertEqual(after["usage"]["input_tokens"]["value"], 251_259 + 25_871)

    def test_a_leg_already_filled_under_v1_is_not_filled_again_under_v2(self):
        run_dir, neighbour = self.make_run(), self.make_run()
        clean = [_series(GEMINI, "input", 1500, "2026-08-16T10:02:00Z")]
        plans = self._plans(run_dir, neighbour)
        first = vtc.run_backfill(WindowedFakeClient(clean), "SYNTHETIC-project",
                                 plans, COLLECTED_AT, attribution_rule="v1")
        self.assertEqual(first["runs"][0]["status"], "backfilled")
        second = vtc.run_backfill(WindowedFakeClient(clean), "SYNTHETIC-project",
                                  plans, COLLECTED_AT, attribution_rule="v2")
        self.assertEqual(second["runs"][0]["status"], "skipped")
        self.assertEqual(self.summary_of(run_dir)["usage"]["input_tokens"]["value"],
                         1500, "the v1 number must not be doubled by a v2 pass")

    def test_inseparable_neighbours_are_refused_rather_than_split(self):
        run_dir, neighbour = self.make_run(), self.make_run()
        plans = [vtc.RunPlan(run_dir, {"main": GEMINI}, A_START, A_END),
                 vtc.RunPlan(neighbour, {"main": GEMINI},
                             "2026-08-16T10:05:30Z", "2026-08-16T10:09:00Z")]
        report = vtc.run_backfill(WindowedFakeClient(self.OWN_TAIL),
                                  "SYNTHETIC-project", plans, COLLECTED_AT,
                                  attribution_rule="v2")
        self.assertEqual(report["status_counts"], {vtc.CONTAMINATED_STATUS: 2})
        self.assertIsNone(self.summary_of(run_dir)["usage"]["input_tokens"]["value"])

    def test_a_v2_refusal_does_not_overwrite_the_v1_refusal_it_disagrees_with(self):
        run_dir, neighbour = self.make_run(), self.make_run()
        plans = self._plans(run_dir, neighbour)
        burst = self.OWN_TAIL + [_series(GEMINI, "input", 800, THIRD_PARTY)]
        vtc.run_backfill(WindowedFakeClient(burst), "SYNTHETIC-project", plans,
                         COLLECTED_AT, attribution_rule="v1")
        vtc.run_backfill(WindowedFakeClient(burst), "SYNTHETIC-project", plans,
                         COLLECTED_AT, attribution_rule="v2")
        v1 = os.path.join(run_dir, vtc.REFUSAL_MARKERS["v1"])
        v2 = os.path.join(run_dir, vtc.REFUSAL_MARKERS["v2"])
        self.assertTrue(os.path.isfile(v1) and os.path.isfile(v2))
        with open(v2, encoding="utf-8") as fh:
            payload = json.load(fh)
        self.assertEqual(payload["attribution_rule"]["id"], vtc.ATTRIBUTION_METHOD_V2)

    def test_the_report_states_which_rule_the_batch_was_collected_under(self):
        _, report, _ = self._backfill(self.OWN_TAIL)
        self.assertEqual(report["attribution"]["rule"], "v2")
        self.assertEqual(report["attribution"]["event_type"], vtc.BACKFILL_EVENT_V2)
        self.assertEqual(report["attribution"]["tail_seconds"],
                         vtc.DEFAULT_TAIL_SECONDS)
        self.assertEqual(report["attribution"]["counts_confidence"], "authoritative")

    def test_an_unknown_rule_is_refused_rather_than_defaulted(self):
        run_dir, neighbour = self.make_run(), self.make_run()
        with self.assertRaises(vtc.CollectorError):
            vtc.run_backfill(WindowedFakeClient([]), "SYNTHETIC-project",
                             self._plans(run_dir, neighbour), COLLECTED_AT,
                             attribution_rule="v9")


# --------------------------------------------------------------------------- #
# v3: the same windows as v2, judged by rate instead of by a fixed constant.
#
# 31 of batch 1's 35 remaining refusals were the fixed 3M ceiling firing on long
# Gemini-executor runs — a 47-minute run legitimately produces more input-side
# tokens than a per-run constant allows, so the constant was refusing duration,
# not contamination. v3 changes ONLY that test. The window, the ownership rule
# and the third-party baseline probe are byte-for-byte the v2 ones, and the
# tests below have to hold both halves of that claim.
# --------------------------------------------------------------------------- #
#: A 50-minute executor run: over the fixed ceiling, unremarkable by rate.
LONG_START, LONG_END = "2026-08-16T10:00:00Z", "2026-08-16T10:50:00Z"
#: Far enough away that the long run's ownership is never squeezed by it.
FAR_START, FAR_END = "2026-08-16T12:00:00Z", "2026-08-16T12:05:00Z"


class RateCeilingBackfillTests(RunDirMixin, unittest.TestCase):

    def _plans(self, run_dir, neighbour_dir, start=LONG_START, end=LONG_END):
        return [vtc.RunPlan(run_dir=run_dir, legs={"main": GEMINI},
                            start=start, end=end),
                vtc.RunPlan(run_dir=neighbour_dir, legs={"main": GEMINI},
                            start=FAR_START, end=FAR_END)]

    def _backfill(self, series, rule="v3", plans=None, **kwargs):
        run_dir, neighbour = self.make_run(), self.make_run()
        plans = plans(run_dir, neighbour) if plans else self._plans(run_dir, neighbour)
        report = vtc.run_backfill(WindowedFakeClient(series), "SYNTHETIC-project",
                                  plans, COLLECTED_AT, attribution_rule=rule, **kwargs)
        return run_dir, report, report["runs"][0]

    #: One long run's own work, all of it inside its own window.
    LONG_OWN = [
        _series(GEMINI, "input", 4_000_000, "2026-08-16T10:25:00Z"),
        _series(GEMINI, "output", 61_400, "2026-08-16T10:25:00Z"),
    ]

    def test_v2_refuses_the_long_run_on_the_fixed_ceiling(self):
        # The negative control. Without it the v3 test below proves nothing.
        _, _, run = self._backfill(self.LONG_OWN, rule="v2")
        self.assertEqual(run["status"], vtc.CONTAMINATED_STATUS)
        self.assertTrue(any("ceiling" in r for r in run["contamination"]["reasons"]))

    def test_v3_attributes_the_long_run_the_fixed_ceiling_refused(self):
        run_dir, _, run = self._backfill(self.LONG_OWN)
        self.assertEqual(run["status"], "backfilled", run.get("detail"))
        usage = self.summary_of(run_dir)["usage"]
        self.assertEqual(usage["input_tokens"]["value"], 4_000_000)
        self.assertEqual(usage["output_tokens"]["value"], 61_400)
        self.assertEqual(usage["input_tokens"]["confidence"], "derived")

    def test_v3_still_refuses_a_window_whose_rate_is_impossible(self):
        # Same 50-minute window, 40x the tokens: 240k/s is not one agent working.
        _, _, run = self._backfill(
            [_series(GEMINI, "input", 750_000_000, "2026-08-16T10:25:00Z")])
        self.assertEqual(run["status"], vtc.CONTAMINATED_STATUS)
        self.assertTrue(any("per second" in r for r in run["contamination"]["reasons"]))

    def test_the_third_party_probe_is_the_v2_one_unchanged(self):
        # KNOWN LIMIT, load-bearing: the historical smoke contamination ran at
        # 16,693 input-side tokens/s, which a 25,000/s ceiling does NOT catch.
        # What catches it is the baseline probe, which v3 leaves alone. If this
        # test ever goes green for the wrong reason, v3 has no defence left
        # against a stranger sharing the meter at a believable rate.
        _, _, run = self._backfill(
            [_series(GEMINI, "input", 4_000_000, "2026-08-16T10:25:00Z"),
             _series(GEMINI, "input", 1_274_568, "2026-08-16T10:55:30Z")])
        self.assertEqual(run["status"], vtc.CONTAMINATED_STATUS)
        reasons = run["contamination"]["reasons"]
        self.assertTrue(any("post-run" in r for r in reasons), reasons)
        self.assertFalse(any("per second" in r for r in reasons), reasons)

    def test_a_refused_run_is_left_unavailable_not_zero(self):
        run_dir, _, _ = self._backfill(
            [_series(GEMINI, "input", 750_000_000, "2026-08-16T10:25:00Z")])
        self.assertIsNone(self.summary_of(run_dir)["usage"]["input_tokens"]["value"])

    def test_the_event_names_v3_as_the_rule_that_attributed_it(self):
        run_dir, _, _ = self._backfill(self.LONG_OWN)
        events = [e for e in read_events(os.path.join(run_dir, "events.jsonl"))
                  if e["event_type"] == vtc.BACKFILL_EVENT_V3]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["attribution_method"], vtc.ATTRIBUTION_METHOD_V3)
        self.assertEqual(events[0]["attribution_confidence"], "derived")
        self.assertEqual(events[0]["counts_confidence"], "authoritative")
        rule = events[0]["attribution_rule"]
        self.assertEqual(rule["rule"], "v3")
        self.assertEqual(rule["id"], vtc.ATTRIBUTION_METHOD_V3)
        # The window is the v2 window: v3 changed the ceiling, not the boundaries.
        self.assertEqual(rule["bounded_by"], "ingestion_tail")
        self.assertEqual(rule["attribution_window"]["end"],
                         "2026-08-16T10:51:00.000000Z")

    def test_the_report_states_the_rate_ceiling_it_applied(self):
        _, report, _ = self._backfill(self.LONG_OWN)
        self.assertEqual(report["attribution"]["rule"], "v3")
        self.assertEqual(report["attribution"]["event_type"], vtc.BACKFILL_EVENT_V3)
        self.assertEqual(report["attribution"]["method"], vtc.ATTRIBUTION_METHOD_V3)
        guard = report["contamination_guard"]
        self.assertEqual(guard["plausibility_ceiling"], "input_side_tokens_per_second")
        self.assertEqual(guard["input_side_ceiling_tokens_per_second"],
                         vtc.DEFAULT_CEILING_INPUT_TOKENS_PER_SECOND)
        # The constant v3 replaces must not also be reported as if it applied.
        self.assertIsNone(guard["input_side_ceiling_tokens"])

    def test_a_v3_refusal_does_not_overwrite_the_v2_refusal_beside_it(self):
        run_dir, neighbour = self.make_run(), self.make_run()
        plans = self._plans(run_dir, neighbour)
        burst = [_series(GEMINI, "input", 750_000_000, "2026-08-16T10:25:00Z")]
        for rule in ("v2", "v3"):
            vtc.run_backfill(WindowedFakeClient(burst), "SYNTHETIC-project", plans,
                             COLLECTED_AT, attribution_rule=rule)
        v2 = os.path.join(run_dir, vtc.REFUSAL_MARKERS["v2"])
        v3 = os.path.join(run_dir, vtc.REFUSAL_MARKERS["v3"])
        self.assertTrue(os.path.isfile(v2) and os.path.isfile(v3))
        with open(v3, encoding="utf-8") as fh:
            payload = json.load(fh)
        self.assertEqual(payload["attribution_rule"]["id"], vtc.ATTRIBUTION_METHOD_V3)
        self.assertEqual(payload["attribution_rule"]["rule"], "v3")

    def test_a_v3_pass_clears_the_v3_marker_a_failed_v3_pass_left(self):
        # Re-running v3 after fixing whatever made it refuse must not leave a
        # marker claiming nothing was written next to the event that was.
        run_dir, neighbour = self.make_run(), self.make_run()
        plans = self._plans(run_dir, neighbour)
        vtc.run_backfill(
            WindowedFakeClient([_series(GEMINI, "input", 750_000_000,
                                        "2026-08-16T10:25:00Z")]),
            "SYNTHETIC-project", plans, COLLECTED_AT, attribution_rule="v3")
        self.assertTrue(os.path.isfile(os.path.join(run_dir,
                                                    vtc.REFUSAL_MARKERS["v3"])))
        report = vtc.run_backfill(WindowedFakeClient(self.LONG_OWN),
                                  "SYNTHETIC-project", plans, COLLECTED_AT,
                                  attribution_rule="v3")
        self.assertEqual(report["runs"][0]["status"], "backfilled")
        self.assertFalse(os.path.isfile(os.path.join(run_dir,
                                                     vtc.REFUSAL_MARKERS["v3"])))

    def test_a_leg_already_filled_under_v2_is_not_filled_again_under_v3(self):
        run_dir, neighbour = self.make_run(), self.make_run()
        plans = self._plans(run_dir, neighbour)
        clean = [_series(GEMINI, "input", 1500, "2026-08-16T10:25:00Z")]
        first = vtc.run_backfill(WindowedFakeClient(clean), "SYNTHETIC-project",
                                 plans, COLLECTED_AT, attribution_rule="v2")
        self.assertEqual(first["runs"][0]["status"], "backfilled")
        second = vtc.run_backfill(WindowedFakeClient(clean), "SYNTHETIC-project",
                                  plans, COLLECTED_AT, attribution_rule="v3")
        self.assertEqual(second["runs"][0]["status"], "skipped")
        self.assertEqual(self.summary_of(run_dir)["usage"]["input_tokens"]["value"],
                         1500, "the v2 number must not be doubled by a v3 pass")

    def test_a_v3_backfill_does_not_count_as_a_turn(self):
        run_dir, neighbour = self.make_run(), self.make_run()
        before = self.summary_of(run_dir)["behavior"]["turns"]["value"]
        vtc.run_backfill(WindowedFakeClient(self.LONG_OWN), "SYNTHETIC-project",
                         self._plans(run_dir, neighbour), COLLECTED_AT,
                         attribution_rule="v3")
        self.assertEqual(self.summary_of(run_dir)["behavior"]["turns"]["value"], before)

    def test_v3_inherits_the_ownership_boundaries_it_did_not_change(self):
        # An inseparable neighbour is still inseparable under v3: the rate
        # ceiling says nothing about whose tokens these are.
        run_dir, neighbour = self.make_run(), self.make_run()
        plans = [vtc.RunPlan(run_dir, {"main": GEMINI}, LONG_START, LONG_END),
                 vtc.RunPlan(neighbour, {"main": GEMINI},
                             "2026-08-16T10:50:30Z", "2026-08-16T10:55:00Z")]
        report = vtc.run_backfill(WindowedFakeClient(self.LONG_OWN),
                                  "SYNTHETIC-project", plans, COLLECTED_AT,
                                  attribution_rule="v3")
        self.assertEqual(report["status_counts"], {vtc.CONTAMINATED_STATUS: 2})
        self.assertIsNone(self.summary_of(run_dir)["usage"]["input_tokens"]["value"])

    def test_the_cli_accepts_v3_and_its_rate_flag(self):
        # A plan with no project stops main() at load with a return of 2. An
        # argparse rejection would SystemExit instead — which is what this
        # distinguishes: the flags parse, the run just has nothing to run on.
        plan = os.path.join(tempfile.mkdtemp(prefix="SYNTHETIC-plan-"), "plan.json")
        self.addCleanup(shutil.rmtree, os.path.dirname(plan), True)
        with open(plan, "w", encoding="utf-8") as fh:
            json.dump({"runs": []}, fh)
        self.assertEqual(
            vtc.main(["--plan", plan, "--attribution-rule", "v3",
                      "--ceiling-input-tokens-per-second", "9000", "--dry-run"]), 2)


if __name__ == "__main__":
    unittest.main()
