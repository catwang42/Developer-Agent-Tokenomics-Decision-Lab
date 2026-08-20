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

Attribution has a precondition, and the collector now CHECKS it rather than
assuming it: before writing anything it runs a contamination guard (a per-run
plausibility ceiling plus a baseline probe either side of the window). If the
window cannot support a per-run number, nothing is written and the run is stamped
``contaminated_window`` with its evidence. See the guard section below.

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
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, replace
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
#: A widened attribution window makes each ``timeSeries.list`` call bigger, and the
#: endpoint occasionally stalls past the socket timeout mid-page. A read timeout
#: says nothing about the data, so retry it a bounded number of times rather than
#: letting one slow page abort a whole batch backfill.
MONITORING_ATTEMPTS = 4
MONITORING_RETRY_BACKOFF_S = (2, 8, 20)
#: 429/500/502/503/504 are transient by contract; 4xx other than 429 are not.
MONITORING_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

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
BACKFILL_EVENT_V2 = "provider_usage_backfill_v2"
COLLECTOR_ID = "vertex_token_collector"

#: Events this collector appends AFTER the fact. They carry the collection
#: timestamp, not a moment of the run, so they must never be read back as part of
#: the run's wall window — see ``run_window_from_events``.
_POST_HOC_EVENT_TYPES = (BACKFILL_EVENT, BACKFILL_EVENT_V2)


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

    def __init__(self, access_token: Optional[str] = None, timeout_s: int = 180,
                 attempts: int = MONITORING_ATTEMPTS, sleep=time.sleep):
        self._token = access_token
        self.timeout_s = timeout_s
        self.attempts = max(1, attempts)
        self._sleep = sleep

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

    def _get(self, url: str) -> Dict[str, Any]:
        """One GET, retried on transient failures only. Never partial-credits.

        A read timeout or a 503 is a statement about the transport, not about the
        meter, so retrying is safe: the call is a read and the interval is fixed.
        Anything else (401, 400, an unparseable body) fails immediately — a wrong
        answer must never look like a slow one.
        """
        last: Optional[Exception] = None
        for attempt in range(self.attempts):
            if attempt:
                self._sleep(MONITORING_RETRY_BACKOFF_S[
                    min(attempt - 1, len(MONITORING_RETRY_BACKOFF_S) - 1)])
            req = urllib.request.Request(
                url, headers={"Authorization": f"Bearer {self._access_token()}"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")[:500]
                err = CollectorError(f"monitoring API {exc.code}: {body}")
                if exc.code not in MONITORING_RETRY_STATUS:
                    raise err from exc
                last = err
            except urllib.error.URLError as exc:
                last = CollectorError(f"monitoring API unreachable: {exc}")
            except (TimeoutError, OSError) as exc:
                # urlopen surfaces a socket read timeout as a bare TimeoutError,
                # which is NOT a URLError — batch 1's v2 pass died on exactly this.
                last = CollectorError(f"monitoring API read timed out: {exc!r}")
        raise CollectorError(
            f"{last} (gave up after {self.attempts} attempts)") from last

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
            payload = self._get(url)
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
# Contamination guard (never write a number the window cannot support)
# --------------------------------------------------------------------------- #
# Time-window attribution is only sound while the subject run is the ONLY thing
# calling the model in the project. That premise broke in the screening smoke: a
# ~10-minute Product-B run's window returned 10,993,105 input tokens, three orders
# of magnitude above anything the run could have produced, because an unrelated
# interactive workload was hitting the same publisher model. The number was
# authoritative as a meter reading and worthless as a per-run measurement, and
# nothing in the collector would have stopped it being written into telemetry.
#
# Two independent checks now run BEFORE any write, because they fail on different
# shapes of contamination:
#   (a) a per-run plausibility CEILING catches a big overlapping burst;
#   (b) BASELINE traffic in the windows immediately before and after the run
#       catches a steady background stream, which no ceiling can distinguish from
#       a genuinely long run.
# Either trips and the run is stamped `contaminated_window` with its evidence and
# nothing is written. A refusal is not a failure of the collector: it is the
# collector doing the one thing that keeps `unavailable` honest (CLAUDE.md rule 3).

#: Input-side tokens one run may plausibly have consumed. 3M is deliberately loose
#: — roughly two orders of magnitude above the input side of the observed smoke
#: runs — so it fires on contamination, not on a long or repetitive agent loop.
#: Configurable per invocation (``--ceiling-input-tokens``; 0 disables).
DEFAULT_CEILING_INPUT_TOKENS = 3_000_000

#: How far either side of the attribution window to probe for background traffic.
#: The window already carries ``guard_seconds`` of slack, so these probe strictly
#: outside it. Configurable (``--baseline-seconds``; 0 disables).
DEFAULT_BASELINE_SECONDS = 300

CONTAMINATED_STATUS = "contaminated_window"

#: Metric ``type`` labels that count toward the input-side ceiling.
_INPUT_SIDE_TYPES = ("input", "cache_read_input", "cache_write_1h_input")


@dataclass
class ContaminationVerdict:
    """Whether a run's window can support a per-run attribution at all."""
    contaminated: bool = False
    reasons: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {"contaminated": self.contaminated, "reasons": list(self.reasons),
                "evidence": self.evidence}


def input_side_tokens(totals_by_type: Dict[str, int]) -> int:
    """Sum of the input-side type labels (plain, cache-read and cache-write).

    All three are counted: a contaminated window can arrive entirely as
    ``cache_read_input``, and checking only ``input`` would wave it through.
    """
    return sum(int(v) for t, v in totals_by_type.items() if t in _INPUT_SIDE_TYPES)


def check_ceiling(collection: Collection,
                  ceiling: int = DEFAULT_CEILING_INPUT_TOKENS) -> ContaminationVerdict:
    """Trip when any model's input-side total in the window exceeds ``ceiling``."""
    verdict = ContaminationVerdict()
    if ceiling <= 0:
        verdict.evidence["ceiling"] = "disabled"
        return verdict
    observed = {mid: input_side_tokens(t.totals_by_type)
                for mid, t in collection.by_model.items()}
    verdict.evidence["ceiling"] = {
        "input_side_tokens_ceiling": ceiling,
        "observed_input_side_tokens": dict(sorted(observed.items())),
    }
    for mid, total in sorted(observed.items()):
        if total > ceiling:
            verdict.contaminated = True
            verdict.reasons.append(
                f"{mid}: {total} input-side tokens in the window exceeds the "
                f"per-run plausibility ceiling of {ceiling} — the window is "
                f"carrying traffic this run cannot have produced"
            )
    return verdict


def _probe_one(client: MonitoringClient, project: str, filter_str: str, name: str,
               probe_window: Tuple[datetime, datetime],
               verdict: ContaminationVerdict) -> Dict[str, Any]:
    """Query one quiet-probe window; trip ``verdict`` if it is not quiet.

    A probe that ERRORS is treated as contaminated, not as quiet: an unverifiable
    quiet window is not a quiet window.
    """
    entry: Dict[str, Any] = {
        "start": format_ts(probe_window[0]), "end": format_ts(probe_window[1])}
    try:
        series = client.list_time_series(project, filter_str, probe_window)
        found = aggregate_series(series, probe_window, guard_seconds=0)
    except CollectorError as exc:
        entry["error"] = str(exc)
        verdict.contaminated = True
        verdict.reasons.append(
            f"{name}-run baseline probe failed ({exc}) — an unverifiable quiet "
            f"window is not a quiet window")
        return entry
    totals = {mid: dict(sorted(t.totals_by_type.items()))
              for mid, t in sorted(found.by_model.items())}
    entry["points"] = found.points_in_window
    entry["by_model"] = totals
    if found.points_in_window:
        verdict.contaminated = True
        verdict.reasons.append(
            f"{name}-run baseline window {entry['start']}..{entry['end']} is "
            f"NOT quiet: {found.points_in_window} point(s), {totals} — traffic "
            f"on the subject models outside the run means points inside the "
            f"run's window cannot be attributed to the run"
        )
    return entry


def probe_baseline(client: MonitoringClient, project: str, filter_str: str,
                   window: Tuple[datetime, datetime],
                   baseline_seconds: int = DEFAULT_BASELINE_SECONDS,
                   ) -> ContaminationVerdict:
    """Trip when the same models carry traffic just before or just after the run.

    Probes ``[lo - baseline, lo)`` and ``(hi, hi + baseline]`` — strictly outside
    the attribution window, whose guard band already absorbs alignment-period
    spill from the run's own first and last calls. Any tokens there mean something
    other than this run is calling these models right now, which is exactly the
    premise time-window attribution rests on.

    This is attribution rule **v1**. It is unaware of the other runs in the batch,
    so it cannot tell the run's own late-arriving points from a third party's and
    refuses both; ``probe_ownership`` below is the batch-aware successor.
    """
    verdict = ContaminationVerdict()
    if baseline_seconds <= 0:
        verdict.evidence["baseline"] = "disabled"
        return verdict
    lo, hi = window
    span = timedelta(seconds=baseline_seconds)
    tick = timedelta(microseconds=1)
    probes = {"pre": (lo - span, lo - tick), "post": (hi + tick, hi + span)}
    evidence: Dict[str, Any] = {"baseline_seconds": baseline_seconds, "windows": {}}
    for name, probe_window in probes.items():
        evidence["windows"][name] = _probe_one(
            client, project, filter_str, name, probe_window, verdict)
    verdict.evidence["baseline"] = evidence
    return verdict


def merge_verdicts(*verdicts: ContaminationVerdict) -> ContaminationVerdict:
    """Combine independent checks; contaminated if ANY of them tripped."""
    merged = ContaminationVerdict()
    for v in verdicts:
        merged.contaminated = merged.contaminated or v.contaminated
        merged.reasons.extend(v.reasons)
        merged.evidence.update(v.evidence)
    return merged


# --------------------------------------------------------------------------- #
# Run windows
# --------------------------------------------------------------------------- #
def run_window_from_events(run_dir: str) -> Tuple[str, str]:
    """First and last event timestamps of a run — its uninstrumented wall window.

    Events this collector appended after the fact are excluded. They carry the
    COLLECTION timestamp, so counting them stretches the window from the end of
    the run to whenever collection happened — which on a second pass over an
    already-collected batch makes every run look hours long and overlapping with
    every other. (Observed on screening batch 1: 73 of 77 runs appeared to overlap
    because their last "event" was a backfill stamped at the epilogue's clock.)
    """
    path = os.path.join(run_dir, "events.jsonl")
    if not os.path.exists(path):
        raise CollectorError(f"no events.jsonl in {run_dir} — cannot bound a window")
    stamps = [parse_ts(e["ts"]) for e in read_events(path)
              if e.get("ts") and e.get("event_type") not in _POST_HOC_EVENT_TYPES]
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


# --------------------------------------------------------------------------- #
# Serialized-run ownership — attribution rule v2
# --------------------------------------------------------------------------- #
# Rule v1 asks each run's window to be surrounded by silence. That is the right
# question to ask of a window in isolation and the wrong one to ask of a BATCH:
# the subject runs are serialized by the driver, one at a time, so the traffic
# just after a run is overwhelmingly the run's OWN meter points arriving late.
# Cloud Monitoring aligns this metric into buckets and ingests them with a delay,
# so a run that stops calling at T still deposits points after T. v1 read that
# tail as "someone else is calling the model" and refused — batch 1 lost 8 legs
# to a post-window tail whose whole content was the run's own last few calls.
#
# v2 replaces "the run must be surrounded by silence" with a statement about
# OWNERSHIP that holds by construction for a serialized batch:
#
#     run i owns the meter from its own start until the next subject run's
#     window opens; nothing else in the batch can have produced points there.
#
# The MAXIMAL window that claim allows is
#
#     [start_i - guard,  min(end_i + guard + tail_cap,  start_{i+1} - guard) )
#
# but the window actually used is narrower, and measured rather than assumed. A
# fixed tail is a guess at an ingestion delay nobody published: set it too short
# and v1's defect comes straight back (the first v2 pass over batch 1 used a flat
# 300s and still refused 37 of 43 legs — the meter was simply still delivering
# their points), set it too long and every run absorbs whatever follows it.
#
# So the tail is TERMINATED BY SILENCE (``resolve_tail``): starting at the run's
# end, each point that arrives within ``silence_seconds`` of the previous one
# extends the tail; the first gap that long closes it. The justification is that
# the run's process is dead — the container is gone — so points contiguous with
# its own traffic can only be its own calls arriving late, while traffic that
# resumes after a full silence cannot be. ``tail_cap`` remains as a backstop: a
# meter still producing points at the cap is not an ingestion tail, it is someone
# else working, and the run is refused rather than credited with it.
#
# The quiet probes survive, moved to the only region where a third party is still
# distinguishable: the no-man's-land between one run's tail and the next run's
# window. When the tail ended in silence, that whole region is probed — none of it
# is ours by construction — and any traffic in it refuses the run. The
# plausibility ceiling is untouched. So v2 stops refusing a run for its own tail
# and keeps refusing it for someone else's burst.
#
# Two ways this rule can fail to hold, both refused rather than papered over:
#   * the runs OVERLAP (start_{i+1} < end_i) — the batch was not serialized here
#     and no boundary exists to draw;
#   * the runs are closer than the guard bands (start_{i+1} - guard <= end_i +
#     guard) — the boundary exists but leaves the run no tail at all, so its late
#     points land inside its neighbour's window and the meter cannot separate the
#     two. Both runs are refused.

#: The LONGEST ingestion tail the rule will grant a run — a hard cap, not the tail
#: itself. The tail actually granted is measured per run (see ``resolve_tail``):
#: it ends at the first silence, and a run whose meter is still producing points
#: at this cap is refused rather than credited with them. Configurable
#: (``--tail-seconds``; 0 reduces v2's window to v1's, keeping only the
#: batch-aware probe placement).
#:
#: 900s comes from the observed behaviour of THIS metric, not from taste. The
#: first v2 pass over batch 1 granted a flat 300s and still refused 37 of 43 legs;
#: querying the meter around one of them showed the run's own points arriving in a
#: contiguous chain until 482s after its last event, then nothing for 20 minutes.
#: A flat 300s tail is therefore shorter than this metric's ingestion delay, and a
#: cap has to leave room for it. It stays a cap because a tail that never stops is
#: the signature of a third party, not of ingestion lag.
DEFAULT_TAIL_SECONDS = 900

#: The silence that ENDS a tail. Points keep extending a run's tail while they
#: arrive closer together than this; the first gap this long closes it. A run's
#: process is dead once the run ends, so contiguous points after it are its own
#: late-ingested calls — but traffic that resumes after a full silence cannot be,
#: and is treated as a third party.
DEFAULT_TAIL_SILENCE_SECONDS = 300

ATTRIBUTION_METHOD_V1 = "time_window_serialized_runs"
ATTRIBUTION_METHOD_V2 = "serialized_run_ownership_with_ingestion_tail"

_TICK = timedelta(microseconds=1)


@dataclass
class Ownership:
    """The slice of the meter one run in a serialized batch owns."""
    run_dir: str
    raw_start: datetime
    raw_end: datetime
    lo: datetime
    hi: datetime
    guard_seconds: int
    tail_seconds: int
    #: "ingestion_tail" (the full tail cap fitted) or "next_subject_run" (clipped).
    #: Describes the MAXIMAL window; ``tail_ended_by`` describes the one used.
    bounded_by: str
    #: The neighbouring boundaries, or None at the ends of the batch.
    prev_hi: Optional[datetime] = None
    next_lo: Optional[datetime] = None
    #: Set when the ownership premise does not hold for this run; the run is
    #: refused and this is the reason.
    inseparable: Optional[str] = None
    #: How the tail actually ended, once the meter had been looked at:
    #: "unresolved" (no points examined yet), "no_points" (nothing after the run),
    #: "silence", "next_subject_run", or "tail_cap" (refused).
    tail_ended_by: str = "unresolved"
    silence_seconds: int = DEFAULT_TAIL_SILENCE_SECONDS
    #: The last point attributed to this run, if any — the tail's evidence.
    last_point: Optional[datetime] = None

    def window(self) -> Tuple[datetime, datetime]:
        return self.lo, self.hi

    def tail_granted_seconds(self) -> float:
        """How much ingestion tail this run actually got, after clipping.

        Less than ``tail_seconds`` means a neighbour took the rest: any of this
        run's points ingested later than this land in the neighbour's window. The
        run is still attributable — the guard band covers the usual delay — but a
        clipped tail is the residual risk in this rule and is recorded so an
        analysis can see it rather than having to reconstruct it.
        """
        return max(0.0, (self.hi - (self.raw_end + timedelta(
            seconds=self.guard_seconds))).total_seconds())

    def pre_probe(self, baseline_seconds: int) -> Optional[Tuple[datetime, datetime]]:
        """Third-party territory before this run, or None if the previous
        subject run owns right up to our window."""
        if baseline_seconds <= 0:
            return None
        start = self.lo - timedelta(seconds=baseline_seconds)
        if self.prev_hi is not None:
            start = max(start, self.prev_hi + _TICK)
        end = self.lo - _TICK
        return (start, end) if start <= end else None

    def post_probe(self, baseline_seconds: int) -> Optional[Tuple[datetime, datetime]]:
        """Third-party territory after this run, or None if the next subject run
        owns from our boundary onward (the case v1 mistook for contamination).

        Once the tail has ended in silence, everything from there to the next run
        is territory no subject run claims, so the whole of it is probed rather
        than a fixed slice: traffic anywhere in it is somebody else on the subject
        models near this batch, which is exactly what would also make the numbers
        inside our window unsafe. Before the tail is resolved — or when it was cut
        short by a neighbour — the probe stays the fixed baseline slice, clipped.
        """
        if baseline_seconds <= 0:
            return None
        start = self.hi + _TICK
        end = self.hi + timedelta(seconds=baseline_seconds)
        if self.tail_ended_by in ("silence", "no_points") and self.next_lo is not None:
            end = max(end, self.next_lo - _TICK)
        if self.next_lo is not None:
            end = min(end, self.next_lo - _TICK)
        return (start, end) if start <= end else None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": ATTRIBUTION_METHOD_V2,
            "statement": ("a serialized subject run owns the provider meter from "
                          "its own start until the next subject run's window "
                          "opens; its own ingestion tail is its own"),
            "run_window": {"start": format_ts(self.raw_start),
                           "end": format_ts(self.raw_end)},
            "attribution_window": {"start": format_ts(self.lo),
                                   "end": format_ts(self.hi)},
            "guard_seconds": self.guard_seconds,
            "tail_cap_seconds": self.tail_seconds,
            "tail_seconds": self.tail_seconds,
            "tail_silence_seconds": self.silence_seconds,
            "tail_granted_seconds": self.tail_granted_seconds(),
            "tail_ended_by": self.tail_ended_by,
            "last_point_attributed": (format_ts(self.last_point)
                                      if self.last_point else None),
            "bounded_by": self.bounded_by,
            "prev_run_owns_until": format_ts(self.prev_hi) if self.prev_hi else None,
            "next_run_window_opens": format_ts(self.next_lo) if self.next_lo else None,
        }


def plan_ownership(plans: List[RunPlan], guard_seconds: int = DEFAULT_GUARD_SECONDS,
                   tail_seconds: int = DEFAULT_TAIL_SECONDS) -> Dict[str, Ownership]:
    """Partition the batch's timeline into one ownership window per run.

    ``plans`` must be the WHOLE serialized batch, not the subset being written:
    a run's boundary is its neighbour's start, so collecting a few runs against a
    plan that omits the runs around them would hand each one its neighbour's
    traffic. (Runs already backfilled are skipped downstream by the idempotence
    guard, so passing the full batch every time is both safe and correct.)
    """
    if guard_seconds < 0 or tail_seconds < 0:
        raise CollectorError("guard_seconds and tail_seconds must be >= 0")
    guard = timedelta(seconds=guard_seconds)
    tail = timedelta(seconds=tail_seconds)

    bounds: List[Tuple[datetime, datetime, RunPlan]] = []
    for plan in plans:
        start = plan.start or run_window_from_events(plan.run_dir)[0]
        end = plan.end or run_window_from_events(plan.run_dir)[1]
        lo, hi = parse_ts(start), parse_ts(end)
        if hi < lo:
            raise CollectorError(f"{plan.run_dir}: run ends before it starts")
        bounds.append((lo, hi, plan))
    bounds.sort(key=lambda b: (b[0], b[1], b[2].run_dir))

    owned: Dict[str, Ownership] = {}
    ordered: List[Ownership] = []
    for index, (raw_start, raw_end, plan) in enumerate(bounds):
        next_raw_start = bounds[index + 1][0] if index + 1 < len(bounds) else None
        next_lo = next_raw_start - guard if next_raw_start is not None else None
        lo = raw_start - guard
        desired_hi = raw_end + guard + tail
        if next_lo is not None and next_lo <= desired_hi:
            hi, bounded_by = next_lo - _TICK, "next_subject_run"
        else:
            hi, bounded_by = desired_hi, "ingestion_tail"

        inseparable: Optional[str] = None
        if next_raw_start is not None and next_raw_start < raw_end:
            inseparable = (
                f"the next subject run starts at {format_ts(next_raw_start)}, before "
                f"this one ends at {format_ts(raw_end)} — the batch was not serialized "
                f"here, so there is no boundary that separates the two runs' tokens")
        elif next_lo is not None and next_lo <= raw_end + guard:
            gap = (next_raw_start - raw_end).total_seconds()  # type: ignore[operator]
            inseparable = (
                f"the next subject run starts {gap:.0f}s after this one ends, inside "
                f"the {guard_seconds}s guard band — this run's own ingestion tail "
                f"lands in its neighbour's window and the meter cannot say which run "
                f"produced it")

        entry = Ownership(
            run_dir=plan.run_dir, raw_start=raw_start, raw_end=raw_end, lo=lo, hi=hi,
            guard_seconds=guard_seconds, tail_seconds=tail_seconds,
            bounded_by=bounded_by, next_lo=next_lo, inseparable=inseparable,
        )
        if ordered:
            entry.prev_hi = ordered[-1].hi
        ordered.append(entry)
        owned[plan.run_dir] = entry

    # Inseparability is symmetric but NOT transitive, and the distinction matters:
    # run i's flag says "my tail lands in i+1's window", which contaminates i+1's
    # LOW side only. Whether i+1's own tail is separable from i+2 is a separate
    # question about a different boundary. Propagating from the flags as they are
    # being written makes one 4s gap poison every run after it to the end of the
    # batch — that is how the first v2 pass refused 14 runs off a single tight gap.
    # So propagate exactly one hop, from a snapshot of the runs' OWN flags.
    own_flags = [entry.inseparable for entry in ordered]
    for index, flag in enumerate(own_flags):
        if flag and index + 1 < len(ordered) and not own_flags[index + 1]:
            ordered[index + 1].inseparable = (
                f"the preceding subject run ({os.path.basename(ordered[index].run_dir)}) "
                f"cannot be separated from this one: {flag}")
    return owned


def series_point_times(series: List[Dict[str, Any]]) -> List[datetime]:
    """Every point's ``interval.endTime`` across a series list, sorted.

    Values are deliberately ignored: where the tail ends is a question about
    WHEN the meter was still delivering, not how much.
    """
    times: List[datetime] = []
    for one in series:
        for point in one.get("points") or []:
            end = (point.get("interval") or {}).get("endTime")
            if not end:
                raise CollectorError("point has no interval.endTime")
            times.append(parse_ts(end))
    return sorted(times)


def resolve_tail(entry: Ownership, point_times: List[datetime],
                 silence_seconds: int = DEFAULT_TAIL_SILENCE_SECONDS) -> Ownership:
    """Narrow a maximal ownership window to the tail the meter actually shows.

    Walks forward from the run's end. Each point closer than ``silence_seconds``
    to the previous one extends the tail; the first gap that long ends it. The
    guard band is granted regardless — it is there for clock skew, not ingestion.

    Four ways it can end, all recorded on the returned window:
      * ``no_points`` — nothing after the run at all; the window is v1's.
      * ``silence`` — the ordinary case. Everything after is third-party territory
        and gets probed as such.
      * ``next_subject_run`` — the meter was still delivering when the neighbour's
        window opened. Attributable, but the run's later points are in its
        neighbour's window; ``tail_granted_seconds`` is the shortfall.
      * ``tail_cap`` — still delivering at the cap. A tail that never stops is not
        ingestion lag, so the run is REFUSED rather than credited with the tokens.

    Pure: takes the times, returns a new window. The caller does the querying.
    """
    if silence_seconds < 0:
        raise CollectorError("silence_seconds must be >= 0")
    guard = timedelta(seconds=entry.guard_seconds)
    silence = timedelta(seconds=silence_seconds)
    floor = entry.raw_end + guard
    cap = entry.raw_end + guard + timedelta(seconds=entry.tail_seconds)

    cursor = entry.raw_end
    ran_on = False          # points kept arriving right up to the boundary
    saw_any = False
    for when in point_times:
        if when <= entry.raw_end:
            continue
        if when - cursor >= silence:
            break
        if when > entry.hi:
            ran_on = True
            break
        cursor, saw_any = when, True

    if not saw_any and not ran_on:
        ended_by = "no_points"
    elif ran_on:
        ended_by = ("next_subject_run" if entry.bounded_by == "next_subject_run"
                    else "tail_cap")
    elif (entry.bounded_by == "next_subject_run"
          and cursor + silence > entry.hi):
        # The points stopped, but the neighbour's window opens before a full
        # silence could have been observed — so silence was not established, it
        # merely was not contradicted. Recorded as the clipped tail it is rather
        # than as evidence nobody looked for.
        ended_by = "next_subject_run"
    else:
        ended_by = "silence"

    resolved_hi = min(entry.hi, max(floor, cursor + guard))
    inseparable = entry.inseparable
    if ended_by == "tail_cap" and inseparable is None:
        inseparable = (
            f"the meter was still delivering points on the subject models "
            f"{(cap - entry.raw_end).total_seconds():.0f}s after this run ended, "
            f"with no {silence_seconds}s silence anywhere in between — an ingestion "
            f"tail decays, so a tail that reaches the cap is somebody else working "
            f"and these tokens cannot be called this run's")

    return replace(entry, hi=resolved_hi, tail_ended_by=ended_by,
                   silence_seconds=silence_seconds, inseparable=inseparable,
                   last_point=cursor if saw_any else None)


def probe_ownership(client: MonitoringClient, project: str, filter_str: str,
                    ownership: Ownership,
                    baseline_seconds: int = DEFAULT_BASELINE_SECONDS,
                    ) -> ContaminationVerdict:
    """The v2 quiet probe: look for a THIRD PARTY, not for silence.

    Probes only the no-man's-land either side of the ownership window — the region
    no subject run claims. A probe the neighbours squeeze to nothing is reported as
    ``not_applicable`` (the neighbour owns it), which is precisely the difference
    from v1: the run's own tail is no longer evidence against it.
    """
    verdict = ContaminationVerdict()
    if ownership.inseparable:
        verdict.contaminated = True
        verdict.reasons.append(ownership.inseparable)
    if baseline_seconds <= 0:
        verdict.evidence["baseline"] = "disabled"
        return verdict
    evidence: Dict[str, Any] = {
        "baseline_seconds": baseline_seconds,
        "probes": ("third-party territory only: the region between this run's "
                   "ownership window and its neighbours'"),
        "windows": {},
    }
    for name, probe_window in (("pre", ownership.pre_probe(baseline_seconds)),
                               ("post", ownership.post_probe(baseline_seconds))):
        if probe_window is None:
            evidence["windows"][name] = {
                "status": "not_applicable",
                "why": ("an adjacent subject run owns this side up to the boundary; "
                        "there is no third-party region to probe"),
            }
            continue
        evidence["windows"][name] = _probe_one(
            client, project, filter_str, name, probe_window, verdict)
    verdict.evidence["baseline"] = evidence
    return verdict


def already_backfilled(events: List[Dict[str, Any]]) -> List[str]:
    """Leg ids that already carry a provider backfill (idempotence guard).

    Both rule versions count: a leg filled under v1 must not be filled again
    under v2, or its tokens would be counted twice.
    """
    return sorted({str(e.get("leg", "main")) for e in events
                   if e.get("event_type") in (BACKFILL_EVENT, BACKFILL_EVENT_V2)})


def build_backfill_event(leg_id: str, model_user_id: str, collection: Collection,
                         collected_at: str,
                         attribution_method: str = ATTRIBUTION_METHOD_V1,
                         attribution_rule: Optional[Dict[str, Any]] = None,
                         ) -> Optional[Dict[str, Any]]:
    """The event to append for one leg, or None when the window held no points.

    ``attribution_rule`` is the full statement of the rule the window came from
    (``Ownership.as_dict()`` under v2). It is recorded on the event, not just in
    the batch report, so a run's own log says which rule attributed its tokens.
    """
    totals = collection.by_model.get(model_user_id)
    if totals is None or not totals.totals_by_type:
        return None
    mapped, unmapped = usage_fields(totals.totals_by_type)
    reason = (f"provider-side {METRIC_TYPE}; counts authoritative, attribution "
              f"derived from the run's time window (serialized runs, "
              f"{attribution_method})")
    event: Dict[str, Any] = {
        "leg": leg_id,
        "collector": COLLECTOR_ID,
        "metric_type": METRIC_TYPE,
        "monitored_resource": MONITORED_RESOURCE,
        "model_user_id": model_user_id,
        "counts_confidence": "authoritative",
        "attribution_confidence": "derived",
        "attribution_method": attribution_method,
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
    if attribution_rule is not None:
        event["attribution_rule"] = attribution_rule
    event["ts"] = collected_at
    return event


@dataclass
class BackfillOutcome:
    run_dir: str
    run_id: str
    #: backfilled | skipped | no_data | dry_run | contaminated_window | error
    status: str
    detail: str = ""
    legs_filled: Dict[str, Dict[str, int]] = field(default_factory=dict)
    unmapped_types: Dict[str, Dict[str, int]] = field(default_factory=dict)
    new_legs: List[str] = field(default_factory=list)
    window: Optional[Dict[str, Any]] = None
    validated: Optional[bool] = None
    validation_reasons: List[str] = field(default_factory=list)
    #: The contamination guard's verdict and its evidence. Present on every run the
    #: guard examined, so a clean run records WHY it was considered clean.
    contamination: Optional[Dict[str, Any]] = None
    #: A refusal marker from an earlier pass under the SAME rule that this write
    #: made false, and which was therefore removed. Named so the report says so.
    superseded_marker: Optional[str] = None

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


#: Refusal markers are named per attribution rule so a later pass never
#: overwrites an earlier pass's evidence: the two rules can refuse for different
#: reasons, and both reasons are worth keeping.
REFUSAL_MARKERS = {"v1": "PROVIDER-BACKFILL-REFUSED.json",
                   "v2": "PROVIDER-BACKFILL-REFUSED-v2.json"}


def write_refusal_marker(run_dir: str, run_id: str, collection: Collection,
                         verdict: ContaminationVerdict, collected_at: str,
                         filename: str = REFUSAL_MARKERS["v1"],
                         attribution_rule: Optional[Dict[str, Any]] = None) -> str:
    """Record a refusal next to the run — evidence only, no measurement.

    The run's telemetry is left untouched (its usage stays *unavailable*, which is
    the truth), but a refusal that exists only in a batch report is a refusal
    nobody reading the run will ever see. This file carries the window, the guard's
    reasons and the raw totals it refused to attribute, and it is deliberately NOT
    a telemetry artifact: nothing derives from it and no number in it is a
    measurement of this run.
    """
    path = os.path.join(run_dir, filename)
    payload: Dict[str, Any] = {
        "refusal": CONTAMINATED_STATUS,
        "collector": COLLECTOR_ID,
        "metric_type": METRIC_TYPE,
        "run_id": run_id,
        "collected_at": collected_at,
        "attribution_rule": attribution_rule,
        "note": ("The provider meter for this window could not be attributed to "
                 "this run, so NOTHING was written to events.jsonl or summary.json "
                 "and the run's Product-B usage remains 'unavailable' (not zero). "
                 "The totals below are what the window contained; they are NOT this "
                 "run's usage."),
        "window_totals_refused": collection.as_dict(),
        "guard": verdict.as_dict(),
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)
    return path


def backfill_run(plan: RunPlan, collection: Collection, collected_at: str,
                 dry_run: bool = False,
                 contamination: Optional[ContaminationVerdict] = None,
                 event_type: str = BACKFILL_EVENT,
                 attribution_method: str = ATTRIBUTION_METHOD_V1,
                 attribution_rule: Optional[Dict[str, Any]] = None,
                 ) -> BackfillOutcome:
    """Append provider-side usage to one run and re-derive its summary.

    ``contamination`` is the guard's verdict for this run's window. When it says
    the window is contaminated NOTHING is written, whatever the meter returned:
    the counts are real, but they are not this run's, and a real number attributed
    to the wrong run is a fabricated measurement (CLAUDE.md rule 1).

    ``event_type``/``attribution_method``/``attribution_rule`` carry the rule the
    window was drawn under. Appending under a distinct event type is what keeps a
    v2 backfill append-only with respect to a v1 one: the two never overwrite each
    other, and the idempotence guard refuses to write a second one either way.
    """
    events_path = os.path.join(plan.run_dir, "events.jsonl")
    summary_path = os.path.join(plan.run_dir, "summary.json")
    for required in (events_path, summary_path):
        if not os.path.exists(required):
            return BackfillOutcome(plan.run_dir, "", "error", f"missing {required}")
    events = list(read_events(events_path))
    with open(summary_path, encoding="utf-8") as fh:
        run_id = json.load(fh).get("run_id", "")

    # Idempotence is checked BEFORE contamination, not after: a leg that already
    # carries a backfill is not going to be written under any verdict, so letting
    # the guard speak first would stamp a refusal marker on a run whose earlier
    # attribution stands — and would overwrite an existing marker with a verdict
    # about a rule this pass never applied.
    done = already_backfilled(events)
    if done:
        return BackfillOutcome(plan.run_dir, run_id, "skipped",
                               f"already backfilled for legs {done} — re-running would "
                               f"double-count; delete the events to redo it")

    if contamination is not None and contamination.contaminated:
        outcome = BackfillOutcome(
            plan.run_dir, run_id, CONTAMINATED_STATUS,
            detail="; ".join(contamination.reasons),
            window={"start": collection.window_start, "end": collection.window_end,
                    "guard_seconds": collection.guard_seconds},
            contamination=contamination.as_dict(),
        )
        if not dry_run:
            write_refusal_marker(
                plan.run_dir, run_id, collection, contamination, collected_at,
                filename=REFUSAL_MARKERS["v2" if attribution_rule else "v1"],
                attribution_rule=attribution_rule)
        return outcome

    known_legs = {str(e.get("leg", "main")) for e in events
                  if e.get("event_type") == "model_call_completed"} or {"main"}
    outcome = BackfillOutcome(plan.run_dir, run_id, "no_data",
                              window={"start": collection.window_start,
                                      "end": collection.window_end,
                                      "guard_seconds": collection.guard_seconds},
                              contamination=(contamination.as_dict()
                                             if contamination is not None else None))
    new_events: List[Dict[str, Any]] = []
    for leg_id, model_user_id in sorted(_leg_model_map(plan).items()):
        event = build_backfill_event(leg_id, model_user_id, collection, collected_at,
                                     attribution_method=attribution_method,
                                     attribution_rule=attribution_rule)
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
        log.append(event_type, event["ts"], **payload)
    _rewrite_summary(plan.run_dir, list(read_events(events_path)))

    # A marker saying "nothing was written under this rule" must not survive next
    # to an event written under that same rule — that self-contradiction is the
    # defect the v1 pass left in four batch-1 runs. The refusal itself is not lost:
    # every pass's verdict is in its own collector report.
    stale = os.path.join(plan.run_dir,
                         REFUSAL_MARKERS["v2" if attribution_rule else "v1"])
    if os.path.exists(stale):
        os.remove(stale)
        outcome.superseded_marker = os.path.basename(stale)

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
                 outcomes: List[BackfillOutcome],
                 ceiling: int = DEFAULT_CEILING_INPUT_TOKENS,
                 baseline_seconds: int = DEFAULT_BASELINE_SECONDS,
                 attribution_rule: str = "v1",
                 tail_seconds: int = DEFAULT_TAIL_SECONDS,
                 silence_seconds: int = DEFAULT_TAIL_SILENCE_SECONDS,
                 ) -> Dict[str, Any]:
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
            "rule": attribution_rule,
            "method": (ATTRIBUTION_METHOD_V2 if attribution_rule == "v2"
                       else ATTRIBUTION_METHOD_V1),
            "event_type": (BACKFILL_EVENT_V2 if attribution_rule == "v2"
                           else BACKFILL_EVENT),
            "tail_cap_seconds": tail_seconds if attribution_rule == "v2" else None,
            "tail_seconds": tail_seconds if attribution_rule == "v2" else None,
            "tail_silence_seconds": (silence_seconds if attribution_rule == "v2"
                                     else None),
            "note": (("a serialized subject run owns the meter from its own start "
                      "until the next subject run's window opens, so its own "
                      "ingestion tail is attributed to it; the tail is measured, "
                      "ending at the first silence and capped, and the quiet probe "
                      "looks only at the region no subject run owns")
                     if attribution_rule == "v2" else
                     ("a run's window must be surrounded by silence on the subject "
                      "models")),
        },
        "contamination_guard": {
            "input_side_ceiling_tokens": ceiling,
            "baseline_probe_seconds": baseline_seconds,
            "on_trip": ("nothing is written; the run is stamped "
                        f"{CONTAMINATED_STATUS} and its usage stays unavailable"),
            "runs_refused": sorted(out.run_dir for out in outcomes
                                   if out.status == CONTAMINATED_STATUS),
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
    refused = [r for r in report["runs"] if r.get("status") == CONTAMINATED_STATUS]
    if refused:
        print("=" * 72)
        print(f"CONTAMINATED WINDOW — {len(refused)} run(s) NOT backfilled. The meter "
              f"readings are real; they are not these runs'.")
        for run in refused:
            print(f"  {run.get('run_id') or run['run_dir']}")
            for reason in (run.get("contamination") or {}).get("reasons", []):
                print(f"    - {reason}")
        print("  -> nothing was written; their Product-B usage stays 'unavailable', "
              "not zero.")
        print("  -> re-collect only if the window can be shown to have been quiet; "
              "widening a filter to make a number appear is fabrication.")
        print("=" * 72)
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


def plan_filter(plan: RunPlan) -> str:
    """The Monitoring filter for one run's declared legs."""
    publishers = {plan.publisher_for(leg_id) for leg_id in plan.legs}
    return build_filter(sorted(set(plan.legs.values())), publishers)


def plan_query(plan: RunPlan, guard_seconds: int
               ) -> Tuple[Tuple[datetime, datetime], str]:
    """The ``(window, filter)`` one run is collected with. Pure but for the events."""
    start = plan.start or run_window_from_events(plan.run_dir)[0]
    end = plan.end or run_window_from_events(plan.run_dir)[1]
    return build_window(start, end, guard_seconds), plan_filter(plan)


def collect_for_run(client: MonitoringClient, project: str, plan: RunPlan,
                    guard_seconds: int,
                    window: Optional[Tuple[datetime, datetime]] = None) -> Collection:
    """Aggregate one run's window. ``window`` overrides the v1 derivation."""
    if window is None:
        window, filter_str = plan_query(plan, guard_seconds)
    else:
        filter_str = plan_filter(plan)
    series = client.list_time_series(project, filter_str, window)
    return aggregate_series(series, window, guard_seconds)


def collect_owned(client: MonitoringClient, project: str, plan: RunPlan,
                  ownership: Ownership, guard_seconds: int,
                  silence_seconds: int = DEFAULT_TAIL_SILENCE_SECONDS,
                  ) -> Tuple[Collection, Ownership]:
    """Resolve the run's tail against the meter, then aggregate inside it.

    One query, over the MAXIMAL window the ownership claim allows plus enough
    slack to see the silence that ends the tail; the resolved window is then
    applied to the same points. Querying the maximum and narrowing afterwards is
    what makes the tail a measurement instead of a setting.
    """
    filter_str = plan_filter(plan)
    horizon = ownership.hi + timedelta(seconds=max(silence_seconds, 0))
    if ownership.next_lo is not None:
        horizon = min(horizon, ownership.next_lo - _TICK)
    horizon = max(horizon, ownership.hi)
    series = client.list_time_series(project, filter_str, (ownership.lo, horizon))
    resolved = resolve_tail(ownership, series_point_times(series), silence_seconds)
    return aggregate_series(series, resolved.window(), guard_seconds), resolved


def guard_run(client: MonitoringClient, project: str, plan: RunPlan,
              collection: Collection, guard_seconds: int,
              ceiling: int = DEFAULT_CEILING_INPUT_TOKENS,
              baseline_seconds: int = DEFAULT_BASELINE_SECONDS,
              ownership: Optional[Ownership] = None,
              ) -> ContaminationVerdict:
    """Run both contamination checks over one run's window.

    The ceiling is the same under either rule. The quiet probe is the part that
    differs: v1 demands silence around the window, v2 probes only the region no
    subject run owns.
    """
    if ownership is not None:
        return merge_verdicts(
            check_ceiling(collection, ceiling),
            probe_ownership(client, project, plan_filter(plan), ownership,
                            baseline_seconds),
        )
    window, filter_str = plan_query(plan, guard_seconds)
    return merge_verdicts(
        check_ceiling(collection, ceiling),
        probe_baseline(client, project, filter_str, window, baseline_seconds),
    )


def run_backfill(client: MonitoringClient, project: str, plans: List[RunPlan],
                 collected_at: str, guard_seconds: int = DEFAULT_GUARD_SECONDS,
                 dry_run: bool = False,
                 ceiling: int = DEFAULT_CEILING_INPUT_TOKENS,
                 baseline_seconds: int = DEFAULT_BASELINE_SECONDS,
                 attribution_rule: str = "v1",
                 tail_seconds: int = DEFAULT_TAIL_SECONDS,
                 silence_seconds: int = DEFAULT_TAIL_SILENCE_SECONDS,
                 ) -> Dict[str, Any]:
    """Collect and backfill a whole batch under one attribution rule.

    Under ``v2`` the batch is treated as the serialized sequence it is: boundaries
    are computed across ALL of ``plans`` first, then each run is collected inside
    the slice it owns, with its ingestion tail resolved against the meter.
    """
    owned: Dict[str, Ownership] = {}
    if attribution_rule == "v2":
        owned = plan_ownership(plans, guard_seconds, tail_seconds)
    elif attribution_rule != "v1":
        raise CollectorError(f"unknown attribution rule {attribution_rule!r}")

    outcomes: List[BackfillOutcome] = []
    for plan in plans:
        try:
            ownership = owned.get(plan.run_dir)
            if ownership is not None:
                collection, ownership = collect_owned(
                    client, project, plan, ownership, guard_seconds, silence_seconds)
            else:
                collection = collect_for_run(client, project, plan, guard_seconds)
            verdict = guard_run(client, project, plan, collection, guard_seconds,
                                ceiling=ceiling, baseline_seconds=baseline_seconds,
                                ownership=ownership)
            outcomes.append(backfill_run(
                plan, collection, collected_at, dry_run=dry_run,
                contamination=verdict,
                event_type=BACKFILL_EVENT_V2 if ownership else BACKFILL_EVENT,
                attribution_method=(ATTRIBUTION_METHOD_V2 if ownership
                                    else ATTRIBUTION_METHOD_V1),
                attribution_rule=ownership.as_dict() if ownership else None))
        except CollectorError as exc:
            outcomes.append(BackfillOutcome(plan.run_dir, "", "error", str(exc)))
    return build_report(project, collected_at, guard_seconds, outcomes,
                        ceiling=ceiling, baseline_seconds=baseline_seconds,
                        attribution_rule=attribution_rule, tail_seconds=tail_seconds,
                        silence_seconds=silence_seconds)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill provider-side Vertex token counts into run telemetry.")
    parser.add_argument("--plan", required=True,
                        help="JSON plan: {project, runs:[{run_dir, legs:{leg: model_user_id}}]}")
    parser.add_argument("--project", help="override the plan's project")
    parser.add_argument("--guard-seconds", type=int, default=DEFAULT_GUARD_SECONDS)
    parser.add_argument("--ceiling-input-tokens", type=int,
                        default=DEFAULT_CEILING_INPUT_TOKENS,
                        help="per-run plausibility ceiling on input-side tokens "
                             "(input + cache read + cache write). A window over it "
                             "is refused, not written. 0 disables the check.")
    parser.add_argument("--baseline-seconds", type=int,
                        default=DEFAULT_BASELINE_SECONDS,
                        help="probe this many seconds before and after each run's "
                             "window for traffic on the same models; any traffic "
                             "there refuses the run. 0 disables the check.")
    parser.add_argument("--attribution-rule", choices=("v1", "v2"), default="v1",
                        help="v1: each run's window must be surrounded by silence. "
                             "v2: serialized-run ownership — a run owns the meter "
                             "until the next subject run's window opens, so its own "
                             "ingestion tail counts as its own and only the region "
                             "no run owns is probed for a third party. v2 needs the "
                             "WHOLE serialized batch in the plan.")
    parser.add_argument("--tail-seconds", type=int, default=DEFAULT_TAIL_SECONDS,
                        help="v2 only: the LONGEST ingestion tail a run may be "
                             "granted. The tail is measured, not assumed — it ends "
                             "at the first silence — and a run still producing "
                             "points at this cap is refused, not credited. Never "
                             "extends past the next subject run's window.")
    parser.add_argument("--tail-silence-seconds", type=int,
                        default=DEFAULT_TAIL_SILENCE_SECONDS,
                        help="v2 only: the gap that ends a run's ingestion tail. "
                             "Points arriving closer together than this extend it.")
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

    try:
        report = run_backfill(GcloudMonitoringClient(), project, plans, collected_at,
                              guard_seconds=args.guard_seconds, dry_run=args.dry_run,
                              ceiling=args.ceiling_input_tokens,
                              baseline_seconds=args.baseline_seconds,
                              attribution_rule=args.attribution_rule,
                              tail_seconds=args.tail_seconds,
                              silence_seconds=args.tail_silence_seconds)
    except CollectorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _print_report(report)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
            fh.write("\n")
    # 1 = something errored; 4 = nothing errored but the guard refused at least one
    # run. Distinct codes because they need different responses: an error is a bug
    # or an outage to fix, a refusal is a window to re-establish.
    if report["status_counts"].get("error"):
        return 1
    return 4 if report["status_counts"].get(CONTAMINATED_STATUS) else 0


if __name__ == "__main__":
    raise SystemExit(main())
