"""Scripted delegation (policy P2, family B3) — split contract + per-leg usage split.

No spend anywhere: the split file is loaded and hashed from disk, the per-model
usage split is exercised on SYNTHETIC ``modelUsage`` payloads shaped like the real
product JSON, and the runner path runs under ``--dry-run`` with the stub adapter.
Nothing here invokes ``claude -p``.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest

import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.adapters import claude_code as cc  # noqa: E402
from harness.adapters.base import (  # noqa: E402
    AttemptSpec,
    DelegatedLeg,
    DelegationPlan,
    ResolvedModel,
)
from harness.adapters.stub import StubAdapter  # noqa: E402
from harness.runner import delegation as dele  # noqa: E402
from harness.runner import run as runner  # noqa: E402
from harness.telemetry.telemetry import derive_summary  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
SYNTH_MANIFEST = str(ROOT / "tests" / "fixtures" / "manifest-SYNTHETIC.yaml")
REAL_MANIFEST = str(ROOT / "manifest" / "delivery-manifest.yaml")
PILOT_TASK = str(ROOT / "tasks" / "pilot-realworld")
W1_TASK = str(ROOT / "tasks" / "suite" / "W1-test-generation")

# SYNTHETIC per-model payloads keyed exactly as the product's JSON is (camelCase
# inside modelUsage, snake_case at the top level). Shape copied from a real batch-3
# invocation record; the NUMBERS are invented for this test.
SYNTH_CONDUCTOR = {
    "inputTokens": 900, "outputTokens": 2100, "cacheReadInputTokens": 50000,
    "cacheCreationInputTokens": 30000, "costUSD": 0.25,
    "canonicalModel": "claude-sonnet-4-6", "provider": "vertex",
}
SYNTH_EXECUTOR = {
    "inputTokens": 400, "outputTokens": 1500, "cacheReadInputTokens": 12000,
    "cacheCreationInputTokens": 4000, "costUSD": 0.03,
    "canonicalModel": "claude-haiku-4-5", "provider": "vertex",
}


def _payload(model_usage=None, **extra):
    """A SYNTHETIC ``claude -p --output-format json`` payload."""
    obj = {
        "usage": {"input_tokens": 1300, "output_tokens": 3600,
                  "cache_read_input_tokens": 62000, "cache_creation_input_tokens": 34000},
        "num_turns": 7, "is_error": False, "subtype": "success",
        "result": "SYNTHETIC result", "total_cost_usd": 0.28,
    }
    if model_usage is not None:
        obj["modelUsage"] = model_usage
    obj.update(extra)
    return obj


def _resolved(model_id: str) -> ResolvedModel:
    return ResolvedModel(
        product="Product A", product_surface="controlled_api", provider="google_vertex",
        model_or_selector=model_id, model_confidence="authoritative", model_id=model_id,
        region="global", cost_basis="marginal_api_cost",
    )


def _plan(conductor="claude-sonnet-4-6@default", executor="claude-haiku-4-5@20251001"):
    return DelegationPlan(
        legs=(DelegatedLeg("conductor", "conductor", _resolved(conductor)),
              DelegatedLeg("executor", "executor", _resolved(executor))),
        brief="\n--- SYNTHETIC BRIEF ---",
        agents_json='{"executor":{"model":"' + executor + '"}}',
        agent_name="executor",
        provenance={"split_file": "SYNTHETIC/split.yaml", "split_sha256": "SYNTHETIC"},
    )


def _spec(plan=None) -> AttemptSpec:
    return AttemptSpec("conductor", "conductor", _resolved("claude-sonnet-4-6@default"),
                       "SYNTHETIC prompt", cache_state="cold",
                       session_id="00000000-0000-4000-8000-000000000000",
                       delegation=plan)


def _collect():
    events = []

    def emit(event_type, **payload):
        events.append({"event_type": event_type, **payload})

    return events, emit


def _completed(events):
    return [e for e in events if e["event_type"] == "model_call_completed"]


class SplitFileContract(unittest.TestCase):
    """The pinned split file is the router; a malformed one is refused, not repaired."""

    def test_pilot_split_loads_and_declares_both_sides(self) -> None:
        split = dele.load_split(PILOT_TASK, repo_root=str(ROOT),
                                expected_task_id="pilot-realworld-draft-articles")
        self.assertTrue(split.executor_scopes)
        self.assertTrue(split.conductor_scopes)
        self.assertEqual(len(split.sha256), 64)
        for scope in split.executor_scopes:
            self.assertIn(scope.kind, dele.EXECUTOR_KINDS)
        for scope in split.conductor_scopes:
            self.assertIn(scope.kind, dele.CONDUCTOR_KINDS)

    def test_w1_split_respects_the_inverted_write_scope(self) -> None:
        # W1 is a test-generation task: target_paths are READ-ONLY and writes are
        # confined to agent_write_scope. A split that got this backwards would fail
        # the gate's diff-scope check on every run.
        task_yaml = yaml.safe_load(open(os.path.join(W1_TASK, "task.yaml"), encoding="utf-8"))
        split = dele.load_split(W1_TASK, repo_root=str(ROOT),
                                expected_task_id=task_yaml["task_id"])
        dele.validate_against_task(split, task_yaml)  # must not raise
        writable, read_only = dele.task_write_scope(task_yaml)
        self.assertTrue(read_only, "W1 should declare read-only product targets")
        for scope in split.scopes:
            if scope.writes:
                for path in scope.paths:
                    self.assertTrue(any(dele._matches(path, w) for w in writable), path)

    def test_writes_to_a_read_only_target_are_refused(self) -> None:
        task_yaml = yaml.safe_load(open(os.path.join(W1_TASK, "task.yaml"), encoding="utf-8"))
        split = dele.load_split(W1_TASK, repo_root=str(ROOT))
        bad = dele.Scope(side="executor", scope_id="X", kind="scaffold", step="s",
                         paths=(task_yaml["target_paths"][0],), writes=True)
        broken = dele.Split(path=split.path, rel_path=split.rel_path, sha256=split.sha256,
                            task_id=split.task_id, scopes=split.scopes + (bad,))
        with self.assertRaises(dele.SplitError):
            dele.validate_against_task(broken, task_yaml)

    def test_missing_split_file_is_refused_not_degraded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(dele.SplitError):
                dele.load_split(tmp, repo_root=str(ROOT))

    def test_structural_defects_are_refused(self) -> None:
        base = {
            "split_version": 1, "policy": "P2", "task_id": "t",
            "executor_scopes": [{"id": "E1", "kind": "scaffold", "step": "s",
                                 "paths": ["src/"], "writes": True}],
            "conductor_scopes": [{"id": "C1", "kind": "integration", "step": "s",
                                  "paths": ["src/"], "writes": True}],
        }
        cases = {
            "wrong version": {"split_version": 2},
            "wrong policy": {"policy": "P3"},
            "empty executor side": {"executor_scopes": []},
            "kind on wrong side": {"executor_scopes": [dict(base["executor_scopes"][0],
                                                            kind="integration")]},
            "writes not declared": {"conductor_scopes": [{"id": "C1", "kind": "integration",
                                                          "step": "s", "paths": ["src/"]}]},
            "no step": {"executor_scopes": [{"id": "E1", "kind": "scaffold",
                                             "paths": ["src/"], "writes": True}]},
        }
        for label, override in cases.items():
            with self.subTest(label):
                with tempfile.TemporaryDirectory() as tmp:
                    doc = {**base, **override}
                    with open(os.path.join(tmp, "split.yaml"), "w", encoding="utf-8") as fh:
                        yaml.safe_dump(doc, fh)
                    with self.assertRaises(dele.SplitError):
                        dele.load_split(tmp, repo_root=str(ROOT))

    def test_task_id_mismatch_is_refused(self) -> None:
        with self.assertRaises(dele.SplitError):
            dele.load_split(PILOT_TASK, repo_root=str(ROOT), expected_task_id="some-other-task")

    def test_hash_is_over_raw_bytes_including_comments(self) -> None:
        split = dele.load_split(PILOT_TASK, repo_root=str(ROOT))
        raw = open(split.path, "rb").read()
        import hashlib
        self.assertEqual(split.sha256, hashlib.sha256(raw).hexdigest())


class ManifestPin(unittest.TestCase):
    """SPEC 2.1c: P2's manifest pin is the split-file hash, per task."""

    def _pin_case(self, task_dir: str, manifest_key: str) -> None:
        manifest = yaml.safe_load(open(REAL_MANIFEST, encoding="utf-8"))
        split = dele.load_split(task_dir, repo_root=str(ROOT))
        # The pin on disk must match the file on disk (this fails loudly if a split
        # is edited without re-pinning — exactly what the pin exists to catch).
        dele.check_pin(split, manifest, manifest_key, require_frozen=False)

    def test_pilot_split_matches_its_manifest_pin(self) -> None:
        self._pin_case(PILOT_TASK, "pilot_task")

    def test_w1_split_matches_its_manifest_pin(self) -> None:
        self._pin_case(W1_TASK, "w1_task")

    def test_altered_split_fails_the_pin(self) -> None:
        manifest = yaml.safe_load(open(REAL_MANIFEST, encoding="utf-8"))
        split = dele.load_split(PILOT_TASK, repo_root=str(ROOT))
        tampered = dele.Split(path=split.path, rel_path=split.rel_path,
                              sha256="0" * 64, task_id=split.task_id, scopes=split.scopes)
        with self.assertRaises(dele.SplitError):
            dele.check_pin(tampered, manifest, "pilot_task", require_frozen=False)

    def test_both_splits_are_frozen_and_live_runnable(self) -> None:
        """Human FREEZE APPROVED 2026-08-16 for both reference splits."""
        manifest = yaml.safe_load(open(REAL_MANIFEST, encoding="utf-8"))
        for task_dir, key in ((PILOT_TASK, "pilot_task"), (W1_TASK, "w1_task")):
            with self.subTest(task=key):
                pin = manifest[key]["delegation_split"]
                self.assertEqual(pin["status"], "frozen")
                split = dele.load_split(task_dir, repo_root=str(ROOT))
                dele.check_pin(split, manifest, key, require_frozen=True)  # must not raise

    def test_live_run_requires_a_frozen_pin(self) -> None:
        """A draft split is dry-runnable but never live-runnable."""
        manifest = yaml.safe_load(open(REAL_MANIFEST, encoding="utf-8"))
        manifest["pilot_task"]["delegation_split"]["status"] = "proposed"
        split = dele.load_split(PILOT_TASK, repo_root=str(ROOT))
        dele.check_pin(split, manifest, "pilot_task", require_frozen=False)  # dry run: ok
        with self.assertRaises(dele.SplitError):
            dele.check_pin(split, manifest, "pilot_task", require_frozen=True)


