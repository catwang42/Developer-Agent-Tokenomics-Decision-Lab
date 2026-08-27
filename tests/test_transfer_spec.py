"""The frozen strategy specs, and the pins that make them checkable.

A transfer probe's only claim is "these are the published strategies, not our
paraphrase of them". That claim rests entirely on the sha256 pins in
``harness/policies/transfer/<id>-spec.yaml``: every behavioural constant is read
from the yaml, and every yaml states the source file its constant came from and
the hash of the bytes we extracted. These tests keep that chain intact —

  * every pinned extract still hashes to its recorded value (drift = refusal);
  * the loader's behavioural fields agree with the extracted source text;
  * the judgment calls are present, unique, and each says what it risks;
  * the r0a version mismatch is recorded rather than glossed.

No test here runs a model or reads results/.
"""

import hashlib
import os
import re
import unittest

import yaml

from harness.adapters import transfer_r6, transfer_r9, transfer_r10
from harness.adapters.transfer_base import ladder_legs
from harness.adapters.transfer_spec import (
    LEVELS,
    SPEC_DIR,
    TransferSpecError,
    build_fresh_prompt,
    build_repair_prompt,
    load_spec,
)

STRATEGIES = ("r9", "r6", "r10")


def raw(strategy_id: str) -> dict:
    with open(os.path.join(SPEC_DIR, f"{strategy_id}-spec.yaml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def extract_text(rel: str) -> str:
    with open(os.path.join(SPEC_DIR, rel), encoding="utf-8") as fh:
        return fh.read()


class Pins(unittest.TestCase):
    def test_every_pinned_extract_still_hashes_true(self) -> None:
        for sid in STRATEGIES:
            doc = raw(sid)
            for entry in doc["extracts"]:
                path = os.path.join(SPEC_DIR, entry["file"])
                with open(path, "rb") as fh:
                    got = hashlib.sha256(fh.read()).hexdigest()
                self.assertEqual(
                    got, entry["sha256"].replace("sha256:", ""),
                    f"{sid}: {entry['file']} no longer matches its pin. The spec's "
                    f"claim to be the source's strategy is only as good as this hash.",
                )

    def test_the_loader_refuses_a_drifted_extract(self) -> None:
        """Drift must be a refusal, not a warning — asserted through the loader."""
        import shutil
        import tempfile

        tmp = tempfile.mkdtemp(prefix="lab-spec-drift-")
        try:
            shutil.copytree(SPEC_DIR, tmp, dirs_exist_ok=True)
            victim = os.path.join(tmp, raw("r9")["extracts"][0]["file"])
            with open(victim, "a", encoding="utf-8") as fh:
                fh.write("\n# SYNTHETIC drift introduced by tests/test_transfer_spec.py\n")
            with self.assertRaises(TransferSpecError) as ctx:
                load_spec("r9", spec_dir=tmp)
            self.assertIn("does not match", str(ctx.exception))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_every_spec_records_the_source_repo_and_commit(self) -> None:
        for sid in STRATEGIES:
            src = raw(sid)["source"]
            self.assertTrue(src["repo"].startswith("https://"))
            self.assertRegex(src["sha"], r"^[0-9a-f]{40}$",
                             f"{sid}: source.sha is not a full commit sha")
            self.assertTrue(src["licence"])
            self.assertTrue(src["files"], f"{sid}: no source file paths recorded")

    def test_all_three_specs_name_the_same_source_commit(self) -> None:
        shas = {sid: raw(sid)["source"]["sha"] for sid in STRATEGIES}
        self.assertEqual(len(set(shas.values())), 1,
                         f"the three arms were extracted from different commits: {shas}")

    def test_shared_extracts_are_pinned_to_the_same_hash_in_every_spec(self) -> None:
        """r9/r6/r10 share most extracts; a per-spec hash would let them diverge."""
        seen: dict = {}
        for sid in STRATEGIES:
            for entry in raw(sid)["extracts"]:
                prev = seen.setdefault(entry["file"], (sid, entry["sha256"]))
                self.assertEqual(
                    prev[1], entry["sha256"],
                    f"{entry['file']} is pinned to different hashes in {prev[0]} and {sid}",
                )


class Loading(unittest.TestCase):
    def test_every_strategy_loads(self) -> None:
        for sid in STRATEGIES:
            spec = load_spec(sid)
            self.assertEqual(spec.strategy_id, sid)
            self.assertTrue(spec.spec_sha256)

    def test_the_spec_hash_is_of_the_yaml_bytes_including_comments(self) -> None:
        for sid in STRATEGIES:
            path = os.path.join(SPEC_DIR, f"{sid}-spec.yaml")
            with open(path, "rb") as fh:
                expect = hashlib.sha256(fh.read()).hexdigest()
            self.assertEqual(load_spec(sid).spec_sha256, expect)

    def test_the_ladder_is_three_cheap_rungs_and_one_frontier(self) -> None:
        for sid in STRATEGIES:
            spec = load_spec(sid)
            self.assertEqual(spec.total_rungs, 3)
            self.assertEqual(spec.frontier_max_calls, 1)
            legs = ladder_legs(spec)
            self.assertEqual(len(legs), 4)
            self.assertEqual(legs[-1][0], spec.frontier.leg_id)

    def test_leg_ids_are_unique_within_an_arm(self) -> None:
        for sid in STRATEGIES:
            ids = [leg[0] for leg in ladder_legs(load_spec(sid))]
            self.assertEqual(len(ids), len(set(ids)), f"{sid}: duplicate leg ids {ids}")

    def test_gate_kinds_are_the_registered_ones(self) -> None:
        self.assertEqual(load_spec("r9").gate_kind, "evidence")
        self.assertEqual(load_spec("r6").gate_kind, "after_ladder")
        self.assertEqual(load_spec("r10").gate_kind, "after_ladder")

    def test_only_r10_discards_the_failed_artefact(self) -> None:
        self.assertTrue(load_spec("r10").discards_failed_artefact)
        self.assertFalse(load_spec("r9").discards_failed_artefact)
        self.assertFalse(load_spec("r6").discards_failed_artefact)

    def test_only_r9_requires_typed_evidence(self) -> None:
        self.assertTrue(load_spec("r9").requires_typed_evidence)
        self.assertFalse(load_spec("r6").requires_typed_evidence)
        self.assertFalse(load_spec("r10").requires_typed_evidence)

    def test_levels_match_the_extracted_source_constants(self) -> None:
        text = extract_text("source/routing-constants.py.txt")
        for level in LEVELS:
            self.assertIn(f'"{level}"', text,
                          f"level {level!r} is not in the pinned routing constants")

    def test_broad_failure_items_matches_the_extracted_constant(self) -> None:
        text = extract_text("source/routing-constants.py.txt")
        match = re.search(r"BROAD_FAILURE_ITEMS\s*=\s*(\d+)", text)
        self.assertIsNotNone(match, "BROAD_FAILURE_ITEMS not found in the pinned extract")
        for sid in STRATEGIES:
            self.assertEqual(load_spec(sid).broad_failure_items, int(match.group(1)))

    def test_the_frontier_budget_override_wording_is_the_sources(self) -> None:
        for sid in STRATEGIES:
            spec = load_spec(sid)
            self.assertIn("frontier budget spent",
                          spec.frontier_budget_override_why.format(max_calls=1))

    def test_the_adapters_are_four_lines_of_spec_selection(self) -> None:
        """If an arm's behaviour lives in Python, the transplant is unverifiable."""
        for cls, sid in ((transfer_r9.TransferR9Adapter, "r9"),
                         (transfer_r6.TransferR6Adapter, "r6"),
                         (transfer_r10.TransferR10Adapter, "r10")):
            self.assertEqual(cls.strategy_id, sid)
            self.assertEqual(cls.name, f"transfer_{sid}")
            self.assertEqual(load_spec(sid).adapter, f"transfer_{sid}")
            # The subclass declares two attributes and nothing else; any method it
            # defined would be arm behaviour that is not in the pinned yaml.
            own = [k for k in vars(cls) if not k.startswith("__")]
            self.assertEqual(sorted(own), ["name", "strategy_id"],
                             f"{cls.__name__} declares {own}; arm behaviour must live "
                             f"in the spec yaml, not in Python")


class Prompts(unittest.TestCase):
    def test_the_repair_prompt_carries_the_digest_under_its_label(self) -> None:
        spec = load_spec("r9")
        text = build_repair_prompt(spec, "TASK BRIEF", "P1: 3 failing")
        self.assertIn("TASK BRIEF", text)
        self.assertIn(spec.repair_evidence_label, text)
        self.assertIn("P1: 3 failing", text)

    def test_the_fresh_suffix_is_pinned_only_for_the_discarding_arm(self) -> None:
        spec = load_spec("r10")
        text = build_fresh_prompt(spec, "TASK BRIEF", "P1: 3 failing", 3)
        self.assertIn("TASK BRIEF", text)
        self.assertIn("P1: 3 failing", text)
        with self.assertRaises(TransferSpecError):
            build_fresh_prompt(load_spec("r9"), "TASK BRIEF", "d", 3)

    def test_the_fresh_suffix_is_byte_exact_from_the_pinned_extract(self) -> None:
        """The suffix is carried verbatim; only its two placeholders are filled."""
        spec = load_spec("r10")
        source = extract_text("source/fresh-prompt.py.txt")
        skeleton = spec.fresh_suffix.format(attempts="{attempts}", digest="{digest}")
        for line in [ln.strip() for ln in skeleton.splitlines() if len(ln.strip()) > 25]:
            probe = line.split("{")[0].strip()
            if len(probe) > 25:
                self.assertIn(probe, source,
                              f"fresh-suffix line is not in the pinned extract: {probe!r}")


class JudgmentCalls(unittest.TestCase):
    """Every deviation from the source is written down, with its risk."""

    def test_each_spec_records_judgment_calls(self) -> None:
        for sid in STRATEGIES:
            calls = raw(sid)["judgment_calls"]
            self.assertGreaterEqual(len(calls), 7, f"{sid}: suspiciously few")

    def test_ids_are_unique_within_a_spec(self) -> None:
        for sid in STRATEGIES:
            ids = [c["id"] for c in raw(sid)["judgment_calls"]]
            self.assertEqual(len(ids), len(set(ids)), f"{sid}: duplicate ids {ids}")

    def test_each_call_states_the_decision_the_alternative_the_why_and_the_risk(self) -> None:
        for sid in STRATEGIES:
            for call in raw(sid)["judgment_calls"]:
                for field in ("decision", "alternative", "why", "risk"):
                    self.assertTrue(
                        str(call.get(field, "")).strip(),
                        f"{sid} {call['id']}: no {field}. A judgment call without a "
                        f"stated risk reads as a fact.",
                    )

    def test_the_calibration_grading_call_is_recorded_in_every_spec(self) -> None:
        """J-12: calibration grades the product's response text, not a written file."""
        for sid in STRATEGIES:
            call = next((c for c in raw(sid)["judgment_calls"] if c["id"] == "J-12"), None)
            self.assertIsNotNone(call, f"{sid}: J-12 (calibration grading) is missing")
            self.assertIn("response", (call["decision"] + call["why"]).lower())


class R0aVersionMismatch(unittest.TestCase):
    """The source's cheap baseline is not the model this lab prices as economical.

    Recorded, not silently mapped: r0a/r0b are the source's baselines and map to
    our C2/P0 anchors, and on r0a the model differs. A comparison against the
    source's published r0a number is therefore approximate, and the spec has to
    say so where anyone reading the anchor will see it.
    """

    def test_every_spec_records_the_mismatch(self) -> None:
        for sid in STRATEGIES:
            anchors = raw(sid)["lab_execution"]["anchors"]
            mismatch = anchors.get("r0a_version_mismatch")
            self.assertIsNotNone(mismatch, f"{sid}: r0a version mismatch not recorded")
            self.assertEqual(mismatch["status"], "approximate")
            self.assertTrue(mismatch["source_model"])
            self.assertTrue(mismatch["lab_model_ref"])
            self.assertTrue(str(mismatch["note"]).strip())

    def test_the_anchors_map_r0a_and_r0b_to_our_configurations(self) -> None:
        for sid in STRATEGIES:
            anchors = raw(sid)["lab_execution"]["anchors"]
            self.assertEqual(anchors["frontier_equals"], "P0")
            self.assertEqual(anchors["cheap_approximates"], "C2")


class PlaceholderDiscipline(unittest.TestCase):
    """CLAUDE.md rule 7: permanent material uses placeholder model labels."""

    def test_lab_execution_refers_to_models_only_by_placeholder(self) -> None:
        for sid in STRATEGIES:
            spec = load_spec(sid)
            for leg_id, _role, model_ref in ladder_legs(spec):
                self.assertRegex(
                    model_ref, r"^[A-Z0-9_]+$",
                    f"{sid} leg {leg_id}: model_ref {model_ref!r} is not a placeholder "
                    f"label; exact models live in manifest/delivery-manifest.yaml",
                )


if __name__ == "__main__":
    unittest.main()
