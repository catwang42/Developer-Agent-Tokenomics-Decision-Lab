"""Validation checks 6 and 7 for review tasks (validate.sh `gate_type=pr_review`).

The defect these tests pin down: validate.sh hardcoded checks 6 and 7 to
`awaiting_human` for every review task and never consulted `hidden/` at all, so a
W6 task could not reach a validated state no matter what the human authored. That
contradicts the sealed-runner contract the human is asked to satisfy ("after you
author: 6 pass, 0 awaiting-human"), and it hid the one property check 6 exists to
establish — that the gate REJECTS an empty review. A matcher that accepts silence
scores every arm as accepted and makes the whole W6 cell meaningless.

The fix is only worth as much as its judgement, so these tests drive validate.sh
end-to-end against three SYNTHETIC sealed runners
(tests/fixtures/w6-hidden-runner-SYNTHETIC/):

  * one that honours the contract          -> check 6 must PASS
  * one that accepts unconditionally       -> check 6 must FAIL (the real defect)
  * one that reports itself unavailable    -> check 6 must FAIL (exit 2 is not a result)

and with no runner — or one the human forgot to chmod — where the original
awaiting_human behaviour must survive unchanged.

Hermetic: a throwaway task directory, a local git repo standing in for the subject
clone, and a SYNTHETIC manifest. No network, no clone, no node, no model spend.
Nothing sealed and nothing real is read — the tests assert, among other things,
that validate.sh never prints the runner's body.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VALIDATE = ROOT / "harness" / "task-tools" / "validate.sh"
FIX = ROOT / "tests" / "fixtures" / "w6-hidden-runner-SYNTHETIC"
FIX_VERSION = (FIX / "VERSION").read_text(encoding="utf-8").strip()

#: Lives in every fixture runner's header. If validate.sh ever echoes the sealed
#: script's source, this string turns up in its output.
SEALED_BODY_MARKER = "NOT the real W6 defect map"

TARGET_PATHS = [
    "src/router/reg-exp-router/node.ts",
    "src/router/reg-exp-router/router.ts",
]
TESTS_DIR = "src/router/reg-exp-router"

TASK_YAML = """\
# SYNTHETIC task definition (tests/fixtures scope) — not a registered task, never
# run as a benchmark subject. Exists only to drive validate.sh's pr_review branch.
task_id: synthetic-review-task-SYNTHETIC
manifest_key: synthetic_task_SYNTHETIC
task_suite_version: SYNTHETIC-v0
class: code_review
gate_type: pr_review
stack: none
repo: SYNTHETIC://no-such-repo
license: MIT
contamination_tier: SYNTHETIC
target_paths:
{target_paths}
tests_dir: {tests_dir}
prompt: |
  SYNTHETIC review prompt. Report defects as <path>:<line> - <description>.
pass_condition: >
  SYNTHETIC: recalls the seeded defects with no fabrications.
task_phase: screening
configurations: [P0]
companion_configurations: []
reps_screening: 1
"""

MANIFEST_YAML = """\
# SYNTHETIC delivery manifest (tests/fixtures scope) — fabricated pins for a
# throwaway local repo. Never describes a real subject and is never published.
SYNTHETIC: "SYNTHETIC test fixture - not a delivery manifest"
synthetic_task_SYNTHETIC:
  repo: {repo}
  pinned_commit: {pin}