class BriefAndAgentBinding(unittest.TestCase):
    def test_brief_is_deterministic_and_names_every_scope(self) -> None:
        split = dele.load_split(PILOT_TASK, repo_root=str(ROOT))
        brief = dele.render_brief(split, executor_agent="executor")
        self.assertEqual(brief, dele.render_brief(split, executor_agent="executor"))
        for scope in split.scopes:
            self.assertIn(scope.step.split("\n")[0][:40], brief)
        self.assertIn(split.sha256, brief)

    def test_brief_never_asks_the_model_to_report_usage(self) -> None:
        split = dele.load_split(PILOT_TASK, repo_root=str(ROOT))
        text = dele.render_brief(split, executor_agent="executor").lower()
        for banned in ("token", "cost", "usage", "how much did"):
            self.assertNotIn(banned, text, f"brief must not solicit self-reported {banned}")

    def test_agents_json_binds_the_executor_model(self) -> None:
        split = dele.load_split(PILOT_TASK, repo_root=str(ROOT))
        raw = dele.executor_agent_json(split, agent_name="executor", model_id="ECON-X")
        defn = json.loads(raw)
        self.assertEqual(defn["executor"]["model"], "ECON-X")
        self.assertEqual(raw, dele.executor_agent_json(split, agent_name="executor",
                                                       model_id="ECON-X"))


