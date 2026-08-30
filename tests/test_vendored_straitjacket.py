"""The r9 evidence path: pins, and the promise that only the facts moved.

Prereg Amendment 4 lets r9's repair change how failure evidence is CAPTURED and
DIGESTED, and nothing else. Two things have to stay checkable by machine for
that promise to mean anything:

* the vendored wrapper is byte-exact against the revision the spec names, and
  the installed harness is the commit the spec names;
* the level rules the evidence-graph path runs are the same rules the regex
  path runs — not a second copy that happens to agree today.
"""

from __future__ import annotations

import ast
import hashlib
import os
import unittest

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, "harness", "vendor")
SPEC = os.path.join(ROOT, "harness", "policies", "transfer", "r9-spec.yaml")

import sys  # noqa: E402

sys.path.insert(0, ROOT)

from harness.adapters.transfer_spec import (  # noqa: E402
    classify_from_evidence_graph,
    classify_from_unittest,
    load_spec,
)


def _sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _capture_block() -> dict:
    with open(SPEC, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    return doc["evidence"]["calibration"]["capture_harness"]


class VendoredWrapper(unittest.TestCase):
    def test_the_wrapper_matches_the_hash_the_spec_declares(self) -> None:
        cfg = _capture_block()["wrapper"]
        path = os.path.join(ROOT, cfg["path"])
        self.assertEqual(
            _sha256(path), cfg["sha256"],
            "harness/vendor/straitjacket.py was edited. It is a byte-exact copy of "
            f"{cfg['from_repo']}@{cfg['from_sha']}:{cfg['from_path']}, and the "
            "calibration's fidelity claim rests on it being unmodified.")

    def test_the_wrapper_is_the_revision_the_spec_pins(self) -> None:
        cfg = _capture_block()["wrapper"]
        self.assertEqual(cfg["from_sha"],
                         "1a18b04385f9a0da16439ba5f48a2f68ac08d53d")

    def test_the_capture_harness_is_pinned_to_a_commit_and_a_hash(self) -> None:
        cfg = _capture_block()
        self.assertEqual(cfg["commit"],
                         "7c69ea70aa40e1017aa6114b19e977225dd4166f")
        self.assertEqual(cfg["package"], "ctx-harness")
        self.assertEqual(len(cfg["installed_sha256"]), 64)

    def test_the_identification_is_recorded_as_unconfirmed(self) -> None:
        # Not a formality. The claim "this is the harness the published rows
        # were produced with" is this lab's inference, and a report that drops
        # the caveat is making a claim nobody verified (CLAUDE.md rule 4).
        self.assertEqual(_capture_block()["author_confirmation"], "pending")

    def test_only_the_bridge_talks_to_ctx(self) -> None:
        """No code of OURS may import ``ctx`` except the bridge.

        A direct ``ctx`` call elsewhere would be our construction of a
        DigestContext instead of the source's, which is the reimplementation the
        calibration exists to detect rather than contain. The two exemptions are
        the bridge itself and the vendored wrapper — the wrapper imports ``ctx``
        because that is what it is for, and it is hash-pinned above.
        """
        allowed = {os.path.join(VENDOR, "sj_capture.py"),
                   os.path.join(VENDOR, "straitjacket.py")}
        offenders = set()
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "harness")):
            for name in files:
                if not name.endswith(".py"):
                    continue
                path = os.path.join(dirpath, name)
                if os.path.abspath(path) in allowed:
                    continue
                with open(path, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read(), filename=path)
                for node in ast.walk(tree):
                    mods = []
                    if isinstance(node, ast.Import):
                        mods = [a.name for a in node.names]
                    elif isinstance(node, ast.ImportFrom):
                        mods = [node.module or ""]
                    if any(m == "ctx" or m.startswith("ctx.") for m in mods):
                        offenders.add(os.path.relpath(path, ROOT))
        self.assertEqual(sorted(offenders), [],
                         f"these import ctx directly: {sorted(offenders)}")


