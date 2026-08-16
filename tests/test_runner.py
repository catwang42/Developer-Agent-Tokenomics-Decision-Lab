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
import shutil
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.adapters import agy  # noqa: E402
from harness.runner import run as runner  # noqa: E402
from harness.telemetry.telemetry import validate  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
SYNTH_MANIFEST = str(ROOT / "tests" / "fixtures" / "manifest-SYNTHETIC.yaml")
UNRESOLVED_MANIFEST = str(ROOT / "tests" / "fixtures" / "manifest-UNRESOLVED-SYNTHETIC.yaml")
TASK = "tasks/pilot-realworld"


def _run(config: str, *, scenario: str = "accept", manifest: str = SYNTH_MANIFEST,
         out_root: str | None = None, allow_spend: bool = False,
         cache_state: str = "cold", session_id: str | None = None, resume: bool = False,
         spend_cap: float | None = None, subject_isolation: str | None = None,
         subject_network: str | None = None):
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
    if subject_isolation is not None:
        argv += ["--subject-isolation", subject_isolation]
    if subject_network is not None:
        argv += ["--subject-network", subject_network]
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


class CostBasisQualifier(unittest.TestCase):
    """A declared qualification of a cost_basis must survive to the summary.

    The screening window declares Product-B costing cache-blind (human decision
    2026-08-16): every Gemini leg carries ``cost_basis_qualifier:
    cache_blind_upper_bound`` beside an unchanged ``cost_basis``. The failure this
    guards against is silence — a qualifier that is pinned in the manifest, dropped
    somewhere between resolution and the summary, and so never seen by whoever
    reads the cost. It must also survive re-derivation, or the run is not
    audit-grade.
    """

    def test_solo_leg_carries_the_qualifier_and_stays_audit_grade(self) -> None:
        rc, run_dir, summary = _run("C3")
        self.assertEqual(rc, 0)
        ok, reasons = validate(run_dir)
        self.assertTrue(ok, f"qualifier broke re-derivation: {reasons}")
        self.assertEqual(summary["legs"][0]["cost_basis_qualifier"],
                         "cache_blind_upper_bound")
        self.assertEqual(summary["economics"]["cost_basis_qualifier"],
                         "cache_blind_upper_bound")
        # The frozen enum is untouched — the qualifier sits BESIDE the basis.
        self.assertEqual(summary["legs"][0]["cost_basis"], "provider_reported_cost")

    def test_one_qualified_leg_qualifies_the_whole_run(self) -> None:
        """C5: a total containing one upper bound is itself an upper bound."""
        rc, _, summary = _run("C5")
        self.assertEqual(rc, 0)
        legs = {leg["leg_id"]: leg for leg in summary["legs"]}
        self.assertNotIn("cost_basis_qualifier", legs["conductor"])
        self.assertEqual(legs["executor"]["cost_basis_qualifier"],
                         "cache_blind_upper_bound")
        self.assertEqual(summary["economics"]["cost_basis_qualifier"],
                         "cache_blind_upper_bound")

    def test_unqualified_run_gains_no_key(self) -> None:
        """Absence stays absence: C1 has nothing to qualify."""
        rc, _, summary = _run("C1")
        self.assertEqual(rc, 0)
        self.assertNotIn("cost_basis_qualifier", summary["legs"][0])
        self.assertNotIn("cost_basis_qualifier", summary["economics"])

    def test_an_unknown_qualifier_is_refused(self) -> None:
        """Free text here could smuggle an unreviewed costing claim into a summary."""
        manifest = yaml.safe_load(open(SYNTH_MANIFEST, encoding="utf-8"))
        manifest["configurations"]["PRODUCT_B_ECON_TIER"]["cost_basis_qualifier"] = \
            "SYNTHETIC-not-a-real-qualifier"
        with self.assertRaises(runner.RunnerError):
            runner.resolve_model(manifest, "PRODUCT_B_ECON_TIER", "product_b")


