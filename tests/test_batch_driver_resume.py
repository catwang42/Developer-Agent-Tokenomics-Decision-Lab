"""Regression tests for the screening batch-1 driver's resume index.

The bug these pin is a *spend* bug, not a cosmetic one. `build_resume_index`
populates `SETTLED`; `settled_why` reads it to decide whether a plan cell has
already been bought. Two ways that silently degrades to "nothing is settled" —
which re-buys 18 cells of real API spend without any error message:

  1. calling the builder through a pipe (`build_resume_index | sed ...`), which
     runs it in a subshell and throws `SETTLED` away;
  2. matching the `|`-delimited key with awk's `sub()`, which reads the key as a
     regex whose `|` is alternation and therefore matches almost every line —
     the opposite failure, settling cells that never ran.

Both are asserted here: (a) statically, against the shipped script, and
(b) behaviourally, by extracting the driver's own matcher functions and running
them under bash against a synthetic index.
"""

import os
import re
import subprocess
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DRIVER = os.path.join(ROOT, "scripts", "screening-batch1-driver.sh")


def driver_text() -> str:
    with open(DRIVER, encoding="utf-8") as fh:
        return fh.read()


def extract_function(name: str, text: str) -> str:
    """The driver's own definition of `name`, from `name() {` to the closing `}`."""
    start = re.search(rf"^{re.escape(name)}\(\) \{{", text, re.M)
    if start is None:
        raise AssertionError(f"{name}() not found in {DRIVER}")
    end = re.search(r"^\}$", text[start.start():], re.M)
    if end is None:
        raise AssertionError(f"{name}() has no closing brace")
    return text[start.start():start.start() + end.end()]


class SettledIndexSurvivesTheCaller(unittest.TestCase):
    """(1) The builder must run in the caller's shell, never a subshell."""

    def setUp(self) -> None:
        self.text = driver_text()

    def test_the_builder_is_never_piped(self) -> None:
        for line in self.text.splitlines():
            if "build_resume_index" in line and not line.lstrip().startswith("#"):
                self.assertNotRegex(
                    line.split("build_resume_index", 1)[1],
                    r"^\s*\|",
                    "build_resume_index piped into another command: the pipeline runs it "
                    "in a subshell, SETTLED is discarded, and every settled cell is re-bought",
                )

    def test_the_builder_is_never_run_in_a_command_substitution(self) -> None:
        code = "\n".join(ln for ln in self.text.splitlines() if not ln.lstrip().startswith("#"))
        self.assertNotIn("$(build_resume_index", code)
        self.assertNotIn("`build_resume_index", code)

    def test_the_builder_reports_through_a_variable_not_stdout(self) -> None:
        body = extract_function("build_resume_index", self.text)
        self.assertIn("RESUME_REPORT=", body)
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertFalse(
                stripped.startswith("echo ") or stripped.startswith("printf "),
                f"build_resume_index writes to stdout ({stripped!r}); callers then pipe it "
                "and lose SETTLED. Accumulate into RESUME_REPORT instead.",
            )

    def test_every_caller_prints_the_report_it_asked_for(self) -> None:
        callers = [
            i for i, line in enumerate(self.text.splitlines())
            if re.match(r"^\s*build_resume_index\s*$", line)
        ]
        self.assertGreaterEqual(len(callers), 2, "expected --list and preflight to build the index")
        lines = self.text.splitlines()
        for i in callers:
            following = "\n".join(lines[i + 1:i + 4])
            self.assertIn("RESUME_REPORT", following,
                          f"the call at line {i + 1} never prints its report")


