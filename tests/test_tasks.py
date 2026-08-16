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
import re
import subprocess
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifest" / "delivery-manifest.yaml"
SCHEMA = ROOT / "harness" / "telemetry" / "schema-v2.json"

# Task directories driven by the shared harness, split by the phase they belong to.
# The two lists differ in ONE invariant — which configuration set task.yaml declares
# (see ConfigurationDeclarations) — so everything else iterates TASK_DIRS.
FEASIBILITY_TASK_DIRS = [
    ROOT / "tasks" / "pilot-realworld",
    ROOT / "tasks" / "suite" / "W4-complex-bugfix",
    ROOT / "tasks" / "suite" / "W1-test-generation",
]
# Phase-4 screening roster, commit-mined and pinned 2026-08-16 to break batch 3's
# ceiling effect. Register: tasks/proposals/2026-08-commit-mined-candidates.md.
SCREENING_TASK_DIRS = [
    ROOT / "tasks" / "suite" / "W4b-zarr-consolidated-order",
    ROOT / "tasks" / "suite" / "W3-migration",
    ROOT / "tasks" / "suite" / "W1b-zarr-block-mask-properties",
    ROOT / "tasks" / "suite" / "W6-pr-review",
]
TASK_DIRS = FEASIBILITY_TASK_DIRS + SCREENING_TASK_DIRS

# Test-file naming, per stack. The suite spans a jest/TypeScript repo and three
# pytest/Python repos, and sqlfluff configures python_files = "*_test.py" while zarr
# uses the default test_*.py — so both Python forms are recognised.
TS_TEST_SUFFIXES = (".test.ts", ".spec.ts")


def _is_test_file(path: str) -> bool:
    """True if ``path`` names a test file in any stack the suite uses."""
    if path.endswith(TS_TEST_SUFFIXES):
        return True
    base = path.rsplit("/", 1)[-1]
    return base.startswith("test_") and base.endswith(".py") or base.endswith("_test.py")


def _patch_files(patch: str) -> list:
    """Repo-relative paths touched by a unified diff, from its `diff --git` lines."""
    return [ln[len("diff --git a/"):].split(" b/")[0]
            for ln in patch.splitlines() if ln.startswith("diff --git ")]