class ScreeningArms(unittest.TestCase):
    """The two extra Product-B arms added for the screening window.

    C3-med (effort) and C3-prev (generation) exist so the summarizer cannot merge
    them into C3. Each must plan, run and validate as its OWN configuration_id and
    resolve its OWN selector — if either collapsed onto C3's id or C3's selector,
    the arm would be invisible in exactly the way the schema widening was meant to
    prevent.
    """

    ARMS = {"C3-med": "PRODUCT_B_ECON_TIER_MED", "C3-prev": "PRODUCT_B_ECON_TIER_PREV"}

    def test_each_arm_validates_under_its_own_configuration_id(self) -> None:
        for config in self.ARMS:
            with self.subTest(config=config):
                rc, run_dir, summary = _run(config)
                self.assertEqual(rc, 0, f"{config} runner exit")
                ok, reasons = validate(run_dir)
                self.assertTrue(ok, f"{config} not audit-grade: {reasons}")
                self.assertEqual(summary["configuration_id"], config)

    def test_arms_resolve_distinct_selectors_from_c3(self) -> None:
        manifest = yaml.safe_load(open(SYNTH_MANIFEST, encoding="utf-8"))
        seen = {}
        for config in ("C3", *self.ARMS):
            plan = runner.build_plan(config, manifest)
            self.assertEqual(len(plan.legs), 1, f"{config} is a solo arm")
            seen[config] = plan.legs[0].resolved.model_or_selector
        self.assertEqual(len(set(seen.values())), 3, f"arms share a selector: {seen}")

    def test_arms_never_infer_a_backend_model_id(self) -> None:
        """SPEC 6.3 holds for the new arms too: label verbatim, id never inferred."""
        manifest = yaml.safe_load(open(SYNTH_MANIFEST, encoding="utf-8"))
        for config in self.ARMS:
            with self.subTest(config=config):
                resolved = runner.build_plan(config, manifest).legs[0].resolved
                self.assertIsNone(resolved.model_id)
                self.assertEqual(resolved.model_confidence, "proxy_observed")


class ProductVersionPreflight(unittest.TestCase):
    """Pre-batch product-version check (human decision 2026-08-16, decision 4).

    agy self-updates, so the binary can move between the CP-SPEND approval that
    priced a batch and the run that spends against it. The adapter's own check
    fires inside the attempt, after the run directory exists; this one fires
    before anything is created or billed.
    """

    def _plan(self, config: str = "C3-med"):
        manifest = yaml.safe_load(open(SYNTH_MANIFEST, encoding="utf-8"))
        return runner.build_plan(config, manifest)

    def _with_version(self, version: str, plan) -> None:
        seen = {}
        original = runner.cli_version

        def fake(binary, container=None, env=None):
            seen["binary"], seen["env"] = binary, env
            return version

        runner.cli_version = fake
        try:
            runner.preflight_product_versions(plan)
        finally:
            runner.cli_version = original
        self.seen = seen

    def test_the_pinned_version_passes_and_the_probe_disables_auto_update(self) -> None:
        plan = self._plan()
        self.assertEqual(plan.legs[0].resolved.product_version_pin, "SYNTHETIC-0.0.0")
        self._with_version("SYNTHETIC-0.0.0", plan)
        self.assertEqual(self.seen["binary"], "agy")
        # The probe itself must not be the invocation that lets an update land.
        self.assertEqual(self.seen["env"].get(agy.AUTO_UPDATE_DISABLE_ENV), "1")

    def test_a_drifted_version_refuses_to_start(self) -> None:
        plan = self._plan()
        with self.assertRaises(runner.RunnerError):
            self._with_version("SYNTHETIC-9.9.9", plan)

    def test_an_unreadable_version_refuses_too(self) -> None:
        """A pin that cannot be checked has not been satisfied — unavailable != ok."""
        plan = self._plan()
        with self.assertRaises(runner.RunnerError):
            self._with_version("unavailable", plan)

    def test_an_unpinned_leg_is_not_probed(self) -> None:
        """Product-A legs have no agy pin; probing for them would make a Claude-only
        run depend on whether agy is installed at all."""
        plan = self._plan("C1")
        self.assertIsNone(plan.legs[0].resolved.product_version_pin)
        self.seen = {}
        self._with_version("SYNTHETIC-9.9.9", plan)   # would raise if probed
        self.assertEqual(self.seen, {})

    def test_dry_runs_do_not_probe_the_product_binary(self) -> None:
        """--dry-run drives stub adapters and never touches agy; probing there would
        make the offline suite depend on the host's installed product."""
        called = []
        original = runner.cli_version
        runner.cli_version = lambda *a, **k: called.append(a) or "SYNTHETIC-9.9.9"
        try:
            rc, run_dir, _ = _run("C3-med")
        finally:
            runner.cli_version = original
        self.assertEqual(rc, 0)
        self.assertEqual(called, [])
        ok, reasons = validate(run_dir)
        self.assertTrue(ok, f"not audit-grade: {reasons}")


