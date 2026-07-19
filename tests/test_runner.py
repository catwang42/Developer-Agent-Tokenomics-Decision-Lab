"""Stub-adapter pipeline tests for the controlled runner (Phase 3).

Offline, no spend, no clone, no network: every test drives the runner in
``--dry-run`` (synthetic :class:`StubAdapter` + synthetic gate) against a temp
out-root, then asserts the produced run directory passes the audit-grade telemetry
validator and encodes the intended economics (escalation, dual-bill, unavailable
handling). All inputs are the SYNTHETIC fixtures under tests/fixtures/.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.runner import run as runner  # noqa: E402
from harness.telemetry.telemetry import validate  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
SYNTH_MANIFEST = str(ROOT / "tests" / "fixtures" / "manifest-SYNTHETIC.yaml")
UNRESOLVED_MANIFEST = str(ROOT / "tests" / "fixtures" / "manifest-UNRESOLVED-SYNTHETIC.yaml")
TASK = "tasks/pilot-realworld"


def _run(config: str, *, scenario: str = "accept", manifest: str = SYNTH_MANIFEST,
         out_root: str | None = None, allow_spend: bool = False,
         cache_state: str = "cold", session_id: str | None = None, resume: bool = False):
    """Invoke the runner; return (rc, run_dir_or_None, summary_or_None)."""
    out_root = out_root or tempfile.mkdtemp(prefix="lab-test-")
    argv = ["--task", TASK, "--config", config, "--dry-run", "--cache-state", cache_state,
            "--stub-scenario", scenario, "--manifest", manifest, "--out-root", out_root]
    if session_id:
        argv += ["--session-id", session_id]
    if resume:
        argv += ["--resume"]
    if not allow_spend:
        os.environ.pop("LAB_ALLOW_SPEND", None)
    rc = runner.main(argv)
    run_dirs = [os.path.join(out_root, d) for d in os.listdir(out_root)
                if os.path.isdir(os.path.join(out_root, d))]
    if not run_dirs:
        return rc, None, None
    run_dir = run_dirs[0]
    summary_path = os.path.join(run_dir, "summary.json")
    summary = json.load(open(summary_path, encoding="utf-8")) if os.path.exists(summary_path) else None
    return rc, run_dir, summary


class DryRunPipeline(unittest.TestCase):
    def test_single_configs_validate_audit_grade(self) -> None:
        for config in ("C1", "C2", "P0"):
            rc, run_dir, summary = _run(config)
            self.assertEqual(rc, 0, f"{config} runner exit")
            self.assertIsNotNone(summary)
            ok, reasons = validate(run_dir)
            self.assertTrue(ok, f"{config} not audit-grade: {reasons}")
            self.assertEqual(summary["configuration_id"], config)

    def test_no_zero_fill_anywhere(self) -> None:
        # Unavailable fields must carry value=None; validate() enforces this, but
        # assert directly on a representative unavailable field too.
        _, _, summary = _run("C1")
        rt = summary["usage"]["reasoning_tokens"]
        self.assertEqual(rt["confidence"], "unavailable")
        self.assertIsNone(rt["value"])

    def test_dry_run_writes_only_under_out_root(self) -> None:
        out_root = tempfile.mkdtemp(prefix="lab-isolation-")
        results_before = set((ROOT / "results" / "feasibility").glob("*")) \
            if (ROOT / "results" / "feasibility").exists() else set()
        _, run_dir, _ = _run("C1", out_root=out_root)
        self.assertTrue(run_dir.startswith(out_root), "dry-run escaped out-root")
        results_after = set((ROOT / "results" / "feasibility").glob("*")) \
            if (ROOT / "results" / "feasibility").exists() else set()
        self.assertEqual(results_before, results_after, "dry-run polluted results/")


class P1Escalation(unittest.TestCase):
    def test_escalation_records_routes_and_failed_attempt_cost(self) -> None:
        rc, run_dir, summary = _run("P1", scenario="escalate")
        self.assertEqual(rc, 0)
        ok, reasons = validate(run_dir)
        self.assertTrue(ok, reasons)

        # ITR + CR recorded; escalation happened; accepted after escalation.
        acc = summary["acceptance"]
        self.assertEqual(acc["intention_to_route"], "economical")
        self.assertEqual(acc["completed_route"], "strong")
        self.assertEqual(acc["result"], "accepted")
        self.assertEqual(summary["behavior"]["escalations"]["value"], 1)

        # Failed-attempt cost is present as its own leg (SPEC feasibility crit. 4).
        legs = {leg["leg_id"]: leg for leg in summary["legs"]}
        self.assertIn("economical_attempt", legs)
        self.assertIn("strong_attempt", legs)
        self.assertEqual(legs["economical_attempt"]["marginal_operating_usd"]["confidence"], "derived")
        self.assertIsNotNone(legs["economical_attempt"]["marginal_operating_usd"]["value"])

    def test_accept_scenario_does_not_escalate(self) -> None:
        _, _, summary = _run("P1", scenario="accept")
        self.assertEqual(summary["acceptance"]["completed_route"], "economical")
        self.assertEqual(summary["behavior"]["escalations"]["value"], 0)
        self.assertEqual([leg["leg_id"] for leg in summary["legs"]], ["economical_attempt"])

    def test_reject_scenario_is_rejected(self) -> None:
        _, _, summary = _run("P0", scenario="reject")
        self.assertEqual(summary["acceptance"]["result"], "rejected")


class C5DualBill(unittest.TestCase):
    def test_two_legs_tagged_and_costed(self) -> None:
        rc, run_dir, summary = _run("C5")
        self.assertEqual(rc, 0)
        ok, reasons = validate(run_dir)
        self.assertTrue(ok, reasons)

        legs = {leg["leg_id"]: leg for leg in summary["legs"]}
        self.assertEqual(set(legs), {"conductor", "executor"})
        # Executor is a black-box product: verbatim selector, proxy_observed.
        self.assertEqual(legs["executor"]["model_or_selector"]["confidence"], "proxy_observed")
        self.assertEqual(legs["executor"]["cost_basis"], "provider_reported_cost")
        # frontier_token_share diagnostic is present (unavailable here since the
        # executor does not expose tokens — recorded, not omitted).
        self.assertIn("frontier_token_share", summary)
        # Mixed cost bases -> no single-basis aggregate (per-leg is source of truth).
        self.assertEqual(summary["economics"]["cost_basis"], "cost_unavailable")


class ProductBlackboxUnavailable(unittest.TestCase):
    def test_c3_usage_unavailable_not_zero(self) -> None:
        rc, run_dir, summary = _run("C3")
        self.assertEqual(rc, 0)
        ok, reasons = validate(run_dir)
        self.assertTrue(ok, reasons)
        for cls in ("input_tokens", "output_tokens"):
            field = summary["usage"][cls]
            self.assertEqual(field["confidence"], "unavailable")
            self.assertIsNone(field["value"])
        # Costed via the product-reported figure, not token math.
        self.assertEqual(summary["economics"]["cost_basis"], "provider_reported_cost")
        self.assertEqual(summary["legs"][0]["marginal_operating_usd"]["confidence"], "proxy_observed")


class StartupGuards(unittest.TestCase):
    def test_refuses_unresolved_manifest(self) -> None:
        # An unresolved manifest (all placeholders) -> resolution must refuse (exit
        # 2), even in --dry-run, and write no run directory. Uses a dedicated
        # fixture so the guard is tested independently of whether the real delivery
        # manifest has been filled at CP-SPEND.
        rc, run_dir, _ = _run("P0", manifest=UNRESOLVED_MANIFEST)
        self.assertEqual(rc, 2)
        self.assertIsNone(run_dir)

    def test_live_run_requires_spend_approval(self) -> None:
        os.environ.pop("LAB_ALLOW_SPEND", None)
        rc = runner.main(["--task", TASK, "--config", "P0", "--cache-state", "cold",
                          "--manifest", SYNTH_MANIFEST])
        self.assertEqual(rc, 2)


class CacheStateContract(unittest.TestCase):
    def test_cold_run_records_authoritative_cold_state(self) -> None:
        rc, run_dir, summary = _run("C1", cache_state="cold")
        self.assertEqual(rc, 0)
        ok, reasons = validate(run_dir)
        self.assertTrue(ok, reasons)
        cs = summary["identity"]["cache_state"]
        self.assertEqual(cs["value"], "cold")
        self.assertEqual(cs["confidence"], "authoritative")
        self.assertEqual(summary["identity"]["session_state"]["value"], "fresh")

    def test_cold_freshness_provable_from_event_log(self) -> None:
        # A session id is stamped on model_call_started so freshness is provable
        # from the immutable log (cache-protocol rule 4), and no leg resumed.
        _, run_dir, _ = _run("P0", cache_state="cold")
        with open(os.path.join(run_dir, "events.jsonl"), encoding="utf-8") as fh:
            starts = [json.loads(l) for l in fh if '"model_call_started"' in l]
        self.assertTrue(starts)
        for e in starts:
            self.assertTrue(e.get("session_id"))
            self.assertFalse(e.get("resumed"))

    def test_warm_series_resumes_session(self) -> None:
        rc, run_dir, summary = _run("C1", cache_state="warm-series",
                                    session_id="lab-warm-1", resume=True)
        self.assertEqual(rc, 0)
        ok, reasons = validate(run_dir)
        self.assertTrue(ok, reasons)
        self.assertEqual(summary["identity"]["cache_state"]["value"], "warm-series")
        self.assertEqual(summary["identity"]["session_state"]["value"], "resumed")

    def test_cache_state_is_required(self) -> None:
        # Omitting --cache-state is an argparse error (SystemExit), not a run.
        out_root = tempfile.mkdtemp(prefix="lab-test-")
        with self.assertRaises(SystemExit):
            runner.main(["--task", TASK, "--config", "C1", "--dry-run",
                         "--manifest", SYNTH_MANIFEST, "--out-root", out_root])

    def test_warm_series_without_resume_refused(self) -> None:
        rc, run_dir, _ = _run("C1", cache_state="warm-series")
        self.assertEqual(rc, 2)
        self.assertIsNone(run_dir)

    def test_cold_with_resume_refused(self) -> None:
        rc, run_dir, _ = _run("C1", cache_state="cold", session_id="x", resume=True)
        self.assertEqual(rc, 2)
        self.assertIsNone(run_dir)


if __name__ == "__main__":
    unittest.main()
