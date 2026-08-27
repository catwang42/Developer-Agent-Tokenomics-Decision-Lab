"""Driver profiles: the batch-1 pins, the probe re-pin, and overrun stamping.

Two things are being protected here, and they pull in opposite directions.

  1. **Batch-1 must not move.** Every published dataset ran under a contract
     where ``agent_timeout_s`` was the kill and Product B's ``--print-timeout``
     came flat from the manifest. Re-timing an arm silently is how two batches
     stop being comparable, so the ``batch1`` profile is asserted to resolve to
     exactly that, and the soft-budget code path is asserted never to be entered
     when no budget is set.
  2. **The probe profile must actually run to completion.** Its whole reason to
     exist is that a cost-of-failure number taken from a truncated attempt
     reports the budget instead of the bill. So: soft budget = the task's
     ``agent_timeout_s``, hard kill = 3x, ``--print-timeout`` re-pinned per task,
     and the crossing recorded as ``overrun_flag``/``overrun_s`` on an EXISTING
     event type (the vocabulary is frozen under CP-SCHEMA).
"""

import os
import subprocess
import sys
import unittest

from harness.adapters.agy import print_timeout_seconds
from harness.adapters.base import AttemptSpec, ResolvedModel, overrun_payload
from harness.container.exec import spawn_with_timeout
from harness.runner import profiles as P


def _spec(budget_s=None) -> AttemptSpec:
    resolved = ResolvedModel(
        provider="SYNTHETIC", model_or_selector="STRONG_MODEL_A",
        model_id="SYNTHETIC-model", cost_basis="marginal_api_cost",
        product="Product A", product_surface="controlled_api",
    )
    return AttemptSpec(leg_id="rung_1", role="economical", resolved=resolved,
                       prompt="x", budget_s=budget_s)


class _Proc:
    def __init__(self, elapsed_s=None, overran=False):
        if elapsed_s is not None:
            self.elapsed_s = elapsed_s
        self.overran = overran


class GoDurations(unittest.TestCase):
    def test_round_trips_through_the_agy_parser(self) -> None:
        for seconds in (60, 900, 1200, 2700, 3600, 7200, 8100):
            self.assertEqual(print_timeout_seconds(P.go_duration(seconds)), seconds,
                             f"{seconds}s does not round-trip")

    def test_the_registered_task_budgets_render_as_expected(self) -> None:
        self.assertEqual(P.go_duration(1200), "20m0s")
        self.assertEqual(P.go_duration(2700), "45m0s")
        self.assertEqual(P.go_duration(3600), "1h0m0s")

    def test_it_refuses_anything_that_is_not_a_positive_int(self) -> None:
        for bad in (0, -1, 1.5, True, "600", None):
            with self.assertRaises(ValueError):
                P.go_duration(bad)  # type: ignore[arg-type]


class Batch1IsUnchanged(unittest.TestCase):
    def test_it_is_still_the_default(self) -> None:
        self.assertEqual(P.DEFAULT_PROFILE, "batch1")
        self.assertIs(P.get_profile(None), P.BATCH1)

    def test_the_budget_is_the_kill_and_there_is_no_soft_line(self) -> None:
        for seconds in (1200, 2700, 7200):
            t = P.BATCH1.timeouts(seconds, manifest_print_timeout="15m0s")
            self.assertEqual(t.kill_s, seconds)
            self.assertIsNone(t.budget_s)

    def test_print_timeout_comes_from_the_manifest_verbatim(self) -> None:
        t = P.BATCH1.timeouts(2700, manifest_print_timeout="15m0s")
        self.assertEqual(t.print_timeout, "15m0s",
                         "batch-1's flat pin is a recorded limitation, not a bug to fix "
                         "retroactively on a published dataset")

    def test_no_soft_budget_means_no_overrun_stamp_at_all(self) -> None:
        self.assertEqual(overrun_payload(_spec(budget_s=None), _Proc(elapsed_s=99.0)), {},
                         "a batch-1 run must derive byte-identically to one recorded "
                         "before soft budgets existed")


class TransferProbeProfile(unittest.TestCase):
    def test_the_soft_budget_is_the_tasks_own_agent_timeout(self) -> None:
        for seconds in (1200, 2700):
            t = P.TRANSFER_PROBE.timeouts(seconds)
            self.assertEqual(t.budget_s, seconds)

    def test_the_hard_kill_is_three_times_the_budget(self) -> None:
        self.assertEqual(P.TRANSFER_PROBE.timeouts(1200).kill_s, 3600)
        self.assertEqual(P.TRANSFER_PROBE.timeouts(2700).kill_s, 8100)

    def test_print_timeout_is_repinned_per_task(self) -> None:
        """Timeout parity: the flat 15m0s pin gave a 2700s task only 900s."""
        t = P.TRANSFER_PROBE.timeouts(2700, manifest_print_timeout="15m0s")
        self.assertEqual(t.print_timeout, "45m0s")
        self.assertEqual(print_timeout_seconds(t.print_timeout), 2700)

    def test_the_products_own_timeout_still_fires_before_ours(self) -> None:
        for seconds in (1200, 2700, 7200):
            t = P.TRANSFER_PROBE.timeouts(seconds)
            self.assertLess(print_timeout_seconds(t.print_timeout), t.kill_s)

    def test_a_budget_above_the_kill_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            P.LegTimeouts(budget_s=1000, kill_s=500, print_timeout=None)

    def test_unknown_profile_names_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            P.get_profile("transfer_probe")  # underscore, not the registered name