class AutoUpdateKillSwitch(unittest.TestCase):
    """The updater state is a pinned run condition, so it must actually be set."""

    def test_the_adapter_env_carries_the_products_own_kill_switch(self) -> None:
        env = agy.agy_env()
        self.assertEqual(env[agy.AUTO_UPDATE_DISABLE_ENV], "1")
        # ...and does not drop what agent_env() already provided.
        for key, value in agy.agent_env().items():
            self.assertEqual(env[key], value)

    def test_the_condition_string_names_the_variable_it_sets(self) -> None:
        """A condition recorded as a bare 'disabled' would not say how, and could not
        be re-established by anyone reading the run record."""
        self.assertIn(agy.AUTO_UPDATE_DISABLE_ENV, agy.AUTO_UPDATE_CONDITION)


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


class SubjectIsolationPosture(unittest.TestCase):
    """The runner authoritatively stamps the subject-isolation posture (batch-2)."""

    def test_host_default_records_host_posture(self) -> None:
        _, run_dir, summary = _run("P0")  # default --subject-isolation host
        ident = summary["identity"]
        self.assertEqual(ident["permission_profile"]["confidence"], "authoritative")
        self.assertIn("no-container", ident["permission_profile"]["value"])
        self.assertEqual(ident["network_policy"]["value"], "no-network-policy")
        self.assertEqual(ident["network_policy"]["confidence"], "authoritative")
        ok, reasons = validate(run_dir)
        self.assertTrue(ok, reasons)

    def test_container_records_container_posture_and_network(self) -> None:
        _, run_dir, summary = _run("P0", subject_isolation="container")
        ident = summary["identity"]
        self.assertIn("container-isolated", ident["permission_profile"]["value"])
        self.assertEqual(ident["permission_profile"]["confidence"], "authoritative")
        self.assertEqual(ident["network_policy"]["value"], "none")
        self.assertEqual(ident["network_policy"]["confidence"], "authoritative")
        ok, reasons = validate(run_dir)
        self.assertTrue(ok, reasons)

    def test_network_value_recorded_verbatim(self) -> None:
        # Whatever --subject-network is used is recorded authoritatively (a CP-SPEND
        # egress network name would flow through unchanged).
        _, _, summary = _run("P0", subject_isolation="container",
                             subject_network="lab-egress-model-only")
        self.assertEqual(summary["identity"]["network_policy"]["value"],
                         "lab-egress-model-only")


