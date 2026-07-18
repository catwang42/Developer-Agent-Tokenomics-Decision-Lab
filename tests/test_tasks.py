"""Static invariants for every benchmark task (Phase 2).

Offline checks (no clone, no network, no model spend): each task's task.yaml is
internally consistent, agrees with the delivery manifest it points at, its
canonical patch targets the declared paths, its shipped artifacts exist, and its
hidden dir carries only the human README (no committed sealed tests). Anything
requiring the subject repo lives in harness/task-tools/validate.sh, not here.
"""

from __future__ import annotations

import json
import pathlib
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifest" / "delivery-manifest.yaml"
SCHEMA = ROOT / "harness" / "telemetry" / "schema-v2.json"

# Every task directory driven by the shared harness.
TASK_DIRS = [
    ROOT / "tasks" / "pilot-realworld",
    ROOT / "tasks" / "suite" / "W4-complex-bugfix",
]


def _yaml(path: pathlib.Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


class TaskInvariants(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = _yaml(MANIFEST)
        with open(SCHEMA, encoding="utf-8") as fh:
            self.schema = json.load(fh)
        self.tier_enum = (self.schema["properties"]["identity"]["properties"]
                          ["contamination_tier"]["enum"])

    def _tasks(self):
        for d in TASK_DIRS:
            yield d, _yaml(d / "task.yaml")

    def test_task_dirs_exist(self) -> None:
        for d in TASK_DIRS:
            self.assertTrue((d / "task.yaml").exists(), f"missing task.yaml in {d}")

    def test_manifest_entry_agrees_with_task(self) -> None:
        for d, task in self._tasks():
            entry = self.manifest[task["manifest_key"]]
            for key in ("repo", "pinned_commit"):
                self.assertEqual(entry[key], task[key],
                                 f"{d.name}: manifest.{task['manifest_key']}.{key} != task.yaml")

    def test_pins_are_full_shas(self) -> None:
        for d, task in self._tasks():
            self.assertRegex(str(task["pinned_commit"]), r"^[0-9a-f]{40}$",
                             f"{d.name}: pinned_commit not a full SHA")

    def test_contamination_tier_is_schema_enum(self) -> None:
        for d, task in self._tasks():
            self.assertIn(task["contamination_tier"], self.tier_enum,
                          f"{d.name}: contamination_tier not a schema-v2 enum")

    def test_canonical_patch_targets_declared_paths(self) -> None:
        for d, task in self._tasks():
            patch = (d / task["canonical_patch"]).read_text(encoding="utf-8")
            for target in task["target_paths"]:
                self.assertIn(f"a/{target}", patch, f"{d.name}: patch missing a/{target}")
                self.assertIn(f"b/{target}", patch, f"{d.name}: patch missing b/{target}")

    def test_public_test_exists(self) -> None:
        for d, task in self._tasks():
            self.assertTrue((d / task["public_test"]).exists(),
                            f"{d.name}: missing public_test {task['public_test']}")

    def test_canonical_patch_touches_no_test_files(self) -> None:
        # Anti-gaming: the agent's canonical solution is product code only; test
        # files are never part of the solution (they are restored/harness-owned).
        for d, task in self._tasks():
            patch = (d / task["canonical_patch"]).read_text(encoding="utf-8")
            for line in patch.splitlines():
                if line.startswith(("+++ ", "--- ", "diff --git")):
                    self.assertNotIn(".test.ts", line,
                                     f"{d.name}: canonical patch must not touch test files")
                    self.assertNotIn(".spec.ts", line,
                                     f"{d.name}: canonical patch must not touch test files")

    def test_target_paths_are_not_test_files(self) -> None:
        # Agent-allowed diff scope must not include any test file.
        for d, task in self._tasks():
            for t in task["target_paths"]:
                self.assertNotIn(".test.ts", t, f"{d.name}: target_paths includes a test file")
                self.assertNotIn(".spec.ts", t, f"{d.name}: target_paths includes a test file")

    def test_compat_patch_touches_only_test_files(self) -> None:
        # If a task ships a harness-owned type-compat shim, it may touch ONLY
        # *.test.ts / *.spec.ts (the single documented exception, mechanically bounded).
        for d, task in self._tasks():
            rel = task.get("test_compat_patch")
            if not rel:
                continue
            patch = (d / rel).read_text(encoding="utf-8")
            for line in patch.splitlines():
                if line.startswith("diff --git"):
                    self.assertTrue(
                        (".test.ts" in line) or (".spec.ts" in line),
                        f"{d.name}: test_compat_patch touches a non-test file: {line}",
                    )

    def test_hidden_dir_has_readme_but_no_committed_tests(self) -> None:
        for d, _ in self._tasks():
            hidden = d / "hidden"
            self.assertTrue((hidden / "README-FOR-HUMAN.md").exists(),
                            f"{d.name}: missing hidden/README-FOR-HUMAN.md")
            committed = list(hidden.glob("*.test.ts")) + list(hidden.glob("*.spec.ts"))
            self.assertEqual(committed, [], f"{d.name}: sealed tests must not be committed")

    def test_public_test_kind_is_known(self) -> None:
        for d, task in self._tasks():
            self.assertIn(task["public_test_kind"], ("repro", "feature"),
                          f"{d.name}: unknown public_test_kind")

    def test_synthetic_fixtures_are_labeled(self) -> None:
        for name in ("pilot-draft-hidden-SYNTHETIC", "w4-bugfix-hidden-SYNTHETIC"):
            fixture = ROOT / "tests" / "fixtures" / name
            self.assertTrue(fixture.is_dir(), f"missing fixture {name}")
            for f in fixture.glob("*.ts"):
                self.assertIn("SYNTHETIC", f.name)


if __name__ == "__main__":
    unittest.main()