class SettledLookupMatchesOnlyItsOwnCell(unittest.TestCase):
    """(2) The `|`-delimited key must be matched literally, never as a regex."""

    SETTLED = (
        "pilot-realworld-draft-articles|P0|1|completed\n"
        "pilot-realworld-draft-articles|C3|3|deferred-contaminated\n"
        "w4-realworld-missing-user-id|C2|2|completed\n"
    )

    def setUp(self) -> None:
        text = driver_text()
        self.harness = "\n".join([
            "set -eu",
            'TASK_ID_MAP="tasks/pilot-realworld pilot-realworld-draft-articles',
            'tasks/suite/W4-complex-bugfix w4-realworld-missing-user-id',
            '"',
            f'SETTLED="{self.SETTLED}"',
            extract_function("task_id_for", text),
            extract_function("settled_why", text),
        ])

    def why(self, task: str, arm: str, rep: str) -> str:
        out = subprocess.run(
            ["bash", "-c", f'{self.harness}\nsettled_why "{task}" "{arm}" "{rep}"'],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()

    def test_a_settled_cell_reports_its_reason(self) -> None:
        self.assertEqual(self.why("tasks/pilot-realworld", "P0", "1"), "completed")
        self.assertEqual(self.why("tasks/pilot-realworld", "C3", "3"), "deferred-contaminated")
        self.assertEqual(self.why("tasks/suite/W4-complex-bugfix", "C2", "2"), "completed")

    def test_an_unsettled_cell_reports_nothing(self) -> None:
        self.assertEqual(self.why("tasks/pilot-realworld", "P0", "2"), "")
        self.assertEqual(self.why("tasks/pilot-realworld", "C5", "1"), "")
        self.assertEqual(self.why("tasks/suite/W4-complex-bugfix", "P0", "1"), "")

    def test_a_task_outside_the_roster_is_never_settled(self) -> None:
        self.assertEqual(self.why("tasks/suite/W6-pr-review", "P0", "1"), "")

    def test_the_arm_prefix_does_not_settle_a_longer_arm(self) -> None:
        """C3 settled must not settle C3-med or C3-prev — the delimiter is load-bearing."""
        self.assertEqual(self.why("tasks/pilot-realworld", "C3-med", "3"), "")
        self.assertEqual(self.why("tasks/pilot-realworld", "C3-prev", "3"), "")

    def test_the_matcher_does_not_treat_the_key_as_a_regex(self) -> None:
        body = extract_function("settled_why", driver_text())
        self.assertIn("index(", body)
        self.assertIn("substr(", body)
        self.assertNotIn("sub(k", body)
        self.assertNotRegex(body, r"\$0\s*~\s*k",
                            "regex match on a key containing '|' settles nearly every cell")


class SkippingHappensBeforeAnySpend(unittest.TestCase):
    """A settled cell must cost nothing — not even a provider-meter probe."""

    def setUp(self) -> None:
        self.text = driver_text()
        self.lines = self.text.splitlines()

    def index_of(self, pattern: str) -> int:
        for i, line in enumerate(self.lines):
            if re.search(pattern, line):
                return i
        raise AssertionError(f"no line matching {pattern!r}")

    def test_the_skip_precedes_the_quiet_window_probe(self) -> None:
        skip = self.index_of(r'^\s*WHY="\$\(settled_why ')
        probe = self.index_of(r"^\s*if ! await_quiet ")
        self.assertLess(skip, probe,
                        "settled cells must be skipped before the quiet-window probe runs")

    def test_resume_can_be_turned_off_explicitly(self) -> None:
        self.assertIn("--no-resume", self.text)
        self.assertIn("NO_RESUME=1", self.text)

    def test_the_resume_index_reads_the_real_dataset_not_the_batch_dir(self) -> None:
        """Under --dry-run the batch dir is a temp; what is already bought is not."""
        self.assertIn('RESUME_DIR="results/$PHASE"', self.text)

    def test_settled_cells_are_counted_separately_from_completed_ones(self) -> None:
        self.assertIn("skipped=$((skipped + 1))", self.text)
        self.assertRegex(self.text, r"skipped \(already settled\)")


if __name__ == "__main__":
    unittest.main()
