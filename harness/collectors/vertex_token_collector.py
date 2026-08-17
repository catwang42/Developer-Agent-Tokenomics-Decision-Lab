"""Provider-side token collector for Vertex AI publisher models (SPEC 2.9 item 1).

Product B exposes no machine-readable usage in headless mode, so its token counts
have to come from the billing plane. This module reads Cloud Monitoring's

    aiplatform.googleapis.com/publisher/online_serving/token_count

on the ``aiplatform.googleapis.com/PublisherModel`` monitored resource, attributes
the points to a run by time window, and backfills the run's telemetry.

What the tiers mean here (and why they are not the same tier):
  * **counts** are ``authoritative`` — they are the provider's own meter, the same
    surface the bill is computed from;
  * **per-run attribution** is ``derived`` — a point is assigned to the run whose
    ``[start - guard, end + guard]`` window contains it. That is only sound
    because subject runs are serialized (see the README's quiet-window rule).

The weaker of the two is what the summary field carries (``derived``); the
provenance — metric type, window, ``model_user_id``, and the authoritative-count
claim — is written into the event log, which is where an auditor should look.

Never fabricate, never zero-fill: a token class with no points in the window is
simply absent from the backfill event, so the deriver records it *unavailable*.
An observed ``type`` label this module does not know how to map is never dropped
and never silently folded into another class — it is recorded verbatim in the
event and flagged at the top of the backfill report.

Stdlib only, by design: ``requirements.txt`` is a pinned two-line file and the
test gate fails on venv drift. HTTP goes through ``urllib``; credentials come
from ``gcloud auth print-access-token``. All network access sits behind an
injectable client so the tests run fully offline.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from harness.telemetry.telemetry import (  # noqa: E402
    EventLog,
    read_events,
    derive_summary,
    tiered,
    validate,
)

METRIC_TYPE = "aiplatform.googleapis.com/publisher/online_serving/token_count"
MONITORED_RESOURCE = "aiplatform.googleapis.com/PublisherModel"
DEFAULT_PUBLISHER = "google"
DEFAULT_GUARD_SECONDS = 60
MONITORING_ENDPOINT = "https://monitoring.googleapis.com/v3"

#: Metric ``type`` label -> schema usage field. Verified against the metric's
#: type label at the SPEC 2.9 pre-build gate: the label carries both
#: ``cache_read_input`` and ``cache_write_1h_input``, which is what makes
#: cache-aware Product-B costing possible at all.
TYPE_TO_USAGE_FIELD: Dict[str, str] = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache_read_input": "cache_read_tokens",
    "cache_write_1h_input": "cache_creation_tokens",
}

BACKFILL_EVENT = "provider_usage_backfill"
COLLECTOR_ID = "vertex_token_collector"


class CollectorError(RuntimeError):
    """Raised when collection or backfill cannot proceed honestly."""


# --------------------------------------------------------------------------- #
# Time helpers (RFC3339 in, RFC3339 out; Python 3.10 has no 'Z' parser)
# --------------------------------------------------------------------------- #
def parse_ts(value: str) -> datetime:
    """Parse an RFC3339/ISO8601 timestamp to an aware UTC datetime."""
    if not isinstance(value, str) or not value.strip():
        raise CollectorError(f"not a timestamp: {value!r}")
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise CollectorError(f"unparseable timestamp {value!r}: {exc}") from exc
    if dt.tzinfo is None:
        raise CollectorError(
            f"timestamp {value!r} has no timezone — refusing to guess UTC")
    return dt.astimezone(timezone.utc)


def format_ts(dt: datetime) -> str:
    """Format an aware datetime as RFC3339 with a 'Z' suffix (the API's dialect)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# --------------------------------------------------------------------------- #
# Query construction (pure)
# --------------------------------------------------------------------------- #
def _label_clause(label: str, values: Iterable[str]) -> str:
    """``label = "v"`` for one value, ``label = one_of("a","b")`` for several.

    ``one_of`` takes a COMMA-separated list. Writing it with ``OR`` between the
    quoted values is not a laxer spelling of the same thing — the Monitoring API
    rejects the whole filter with HTTP 400 ("Could not parse filter"), so a run
    whose legs span two models used to fail collection outright. Observed live
    against project vital-octagon-19612 on 2026-08-17; regression-tested in
    tests/test_vertex_collector.py.
    """
    vals = sorted({str(v).strip() for v in values if str(v).strip()})
    if not vals:
        raise CollectorError(f"no {label} declared — refusing an unfiltered query")
    if len(vals) == 1:
        return f'{label} = "{vals[0]}"'
    return f"{label} = one_of({','.join(chr(34) + v + chr(34) for v in vals)})"


def build_filter(model_user_ids: Iterable[str],
                 publisher: Any = DEFAULT_PUBLISHER) -> str:
    """Cloud Monitoring filter for one run's declared subject models.

    Restricting to the declared models is also the quiet-window escape hatch: an
    unrelated Gemini-calling workload in the same project (e.g. the ta-daily
    Cloud Run job) is excluded here as long as it uses a different model.

    ``publisher`` accepts one publisher or several. Several is not a widening of
    the query — every model is still named explicitly — it is what makes a
    MIXED-PUBLISHER run collectable at all: a C5 run's conductor is an Anthropic
    publisher model and its executor a Google one, and a filter pinned to
    ``publisher = "google"`` silently returns nothing for the conductor. The
    publisher is DECLARED per leg in the plan, never inferred from the model
    name (SPEC 6.3).
    """
    ids = [str(m).strip() for m in model_user_ids if str(m).strip()]
    if not ids:
        raise CollectorError("no model_user_id declared — refusing an unfiltered query")
    publishers = [publisher] if isinstance(publisher, str) else list(publisher)
    return " AND ".join([
        f'metric.type = "{METRIC_TYPE}"',
        f'resource.type = "{MONITORED_RESOURCE}"',
        _label_clause("resource.labels.publisher", publishers),
        _label_clause("resource.labels.model_user_id", ids),
    ])


def build_window(start: str, end: str,
                 guard_seconds: int = DEFAULT_GUARD_SECONDS) -> Tuple[datetime, datetime]:
    """A run's ``[start - guard, end + guard]`` attribution window."""
    if guard_seconds < 0:
        raise CollectorError(f"guard_seconds must be >= 0, got {guard_seconds}")
    lo, hi = parse_ts(start), parse_ts(end)
    if hi < lo:
        raise CollectorError(f"run window ends before it starts: {start} .. {end}")
    guard = timedelta(seconds=guard_seconds)
    return lo - guard, hi + guard


# --------------------------------------------------------------------------- #
# Monitoring client (the only network boundary)
# --------------------------------------------------------------------------- #
class MonitoringClient:
    """Interface: return raw ``timeSeries`` objects for a filter + interval.

    Tests substitute a fake; nothing else in this module touches the network.
    """

    def list_time_series(self, project: str, filter_str: str,
                         window: Tuple[datetime, datetime]) -> List[Dict[str, Any]]:
        raise NotImplementedError


class GcloudMonitoringClient(MonitoringClient):
    """Cloud Monitoring v3 over urllib, authenticated by the gcloud CLI.

    Read-only: the only credential use is ``gcloud auth print-access-token``, and
    the only call is ``timeSeries.list``. No model is invoked, so this costs
    nothing against a model budget.
    """

    def __init__(self, access_token: Optional[str] = None, timeout_s: int = 60):
        self._token = access_token
        self.timeout_s = timeout_s

    def _access_token(self) -> str:
        if self._token:
            return self._token
        try:
            proc = subprocess.run(
                ["gcloud", "auth", "print-access-token"],
                capture_output=True, text=True, timeout=60, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CollectorError(f"could not run gcloud for an access token: {exc}") from exc
        if proc.returncode != 0:
            raise CollectorError(
                f"gcloud auth print-access-token failed ({proc.returncode}): "
                f"{proc.stderr.strip()}")
        self._token = proc.stdout.strip()
        if not self._token:
            raise CollectorError("gcloud returned an empty access token")
        return self._token

    def list_time_series(self, project: str, filter_str: str,
                         window: Tuple[datetime, datetime]) -> List[Dict[str, Any]]:
        lo, hi = window
        series: List[Dict[str, Any]] = []
        page_token = ""
        while True:
            params = {
                "filter": filter_str,
                "interval.startTime": format_ts(lo),
                "interval.endTime": format_ts(hi),
                "view": "FULL",
            }
            if page_token:
                params["pageToken"] = page_token
            url = (f"{MONITORING_ENDPOINT}/projects/{urllib.parse.quote(project)}"
                   f"/timeSeries?{urllib.parse.urlencode(params)}")
            req = urllib.request.Request(
                url, headers={"Authorization": f"Bearer {self._access_token()}"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")[:500]
                raise CollectorError(f"monitoring API {exc.code}: {body}") from exc
            except urllib.error.URLError as exc:
                raise CollectorError(f"monitoring API unreachable: {exc}") from exc
            series.extend(payload.get("timeSeries") or [])
            page_token = payload.get("nextPageToken") or ""
            if not page_token:
                return series


# --------------------------------------------------------------------------- #
# Aggregation (pure)
# --------------------------------------------------------------------------- #
#: Metric label keys that split a model's tokens into differently-priced or
#: differently-sourced buckets. Totals are summed across them, but the split is
#: recorded verbatim per series so a later analysis can re-cost by modality,
#: region or caching without re-querying (observed keys, 2026-08-16).
_BREAKDOWN_METRIC_LABELS = (
    "type", "modality", "request_type", "shared_request_type",
    "explicit_caching", "source", "accounting_resource", "max_token_size",
)
_BREAKDOWN_RESOURCE_LABELS = ("model_version_id", "location", "publisher")


@dataclass
class ModelTotals:
    """Per-``model_user_id`` totals within one attribution window."""
    model_user_id: str
    totals_by_type: Dict[str, int] = field(default_factory=dict)
    points_in_window: int = 0
    #: One entry per contributing time series: its full label set and its total.
    #: Summing by ``type`` alone would silently merge e.g. text and image tokens,
    #: which are priced differently; this keeps the split recoverable.
    series_breakdown: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Collection:
    """The result of aggregating one window's time series."""
    window_start: str
    window_end: str
    guard_seconds: int
    by_model: Dict[str, ModelTotals] = field(default_factory=dict)
    points_in_window: int = 0
    points_outside_window: int = 0

    def unmapped_types(self) -> Dict[str, Dict[str, int]]:
        """Observed ``type`` labels with no mapping, per model. Never dropped."""
        out: Dict[str, Dict[str, int]] = {}
        for mid, totals in self.by_model.items():
            extra = {t: v for t, v in totals.totals_by_type.items()
                     if t not in TYPE_TO_USAGE_FIELD}
            if extra:
                out[mid] = dict(sorted(extra.items()))
        return out

    def as_dict(self) -> Dict[str, Any]:
        return {
            "window": {"start": self.window_start, "end": self.window_end,
                       "guard_seconds": self.guard_seconds},
            "points_in_window": self.points_in_window,
            "points_outside_window": self.points_outside_window,
            "by_model": {mid: dict(sorted(t.totals_by_type.items()))
                         for mid, t in sorted(self.by_model.items())},
            "unmapped_types": self.unmapped_types(),
        }


def _point_value(point: Dict[str, Any]) -> int:
    """Read a token count off a point. A value we cannot read is an error, not 0."""
    value = point.get("value") or {}
    for key in ("int64Value", "doubleValue"):
        if key in value and value[key] is not None:
            try:
                return int(round(float(value[key])))
            except (TypeError, ValueError) as exc:
                raise CollectorError(f"unreadable point value {value!r}: {exc}") from exc
    raise CollectorError(
        f"point carries no int64Value/doubleValue: {value!r} — refusing to treat as 0")


def _model_user_id(series: Dict[str, Any]) -> str:
    resource = (series.get("resource") or {}).get("labels") or {}
    metric = (series.get("metric") or {}).get("labels") or {}
    mid = resource.get("model_user_id") or metric.get("model_user_id")
    if not mid:
        raise CollectorError(
            "time series carries no model_user_id label — cannot attribute it to a leg")
    return str(mid)


def aggregate_series(series: List[Dict[str, Any]],
                     window: Tuple[datetime, datetime],
                     guard_seconds: int = DEFAULT_GUARD_SECONDS) -> Collection:
    """Sum points that fall inside the window, grouped by model_user_id and type.

    A DELTA point covers ``[startTime, endTime]``; it is attributed to the window
    when its ``endTime`` lands inside it (the alignment period is short relative
    to a run, and the guard absorbs the edges). Points outside are counted, not
    discarded silently, so the report can show what the window excluded.
    """
    lo, hi = window
    result = Collection(window_start=format_ts(lo), window_end=format_ts(hi),
                        guard_seconds=guard_seconds)
    for s in series:
        mid = _model_user_id(s)
        type_label = ((s.get("metric") or {}).get("labels") or {}).get("type")
        if not type_label:
            raise CollectorError(
                f"time series for {mid} carries no 'type' label — refusing to "
                f"guess which token class it is")
        series_total = 0
        series_points = 0
        for point in s.get("points") or []:
            end = (point.get("interval") or {}).get("endTime")
            if not end:
                raise CollectorError(f"point for {mid}/{type_label} has no interval.endTime")
            when = parse_ts(end)
            if not (lo <= when <= hi):
                result.points_outside_window += 1
                continue
            series_total += _point_value(point)
            series_points += 1
        if not series_points:
            # No entry at all: a model with an empty totals block would read as a
            # measured zero. Absent means unmeasured (CLAUDE.md rule 3).
            continue
        totals = result.by_model.setdefault(mid, ModelTotals(model_user_id=mid))
        totals.totals_by_type[type_label] = (
            totals.totals_by_type.get(type_label, 0) + series_total)
        totals.points_in_window += series_points
        totals.series_breakdown.append(_series_labels(s, series_total, series_points))
        result.points_in_window += series_points
    return result


def _series_labels(series: Dict[str, Any], total: int, points: int) -> Dict[str, Any]:
    """The labels that make one contributing series distinct, plus its total."""
    metric = (series.get("metric") or {}).get("labels") or {}
    resource = (series.get("resource") or {}).get("labels") or {}
    labels = {k: metric[k] for k in _BREAKDOWN_METRIC_LABELS if k in metric}
    labels.update({k: resource[k] for k in _BREAKDOWN_RESOURCE_LABELS if k in resource})
    return {"labels": dict(sorted(labels.items())), "tokens": total, "points": points}


def usage_fields(totals_by_type: Dict[str, int]) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Split observed type totals into (mapped schema fields, unmapped types).

    A mapped class that was not observed is simply absent from the first dict —
    the deriver then records it *unavailable*, never 0 (CLAUDE.md rule 3).
    """
    mapped: Dict[str, int] = {}
    unmapped: Dict[str, int] = {}
    for type_label, total in totals_by_type.items():
        target = TYPE_TO_USAGE_FIELD.get(type_label)
        if target is None:
            unmapped[type_label] = total
        else:
            mapped[target] = mapped.get(target, 0) + total
    return mapped, unmapped


# --------------------------------------------------------------------------- #
# Run windows
# --------------------------------------------------------------------------- #
def run_window_from_events(run_dir: str) -> Tuple[str, str]:
    """First and last event timestamps of a run — its uninstrumented wall window."""
    path = os.path.join(run_dir, "events.jsonl")
    if not os.path.exists(path):
        raise CollectorError(f"no events.jsonl in {run_dir} — cannot bound a window")
    stamps = [parse_ts(e["ts"]) for e in read_events(path) if e.get("ts")]
    if not stamps:
        raise CollectorError(f"{path} has no timestamped events")
    return format_ts(min(stamps)), format_ts(max(stamps))


# --------------------------------------------------------------------------- #
# Backfill
# --------------------------------------------------------------------------- #
@dataclass
class RunPlan:
    """One run to backfill: where it is, and which model_user_id each leg used."""
    run_dir: str
    legs: Dict[str, str]                 # leg_id -> model_user_id
    start: Optional[str] = None          # default: first event ts
    end: Optional[str] = None            # default: last event ts
    #: leg_id -> publisher, DECLARED (never inferred from the model name). A leg
    #: that does not declare one is DEFAULT_PUBLISHER, which keeps every existing
    #: single-product Gemini plan valid unchanged.
    publishers: Dict[str, str] = field(default_factory=dict)

    def publisher_for(self, leg_id: str) -> str:
        return self.publishers.get(leg_id, DEFAULT_PUBLISHER)

    @staticmethod
    def from_dict(raw: Dict[str, Any]) -> "RunPlan":
        """Parse one plan entry.

        A leg value is either a bare ``model_user_id`` string (publisher defaults
        to google) or an object ``{"model_user_id": ..., "publisher": ...}``. The
        object form exists for mixed-publisher runs such as C5, whose conductor is
        an Anthropic publisher model — the publisher is stated by the operator,
        not guessed from the id.
        """
        raw_legs = raw.get("legs") or {}
        if not isinstance(raw_legs, dict) or not raw_legs:
            raise CollectorError(f"plan entry for {raw.get('run_dir')!r} declares no legs")
        legs: Dict[str, str] = {}
        publishers: Dict[str, str] = {}
        for leg_id, spec in raw_legs.items():
            leg_id = str(leg_id)
            if isinstance(spec, dict):
                model = spec.get("model_user_id")
                if not model:
                    raise CollectorError(
                        f"plan entry for {raw.get('run_dir')!r} leg {leg_id!r} declares "
                        f"no model_user_id")
                legs[leg_id] = str(model)
                if spec.get("publisher"):
                    publishers[leg_id] = str(spec["publisher"])
            else:
                legs[leg_id] = str(spec)
        return RunPlan(run_dir=raw["run_dir"], legs=legs,
                       start=raw.get("start"), end=raw.get("end"),
                       publishers=publishers)


def _leg_model_map(plan: RunPlan) -> Dict[str, str]:
    """Reject an ambiguous map: two legs on one model cannot be split by model."""
    inverted: Dict[str, List[str]] = {}
    for leg_id, mid in plan.legs.items():
        inverted.setdefault(mid, []).append(leg_id)
    clashes = {m: sorted(ls) for m, ls in inverted.items() if len(ls) > 1}
    if clashes:
        raise CollectorError(
            f"{plan.run_dir}: legs share a model_user_id {clashes} — billing-plane "
            f"metrics cannot separate them; do not attribute")
    return plan.legs


def already_backfilled(events: List[Dict[str, Any]]) -> List[str]:
    """Leg ids that already carry a provider backfill (idempotence guard)."""
    return sorted({str(e.get("leg", "main")) for e in events
                   if e.get("event_type") == BACKFILL_EVENT})


def build_backfill_event(leg_id: str, model_user_id: str, collection: Collection,
                         collected_at: str) -> Optional[Dict[str, Any]]:
    """The event to append for one leg, or None when the window held no points."""
    totals = collection.by_model.get(model_user_id)
    if totals is None or not totals.totals_by_type:
        return None
    mapped, unmapped = usage_fields(totals.totals_by_type)
    reason = (f"provider-side {METRIC_TYPE}; counts authoritative, attribution "
              f"derived from the run's time window (serialized runs)")
    event: Dict[str, Any] = {
        "leg": leg_id,
        "collector": COLLECTOR_ID,
        "metric_type": METRIC_TYPE,
        "monitored_resource": MONITORED_RESOURCE,
        "model_user_id": model_user_id,
        "counts_confidence": "authoritative",
        "attribution_confidence": "derived",
        "attribution_method": "time_window_serialized_runs",
        "window": {"start": collection.window_start, "end": collection.window_end,
                   "guard_seconds": collection.guard_seconds},
        "points_in_window": totals.points_in_window,
        "observed_types": dict(sorted(totals.totals_by_type.items())),
        "series_breakdown": totals.series_breakdown,
        "usage": {cls: tiered(v, "derived", reason=reason) for cls, v in sorted(mapped.items())},
    }
    if unmapped:
        # Never dropped, never folded into a mapped class. The report shouts about it.
        event["unmapped_types"] = dict(sorted(unmapped.items()))
    event["ts"] = collected_at
    return event


@dataclass
class BackfillOutcome:
    run_dir: str
    run_id: str
    status: str                                   # backfilled | skipped | no_data | error
    detail: str = ""
    legs_filled: Dict[str, Dict[str, int]] = field(default_factory=dict)
    unmapped_types: Dict[str, Dict[str, int]] = field(default_factory=dict)
    new_legs: List[str] = field(default_factory=list)
    window: Optional[Dict[str, Any]] = None
    validated: Optional[bool] = None
    validation_reasons: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in (None, [], {})} | {
            "run_dir": self.run_dir, "run_id": self.run_id, "status": self.status}


def _rewrite_summary(run_dir: str, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Re-derive summary.json from the (now longer) event log and write it back.

    Hand-editing usage into summary.json would fail ``telemetry.validate``, which
    re-derives from the event log and diffs — so the only honest backfill is:
    append events, re-derive, rewrite. Caller-supplied blocks the deriver cannot
    know (identity, economics, human_effort) and any extra diagnostic keys are
    carried across from the stored summary.
    """
    summary_path = os.path.join(run_dir, "summary.json")
    with open(summary_path, encoding="utf-8") as fh:
        stored = json.load(fh)
    rederived = derive_summary(
        events,
        run_id=stored.get("run_id", ""),
        task_id=stored.get("task_id", ""),
        task_suite_version=stored.get("task_suite_version", ""),
        configuration_id=stored.get("configuration_id", "C1"),
        manifest_ref=stored.get("manifest_ref", ""),
        identity=stored.get("identity"),
        economics=stored.get("economics"),
        human_effort=stored.get("human_effort"),
        hidden_test_hash=stored.get("hidden_test_hash"),
    )
    merged = dict(stored)
    merged.update(rederived)
    if "frontier_token_share" in stored:
        # Pure function of legs, and the legs just changed — recomputing keeps the
        # C5 diagnostic consistent with the usage it is a share of.
        from harness.runner.run import _frontier_token_share  # local: avoid import weight
        merged["frontier_token_share"] = _frontier_token_share(merged["legs"])
    tmp = summary_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(merged, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, summary_path)
    return merged


def backfill_run(plan: RunPlan, collection: Collection, collected_at: str,
                 dry_run: bool = False) -> BackfillOutcome:
    """Append provider-side usage to one run and re-derive its summary."""
    events_path = os.path.join(plan.run_dir, "events.jsonl")
    summary_path = os.path.join(plan.run_dir, "summary.json")
    for required in (events_path, summary_path):
        if not os.path.exists(required):
            return BackfillOutcome(plan.run_dir, "", "error", f"missing {required}")
    events = list(read_events(events_path))
    with open(summary_path, encoding="utf-8") as fh:
        run_id = json.load(fh).get("run_id", "")

    done = already_backfilled(events)
    if done:
        return BackfillOutcome(plan.run_dir, run_id, "skipped",
                               f"already backfilled for legs {done} — re-running would "
                               f"double-count; delete the events to redo it")

    known_legs = {str(e.get("leg", "main")) for e in events
                  if e.get("event_type") == "model_call_completed"} or {"main"}
    outcome = BackfillOutcome(plan.run_dir, run_id, "no_data",
                              window={"start": collection.window_start,
                                      "end": collection.window_end,
                                      "guard_seconds": collection.guard_seconds})
    new_events: List[Dict[str, Any]] = []
    for leg_id, model_user_id in sorted(_leg_model_map(plan).items()):
        event = build_backfill_event(leg_id, model_user_id, collection, collected_at)
        if event is None:
            continue
        new_events.append(event)
        mapped, unmapped = usage_fields(collection.by_model[model_user_id].totals_by_type)
        outcome.legs_filled[leg_id] = mapped
        if unmapped:
            outcome.unmapped_types[f"{leg_id}/{model_user_id}"] = unmapped
        if leg_id not in known_legs:
            outcome.new_legs.append(leg_id)

    if not new_events:
        outcome.detail = ("no points for the declared model_user_id in this window — "
                          "usage stays unavailable (not zero)")
        return outcome
    if dry_run:
        outcome.status = "dry_run"
        outcome.detail = f"would append {len(new_events)} backfill event(s)"
        return outcome

    log = EventLog(events_path)
    for event in new_events:
        payload = {k: v for k, v in event.items() if k != "ts"}
        log.append(BACKFILL_EVENT, event["ts"], **payload)
    _rewrite_summary(plan.run_dir, list(read_events(events_path)))

    ok, reasons = validate(plan.run_dir)
    outcome.status = "backfilled" if ok else "error"
    outcome.validated = ok
    outcome.validation_reasons = [] if ok else list(reasons)
    if not ok:
        outcome.detail = "summary failed audit-grade validation after backfill"
    return outcome


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def build_report(project: str, collected_at: str, guard_seconds: int,
                 outcomes: List[BackfillOutcome]) -> Dict[str, Any]:
    """Machine-readable backfill report. Unmapped types sit at the top, on purpose."""
    unmapped: Dict[str, Dict[str, int]] = {}
    for out in outcomes:
        for key, types in out.unmapped_types.items():
            bucket = unmapped.setdefault(key, {})
            for t, v in types.items():
                bucket[t] = bucket.get(t, 0) + v
    counts: Dict[str, int] = {}
    for out in outcomes:
        counts[out.status] = counts.get(out.status, 0) + 1
    return {
        "report": "provider-side token backfill",
        "collector": COLLECTOR_ID,
        "metric_type": METRIC_TYPE,
        "project": project,
        "collected_at": collected_at,
        "guard_seconds": guard_seconds,
        "unmapped_types_observed": unmapped,
        "unmapped_types_note": (
            "Type labels with no mapping to a schema usage field. They are recorded "
            "verbatim in each run's event log and are NOT counted in any token class. "
            "A thinking/reasoning-flavoured type appearing here is a finding, not "
            "noise: it is the thinking share of the bill and must be mapped or "
            "reported explicitly before any Product-B cost is published."
        ),
        "attribution": {
            "counts_confidence": "authoritative",
            "per_run_attribution_confidence": "derived",
            "method": "time_window_serialized_runs",
        },
        "economics_note": (
            "Usage only. This collector does not recompute economics: costs stay as "
            "the runner recorded them. Re-cost with harness/runner/run.py's "
            "build_economics against the pinned pricing snapshot once usage is filled."
        ),
        "status_counts": counts,
        "runs": [out.as_dict() for out in outcomes],
    }


def _print_report(report: Dict[str, Any]) -> None:
    unmapped = report["unmapped_types_observed"]
    if unmapped:
        print("=" * 72)
        print("UNMAPPED METRIC TYPES OBSERVED — not counted in any token class:")
        for key, types in sorted(unmapped.items()):
            for t, v in sorted(types.items()):
                print(f"  {key}: type={t!r} total={v}")
        print("  -> map them or report them explicitly before publishing any cost.")
        print("=" * 72)
    print(json.dumps(report, indent=2, sort_keys=True))


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def load_plan(path: str) -> Tuple[str, List[RunPlan]]:
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    project = raw.get("project")
    if not project:
        raise CollectorError(f"{path}: no 'project'")
    runs = [RunPlan.from_dict(r) for r in (raw.get("runs") or [])]
    if not runs:
        raise CollectorError(f"{path}: no 'runs'")
    return str(project), runs


def collect_for_run(client: MonitoringClient, project: str, plan: RunPlan,
                    guard_seconds: int) -> Collection:
    start = plan.start or run_window_from_events(plan.run_dir)[0]
    end = plan.end or run_window_from_events(plan.run_dir)[1]
    window = build_window(start, end, guard_seconds)
    publishers = {plan.publisher_for(leg_id) for leg_id in plan.legs}
    series = client.list_time_series(
        project, build_filter(sorted(set(plan.legs.values())), publishers), window)
    return aggregate_series(series, window, guard_seconds)


def run_backfill(client: MonitoringClient, project: str, plans: List[RunPlan],
                 collected_at: str, guard_seconds: int = DEFAULT_GUARD_SECONDS,
                 dry_run: bool = False) -> Dict[str, Any]:
    outcomes: List[BackfillOutcome] = []
    for plan in plans:
        try:
            collection = collect_for_run(client, project, plan, guard_seconds)
            outcomes.append(backfill_run(plan, collection, collected_at, dry_run=dry_run))
        except CollectorError as exc:
            outcomes.append(BackfillOutcome(plan.run_dir, "", "error", str(exc)))
    return build_report(project, collected_at, guard_seconds, outcomes)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill provider-side Vertex token counts into run telemetry.")
    parser.add_argument("--plan", required=True,
                        help="JSON plan: {project, runs:[{run_dir, legs:{leg: model_user_id}}]}")
    parser.add_argument("--project", help="override the plan's project")
    parser.add_argument("--guard-seconds", type=int, default=DEFAULT_GUARD_SECONDS)
    parser.add_argument("--collected-at",
                        help="RFC3339 collection timestamp (default: now, UTC)")
    parser.add_argument("--report", help="write the JSON report here as well as stdout")
    parser.add_argument("--dry-run", action="store_true",
                        help="query and report, but write nothing")
    args = parser.parse_args(argv)

    try:
        project, plans = load_plan(args.plan)
    except CollectorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    project = args.project or project
    collected_at = args.collected_at or format_ts(datetime.now(timezone.utc))

    report = run_backfill(GcloudMonitoringClient(), project, plans, collected_at,
                          guard_seconds=args.guard_seconds, dry_run=args.dry_run)
    _print_report(report)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
            fh.write("\n")
    return 1 if report["status_counts"].get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
