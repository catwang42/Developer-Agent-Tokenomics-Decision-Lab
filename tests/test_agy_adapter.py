"""Regression tests for the Product B (``agy``) adapter — pure functions, no spend.

These cover the two-part defect that left every Gemini leg cost-unavailable across
screening batch 1: the adapter never asked agy for JSON, and behind that the usage
mapper looked for a token-class key agy does not emit. Both are pure given a parsed
payload, so nothing here invokes the product.

See ``report/findings/agy-json-flag-defect.md``.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.adapters import agy  # noqa: E402

LABEL = "Gemini 3.7 Flash (High)"


class OutputFormatFlag(unittest.TestCase):
    """Task 1: without this flag agy prints prose and no usage is ever captured."""

    def test_build_command_requests_json_output(self) -> None:
        cmd = agy.build_command("do it", LABEL)
        self.assertIn("--output-format", cmd)
        self.assertEqual(cmd[cmd.index("--output-format") + 1], "json")

    def test_json_flag_survives_the_pinned_print_timeout_path(self) -> None:
        # The flag must be on the command actually built for a pinned run, not only
        # on the unpinned default path.
        cmd = agy.build_command("do it", LABEL, "15m0s")
        self.assertIn("--output-format", cmd)
        self.assertEqual(cmd[cmd.index("--output-format") + 1], "json")
        # ...and the ordering invariants the other tests pin are unchanged.
        self.assertEqual(cmd[0], "agy")
        self.assertTrue(cmd[1].startswith("-"))
        self.assertEqual(cmd[-2:], ["--print", "do it"])

    def test_stream_json_is_not_requested(self) -> None:
        """stream-json would give per-turn usage but is a run-CONDITION change; the
        adapter must not adopt it unilaterally."""
        self.assertNotIn("stream-json", agy.build_command("do it", LABEL, "15m0s"))


class ReasoningClassMapping(unittest.TestCase):
    """Task 2: agy spells the reasoning class ``thinking_tokens``."""

    def test_thinking_tokens_maps_to_the_canonical_reasoning_field(self) -> None:
        usage = agy.usage_from_agy_json({"usage": {"thinking_tokens": 30}})
        self.assertEqual(usage["reasoning_tokens"]["value"], 30)
        self.assertEqual(usage["reasoning_tokens"]["confidence"], "proxy_observed")
        # Provenance: which product key the number came from stays inspectable.
        self.assertEqual(usage["reasoning_tokens"]["source_key"], "thinking_tokens")

    def test_reasoning_tokens_still_maps(self) -> None:
        usage = agy.usage_from_agy_json({"usage": {"reasoning_tokens": 7}})
        self.assertEqual(usage["reasoning_tokens"]["value"], 7)
        self.assertEqual(usage["reasoning_tokens"]["confidence"], "proxy_observed")
        self.assertEqual(usage["reasoning_tokens"]["source_key"], "reasoning_tokens")

    def test_canonical_key_wins_when_both_are_present(self) -> None:
        usage = agy.usage_from_agy_json(
            {"usage": {"reasoning_tokens": 7, "thinking_tokens": 30}})
        self.assertEqual(usage["reasoning_tokens"]["value"], 7)
        self.assertEqual(usage["reasoning_tokens"]["source_key"], "reasoning_tokens")

    def test_neither_key_leaves_the_class_unavailable_never_zero(self) -> None:
        usage = agy.usage_from_agy_json({"usage": {"input_tokens": 5}})
        self.assertEqual(usage["reasoning_tokens"]["confidence"], "unavailable")
        self.assertIsNone(usage["reasoning_tokens"]["value"])


class UsageTierAndAbsentClasses(unittest.TestCase):
    def test_the_verified_agy_block_maps_as_a_whole(self) -> None:
        """The block observed on agy 1.1.13, 2026-08-22."""
        usage = agy.usage_from_agy_json({"usage": {
            "input_tokens": 12733, "output_tokens": 31, "thinking_tokens": 30,
            "cache_read_tokens": 0, "total_tokens": 12764,
        }})
        self.assertEqual(usage["input_tokens"]["value"], 12733)
        self.assertEqual(usage["output_tokens"]["value"], 31)
        self.assertEqual(usage["reasoning_tokens"]["value"], 30)
        # A product-reported 0 is a measurement, not a zero-fill: it is recorded.
        self.assertEqual(usage["cache_read_tokens"]["value"], 0)
        self.assertEqual(usage["cache_read_tokens"]["confidence"], "proxy_observed")
        for cls in ("input_tokens", "output_tokens", "reasoning_tokens",
                    "cache_read_tokens"):
            self.assertEqual(usage[cls]["confidence"], "proxy_observed",
                             msg=f"{cls} must never be recorded authoritative")

    def test_cache_creation_stays_unavailable(self) -> None:
        """agy exposes no cache-creation class; it must not be aliased or zeroed."""
        usage = agy.usage_from_agy_json({"usage": {
            "input_tokens": 12733, "output_tokens": 31, "thinking_tokens": 30,
            "cache_read_tokens": 0, "total_tokens": 12764,
        }})
        self.assertEqual(usage["cache_creation_tokens"]["confidence"], "unavailable")
        self.assertIsNone(usage["cache_creation_tokens"]["value"])
        self.assertEqual(usage["tool_result_tokens"]["confidence"], "unavailable")


class UnmappedUsageKeys(unittest.TestCase):
    def test_unknown_extra_key_is_preserved_verbatim(self) -> None:
        extra = agy.unmapped_usage_keys({"usage": {
            "input_tokens": 10, "thinking_tokens": 1, "some_new_class_tokens": 42,
        }})
        self.assertEqual(extra["some_new_class_tokens"], 42)
        # Keys that DID map are not duplicated into the record.
        self.assertNotIn("input_tokens", extra)
        self.assertNotIn("thinking_tokens", extra)

    def test_total_tokens_is_preserved_not_treated_as_a_class(self) -> None:
        payload = {"usage": {"input_tokens": 12733, "output_tokens": 31,
                             "thinking_tokens": 30, "cache_read_tokens": 0,
                             "total_tokens": 12764}}
        self.assertEqual(agy.unmapped_usage_keys(payload), {"total_tokens": 12764})
        self.assertNotIn("total_tokens", agy.usage_from_agy_json(payload))

    def test_nothing_unmapped_yields_an_empty_record(self) -> None:
        self.assertEqual(agy.unmapped_usage_keys({"usage": {"input_tokens": 1}}), {})


class NoPayloadPaths(unittest.TestCase):
    """The C3 no-output finding: empty stdout is a diagnosis, not a crash."""

    def test_none_payload_leaves_every_class_unavailable(self) -> None:
        usage = agy.usage_from_agy_json(None)
        for cls, field in usage.items():
            self.assertEqual(field["confidence"], "unavailable", msg=cls)
            self.assertIsNone(field["value"], msg=cls)
        self.assertEqual(agy.unmapped_usage_keys(None), {})

    def test_payload_without_a_usage_block(self) -> None:
        for payload in ({}, {"usage": None}, {"usage": {}}, {"result": "text"}):
            usage = agy.usage_from_agy_json(payload)
            self.assertEqual(usage["input_tokens"]["confidence"], "unavailable",
                             msg=repr(payload))
            self.assertEqual(agy.unmapped_usage_keys(payload), {}, msg=repr(payload))

    def test_non_numeric_and_boolean_values_are_not_counted(self) -> None:
        """A string or a bool is not a token count; recording it would fabricate one."""
        usage = agy.usage_from_agy_json(
            {"usage": {"input_tokens": "lots", "output_tokens": True}})
        self.assertEqual(usage["input_tokens"]["confidence"], "unavailable")
        self.assertEqual(usage["output_tokens"]["confidence"], "unavailable")


if __name__ == "__main__":
    unittest.main()
