"""The graded hidden gate widens what `results/` contains. Bound it in a test.

Recording which sealed checks passed makes the archive more useful and makes it
carry more. pytest's own summary line for a failure is

    FAILED tests/test_rules.py::test_L010 - assert 5 == 7

and the tail after ` - ` is an exception repr, which routinely quotes values and
strings lifted straight out of the sealed test. `results/` is committed. So the
drivers cut the line at the id, and this file is the check on that: node ids and
statuses in, assertion text out, permanently.

Both drivers are exercised against SYNTHETIC runner output through stubbed
`subject_run` / `run_jest`. No container, no real test suite, no sealed material.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
STACKS = ROOT / "harness" / "task-tools" / "stacks"

# A SYNTHETIC pytest run: two passes, one fail whose summary line carries the
# assertion repr, one error, and a traceback header that must not survive either.
SYNTHETIC_PYTEST = r"""
tests/SYNTHETIC_rules.py::test_L010_clean PASSED
tests/SYNTHETIC_rules.py::test_L019_clean PASSED
=========================== short test summary info ============================
PASSED tests/SYNTHETIC_rules.py::test_L010_clean
PASSED tests/SYNTHETIC_rules.py::test_L019_clean
FAILED tests/SYNTHETIC_rules.py::test_L044_clean - AssertionError: assert 'SELECT
  a' == 'SELECT a' + where the sealed fixture says SEALED_SECRET_VALUE
