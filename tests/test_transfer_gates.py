"""Gate logic for the three transplanted arms, from SYNTHETIC public reports.

Every case here drives ``classify`` + ``gate_decision`` + ``next_step`` from
``tests/fixtures/transfer-gate-reports-SYNTHETIC.json`` — hand-written reports,
never run output (CLAUDE.md rule 1).

The test this file exists for is
:meth:`FluentButWrong.test_r9_does_not_escalate_on_a_fluent_but_wrong_answer`.
The prereg predicts transfer BREAKS on W6 because a review can be fluent,
in-scope, well-formed and *locationally wrong*: the sealed grader rejects it and
the public report — the only thing an evidence gate may read — shows nothing at
all. r9 must therefore decline to escalate and burn three cheap rungs. That is
not a bug being pinned, it is the registered mechanism; a change that makes this
case escalate has replaced r9 with a different strategy.
"""

import json
import os
import unittest

from harness.adapters.transfer_base import LadderState, next_step, routing_payload
from harness.adapters.transfer_spec import (
    Difficulty,
    classify,
    gate_decision,
    gate_is_degraded,
    load_spec,
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FIXTURE = os.path.join(ROOT, "tests", "fixtures",
                       "transfer-gate-reports-SYNTHETIC.json")


def scenarios():
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)["scenarios"]


SCENARIOS = scenarios()


def report(name: str):
    return SCENARIOS[name]["report"]