class ModelUsageSplit(unittest.TestCase):
    """Per-leg usage comes from the product's own modelUsage metadata (authoritative)."""

    def test_splits_per_model_and_keeps_missing_classes_unavailable(self) -> None:
        mu = {"claude-sonnet-4-6@20260130": SYNTH_CONDUCTOR,
              "claude-haiku-4-5@20251001": dict(SYNTH_EXECUTOR, cacheReadInputTokens=None)}
        split = cc.split_usage_by_model(_payload(mu))
        self.assertEqual(set(split), set(mu))
        strong = split["claude-sonnet-4-6@20260130"]
        self.assertEqual(strong["input_tokens"], {"value": 900, "confidence": "authoritative"})
        self.assertEqual(strong["output_tokens"]["value"], 2100)
        econ = split["claude-haiku-4-5@20251001"]
        self.assertEqual(econ["cache_read_tokens"]["confidence"], "unavailable")
        self.assertIsNone(econ["cache_read_tokens"]["value"])  # never zero-filled

    def test_absent_modelusage_is_empty_not_invented(self) -> None:
        self.assertEqual(cc.split_usage_by_model(_payload()), {})

    def test_single_model_parsing_is_unchanged(self) -> None:
        usage = cc.usage_from_claude_json(_payload())
        self.assertEqual(usage["input_tokens"]["value"], 1300)
        self.assertEqual(usage["cache_creation_tokens"]["value"], 34000)
        self.assertEqual(usage["reasoning_tokens"]["confidence"], "unavailable")

    def test_command_has_no_agents_flag_without_delegation(self) -> None:
        cmd = cc.build_command("p", "m", session_id="s")
        self.assertNotIn("--agents", cmd)
        self.assertIn("--agents", cc.build_command("p", "m", agents_json='{"executor":{}}'))