class ContainerizedAgentLegPosture(unittest.TestCase):
    """Stamps for the containerized AGENT leg (SPEC §6 item 1).

    Drives ``execute_and_validate_run`` with the stub adapter and
    ``agent_containerized=True`` — the state a real container-mode run reaches —
    so the recorded posture is pinned without a Docker daemon or any spend.
    """

    def _stub_run(self, network_label: str):
        out_root = tempfile.mkdtemp(prefix="lab-agentmode-")
        run_dir = os.path.join(out_root, "pilot__P0__rep1__stub")
        os.makedirs(run_dir)
        manifest = runner._load_yaml(SYNTH_MANIFEST)
        task = runner.load_task(TASK, manifest)
        plan = runner.build_plan("P0", manifest)
        prices, snapshot = runner.resolve_pricing(manifest, plan)
        ok, reasons = runner.execute_and_validate_run(
            run_dir=run_dir, task=task, plan=plan, adapter=runner.StubAdapter(),
            subject_dir=os.path.join(run_dir, "SYNTHETIC-subject"), launch=None,
            cache_state="cold", base_session="11111111-1111-4111-8111-111111111111",
            resume=False, subject_isolation="container",
            subject_network=network_label, agent_containerized=True,
            manifest_rel="tests/fixtures/manifest-SYNTHETIC.yaml",
            prices=prices, pricing_snapshot=snapshot, config_id="P0",
            dry_run=True, scenario="accept",
        )
        with open(os.path.join(run_dir, "summary.json"), encoding="utf-8") as fh:
            summary = json.load(fh)
        return ok, reasons, run_dir, summary

    def test_stub_run_in_container_mode_produces_a_valid_summary(self) -> None:
        ok, reasons, run_dir, summary = self._stub_run("egress-allowlist:model-api-v1")
        self.assertTrue(ok, reasons)
        valid, why = validate(run_dir)
        self.assertTrue(valid, why)
        self.assertIsNotNone(summary["identity"]["permission_profile"]["value"])

    def test_agent_profile_states_what_is_actually_enforced(self) -> None:
        _, _, _, summary = self._stub_run("egress-allowlist:model-api-v1")
        profile = summary["identity"]["permission_profile"]["value"]
        self.assertEqual(
            summary["identity"]["permission_profile"]["confidence"], "authoritative")
        # Claims the agent image genuinely enforces.
        for claim in ("container-isolated", "image=subject-agent", "cwd-confined-/subject",
                      "credentials-mounted-read-only",
                      "no-canonical|hidden|task.yaml-in-image(build-asserted)"):
            self.assertIn(claim, profile)
        # The FIX C lesson: the stamp must NOT imply isolation the mode lacks.
        # Tool permissions are still bypassed and egress is allowlisted, not absent.
        self.assertIn("skip-all-tools-inside-container", profile)
        self.assertNotIn("no-network", profile)
        self.assertIn("egress-allowlisted-see-network_policy", profile)

    def test_network_label_distinguishes_agent_leg_from_gate(self) -> None:
        # One field covers two containers with opposite postures; a reader must not
        # have to guess which leg the recorded policy applied to.
        _, _, _, summary = self._stub_run(
            "egress-allowlist:model-api-v1@sha256:ce78aa16d545; deny-by-default")
        label = summary["identity"]["network_policy"]["value"]
        self.assertTrue(label.startswith("agent-leg: "))
        self.assertIn("sha256:ce78aa16d545", label)
        self.assertIn("gate: none", label)


