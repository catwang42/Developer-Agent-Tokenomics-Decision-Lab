"""Static invariants for the pilot task artifacts (Phase 2).

These are offline checks (no clone, no network, no model spend): they assert that
the pinned pilot task is internally consistent — the delivery manifest and
task.yaml agree, the canonical patch targets the declared file, the shipped
scripts and repro test exist, and the contamination tier is a schema-v2 enum.
Anything that requires cloning the subject repo lives in validate.sh, not here.
"""

from __future__ import annotations

import pathlib
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PILOT = ROOT / "tasks" / "pilot-realworld"
MANIFEST = ROOT / "manifest" / "delivery-manifest.yaml"
SCHEMA = ROOT / "harness" / "telemetry" / "schema-v2.json"


def _load_yaml(path: pathlib.Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class PilotTaskInvariants(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = _load_yaml(MANIFEST)
        self.pilot = self.manifest["pilot_task"]
        self.task = _load_yaml(PILOT / "task.yaml")

    def test_manifest_and_task_agree_on_pins(self) -> None:
        for key in ("task_id", "repo", "pinned_commit", "canonical_fix_commit"):
            self.assertEqual(
                self.pilot[key], self.task[key],
                f"manifest.pilot_task.{key} disagrees with task.yaml {key}",
            )

    def test_pins_are_full_40_char_shas(self) -> None:
        for key in ("pinned_commit", "canonical_fix_commit"):
            sha = self.pilot[key]
            self.assertRegex(sha, r"^[0-9a-f]{40}$", f"{key} is not a full SHA")

    def test_contamination_tier_is_schema_enum(self) -> None:
        import json

        with open(SCHEMA, encoding="utf-8") as fh:
            schema = json.load(fh)
        enum = (schema["properties"]["identity"]["properties"]
                ["contamination_tier"]["enum"])
        self.assertIn(self.pilot["contamination_tier"], enum)
        self.assertEqual(self.task["contamination_tier"], self.pilot["contamination_tier"])

    def test_canonical_patch_targets_declared_file(self) -> None:
        patch = (PILOT / self.task["canonical_patch"]).read_text(encoding="utf-8")
        target = self.task["target_path"]
        self.assertIn(f"a/{target}", patch)
        self.assertIn(f"b/{target}", patch)
        # The pilot bug fix adds the id selection.
        self.assertIn("+      id: true,", patch)

    def test_required_pilot_artifacts_exist(self) -> None:
        for rel in (
            "setup.sh", "reset.sh", "validate.sh", "lib.sh", "Dockerfile",
            "gate/check-public.sh", "gate/check-hidden.sh",
            "gate/repro/getCurrentUser.repro.test.ts",
            "canonical/fix-missing-user-id.patch",
        ):
            self.assertTrue((PILOT / rel).exists(), f"missing pilot artifact: {rel}")

    def test_hidden_dir_has_human_readme_but_no_committed_tests(self) -> None:
        hidden = ROOT / "tasks" / "hidden"
        self.assertTrue((hidden / "README-FOR-HUMAN.md").exists())
        # No real sealed test may be committed under tasks/hidden/.
        committed_tests = list(hidden.glob("*.test.ts")) + list(hidden.glob("*.spec.ts"))
        self.assertEqual(committed_tests, [], "sealed hidden tests must not be committed")

    def test_synthetic_hidden_fixture_is_labeled(self) -> None:
        fixture = ROOT / "tests" / "fixtures" / "pilot-hidden-SYNTHETIC"
        self.assertTrue(fixture.is_dir())
        for f in fixture.glob("*.ts"):
            self.assertIn("SYNTHETIC", f.name)


if __name__ == "__main__":
    unittest.main()
