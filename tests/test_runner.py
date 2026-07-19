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
         cache_state: str = "cold", session_id: str | None = None, resume: bool = False,
         spend_cap: float | None = None):
    """Invoke the runner; return (rc, run_dir_or_None, summary_or_None).

    ``run_dir`` is the newest run directory under ``out_root`` (so a second call
    sharing an ``out_root`` reports the run it just produced, not an earlier one).
    """
    out_root = out_root or tempfile.mkdtemp(prefix="lab-test-")
    argv = ["--task", TASK, "--config", config, "--dry-run", "--cache-state", cache_state,
            "--stub-scenario", scenario, "--manifest", manifest, "--out-root", out_root]
    if session_id:
        argv += ["--session-id", session_id]
    if resume:
        argv += ["--resume"]
    if spend_cap is not None:
        argv += ["--spend-cap-usd", str(spend_cap)]
    if not allow_spend:
        os.environ.pop("LAB_ALLOW_SPEND", None)
    rc = runner.main(argv)
    run_dirs = [os.path.join(out_root, d) for d in os.listdir(out_root)
                if os.path.isdir(os.path.join(out_root, d))]
    if not run_dirs:
        return rc, None, None
    run_dir = max(run_dirs, key=os.path.getmtime)
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
                                    session_id="11111111-1111-4111-8111-111111111111",
                                    resume=True)
        self.assertEqual(rc, 0)
        ok, reasons = validate(run_dir)
        self.assertTrue(ok, reasons)
        self.assertEqual(summary["identity"]["cache_state"]["value"], "warm-series")
        self.assertEqual(summary["identity"]["session_state"]["value"], "resumed")

    def test_non_uuid_session_id_rejected(self) -> None:
        # A non-UUID --session-id is a clear runner error (the product CLI rejects
        # it and would otherwise emit a non-JSON error, losing usage telemetry).
        rc, run_dir, _ = _run("C1", cache_state="warm-series",
                              session_id="lab-warm-1", resume=True)
        self.assertEqual(rc, 2)
        self.assertIsNone(run_dir)

    def test_cold_leg_session_ids_are_valid_uuids(self) -> None:
        # Every leg's session id in the event log must parse as a UUID (P1 has two
        # cold legs, each an independent fresh session).
        import uuid as _uuid
        _, run_dir, _ = _run("P1", scenario="escalate", cache_state="cold")
        with open(os.path.join(run_dir, "events.jsonl"), encoding="utf-8") as fh:
            starts = [json.loads(l) for l in fh if '"model_call_started"' in l]
        self.assertGreaterEqual(len(starts), 2)
        seen = set()
        for e in starts:
            _uuid.UUID(e["session_id"])       # raises if not a valid UUID
            seen.add(e["session_id"])
        self.assertEqual(len(seen), len(starts))   # distinct fresh session per cold leg

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