class OverrunStamping(unittest.TestCase):
    def test_inside_the_budget_records_the_budget_and_no_overrun(self) -> None:
        payload = overrun_payload(_spec(budget_s=1200), _Proc(elapsed_s=900.0))
        self.assertEqual(payload["budget_s"], 1200)
        self.assertEqual(payload["elapsed_s"], 900.0)
        self.assertFalse(payload["overrun_flag"])
        self.assertEqual(payload["overrun_s"], 0.0)

    def test_past_the_budget_records_how_far_past(self) -> None:
        payload = overrun_payload(_spec(budget_s=1200), _Proc(elapsed_s=1503.4))
        self.assertTrue(payload["overrun_flag"])
        self.assertEqual(payload["overrun_s"], 303.4)

    def test_an_unmeasured_duration_is_unavailable_never_the_budget(self) -> None:
        payload = overrun_payload(_spec(budget_s=1200), _Proc(elapsed_s=None, overran=True))
        self.assertNotIsInstance(payload["elapsed_s"], (int, float))
        self.assertTrue(payload["overrun_flag"])
        self.assertNotIn("overrun_s", payload,
                         "an overrun distance cannot be derived from a duration we "
                         "do not have (CLAUDE.md rule 3)")


class SpawnSoftBudget(unittest.TestCase):
    """The seam itself: crossing the soft line must NOT stop the child."""

    def test_the_child_survives_the_soft_budget_and_the_crossing_is_reported(self) -> None:
        seen = []
        result = spawn_with_timeout(
            [sys.executable, "-c",
             "import time,sys; time.sleep(1.0); sys.stdout.write('finished')"],
            cwd=None, env=os.environ.copy(), timeout_s=30.0, budget_s=0.3,
            on_overrun=seen.append,
        )
        self.assertEqual(result.stdout, "finished",
                         "the attempt was cut off at the soft budget; the probe would "
                         "then be measuring the budget instead of the bill")
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertTrue(result.overran)
        self.assertEqual(seen, [0.3], "the overrun warning must fire exactly once")

    def test_the_hard_kill_still_kills(self) -> None:
        result = spawn_with_timeout(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=None, env=os.environ.copy(), timeout_s=1.0, budget_s=0.3,
        )
        self.assertTrue(result.timed_out)
        self.assertTrue(result.overran)
        self.assertIsNone(result.returncode)

    def test_without_a_budget_the_original_single_timeout_path_is_taken(self) -> None:
        seen = []
        result = spawn_with_timeout(
            [sys.executable, "-c", "import sys; sys.stdout.write('ok')"],
            cwd=None, env=os.environ.copy(), timeout_s=30.0, budget_s=None,
            on_overrun=seen.append,
        )
        self.assertEqual(result.stdout, "ok")
        self.assertFalse(result.overran)
        self.assertEqual(seen, [])


class DatasetMarker(unittest.TestCase):
    def test_a_non_default_profile_marker_shouts_new_arm_condition(self) -> None:
        text = P.dataset_marker(P.TRANSFER_PROBE, dataset="results/transfer-probe",
                                tasks={"w4b-zarr-consolidated-order": 2700})
        self.assertIn("NEW ARM CONDITION", text)
        self.assertIn("Do not pool them", text)
        self.assertIn("results/transfer-probe", text)

    def test_it_states_the_resolved_numbers_not_the_rule(self) -> None:
        text = P.dataset_marker(P.TRANSFER_PROBE, dataset="results/transfer-probe",
                                tasks={"w4-realworld-missing-user-id": 1200,
                                       "w4b-zarr-consolidated-order": 2700})
        self.assertIn("| 1200 | 1200s | 3600s | 20m0s |", text)
        self.assertIn("| 2700 | 2700s | 8100s | 45m0s |", text)

    def test_the_batch1_marker_carries_no_new_arm_warning(self) -> None:
        text = P.dataset_marker(P.BATCH1, dataset="results/screening-batch1")
        self.assertNotIn("NEW ARM CONDITION", text)


class SubprocessSmoke(unittest.TestCase):
    """The probe's per-cell argv really does carry the profile through to run.py."""

    def test_run_py_accepts_the_registered_profile_name(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "harness.runner.run", "--help"],
            cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
            capture_output=True, text=True, check=True,
        )
        self.assertIn("transfer-probe", proc.stdout)


if __name__ == "__main__":
    unittest.main()
