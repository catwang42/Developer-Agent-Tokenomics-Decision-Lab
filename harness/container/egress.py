"""Egress allowlist for the containerized AGENT leg (SPEC §6 item 1).

The deterministic gate runs ``--network=none`` and always will. The agent leg
cannot: it must reach a model API. This module supplies the narrowest egress we
can actually enforce, and — just as importantly — a label that says exactly what
was enforced, so no run is later described as more isolated than it was.

**Mechanism.** Two Docker networks and one proxy:

  * ``lab-egress`` is created ``--internal`` — containers on it have **no default
    route** off the host. Attaching the agent container to it removes direct
    egress entirely, verifiably (``verify-egress.sh`` case 1).
  * A tinyproxy container sits on ``lab-egress`` *and* on ``bridge``, so it is the
    single hop out. It is configured deny-by-default against a pinned allowlist of
    host regexes; a host that does not match is refused ``403`` and named in the
    proxy log.
  * The agent container gets ``HTTPS_PROXY``/``HTTP_PROXY`` pointing at it.

The proxy env vars are a *convenience*, not the control: an agent that unsets them
still has no route, because the network is internal. That distinction is why this
is worth calling enforcement rather than configuration.

**What this does NOT establish.** That the allowlist is *sufficient* for a live
agentic run of either product. Only a live run can show that, and live runs are
CP-SPEND-gated. Enforcement is verified without spend; sufficiency is declared
open. See ``egress/allowlist-model-api.txt``.

Nothing in this module makes a model API call.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
EGRESS_DIR = os.path.join(_HERE, "egress")
DEFAULT_ALLOWLIST = os.path.join(EGRESS_DIR, "allowlist-model-api.txt")

#: Internal (no default route) Docker network the agent container joins.
EGRESS_NETWORK = "lab-egress"
#: The bridge network the proxy is *also* attached to, giving it the only way out.
UPLINK_NETWORK = "bridge"
PROXY_CONTAINER = "lab-egress-proxy"
PROXY_PORT = 8888

#: Recorded in identity.network_policy when the agent leg runs with no egress at
#: all (the gate posture, and the default for a container run that needs none).
NETWORK_NONE_LABEL = "none"


class EgressError(RuntimeError):
    """Docker refused to create or start the egress plumbing."""


@dataclass(frozen=True)
class EgressPolicy:
    """A pinned, hashed allowlist plus the plumbing that enforces it."""

    name: str
    patterns: Tuple[str, ...]
    sha256: str
    source_path: str
    network: str = EGRESS_NETWORK
    proxy_host: str = PROXY_CONTAINER
    proxy_port: int = PROXY_PORT

    @property
    def label(self) -> str:
        """The string stamped verbatim into ``identity.network_policy``.

        Carries the mechanism, the deny-default posture, the allowlist identity
        and its hash, so two runs under different allowlists are distinguishable
        from the summary alone without needing this repo at that commit.
        """
        return (
            f"egress-allowlist:{self.name}@sha256:{self.sha256[:12]}; "
            f"{len(self.patterns)}-host-patterns; deny-by-default; "
            f"internal-network={self.network}; proxy-enforced-CONNECT-443-only"
        )

    @property
    def proxy_url(self) -> str:
        return f"http://{self.proxy_host}:{self.proxy_port}"

    def proxy_env(self) -> Dict[str, str]:
        """Proxy env for the agent container (both cases — tools differ)."""
        url = self.proxy_url
        no_proxy = "localhost,127.0.0.1,::1"
        return {
            "HTTP_PROXY": url, "HTTPS_PROXY": url,
            "http_proxy": url, "https_proxy": url,
            "NO_PROXY": no_proxy, "no_proxy": no_proxy,
        }

    def image_tag(self) -> str:
        return f"lab-egress/proxy:{self.sha256[:12]}"

    def matches(self, host: str) -> bool:
        """True if ``host`` would be permitted. Mirrors tinyproxy's matching
        (POSIX extended, case-insensitive) so tests can assert the policy's intent
        without a daemon. The proxy remains the enforcement point."""
        return any(re.search(p, host, re.IGNORECASE) for p in self.patterns)


def load_policy(path: str = DEFAULT_ALLOWLIST, *, name: str = "model-api-v1") -> EgressPolicy:
    """Parse and hash an allowlist file.

    The hash is over the **raw file bytes**, comments included: a comment that
    changes the documented provenance of an entry is a change to the policy's
    meaning and should produce a new label.
    """
    with open(path, "rb") as fh:
        raw = fh.read()
    patterns: List[str] = []
    for line in raw.decode("utf-8").splitlines():
        entry = line.strip()
        if entry and not entry.startswith("#"):
            patterns.append(entry)
    if not patterns:
        raise EgressError(
            f"allowlist {path} has no entries — refusing to build an egress policy "
            f"that permits nothing (a run under it could never succeed, and an "
            f"empty policy is more likely a staging bug than an intent)"
        )
    return EgressPolicy(
        name=name, patterns=tuple(patterns),
        sha256=hashlib.sha256(raw).hexdigest(), source_path=path,
    )


# ---------------------------------------------------------------- docker plumbing

def _docker(*args: str, check: bool = True, timeout: int = 300) -> subprocess.CompletedProcess:
    proc = subprocess.run(  # noqa: S603 - fixed argv, workshop-owned
        ["docker", *args], capture_output=True, text=True, check=False, timeout=timeout,
    )
    if check and proc.returncode != 0:
        raise EgressError(
            f"docker {' '.join(args[:2])} failed (rc={proc.returncode}): "
            f"{(proc.stderr or proc.stdout).strip()[:400]}"
        )
    return proc


def network_exists(name: str) -> bool:
    return _docker("network", "inspect", name, check=False).returncode == 0


def container_running(name: str) -> bool:
    proc = _docker("inspect", "-f", "{{.State.Running}}", name, check=False)
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def ensure_network(policy: EgressPolicy) -> None:
    """Create the internal (no-default-route) network if absent — idempotent."""
    if not network_exists(policy.network):
        _docker("network", "create", "--internal", policy.network)


def build_proxy_image(policy: EgressPolicy, *, timeout: int = 900) -> str:
    """Build the allowlist proxy image (package install only; not model spend)."""
    tag = policy.image_tag()
    _docker(
        "build", "-f", os.path.join(EGRESS_DIR, "Dockerfile.egress"),
        "-t", tag, EGRESS_DIR, timeout=timeout,
    )
    return tag


def ensure_proxy(policy: EgressPolicy, *, rebuild: bool = False) -> str:
    """Bring up the allowlist proxy on both networks — idempotent.

    Returns the proxy container name. The proxy publishes **no host port**: it is
    reachable only from the internal network, so it can never act as an open relay
    for anything else on the machine.
    """
    ensure_network(policy)
    tag = policy.image_tag()
    if rebuild or _docker("image", "inspect", tag, check=False).returncode != 0:
        build_proxy_image(policy)

    if container_running(PROXY_CONTAINER):
        current = _docker(
            "inspect", "-f", "{{.Config.Image}}", PROXY_CONTAINER, check=False,
        ).stdout.strip()
        if current == tag:
            return PROXY_CONTAINER
        # A proxy from a DIFFERENT allowlist is running. Replacing it silently
        # would mean runs recorded under this policy label were filtered by
        # another; replace it explicitly instead.
        _docker("rm", "-f", PROXY_CONTAINER, check=False)
    else:
        _docker("rm", "-f", PROXY_CONTAINER, check=False)

    _docker("run", "-d", "--name", PROXY_CONTAINER, "--network", policy.network,
            "--restart", "no", tag)
    # Second attachment = the only uplink. Without this the proxy is as isolated
    # as its clients and every request fails closed (safe, but useless).
    _docker("network", "connect", UPLINK_NETWORK, PROXY_CONTAINER)
    return PROXY_CONTAINER


def teardown(policy: Optional[EgressPolicy] = None, *, remove_network: bool = False) -> None:
    """Stop the proxy (and optionally drop the network). Best-effort."""
    _docker("rm", "-f", PROXY_CONTAINER, check=False)
    if remove_network:
        _docker("network", "rm", (policy or load_policy()).network, check=False)


def proxy_log(tail: int = 50) -> str:
    """Recent proxy log lines — the record of which hosts were refused.

    Worth capturing into a run's artifacts when an agent leg fails: the refusal
    line names the host, which is the difference between "the allowlist is
    incomplete" and "the model API was down".
    """
    proc = _docker("logs", "--tail", str(tail), PROXY_CONTAINER, check=False)
    return (proc.stdout or "") + (proc.stderr or "")