class DelegatedEmission(unittest.TestCase):
    """``_emit_delegated_usage`` is the adapter's internal splitter — pure, no spend."""

    def _run_fields(self, payload):
        return {"requested_selector": "claude-sonnet-4-6@default",
                "resolved_model_version": "claude-sonnet-4-6@20260130",
                "num_turns": payload.get("num_turns"),
                "product_reported_cost_usd": payload.get("total_cost_usd")}

    def test_two_legs_with_distinct_models_and_own_usage(self) -> None:
        payload = _payload({"claude-sonnet-4-6@20260130": SYNTH_CONDUCTOR,
                            "claude-haiku-4-5@20251001": SYNTH_EXECUTOR})
        events, emit = _collect()
        plan = _plan()
        cc._emit_delegated_usage(emit, _spec(plan), payload, self._run_fields(payload))

        done = _completed(events)
        self.assertEqual([e["leg"] for e in done], ["conductor", "executor"])
        models = [e["model_or_selector"]["value"] for e in done]
        self.assertEqual(models, ["claude-sonnet-4-6@default", "claude-haiku-4-5@20251001"])
        self.assertEqual(len(set(models)), 2)
        # Each leg carries the usage of ITS model, not the run total.
        self.assertEqual(done[0]["usage"]["output_tokens"]["value"], 2100)
        self.assertEqual(done[1]["usage"]["output_tokens"]["value"], 1500)
        # The metered concrete version is recorded beside the priced manifest id.
        self.assertEqual(done[1]["resolved_model_version"], "claude-haiku-4-5@20251001")
        self.assertEqual(done[1]["model_reported_cost_usd"], 0.03)
        # Run-level diagnostics belong to the invocation, so they sit on the
        # conductor's event only — duplicating them would double-count turns.
        self.assertEqual(done[0]["num_turns"], 7)
        self.assertNotIn("num_turns", done[1])
        self.assertEqual(done[0]["split_sha256"], "SYNTHETIC")

    def test_floating_alias_matches_the_concrete_metered_version(self) -> None:
        payload = _payload({"claude-sonnet-4-6@20260130": SYNTH_CONDUCTOR})
        events, emit = _collect()
        cc._emit_delegated_usage(emit, _spec(_plan()), payload, self._run_fields(payload))
        conductor = _completed(events)[0]
        self.assertEqual(conductor["leg"], "conductor")
        self.assertEqual(conductor["usage"]["input_tokens"]["value"], 900)

    def test_missing_modelusage_is_unattributed_never_divided(self) -> None:
        payload = _payload()
        events, emit = _collect()
        cc._emit_delegated_usage(emit, _spec(_plan()), payload, self._run_fields(payload))

        done = _completed(events)
        self.assertEqual([e["leg"] for e in done], ["conductor", "executor"])
        self.assertEqual(done[0]["usage"]["input_tokens"]["value"], 1300)  # the run total
        self.assertEqual(done[0]["delegation_attribution"], "unavailable")
        self.assertEqual(done[1]["usage"]["input_tokens"]["confidence"], "unavailable")
        self.assertIsNone(done[1]["usage"]["input_tokens"]["value"])
        cats = [e.get("category") for e in events if e["event_type"] == "failure"]
        self.assertIn("delegation_attribution_unavailable", cats)

    def test_declared_but_unmetered_leg_is_flagged_not_zeroed(self) -> None:
        payload = _payload({"claude-sonnet-4-6@20260130": SYNTH_CONDUCTOR})
        events, emit = _collect()
        cc._emit_delegated_usage(emit, _spec(_plan()), payload, self._run_fields(payload))
        executor = _completed(events)[1]
        self.assertEqual(executor["leg"], "executor")
        self.assertEqual(executor["usage"]["output_tokens"]["confidence"], "unavailable")
        cats = [e.get("category") for e in events if e["event_type"] == "failure"]
        self.assertIn("delegation_leg_unmetered", cats)

    def test_unmatched_metered_model_gets_its_own_unattributed_leg(self) -> None:
        payload = _payload({"claude-sonnet-4-6@20260130": SYNTH_CONDUCTOR,
                            "claude-haiku-4-5@20251001": SYNTH_EXECUTOR,
                            "some-other-model@1": dict(SYNTH_EXECUTOR, inputTokens=11)})
        events, emit = _collect()
        cc._emit_delegated_usage(emit, _spec(_plan()), payload, self._run_fields(payload))
        extra = [e for e in _completed(events) if e["role"] == "unattributed"]
        self.assertEqual(len(extra), 1)
        self.assertEqual(extra[0]["cost_basis"], "cost_unavailable")
        self.assertEqual(extra[0]["usage"]["input_tokens"]["value"], 11)
        self.assertEqual(extra[0]["provider"]["confidence"], "unavailable")

    def test_lost_telemetry_accounts_for_every_declared_leg(self) -> None:
        events, emit = _collect()
        cc._emit_lost_usage(emit, _spec(_plan()), "SYNTHETIC loss")
        done = _completed(events)
        self.assertEqual([e["leg"] for e in done], ["conductor", "executor"])
        for e in done:
            self.assertEqual(e["usage"]["input_tokens"]["confidence"], "unavailable")

    def test_lost_telemetry_without_delegation_is_one_leg(self) -> None:
        events, emit = _collect()
        cc._emit_lost_usage(emit, _spec(), "SYNTHETIC loss")
        self.assertEqual([e["leg"] for e in _completed(events)], ["conductor"])


