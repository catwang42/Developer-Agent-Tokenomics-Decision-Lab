"""Product B adapter (``agy``) — WORKSHOP-OWNED black-box wrapper (SPEC 1.3, 6.3).

Product B exposes limited telemetry. This wrapper is where its headless quirks
live: OUR exit codes and OUR timeout are authoritative (the workshop owns them),
the product **selector label is recorded verbatim** (we never infer the backend
model id — SPEC 6.3), and any usage the product does not expose is recorded
``unavailable``, never zero-filled. If the product exposes a cost figure it is
carried as a provider-reported (proxy_observed) cost.

Live execution is gated behind ``LAB_ALLOW_SPEND=1`` like every billing adapter.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List, Optional

from harness.container.exec import resolve_spawn
from harness.telemetry.telemetry import tiered, unavailable

from .base import (
    SUBJECT_PERMISSION_PROFILE,
    Adapter,
    AttemptOutcome,
    AttemptSpec,
    EmitFn,
    agent_env,
    cli_version,
    leg_identity_payload,
    session_payload,
)

# Workshop-owned exit codes (SPEC 1.3 — ours, not the product's).
EXIT_OK = 0
EXIT_PRODUCT_ERROR = 40
EXIT_TIMEOUT = 41

# OUR subprocess kill. It must stay strictly ABOVE the manifest-pinned
# --print-timeout (15m0s = 900s) so the product's own timeout fires first and leaves
# a diagnosable product error, rather than this opaque kill truncating the evidence.
DEFAULT_TIMEOUT_S = 1800

# agy self-updates in-process: its shipped binary carries
# third_party/jetski/cli/updater/auto_updater.go, the format string "Auto-update
# disabled via environment variable %s", and this variable's name — and the updater
# was observed running in a live invocation (auto_updater.go:252, 2026-08-16). What
# we have NOT observed is the matched negative control (same invocation, var set,
# updater silent), which needs a live agy run; see the manifest's
# agy_auto_update_evidence. So this is belt-and-braces, not the enforcement: an
# in-flight update would change the measured product mid-batch, and what actually
# stops that is the version pin, checked here per attempt and again pre-batch in the
# runner. The variable is set on EVERY invocation, including the `--version` probe
# that checks the pin. Recorded as a pinned run condition
# (manifest configurations.PRODUCT_B_*.conditions.auto_update); the value is the
# product's own env var name, not a lab invention.
AUTO_UPDATE_DISABLE_ENV = "AGY_CLI_DISABLE_AUTO_UPDATE"
AUTO_UPDATE_CONDITION = f"disabled_via_{AUTO_UPDATE_DISABLE_ENV}"


def agy_env() -> Dict[str, str]:
    """:func:`agent_env` plus the updater kill-switch."""
    return {**agent_env(), AUTO_UPDATE_DISABLE_ENV: "1"}


class ProductVersionMismatch(RuntimeError):
    """The product on PATH is not the version pinned as a run condition."""


_GO_DURATION_UNITS = {"h": 3600, "m": 60, "s": 1}


def print_timeout_seconds(value: str) -> float:
    """Parse agy's Go-duration ``--print-timeout`` (e.g. ``"15m0s"``) to seconds.

    Deliberately strict — an unparseable pin is a configuration error, not a
    default to fall back to, because falling back would silently reinstate the
    5m0s product default that already truncated one real attempt.
    """
    rest, total, seen = value.strip(), 0.0, False
    while rest:
        digits = ""
        while rest and (rest[0].isdigit() or rest[0] == "."):
            digits, rest = digits + rest[0], rest[1:]
        if not digits or not rest or rest[0] not in _GO_DURATION_UNITS:
            raise ValueError(f"print_timeout {value!r} is not a Go duration (e.g. '15m0s')")
        total, seen = total + float(digits) * _GO_DURATION_UNITS[rest[0]], True
        rest = rest[1:]
    if not seen:
        raise ValueError(f"print_timeout {value!r} is not a Go duration (e.g. '15m0s')")
    return total


def build_command(prompt: str, selector_label: str,
                  print_timeout: Optional[str] = None) -> List[str]:
    """Build the headless ``agy`` command (pure; no execution).

    ``print_timeout`` is the manifest-pinned ``--print-timeout`` value (a Go
    duration such as ``"15m0s"``). It is a PINNED CONDITION, not a tuning knob: the
    product's own default is 5m0s and the one verified-invocation smoke was cut off
    by it mid-attempt, so the value in force is recorded per run like any other
    condition. When None, no flag is passed and the product default applies —
    we never invent a value the manifest did not declare.

    Reasoning effort is expressed through the SELECTOR SUFFIX only (e.g. "Gemini
    3.7 Flash (High)"), never through agy's separate ``--effort`` flag: two
    mechanisms for one condition is how an arm silently becomes un-attributable.

    Verified against ``agy --help`` / ``agy models`` (agy 1.1.4):
      * There is **no ``run`` subcommand** — ``agy help run`` errors
        "unknown subcommand: run", and the prompt-running mode is a top-level flag.
        The prior ``["agy", "run", ...]`` prepended a bogus positional; it is
        removed. Prompt-running flags are global, invoked as ``agy [flags]``.
      * ``selector_label`` is passed verbatim via ``--model`` (agy's selector IS the
        human label, e.g. "Gemini 3.5 Flash (High)", present verbatim in ``agy
        models``); we never translate it to a backend model id.
      * ``--dangerously-skip-permissions`` auto-approves tool use so the headless
        agent can modify files (without it: empty diff).
      * ``--print`` runs a single prompt non-interactively. Whether ``--print``
        takes the prompt as its VALUE or is a boolean switch (prompt then positional)
        is **NOT yet resolved from ``--help`` alone**, and cannot be settled by
        inference — the two batch-2 C3 diffs were byte-identical to the harness
        test-compat patch (Antigravity produced zero changes), so we have no verified
        invocation. The pinned CP-SPEND smoke run settles it. The current ordering
        (``--print`` immediately before the prompt) is correct under either reading.
      * ``--print-timeout`` takes a Go duration and defaults to ``5m0s`` (``agy
        --help``, re-read 2026-08-16 on agy 1.1.13).
    """
    cmd = ["agy", "--dangerously-skip-permissions", "--model", selector_label]
    if print_timeout:
        if print_timeout_seconds(print_timeout) >= DEFAULT_TIMEOUT_S:
            raise ValueError(
                f"pinned --print-timeout {print_timeout!r} is not below our own "
                f"{DEFAULT_TIMEOUT_S}s subprocess kill; the product's timeout must "
                f"fire first so a slow attempt yields a diagnosable product error"
            )
        cmd += ["--print-timeout", print_timeout]
    return cmd + ["--print", prompt]


def usage_from_agy_json(obj: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Map any product-exposed usage to tiered fields; unexposed -> unavailable.

    Product B usage is captured as ``proxy_observed`` (product-reported, not an
    authoritative provider meter). Absent classes are unavailable, never 0.
    """
    raw = (obj or {}).get("usage") or {}
    usage: Dict[str, Any] = {}
    for cls in ("input_tokens", "cache_creation_tokens", "cache_read_tokens", "output_tokens",
                "reasoning_tokens", "tool_result_tokens"):
        val = raw.get(cls)
        usage[cls] = tiered(int(val), "proxy_observed") if isinstance(val, (int, float)) \
            else unavailable("Product B does not expose this token class")
    return usage


class AgyAdapter(Adapter):
    name = "agy"

    def run_attempt(self, spec: AttemptSpec, subject_dir: str, emit: EmitFn) -> AttemptOutcome:
        if os.environ.get("LAB_ALLOW_SPEND") != "1":
            raise RuntimeError(
                "AgyAdapter would incur live product spend; refused. Runs only "
                "under a CP-SPEND-approved runner (LAB_ALLOW_SPEND=1). Use --dry-run."
            )
        r = spec.resolved
        leg_meta = {"leg": spec.leg_id, "role": spec.role, **leg_identity_payload(r)}
        # Product B does not expose session/cache control, so we do NOT inject a
        # session flag into its command (never invent product flags). We DO record
        # the runner's cache-state intent + session id for traceability; freshness
        # for a black-box product is best-effort (a fresh process, no resume asked),
        # recorded and reported as such — never claimed as authoritative.
        emit("model_call_started", **leg_meta, **session_payload(spec))

        # Product-B version drift is a known hazard (SPEC 2.9: 1.1.4 -> 1.1.7 mid-
        # programme, and agy self-updates). The manifest pins the version as a run
        # CONDITION, so a mismatch invalidates the condition and we refuse BEFORE
        # spending rather than quietly measuring a different product.
        observed_version = cli_version("agy", self.container, env=agy_env())
        if r.product_version_pin and observed_version != r.product_version_pin:
            raise ProductVersionMismatch(
                f"agy version {observed_version!r} does not match the manifest pin "
                f"{r.product_version_pin!r} for selector {r.model_or_selector!r}. A "
                f"run under a different product version is a different condition; "
                f"refusing before spend. Re-pin the manifest (with the drift recorded) "
                f"or install the pinned version."
            )

        cmd = build_command(spec.prompt, r.model_or_selector, r.print_timeout)
        # Host mode runs cmd in subject_dir; container mode wraps it in `docker run`
        # (offline default; agent-leg egress is a CP-SPEND item). Only argv/cwd differ.
        argv, cwd = resolve_spawn(self.container, cmd, subject_dir)
        # Exact command executed, for the per-run invocation.txt artifact (run
        # provenance, not telemetry; the runner redacts credential-bearing env).
        invocation = {
            "leg": spec.leg_id, "role": spec.role,
            "product_version": observed_version,
            "product_version_pin": r.product_version_pin or "unpinned",
            "auto_update": AUTO_UPDATE_CONDITION,
            "print_timeout": r.print_timeout or "product_default",
            "effort_pin": r.effort_pin or "unpinned",
            "argv": list(argv), "cwd": cwd,
        }
        payload: Optional[Dict[str, Any]] = None
        try:
            proc = subprocess.run(  # noqa: S603 - workshop-owned command
                argv, cwd=cwd, capture_output=True, text=True,
                check=False, timeout=DEFAULT_TIMEOUT_S, env=agy_env(),  # FIX B
            )
            # Record the product's exit/output for invocation.txt (redacted by the
            # runner). For a black-box product this raw stdout is the only place its
            # usage block — if any — can be inspected; an empty stdout IS the
            # diagnosis (see the C3 no-output finding).
            invocation.update(exit_code=proc.returncode, stdout=proc.stdout,
                              stderr=proc.stderr)
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError:
                payload = None
        except subprocess.TimeoutExpired as exc:
            invocation.update(exit_code="timeout", stdout=exc.stdout or "",
                              stderr=exc.stderr or "")
            emit("failure", leg=spec.leg_id, category="agy_timeout", exit_code=EXIT_TIMEOUT)

        usage = usage_from_agy_json(payload)
        emit("model_call_completed", usage=usage, **leg_meta)

        leg_options: Dict[str, Any] = {}
        reported = (payload or {}).get("cost_usd") if isinstance(payload, dict) else None
        if isinstance(reported, (int, float)):
            leg_options["provider_reported_usd"] = float(reported)

        identity = {
            "product": tiered(r.product, "authoritative"),
            "provider": tiered(r.provider, "authoritative"),
            # Verbatim selector label; backend id NOT inferred (SPEC 6.3).
            "model_or_selector": tiered(r.model_or_selector, "proxy_observed"),
            "auth_billing_path": tiered("product_blackbox", "authoritative"),
            "permission_profile": tiered(SUBJECT_PERMISSION_PROFILE, "authoritative"),
        }
        if r.effort_pin:
            # The effort tier we PINNED, carried verbatim inside the selector label
            # we passed. Authoritative as a condition (it is what we asked for); it
            # is not a claim about what the product did internally.
            identity["reasoning_config"] = tiered(
                f"selector_suffix:{r.effort_pin}", "authoritative")
        return AttemptOutcome(identity=identity, leg_options=leg_options,
                              invocation=invocation)
