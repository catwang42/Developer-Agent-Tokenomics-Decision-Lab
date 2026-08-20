"""Controlled harness runner (SPEC 2.1–2.3, 2.7).

Turns ``(task, configuration/policy, manifest)`` into an immutable event log plus a
derived, validated run summary. Exit 0 only when the audit-grade telemetry
validator passes on the completed run directory.

Design (see plans/PHASE-3-harness-feasibility.md):
  * Adapters emit telemetry events; they never write the summary, run the gate, or
    fabricate usage (missing usage -> ``unavailable``, not 0).
  * The runner owns the clock, the acceptance gate (deterministic, independent of
    the generating model — SPEC 2.6), policy semantics (P0 static / P1 cheap-first
    escalation), and cost derivation under the declared cost basis.
  * ``--dry-run`` uses the synthetic :class:`StubAdapter` and a synthetic gate — no
    model spend, no clone, no network — and writes ONLY under ``--out-root`` (never
    ``results/``). A live run refuses to start unless ``LAB_ALLOW_SPEND=1`` (set
    only under a CP-SPEND-approved invocation).

Every volatile name/price resolves through the delivery manifest (SPEC 1.4); the
runner refuses to start if any required field is missing or still a placeholder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import yaml

from harness.adapters import REAL_ADAPTERS, ResolvedModel, StubAdapter
from harness.adapters import agy as agy_adapter
from harness.adapters.base import (
    SUBJECT_PROFILE_CONTAINER_AGENT,
    SUBJECT_PROFILE_CONTAINER_GATE,
    SUBJECT_PROFILE_HOST,
    AttemptSpec,
    DelegatedLeg,
    DelegationPlan,
    cli_version,
)
from harness.container import egress as egress_mod
from harness.container.exec import (
    TARGET_AGENT,
    TARGET_GATE,
    ContainerExecutor,
    ContainerLaunch,
    agent_build_args,
    agent_container_env,
    agent_container_prefix,
    agent_credential_mounts,
    agent_image_tag,
    agent_volume_name,
    assert_image_uid_matches_host,
    build_subject_image,
    create_volume,
    image_exists,
    remove_volume,
    subject_image_tag,
)
from harness.results.record import build_result_record
from harness.runner import delegation
from harness.telemetry.costing import cost_for_legs, load_prices
from harness.telemetry.telemetry import EventLog, derive_summary, tiered, unavailable, validate

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COST_BASES = ("marginal_api_cost", "allocated_subscription_cost",
              "provider_reported_cost", "cost_unavailable")

# Declared qualifications of a cost_basis (manifest `cost_basis_qualifier`). The
# schema's cost_basis enum is FROZEN at COST_BASES and widening it is a CP-SCHEMA
# decision; a qualifier says how the basis was derived without touching the enum.
# Closed list on purpose — an unrecognised qualifier is a manifest error, because a
# free-text qualifier could smuggle an unreviewed costing claim into a summary.
#   cache_blind_upper_bound — cache token classes were not measurable for this
#   provider, so the figure prices all input at the full input rate and is an UPPER
#   BOUND on real spend (human decision 2026-08-16; manifest notes
#   gemini_cache_blindness; report/findings/vertex-token-metric-surface-2026-08-16.md).
COST_BASIS_QUALIFIERS = ("cache_blind_upper_bound",)

# Per-task offline subject image (batch-2 containerized posture; see
# harness/container/README.md and manifest subject_isolation).
SUBJECT_DOCKERFILE = os.path.join(REPO_ROOT, "harness", "container", "Dockerfile.subject")
CONTAINER_LAB_ROOT = "/lab"

# Fallback agent budget for a task that pins none. Every roster task DOES pin one
# (task.yaml + manifest `agent_timeout_s`, enforced by tests/test_tasks.py); this
# only covers synthetic fixture tasks, and matches the adapters' historical flat
# bound so nothing changes silently for them.
DEFAULT_AGENT_TIMEOUT_S = 1800

# Values that mean "not resolved yet" — a live run must not proceed on these.
_PLACEHOLDERS = {
    "TBD", "DECLARE_AT_DELIVERY", "EXACT-VERSIONED-ID", "YYYY-MM-DD",
    "verbatim label from product", "null", "None", "",
}
_PRODUCT_LABELS = {"PRODUCT_A": "Product A", "PRODUCT_B": "Product B"}
_POLICY_FILES = {"P0": "p0-baseline.yaml", "P1": "p1-cheap-first.yaml",
                 "P2": "p2-delegation.yaml"}

# The telemetry schema (CP-SCHEMA) enumerates the configuration ids a summary may
# carry; a run whose id is outside it cannot be recorded, however well it runs, so
# tests assert the harness and the enum agree.
TELEMETRY_SCHEMA = os.path.join(REPO_ROOT, "harness", "telemetry", "schema-v2.json")


class RunnerError(Exception):
    """A configuration/resolution problem that must stop the run before any work."""


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_yaml(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _is_placeholder(val: Any) -> bool:
    return val is None or str(val).strip() in _PLACEHOLDERS or "YYYY" in str(val)


def _opt_str(val: Any) -> Optional[str]:
    """A declared condition as a string, or None when absent/placeholder."""
    return None if _is_placeholder(val) else str(val).strip()


def _require_resolved(field: str, val: Any, model_ref: str) -> Any:
    if _is_placeholder(val):
        raise RunnerError(
            f"manifest {model_ref}.{field} is unresolved ({val!r}); fill the delivery "
            f"manifest (CP-SPEND) before a live run, or use --dry-run with a synthetic manifest"
        )
    return val


# --------------------------------------------------------------------------- #
# Manifest resolution (SPEC 1.4)
# --------------------------------------------------------------------------- #
def resolve_model(manifest: Dict[str, Any], model_ref: str, product: str) -> ResolvedModel:
    """Resolve a model_ref to a concrete, priced model or verbatim selector.

    Refuses (RunnerError) on a missing entry, unresolved placeholder, or bad
    cost_basis — this is exactly what keeps live runs from starting before the
    manifest is filled at CP-SPEND.
    """
    entry = (manifest.get("configurations") or {}).get(model_ref)
    if not entry:
        raise RunnerError(f"manifest has no configuration for model_ref {model_ref!r}")

    provider = _require_resolved("provider", entry.get("provider"), model_ref)
    cost_basis = _require_resolved("cost_basis", entry.get("cost_basis"), model_ref)
    if cost_basis not in COST_BASES:
        raise RunnerError(f"{model_ref}.cost_basis {cost_basis!r} not in {COST_BASES}")
    qualifier = _opt_str(entry.get("cost_basis_qualifier"))
    if qualifier is not None and qualifier not in COST_BASIS_QUALIFIERS:
        raise RunnerError(
            f"{model_ref}.cost_basis_qualifier {qualifier!r} not in "
            f"{COST_BASIS_QUALIFIERS}; a qualifier changes how a cost figure must be "
            f"read, so a new one is a human decision, not a manifest free-text field"
        )
    surface = entry.get("product_surface")

    region = entry.get("region")
    region = None if _is_placeholder(region) else region
    seat = entry.get("seat_allocation_usd")
    seat = float(seat) if isinstance(seat, (int, float)) else None

    if surface == "controlled_api":
        model_id = _require_resolved("model_id", entry.get("model_id"), model_ref)
        return ResolvedModel(
            provider=provider, model_or_selector=model_id, model_id=model_id,
            cost_basis=cost_basis, product=product, product_surface=surface,
            region=region, model_confidence="authoritative", seat_allocation_usd=seat,
            cost_basis_qualifier=qualifier,
        )
    if surface == "product_blackbox":
        selector = _require_resolved("selector_label", entry.get("selector_label"), model_ref)
        # Pinned run conditions travel with the resolution so the adapter enforces
        # them (version mismatch -> refuse before spend) instead of the runner
        # silently tolerating a drifted product. Absent block => no pin declared.
        cond = entry.get("conditions") or {}
        # model_id stays None — the backend id is never inferred (SPEC 6.3).
        return ResolvedModel(
            provider=provider, model_or_selector=selector, model_id=None,
            cost_basis=cost_basis, product=product, product_surface=surface,
            region=region, model_confidence="proxy_observed", seat_allocation_usd=seat,
            cost_basis_qualifier=qualifier,
            product_version_pin=_opt_str(cond.get("agy_version")),
            print_timeout=_opt_str(cond.get("print_timeout")),
            effort_pin=_opt_str(cond.get("effort")),
        )
    raise RunnerError(f"{model_ref}.product_surface {surface!r} unknown (controlled_api|product_blackbox)")


# --------------------------------------------------------------------------- #
# Run plan (which legs, which adapter, which policy)
# --------------------------------------------------------------------------- #
@dataclass
class LegPlan:
    leg_id: str
    role: str
    resolved: ResolvedModel


@dataclass
class RunPlan:
    adapter_name: str
    legs: List[LegPlan]
    policy: str  # "static" | "cheap_first" | "scripted_delegation" | "workflow"
    # Set only under scripted delegation (P2): the pinned split's legs, brief and
    # executor binding, handed to the adapter as ONE attempt that bills two models.
    delegation: Optional[DelegationPlan] = None


def _delegation_plan(pol: Dict[str, Any], manifest: Dict[str, Any], task: Optional["Task"],
                     *, require_frozen: bool) -> Tuple[List[LegPlan], DelegationPlan]:
    """Build P2's two legs and their pinned split (SPEC 2.1b B3 / 2.1c).

    Everything that could make the delegation ambiguous is refused here rather than
    at run time: no task, no split file, a split that disagrees with the task's own
    write scope, a split whose hash is not the manifest's pin, or (for a live run) a
    split that has not been frozen by human review.
    """
    if task is None:
        raise RunnerError(
            "P2 (scripted delegation) is defined by the task's pinned split file, so "
            "the plan cannot be built without a task"
        )
    if pol.get("runtime_model_choice_routes_work") is not False:
        raise RunnerError(
            "p2-delegation.yaml must declare runtime_model_choice_routes_work: false — "
            "work assigned by a runtime decision is B4 (P3), not B3, and would be "
            "recorded under the wrong family"
        )
    product = _PRODUCT_LABELS["PRODUCT_A"]
    conductor = resolve_model(manifest, pol["conductor_model_ref"], product)
    executor = resolve_model(manifest, pol["executor_model_ref"], product)
    agent_name = ((pol.get("mechanism") or {}).get("executor_agent_name")
                  or delegation.EXECUTOR_LEG_ID)
    try:
        split = delegation.load_split(task.task_dir, repo_root=REPO_ROOT,
                                      expected_task_id=task.task_id)
        delegation.validate_against_task(split, task.task_yaml)
        delegation.check_pin(split, manifest, task.manifest_key or "",
                             require_frozen=require_frozen)
    except delegation.SplitError as exc:
        raise RunnerError(str(exc)) from exc

    legs = [LegPlan(delegation.CONDUCTOR_LEG_ID, "conductor", conductor),
            LegPlan(delegation.EXECUTOR_LEG_ID, "executor", executor)]
    plan = DelegationPlan(
        legs=tuple(DelegatedLeg(leg.leg_id, leg.role, leg.resolved) for leg in legs),
        brief=delegation.render_brief(split, executor_agent=agent_name),
        agents_json=delegation.executor_agent_json(
            split, agent_name=agent_name,
            model_id=executor.model_id or executor.model_or_selector),
        agent_name=agent_name,
        provenance=delegation.telemetry_payload(split),
    )
    return legs, plan


# --------------------------------------------------------------------------- #
# Configuration -> routing policy, by reference (SPEC 2.1c)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ResolvedPolicy:
    """A routing policy resolved from a configuration's ``policy_file`` reference."""
    policy_id: str
    rel_path: str
    sha256: str          # over the RAW FILE BYTES — what the manifest pins
    doc: Dict[str, Any]

    @property
    def rules(self) -> List[Any]:
        return list(self.doc.get("rules") or [])

    @property
    def label(self) -> str:
        return f"{self.policy_id}@{os.path.basename(self.rel_path)}:sha256:{self.sha256[:12]}"