class SpendCapKillSwitch(unittest.TestCase):
    """CP-SPEND option (a): cumulative batch spend ceiling, no spend to test."""

    def _seed_summary(self, batch_dir: str, name: str, leg_costs) -> None:
        """Write a minimal sibling summary.json with the given per-leg costs.

        ``leg_costs`` entries are either a float (a derived cost) or ``None`` (an
        unavailable-cost leg) — matching the shape cumulative_spend_usd reads.
        """
        run_dir = os.path.join(batch_dir, name)
        os.makedirs(run_dir, exist_ok=True)
        legs = []
        for i, c in enumerate(leg_costs):
            if c is None:
                mov = {"value": None, "confidence": "unavailable", "reason": "test"}
            else:
                mov = {"value": c, "confidence": "derived"}
            legs.append({"leg_id": f"leg{i}", "marginal_operating_usd": mov})
        with open(os.path.join(run_dir, "summary.json"), "w", encoding="utf-8") as fh:
            json.dump({"legs": legs}, fh)

    def test_cumulative_spend_sums_per_leg_and_counts_unavailable(self) -> None:
        batch = tempfile.mkdtemp(prefix="lab-cap-")
        self._seed_summary(batch, "runA", [10.0, 15.0])       # single-basis, $25
        self._seed_summary(batch, "runB", [5.0, None])        # mixed: $5 + unavailable
        total, n_runs, n_unavail = runner.cumulative_spend_usd(batch)
        self.assertAlmostEqual(total, 30.0)
        self.assertEqual(n_runs, 2)
        self.assertEqual(n_unavail, 1)   # unavailable leg counted, never zero-imputed

    def test_empty_or_missing_batch_dir_is_zero(self) -> None:
        self.assertEqual(runner.cumulative_spend_usd("/nonexistent/batch"), (0.0, 0, 0))
        self.assertEqual(runner.cumulative_spend_usd(tempfile.mkdtemp()), (0.0, 0, 0))

    def test_halts_before_run_when_prior_spend_at_cap(self) -> None:
        batch = tempfile.mkdtemp(prefix="lab-cap-")
        self._seed_summary(batch, "prior", [61.0])            # already over a $60 cap
        before = set(os.listdir(batch))
        rc, _, _ = _run("P0", out_root=batch, spend_cap=60.0)
        self.assertEqual(rc, 3)                                # dedicated halt code
        # No new run directory was created — the run never started.
        self.assertEqual(set(os.listdir(batch)), before)

    def test_under_cap_run_proceeds(self) -> None:
        batch = tempfile.mkdtemp(prefix="lab-cap-")
        self._seed_summary(batch, "prior", [1.0])             # well under cap
        rc, run_dir, summary = _run("P0", out_root=batch, spend_cap=60.0)
        self.assertEqual(rc, 0)
        self.assertIsNotNone(summary)

    def test_halt_is_resumable_by_raising_cap(self) -> None:
        batch = tempfile.mkdtemp(prefix="lab-cap-")
        self._seed_summary(batch, "prior", [50.0])
        # $50 prior >= $40 cap -> halt; prior results untouched.
        rc_halt, _, _ = _run("P0", out_root=batch, spend_cap=40.0)
        self.assertEqual(rc_halt, 3)
        # Raise the cap above prior spend -> the same batch resumes and runs.
        rc_resume, run_dir, summary = _run("P0", out_root=batch, spend_cap=100.0)
        self.assertEqual(rc_resume, 0)
        self.assertIsNotNone(summary)

    def test_cap_counts_real_completed_run(self) -> None:
        # A first real (stub) run accrues a small cost; a second run under a cap
        # below that accrued cost halts — the cap reads live event-log-derived cost.
        batch = tempfile.mkdtemp(prefix="lab-cap-")
        rc1, run_dir1, _ = _run("P0", out_root=batch)         # default cap, proceeds
        self.assertEqual(rc1, 0)
        spent, n_runs, _ = runner.cumulative_spend_usd(batch)
        self.assertGreater(spent, 0.0)
        self.assertEqual(n_runs, 1)
        rc2, _, _ = _run("P0", out_root=batch, spend_cap=spent / 2)
        self.assertEqual(rc2, 3)


class AgentDiffArchive(unittest.TestCase):
    """Provenance: the agent's solution diff is preserved before any reset."""

    def _git(self, repo, *args):
        import subprocess
        subprocess.run(["git", "-C", repo, *args], check=True,
                       capture_output=True, text=True)

    def test_archives_tracked_diff_and_untracked_list(self) -> None:
        import subprocess
        repo = tempfile.mkdtemp(prefix="lab-subj-")
        self._git(repo, "init", "-q")
        self._git(repo, "config", "user.email", "t@t")
        self._git(repo, "config", "user.name", "t")
        with open(os.path.join(repo, "svc.ts"), "w") as fh:
            fh.write("const x = 1;\n")
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-qm", "base")
        # Agent edits a tracked file and creates an untracked one.
        with open(os.path.join(repo, "svc.ts"), "w") as fh:
            fh.write("const x = 2;  // draft: false\n")
        with open(os.path.join(repo, "new.ts"), "w") as fh:
            fh.write("extra\n")
        run_dir = tempfile.mkdtemp(prefix="lab-run-")
        runner._archive_agent_diff(repo, run_dir)
        text = open(os.path.join(run_dir, "agent-solution.diff"), encoding="utf-8").read()
        self.assertIn("draft: false", text)      # tracked edit captured
        self.assertIn("svc.ts", text)
        self.assertIn("new.ts", text)            # untracked file listed

    def test_never_raises_on_non_repo(self) -> None:
        run_dir = tempfile.mkdtemp(prefix="lab-run-")
        runner._archive_agent_diff(tempfile.mkdtemp(), run_dir)  # not a git repo -> no raise


if __name__ == "__main__":
    unittest.main()
