"""Unit tests for the test-generation gate's decision logic (Phase 3, W1/F3).

The bash gate (harness/task-tools/gate/check-public.sh, gate_type=test_generation)
is a thin orchestrator; the two error-prone decisions are split into pure Python so
they can be tested offline (no clone, no node, no model spend):

  * scope_eval.py   — T1 diff-scope classification (add-only under agent_write_scope)
  * coverage_eval.py — T3 per-file branch-coverage thresholds

Coverage fixtures are hand-written and labeled SYNTHETIC (tests/fixtures/); they
carry no telemetry (CLAUDE.md non-negotiable #1).
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GATE = ROOT / "harness" / "task-tools" / "gate"
FIX = ROOT / "tests" / "fixtures" / "w1-coverage-SYNTHETIC"
W1_TASK = ROOT / "tasks" / "suite" / "W1-test-generation" / "task.yaml"

ARTICLE = "src/app/routes/article/article.mapper.ts"
AUTHOR = "src/app/routes/article/author.mapper.ts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, GATE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


coverage_eval = _load("coverage_eval")
scope_eval = _load("scope_eval")


def _entry(covered: int, total: int, pct: float) -> dict:
    b = {"total": total, "covered": covered, "skipped": 0, "pct": pct}
    return {"lines": b, "statements": b, "functions": b, "branches": b}


def _summary(article, author, prefix="/x/repo/") -> dict:
    return {
        "total": _entry(5, 6, 83.33),
        prefix + ARTICLE: _entry(*article),
        prefix + AUTHOR: _entry(*author),
    }


CT = {
    "metric": "branches",
    "files": [{"path": ARTICLE, "min_pct": 100}, {"path": AUTHOR, "min_pct": 83.33}],
}


class CoverageEvalTest(unittest.TestCase):
    def test_honest_ceiling_passes(self) -> None:
        # article 100% (0/0), author 83.33% (5/6) — the reachable ceiling.
        ok, detail = coverage_eval.evaluate(_summary((0, 0, 100), (5, 6, 83.33)), CT)
        self.assertTrue(ok, detail)
        self.assertNotIn("SHORTFALL", detail)

    def test_author_shortfall_fails(self) -> None:
        # vacuous suite: mappers run but branches unexercised.
        ok, detail = coverage_eval.evaluate(_summary((0, 0, 100), (1, 6, 16.66)), CT)
        self.assertFalse(ok)
        self.assertIn("SHORTFALL", detail)
        self.assertIn(AUTHOR, detail)

    def test_article_shortfall_fails(self) -> None:
        ok, _ = coverage_eval.evaluate(_summary((1, 4, 25), (5, 6, 83.33)), CT)
        self.assertFalse(ok)

    def test_missing_target_file_is_not_measured(self) -> None:
        summ = {"total": _entry(5, 6, 83.33), "/x/repo/" + AUTHOR: _entry(5, 6, 83.33)}
        ok, detail = coverage_eval.evaluate(summ, CT)
        self.assertFalse(ok)
        self.assertIn("NOT MEASURED", detail)

    def test_empty_files_fails(self) -> None:
        ok, detail = coverage_eval.evaluate(_summary((0, 0, 100), (5, 6, 83.33)),
                                            {"metric": "branches", "files": []})
        self.assertFalse(ok)
        self.assertIn("empty", detail)

    def test_epsilon_boundary(self) -> None:
        # exactly at the configured minimum passes; just below fails.
        self.assertTrue(coverage_eval.evaluate(_summary((0, 0, 100), (5, 6, 83.33)), CT)[0])
        self.assertFalse(coverage_eval.evaluate(_summary((0, 0, 100), (5, 6, 83.30)), CT)[0])

    def test_metric_defaults_and_switch(self) -> None:
        # a statements-metric target reads statements, not branches.
        ct_stmt = {"metric": "statements",
                   "files": [{"path": AUTHOR, "min_pct": 100}]}
        summ = {"total": _entry(3, 3, 100), "/x/repo/" + AUTHOR: {
            "statements": {"total": 3, "covered": 3, "skipped": 0, "pct": 100},
            "branches": {"total": 6, "covered": 1, "skipped": 0, "pct": 16.66}}}
        self.assertTrue(coverage_eval.evaluate(summ, ct_stmt)[0])

    def test_suffix_matches_absolute_key(self) -> None:
        # summary keys are absolute; a repo-relative target path still matches.
        ok, _ = coverage_eval.evaluate(_summary((0, 0, 100), (5, 6, 83.33),
                                                prefix="/deep/nested/abs/"), CT)
        self.assertTrue(ok)

    def test_cli_exit_codes_against_synthetic_fixtures(self) -> None:
        passing = subprocess.run(
            [sys.executable, str(GATE / "coverage_eval.py"),
             str(FIX / "pass-summary-SYNTHETIC.json"), str(W1_TASK)],
            capture_output=True, text=True)
        self.assertEqual(passing.returncode, 0, passing.stdout + passing.stderr)

        shortfall = subprocess.run(
            [sys.executable, str(GATE / "coverage_eval.py"),
             str(FIX / "shortfall-summary-SYNTHETIC.json"), str(W1_TASK)],
            capture_output=True, text=True)
        self.assertEqual(shortfall.returncode, 1)
        self.assertIn("SHORTFALL", shortfall.stdout)

        usage = subprocess.run([sys.executable, str(GATE / "coverage_eval.py")],
                               capture_output=True, text=True)
        self.assertEqual(usage.returncode, 2)


class ScopeEvalTest(unittest.TestCase):
    SCOPE = "src/tests/"
    TARGETS = [ARTICLE, AUTHOR]

    def _classify(self, porcelain: str):
        return scope_eval.classify(porcelain, self.SCOPE, self.TARGETS)

    def test_only_new_test_file_is_clean(self) -> None:
        v, tests, aux = self._classify("?? src/tests/mappers/mappers.test.ts")
        self.assertEqual(v, [])
        self.assertEqual(tests, ["src/tests/mappers/mappers.test.ts"])
        self.assertEqual(aux, [])

    def test_new_file_outside_scope_is_violation(self) -> None:
        v, tests, _ = self._classify("?? src/app/routes/article/sneaky.ts")
        self.assertEqual(len(v), 1)
        self.assertIn("outside", v[0])
        self.assertEqual(tests, [])

    def test_modified_tracked_file_is_violation(self) -> None:
        v, _, _ = self._classify(" M src/tests/services/article.service.test.ts")
        self.assertEqual(len(v), 1)
        self.assertIn("(M)", v[0])

    def test_modified_product_target_is_flagged(self) -> None:
        v, _, _ = self._classify(" M " + AUTHOR)
        self.assertEqual(len(v), 1)
        self.assertIn("[target/product]", v[0])

    def test_deleted_tracked_file_is_violation(self) -> None:
        v, _, _ = self._classify(" D src/tests/services/tag.service.test.ts")
        self.assertEqual(len(v), 1)
        self.assertIn("(D)", v[0])

    def test_new_aux_file_under_scope_is_allowed(self) -> None:
        # a non-test helper/fixture under the scope is allowed (contract: add-only
        # under scope), but is not a graded test file.
        v, tests, aux = self._classify("?? src/tests/mappers/helpers.ts")
        self.assertEqual(v, [])
        self.assertEqual(tests, [])
        self.assertEqual(aux, ["src/tests/mappers/helpers.ts"])

    def test_mixed_tree(self) -> None:
        porcelain = "\n".join([
            "?? src/tests/mappers/mappers.test.ts",     # ok
            "?? src/tests/mappers/fixtures.ts",          # ok (aux)
            " M " + ARTICLE,                              # violation (product)
            "?? README.hack.md",                         # violation (out of scope)
        ])
        v, tests, aux = self._classify(porcelain)
        self.assertEqual(len(v), 2)
        self.assertEqual(tests, ["src/tests/mappers/mappers.test.ts"])
        self.assertEqual(aux, ["src/tests/mappers/fixtures.ts"])

    def test_cli_exit_codes(self) -> None:
        clean = subprocess.run(
            [sys.executable, str(GATE / "scope_eval.py"), self.SCOPE, *self.TARGETS],
            input="?? src/tests/mappers/mappers.test.ts\n",
            capture_output=True, text=True)
        self.assertEqual(clean.returncode, 0)
        self.assertIn("TEST\tsrc/tests/mappers/mappers.test.ts", clean.stdout)

        dirty = subprocess.run(
            [sys.executable, str(GATE / "scope_eval.py"), self.SCOPE, *self.TARGETS],
            input=" M " + AUTHOR + "\n", capture_output=True, text=True)
        self.assertEqual(dirty.returncode, 1)
        self.assertTrue(dirty.stdout.startswith("BAD\t"))

        usage = subprocess.run([sys.executable, str(GATE / "scope_eval.py")],
                               capture_output=True, text=True)
        self.assertEqual(usage.returncode, 2)


class SyntheticFixtureLabelingTest(unittest.TestCase):
    def test_coverage_fixtures_are_labeled_synthetic(self) -> None:
        files = list(FIX.glob("*.json"))
        self.assertTrue(files, "no synthetic coverage fixtures found")
        for f in files:
            self.assertIn("SYNTHETIC", f.name)
            self.assertIn("_SYNTHETIC", json.loads(f.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