def _yaml(path: pathlib.Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _gate_type(task: dict) -> str:
    # Default (feature/bugfix) tasks omit gate_type; test-generation and pr_review
    # declare it.
    return task.get("gate_type", "solution")


# --- Configuration-declaration enforcement (SPEC §2.3; FIX 4) ---------------- #
VALID_CONFIGS = {"C1", "C2", "C3", "C4", "C5", "P0", "P1"}
# Run dir convention: <task_id>__<CONFIG>__rep<N>__<UTCstamp>
_RUN_DIR_RE = re.compile(r"^(?P<tid>[a-z0-9-]+)__(?P<cfg>[A-Z0-9]+)__rep\d+__")


def _declared_configs_by_task() -> dict:
    """task_id -> set(configurations ∪ companion_configurations) from each task.yaml."""
    out: dict = {}
    for d in TASK_DIRS:
        t = _yaml(d / "task.yaml")
        out[t["task_id"]] = (set(t.get("configurations") or [])
                             | set(t.get("companion_configurations") or []))
    return out


def _runs_by_task(results_root: pathlib.Path):
    """Yield (task_id, config) for each run directory under ``results_root``."""
    if not results_root.is_dir():
        return
    for child in sorted(results_root.iterdir()):
        if not child.is_dir():
            continue
        m = _RUN_DIR_RE.match(child.name)
        if m and m.group("cfg") in VALID_CONFIGS:
            yield m.group("tid"), m.group("cfg")


def undeclared_runs(results_root: pathlib.Path) -> set:
    """Configs run against a task that are NOT declared for it (SPEC §2.3 breach)."""
    declared = _declared_configs_by_task()
    return {(tid, cfg) for tid, cfg in _runs_by_task(results_root)
            if cfg not in declared.get(tid, set())}


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
        # Solution gate: the canonical patch modifies the declared PRODUCT
        # target_paths. Test-generation gate is the inverse — see
        # test_testgen_canonical_only_adds_tests_under_scope. pr_review ships no
        # canonical at all: the reference "solution" is the sealed defect map.
        for d, task in self._tasks():
            if _gate_type(task) == "pr_review":
                self.assertNotIn("canonical_patch", task,
                                 f"{d.name}: pr_review grades a report against the "
                                 f"sealed defect map; it ships no canonical patch")
                continue
            if _gate_type(task) == "test_generation":
                continue
            patch = (d / task["canonical_patch"]).read_text(encoding="utf-8")
            for target in task["target_paths"]:
                self.assertIn(f"a/{target}", patch, f"{d.name}: patch missing a/{target}")
                self.assertIn(f"b/{target}", patch, f"{d.name}: patch missing b/{target}")

    def test_public_test_exists(self) -> None:
        # Only solution-gate tasks ship a public_test file; test-generation grades
        # the agent's own tests (T1–T4) and pr_review grades a report, so neither
        # declares one.
        for d, task in self._tasks():
            if _gate_type(task) in ("test_generation", "pr_review"):
                self.assertNotIn("public_test", task,
                                 f"{d.name}: {_gate_type(task)} task must not declare public_test")
                continue
            self.assertTrue((d / task["public_test"]).exists(),
                            f"{d.name}: missing public_test {task['public_test']}")
            # public_test_support names files the gate CREATES EMPTY in the subject
            # tree (e.g. a package __init__.py the upstream PR adds alongside its new
            # test module), so they are repo-relative paths, never task-dir paths.
            for rel in task.get("public_test_support") or []:
                self.assertFalse(str(rel).startswith(("/", "..")),
                                 f"{d.name}: public_test_support {rel} is not repo-relative")
                self.assertFalse((d / rel).exists(),
                                 f"{d.name}: public_test_support {rel} must not be shipped "
                                 f"in the task dir; the gate creates it empty")

    def test_canonical_patch_touches_no_test_files(self) -> None:
        # Anti-gaming: a SOLUTION canonical is product code only; test files are
        # never part of the solution (they are restored/harness-owned). This
        # invariant does not apply to test-generation, whose canonical IS tests,
        # nor to pr_review, which has no canonical.
        for d, task in self._tasks():
            if _gate_type(task) in ("test_generation", "pr_review"):
                continue
            patch = (d / task["canonical_patch"]).read_text(encoding="utf-8")
            for f in _patch_files(patch):
                self.assertFalse(_is_test_file(f),
                                 f"{d.name}: canonical patch must not touch test file {f}")

    def test_testgen_canonical_only_adds_tests_under_scope(self) -> None:
        # Test-generation canonical: every file it touches is a NEW test file under
        # agent_write_scope, and it touches NONE of the product target_paths — the
        # mirror image of the solution-gate contract.
        for d, task in self._tasks():
            if _gate_type(task) != "test_generation":
                continue
            scope = task["agent_write_scope"].rstrip("/") + "/"
            targets = set(task["target_paths"])
            patch = (d / task["canonical_patch"]).read_text(encoding="utf-8")
            touched = _patch_files(patch)
            self.assertTrue(touched, f"{d.name}: canonical patch touches no files")
            for f in touched:
                self.assertTrue(f.startswith(scope),
                                f"{d.name}: canonical adds {f} outside agent_write_scope {scope}")
                self.assertTrue(_is_test_file(f),
                                f"{d.name}: canonical adds non-test file {f}")
                self.assertNotIn(f, targets,
                                 f"{d.name}: canonical must not touch product target {f}")
            # The canonical adds files, so it must contain new-file hunks from /dev/null.
            self.assertIn("--- /dev/null", patch,
                          f"{d.name}: test-generation canonical should add new files")

    def test_testgen_coverage_target_wellformed(self) -> None:
        for d, task in self._tasks():
            if _gate_type(task) != "test_generation":
                continue
            ct = task.get("coverage_target")
            self.assertIsInstance(ct, dict, f"{d.name}: missing coverage_target")
            self.assertIn(ct.get("metric"), ("branches", "statements", "lines", "functions"),
                          f"{d.name}: coverage_target.metric unknown")
            files = ct.get("files")
            self.assertTrue(files, f"{d.name}: coverage_target.files empty")
            declared = {f["path"] for f in files}
            for f in files:
                self.assertIn("path", f)
                pct = float(f["min_pct"])
                self.assertTrue(0 <= pct <= 100, f"{d.name}: min_pct out of range: {pct}")
            # Every product target is a coverage target (the mappers are what T3 grades).
            for t in task["target_paths"]:
                self.assertIn(t, declared,
                              f"{d.name}: target {t} absent from coverage_target.files")

    def test_target_paths_are_not_test_files(self) -> None:
        # Agent-allowed diff scope must not include any test file.
        for d, task in self._tasks():
            for t in task["target_paths"]:
                self.assertFalse(_is_test_file(t),
                                 f"{d.name}: target_paths includes a test file: {t}")

    def test_compat_patch_touches_only_test_files(self) -> None:
        # If a task ships a harness-owned type-compat shim, it may touch ONLY test
        # files (the single documented exception, mechanically bounded).
        for d, task in self._tasks():
            rel = task.get("test_compat_patch")
            if not rel:
                continue
            patch = (d / rel).read_text(encoding="utf-8")
            for f in _patch_files(patch):
                self.assertTrue(_is_test_file(f),
                                f"{d.name}: test_compat_patch touches a non-test file: {f}")

    def test_hidden_dir_has_readme_but_no_committed_tests(self) -> None:
        for d, _ in self._tasks():
            hidden = d / "hidden"
            self.assertTrue((hidden / "README-FOR-HUMAN.md").exists(),
                            f"{d.name}: missing hidden/README-FOR-HUMAN.md")
            # Sealed material is human-held and gitignored: it MAY exist locally
            # (that is the CP-TASK deliverable, authored in the gate's default
            # HIDDEN_TESTS_DIR=$TASK_DIR/hidden), but must never be *committed*.
            # Check git tracking, not filesystem presence — otherwise this test
            # goes red on the very machine where the human authored the tests
            # while passing in a clean checkout (SPEC §2.6).
            #
            # Whitelist rather than blacklist: the roster's sealed artifacts are no
            # longer just test modules (W1b ships check.sh + mutants/, W6 ships
            # check.sh + defect-map.json + review-diff.patch), and a suffix list
            # would silently stop covering the next gate type. README-FOR-HUMAN.md
            # is the ONLY tracked file any hidden/ dir may contain — the same rule
            # .gitignore enforces (`**/hidden/*`, `!**/hidden/README-FOR-HUMAN.md`).
            tracked = subprocess.run(
                ["git", "ls-files", "-z", str(hidden)],
                cwd=ROOT, capture_output=True, text=True, check=True,
            ).stdout.split("\0")
            committed = sorted(p.rsplit("/", 1)[-1] for p in tracked if p)
            self.assertEqual(committed, ["README-FOR-HUMAN.md"],
                             f"{d.name}: hidden/ may commit only README-FOR-HUMAN.md; "
                             f"found {committed}")

    def test_public_test_kind_is_known(self) -> None:
        # repro       — a hand-authored failing test reproducing the reported defect
        # feature     — a hand-authored test for behaviour the task adds
        # pr_own_tests — the upstream PR's OWN test file, lifted verbatim (the
        #                commit-mining default: the gate is sealed by construction
        #                and pre-modification failure is free; WORKLOAD-SELECTION §4)
        for d, task in self._tasks():
            if _gate_type(task) in ("test_generation", "pr_review"):
                continue  # no public_test, hence no public_test_kind
            self.assertIn(task["public_test_kind"], ("repro", "feature", "pr_own_tests"),
                          f"{d.name}: unknown public_test_kind")

    def test_gate_type_is_known(self) -> None:
        for d, task in self._tasks():
            self.assertIn(_gate_type(task), ("solution", "test_generation", "pr_review"),
                          f"{d.name}: unknown gate_type")

    def test_screening_tasks_declare_the_screening_phase(self) -> None:
        # task_phase disambiguates which configuration set applies (below) and which
        # dataset a run belongs to. Feasibility tasks predate the field.
        for d in SCREENING_TASK_DIRS:
            t = _yaml(d / "task.yaml")
            self.assertEqual(t.get("task_phase"), "screening",
                             f"{d.name}: screening task must declare task_phase: screening")

    def test_synthetic_fixtures_are_labeled(self) -> None:
        for name in ("pilot-draft-hidden-SYNTHETIC", "w4-bugfix-hidden-SYNTHETIC"):
            fixture = ROOT / "tests" / "fixtures" / name
            self.assertTrue(fixture.is_dir(), f"missing fixture {name}")
            for f in fixture.glob("*.ts"):
                self.assertIn("SYNTHETIC", f.name)


class ConfigurationDeclarations(unittest.TestCase):
    """SPEC §2.3 (FIX 4): every configuration run against a task must be declared in
    that task's configurations or companion_configurations list."""

    BATCH2 = ROOT / "results" / "feasibility-batch2"

    def test_declared_fields_are_valid(self) -> None:
        for d in TASK_DIRS:
            t = _yaml(d / "task.yaml")
            self.assertIn("configurations", t, f"{d.name}: task.yaml lacks configurations")
            comp = t.get("companion_configurations", [])
            self.assertIsInstance(comp, list,
                                  f"{d.name}: companion_configurations must be a list")
            for c in list(t["configurations"]) + list(comp):
                self.assertIn(c, VALID_CONFIGS, f"{d.name}: unknown config id {c!r}")

    def test_configurations_is_the_controlled_feasibility_set(self) -> None:
        # Convention for FEASIBILITY tasks: task.yaml `configurations` is the SPEC
        # §2.3 controlled set (P0/C2/P1); companions go in
        # companion_configurations; the screening arms live in workload.yaml.
        # Guards against the old F2 screening-framing regression.
        for d in FEASIBILITY_TASK_DIRS:
            t = _yaml(d / "task.yaml")
            self.assertEqual(
                set(t["configurations"]), {"P0", "C2", "P1"},
                f"{d.name}: configurations must be the controlled feasibility set "
                f"P0/C2/P1 (screening configs belong in workload.yaml)",
            )

    def test_screening_configurations_are_the_screening_arms(self) -> None:
        # The screening roster is not part of the feasibility dataset: those tasks
        # were commit-mined FOR screening, are named in no feasibility batch, and
        # carry no workload.yaml of their own in two of four cases (W1b, W4b are
        # second TASKS of W1/W4). So their task.yaml is the only place the arms can
        # be declared, and they declare the screening set — C1/C2/C3/C5 — matching
        # the workload.yaml of the workload they belong to.
        for d in SCREENING_TASK_DIRS:
            t = _yaml(d / "task.yaml")
            self.assertEqual(
                set(t["configurations"]), {"C1", "C2", "C3", "C5"},
                f"{d.name}: screening task must declare the screening arms C1/C2/C3/C5",
            )
            self.assertEqual(
                t.get("companion_configurations", []), [],
                f"{d.name}: screening tasks run no companions",
            )

    def test_batch2_undeclared_runs_are_exactly_dropped_f1_companions(self) -> None:
        """The check flags batch-2's out-of-plan runs and ONLY those: F1·C3 and F1·C5
        (product/hybrid companions dropped from the re-collection). That F2/F3 (and
        F1's C1/C2/P0/P1) raise no violation also confirms their declarations match
        what batch 2 actually ran — i.e. what the re-collection will run."""
        if not self.BATCH2.is_dir():
            self.skipTest("batch-2 dataset not present")
        self.assertEqual(
            undeclared_runs(self.BATCH2),
            {("pilot-realworld-draft-articles", "C3"),
             ("pilot-realworld-draft-articles", "C5")},
        )


if __name__ == "__main__":
    unittest.main()
