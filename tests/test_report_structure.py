"""Structural guardrails for report/ and results/ (CLAUDE.md rule 8).

Three CP-DATA telemetry-completeness reports once overwrote each other because nothing
forbade it. These tests make the append-only, one-authoritative, paired-with-a-dataset
structure a hard gate:

  - every dataset-scoped ``report/<name>/`` has the matching ``results/<name>/``;
  - every non-empty dataset directory under ``results/`` is named in results/README.md;
  - every report under a dataset-scoped ``report/<name>/`` carries a STATUS banner in
    its first 5 lines;
  - at most one telemetry-completeness.md is marked AUTHORITATIVE;
  - nothing lives directly in ``report/`` except README.md and REPORT-SPEC.md.

The feasibility era (``results/feasibility-batch*/`` paired with ``report/batch*/``) was
removed in the 2026-08-27 cleanup, so the pairing rule is asserted against the screening
datasets that remain. The rule itself is unchanged: a report folder never exists without
the dataset it documents.

Note on ``test_at_most_one_authoritative_telemetry``: no telemetry-completeness.md exists
in the tree today, so the assertion is "never more than one" rather than "exactly one".
Requiring existence would encode a premise the repo no longer satisfies; the guardrail
stays armed for the reports that land next.

Offline, no spend: pure filesystem inspection of the repo.
"""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
REPORT = ROOT / "report"

STATUS_RE = re.compile(r"STATUS:\s*\*{0,2}\s*(AUTHORITATIVE|SUPERSEDED|PENDING)")
AUTHORITATIVE_RE = re.compile(r"STATUS:\s*\*{0,2}\s*AUTHORITATIVE")

# report/ subdirectories that are NOT dataset-scoped: they document no single dataset,
# so the pairing rule does not apply to them.
NON_DATASET_REPORT_DIRS = {"findings", "workshop-dashboard", "smoke-screening"}


def _first_lines(path: pathlib.Path, n: int = 5) -> str:
    with open(path, encoding="utf-8") as fh:
        return "".join(fh.readline() for _ in range(n))


def _dataset_dirs():
    """Immediate subdirectories of results/ (cohort/ is gitignored; skip if absent)."""
    return sorted(p for p in RESULTS.iterdir() if p.is_dir())


def _dataset_scoped_report_dirs():
    """report/ subdirectories that claim to document one named dataset."""
    return sorted(
        p for p in REPORT.iterdir()
        if p.is_dir() and p.name not in NON_DATASET_REPORT_DIRS
    )


def _is_nonempty_dataset(d: pathlib.Path) -> bool:
    """A dir counts as a non-empty dataset if it holds any file other than .gitkeep."""
    return any(p.is_file() and p.name != ".gitkeep" for p in d.rglob("*"))


class ReportResultsStructure(unittest.TestCase):
    def test_report_dirs_pair_with_a_dataset(self):
        report_dirs = _dataset_scoped_report_dirs()
        self.assertTrue(report_dirs, "expected at least one dataset-scoped report/<name>/")
        for r in report_dirs:
            dataset = RESULTS / r.name
            self.assertTrue(
                dataset.is_dir(),
                f"report/{r.name}/ documents no dataset: expected "
                f"results/{r.name}/ (pairing rule, CLAUDE.md rule 8)",
            )

    def test_nonempty_datasets_listed_in_readme(self):
        readme = (RESULTS / "README.md").read_text(encoding="utf-8")
        for d in _dataset_dirs():
            if _is_nonempty_dataset(d):
                self.assertIn(
                    f"{d.name}/", readme,
                    f"non-empty dataset results/{d.name}/ is not listed in results/README.md",
                )

    def test_dataset_reports_have_status_banner(self):
        reports = sorted(
            m for r in _dataset_scoped_report_dirs() for m in r.rglob("*.md")
        )
        self.assertTrue(reports, "expected .md reports under a dataset-scoped report/<name>/")
        for r in reports:
            head = _first_lines(r, 5)
            self.assertRegex(
                head, STATUS_RE,
                f"{r.relative_to(ROOT)} lacks a STATUS banner (AUTHORITATIVE/SUPERSEDED/"
                f"PENDING) in its first 5 lines",
            )

    def test_at_most_one_authoritative_telemetry(self):
        telem = sorted(REPORT.glob("*/telemetry-completeness.md"))
        authoritative = [t for t in telem if AUTHORITATIVE_RE.search(_first_lines(t, 5))]
        self.assertLessEqual(
            len(authoritative), 1,
            "at most one telemetry-completeness.md may be marked AUTHORITATIVE in its "
            f"STATUS banner; found {len(authoritative)}: "
            f"{[str(t.relative_to(ROOT)) for t in authoritative]}",
        )

    def test_no_stray_files_directly_in_report(self):
        allowed = {"README.md", "REPORT-SPEC.md"}
        stray = [p.name for p in REPORT.iterdir() if p.is_file() and p.name not in allowed]
        self.assertEqual(
            stray, [],
            f"only {sorted(allowed)} may live directly in report/; found stray: {stray} "
            f"(dataset reports go in report/<dataset-name>/, findings in report/findings/)",
        )


if __name__ == "__main__":
    unittest.main()
