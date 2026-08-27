"""The transfer-probe driver: the registered cell list, the preflight, and resume.

``harness/runner/transfer_probe.py`` owns three things that cost money if they
are wrong, and these tests pin all three.

  * **The cell list** must be the registered one — 27 cells, the prereg's run
    order, no silent extra rep and no silently dropped arm.
  * **The preflight** must refuse. Two of its refusals (the frozen
    ``configuration_id`` enum and the absent manifest policy pins) are live in
    this repo right now, so the tests assert against reality rather than against
    a mock; if a human widens the enum or pins the specs, the corresponding test
    flips to asserting the refusal has cleared, which is what it should do.
  * **Resume** must skip a cell that already produced a run directory. Getting
    this wrong re-buys cells that were already paid for — the same failure mode
    tests/test_batch_driver_resume.py pins for the screening driver.

Nothing here spends. The driver's own default mode launches nothing.
"""

import contextlib
import io
import json
import os
import unittest

import yaml

from harness.runner import profiles as P
from harness.runner import transfer_probe as T

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def manifest():
    with open(T.DEFAULT_MANIFEST, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class RegisteredScope(unittest.TestCase):
    """27 cells, {W6,W4b,W4} x {r9,r6,r10} x rep1-3, per the prereg."""

    def setUp(self) -> None:
        self.cells = T.plan_cells()

    def test_there_are_exactly_twenty_seven_cells(self) -> None:
        self.assertEqual(len(self.cells), 27)

    def test_the_three_registered_tasks_and_no_others(self) -> None:
        self.assertEqual({c.task_key for c in self.cells}, {"W4", "W6", "W4b"})

    def test_the_three_registered_arms_and_no_others(self) -> None:
        self.assertEqual({c.config_id for c in self.cells}, {"R9", "R6", "R10"})

    def test_every_task_arm_pair_gets_exactly_three_reps(self) -> None:
        counts = {}
        for c in self.cells:
            counts[(c.task_key, c.config_id)] = counts.get((c.task_key, c.config_id), 0) + 1
        self.assertEqual(len(counts), 9)
        self.assertEqual(set(counts.values()), {3})

    def test_no_cell_is_duplicated(self) -> None:
        keys = [(c.task_key, c.config_id, c.rep) for c in self.cells]
        self.assertEqual(len(keys), len(set(keys)))

    def test_the_run_order_is_w4_then_w6_then_w4b(self) -> None:
        order = []
        for c in self.cells:
            if not order or order[-1] != c.task_key:
                order.append(c.task_key)
        self.assertEqual(order, ["W4", "W6", "W4b"],
                         "the prereg's registered run order; a task appearing twice "
                         "means the tasks were interleaved")

    def test_reps_are_nested_inside_arms_so_a_cut_off_batch_stays_comparable(self) -> None:
        """Rep-before-arm: any prefix has equal reps of all three arms per task."""
        first_nine = self.cells[:9]
        self.assertEqual([c.rep for c in first_nine], [1, 1, 1, 2, 2, 2, 3, 3, 3])
        self.assertEqual([c.config_id for c in first_nine[:3]], ["R9", "R6", "R10"])

    def test_every_task_directory_exists_and_is_not_a_hidden_dir(self) -> None:
        for _key, rel in T.TASKS:
            self.assertTrue(os.path.isdir(os.path.join(ROOT, rel)), rel)
            self.assertNotIn("hidden", rel)

    def test_the_cell_index_is_one_based_and_contiguous(self) -> None:
        self.assertEqual([c.index for c in self.cells], list(range(1, 28)))


class Timing(unittest.TestCase):
    def test_the_profile_is_the_probe_profile_not_batch1(self) -> None:
        self.assertIs(T.PROFILE, P.TRANSFER_PROBE)
        self.assertNotEqual(T.PROFILE.name, P.DEFAULT_PROFILE)

    def test_budgets_are_read_from_the_task_files(self) -> None:
        timeouts = T.task_timeouts()
        self.assertEqual(len(timeouts), 3)
        for task_id, seconds in timeouts.items():
            self.assertIsInstance(seconds, int, task_id)
            self.assertGreater(seconds, 0, task_id)

    def test_each_task_resolves_to_a_soft_budget_and_a_3x_kill(self) -> None:
        for task_id, seconds in T.task_timeouts().items():
            t = T.PROFILE.timeouts(seconds)
            self.assertEqual(t.budget_s, seconds, task_id)
            self.assertEqual(t.kill_s, seconds * 3, task_id)

    def test_the_marker_is_only_written_when_asked(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "dataset")
            self.assertFalse(os.path.exists(out))
            path = T.write_marker(out, T.task_timeouts())
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("NEW ARM CONDITION", text)
            self.assertIn("transfer-probe", text)


class CellCommands(unittest.TestCase):
    def setUp(self) -> None:
        self.cell = T.plan_cells()[0]

    def test_the_command_carries_every_registered_run_condition(self) -> None:
        argv = T.cell_command(self.cell, spend_cap_usd=300.0, dry_run=False)
        pairs = dict(zip(argv, argv[1:]))
        self.assertEqual(pairs["--config"], "R9")
        self.assertEqual(pairs["--phase"], "transfer-probe")
        self.assertEqual(pairs["--profile"], "transfer-probe")
        self.assertEqual(pairs["--cache-state"], "cold")
        self.assertEqual(pairs["--subject-isolation"], "container")
        self.assertEqual(pairs["--subject-egress"], "allowlist")
        self.assertEqual(pairs["--spend-cap-usd"], "300")
        self.assertEqual(pairs["--rep"], "1")

    def test_a_live_command_never_carries_dry_run(self) -> None:
        self.assertNotIn("--dry-run",
                         T.cell_command(self.cell, spend_cap_usd=300.0, dry_run=False))

    def test_a_dry_run_command_never_writes_into_results(self) -> None:
        argv = T.cell_command(self.cell, spend_cap_usd=300.0, dry_run=True,
                              out_root="/tmp/SYNTHETIC-probe")
        self.assertIn("--dry-run", argv)
        self.assertEqual(dict(zip(argv, argv[1:]))["--out-root"], "/tmp/SYNTHETIC-probe")

    def test_host_isolation_drops_the_egress_flag(self) -> None:
        """--subject-egress is only meaningful under container isolation."""
        argv = T.cell_command(self.cell, spend_cap_usd=300.0, dry_run=False,
                              isolation="host")
        self.assertNotIn("--subject-egress", argv)


class LaunchCommands(unittest.TestCase):
    def test_calibration_comes_first_and_probe_second(self) -> None:
        labels = [label for label, _ in T.launch_commands()]
        self.assertIn("calibration", labels[0])
        self.assertIn("probe", labels[1])

    def test_both_commands_require_the_spend_flag_explicitly(self) -> None:
        for _label, command in T.launch_commands():
            self.assertIn("LAB_ALLOW_SPEND=1", command)
            self.assertIn("--spend-cap-usd", command)

    def test_the_probe_command_needs_launch_as_well_as_live(self) -> None:
        _label, cmd = T.launch_commands()[1]
        self.assertIn("harness.runner.transfer_probe", cmd)
        self.assertIn("--live --launch", cmd)

    def test_the_shared_cap_note_states_the_arithmetic_rather_than_guessing(self) -> None:
        note = T.shared_cap_note(300.0)
        self.assertIn("COMBINED", note)
        self.assertIn("per dataset directory", note)


class Preflight(unittest.TestCase):
    def setUp(self) -> None:
        self.refusals = T.preflight(manifest())
        self.codes = {r.code for r in self.refusals}

    def test_every_refusal_says_what_a_human_must_do(self) -> None:
        for r in self.refusals:
            self.assertTrue(r.remedy.strip(), f"{r.code} has no remedy")
            self.assertTrue(r.detail.strip(), f"{r.code} has no detail")

    def test_all_refusals_are_reported_not_just_the_first(self) -> None:
        """An operator fixing one gate only to be told about the next is N
        round-trips where one would do.

        Asserted against a manifest with the pins removed rather than the live
        one: since the 2026-08-27 CP-SCHEMA widening and the manifest freeze,
        real state produces exactly one refusal (CALIBRATION), so the live
        preflight can no longer demonstrate the property.
        """
        import tempfile

        doc = manifest()
        doc.pop("routing_policies", None)
        with tempfile.TemporaryDirectory() as tmp:
            refusals = T.preflight(doc, calibration_dir=tmp)
        codes = [r.code for r in refusals]
        self.assertEqual(sorted(set(codes)), ["CALIBRATION", "MANIFEST-PIN"])
        self.assertEqual(codes.count("MANIFEST-PIN"), 3,
                         "one refusal per unpinned arm, not one for the batch")

    def test_the_specs_themselves_load_cleanly(self) -> None:
        self.assertNotIn("SPEC", self.codes,
                         "a strategy spec or one of its pinned extracts has drifted")

    def test_calibration_blocks_until_it_has_been_run(self) -> None:
        """The automatic gate. Flips to clear only once three live reports pass."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            codes = {r.code for r in T.preflight(manifest(), calibration_dir=tmp)}
            self.assertIn("CALIBRATION", codes)

    def test_the_frozen_schema_enum_blocks_the_arms(self) -> None:
        """R9/R6/R10 are outside the CP-SCHEMA enum; widening it is a human call.

        Asserted against the live schema on purpose. When a human widens the
        enum this test must be updated in the same change that widens it — that
        is the point of a CP-SCHEMA gate.
        """
        from harness.runner.run import schema_configuration_ids

        allowed = set(schema_configuration_ids())
        if {"R9", "R6", "R10"} <= allowed:
            self.assertNotIn("SCHEMA-ENUM", self.codes)
        else:
            self.assertIn("SCHEMA-ENUM", self.codes)

    def test_the_manifest_policy_pins_block_until_a_human_freezes_them(self) -> None:
        from harness.runner.run import policy_manifest_pin

        pinned = all(policy_manifest_pin(manifest(), c) for c in T.CONFIGS)
        if pinned:
            self.assertNotIn("MANIFEST-PIN", self.codes)
        else:
            self.assertIn("MANIFEST-PIN", self.codes)

    def test_a_wrong_manifest_pin_is_a_refusal_not_a_shrug(self) -> None:
        doc = manifest()
        doc.setdefault("routing_policies", {})
        for config_id in T.CONFIGS:
            doc["routing_policies"][config_id] = {"sha256": "sha256:" + "0" * 64}
        refusals = T.preflight(doc)
        pins = [r for r in refusals if r.code == "MANIFEST-PIN"]
        self.assertEqual(len(pins), 3)
        for r in pins:
            self.assertIn("hashes to", r.detail)

    def test_a_correct_manifest_pin_clears_that_refusal(self) -> None:
        doc = manifest()
        doc.setdefault("routing_policies", {})
        for config_id in T.CONFIGS:
            doc["routing_policies"][config_id] = {"sha256": T._spec_sha(config_id)}
        codes = {r.code for r in T.preflight(doc)}
        self.assertNotIn("MANIFEST-PIN", codes)

    def test_the_dataset_must_be_listed_in_results_readme_before_it_exists(self) -> None:
        """CLAUDE.md rule 8. Blocks today; clears when the entry is added."""
        with open(os.path.join(ROOT, "results", "README.md"), encoding="utf-8") as fh:
            listed = T.DATASET in fh.read()
        self.assertEqual(listed, "RESULTS-README" not in self.codes)


class Resume(unittest.TestCase):
    """A settled cell must never be re-bought."""

    def _dataset(self, tmp, names):
        for name in names:
            os.makedirs(os.path.join(tmp, name), exist_ok=True)
            with open(os.path.join(tmp, name, "result.json"), "w",
                      encoding="utf-8") as fh:
                json.dump({"_SYNTHETIC": "written by tests/test_transfer_probe.py"}, fh)
        return tmp

    def test_a_completed_run_settles_its_cell_despite_the_timestamp(self) -> None:
        import tempfile

        ids = T.task_ids()
        with tempfile.TemporaryDirectory() as tmp:
            self._dataset(tmp, [f"{ids['W4']}__R9__rep1__20260827T120000"])
            settled = T.completed_cells(tmp, ids)
            self.assertIn((ids["W4"], "R9", 1), settled)
            self.assertEqual(len(settled), 1)

    def test_a_run_directory_without_a_result_is_not_settled(self) -> None:
        import tempfile

        ids = T.task_ids()
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, f"{ids['W4']}__R9__rep1__20260827T120000"))
            self.assertEqual(T.completed_cells(tmp, ids), {},
                             "a cell killed mid-flight must be retried, not skipped")

    def test_a_foreign_run_directory_is_ignored(self) -> None:
        import tempfile

        ids = T.task_ids()
        with tempfile.TemporaryDirectory() as tmp:
            self._dataset(tmp, ["some-other-task__C1__rep1__20260827T120000",
                                "TIMING-PROFILE.md-not-a-dir"])
            self.assertEqual(T.completed_cells(tmp, ids), {})

    def test_an_absent_dataset_directory_settles_nothing(self) -> None:
        self.assertEqual(T.completed_cells("/nonexistent/SYNTHETIC", T.task_ids()), {})

    def test_the_rep_number_is_parsed_not_pattern_matched(self) -> None:
        import tempfile

        ids = T.task_ids()
        with tempfile.TemporaryDirectory() as tmp:
            self._dataset(tmp, [f"{ids['W4b']}__R10__rep3__20260827T120000",
                                f"{ids['W4b']}__R10__repX__20260827T120000"])
            settled = T.completed_cells(tmp, ids)
            self.assertEqual(list(settled), [(ids["W4b"], "R10", 3)])


class Modes(unittest.TestCase):
    @staticmethod
    def _main(argv):
        """Run the CLI with its plan output captured — the plan is 40 lines."""
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = T.main(argv)
        return rc, buf.getvalue(), err.getvalue()

    def test_the_default_mode_launches_nothing(self) -> None:
        rc, out, err = self._main([])
        self.assertEqual(rc, T.EXIT_PLAN_ONLY)
        self.assertIn("PLAN ONLY", err)
        self.assertIn("27 registered cells", out)

    def test_live_without_launch_only_prints_the_plan(self) -> None:
        rc, _out, _err = self._main(["--live"])
        self.assertEqual(rc, T.EXIT_PLAN_ONLY, "--live alone must not start a batch")

    def test_a_live_launch_is_refused_while_the_preflight_has_refusals(self) -> None:
        env = os.environ.get("LAB_ALLOW_SPEND")
        os.environ["LAB_ALLOW_SPEND"] = "1"
        try:
            if T.preflight(manifest()):
                rc, _out, err = self._main(["--live", "--launch"])
                self.assertEqual(rc, T.EXIT_REFUSED)
                self.assertIn("nothing was billed", err)
        finally:
            if env is None:
                os.environ.pop("LAB_ALLOW_SPEND", None)
            else:
                os.environ["LAB_ALLOW_SPEND"] = env

    def test_the_exit_codes_are_distinct(self) -> None:
        codes = [T.EXIT_OK, T.EXIT_CELL_FAILED, T.EXIT_REFUSED, T.EXIT_SPEND_CAP,
                 T.EXIT_PLAN_ONLY]
        self.assertEqual(len(set(codes)), 5)

    def test_the_spend_cap_code_matches_the_runners(self) -> None:
        """run.py returns 3 on the cap; the driver must recognise it to halt."""
        self.assertEqual(T.EXIT_SPEND_CAP, 3)

    def test_the_plan_text_names_the_prereg_and_the_cp_spend_record(self) -> None:
        text = T.render_plan(T.plan_cells(), T.task_timeouts(), T.task_ids(),
                             T.preflight(manifest()), {}, spend_cap_usd=300.0,
                             dry_run=False, out_root=None, manifest_path=None)
        self.assertIn("2026-08-27-transfer-probe.md", text)
        self.assertIn("cp-spend-transfer-probe.md", text)
        self.assertIn("NEW ARM CONDITION", text)
        self.assertEqual(text.count("pending"), 27)


class NoStrayWrites(unittest.TestCase):
    def test_importing_the_driver_creates_no_dataset_directory(self) -> None:
        self.assertFalse(os.path.exists(T.DATASET_DIR),
                         "the dataset directory must be created at launch, by run.py, "
                         "and never as an import side effect")

    def test_the_dataset_and_calibration_paths_are_under_results(self) -> None:
        self.assertTrue(T.DATASET_DIR.startswith(os.path.join(ROOT, "results")))
        self.assertTrue(T.CALIBRATION_DIR.startswith(os.path.join(ROOT, "results")))


if __name__ == "__main__":
    unittest.main()