class TheGateDidNotMove(unittest.TestCase):
    """Same facts in, same Difficulty out, whichever path produced the facts."""

    def setUp(self) -> None:
        self.spec = load_spec("r9")

    def _graph(self, items, failing=None):
        return {"family": "unittest", "profile_version": "unittest/v1",
                "outcome": "fail",
                "aggregate": {"failing": len(items) if failing is None else failing},
                "items": [{"id": i, "failure_class": c, "kind": "failing_test",
                           "severity": "error", "location": "", "summary": ""}
                          for i, c in items],
                "coverage": {}, "parser_warnings": []}

    def test_broad_at_the_specs_threshold(self) -> None:
        d = classify_from_evidence_graph(
            self._graph([("T.test_a", "AssertionError"),
                         ("T.test_b", "AssertionError"),
                         ("T.test_c", "ValueError")]), self.spec)
        self.assertEqual(d.level, "broad")
        self.assertTrue(d.is_hard)
        self.assertEqual(d.failing, self.spec.broad_failure_items)

    def test_local_below_the_threshold(self) -> None:
        d = classify_from_evidence_graph(
            self._graph([("T.test_a", "AssertionError")]), self.spec)
        self.assertEqual(d.level, "local")
        self.assertFalse(d.is_hard)

    def test_all_shallow_classes_stay_shallow_however_many(self) -> None:
        d = classify_from_evidence_graph(
            self._graph([("T.test_a", "ImportError"), ("T.test_b", "NameError"),
                         ("T.test_c", "SyntaxError"), ("T.test_d", "TabError")]),
            self.spec)
        self.assertEqual(d.level, "shallow")
        self.assertFalse(d.is_hard)

    def test_an_environment_class_short_circuits(self) -> None:
        d = classify_from_evidence_graph(
            self._graph([("T.test_a", "EnvironmentError"),
                         ("T.test_b", "AssertionError"),
                         ("T.test_c", "AssertionError")]), self.spec)
        self.assertEqual(d.level, "environment")
        self.assertTrue(d.is_environment)
        self.assertFalse(d.is_hard)

    def test_identical_identities_across_a_repair_turn_stall(self) -> None:
        items = [("T.test_a", "AssertionError")]
        first = classify_from_evidence_graph(self._graph(items), self.spec)
        second = classify_from_evidence_graph(self._graph(items), self.spec,
                                              previous=first)
        self.assertEqual(second.level, "stalled")
        self.assertTrue(second.is_hard)

    def test_no_fact_tier_is_untyped_not_zero(self) -> None:
        """``graph is None`` degrades the run; it never reads as "no failures"."""
        d = classify_from_evidence_graph(None, self.spec)
        self.assertFalse(d.typed)
        self.assertEqual(d.failing, 0)
        self.assertFalse(d.is_hard)

    def test_both_paths_agree_on_the_same_facts(self) -> None:
        """The invariant Amendment 4 turns on: the rules are shared, not copied.

        The regex path is handed runner text carrying exactly the identities and
        classes the graph carries. Every level must come out the same — if these
        two ever diverge, the evidence-graph path grew a rule of its own.
        """
        cases = [
            # (stderr the regex path reads, items the graph path reads)
            ("FAIL: test_a\nAssertionError: x\n",
             [("test_a", "AssertionError")]),
            ("FAIL: test_a\nFAIL: test_b\nERROR: test_c\nAssertionError: x\n"
             "ValueError: y\n",
             [("test_a", "AssertionError"), ("test_b", "AssertionError"),
              ("test_c", "ValueError")]),
            ("ERROR: test_a\nImportError: no numpy\n",
             [("test_a", "ImportError")]),
            ("ERROR: test_a\nEnvironmentError: disk\n",
             [("test_a", "EnvironmentError")]),
        ]
        for stderr, items in cases:
            with self.subTest(stderr=stderr):
                self.assertEqual(
                    classify_from_unittest(stderr, self.spec).level,
                    classify_from_evidence_graph(self._graph(items), self.spec).level)


if __name__ == "__main__":
    unittest.main()
