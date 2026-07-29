"""Structural guardrails for report/ and results/ (CLAUDE.md rule 8).

Three CP-DATA telemetry-completeness reports once overwrote each other because nothing
forbade it. These tests make the append-only, one-authoritative, paired-with-a-dataset
structure a hard gate:

  - every ``results/feasibility-batch*/`` has a matching ``report/batch*/``;
  - every non-empty dataset directory under ``results/`` is named in results/README.md;
  - every report under ``report/batchN/`` carries a STATUS banner in its first 5 lines;
  - exactly one telemetry-completeness.md is marked AUTHORITATIVE;
  - nothing lives directly in ``report/`` except README.md and REPORT-SPEC.md.

Offline, no spend: pure filesystem inspection of the repo.
"""

from __future__ import annotations

import os
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
REPORT = ROOT / "report"

STATUS_RE = re.compile(r"STATUS:\s*\*{0,2}\s*(AUTHORITATIVE|SUPERSEDED|PENDING)")
AUTHORITATIVE_RE = re.compile(r"STATUS:\s*\*{0,2}\s*AUTHORITATIVE")


def _first_lines(path: pathlib.Path, n: int = 5) -> str:
    with open(path, encoding="utf-8") as fh:
        return "".join(fh.readline() for _ in range(n))


def _dataset_dirs():
    """Immediate subdirectories of results/ (cohort/ is gitignored; skip if absent)."""
    return sorted(p for p in RESULTS.iterdir() if p.is_dir())


def _is_nonempty_dataset(d: pathlib.Path) -> bool:
    """A dir counts as a non-empty dataset if it holds any file other than .gitkeep."""
    return any(p.is_file() and p.name != ".gitkeep" for p in d.rglob("*"))


class ReportResultsStructure(unittest.TestCase):
    def test_batch_datasets_have_matching_report(self):
        batches = sorted(RESULTS.glob("feasibility-batch*"))
        self.assertTrue(batches, "expected at least one results/feasibility-batch*/")
        for d in batches:
            report_dir = REPORT / d.name.replace("feasibility-", "")  # feasibility-batch3 -> batch3
            self.assertTrue(
                report_dir.is_dir(),
                f"{d.name} has no matching {report_dir.relative_to(ROOT)}/ (pairing rule)",
            )

    def test_nonempty_datasets_listed_in_readme(self):
        readme = (RESULTS / "README.md").read_text(encoding="utf-8")
        for d in _dataset_dirs():
            if _is_nonempty_dataset(d):
                self.assertIn(
                    f"{d.name}/", readme,
                    f"non-empty dataset results/{d.name}/ is not listed in results/README.md",
                )

    def test_batch_reports_have_status_banner(self):
        reports = sorted(REPORT.glob("batch*/*.md"))
        self.assertTrue(reports, "expected reports under report/batch*/")
        for r in reports:
            head = _first_lines(r, 5)
            self.assertRegex(
                head, STATUS_RE,
                f"{r.relative_to(ROOT)} lacks a STATUS banner (AUTHORITATIVE/SUPERSEDED/"
                f"PENDING) in its first 5 lines",
            )

    def test_exactly_one_authoritative_telemetry(self):
        telem = sorted(REPORT.glob("batch*/telemetry-completeness.md"))
        self.assertTrue(telem, "expected telemetry-completeness.md under report/batch*/")
        authoritative = [t for t in telem if AUTHORITATIVE_RE.search(_first_lines(t, 5))]
        self.assertEqual(
            len(authoritative), 1,
            "exactly one telemetry-completeness.md must be marked AUTHORITATIVE in its "
            f"STATUS banner; found {len(authoritative)}: "
            f"{[str(t.relative_to(ROOT)) for t in authoritative]}",
        )

    def test_no_stray_files_directly_in_report(self):
        allowed = {"README.md", "REPORT-SPEC.md"}
        stray = [p.name for p in REPORT.iterdir() if p.is_file() and p.name not in allowed]
        self.assertEqual(
            stray, [],
            f"only {sorted(allowed)} may live directly in report/; found stray: {stray} "
            f"(batch reports go in report/batchN/, findings in report/findings/)",
        )


if __name__ == "__main__":
    unittest.main()
