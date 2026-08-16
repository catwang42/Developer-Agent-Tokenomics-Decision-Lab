"""Unit tests for the agent-leg egress allowlist (SPEC §6 item 1).

Pure policy tests — no Docker daemon, no network, no model spend. They pin the two
things that must not drift silently:

  * WHAT the allowlist permits (a widened list is a changed experiment), and
  * that the recorded ``identity.network_policy`` label identifies the exact list,
    so a run made under one allowlist can never be read as made under another.

Live ENFORCEMENT is verified separately by ``harness/container/verify-egress.sh``,
which needs a daemon and is therefore not part of this suite.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from harness.container.egress import (  # noqa: E402
    DEFAULT_ALLOWLIST,
    EgressError,
    load_policy,
)

# Hosts the model API legs need. Sourced in the allowlist header; if an entry is
# dropped, the corresponding leg fails closed at run time — this test says so first.
MUST_ALLOW = (
    "aiplatform.googleapis.com",
    "us-central1-aiplatform.googleapis.com",
    "global-aiplatform.googleapis.com",
    "oauth2.googleapis.com",
    "sts.googleapis.com",
    "api.anthropic.com",
    "antigravity-unleash.goog",
    "cloudcode-pa.googleapis.com",
)

# Deny-by-default means everything else, including plausible near-misses. The
# lookalikes matter: a pattern anchored loosely would let an attacker-controlled
# suffix domain through, and the agent leg is the one leg with egress.
MUST_DENY = (
    "example.com",
    "github.com",
    "pypi.org",
    "raw.githubusercontent.com",
    "aiplatform.googleapis.com.evil.test",
    "notaiplatform.googleapis.com",
    "oauth2.googleapis.com.attacker.test",
    "api.anthropic.com.evil.test",
    "metadata.google.internal",
)


class AllowlistContents(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_policy()

    def test_required_model_api_hosts_are_permitted(self) -> None:
        for host in MUST_ALLOW:
            with self.subTest(host=host):
                self.assertTrue(self.policy.matches(host),
                                f"{host} must be reachable by the agent leg")

    def test_everything_else_is_denied(self) -> None:
        for host in MUST_DENY:
            with self.subTest(host=host):
                self.assertFalse(self.policy.matches(host),
                                 f"{host} must NOT be reachable from the agent leg")

    def test_patterns_are_anchored(self) -> None:
        # An unanchored entry is the difference between an allowlist and a
        # substring filter; ``evil-aiplatform.googleapis.com.attacker.test``
        # matching would defeat the whole mechanism.
        for pattern in self.policy.patterns:
            with self.subTest(pattern=pattern):
                self.assertTrue(pattern.startswith("^"), f"{pattern} lacks ^")
                self.assertTrue(pattern.endswith("$"), f"{pattern} lacks $")

    def test_comments_are_not_patterns(self) -> None:
        self.assertTrue(all(not p.startswith("#") for p in self.policy.patterns))


class PolicyLabel(unittest.TestCase):
    """The label is the run's permanent record of what egress was enforced."""

    def test_label_carries_name_and_hash(self) -> None:
        policy = load_policy()
        self.assertIn("model-api-v1", policy.label)
        self.assertIn(policy.sha256[:12], policy.label)
        self.assertIn("deny-by-default", policy.label)

    def test_editing_the_allowlist_changes_the_label(self) -> None:
        # Two runs under different allowlists must be distinguishable from their
        # summaries alone, without needing this repo at that commit.
        with open(DEFAULT_ALLOWLIST, encoding="utf-8") as fh:
            body = fh.read()
        with tempfile.TemporaryDirectory() as tmp:
            widened = os.path.join(tmp, "allowlist.txt")
            with open(widened, "w", encoding="utf-8") as fh:
                fh.write(body + "\n^example\\.com$\n")
            other = load_policy(widened)
        base = load_policy()
        self.assertNotEqual(base.sha256, other.sha256)
        self.assertNotEqual(base.label, other.label)
        self.assertTrue(other.matches("example.com"))
        self.assertFalse(base.matches("example.com"))

    def test_comment_only_edit_still_changes_the_hash(self) -> None:
        # The hash covers the raw bytes: a comment that changes an entry's
        # documented provenance changes what the policy MEANS.
        with open(DEFAULT_ALLOWLIST, encoding="utf-8") as fh:
            body = fh.read()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "allowlist.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# provenance note added later\n" + body)
            self.assertNotEqual(load_policy(path).sha256, load_policy().sha256)


class ProxyWiring(unittest.TestCase):
    def test_proxy_env_set_for_both_case_conventions(self) -> None:
        env = load_policy().proxy_env()
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            self.assertTrue(env[key].startswith("http://lab-egress-proxy:8888"))
        self.assertIn("127.0.0.1", env["NO_PROXY"])

    def test_image_tag_tracks_the_allowlist_hash(self) -> None:
        policy = load_policy()
        self.assertIn(policy.sha256[:12], policy.image_tag())

    def test_empty_allowlist_is_refused(self) -> None:
        # An allowlist that permits nothing is far more likely a staging bug than
        # an intent, and it would fail every run with an opaque connection error.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "allowlist.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# nothing but comments\n")
            with self.assertRaises(EgressError):
                load_policy(path)


class ManifestAgreement(unittest.TestCase):
    """The manifest pin must match the file on disk (SPEC 1.4)."""

    def test_manifest_records_the_current_allowlist_hash(self) -> None:
        import yaml

        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        with open(os.path.join(root, "manifest", "delivery-manifest.yaml"),
                  encoding="utf-8") as fh:
            manifest = yaml.safe_load(fh) or {}
        pinned = ((manifest.get("subject_isolation") or {})
                  .get("agent_leg_egress") or {})
        self.assertEqual(pinned.get("policy_sha256"), load_policy().sha256)
        self.assertEqual(pinned.get("host_patterns"), len(load_policy().patterns))

    def test_manifest_does_not_claim_sufficiency(self) -> None:
        # Enforcement is verified without spend; SUFFICIENCY for a live agentic run
        # is not, and the manifest must not imply otherwise (CLAUDE.md rule 1/4).
        import yaml

        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        with open(os.path.join(root, "manifest", "delivery-manifest.yaml"),
                  encoding="utf-8") as fh:
            manifest = yaml.safe_load(fh) or {}
        pinned = ((manifest.get("subject_isolation") or {})
                  .get("agent_leg_egress") or {})
        self.assertEqual(pinned.get("sufficiency_verified"), "unavailable")


if __name__ == "__main__":
    unittest.main()