def load_policy_file(rel_path: str) -> Tuple[Dict[str, Any], str]:
    """Parse a policy file and hash its raw bytes (comments included)."""
    path = rel_path if os.path.isabs(rel_path) else os.path.join(REPO_ROOT, rel_path)
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise RunnerError(f"policy file {rel_path} cannot be read: {exc}") from exc
    return yaml.safe_load(raw.decode("utf-8")) or {}, hashlib.sha256(raw).hexdigest()


def policy_manifest_pin(manifest: Dict[str, Any], policy_id: str) -> Dict[str, Any]:
    return ((manifest.get("routing_policies") or {}).get(policy_id) or {})


def resolve_config_policy(cfg: Dict[str, Any], config_id: str,
                          manifest: Optional[Dict[str, Any]] = None,
                          *, require_pin: bool = False) -> Optional[ResolvedPolicy]:
    """Resolve the routing policy a configuration references (SPEC 2.1c).

    A configuration declares the *stack*; a policy declares the *routing decision*.
    C5 references P3 by path so its delegation rules are hash-pinned rather than
    inline — which is what makes "which rules did this run execute?" answerable from
    the manifest. Returns ``None`` for a configuration that declares no routing
    decision at all (C1–C4 are static single-leg stacks).

    Refuses a configuration that carries BOTH a reference and inline ``rules`` (two
    copies drift, and only one of them is hashed), a reference whose ``policy_id``
    disagrees with ``policy_ref``, a policy that does not declare it governs this
    configuration, and a file whose bytes no longer match the manifest pin.
    """
    if "rules" in cfg:
        raise RunnerError(
            f"{config_id}.yaml carries inline 'rules'; routing rules live in the "
            f"referenced policy file (SPEC 2.1c) so they are hash-pinned — a second "
            f"inline copy would drift unhashed"
        )
    rel_path = cfg.get("policy_file")
    if not rel_path:
        return None
    doc, sha = load_policy_file(rel_path)
    policy_id = str(doc.get("policy_id") or "")
    declared = cfg.get("policy_ref")
    if declared and policy_id != declared:
        raise RunnerError(
            f"{config_id}.yaml references {declared} but {rel_path} declares "
            f"policy_id {policy_id or '<missing>'}"
        )
    governs = doc.get("governs") or []
    if governs and config_id not in governs:
        raise RunnerError(
            f"{rel_path} ({policy_id}) governs {list(governs)}, not {config_id}"
        )
    pin = policy_manifest_pin(manifest or {}, policy_id)
    if not pin:
        if require_pin:
            raise RunnerError(
                f"manifest routing_policies.{policy_id}.sha256 is missing; {policy_id}'s "
                f"manifest pin is its policy hash (SPEC 2.1c) and no {config_id} run may "
                f"be cited in workshop material without it"
            )
    else:
        pinned = str(pin.get("sha256") or "").replace("sha256:", "")
        if pinned != sha:
            raise RunnerError(
                f"{rel_path} sha256 {sha} does not match the manifest pin "
                f"{pinned or '<empty>'} — the policy changed after it was pinned. "
                f"Re-pin it (and, if it was frozen, re-freeze it) before running."
            )
    return ResolvedPolicy(policy_id=policy_id, rel_path=rel_path, sha256=sha, doc=doc)


def build_plan(config_id: str, manifest: Dict[str, Any], task: Optional["Task"] = None,
               *, require_frozen: bool = True) -> RunPlan:
    cfg_dir = os.path.join(REPO_ROOT, "harness", "configurations")
    pol_dir = os.path.join(REPO_ROOT, "harness", "policies")

    if config_id in _POLICY_FILES:  # P0 / P1 / P2 run on the controlled harness (Product A).
        pol = _load_yaml(os.path.join(pol_dir, _POLICY_FILES[config_id]))
        product = _PRODUCT_LABELS["PRODUCT_A"]
        if config_id == "P0":
            r = resolve_model(manifest, pol["model_ref"], product)
            return RunPlan("claude_code", [LegPlan("main", "solver", r)], "static")
        if config_id == "P2":
            legs, dele = _delegation_plan(pol, manifest, task, require_frozen=require_frozen)
            return RunPlan(pol.get("adapter", "claude_code"), legs,
                           "scripted_delegation", delegation=dele)
        econ = resolve_model(manifest, pol["attempt_model_ref"], product)
        strong = resolve_model(manifest, pol["escalate_to_model_ref"], product)
        return RunPlan("claude_code", [
            LegPlan("economical_attempt", "economical", econ),
            LegPlan("strong_attempt", "strong", strong),
        ], "cheap_first")

    cfg = _load_yaml(os.path.join(cfg_dir, f"{config_id}.yaml"))
    if not cfg:
        raise RunnerError(f"no configuration or policy named {config_id!r}")

    # The routing decision is resolved by reference and hash-checked against the
    # manifest before any work happens (SPEC 2.1c; C5 -> P3). Validation only: the
    # rules describe how the run is read, not how it executes, so this does not
    # change what a run does — it stops a run whose policy drifted from its pin.
    resolve_config_policy(cfg, config_id, manifest)

    if config_id == "C5":  # integrated workflow: conductor + executor, both billed.
        legs_cfg = cfg.get("legs") or {}
        legs: List[LegPlan] = []
        for leg_id in ("conductor", "executor"):
            spec = legs_cfg.get(leg_id) or {}
            product = _PRODUCT_LABELS.get(spec.get("product_ref"), spec.get("product_ref", leg_id))
            legs.append(LegPlan(leg_id, leg_id, resolve_model(manifest, spec["model_ref"], product)))
        return RunPlan(cfg.get("adapter", "hybrid_c5"), legs, "workflow")

    # C1/C2/C3/C4: static single leg.
    product = _PRODUCT_LABELS.get(cfg.get("product_ref"), cfg.get("product_ref", "unknown"))
    r = resolve_model(manifest, cfg["model_ref"], product)
    return RunPlan(cfg.get("adapter", "claude_code"), [LegPlan("main", "solver", r)], "static")


def product_b_legs(plan: RunPlan) -> List[str]:
    """Leg ids in ``plan`` billed to Product B (declared, never name-inferred)."""
    return [leg.leg_id for leg in plan.legs
            if leg.resolved.product == _PRODUCT_LABELS["PRODUCT_B"]]


def assert_product_b_isolation(plan: RunPlan, subject_isolation: str,
                               config_id: str = "") -> None:
    """Container is the ONLY admissible isolation for a Product-B leg (SMOKE-3).

    In the screening smoke a host-mode Product-B leg exited 0 with an empty
    ``agent-solution.diff`` while its actual edits landed in the lab's own
    ``tasks/pilot-realworld/.work/repo`` — outside the staged subject tree, inside
    the repository, and in the exact directory the NEXT run stages from. Two runs
    were destroyed: the one with no output, and the one that started from a tree
    already carrying the previous run's solution.

    Host mode cannot be made safe for this product by patching a path: the agent
    runs same-uid with no filesystem namespace, and the product carries
    cross-session workspace memory of absolute host paths (its ``brain/``
    directory), so it can address the lab repo directly no matter where its cwd is.
    The container is what removes those paths from existence. So this is a refusal,
    not a warning, and it fires before anything is staged or spent.

    ``--dry-run`` is exempt: it drives the stub adapter, never launches the
    product, and is how the plan/telemetry path is tested offline.
    """
    legs = product_b_legs(plan)
    if not legs or subject_isolation == "container":
        return
    where = f" ({config_id})" if config_id else ""
    raise RunnerError(
        f"--subject-isolation {subject_isolation!r} is REFUSED for Product-B "
        f"leg(s) {legs}{where}: SMOKE-3 — in host mode this product wrote its "
        f"solution into the lab repo's task working tree instead of the staged "
        f"subject, silently producing an empty diff and contaminating the next "
        f"run's input. Container isolation is the only admissible mode for "
        f"Product B; re-run with --subject-isolation container (or --dry-run, "
        f"which never launches the product)."
    )