class ResultRecordEmission(unittest.TestCase):
    def test_result_json_emitted_and_matches_summary(self) -> None:
        _, run_dir, summary = _run("P1", scenario="escalate")
        result_path = os.path.join(run_dir, "result.json")
        self.assertTrue(os.path.exists(result_path))
        with open(result_path, encoding="utf-8") as fh:
            record = json.load(fh)
        self.assertEqual(record["run_id"], summary["run_id"])
        self.assertEqual(record["task_id"], summary["task_id"])
        self.assertEqual(record["acceptance"]["result"], summary["acceptance"]["result"])
        self.assertEqual(record["acceptance"]["completed_route"], "strong")
        # Per-leg costs match the summary (pure projection, no new numbers).
        self.assertEqual([leg["leg_id"] for leg in record["legs"]],
                         [leg["leg_id"] for leg in summary["legs"]])

    def test_result_json_preserves_unavailable(self) -> None:
        _, run_dir, _ = _run("C3")  # black-box product: tokens unavailable
        with open(os.path.join(run_dir, "result.json"), encoding="utf-8") as fh:
            record = json.load(fh)
        it = record["usage"]["input_tokens"]
        self.assertIsNone(it["value"])
        self.assertEqual(it["confidence"], "unavailable")


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
        self.assertIn("extra", text)             # ...with its content, not just its name

    def test_untracked_file_content_is_captured(self) -> None:
        """Test-generation tasks emit only new files; their CONTENT must survive.

        Regression for the batch-2 defect where the archive recorded untracked
        filenames only (79-byte agent-solution.diff), so the whole generated test
        suite was lost at reset.
        """
        repo = tempfile.mkdtemp(prefix="lab-subj-")
        self._git(repo, "init", "-q")
        self._git(repo, "config", "user.email", "t@t")
        self._git(repo, "config", "user.name", "t")
        with open(os.path.join(repo, "README.md"), "w") as fh:
            fh.write("base\n")
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-qm", "base")
        # Agent's entire output is a brand-new (untracked) test file — no tracked edits.
        test_dir = os.path.join(repo, "src", "tests", "mappers")
        os.makedirs(test_dir)
        marker = "describe('article.mapper', () => { it('maps', () => expect(1).toBe(1)); });"
        rel_path = os.path.join("src", "tests", "mappers", "article.mapper.test.ts")
        with open(os.path.join(repo, rel_path), "w") as fh:
            fh.write(marker + "\n")
        run_dir = tempfile.mkdtemp(prefix="lab-run-")
        runner._archive_agent_diff(repo, run_dir)
        text = open(os.path.join(run_dir, "agent-solution.diff"), encoding="utf-8").read()
        self.assertIn(rel_path, text)   # path recorded
        self.assertIn(marker, text)     # ...and the full file content, not just the name

    def test_excludes_node_modules_untracked(self) -> None:
        """node_modules content is still excluded when capturing untracked files."""
        repo = tempfile.mkdtemp(prefix="lab-subj-")
        self._git(repo, "init", "-q")
        self._git(repo, "config", "user.email", "t@t")
        self._git(repo, "config", "user.name", "t")
        with open(os.path.join(repo, "README.md"), "w") as fh:
            fh.write("base\n")
        self._git(repo, "add", "-A")
        self._git(repo, "commit", "-qm", "base")
        os.makedirs(os.path.join(repo, "node_modules", "left-pad"))
        with open(os.path.join(repo, "node_modules", "left-pad", "index.js"), "w") as fh:
            fh.write("NODE_MODULES_LEAK_MARKER\n")
        with open(os.path.join(repo, "solution.ts"), "w") as fh:
            fh.write("REAL_SOLUTION_MARKER\n")
        run_dir = tempfile.mkdtemp(prefix="lab-run-")
        runner._archive_agent_diff(repo, run_dir)
        text = open(os.path.join(run_dir, "agent-solution.diff"), encoding="utf-8").read()
        self.assertIn("REAL_SOLUTION_MARKER", text)
        self.assertNotIn("NODE_MODULES_LEAK_MARKER", text)

    def test_never_raises_on_non_repo(self) -> None:
        run_dir = tempfile.mkdtemp(prefix="lab-run-")
        runner._archive_agent_diff(tempfile.mkdtemp(), run_dir)  # not a git repo -> no raise