ERROR tests/SYNTHETIC_rules.py::test_L060_clean - fixture 'sealed_db' not found
"""

# What jest's --json report looks like; failureMessages carries the diff.
SYNTHETIC_JEST = r"""{
  "testResults": [{"assertionResults": [
    {"fullName": "SYNTHETIC mapper returns following", "status": "passed",
     "failureMessages": []},
    {"fullName": "SYNTHETIC mapper counts favorites", "status": "failed",
     "failureMessages": ["Expected: SEALED_SECRET_VALUE\nReceived: 3"]}
  ]}]
}"""

FORBIDDEN = ("SEALED_SECRET_VALUE", "AssertionError", "Expected:", "assert ",
             "fixture 'sealed_db'")


def _bash(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True)


class ThePythonDriverRecordsIdsAndStatusesOnly(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="graded-SYNTHETIC-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp,
                                                            ignore_errors=True))
        self.out = self.tmp / "graded.tsv"
        (self.tmp / "pytest-output.txt").write_text(SYNTHETIC_PYTEST, encoding="utf-8")

    def _run(self, rc: int = 1) -> str:
        script = f"""
        set -uo pipefail
        stack_cmd() {{ echo 'pytest {{SEL}} -q'; }}
        subject_run() {{ cat "{self.tmp}/pytest-output.txt"; return {rc}; }}
        . "{STACKS}/python.sh"
        stack_run_selected_graded "tests/SYNTHETIC_rules.py" "{self.out}"
        echo "rc=$?"
        """
        proc = _bash(script)
        self.assertIn("rc=", proc.stdout, proc.stderr)
        return self.out.read_text(encoding="utf-8")

    def test_it_records_one_line_per_sealed_check(self):
        rows = [l.split("\t") for l in self._run().strip().splitlines()]
        self.assertEqual(
            sorted(rows),
            sorted([["ERROR", "tests/SYNTHETIC_rules.py::test_L060_clean"],
                    ["FAILED", "tests/SYNTHETIC_rules.py::test_L044_clean"],
                    ["PASSED", "tests/SYNTHETIC_rules.py::test_L010_clean"],
                    ["PASSED", "tests/SYNTHETIC_rules.py::test_L019_clean"]]))

    def test_no_assertion_text_survives(self):
        got = self._run()
        for needle in FORBIDDEN:
            self.assertNotIn(needle, got, f"{needle!r} leaked into the graded report")

    def test_it_returns_the_runners_exit_code(self):
        for rc in (0, 1, 4):
            proc = _bash(f"""
            stack_cmd() {{ echo 'pytest {{SEL}} -q'; }}
            subject_run() {{ cat "{self.tmp}/pytest-output.txt"; return {rc}; }}
            . "{STACKS}/python.sh"
            stack_run_selected_graded "sel" "{self.out}"; echo "rc=$?"
            """)
            self.assertIn(f"rc={rc}", proc.stdout, proc.stderr)

    def test_a_runner_that_prints_nothing_yields_an_empty_report(self):
        _bash(f"""
        stack_cmd() {{ echo 'pytest {{SEL}}'; }}
        subject_run() {{ return 2; }}
        . "{STACKS}/python.sh"
        stack_run_selected_graded "sel" "{self.out}"
        """)
        self.assertEqual(self.out.read_text(encoding="utf-8"), "",
                         "an empty report is how 'nothing was recorded' is said")


class TheNodeDriverReadsTheStructuredReport(unittest.TestCase):
    """Via jest's --json, not its console output: `status` and `failureMessages`
    are separate fields there, so not reading the second is structural."""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="graded-SYNTHETIC-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp,
                                                            ignore_errors=True))
        self.out = self.tmp / "graded.tsv"

    def _run(self) -> str:
        # run_jest is stubbed to write the SYNTHETIC report to --outputFile.
        script = f"""
        set -uo pipefail
        pilot_python() {{ python3 "$@"; }}
        run_jest() {{
          local out=""
          while [ $# -gt 0 ]; do
            [ "$1" = "--outputFile" ] && {{ out="$2"; shift; }}
            shift
          done
          cat > "$out" <<'JSON'
{SYNTHETIC_JEST}
JSON
          return 1
        }}
        . "{STACKS}/node.sh"
        stack_run_selected_graded "pattern" "{self.out}"
        """
        proc = _bash(script)
        self.assertTrue(self.out.exists(), proc.stdout + proc.stderr)
        return self.out.read_text(encoding="utf-8")

    def test_it_records_the_test_names_and_statuses(self):
        rows = sorted(l.split("\t") for l in self._run().strip().splitlines())
        self.assertEqual(rows, [["FAILED", "SYNTHETIC mapper counts favorites"],
                                ["PASSED", "SYNTHETIC mapper returns following"]])

    def test_the_failure_message_is_not_read(self):
        got = self._run()
        self.assertNotIn("SEALED_SECRET_VALUE", got)
        self.assertNotIn("Expected:", got)


class TheGateSurfacesItWithoutReadingSealedFiles(unittest.TestCase):
    """A source-level check on the wiring, since running the real gate needs a
    container. If the block header drifts, the extractor stops finding it."""

    GATE = ROOT / "harness" / "task-tools" / "gate" / "check-hidden.sh"

    def test_the_gate_calls_the_graded_primitive_and_labels_the_block(self):
        src = self.GATE.read_text(encoding="utf-8")
        self.assertIn("stack_run_selected_graded", src)
        self.assertIn("-- sealed checks (id and status only) --", src)

    def test_the_extractor_looks_for_the_same_header(self):
        from harness.analysis.quality import SEALED_CHECK_HEADER
        self.assertIn(SEALED_CHECK_HEADER, self.GATE.read_text(encoding="utf-8"))

    def test_it_falls_back_when_a_driver_has_no_graded_primitive(self):
        src = self.GATE.read_text(encoding="utf-8")
        self.assertIn("declare -F stack_run_selected_graded", src,
                      "an older driver must still grade, just without detail")

    def test_every_driver_defines_it(self):
        for driver in ("python.sh", "node.sh", "none.sh"):
            self.assertIn("stack_run_selected_graded()",
                          (STACKS / driver).read_text(encoding="utf-8"), driver)

    def test_the_contract_is_documented(self):
        readme = (STACKS / "README.md").read_text(encoding="utf-8")
        self.assertIn("stack_run_selected_graded", readme)
        self.assertIn("never assertion text", readme)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
