"""Guardrails for the screening report page (docs/screening-report.md + its assets).

The page is a renderer with no data of its own, and three things about it are easy to
break silently:

  - the SYNTHETIC fixture drifting away from what summarize.py actually emits, so the
    page is developed against a shape that no longer exists;
  - a real figure reaching the repo or a published build ahead of CP-FINDINGS/CP-PUBLISH;
  - claims-register language, real model names or prices leaking into permanent material
    (CLAUDE.md rules 4 and 7).

These tests make each of those a hard failure. The view-model behaviour itself
(unavailable never rendering as 0, declared arm order, prediction band provenance) is
tested by tests/js/decision-report.test.js, which this module shells out to under node
and skips when node is not installed.

Offline, no spend: filesystem inspection plus one local node process.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"
FIXTURES = ROOT / "tests" / "fixtures"

PAGE = DOCS / "screening-report.md"
JS = ASSETS / "decision-report.js"
CSS = ASSETS / "decision-report.css"
FIXTURE = FIXTURES / "decision-table-SYNTHETIC.json"
GENERATOR = FIXTURES / "make_decision_table_SYNTHETIC.py"
PREVIEW = FIXTURES / "decision-report-preview-SYNTHETIC.html"
JS_TESTS = ROOT / "tests" / "js" / "decision-report.test.js"

#: Permanent material may not carry these (SPEC §1.2 claims register, CLAUDE.md rule 4).
BANNED_PHRASES = [
    "audit-grade",
    "audit grade",
    "better than",
    "outperform",
    "beats ",
    "winner",
    "fte",
    "full-time equivalent",
    "headcount",
    "industry-leading",
    "state of the art",
    "state-of-the-art",
]

#: Real product/model identifiers belong in manifest/ and pricing/, never in permanent
#: material, which uses placeholder labels only (CLAUDE.md rule 7).
REAL_IDENTIFIERS = [
    "claude-",
    "sonnet",
    "opus",
    "haiku",
    "gemini",
    "flash",
    "anthropic",
    "vertex",
    "openai",
    "gpt-",
    "agy",
]

PERMANENT_FILES = [PAGE, JS, CSS, PREVIEW, ASSETS / "data" / "README.md"]


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


class TestAssetsExist(unittest.TestCase):
    def test_the_page_and_its_assets_are_present(self):
        for path in [PAGE, JS, CSS, FIXTURE, GENERATOR, PREVIEW, JS_TESTS]:
            self.assertTrue(path.is_file(), f"missing {path.relative_to(ROOT)}")

    def test_the_page_mounts_the_renderer(self):
        self.assertIn('id="decision-report"', _read(PAGE),
                      "the page must contain the mount point the script looks for")

    def test_mkdocs_loads_the_assets_and_lists_the_page(self):
        mkdocs = _read(ROOT / "mkdocs.yml")
        self.assertIn("assets/decision-report.css", mkdocs)
        self.assertIn("assets/decision-report.js", mkdocs)
        self.assertIn("screening-report.md", mkdocs)

    def test_the_preview_uses_the_shipped_assets_rather_than_copies(self):
        # A forked copy of the CSS/JS would let the preview and the site diverge, so the
        # preview must point at docs/assets/ directly.
        html = _read(PREVIEW)
        self.assertIn("../../docs/assets/decision-report.css", html)
        self.assertIn("../../docs/assets/decision-report.js", html)


class TestNoRealDataCanLeak(unittest.TestCase):
    def test_the_local_data_directory_is_gitignored(self):
        ignore = _read(ROOT / ".gitignore")
        self.assertIn("docs/assets/data/*", ignore,
                      "a real decision table copied into docs/assets/data/ must not be committable")

    def test_no_decision_table_is_committed_under_docs(self):
        stray = [p for p in DOCS.rglob("*.json")]
        self.assertEqual([], stray,
                         f"unexpected JSON under docs/: {[str(p) for p in stray]}")

    def test_the_page_ships_pointed_at_nothing(self):
        page = _read(PAGE)
        self.assertNotIn("data-src=", page,
                         "the mkdocs page must not hardcode a data source; it renders an "
                         "empty state until a table is supplied under CP-FINDINGS")
        self.assertIn("CP-FINDINGS", page)

    def test_the_renderer_talks_to_no_external_service(self):
        js = _read(JS)
        for pattern in ("http://", "https://"):
            hits = [line for line in js.splitlines()
                    if pattern in line and "://www.w3.org" not in line and not line.strip().startswith("*")]
            self.assertEqual([], hits, f"absolute URL in the renderer: {hits}")
        for api in ("localStorage", "sessionStorage", "document.cookie", "indexedDB", "XMLHttpRequest"):
            self.assertNotIn(api, js, f"the page must not use {api}")

    def test_the_fixture_lives_only_under_tests_fixtures(self):
        strays = [p for p in (ROOT / "results").rglob("*SYNTHETIC*")] if (ROOT / "results").is_dir() else []
        self.assertEqual([], strays,
                         f"synthetic material must never appear under results/: {strays}")


class TestFixtureIsLabelledSynthetic(unittest.TestCase):
    def setUp(self):
        self.table = json.loads(_read(FIXTURE))

    def test_the_filename_says_synthetic(self):
        self.assertIn("SYNTHETIC", FIXTURE.name)

    def test_the_payload_says_synthetic(self):
        self.assertIs(True, self.table.get("synthetic"))
        self.assertIn("SYNTHETIC", self.table.get("SYNTHETIC", ""))
        self.assertIn("SYNTHETIC", self.table.get("synthetic_notice", ""))
        self.assertIn("SYNTHETIC", self.table.get("source_dataset", ""))
        self.assertIn("SYNTHETIC", self.table.get("manifest_ref", ""))

    def test_every_scope_line_is_traceable_to_the_synthetic_suite(self):
        # A scope line that named a real suite version or pricing snapshot could be
        # mistaken for a measurement if the fixture were screenshotted.
        for cell in self.table["cells"]:
            self.assertIn("SYNTHETIC", cell["scope_line"], cell["scope_line"])

    def test_the_preview_shell_carries_a_synthetic_banner(self):
        html = _read(PREVIEW)
        self.assertIn("SYNTHETIC DATA.", html)
        self.assertIn("SYNTHETIC", html.split("<title>")[1].split("</title>")[0])

    def test_the_fixture_regenerates_byte_identically(self):
        # The fixture is produced by running the real summarizer over fabricated runs. If
        # the emitter's shape changes, this fails rather than letting the page render
        # against a shape the pipeline no longer produces.
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--check"],
            cwd=str(ROOT), capture_output=True, text=True,
        )
        self.assertEqual(0, result.returncode,
                         "the committed fixture is stale — re-run "
                         f"tests/fixtures/make_decision_table_SYNTHETIC.py\n{result.stderr}")


class TestClaimsRegister(unittest.TestCase):
    """Permanent material carries no comparative claims and no real identifiers."""

    def test_no_banned_phrase_appears(self):
        for path in PERMANENT_FILES:
            text = _read(path).lower()
            for phrase in BANNED_PHRASES:
                # "fte" is a substring of ordinary words ("often", "after"); require a
                # word boundary so the check is strict without being absurd.
                pattern = r"\b" + re.escape(phrase).replace(r"\ ", r"\s") + (r"\b" if phrase.isalpha() else "")
                self.assertIsNone(re.search(pattern, text),
                                  f"{path.relative_to(ROOT)} contains banned phrase {phrase!r}")

    def test_no_real_model_or_product_identifier_appears(self):
        for path in PERMANENT_FILES:
            text = _read(path).lower()
            for ident in REAL_IDENTIFIERS:
                self.assertNotIn(ident, text,
                                 f"{path.relative_to(ROOT)} names {ident!r}; permanent material "
                                 "uses placeholder labels only (CLAUDE.md rule 7)")

    def test_the_page_states_the_screening_scope(self):
        page = _read(PAGE)
        self.assertIn("SPEC §5", page, "the page must scope screening results")
        self.assertIn("§2.1", page, "the page must say why there is no single leaderboard")

    def test_the_renderer_never_substitutes_zero_for_a_missing_figure(self):
        # A grep-level guard to back the behavioural tests in the node suite: the
        # renderer must not contain a "|| 0" fallback on a cost or a value.
        js = _read(JS)
        for bad in ("value || 0", "?? 0", "|| 0.0"):
            self.assertNotIn(bad, js, f"suspicious zero-fill fallback in the renderer: {bad!r}")


class TestViewModelUnderNode(unittest.TestCase):
    """Run the node suite that exercises the renderer's pure layer."""

    def test_node_view_model_suite_passes(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed; run tests/js/decision-report.test.js manually")
        result = subprocess.run([node, str(JS_TESTS)], cwd=str(ROOT), capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("passed all", result.stdout)


if __name__ == "__main__":
    unittest.main()
