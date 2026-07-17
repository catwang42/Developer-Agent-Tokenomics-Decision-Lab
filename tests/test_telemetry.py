"""Unit tests for harness/telemetry/telemetry.py.

All fixtures are SYNTHETIC (see tests/fixtures/). No real telemetry, no network,
no model calls. Uses the stdlib unittest runner so CI needs no extra deps.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.telemetry import telemetry  # noqa: E402
from harness.telemetry.telemetry import (  # noqa: E402
    EventLog,
    derive_summary,
    read_events,
    tiered,
    unavailable,
    validate,
    validate_summary,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return json.load(fh)


class TieredHelperTests(unittest.TestCase):
    def test_unavailable_is_never_zero_filled(self):
        # A zero-filled "unavailable" is exactly the forbidden state (rule 3).
        with self.assertRaises(ValueError):
            tiered(0, "unavailable")
        with self.assertRaises(ValueError):
            tiered(5, "unavailable")

    def test_available_field_needs_value(self):
        with self.assertRaises(ValueError):
            tiered(None, "authoritative")

    def test_unknown_tier_rejected(self):
        with self.assertRaises(ValueError):
            tiered(1, "made_up_tier")

    def test_unavailable_helper(self):
        u = unavailable("no telemetry exposed")
        self.assertIsNone(u["value"])
        self.assertEqual(u["confidence"], "unavailable")
        self.assertEqual(u["reason"], "no telemetry exposed")


class ValidatorTests(unittest.TestCase):
    def test_valid_summary_passes(self):
        ok, reasons = validate_summary(_load("summary-valid-SYNTHETIC.json"))
        self.assertTrue(ok, msg=f"expected valid, got reasons: {reasons}")
        # Standalone validation is labelled structural-only / not audit-grade.
        self.assertTrue(any(r.startswith("note:") and "not audit-grade" in r for r in reasons))
        # ...and carries no failure reasons.
        self.assertEqual([r for r in reasons if not r.startswith("note:")], [])

    def test_dualbill_summary_valid(self):
        summary = _load("summary-dualbill-SYNTHETIC.json")
        ok, reasons = validate_summary(summary)
        self.assertTrue(ok, msg=f"reasons: {reasons}")
        self.assertEqual(len(summary["legs"]), 2)

    def test_zerofilled_and_unlabeled_rejected(self):
        ok, reasons = validate_summary(_load("summary-zerofill-bad-SYNTHETIC.json"))
        self.assertFalse(ok)
        blob = " | ".join(reasons)
        # zero-filled unavailable field (output_tokens value 0 + unavailable) — semantic layer
        self.assertIn("zero-filled", blob)
        # labelled-but-null (human_effort.active_minutes derived + null) — semantic layer
        self.assertIn("value is null", blob)
        # unlabeled field (input_tokens has no confidence) — structural (jsonschema) layer
        self.assertTrue(
            any("input_tokens" in r and "confidence" in r and "required" in r for r in reasons),
            msg=f"expected unlabeled-field error; got {reasons}",
        )
        # invalid tier (cache_read_tokens confidence 'bogus_tier') — structural layer
        self.assertTrue(
            any("is not one of" in r for r in reasons),
            msg=f"expected invalid-tier error; got {reasons}",
        )

    def test_missing_cost_basis_rejected(self):
        summary = _load("summary-valid-SYNTHETIC.json")
        del summary["economics"]["cost_basis"]
        ok, reasons = validate_summary(summary)
        self.assertFalse(ok)
        self.assertTrue(any("cost_basis" in r for r in reasons))

    def test_bad_configuration_id_rejected(self):
        summary = _load("summary-valid-SYNTHETIC.json")
        summary["configuration_id"] = "C9"
        ok, reasons = validate_summary(summary)
        self.assertFalse(ok)
        self.assertTrue(any("configuration_id" in r for r in reasons))


class DeriveSummaryTests(unittest.TestCase):
    def setUp(self):
        self.events = list(read_events(os.path.join(FIXTURES, "events-SYNTHETIC.jsonl")))

    def _derive(self):
        return derive_summary(
            self.events,
            run_id="SYNTHETIC-derived-0001",
            task_id="SYNTHETIC-pilot-task",
            task_suite_version="SYNTHETIC-v0",
            configuration_id="C1",
            manifest_ref="SYNTHETIC-manifest@0",
            identity={"provider": tiered("provider_a", "authoritative")},
            economics={"cost_basis": "marginal_api_cost"},
        )

    def test_usage_summed_across_events(self):
        s = self._derive()
        self.assertEqual(s["usage"]["input_tokens"], {"value": 1500, "confidence": "authoritative"})
        self.assertEqual(s["usage"]["output_tokens"], {"value": 400, "confidence": "authoritative"})
        self.assertEqual(s["usage"]["cache_read_tokens"]["value"], 5000)
        self.assertEqual(s["usage"]["cache_creation_tokens"]["value"], 200)

    def test_unavailable_stays_unavailable(self):
        # No event reported reasoning/tool_result tokens -> unavailable, NOT 0.
        s = self._derive()
        self.assertEqual(s["usage"]["reasoning_tokens"]["confidence"], "unavailable")
        self.assertIsNone(s["usage"]["reasoning_tokens"]["value"])
        self.assertEqual(s["usage"]["tool_result_tokens"]["confidence"], "unavailable")
        self.assertIsNone(s["usage"]["tool_result_tokens"]["value"])

    def test_behavior_counts(self):
        s = self._derive()
        self.assertEqual(s["behavior"]["turns"]["value"], 2)
        self.assertEqual(s["behavior"]["retries"]["value"], 1)
        self.assertEqual(s["behavior"]["verifier_calls"]["value"], 1)
        self.assertEqual(s["behavior"]["file_reads"]["value"], 1)
        self.assertEqual(s["behavior"]["file_read_bytes"]["value"], 2048)
        self.assertEqual(s["behavior"]["tool_calls_by_type"]["value"], {"Read": 1, "Bash": 1})

    def test_acceptance_derived(self):
        s = self._derive()
        self.assertEqual(s["acceptance"]["result"], "accepted")
        self.assertEqual(s["acceptance"]["completed_route"], "P0")

    def test_derived_summary_validates(self):
        ok, reasons = validate_summary(self._derive())
        self.assertTrue(ok, msg=f"reasons: {reasons}")

    def test_no_model_events_leaves_usage_unavailable(self):
        # An event log with no model_call_completed must NOT zero-fill usage.
        s = derive_summary(
            [{"event_type": "tool_invoked", "ts": "T0", "tool": "Read"}],
            run_id="r", task_id="t", task_suite_version="v",
            configuration_id="C1", manifest_ref="m",
            economics={"cost_basis": "cost_unavailable"},
        )
        self.assertEqual(s["usage"]["input_tokens"]["confidence"], "unavailable")
        self.assertIsNone(s["usage"]["input_tokens"]["value"])


class EventLogTests(unittest.TestCase):
    def test_append_and_read_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            log = EventLog(os.path.join(d, "events.jsonl"))
            log.append("model_call_started", "T0", leg="main")
            log.append("acceptance", "T1", result="accepted")
            events = log.read()
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["event_type"], "model_call_started")
            self.assertEqual(events[1]["result"], "accepted")

    def test_unknown_event_type_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            log = EventLog(os.path.join(d, "events.jsonl"))
            with self.assertRaises(ValueError):
                log.append("not_a_real_event", "T0")

    def test_missing_ts_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            log = EventLog(os.path.join(d, "events.jsonl"))
            with self.assertRaises(ValueError):
                log.append("retry", "")


class ValidateRunDirTests(unittest.TestCase):
    """validate(run_dir) is audit-grade: it re-derives from the event log and
    fails on any mismatch, so no fabricated/hand-authored value can pass."""

    def _build_run(self, d, events, mutate=None, cost_basis="marginal_api_cost"):
        log = EventLog(os.path.join(d, "events.jsonl"))
        for ev in events:
            payload = {k: v for k, v in ev.items() if k not in ("event_type", "ts")}
            log.append(ev["event_type"], ev["ts"], **payload)
        summary = derive_summary(
            log.read(), run_id="SYNTHETIC-r", task_id="SYNTHETIC-t",
            task_suite_version="SYNTHETIC-v", configuration_id="C1",
            manifest_ref="SYNTHETIC-m", economics={"cost_basis": cost_basis},
        )
        if mutate:
            mutate(summary)
        with open(os.path.join(d, "summary.json"), "w", encoding="utf-8") as fh:
            json.dump(summary, fh)
        return summary

    def test_validate_run_dir_ok_rederives(self):
        events = list(read_events(os.path.join(FIXTURES, "events-SYNTHETIC.jsonl")))
        with tempfile.TemporaryDirectory() as d:
            self._build_run(d, events)
            ok, reasons = validate(d)
            self.assertTrue(ok, msg=f"reasons: {reasons}")

    def test_validate_missing_summary(self):
        with tempfile.TemporaryDirectory() as d:
            ok, reasons = validate(d)
            self.assertFalse(ok)
            self.assertTrue(any("missing summary.json" in r for r in reasons))

    def test_validate_missing_events_not_audit_grade(self):
        events = list(read_events(os.path.join(FIXTURES, "events-SYNTHETIC.jsonl")))
        with tempfile.TemporaryDirectory() as d:
            self._build_run(d, events)
            os.remove(os.path.join(d, "events.jsonl"))
            ok, reasons = validate(d)
            self.assertFalse(ok)
            self.assertTrue(any("missing events.jsonl" in r for r in reasons))

    def test_validate_flags_bad_event(self):
        events = list(read_events(os.path.join(FIXTURES, "events-SYNTHETIC.jsonl")))
        with tempfile.TemporaryDirectory() as d:
            self._build_run(d, events)
            # Append a malformed event line (bypasses EventLog guards).
            with open(os.path.join(d, "events.jsonl"), "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"event_type": "bogus", "ts": "T9"}) + "\n")
            ok, reasons = validate(d)
            self.assertFalse(ok)
            self.assertTrue(any("unknown event_type" in r for r in reasons))

    # --- Case 1: re-derivation corroborates authoritative values incl. zeros ---
    _AUTH_ZERO_EVENTS = [
        {"event_type": "model_call_completed", "ts": "T1", "leg": "main", "role": "solo",
         "provider": {"value": "provider_a", "confidence": "authoritative"},
         "model_or_selector": {"value": "STRONG_MODEL_A", "confidence": "authoritative"},
         "cost_basis": "marginal_api_cost",
         "usage": {
             "input_tokens": {"value": 100, "confidence": "authoritative"},
             "cache_creation_tokens": {"value": 0, "confidence": "authoritative"},
             "cache_read_tokens": {"value": 0, "confidence": "authoritative"},
             "output_tokens": {"value": 50, "confidence": "authoritative"}}},
        {"event_type": "acceptance", "ts": "T2", "result": "accepted",
         "gate_checks": {}, "intention_to_route": None, "completed_route": None},
    ]

    def test_fabricated_authoritative_zero_rejected(self):
        # Stored output_tokens claims an authoritative 0 the events do not support
        # (the event log says 50). Structural/semantic checks pass it; only
        # re-derivation against the event log catches the fabrication.
        def fake_zero(summary):
            summary["usage"]["output_tokens"] = {"value": 0, "confidence": "authoritative"}
        with tempfile.TemporaryDirectory() as d:
            self._build_run(d, self._AUTH_ZERO_EVENTS, mutate=fake_zero)
            ok, reasons = validate(d)
            self.assertFalse(ok)
            self.assertTrue(
                any("corroboration" in r and "output_tokens" in r for r in reasons),
                msg=f"expected corroboration failure; got {reasons}",
            )

    def test_legitimate_authoritative_zero_passes(self):
        # cache_creation/cache_read are authoritative 0 AND the event log agrees,
        # so the corroborated zero must pass.
        with tempfile.TemporaryDirectory() as d:
            summary = self._build_run(d, self._AUTH_ZERO_EVENTS)
            self.assertEqual(summary["usage"]["cache_read_tokens"],
                             {"value": 0, "confidence": "authoritative"})
            ok, reasons = validate(d)
            self.assertTrue(ok, msg=f"reasons: {reasons}")


if __name__ == "__main__":
    unittest.main()