class FixtureHygiene(unittest.TestCase):
    def test_the_fixture_says_it_is_synthetic(self) -> None:
        with open(FIXTURE, encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertIn("SYNTHETIC", doc["_SYNTHETIC"])
        self.assertIn("SYNTHETIC", os.path.basename(FIXTURE))

    def test_every_scenario_says_why_it_exists(self) -> None:
        for name, sc in SCENARIOS.items():
            self.assertTrue(sc.get("_why", "").strip(),
                            f"{name} has no _why: a fixture nobody can explain is a "
                            f"fixture nobody can maintain")


class Classification(unittest.TestCase):
    """``classify`` against each fixture, for the spec whose map it uses."""

    def setUp(self) -> None:
        self.r9 = load_spec("r9")

    def test_all_public_checks_pass_is_typed_shallow_not_hard(self) -> None:
        d = classify(report("fluent_but_locationally_wrong"), self.r9)
        self.assertEqual(d.level, "shallow")
        self.assertTrue(d.typed)
        self.assertFalse(d.is_hard)
        self.assertEqual(d.failing, 0)

    def test_empty_check_list_is_typed_shallow_not_untyped(self) -> None:
        d = classify(report("no_failing_checks_but_rejected"), self.r9)
        self.assertEqual(d.level, "shallow")
        self.assertTrue(d.typed, "an empty census is a fact, not missing evidence")

    def test_absent_report_is_untyped(self) -> None:
        d = classify(None, self.r9)
        self.assertEqual(d.level, "shallow")
        self.assertFalse(d.typed)

    def test_shallow_classes_stay_shallow(self) -> None:
        self.assertEqual(classify(report("shallow_typecheck_only"), self.r9).level,
                         "shallow")

    def test_two_behavioural_failures_are_local(self) -> None:
        d = classify(report("local_two_behavioural"), self.r9)
        self.assertEqual(d.level, "local")
        self.assertEqual(d.failing, 2)
        self.assertFalse(d.is_hard)

    def test_three_behavioural_failures_are_broad(self) -> None:
        d = classify(report("broad_three_behavioural"), self.r9)
        self.assertEqual(d.level, "broad")
        self.assertEqual(d.failing, 3)
        self.assertTrue(d.is_hard)

    def test_environment_short_circuits_everything(self) -> None:
        d = classify(report("environment_guard"), self.r9)
        self.assertEqual(d.level, "environment")
        self.assertTrue(d.is_environment)
        self.assertEqual(d.guard, "G0-subject-readable")

    def test_malformed_only_is_the_guard_branch_and_is_shallow(self) -> None:
        d = classify(report("malformed_guard"), self.r9)
        self.assertEqual(d.level, "shallow")
        self.assertIn("not a usable artefact", " ".join(d.reasons))

    def test_identical_failing_set_after_a_repair_turn_is_a_stall(self) -> None:
        first = classify(report("local_two_behavioural"), self.r9)
        again = classify(report("local_two_behavioural"), self.r9, previous=first)
        self.assertEqual(again.level, "stalled")
        self.assertTrue(again.is_hard)


class FluentButWrong(unittest.TestCase):
    """The registered mechanism, asserted directly."""

    def test_r9_does_not_escalate_on_a_fluent_but_wrong_answer(self) -> None:
        spec = load_spec("r9")
        d = classify(report("fluent_but_locationally_wrong"), spec)
        for attempt in (1, 2):
            escalate, why = gate_decision(spec, d, attempt)
            self.assertFalse(
                escalate,
                f"attempt {attempt}: r9's evidence gate escalated on a report with no "
                f"failing checks. The gate READS evidence; there is none here, and the "
                f"prereg registers that r9 therefore cannot see this failure. why={why!r}",
            )
            self.assertIn("keep it cheap", why)

    def test_the_ladder_spends_every_cheap_rung_and_then_escalates(self) -> None:
        """r9 is not stuck — it exhausts the cheap rungs, then takes the frontier.

        Pins the full trajectory so "does not escalate" cannot be misread as
        "never escalates". The frontier arrives at attempt 3 of 3, i.e. after the
        arm has already paid for the rungs that could not see the problem.
        """
        spec = load_spec("r9")
        d = classify(report("fluent_but_locationally_wrong"), spec)
        state = LadderState()
        legs = []
        for _ in range(4):
            step, decision = next_step(spec, state, d)
            if step is None:
                legs.append(("stop", decision["stop_reason"]))
                break
            legs.append((step.leg_id, step.is_frontier))
            state = LadderState(attempt=step.attempt,
                                frontier_calls=state.frontier_calls + int(step.is_frontier),
                                degraded=state.degraded, previous=d)
        self.assertEqual([is_f for _, is_f in legs[:3]], [False, False, True],
                         f"expected two cheap rungs then the frontier, got {legs}")

    def test_r6_reaches_the_same_answer_by_counting_instead_of_reading(self) -> None:
        """Same report, r6's counting gate: identical shape, different reason.

        Worth pinning because it is the probe's whole gradient-of-trust claim —
        on evidence this thin, the arm that reads and the arm that counts are
        indistinguishable in behaviour and distinguishable only in ``why``.
        """
        spec = load_spec("r6")
        d = classify(report("fluent_but_locationally_wrong"), spec)
        self.assertEqual([gate_decision(spec, d, a) for a in (1, 2, 3)],
                         [(False, "cheap rungs remain (1/3)"),
                          (False, "cheap rungs remain (2/3)"),
                          (True, "all 3 cheap rungs exhausted")])


class EvidenceGateVsCountingGate(unittest.TestCase):
    def test_broad_evidence_escalates_r9_at_the_first_gate(self) -> None:
        spec = load_spec("r9")
        d = classify(report("broad_three_behavioural"), spec)
        escalate, why = gate_decision(spec, d, 1)
        self.assertTrue(escalate)
        self.assertIn("evidence says broad", why)

    def test_the_same_evidence_does_not_move_r6(self) -> None:
        spec = load_spec("r6")
        d = classify(report("broad_three_behavioural"), spec)
        self.assertEqual(gate_decision(spec, d, 1), (False, "cheap rungs remain (1/3)"))

    def test_environment_blocks_both_kinds_of_gate(self) -> None:
        for sid in ("r9", "r6", "r10"):
            spec = load_spec(sid)
            d = classify(report("environment_guard"), spec)
            escalate, why = gate_decision(spec, d, spec.total_rungs)
            self.assertFalse(escalate, f"{sid} escalated on an environment failure")
            self.assertIn("no model fixes this", why)

    def test_r9_degrades_when_it_has_no_typed_evidence(self) -> None:
        spec = load_spec("r9")
        self.assertTrue(gate_is_degraded(spec, classify(None, spec)))
        self.assertFalse(gate_is_degraded(spec, classify(report("malformed_guard"), spec)))

    def test_a_counting_gate_never_degrades(self) -> None:
        """r6/r10 declare no typed-evidence requirement, so there is nothing to degrade."""
        for sid in ("r6", "r10"):
            spec = load_spec(sid)
            self.assertFalse(gate_is_degraded(spec, classify(None, spec)))


class LadderArithmetic(unittest.TestCase):
    """The two source behaviours a rewrite loses (transfer_base.next_step)."""

    def test_escalation_consumes_a_rung_slot(self) -> None:
        spec = load_spec("r9")
        hard = classify(report("broad_three_behavioural"), spec)
        step, _ = next_step(spec, LadderState(attempt=0), hard)
        self.assertTrue(step.is_frontier)
        self.assertEqual(step.attempt, 1,
                         "the frontier REPLACED rung 1; it was not appended after it")

    def test_a_spent_frontier_budget_falls_back_to_a_cheap_rung(self) -> None:
        spec = load_spec("r9")
        hard = classify(report("broad_three_behavioural"), spec)
        state = LadderState(attempt=1, frontier_calls=spec.frontier_max_calls)
        step, decision = next_step(spec, state, hard)
        self.assertFalse(step.is_frontier)
        self.assertTrue(decision["gate_escalate"],
                        "the gate wanted the frontier and must be recorded as having "
                        "wanted it, separately from what it got")
        self.assertTrue(decision["frontier_budget_spent"])
        self.assertIn("frontier budget spent", decision["why"])

    def test_the_ladder_stops_when_cheap_rungs_run_out_and_the_gate_says_no(self) -> None:
        spec = load_spec("r9")
        d = classify(report("shallow_typecheck_only"), spec)
        state = LadderState(attempt=spec.total_rungs,
                            frontier_calls=spec.frontier_max_calls)
        step, decision = next_step(spec, state, d)
        self.assertIsNone(step)
        self.assertIn("cheap rungs exhausted", decision["stop_reason"])

    def test_r10_discards_the_artefact_at_the_frontier_turn(self) -> None:
        self.assertTrue(load_spec("r10").discards_failed_artefact)
        self.assertFalse(load_spec("r9").discards_failed_artefact)
        self.assertFalse(load_spec("r6").discards_failed_artefact)


class RoutingEvidence(unittest.TestCase):
    """A routing event must carry the gate's INPUT verbatim, not a level label."""

    def test_the_payload_carries_the_failing_checks_verbatim(self) -> None:
        spec = load_spec("r9")
        rep = report("broad_three_behavioural")
        d = classify(rep, spec)
        _, decision = next_step(spec, LadderState(), d)
        payload = routing_payload(spec, decision, d, rep, degraded=False)
        ids = [c["id"] for c in payload["evidence"]]
        self.assertEqual(ids, ["P1-public-test", "P2-regression", "T2-suite-green"])
        details = [c["detail"] for c in payload["evidence"]]
        self.assertEqual(details, ["3 failing", "2 failing", "suite red"],
                         "detail strings must be unedited — a reader has to be able to "
                         "second-guess the gate from the event alone")
        self.assertEqual(payload["evidence_source"], "gate-public.json")
        self.assertEqual(payload["spec_sha256"], spec.spec_sha256)

    def test_passing_checks_are_not_in_the_evidence(self) -> None:
        spec = load_spec("r9")
        rep = report("fluent_but_locationally_wrong")
        d = classify(rep, spec)
        _, decision = next_step(spec, LadderState(), d)
        payload = routing_payload(spec, decision, d, rep, degraded=False)
        self.assertEqual(payload["evidence"], [],
                         "an empty evidence list is the honest record of what r9 saw")

    def test_the_calibration_path_may_override_the_source_but_not_omit_it(self) -> None:
        spec = load_spec("r9")
        d = Difficulty(level="broad", failing=3, typed=True)
        _, decision = next_step(spec, LadderState(), d)
        payload = routing_payload(spec, decision, d, None,
                                  degraded=False,
                                  evidence_source="unittest_stderr",
                                  evidence={"text": "AssertionError: 3 != 4"})
        self.assertEqual(payload["evidence_source"], "unittest_stderr")
        self.assertEqual(payload["evidence"], {"text": "AssertionError: 3 != 4"})

    def test_a_degraded_run_is_stamped_degraded(self) -> None:
        spec = load_spec("r9")
        d = classify(None, spec)
        _, decision = next_step(spec, LadderState(), d)
        payload = routing_payload(spec, decision, d, None, degraded=True)
        self.assertTrue(payload["degraded"])


if __name__ == "__main__":
    unittest.main()