class SubjectStagingIsolation(unittest.TestCase):
    """FIX A: from the staged subject root, relative traversal must not reach
    canonical/, hidden/, or task.yaml (the documented subject-isolation leak)."""

    # The exact relative paths that WERE reachable when cwd was <TASK_DIR>/.work/repo.
    _SENSITIVE_RELS = (
        "../../canonical", "../../hidden", "../../task.yaml",
        "../canonical", "../hidden", "../task.yaml",
        "../../../tasks",
    )

    def test_staged_subject_blocks_relative_traversal_to_answers(self) -> None:
        repo_root = runner.REPO_ROOT
        # The leak was real: under the old in-repo layout the answer sat at ../../.
        self.assertTrue(
            os.path.isdir(os.path.join(repo_root, "tasks", "pilot-realworld", "canonical")),
            "precondition: pilot canonical/ exists in-repo (the material that leaked)",
        )

        # Synthetic prepared subject repo (no clone; offline).
        src = tempfile.mkdtemp(prefix="fake-src-repo-")
        with open(os.path.join(src, "package.json"), "w", encoding="utf-8") as fh:
            fh.write("{}\n")
        os.makedirs(os.path.join(src, "src"))
        with open(os.path.join(src, "src", "app.ts"), "w", encoding="utf-8") as fh:
            fh.write("export const x = 1;\n")

        staged_repo = runner._stage_subject_outside_repo(src)
        try:
            # 1) staged outside the lab repo.
            self.assertFalse(
                os.path.abspath(staged_repo) == repo_root
                or os.path.abspath(staged_repo).startswith(repo_root + os.sep),
                f"staged repo must be outside the lab repo: {staged_repo}",
            )
            # 2) subject content actually copied.
            self.assertTrue(os.path.exists(os.path.join(staged_repo, "package.json")))
            self.assertTrue(os.path.exists(os.path.join(staged_repo, "src", "app.ts")))
            # 3) the exact relative paths that used to leak now (a) do not exist and
            #    (b) do not resolve into the lab repo.
            for rel in self._SENSITIVE_RELS:
                p = os.path.join(staged_repo, rel)
                self.assertFalse(os.path.exists(p),
                                 f"sensitive path reachable via {rel}: {p}")
                target = os.path.realpath(p)
                self.assertFalse(
                    target == repo_root or target.startswith(repo_root + os.sep),
                    f"{rel} escapes into the lab repo: {target}",
                )
        finally:
            shutil.rmtree(os.path.dirname(staged_repo), ignore_errors=True)
            shutil.rmtree(src, ignore_errors=True)

    def test_refuses_staging_inside_lab_repo(self) -> None:
        """If TMPDIR would place the staged tree inside the repo, refuse (would
        re-open the leak) rather than silently staging in-repo."""
        src = tempfile.mkdtemp(prefix="fake-src-repo-")
        inside = tempfile.mkdtemp(prefix="staged-", dir=runner.REPO_ROOT)
        orig_mkdtemp = tempfile.mkdtemp
        tempfile.mkdtemp = lambda *a, **k: inside  # force an in-repo staging dir
        try:
            with self.assertRaises(runner.RunnerError):
                runner._stage_subject_outside_repo(src)
        finally:
            tempfile.mkdtemp = orig_mkdtemp
            shutil.rmtree(inside, ignore_errors=True)
            shutil.rmtree(src, ignore_errors=True)