class RunnerIntegration(unittest.TestCase):
    def _manifest(self):
        """Synthetic manifest + the real split's hash, pinned as a draft."""
        manifest = yaml.safe_load(open(SYNTH_MANIFEST, encoding="utf-8"))
        split = dele.load_split(PILOT_TASK, repo_root=str(ROOT))
        manifest["pilot_task"]["delegation_split"] = {
            "path": split.rel_path, "sha256": f"sha256:{split.sha256}", "status": "proposed",
        }
        return manifest

    def test_plan_has_two_legs_bound_to_different_models(self) -> None:
        manifest = self._manifest()
        task = runner.load_task("tasks/pilot-realworld", manifest)
        plan = runner.build_plan("P2", manifest, task=task, require_frozen=False)
        self.assertEqual(plan.policy, "scripted_delegation")
        self.assertEqual([leg.leg_id for leg in plan.legs], ["conductor", "executor"])
        self.assertNotEqual(plan.legs[0].resolved.model_id, plan.legs[1].resolved.model_id)
        self.assertIn(plan.legs[1].resolved.model_id, plan.delegation.agents_json)
        self.assertIn("SCRIPTED DELEGATION", plan.delegation.brief)

    def test_live_run_refuses_an_unfrozen_split(self) -> None:
        manifest = self._manifest()
        task = runner.load_task("tasks/pilot-realworld", manifest)
        with self.assertRaises(runner.RunnerError):
            runner.build_plan("P2", manifest, task=task, require_frozen=True)

    def test_dry_run_emits_two_legs_with_distinct_models(self) -> None:
        manifest = self._manifest()
        task = runner.load_task("tasks/pilot-realworld", manifest)
        plan = runner.build_plan("P2", manifest, task=task, require_frozen=False)
        events, emit = _collect()
        with tempfile.TemporaryDirectory() as run_dir:
            identity, leg_options, _ = runner.execute(
                plan, task, StubAdapter(), "", run_dir, emit,
                dry_run=True, scenario="accept", cache_state="cold",
                base_session="00000000-0000-4000-8000-000000000000", resume=False,
            )
        self.assertEqual(set(leg_options), {"conductor", "executor"})
        summary = derive_summary(
            events, run_id="SYNTHETIC", task_id=task.task_id,
            task_suite_version=task.task_suite_version, configuration_id="P0",
            manifest_ref="SYNTHETIC", identity=identity,
            economics={"cost_basis": "marginal_api_cost"},
        )
        legs = {leg["leg_id"]: leg for leg in summary["legs"]}
        self.assertEqual(set(legs), {"conductor", "executor"})
        self.assertNotEqual(legs["conductor"]["model_or_selector"]["value"],
                            legs["executor"]["model_or_selector"]["value"])
        for leg in legs.values():
            self.assertIsNotNone(leg["usage"]["output_tokens"]["value"])
        # ONE product invocation, so the cache contract still sees one fresh session.
        self.assertEqual(runner.assert_cache_contract(events, "cold"), [])

    def test_p2_is_recordable_by_the_telemetry_schema(self) -> None:
        # CP-SCHEMA 2026-08-16 widened configuration_id additively; a P2 run now
        # records as a valid summary instead of validating only at the end.
        self.assertIn("P2", runner.schema_configuration_ids())

    def test_cli_dry_run_under_p2_writes_a_valid_summary(self) -> None:
        """End-to-end through main(): plan -> stub attempt -> derived summary -> validate."""
        manifest = self._manifest()
        manifest["pilot_task"]["delegation_split"]["status"] = "frozen"
        out_root = tempfile.mkdtemp(prefix="lab-p2-")
        manifest_path = os.path.join(out_root, "manifest-SYNTHETIC.yaml")
        with open(manifest_path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(manifest, fh)
        os.environ.pop("LAB_ALLOW_SPEND", None)
        rc = runner.main(["--task", "tasks/pilot-realworld", "--config", "P2", "--dry-run",
                          "--cache-state", "cold", "--manifest", manifest_path,
                          "--out-root", out_root])
        self.assertEqual(rc, 0, "P2 dry run must produce an audit-grade summary")
        runs = [d for d in os.listdir(out_root) if "__P2__" in d]
        self.assertEqual(len(runs), 1)
        with open(os.path.join(out_root, runs[0], "summary.json"), encoding="utf-8") as fh:
            summary = json.load(fh)
        self.assertEqual(summary["configuration_id"], "P2")
        legs = {leg["leg_id"]: leg for leg in summary["legs"]}
        self.assertEqual(set(legs), {"conductor", "executor"})
        self.assertNotEqual(legs["conductor"]["model_or_selector"]["value"],
                            legs["executor"]["model_or_selector"]["value"])


if __name__ == "__main__":
    unittest.main()