# --------------------------------------------------------------------------- #
# Task
# --------------------------------------------------------------------------- #
@dataclass
class Task:
    task_dir: str
    task_id: str
    task_suite_version: str
    prompt: str
    contamination_tier: Optional[str]
    hidden_test_hash: Optional[str]
    gate_type: str = "solution"
    pinned_commit: Optional[str] = None
    task_dir_rel: Optional[str] = None  # repo-root-relative (for the container image)
    manifest_key: Optional[str] = None  # where this task's pins live in the manifest
    #: Workshop-owned agent budget for ONE attempt of this task, in seconds.
    #: Pinned per task because the suite's tasks are not the same size.
    agent_timeout_s: int = DEFAULT_AGENT_TIMEOUT_S
    # The parsed task.yaml, kept so policies that must agree with the task's own
    # declarations (P2's split file vs the gate's write scope) can check, not assume.
    task_yaml: Dict[str, Any] = field(default_factory=dict)


def resolve_agent_timeout(task_id: str, ty: Dict[str, Any],
                          mentry: Dict[str, Any]) -> int:
    """The task's pinned agent budget, cross-checked across its two declarations.

    ``agent_timeout_s`` is a RUN CONDITION: it decides whether a slow attempt is a
    measurement or a right-censored non-result, so it is pinned like any other
    condition — in task.yaml (next to the task it bounds) and in the manifest (the
    single place volatile pins resolve). Both must agree; a disagreement is refused
    rather than resolved by precedence, because either value could be the stale one
    and picking silently would mislabel every run in the batch.

    Absent from both, the adapter default applies — the historical behaviour, kept so
    a synthetic fixture task need not pin one. ``tests/test_tasks.py`` is what
    requires every roster task to pin it in both places.
    """
    declared = {"task.yaml": ty.get("agent_timeout_s"),
                "manifest": mentry.get("agent_timeout_s")}
    values = {}
    for where, raw in declared.items():
        if raw is None:
            continue
        if not isinstance(raw, int) or isinstance(raw, bool) or raw <= 0:
            raise RunnerError(
                f"{task_id}: {where} agent_timeout_s must be a positive integer "
                f"number of seconds, got {raw!r}"
            )
        values[where] = raw
    if len(values) == 2 and values["task.yaml"] != values["manifest"]:
        raise RunnerError(
            f"{task_id}: agent_timeout_s disagrees between task.yaml "
            f"({values['task.yaml']}s) and the manifest ({values['manifest']}s). "
            f"The agent budget is a pinned run condition; reconcile the two rather "
            f"than letting the runner pick one."
        )
    return next(iter(values.values()), DEFAULT_AGENT_TIMEOUT_S)


def load_task(task_arg: str, manifest: Dict[str, Any]) -> Task:
    task_dir = task_arg if os.path.isabs(task_arg) else os.path.join(REPO_ROOT, task_arg)
    ty_path = os.path.join(task_dir, "task.yaml")
    if not os.path.exists(ty_path):
        raise RunnerError(f"no task.yaml at {ty_path}")
    ty = _load_yaml(ty_path)
    mkey = ty.get("manifest_key")
    mentry = (manifest.get(mkey) or {}) if mkey else {}
    sealed = mentry.get("sealed_hidden_test") or {}
    return Task(
        task_dir=task_dir,
        task_id=ty["task_id"],
        task_suite_version=ty.get("task_suite_version", "unversioned"),
        prompt=ty.get("prompt", ""),
        contamination_tier=ty.get("contamination_tier"),
        hidden_test_hash=sealed.get("sha256"),
        gate_type=ty.get("gate_type", "solution"),
        pinned_commit=mentry.get("pinned_commit"),
        task_dir_rel=os.path.relpath(task_dir, REPO_ROOT),
        manifest_key=mkey,
        agent_timeout_s=resolve_agent_timeout(ty.get("task_id", task_dir), ty, mentry),
        task_yaml=ty,
    )


# --------------------------------------------------------------------------- #
# Acceptance gate
# --------------------------------------------------------------------------- #
def synthetic_gate(scenario: str, leg_id: str) -> Tuple[bool, str, Dict[str, Any]]:
    """Deterministic dry-run gate. ``escalate`` fails only the economical attempt."""
    if scenario == "reject":
        passed = False
    elif scenario == "escalate":
        passed = "econ" not in leg_id  # economical_attempt fails; strong passes
    else:  # "accept"
        passed = True
    return passed, ("accepted" if passed else "rejected"), \
        {"synthetic_public_gate": "pass" if passed else "fail"}