class ArchiveOrdering(unittest.TestCase):
    """Fix 5: agent-solution.diff must be captured BEFORE the gate mutates the tree,
    so the harness's own edits (test_compat_patch, test restores) are never
    attributed to the agent. Root cause of the C3 identical-diff / P0 phantom-file
    findings."""

    def _git(self, repo, *args):
        import subprocess
        subprocess.run(["git", "-C", repo, *args], check=True,
                       capture_output=True, text=True)

    def test_harness_patch_absent_from_agent_diff(self) -> None:
        import uuid
        from harness.adapters.base import AttemptOutcome, ResolvedModel

        subject_dir = tempfile.mkdtemp(prefix="lab-subj-")
        self._git(subject_dir, "init", "-q")
        self._git(subject_dir, "config", "user.email", "t@t")
        self._git(subject_dir, "config", "user.name", "t")
        with open(os.path.join(subject_dir, "base.ts"), "w") as fh:
            fh.write("base\n")
        self._git(subject_dir, "add", "-A")
        self._git(subject_dir, "commit", "-qm", "base")

        # Agent writes its solution; the gate later mutates the tree (as the real
        # gate does when it applies test_compat_patch and restores tests).
        class _TreeWritingAdapter:
            container = None

            def run_attempt(self, spec, sdir, emit):
                with open(os.path.join(sdir, "agent_solution.ts"), "w") as fh:
                    fh.write("// AGENT_MARKER\n")
                return AttemptOutcome(identity={}, leg_options={}, invocation={})

        def fake_gate(dry_run, scenario, leg_id, task, run_dir, launch, subject_dir_arg):
            with open(os.path.join(subject_dir, "harness_patch.ts"), "w") as fh:
                fh.write("// HARNESS_MARKER injected by the gate\n")
            return True, "accepted", {}

        resolved = ResolvedModel(
            product="Product A", product_surface="controlled_api",
            provider="google_vertex", model_or_selector="m", model_id="m",
            cost_basis="marginal_api_cost",
        )
        plan = runner.RunPlan("fake", [runner.LegPlan("main", "solver", resolved)], "static")
        task = runner.Task(task_dir=subject_dir, task_id="t", task_suite_version="v",
                           prompt="do it", contamination_tier=None, hidden_test_hash=None)
        run_dir = tempfile.mkdtemp(prefix="lab-run-")

        orig_gate = runner._gate
        runner._gate = fake_gate
        try:
            runner.execute(
                plan, task, _TreeWritingAdapter(), subject_dir, run_dir,
                lambda *a, **k: None, dry_run=False, scenario="accept",
                cache_state="cold", base_session=str(uuid.uuid4()), resume=False,
            )
        finally:
            runner._gate = orig_gate

        with open(os.path.join(run_dir, "agent-solution.diff"), encoding="utf-8") as fh:
            agent_diff = fh.read()
        self.assertIn("AGENT_MARKER", agent_diff)           # agent's work captured
        self.assertNotIn("HARNESS_MARKER", agent_diff)      # harness patch NOT attributed
        self.assertNotIn("harness_patch.ts", agent_diff)

        # The post-gate snapshot is separate and DOES include the harness edit.
        post_gate_path = os.path.join(run_dir, "post-gate.diff")
        self.assertTrue(os.path.exists(post_gate_path))
        with open(post_gate_path, encoding="utf-8") as fh:
            post_diff = fh.read()
        self.assertIn("HARNESS_MARKER", post_diff)
        self.assertIn("AGENT_MARKER", post_diff)