"""


def _git(repo: pathlib.Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


class ReviewGateHarness(unittest.TestCase):
    """Builds a throwaway review task and runs the real validate.sh over it."""

    def _validate(self, runner=None, review_report=None, runner_mode=0o755):
        """Run validate.sh against a synthetic review task.

        runner       — a *-SYNTHETIC.sh fixture to install as the sealed
                       hidden/check.sh, or None to leave the dir unauthored.
        review_report— optionally plant a review artifact in the subject tree,
                       to prove check 6 still scores an EMPTY review.
        runner_mode  — permissions for the installed check.sh; 0o644 models the
                       human who authored the runner but forgot to chmod it.
        """
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="w6review-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)

        # --- subject repo: a local git repo standing in for the pinned clone ---
        subject = tmp / "work" / "repo"
        subject.mkdir(parents=True)
        _git(subject, "init", "--quiet")
        _git(subject, "config", "user.email", "synthetic@example.invalid")
        _git(subject, "config", "user.name", "SYNTHETIC")
        for rel in TARGET_PATHS:
            path = subject / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("// SYNTHETIC subject file\n", encoding="utf-8")
        _git(subject, "add", "-A")
        _git(subject, "commit", "--quiet", "-m", "SYNTHETIC pinned commit")
        pin = _git(subject, "rev-parse", "HEAD")

        # --- task dir + manifest ---
        task_dir = tmp / "task"
        task_dir.mkdir()
        (task_dir / "task.yaml").write_text(
            TASK_YAML.format(
                target_paths="\n".join(f"  - {p}" for p in TARGET_PATHS),
                tests_dir=TESTS_DIR,
            ),
            encoding="utf-8",
        )
        manifest = tmp / "manifest-SYNTHETIC.yaml"
        manifest.write_text(
            MANIFEST_YAML.format(repo=str(subject), pin=pin), encoding="utf-8"
        )

        # --- sealed dir (throwaway; the real tasks/*/hidden is never touched) ---
        hidden = tmp / "hidden"
        hidden.mkdir()
        (hidden / "README-FOR-HUMAN.md").write_text(
            "SYNTHETIC placeholder\n", encoding="utf-8"
        )
        if runner is not None:
            entry = hidden / "check.sh"
            shutil.copy(FIX / runner, entry)
            entry.chmod(runner_mode)
            (hidden / "VERSION").write_text(FIX_VERSION + "\n", encoding="utf-8")

        if review_report is not None:
            (subject / "review-report.txt").write_text(review_report, encoding="utf-8")

        report = tmp / "validation-report.json"
        env = {
            **os.environ,
            "TASK_DIR": str(task_dir),
            "TASK_WORKDIR": str(tmp / "work"),
            "DELIVERY_MANIFEST": str(manifest),
            "HIDDEN_TESTS_DIR": str(hidden),
            "VALIDATION_REPORT": str(report),
        }
        proc = subprocess.run(
            ["bash", str(VALIDATE)], capture_output=True, text=True, env=env,
        )
        data = json.loads(report.read_text(encoding="utf-8")) if report.exists() else None
        self.assertIsNotNone(data, f"validate.sh wrote no report:\n{proc.stdout}{proc.stderr}")
        return proc, data

    @staticmethod
    def _check(data, n: int):
        return next(c for c in data["checks"] if c["n"] == n)


class TestCheckSixScoresAnEmptyReview(ReviewGateHarness):
    def test_a_gate_that_rejects_an_empty_review_passes_check_six(self):
        proc, data = self._validate("contract-SYNTHETIC.sh")
        check = self._check(data, 6)
        self.assertEqual("pass", check["status"], proc.stdout + proc.stderr)
        self.assertIn("empty review", check["detail"])
        self.assertIn("exit 1", check["detail"])

    def test_a_gate_that_accepts_an_empty_review_fails_check_six(self):
        # The defect check 6 exists to catch. If this ever passes, the check is
        # decorative: it would mean W6 could be "validated" with a matcher that
        # scores silence as a successful review.
        proc, data = self._validate("accepts-anything-SYNTHETIC.sh")
        check = self._check(data, 6)
        self.assertEqual("fail", check["status"], proc.stdout + proc.stderr)
        self.assertIn("exit 0", check["detail"])
        self.assertIn("ACCEPTED", check["detail"])

    def test_a_runner_reporting_unavailable_fails_check_six(self):
        # exit 2 means "I could not score", which is not evidence that an empty
        # review is rejected. Passing it would record unavailable as a result.
        proc, data = self._validate("unavailable-SYNTHETIC.sh")
        check = self._check(data, 6)
        self.assertEqual("fail", check["status"], proc.stdout + proc.stderr)
        self.assertIn("exit 2", check["detail"])
        self.assertIn("unavailable", check["detail"])

    def test_a_failing_check_six_fails_the_whole_validation(self):
        # awaiting_human does not fail validate.sh; a real fail must.
        proc, data = self._validate("accepts-anything-SYNTHETIC.sh")
        self.assertNotEqual(0, proc.returncode)
        self.assertGreaterEqual(data["summary"]["failed"], 1)

    def test_the_scored_review_is_empty_even_if_the_tree_arrived_dirty(self):
        # A leftover review artifact from an earlier run must not be what check 6
        # scores — otherwise the check silently becomes "does the gate accept THAT
        # review", which is a different question with a different answer.
        proc, data = self._validate(
            "contract-SYNTHETIC.sh",
            review_report="src/router/reg-exp-router/router.ts:42 - SYNTHETIC defect\n",
        )
        self.assertEqual("pass", self._check(data, 6)["status"],
                         proc.stdout + proc.stderr)

    def test_the_synthetic_runner_can_tell_the_two_apart(self):
        # Guards the test above: if the fixture accepted everything, that test
        # would pass for the wrong reason. Invoke it directly, outside the harness.
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="w6runner-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        env = {**os.environ, "SUBJECT_DIR": str(tmp)}
        empty = subprocess.run(["bash", str(FIX / "contract-SYNTHETIC.sh")],
                               capture_output=True, text=True, env=env)
        self.assertEqual(1, empty.returncode, "fixture must reject an empty review")
        (tmp / "review-report.txt").write_text(
            "src/router/reg-exp-router/router.ts:42 - SYNTHETIC defect\n",
            encoding="utf-8")
        filled = subprocess.run(["bash", str(FIX / "contract-SYNTHETIC.sh")],
                                capture_output=True, text=True, env=env)
        self.assertEqual(0, filled.returncode, "fixture must accept a real review")


class TestCheckSevenFingerprintsTheSealedSet(ReviewGateHarness):
    def test_the_sealed_set_is_fingerprinted_and_versioned(self):
        proc, data = self._validate("contract-SYNTHETIC.sh")
        check = self._check(data, 7)
        self.assertEqual("pass", check["status"], proc.stdout + proc.stderr)
        self.assertIn("sha256:", check["detail"])
        self.assertIn(FIX_VERSION, check["detail"])

    def test_the_no_canonical_patch_nuance_survives(self):
        # A review task genuinely has no canonical patch. Check 7 must say so
        # rather than implying a patch was applied and hidden tests then passed.
        _, data = self._validate("contract-SYNTHETIC.sh")
        self.assertIn("no canonical patch", self._check(data, 7)["detail"])

    def test_the_report_cites_which_sealed_set_judged_the_task(self):
        # Previously null for every review task, so a W6 result could not name the
        # sealed set behind it.
        _, data = self._validate("contract-SYNTHETIC.sh")
        self.assertTrue(data["hidden_test_hash"].startswith("sha256:"))
        self.assertEqual(FIX_VERSION, data["hidden_test_version"])

    def test_check_seven_cites_the_same_hash_the_gate_recorded(self):
        # Check 7 must quote the bytes the GATE hashed, not a second computation
        # that could drift from it.
        _, data = self._validate("contract-SYNTHETIC.sh")
        self.assertIn(data["hidden_test_hash"], self._check(data, 7)["detail"])

    def test_the_hash_covers_the_sealed_content_not_just_the_filename(self):
        _, a = self._validate("contract-SYNTHETIC.sh")
        _, b = self._validate("accepts-anything-SYNTHETIC.sh")
        self.assertNotEqual(a["hidden_test_hash"], b["hidden_test_hash"])

    def test_the_fingerprint_is_recorded_even_when_check_six_fails(self):
        # The two checks answer different questions; a runner that misjudges an
        # empty review is still a pinned sealed set.
        _, data = self._validate("accepts-anything-SYNTHETIC.sh")
        self.assertEqual("fail", self._check(data, 6)["status"])
        self.assertEqual("pass", self._check(data, 7)["status"])


class TestUnauthoredSealedSetStillAwaitsTheHuman(ReviewGateHarness):
    def test_no_runner_keeps_both_checks_awaiting_human(self):
        proc, data = self._validate(None)
        for n in (6, 7):
            self.assertEqual("awaiting_human", self._check(data, n)["status"],
                             proc.stdout + proc.stderr)
        self.assertEqual(0, data["summary"]["failed"], proc.stdout)
        self.assertEqual(0, proc.returncode, "awaiting_human must not fail validation")

    def test_an_unauthored_task_records_no_fingerprint(self):
        _, data = self._validate(None)
        self.assertIsNone(data["hidden_test_hash"])
        self.assertIsNone(data["hidden_test_version"])

    def test_a_runner_that_was_never_chmodded_is_not_treated_as_authored(self):
        # An unexecutable check.sh cannot be invoked. Failing check 6 here would
        # punish a human who delivered the map but forgot the mode bit; the honest
        # reading is that the sealed runner is not yet usable.
        proc, data = self._validate("contract-SYNTHETIC.sh", runner_mode=0o644)
        self.assertEqual("awaiting_human", self._check(data, 6)["status"],
                         proc.stdout + proc.stderr)
        self.assertEqual("awaiting_human", self._check(data, 7)["status"])


class TestSealedMaterialIsNeverExposed(ReviewGateHarness):
    def test_validate_never_prints_the_sealed_runner_source(self):
        proc, _ = self._validate("contract-SYNTHETIC.sh")
        self.assertNotIn(SEALED_BODY_MARKER, proc.stdout)
        self.assertNotIn(SEALED_BODY_MARKER, proc.stderr)

    def test_the_validation_report_carries_no_sealed_contents(self):
        _, data = self._validate("contract-SYNTHETIC.sh")
        blob = json.dumps(data)
        self.assertNotIn(SEALED_BODY_MARKER, blob)
        # the fingerprint and the version are the ONLY sealed-derived values
        self.assertIn("sha256:", blob)

    def test_the_branch_reads_nothing_from_hidden_beyond_the_mode_bit(self):
        # A grep over the pr_review branch: it may test check.sh for executability
        # and delegate to the gate, but must never cat/copy/read the sealed dir.
        src = VALIDATE.read_text(encoding="utf-8")
        # From where the branch names the sealed dir to the outer `else` that
        # begins the gate types with an executable public gate.
        self.assertIn("REVIEW_HIDDEN_DIR=", src)
        branch = src.split("REVIEW_HIDDEN_DIR=", 1)[1].split("\nelse\n", 1)[0]
        for forbidden in ("cat ", "cp ", "head ", "tail ", "grep ", "find "):
            self.assertNotIn(forbidden + '"$REVIEW_HIDDEN_DIR', branch)
            self.assertNotIn(forbidden + "$REVIEW_HIDDEN_DIR", branch)
        self.assertIn('-x "$REVIEW_HIDDEN_DIR/check.sh"', branch)


class TestFixturesAreLabelledSynthetic(unittest.TestCase):
    def test_every_runner_says_synthetic_in_name_and_body(self):
        runners = list(FIX.glob("*.sh"))
        self.assertTrue(runners, "no synthetic runner fixtures found")
        for f in runners:
            self.assertIn("SYNTHETIC", f.name)
            self.assertIn("SYNTHETIC", f.read_text(encoding="utf-8"))
            self.assertTrue(os.access(f, os.X_OK), f"{f.name} is not executable")

    def test_the_version_is_marked_synthetic(self):
        self.assertIn("SYNTHETIC", FIX_VERSION)

    def test_no_synthetic_runner_lives_outside_tests_fixtures(self):
        results = ROOT / "results"
        strays = list(results.rglob("*w6-hidden-runner*")) if results.is_dir() else []
        self.assertEqual([], strays)


if __name__ == "__main__":
    unittest.main()