def _read_gate_reports(run_dir: str) -> Dict[str, Any]:
    checks: Dict[str, Any] = {}
    for key, name in (("public", "gate-public.json"), ("hidden", "gate-hidden.json")):
        path = os.path.join(run_dir, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                checks[key] = json.load(fh)
    return checks


def _gate_verdict(pub_rc: int, hid_rc: int, checks: Dict[str, Any]
                  ) -> Tuple[bool, str, Dict[str, Any]]:
    """Combine public+hidden exit codes into a verdict (SPEC 2.6).

    Hidden tests are authoritative: accepted only if public passes AND hidden
    passes; rejected if either fails; ``error`` if hidden tests are unavailable
    (cannot authoritatively accept — e.g. the sealed set is not present).
    """
    public_pass = pub_rc == 0
    if hid_rc == 2:
        return False, "error", checks  # hidden unavailable — cannot authoritatively accept
    if hid_rc == 1 or not public_pass:
        return False, "rejected", checks
    return True, "accepted", checks


def hidden_tests_dir(task_dir: str) -> str:
    """HOST location of the sealed hidden set for ``task_dir``.

    Mirrors check-hidden.sh's own rule (``HIDDEN_TESTS_DIR`` overrides, else
    ``$TASK_DIR/hidden``) so the host gate and the container gate resolve the same
    directory. The container gate needs it explicitly because it must MOUNT the
    directory — the sealed set is never baked into an image (.dockerignore excludes
    ``**/hidden/``), so a path alone would resolve to nothing inside the container.
    """
    override = os.environ.get("HIDDEN_TESTS_DIR")
    if override:
        return os.path.abspath(override)
    return os.path.join(os.path.abspath(task_dir), "hidden")


def real_gate(task_dir: str, run_dir: str, subject_dir: str
              ) -> Tuple[bool, str, Dict[str, Any]]:
    """Run the Phase 2 deterministic gate on the HOST against the subject tree.

    The subject tree is staged OUTSIDE the lab repo (FIX A, ``_setup_subject``), so
    the gate is pointed at it via ``TASK_WORKDIR`` (lib.sh: ``SUBJECT_DIR =
    TASK_WORKDIR/repo``). ``subject_dir`` is ``<staged>/repo``, so its parent is the
    workdir. ``TASK_DIR`` still points at the in-repo task dir — the gate is trusted
    harness code and legitimately reads ``gate/``, ``tests/``, ``hidden/`` from
    there; only the *agent* is denied a relative path to them.
    """
    gate_dir = os.path.join(REPO_ROOT, "harness", "task-tools", "gate")
    pub_report = os.path.join(run_dir, "gate-public.json")
    hid_report = os.path.join(run_dir, "gate-hidden.json")
    workdir = os.path.dirname(os.path.abspath(subject_dir))

    env = {**os.environ, "TASK_DIR": task_dir, "TASK_WORKDIR": workdir,
           "GATE_REPORT": pub_report}
    pub_rc = subprocess.run(  # noqa: S603
        ["bash", os.path.join(gate_dir, "check-public.sh")], env=env, check=False,
    ).returncode
    env_h = {**os.environ, "TASK_DIR": task_dir, "TASK_WORKDIR": workdir,
             "HIDDEN_REPORT": hid_report}
    hid_rc = subprocess.run(  # noqa: S603
        ["bash", os.path.join(gate_dir, "check-hidden.sh")], env=env_h, check=False,
    ).returncode
    return _gate_verdict(pub_rc, hid_rc, _read_gate_reports(run_dir))


def container_gate(launch: ContainerLaunch, task: "Task", run_dir: str
                   ) -> Tuple[bool, str, Dict[str, Any]]:
    """Run the deterministic gate OFFLINE inside the subject-gate container (--network=none).

    Grades the tree at ``/lab/<task>/.work/repo``. When the agent leg ran in its own
    container, ``launch.agent_volume`` is the named volume holding the agent's edits
    and it is mounted over that path here — so the gate grades what the agent
    actually produced, across two images, without either image needing the other's
    contents. With no agent volume this grades the pristine baked tree (the
    containerized pre-modification gate).

    ``run_dir`` is mounted at ``/out`` so the gate's JSON reports land on the host.
    The gate is always ``--network=none``; the agent leg's egress never applies here.

    The SEALED HIDDEN SET is mounted read-only at ``<task>/hidden``. It is never
    baked into any image — ``.dockerignore`` excludes ``**/hidden/`` from every
    build context, by design ("the runtime gate needs only gate/ + tests/ + mounted
    hidden/"). Without the mount, check-hidden.sh finds no sealed tests, reports
    ``awaiting_human``, exits 2, and ``_gate_verdict`` turns EVERY containerized run
    into ``error`` — a batch that bills real spend and grades nothing. Mounting is
    what makes the containerized posture gradable at all. Read-only: sealed material
    is human-held and its content hash is frozen in the manifest, so a gate run must
    not be able to alter it; a sealed runner needing scratch space uses ``/tmp``.
    """
    ex = ContainerExecutor(launch.image)
    task_c = f"{CONTAINER_LAB_ROOT}/{task.task_dir_rel}"
    work_c = f"{task_c}/.work"
    repo_c = f"{work_c}/repo"
    mounts = [(run_dir, "/out", "rw")]
    if launch.agent_volume:
        mounts.append((launch.agent_volume, repo_c, "rw"))
    base_env = {"TASK_DIR": task_c, "TASK_WORKDIR": work_c}

    # Absent on the host = genuinely unsealed: leave the mount off and let the gate
    # report awaiting_human. Never mount a non-existent source — docker would create
    # it, silently planting a root-owned empty `hidden/` in the task directory.
    hidden_host = hidden_tests_dir(task.task_dir)
    if os.path.isdir(hidden_host):
        hidden_c = f"{task_c}/hidden"
        mounts.append((hidden_host, hidden_c, "ro"))
        base_env["HIDDEN_TESTS_DIR"] = hidden_c

    pub = ex.run(
        ["bash", f"{CONTAINER_LAB_ROOT}/harness/task-tools/gate/check-public.sh"],
        mounts=mounts, network="none", workdir=repo_c,
        env={**base_env, "GATE_REPORT": "/out/gate-public.json"},
    )
    hid = ex.run(
        ["bash", f"{CONTAINER_LAB_ROOT}/harness/task-tools/gate/check-hidden.sh"],
        mounts=mounts, network="none", workdir=repo_c,
        env={**base_env, "HIDDEN_REPORT": "/out/gate-hidden.json"},
    )
    return _gate_verdict(pub.returncode, hid.returncode, _read_gate_reports(run_dir))


# --------------------------------------------------------------------------- #
# Cache-protocol contract (methodology/cache-protocol.md rule 4)
# --------------------------------------------------------------------------- #
def assert_cache_contract(events: List[Dict[str, Any]], cache_state: str) -> List[str]:
    """Verify the emitted event log honours the declared cache state.

    Freshness is proven from the immutable log, not asserted by the runner: every
    ``model_call_started`` event carries the ``session_id`` the adapter actually
    used and whether it ``resumed``. For ``cold`` every leg must be a fresh,
    identified session (a new id, ``resumed=False``); for ``warm-series`` every
    leg must resume an identified session. Returns a list of violations (empty =
    contract satisfied).
    """
    starts = [e for e in events if e.get("event_type") == "model_call_started"]
    reasons: List[str] = []
    if not starts:
        return ["cache-contract: no model_call_started event to prove session freshness"]
    for e in starts:
        leg = e.get("leg", "?")
        sid = e.get("session_id")
        resumed = e.get("resumed")
        if not sid:
            reasons.append(f"cache-contract: leg {leg!r} model_call_started has no session_id")
        if cache_state == "cold" and resumed:
            reasons.append(
                f"cache-contract: leg {leg!r} resumed a session under cold cache-state "
                f"(cold requires a fresh session — cache-protocol rule 1)"
            )
        if cache_state == "warm-series" and not resumed:
            reasons.append(
                f"cache-contract: leg {leg!r} did not resume a session under warm-series "
                f"(warm runs continue the cold run's session — cache-protocol rule 2)"
            )
    return reasons


# --------------------------------------------------------------------------- #
# Cumulative-spend kill-switch (CP-SPEND option a — batch cost ceiling)
# --------------------------------------------------------------------------- #
def cumulative_spend_usd(batch_dir: str) -> Tuple[float, int, int]:
    """Sum realized marginal operating USD across completed runs in ``batch_dir``.

    Reads every sibling ``summary.json`` (the event-log-derived cost artifact) and
    sums each leg's numeric ``marginal_operating_usd`` value. This is per-leg — so
    it captures both single-basis runs and mixed-basis workflows (C5), whose
    top-level cost is intentionally ``unavailable``. A leg whose cost is
    ``unavailable`` (e.g. Product B not exposing tokens) is COUNTED, never
    zero-imputed (CLAUDE.md rule 3): the returned total is therefore the
    KNOWN-spend floor, and the unavailable-leg count flags that real spend may be
    higher. Returns ``(total_usd, n_runs, n_unavailable_legs)``.
    """
    total = 0.0
    n_runs = 0
    n_unavailable = 0
    if not os.path.isdir(batch_dir):
        return 0.0, 0, 0
    for name in sorted(os.listdir(batch_dir)):
        summary_path = os.path.join(batch_dir, name, "summary.json")
        if not os.path.isfile(summary_path):
            continue
        try:
            with open(summary_path, encoding="utf-8") as fh:
                summary = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue  # a half-written or corrupt sibling never inflates/masks spend
        n_runs += 1
        for leg in summary.get("legs", []):
            value = (leg.get("marginal_operating_usd") or {}).get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                total += float(value)
            else:
                n_unavailable += 1
    return round(total, 6), n_runs, n_unavailable


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #
def _gate(dry_run: bool, scenario: str, leg_id: str, task: "Task",
          run_dir: str, launch: Optional[ContainerLaunch], subject_dir: str
          ) -> Tuple[bool, str, Dict[str, Any]]:
    if dry_run:
        return synthetic_gate(scenario, leg_id)
    if launch is not None:  # containerized posture: grade offline in the container
        return container_gate(launch, task, run_dir)
    return real_gate(task.task_dir, run_dir, subject_dir)


def execute(plan: RunPlan, task: Task, adapter, subject_dir: str, run_dir: str,
            emit, *, dry_run: bool, scenario: str,
            cache_state: str, base_session: str, resume: bool,
            launch: Optional[ContainerLaunch] = None
            ) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    """Run the plan's policy, emitting events.

    Returns ``(identity, leg_options_by_id, invocations)`` — ``invocations`` is the
    ordered list of exact CLI commands each leg executed (for the invocation.txt
    run artifact; provenance, not telemetry).
    """
    identity: Dict[str, Any] = {}
    leg_options: Dict[str, Dict[str, Any]] = {}
    invocations: List[Dict[str, Any]] = []

    def record_outcome(leg: LegPlan, outcome: Any) -> None:
        """Fold one adapter outcome into the run's identity, costing options, argv log."""
        if not identity:  # top-level identity from the primary leg; legs[] hold per-leg detail
            identity.update(outcome.identity)
        opts = dict(outcome.leg_options)
        if leg.resolved.seat_allocation_usd is not None:
            opts.setdefault("seat_allocation_usd", leg.resolved.seat_allocation_usd)
        leg_options[leg.leg_id] = opts
        if outcome.invocation:
            invocations.append(outcome.invocation)

    def run_leg(leg: LegPlan, leg_index: int) -> None:
        # Session ids MUST be valid UUIDs — the claude CLI's --session-id rejects
        # anything else (and then prints a non-JSON error, losing all usage
        # telemetry). Warm-series and the first cold leg use base_session (a valid
        # UUID, operator-supplied for a resumable warm series or freshly minted);
        # any further cold leg (e.g. P1's strong attempt) gets its own fresh UUID
        # so each cold leg is an independent, provably-fresh session.
        if resume or leg_index == 0:
            leg_session = base_session
        else:
            leg_session = str(uuid.uuid4())
        spec = AttemptSpec(leg.leg_id, leg.role, leg.resolved, task.prompt,
                           cache_state=cache_state, session_id=leg_session,
                           resume=resume, timeout_s=task.agent_timeout_s)
        record_outcome(leg, adapter.run_attempt(spec, subject_dir, emit))

    # Fix 5: archive the agent's diff the instant its work is complete and BEFORE
    # any gate step mutates the tree (the gate restores src/tests and applies
    # test_compat_patch, which otherwise gets attributed to the agent). Host-mode
    # real runs only; idempotent so the P1 branch cannot double-write.
    archived = {"done": False}

    def archive_pre_gate() -> None:
        if dry_run or archived["done"]:
            return
        if launch is not None and launch.agent_volume:
            # Container mode: the tree is in a Docker volume, not on the host.
            _archive_agent_diff_container(launch, task, run_dir)
            archived["done"] = True
        elif subject_dir:
            _archive_agent_diff(subject_dir, run_dir)  # agent-solution.diff (pre-gate)
            archived["done"] = True

    itr: Optional[str] = None
    cr: Optional[str] = None

    if plan.policy == "cheap_first":
        econ, strong = plan.legs
        itr = "economical"
        run_leg(econ, 0)
        # The economical attempt has exited; capture it before the gate touches the
        # tree. NOTE: if this run escalates, the strong leg necessarily runs AFTER
        # this gate (the cheap-first design is interleaved), so agent-solution.diff
        # reflects the pre-gate economical attempt; the final tree (incl. the strong
        # leg) is preserved in post-gate.diff below. No escalation fired in batch 2.
        archive_pre_gate()
        passed, result, checks = _gate(dry_run, scenario, econ.leg_id, task, run_dir,
                                       launch, subject_dir)
        if passed:
            cr = "economical"
        else:
            # Escalate: record the failed attempt explicitly (its cost lives on the
            # economical_attempt leg) so P1 cells record failed-attempt costs every run.
            emit("retry", leg=econ.leg_id, reason="gate_fail")
            emit("escalation", from_route="economical", to_route="strong",
                 reason="gate_fail", failed_leg=econ.leg_id)
            run_leg(strong, 1)
            passed, result, checks = _gate(dry_run, scenario, strong.leg_id, task, run_dir,
                                           launch, subject_dir)
            cr = "strong"
    elif plan.policy == "scripted_delegation":
        # P2/B3: ONE product invocation that bills every leg the pinned split
        # declares. The conductor leg carries the attempt; the adapter splits the
        # product's per-model usage metadata across the legs (it does not decide the
        # assignment — the split file did that before the run).
        conductor, *others = plan.legs
        spec = AttemptSpec(conductor.leg_id, conductor.role, conductor.resolved,
                           task.prompt, cache_state=cache_state,
                           session_id=base_session, resume=resume,
                           delegation=plan.delegation,
                           timeout_s=task.agent_timeout_s)
        outcome = adapter.run_attempt(spec, subject_dir, emit)
        record_outcome(conductor, outcome)
        for leg in others:
            # Per-leg costing options for a leg that shares the attempt: only what
            # the manifest declares for it (an adapter outcome describes the attempt,
            # and attributing its options to a second leg would double-count).
            leg_options[leg.leg_id] = (
                {"seat_allocation_usd": leg.resolved.seat_allocation_usd}
                if leg.resolved.seat_allocation_usd is not None else {}
            )
        itr = "scripted_split"
        cr = "scripted_split"
        archive_pre_gate()
        passed, result, checks = _gate(dry_run, scenario, conductor.leg_id, task,
                                       run_dir, launch, subject_dir)
    else:  # static | workflow
        for i, leg in enumerate(plan.legs):
            run_leg(leg, i)
        archive_pre_gate()  # all agent legs done; archive before the gate mutates the tree
        passed, result, checks = _gate(dry_run, scenario, "main", task, run_dir,
                                       launch, subject_dir)

    # Optional post-gate snapshot for provenance — the tree AFTER the gate's own
    # edits (test_compat_patch, restores). Written to a SEPARATE file, never merged
    # into agent-solution.diff (Fix 5). Host-mode real runs only.
    if not dry_run and subject_dir:
        _archive_agent_diff(subject_dir, run_dir, filename="post-gate.diff")

    emit("acceptance", result=result, gate_checks=checks,
         intention_to_route=itr, completed_route=cr)
    return identity, leg_options, invocations


# --------------------------------------------------------------------------- #
# Cost + summary assembly
# --------------------------------------------------------------------------- #
def _leg_billed_tokens(usage: Dict[str, Any]) -> Optional[int]:
    """Sum a leg's available billed token classes; None if none are available."""
    total, any_avail = 0, False
    for cls in ("input_tokens", "cache_creation_tokens", "cache_read_tokens", "output_tokens"):
        field = usage.get(cls) or {}
        if field.get("confidence") != "unavailable" and field.get("value") is not None:
            total += field["value"]
            any_avail = True
    return total if any_avail else None


def _frontier_token_share(legs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Conductor share of tokens across legs — a C5 diagnostic only (never a claim)."""
    per_leg = {leg["leg_id"]: _leg_billed_tokens(leg.get("usage") or {}) for leg in legs}
    if any(v is None for v in per_leg.values()) or "conductor" not in per_leg:
        return unavailable("token counts unavailable on one or more legs")
    total = sum(per_leg.values())
    if total == 0:
        return unavailable("zero total tokens")
    return tiered(round(per_leg["conductor"] / total, 6), "derived")


def build_economics(legs: List[Dict[str, Any]], prices: Dict[str, Any],
                    leg_options: Dict[str, Dict[str, Any]], pricing_snapshot: str
                    ) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    """Cost every leg under its own basis and aggregate (SPEC 2.7 two views).

    A single-basis run reports the aggregate under that basis. A mixed-basis
    workflow (e.g. C5 conductor subscription + executor provider-reported) does
    NOT get a single-basis aggregate placed beside incompatible bases — the top
    level is marked ``cost_unavailable`` and per-leg costs (precise, available)
    are the source of truth.

    ``cost_basis_qualifier`` propagates UP, not sideways: if ANY leg's basis is
    qualified, the run-level figure inherits the qualification, because a total
    that contains one cache-blind upper bound is itself an upper bound. C5 is the
    case that matters — a Claude conductor plus a cache-blind Gemini executor.
    """
    agg = cost_for_legs(legs, prices, leg_options=leg_options)
    per_leg_views = {v["leg_id"]: v for v in agg["legs"]}

    bases = {leg["cost_basis"] for leg in legs}
    uniform = next(iter(bases)) if len(bases) == 1 else None
    qualifiers = sorted({q for leg in legs if (q := leg.get("cost_basis_qualifier"))})

    econ: Dict[str, Any] = {"pricing_snapshot": os.path.basename(pricing_snapshot)}
    if qualifiers:
        econ["cost_basis_qualifier"] = ",".join(qualifiers)
    if uniform:
        econ["cost_basis"] = uniform
        econ["marginal_operating_usd"] = agg["marginal_operating_usd"]
        econ["fully_allocated_usd"] = agg["fully_allocated_usd"]
        econ["total_cost_usd"] = agg["fully_allocated_usd"]
    else:
        econ["cost_basis"] = "cost_unavailable"
        econ["marginal_operating_usd"] = unavailable("mixed cost bases across legs; see per-leg")
        econ["fully_allocated_usd"] = unavailable("mixed cost bases across legs; see per-leg")
    return econ, per_leg_views


def assemble_and_validate(events: List[Dict[str, Any]], *, run_id: str, task: Task,
                          config_id: str, manifest_ref: str, identity: Dict[str, Any],
                          plan: RunPlan, prices: Dict[str, Any],
                          leg_options: Dict[str, Dict[str, Any]], pricing_snapshot: str,
                          run_dir: str) -> Tuple[bool, List[str]]:
    """Two-pass derive (usage -> cost -> final summary), write, and audit-validate."""
    ident = dict(identity)
    if task.contamination_tier:
        ident["contamination_tier"] = task.contamination_tier

    common = dict(
        run_id=run_id, task_id=task.task_id, task_suite_version=task.task_suite_version,
        configuration_id=config_id, manifest_ref=manifest_ref, identity=ident,
        hidden_test_hash=task.hidden_test_hash,
    )
    # Pass 1: derive event-sourced legs/usage (economics defaulted) to cost from.
    base = derive_summary(events, **common)
    econ, per_leg_views = build_economics(base["legs"], prices, leg_options, pricing_snapshot)

    # Pass 2: final summary with computed economics (deterministic; event-sourced
    # fields are identical to pass 1, so validate() re-derivation still corroborates).
    summary = derive_summary(events, economics=econ, **common)

    # Enrich per-leg cost views + C5 frontier diagnostic (not event-corroborated fields).
    for leg in summary["legs"]:
        view = per_leg_views.get(leg["leg_id"])
        if view:
            leg["marginal_operating_usd"] = view["marginal_operating_usd"]
            leg["fully_allocated_usd"] = view["fully_allocated_usd"]
    if plan.policy == "workflow":
        summary["frontier_token_share"] = _frontier_token_share(summary["legs"])

    with open(os.path.join(run_dir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
    return validate(run_dir)


# --------------------------------------------------------------------------- #
# Subject repo setup (live runs only)
# --------------------------------------------------------------------------- #
def _archive_agent_diff(subject_dir: str, run_dir: str,
                        filename: str = "agent-solution.diff") -> None:
    """Snapshot the subject working tree's diff for provenance (gate-fairness audits).

    Captures the tracked-file diff plus the FULL CONTENT of every untracked file.
    Capturing untracked *content* (not just names) is essential for test-generation
    tasks, where the agent's entire output is new files — a name-only list would
    discard the solution the reset then deletes. ``node_modules`` is excluded;
    ``--no-index`` reads the working tree without touching the index, so the
    subsequent reset is unaffected. Best-effort: a git failure never fails the run.

    WHEN this is called matters (Fix 5): for ``agent-solution.diff`` the runner calls
    it immediately after the agent leg(s) exit and BEFORE any gate step touches the
    tree, so the harness's own edits (e.g. ``test_compat_patch``, test restores) can
    never be attributed to the agent. A post-gate snapshot, if wanted, is written
    separately as ``post-gate.diff`` — never merged into ``agent-solution.diff``.
    """
    try:
        diff = subprocess.run(  # noqa: S603
            ["git", "-C", subject_dir, "diff", "--", ":!node_modules"],
            capture_output=True, text=True, check=False,
        ).stdout
        untracked = subprocess.run(  # noqa: S603
            ["git", "-C", subject_dir, "ls-files", "--others", "--exclude-standard",
             "--", ":!node_modules"],
            capture_output=True, text=True, check=False,
        ).stdout
        # Diff each untracked file against /dev/null so its full content is archived
        # as a proper new-file diff. --no-index never mutates the index or working
        # tree (reset stays deterministic); exit 1 = "differences found", expected.
        untracked_diffs: List[str] = []
        for path in untracked.splitlines():
            if not path.strip():
                continue
            content_diff = subprocess.run(  # noqa: S603
                ["git", "-C", subject_dir, "diff", "--no-index", "--",
                 os.devnull, path],
                capture_output=True, text=True, check=False,
            ).stdout
            if content_diff:
                untracked_diffs.append(content_diff)
        with open(os.path.join(run_dir, filename), "w", encoding="utf-8") as fh:
            fh.write(diff)
            if untracked_diffs:
                fh.write("\n# untracked files (agent-created), full content below:\n")
                fh.write("".join(untracked_diffs))
    except OSError:
        pass


def _archive_agent_diff_container(launch: ContainerLaunch, task: "Task", run_dir: str,
                                  filename: str = "agent-solution.diff") -> None:
    """Same snapshot as ``_archive_agent_diff``, taken INSIDE the gate container.

    In container mode the agent's edits live in a named Docker volume, not in any
    host directory, so the host-side ``git -C subject_dir`` produced nothing and the
    run landed with no provenance diff at all — the gate verdict was the only
    evidence the agent had changed anything. The gate image (task material present,
    ``--network=none``) already mounts that volume to grade it, so the diff is taken
    there, with the same pre-gate timing (Fix 5) as the host path.

    Written from the container's stdout rather than by the container itself: the
    gate image runs as root and would leave a root-owned file in the operator's
    results dir.
    """
    if not launch.agent_volume:
        return
    repo_c = f"{CONTAINER_LAB_ROOT}/{task.task_dir_rel}/.work/repo"
    script = (
        'git diff -- ":!node_modules"; '
        'u="$(git ls-files --others --exclude-standard -- ":!node_modules")"; '
        'if [ -n "$u" ]; then '
        '  echo; echo "# untracked files (agent-created), full content below:"; '
        '  echo "$u" | while IFS= read -r p; do '
        '    [ -n "$p" ] && git diff --no-index -- /dev/null "$p" || true; '
        '  done; '
        'fi'
    )
    res = ContainerExecutor(launch.image).run(
        ["bash", "-lc", script],
        mounts=[(launch.agent_volume, repo_c, "rw")], network="none", workdir=repo_c,
        # The volume is owned by the agent's uid and this image runs as root, so
        # git's safe.directory guard refuses the repo and every command returns
        # empty. Trust this one path by env (never by writing a gitconfig) — the
        # same guard check-public.sh's G0 makes.
        env={"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "safe.directory",
             "GIT_CONFIG_VALUE_0": repo_c},
    )
    try:
        with open(os.path.join(run_dir, filename), "w", encoding="utf-8") as fh:
            fh.write(res.stdout)
    except OSError:
        pass


# Env-var names whose VALUES may carry a credential — redacted in invocation.txt.
# Matched as case-insensitive substrings of the key, so ANTHROPIC_API_KEY,
# CLAUDE_CODE_OAUTH_TOKEN, AWS_SECRET_ACCESS_KEY, *_CREDENTIALS, etc. all mask.
# Non-credential env (PATH, project id, region, model overrides) stays verbatim.
_CREDENTIAL_ENV_PATTERNS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD",
                            "CREDENTIAL", "AUTH", "SESSION", "COOKIE", "PRIVATE")
_REDACTED = "<redacted>"

# Secret-shaped tokens to mask in free-text CLI stdout/stderr (bearer handled
# separately so its "Bearer " prefix survives). Best-effort: catches common
# provider key/token formats not sourced from the environment.
_SECRET_TEXT_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),                                  # Anthropic/OpenAI-style
    re.compile(r"AIza[0-9A-Za-z_\-]{35}"),                                 # Google API key
    re.compile(r"ya29\.[0-9A-Za-z_\-]+"),                                  # Google OAuth token
    re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),  # JWT
)
# Cap stdout/stderr in the artifact so a pathological run cannot write an enormous
# file; generous enough to retain a smoke run's full raw JSON usage block.
_INVOCATION_IO_CAP = 20000


def _redact_env(env: Dict[str, str]) -> Dict[str, str]:
    """Return ``env`` with credential-bearing VALUES masked (keys preserved).

    Redaction is by key name (case-insensitive substring match). The key stays
    visible so a diagnostician still sees which credentials were set, but the secret
    value never lands in the (committed) artifact. Errs toward over-redaction — better
    to mask a benign var than to write a secret.
    """
    out: Dict[str, str] = {}
    for key in sorted(env):
        ku = key.upper()
        out[key] = _REDACTED if any(p in ku for p in _CREDENTIAL_ENV_PATTERNS) else env[key]
    return out


def _redact_text(text: str, env: Dict[str, str]) -> str:
    """Mask credential-bearing values in free-text CLI output (stdout/stderr).

    Two passes: (1) replace, verbatim, the VALUE of every credential-bearing env var
    (so a known secret echoed into output cannot leak); (2) mask common secret token
    formats (:data:`_SECRET_TEXT_PATTERNS` + bearer tokens). Non-secret content — e.g.
    a product's JSON usage block — is preserved for diagnosis. Best-effort, not a
    guarantee; erring toward over-redaction.
    """
    if not text:
        return text
    red = text
    for key, val in sorted(env.items()):
        if val and len(val) >= 6 and any(p in key.upper() for p in _CREDENTIAL_ENV_PATTERNS):
            red = red.replace(val, f"<redacted:{key}>")
    red = re.sub(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-]+", r"\1 <redacted>", red)
    for pat in _SECRET_TEXT_PATTERNS:
        red = pat.sub(_REDACTED, red)
    return red


def _cap_io(text: str) -> str:
    """Bound an stdout/stderr blob for the artifact, marking any truncation."""
    if len(text) <= _INVOCATION_IO_CAP:
        return text
    return text[:_INVOCATION_IO_CAP] + f"\n...[truncated {len(text) - _INVOCATION_IO_CAP} chars]"


def _write_invocation_file(run_dir: str, invocations: List[Dict[str, Any]],
                           env: Dict[str, str]) -> None:
    """Record the exact agent-CLI command(s) executed + their result, for diagnosis.

    A per-run artifact (``invocation.txt``, beside ``agent-solution.diff``) — NOT
    telemetry: never emitted to the event log, never added to summary.json, and no
    schema field is defined for it (CP-SCHEMA frozen). Records, per billing leg, the
    full argv, the adapter's product version, and the CLI's exit code + stdout +
    stderr (a command that produced no output is itself the diagnosis — cf. the C3
    no-output finding). Credential-bearing values are redacted: env values by key
    (:func:`_redact_env`) and any secret echoed into output (:func:`_redact_text`).
    Best-effort: a write failure never fails the run.
    """
    if not invocations:
        return
    try:
        lines: List[str] = [
            "# Per-run agent-CLI invocation(s) — run artifact, NOT telemetry.",
            "# Full argv + product version + exit/stdout/stderr per billing leg;",
            "# credential-bearing values are redacted. Provenance for diagnosis.",
            "",
        ]
        for inv in invocations:
            lines.append(f"## leg: {inv.get('leg', '?')} (role: {inv.get('role', '?')})")
            lines.append(f"product_version: {inv.get('product_version', 'unavailable')}")
            cwd = inv.get("cwd")
            lines.append(f"cwd: {cwd if cwd is not None else '(container: image workdir)'}")
            lines.append(f"exit_code: {inv.get('exit_code', 'unavailable')}")
            lines.append("argv:")
            lines.append(json.dumps(inv.get("argv") or [], ensure_ascii=False))
            lines.append("stdout:")
            lines.append(_cap_io(_redact_text(inv.get("stdout") or "", env)))
            lines.append("stderr:")
            lines.append(_cap_io(_redact_text(inv.get("stderr") or "", env)))
            lines.append("")
        lines.append("## environment (credential-bearing values redacted)")
        for key, val in _redact_env(env).items():
            lines.append(f"{key}={val}")
        lines.append("")
        with open(os.path.join(run_dir, "invocation.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
    except OSError:
        pass


def _ensure_image(task: Task, tag: str, target: str,
                  build_args: Optional[Dict[str, str]] = None) -> None:
    """Build ``tag`` from ``target`` if it is not already present locally.

    Build-time network clones the subject repo, runs ``npm ci`` and installs the
    product CLIs — tooling setup, not model spend (CLAUDE.md rule 5).
    """
    if image_exists(tag):
        return
    print(f"runner: building subject image {tag} (target {target}; build-time "
          f"network; not model spend)", file=sys.stderr)
    proc = build_subject_image(task.task_dir_rel, tag, REPO_ROOT, SUBJECT_DOCKERFILE,
                               target=target, build_args=build_args)
    if proc.returncode != 0:
        raise RunnerError(f"docker build failed for {tag} (rc={proc.returncode})")


def _require_pin(task: Task) -> None:
    if not task.pinned_commit:
        raise RunnerError(
            f"container isolation needs task {task.task_id!r} pinned_commit in the "
            f"manifest to tag/build the subject image"
        )


def _ensure_gate_launch(task: Task, agent_volume: Optional[str] = None) -> ContainerLaunch:
    """The deterministic gate's launch: ``subject-gate`` image, always offline."""
    _require_pin(task)
    tag = subject_image_tag(task.task_id, task.pinned_commit)
    _ensure_image(task, tag, TARGET_GATE)
    return ContainerLaunch(
        image=tag, network=egress_mod.NETWORK_NONE_LABEL,
        agent_volume=agent_volume, profile=SUBJECT_PROFILE_CONTAINER_GATE,
    )


def _ensure_agent_launch(
    task: Task, run_id: str, policy: Optional[egress_mod.EgressPolicy],
    manifest: Dict[str, Any],
    *, network_override: Optional[str] = None,
) -> Tuple[ContainerLaunch, str]:
    """The agent leg's launch: ``subject-agent`` image + credentials + egress.

    Returns ``(launch, network_policy_label)``. The label is what lands verbatim in
    ``identity.network_policy``; it names the allowlist and its hash, so a run under
    a later, wider allowlist is not mistaken for one made under this one.

    With no policy the agent container runs ``--network=none``. That is a legitimate
    posture for exercising the container path without spend, and the label says so
    plainly rather than implying an allowlist was in force.
    """
    _require_pin(task)
    tag = agent_image_tag(task.task_id, task.pinned_commit)
    # The SAME build args build-subject-image.sh resolves. Batch 1 halted at plan
    # index 19 because this call passed none: the first mid-batch auto-build took the
    # Dockerfile's ARG defaults, baked uid 1001, and the guard below refused it.
    try:
        build_args = agent_build_args(manifest, REPO_ROOT)
    except ValueError as exc:
        raise RunnerError(str(exc)) from exc
    _ensure_image(task, tag, TARGET_AGENT, build_args)
    # Before anything can spend: the container user must be able to read the
    # credential mounts. See exec.assert_image_uid_matches_host.
    try:
        assert_image_uid_matches_host(tag)
    except PermissionError as exc:
        raise RunnerError(str(exc)) from exc

    if policy is not None:
        egress_mod.ensure_proxy(policy)
        network = policy.network
        label = policy.label
        env = agent_container_env(policy.proxy_env())
    else:
        network = network_override or egress_mod.NETWORK_NONE_LABEL
        env = agent_container_env()
        label = (
            f"{network}; no-egress-allowlist-in-force"
            if network == egress_mod.NETWORK_NONE_LABEL
            else f"{network}; docker-network-verbatim; no-lab-allowlist-in-force"
        )

    volume = agent_volume_name(run_id)
    create_volume(volume)
    return ContainerLaunch(
        image=tag, network=network, mounts=tuple(agent_credential_mounts()),
        env=env, agent_volume=volume, profile=SUBJECT_PROFILE_CONTAINER_AGENT,
        # Names the run's agent containers so a timeout has something to kill. An
        # unnamed container can only be reached through the docker CLI client the
        # timeout already killed, which is how batch 1 left an orphan running past
        # its own run (exec.kill_container).
        name_prefix=agent_container_prefix(run_id),
    ), label


def _stage_subject_outside_repo(source_repo: str) -> str:
    """Stage the prepared subject repo into a temp dir OUTSIDE the lab repo (FIX A).

    Root cause of the subject-isolation leak: with the agent's cwd at
    ``<TASK_DIR>/.work/repo`` inside the lab repo, ``../../canonical``,
    ``../../hidden`` and ``../../task.yaml`` were reachable by relative traversal.
    Copying ONLY the subject repo to a temp dir whose ancestors contain none of the
    lab's task material closes that path: from ``<staged>/repo`` no ``../`` chain
    reaches canonical/, hidden/, or task.yaml (they are not staged at all).

    We copy the already-prepared tree (clone-at-pin + deps + prisma client) rather
    than re-cloning, and preserve symlinks (node_modules ``.bin`` uses relative
    ones). Refuses if the temp dir resolves inside the lab repo (e.g. a TMPDIR set
    under the repo) — that would re-open the leak. Returns ``<staged>/repo``.

    NOTE (honest scope, see SUBJECT_PROFILE_HOST): this blocks *relative-path*
    traversal only. The agent still runs same-uid with no container/fs-namespace, so
    absolute paths into the lab repo remain possible; full confinement is the
    Phase-4 containerized agent leg.
    """
    staged_root = tempfile.mkdtemp(prefix="lab-subject-")
    staged_abs = os.path.abspath(staged_root)
    if staged_abs == REPO_ROOT or staged_abs.startswith(REPO_ROOT + os.sep):
        shutil.rmtree(staged_root, ignore_errors=True)
        raise RunnerError(
            f"staged subject dir {staged_abs!r} is inside the lab repo {REPO_ROOT!r}; "
            f"set TMPDIR to a location outside the repo so canonical/, hidden/ and "
            f"task.yaml are not reachable by relative traversal from the agent cwd"
        )
    staged_repo = os.path.join(staged_abs, "repo")
    shutil.copytree(source_repo, staged_repo, symlinks=True)
    return staged_repo


def _setup_subject(task_dir: str, run_dir: str) -> str:
    tt = os.path.join(REPO_ROOT, "harness", "task-tools")
    env = {**os.environ, "TASK_DIR": task_dir}
    subprocess.run(["bash", os.path.join(tt, "setup.sh")], env=env, check=True)  # noqa: S603
    reset = subprocess.run(  # noqa: S603
        ["bash", os.path.join(tt, "reset.sh")], env=env, check=True,
        capture_output=True, text=True,
    )
    with open(os.path.join(run_dir, "reset.txt"), "w", encoding="utf-8") as fh:
        fh.write(reset.stdout)  # records the reset tree hash (determinism check input)
    # FIX A: hand the agent a subject tree staged OUTSIDE the lab repo, so canonical/,
    # hidden/ and task.yaml cannot be reached by relative traversal from its cwd.
    source_repo = os.path.join(task_dir, ".work", "repo")
    return _stage_subject_outside_repo(source_repo)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _make_run_id(task: Task, config_id: str, rep: int) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{task.task_id}__{config_id}__rep{rep}__{stamp}"


def schema_configuration_ids() -> Tuple[str, ...]:
    """Configuration ids the telemetry schema will accept in a summary.

    Read from ``schema-v2.json`` rather than duplicated here, so a harness that can
    run an id the schema cannot record is a test failure (tests/test_telemetry.py)
    rather than a run that bills and then fails validation at the end. Widening the
    enum stays a CP-SCHEMA decision; the last one was the human-approved additive
    widening of 2026-08-16 (C3-prev, P2).
    """
    with open(TELEMETRY_SCHEMA, encoding="utf-8") as fh:
        schema = json.load(fh)
    enum = ((schema.get("properties") or {}).get("configuration_id") or {}).get("enum") or []
    return tuple(str(v) for v in enum)


def preflight_product_versions(plan: RunPlan) -> None:
    """Refuse to start a run whose product binary has drifted from the manifest pin.

    The agy adapter already refuses on a version mismatch, but it does so *inside*
    the attempt, after the run directory exists and the batch has begun. `agy`
    self-updates, so the version on PATH can move between the CP-SPEND approval
    that priced a batch and the run that spends against it — and a batch whose
    later runs measure a different product build is not the experiment that was
    approved. This check runs before anything is created or billed.

    The HOST binary is checked in both isolation modes on purpose: under
    ``--subject-isolation container`` the agent image is staged FROM the host
    binary (harness/container/stage-agy.sh vendors it and the build asserts its
    sha256), so host drift is exactly what would silently rebuild the image on a
    different version. The adapter's in-container check still runs afterwards.

    ``unavailable`` (binary absent or unrunnable) is a refusal too: a pin that
    cannot be checked has not been satisfied.
    """
    for leg in plan.legs:
        pin = leg.resolved.product_version_pin
        if not pin:
            continue
        observed = cli_version("agy", None, env=agy_adapter.agy_env())
        if observed != pin:
            raise RunnerError(
                f"pre-batch check: `agy --version` reports {observed!r} but the "
                f"manifest pins {pin!r} (leg {leg.leg_id}, selector "
                f"{leg.resolved.model_or_selector!r}). agy self-updates, so this is "
                f"the expected drift mode; refusing to start before anything is "
                f"created or billed. Re-pin the manifest with the drift recorded "
                f"(subject_isolation.agent_leg.agy_version + agy_sha256 + every "
                f"configurations.PRODUCT_B_*.conditions.agy_version, which "
                f"tests/test_manifest_pricing.py keeps in agreement), or install "
                f"the pinned version."
            )


def resolve_pricing(manifest: Dict[str, Any], plan: RunPlan) -> Tuple[Dict[str, Any], str]:
    """Load the pinned pricing snapshot for a plan (SPEC 1.4 / cache-protocol rule 3).

    Returns ``(prices, pricing_snapshot)``. Refuses (RunnerError) if a leg needs
    token-based pricing but the snapshot is missing/unresolved — this is what keeps
    a live run from starting on an unpriced manifest. Shared by the single-run
    ``main`` and the warm-series driver so both resolve pricing identically.
    """
    pricing_snapshot = manifest.get("pricing_snapshot") or ""
    prices: Dict[str, Any] = {}
    if not _is_placeholder(pricing_snapshot):
        price_path = pricing_snapshot if os.path.isabs(pricing_snapshot) \
            else os.path.join(REPO_ROOT, pricing_snapshot)
        if os.path.exists(price_path):
            prices = load_prices(price_path)
    if not prices and any(leg.resolved.cost_basis in ("marginal_api_cost",
                          "allocated_subscription_cost") for leg in plan.legs):
        raise RunnerError(
            f"pricing snapshot {pricing_snapshot!r} missing/unresolved but a leg "
            f"needs token-based pricing; fill pricing at CP-SPEND or use --dry-run"
        )
    return prices, pricing_snapshot


def execute_and_validate_run(
    *, run_dir: str, task: Task, plan: RunPlan, adapter: Any,
    subject_dir: Optional[str], launch: Optional[ContainerLaunch],
    cache_state: str, base_session: str, resume: bool,
    subject_isolation: str, subject_network: str, manifest_rel: str,
    agent_containerized: bool = False,
    prices: Dict[str, Any], pricing_snapshot: str, config_id: str,
    dry_run: bool, scenario: str,
) -> Tuple[bool, List[str]]:
    """Run one attempt-set into ``run_dir`` and validate its telemetry.

    Encapsulates the per-run core shared by the single-run ``main`` and the
    warm-series driver: event log -> ``execute`` (which archives the agent diff
    before the gate mutates the tree) -> authoritative identity stamps -> cache
    contract -> audit-grade summary + result.json. It does NOT stage or clean up
    the subject tree (the caller owns that lifecycle — critical for the warm-series
    driver, which stages ONCE and resets between reps). Returns ``(ok, reasons)``.
    """
    log = EventLog(os.path.join(run_dir, "events.jsonl"))

    def emit(event_type: str, **payload: Any) -> None:
        log.append(event_type, ts=_now_iso(), **payload)

    # execute() archives the agent's diff internally, BEFORE the gate mutates the
    # subject tree (Fix 5), and writes an optional post-gate.diff after — so the
    # harness's own edits are never attributed to the agent.
    identity, leg_options, invocations = execute(
        plan, task, adapter, subject_dir or "", run_dir, emit,
        dry_run=dry_run, scenario=scenario,
        cache_state=cache_state, base_session=base_session, resume=resume,
        launch=launch,
    )
    # Record the exact CLI command(s) executed (run artifact, not telemetry) so a
    # run can be diagnosed retroactively; credential-bearing env is redacted.
    _write_invocation_file(run_dir, invocations, dict(os.environ))
    # Cache state is a runner-controlled experimental variable — stamped
    # authoritatively here (overriding any adapter default) and proven against
    # the event log below.
    identity["cache_state"] = tiered(cache_state, "authoritative")
    identity["session_state"] = tiered("resumed" if resume else "fresh", "authoritative")
    # Subject isolation posture — the runner authoritatively knows the mode it
    # launched, so it stamps permission_profile + network_policy here, overriding
    # any adapter default (SPEC 1.3; batch-2 decision, manifest subject_isolation).
    # ``subject_network`` is the LABEL for the agent leg's egress (a bare network
    # name, or the allowlist policy label naming the list and its hash). The gate is
    # always offline, and the stamp says so explicitly rather than leaving a reader
    # to infer which leg the recorded policy applied to.
    if subject_isolation == "container":
        identity["permission_profile"] = tiered(
            SUBJECT_PROFILE_CONTAINER_AGENT if agent_containerized
            else SUBJECT_PROFILE_CONTAINER_GATE,
            "authoritative",
        )
        identity["network_policy"] = tiered(
            f"agent-leg: {subject_network} | gate: none" if agent_containerized
            else subject_network,
            "authoritative",
        )
    else:
        identity["permission_profile"] = tiered(SUBJECT_PROFILE_HOST, "authoritative")
        identity["network_policy"] = tiered("no-network-policy", "authoritative")

    events = log.read()
    cache_reasons = assert_cache_contract(events, cache_state)

    ok, reasons = assemble_and_validate(
        events, run_id=os.path.basename(run_dir), task=task, config_id=config_id,
        manifest_ref=manifest_rel, identity=identity,
        plan=plan, prices=prices, leg_options=leg_options,
        pricing_snapshot=pricing_snapshot or "unavailable", run_dir=run_dir,
    )
    ok = ok and not cache_reasons
    reasons = list(reasons) + cache_reasons

    # Emit the compact per-run result record (a pure projection of the validated
    # summary — summary.json stays authoritative). Regeneratable; never fabricates.
    summary_path = os.path.join(run_dir, "summary.json")
    if os.path.exists(summary_path):
        with open(summary_path, encoding="utf-8") as fh:
            summary_doc = json.load(fh)
        with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as fh:
            json.dump(build_result_record(summary_doc), fh, indent=2, sort_keys=True)
    return ok, reasons


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Controlled harness runner (SPEC 2.1–2.3, 2.7)")
    ap.add_argument("--task", required=True, help="task dir (e.g. tasks/pilot-realworld)")
    ap.add_argument("--config", required=True,
                    help="configuration or policy id: "
                         "C1|C2|C3|C3-med|C3-prev|C4|C5|P0|P1|P2. P2 is "
                         "scripted delegation (B3): it needs the task's pinned, frozen "
                         "split.yaml (a live run is refused on a draft split)")
    ap.add_argument("--manifest", default=os.path.join(REPO_ROOT, "manifest", "delivery-manifest.yaml"))
    ap.add_argument("--phase", default="feasibility", help="results/<phase>/ for live runs")
    ap.add_argument("--rep", type=int, default=1)
    ap.add_argument("--cache-state", required=True, choices=("cold", "warm-series"),
                    help="cache-protocol contract (methodology/cache-protocol.md rule 4): "
                         "cold = fresh session, no carried cache; warm-series = resume a "
                         "prior session so provider prompt-cache carries over")
    ap.add_argument("--session-id", default=None,
                    help="explicit session id (required to --resume a warm-series run)")
    ap.add_argument("--resume", action="store_true",
                    help="continue --session-id (warm-series runs 2..n)")
    ap.add_argument("--spend-cap-usd", type=float, default=60.0,
                    help="cumulative batch spend ceiling (CP-SPEND option a). Before "
                         "starting a run, the summed realized marginal cost of completed "
                         "sibling runs under the same output root is checked; at/over the "
                         "cap the runner halts (exit 3) without starting. Resumable: "
                         "re-invoke (optionally with a raised cap) to continue.")
    ap.add_argument("--subject-isolation", choices=("host", "container"), default="host",
                    help="subject sandbox posture. host: skip-perms + staged cwd on "
                         "the dev VM (the feasibility fallback; no fs namespace, no "
                         "network policy). container: the agent leg execs in the "
                         "subject-agent image (product CLIs baked, no task material, "
                         "credentials read-only, egress per --subject-egress) and the "
                         "gate grades its edits in the subject-gate image offline. "
                         "Recorded authoritatively in identity.permission_profile + "
                         "identity.network_policy. host is REFUSED for any "
                         "Product-B leg (SMOKE-3: the product wrote outside the "
                         "staged subject tree and into the lab repo).")
    ap.add_argument("--subject-egress", choices=("none", "allowlist"), default="none",
                    help="agent-leg egress under --subject-isolation container. none: "
                         "--network=none (no model API reachable; container path "
                         "without spend). allowlist: deny-by-default proxy on an "
                         "internal network permitting only "
                         "harness/container/egress/allowlist-model-api.txt; the list "
                         "name + sha256 are recorded in identity.network_policy. The "
                         "deterministic gate is --network=none either way.")
    ap.add_argument("--subject-network", default="none",
                    help="raw docker --network for the agent container, used only "
                         "when --subject-egress none. Recorded verbatim; carries no "
                         "claim that the lab allowlist was in force.")
    ap.add_argument("--dry-run", action="store_true",
                    help="synthetic adapters + gate; no spend/clone/network")
    ap.add_argument("--out-root", default=None,
                    help="output root for --dry-run (default: a temp dir; never results/)")
    ap.add_argument("--stub-scenario", choices=("accept", "escalate", "reject"), default="accept",
                    help="dry-run gate outcome to simulate")
    args = ap.parse_args(argv)

    try:
        # Cache-protocol contract (methodology/cache-protocol.md rule 4).
        if args.resume and not args.session_id:
            raise RunnerError("--resume requires --session-id (the session to continue)")
        if args.cache_state == "cold" and args.resume:
            raise RunnerError(
                "cold cache-state cannot --resume a session (cold = fresh session, "
                "cache-protocol rule 1); drop --resume or use --cache-state warm-series"
            )
        if args.cache_state == "warm-series" and not args.resume:
            raise RunnerError(
                "warm-series continues the cold run's session; pass --session-id <id> "
                "--resume (cache-protocol rule 2). Run 1 of the series uses --cache-state cold"
            )
        # Session ids must be valid UUIDs (the claude CLI rejects anything else on
        # --session-id/--resume). Operator-supplied ids are validated here so the
        # failure is a clear runner error, not a downstream non-JSON adapter crash.
        if args.session_id is not None:
            try:
                uuid.UUID(str(args.session_id))
            except ValueError:
                raise RunnerError(
                    f"--session-id must be a valid UUID (got {args.session_id!r}); "
                    f"the product CLI rejects non-UUID session ids"
                )
        base_session = args.session_id or str(uuid.uuid4())

        manifest = _load_yaml(args.manifest)
        if not args.dry_run and os.environ.get("LAB_ALLOW_SPEND") != "1":
            raise RunnerError(
                "a live run bills a real account and requires CP-SPEND approval; set "
                "LAB_ALLOW_SPEND=1 for an approved run, or pass --dry-run"
            )
        task = load_task(args.task, manifest)
        plan = build_plan(args.config, manifest, task=task,
                          require_frozen=not args.dry_run)

        # Pre-batch product-version check. Live runs only: --dry-run drives stub
        # adapters and never touches the product binary, so probing it there would
        # make an offline test depend on what is installed on the machine.
        if not args.dry_run:
            # SMOKE-3, checked before the version probe and before anything is
            # staged: a host-mode Product-B leg is refused outright.
            assert_product_b_isolation(plan, args.subject_isolation, args.config)
            preflight_product_versions(plan)

        prices, pricing_snapshot = resolve_pricing(manifest, plan)

        run_id = _make_run_id(task, args.config, args.rep)
        if args.dry_run:
            batch_dir = args.out_root or tempfile.mkdtemp(prefix="lab-dryrun-")
        else:
            batch_dir = os.path.join(REPO_ROOT, "results", args.phase)
        run_dir = os.path.join(batch_dir, run_id)

        # Cumulative-spend kill-switch (CP-SPEND option a). Enforced from the
        # realized, event-log-derived cost of runs already completed in this batch
        # directory — checked BEFORE this run starts, so once known spend reaches
        # the cap no further run begins. A stopped batch resumes by re-invoking
        # (optionally with a raised --spend-cap-usd); prior results are untouched.
        spent, n_prior, n_unavail = cumulative_spend_usd(batch_dir)
        if spent >= args.spend_cap_usd:
            floor_note = (f" (plus {n_unavail} prior leg(s) with unavailable cost — "
                          f"actual spend may exceed this known floor)") if n_unavail else ""
            print(
                f"runner: SPEND CAP REACHED — ${spent:.2f} known spend across {n_prior} "
                f"completed run(s){floor_note} >= ${args.spend_cap_usd:.2f} cap; halting "
                f"before this run starts. Raise --spend-cap-usd to resume the batch.",
                file=sys.stderr,
            )
            return 3

        os.makedirs(run_dir, exist_ok=True)

        launch: Optional[ContainerLaunch] = None
        subject_dir: Optional[str] = None
        staged_root: Optional[str] = None  # temp staging dir to clean up (FIX A)
        agent_volume: Optional[str] = None
        agent_containerized = False
        network_label = args.subject_network
        if args.dry_run:
            adapter: Any = StubAdapter()
            subject_dir = os.path.join(run_dir, "SYNTHETIC-subject")  # unused by stub
            if args.subject_isolation == "container":
                # --dry-run never touches Docker (no daemon required, no build). The
                # posture is still stamped, so the recorded label must not imply an
                # allowlist that was never brought up.
                network_label = args.subject_network
        else:
            adapter = REAL_ADAPTERS[plan.adapter_name]()
            if args.subject_isolation == "container":
                policy = (egress_mod.load_policy()
                          if args.subject_egress == "allowlist" else None)
                agent_launch, network_label = _ensure_agent_launch(
                    task, run_id, policy, manifest,
                    network_override=args.subject_network)
                adapter.container = agent_launch
                agent_volume = agent_launch.agent_volume
                agent_containerized = True
                # The gate is a SEPARATE image and a separate posture: task material
                # intact, --network=none, mounting the agent's volume so it grades
                # the agent's tree rather than the pristine baked one.
                launch = _ensure_gate_launch(task, agent_volume=agent_volume)
            else:
                subject_dir = _setup_subject(task.task_dir, run_dir)
                staged_root = os.path.dirname(subject_dir)  # <staged>/repo -> <staged>

        ok, reasons = execute_and_validate_run(
            run_dir=run_dir, task=task, plan=plan, adapter=adapter,
            subject_dir=subject_dir, launch=launch,
            cache_state=args.cache_state, base_session=base_session, resume=args.resume,
            subject_isolation=args.subject_isolation, subject_network=network_label,
            agent_containerized=agent_containerized,
            manifest_rel=os.path.relpath(args.manifest, REPO_ROOT),
            prices=prices, pricing_snapshot=pricing_snapshot, config_id=args.config,
            dry_run=args.dry_run, scenario=args.stub_scenario,
        )

        # The staged subject tree (FIX A) is transient scratch outside the lab repo;
        # all provenance (diffs, summary, gate reports) already lives under run_dir.
        # Best-effort cleanup so batches don't accumulate temp trees.
        if staged_root:
            shutil.rmtree(staged_root, ignore_errors=True)
        # Same for the agent->gate handoff volume: it has already been graded, and
        # the agent's edits are archived as a diff under run_dir.
        if agent_volume:
            remove_volume(agent_volume)
    except RunnerError as exc:
        print(f"runner: {exc}", file=sys.stderr)
        return 2

    print(f"run_dir: {run_dir}")
    if ok:
        print("validate: PASS (audit-grade)")
        return 0
    print("validate: FAIL", file=sys.stderr)
    for r in reasons:
        print(f"  - {r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