class InvocationRecord(unittest.TestCase):
    """invocation.txt records the exact CLI command(s) + version; redacts creds."""

    def test_writes_argv_version_and_redacts_credentials(self) -> None:
        run_dir = tempfile.mkdtemp(prefix="lab-run-")
        invocations = [{
            "leg": "main", "role": "solver",
            "product_version": "claude 9.9.9 (Claude Code)",
            "argv": ["claude", "-p", "implement the draft flag", "--model",
                     "strong@default", "--output-format", "json",
                     "--dangerously-skip-permissions"],
            "cwd": "/tmp/subject/.work/repo",
        }]
        env = {
            "PATH": "/usr/bin",
            "ANTHROPIC_API_KEY": "sk-secret-value-xyz",
            "CLAUDE_CODE_OAUTH_TOKEN": "oauth-secret-abc",
            "GOOGLE_APPLICATION_CREDENTIALS": "/home/u/adc.json",
            "ANTHROPIC_VERTEX_PROJECT_ID": "vital-octagon-19612",
            "CLOUD_ML_REGION": "us-central1",
        }
        runner._write_invocation_file(run_dir, invocations, env)
        path = os.path.join(run_dir, "invocation.txt")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        # Full argv + product version + leg recorded.
        self.assertIn("--dangerously-skip-permissions", text)
        self.assertIn("implement the draft flag", text)
        self.assertIn("claude 9.9.9 (Claude Code)", text)
        self.assertIn("leg: main", text)
        # Non-credential env kept for diagnosis.
        self.assertIn("us-central1", text)
        self.assertIn("vital-octagon-19612", text)
        # Credential-bearing values redacted (key stays, secret gone).
        self.assertIn("ANTHROPIC_API_KEY=<redacted>", text)
        self.assertIn("CLAUDE_CODE_OAUTH_TOKEN=<redacted>", text)
        self.assertNotIn("sk-secret-value-xyz", text)
        self.assertNotIn("oauth-secret-abc", text)

    def test_no_file_when_no_invocations(self) -> None:
        run_dir = tempfile.mkdtemp(prefix="lab-run-")
        runner._write_invocation_file(run_dir, [], {"ANY": "1"})
        self.assertFalse(os.path.exists(os.path.join(run_dir, "invocation.txt")))

    def test_records_exit_stdout_stderr_and_redacts_output_secrets(self) -> None:
        """Fix 2 extension: capture exit/stdout/stderr; a command that produced no
        output is itself the diagnosis. Secrets echoed into output are redacted."""
        run_dir = tempfile.mkdtemp(prefix="lab-run-")
        invocations = [{
            "leg": "main", "role": "solver", "product_version": "agy 1.1.4",
            "argv": ["agy", "--print", "do it"], "cwd": "/tmp/subject",
            "exit_code": 0,
            # Raw product JSON (usage block must survive for diagnosis) with a leaked
            # api key and a leaked env-sourced secret value mixed in.
            "stdout": '{"usage": {"input_tokens": 5}, "leaked": '
                      '"sk-secretkeyabcdefghijklmnop", "v": "TOPSECRETVALUE123"}',
            "stderr": "authenticated with Bearer ya29.fake-oauth-token-value",
        }]
        env = {"ANTHROPIC_API_KEY": "TOPSECRETVALUE123"}
        runner._write_invocation_file(run_dir, invocations, env)
        with open(os.path.join(run_dir, "invocation.txt"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("exit_code: 0", text)
        self.assertIn('"usage"', text)            # raw JSON body retained
        self.assertIn("input_tokens", text)
        self.assertNotIn("sk-secretkeyabcdefghijklmnop", text)  # pattern-redacted
        self.assertNotIn("TOPSECRETVALUE123", text)             # env-value-redacted
        self.assertNotIn("ya29.fake-oauth-token-value", text)   # oauth-redacted
        self.assertIn("Bearer <redacted>", text)                # prefix preserved

    def test_empty_output_is_recorded_as_diagnosis(self) -> None:
        """An invocation with empty stdout still writes the file with exit_code."""
        run_dir = tempfile.mkdtemp(prefix="lab-run-")
        invocations = [{
            "leg": "main", "role": "solver", "product_version": "agy 1.1.4",
            "argv": ["agy", "--print", "x"], "cwd": "/t",
            "exit_code": 0, "stdout": "", "stderr": "",
        }]
        runner._write_invocation_file(run_dir, invocations, {})
        with open(os.path.join(run_dir, "invocation.txt"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("exit_code: 0", text)
        self.assertIn("stdout:", text)

    def test_dry_run_produces_invocation_file(self) -> None:
        """End-to-end: a stub dry-run writes invocation.txt beside the summary."""
        rc, run_dir, _ = _run("P0")
        self.assertEqual(rc, 0)
        path = os.path.join(run_dir, "invocation.txt")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as fh:
            self.assertIn("argv:", fh.read())


if __name__ == "__main__":
    unittest.main()
