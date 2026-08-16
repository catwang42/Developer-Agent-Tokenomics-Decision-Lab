"""Scripted delegation — policy P2, routing family B3 (SPEC §2.1b / §2.1c).

B3 is *scripted*: which work goes to the executor and which stays with the
conductor is fixed **before the run** by a pinned per-task ``split.yaml``, and
nothing decided at runtime may change that assignment. A policy that lets the
conductor decide *when* to delegate is B4 (P3), a different family with different
claims attached — so the split file, not the model, is the router here. This
module is where that guarantee is implemented: it loads the split, validates it
against the task's own write scope, hashes it, and renders the one deterministic
brief the conductor receives.

What is measured, and what is not:
  * The split file's sha256 is pinned in the delivery manifest, so a run's
    delegation policy is reconstructible from the summary + the manifest alone.
  * The *mechanism* by which the product performs the delegation (a product-native
    subagent bound to the executor model) cannot be validated without live spend.
    It is declared in ``harness/policies/p2-delegation.yaml`` with its verification
    status and is NOT claimed here to work.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import yaml

SPLIT_FILENAME = "split.yaml"
SPLIT_VERSION = 1
POLICY_ID = "P2"

# Scope kinds, per side. The vocabulary is closed: an unrecognised kind is a
# split-file defect, not a free-text label, because these kinds are what the
# workshop material describes B3 as splitting on (SPEC §2.1b).
EXECUTOR_KINDS = ("scaffold", "boilerplate", "test_generation")
CONDUCTOR_KINDS = ("integration", "edge_cases", "final_verification")

EXECUTOR_LEG_ID = "executor"
CONDUCTOR_LEG_ID = "conductor"


class SplitError(Exception):
    """A malformed, missing, unpinned or out-of-scope split file."""


@dataclass(frozen=True)
class Scope:
    """One assigned unit of work: a step description plus the paths it covers."""

    side: str          # "executor" | "conductor"
    scope_id: str
    kind: str
    step: str
    paths: Tuple[str, ...]
    writes: bool

    @property
    def label(self) -> str:
        return f"{'E' if self.side == 'executor' else 'C'}:{self.scope_id}"


@dataclass(frozen=True)
class Split:
    """A loaded, validated, hashed split file."""

    path: str            # absolute
    rel_path: str        # repo-root-relative (what the manifest pins)
    sha256: str          # over the RAW FILE BYTES, comments included
    task_id: str
    scopes: Tuple[Scope, ...]

    @property
    def executor_scopes(self) -> Tuple[Scope, ...]:
        return tuple(s for s in self.scopes if s.side == "executor")

    @property
    def conductor_scopes(self) -> Tuple[Scope, ...]:
        return tuple(s for s in self.scopes if s.side == "conductor")

    @property
    def label(self) -> str:
        """Compact identifier for logs/telemetry payloads."""
        return (f"split:{os.path.basename(os.path.dirname(self.path))}/"
                f"{os.path.basename(self.path)}@sha256:{self.sha256[:12]}")


# --------------------------------------------------------------------------- #
# Loading + structural validation
# --------------------------------------------------------------------------- #
def split_path(task_dir: str) -> str:
    return os.path.join(task_dir, SPLIT_FILENAME)


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise SplitError(msg)


def _scope_from(raw: Any, side: str, index: int, seen: set) -> Scope:
    where = f"{side}_scopes[{index}]"
    _require(isinstance(raw, dict), f"{where} must be a mapping")
    scope_id = raw.get("id")
    _require(isinstance(scope_id, str) and scope_id.strip(),
             f"{where} needs a non-empty string id")
    _require(scope_id not in seen, f"duplicate scope id {scope_id!r}")
    seen.add(scope_id)

    kind = raw.get("kind")
    allowed = EXECUTOR_KINDS if side == "executor" else CONDUCTOR_KINDS
    _require(kind in allowed,
             f"{where} ({scope_id}) kind {kind!r} not in {list(allowed)} — the "
             f"kind vocabulary is what makes the split readable as B3; a step "
             f"that does not fit belongs on the other side")

    step = raw.get("step")
    _require(isinstance(step, str) and step.strip(),
             f"{where} ({scope_id}) needs a 'step' description — the split assigns "
             f"work by step + path glob, and a path list alone does not say what to do")

    paths = raw.get("paths")
    _require(isinstance(paths, list) and paths and all(
        isinstance(p, str) and p.strip() for p in paths),
        f"{where} ({scope_id}) needs a non-empty 'paths' list of globs")

    writes = raw.get("writes")
    _require(isinstance(writes, bool),
             f"{where} ({scope_id}) needs an explicit boolean 'writes' — whether a "
             f"scope may modify its paths is exactly what the gate's diff-scope "
             f"check enforces, so it is never inferred")

    return Scope(side=side, scope_id=scope_id, kind=kind, step=step.strip(),
                 paths=tuple(paths), writes=writes)


def load_split(task_dir: str, *, repo_root: str,
               expected_task_id: Optional[str] = None) -> Split:
    """Load, validate and hash ``<task_dir>/split.yaml``.

    Raises :class:`SplitError` on anything that would make the delegation
    ambiguous at run time. A P2 run with no split file is refused rather than
    silently degraded to a single-model run — the missing file *is* the policy.
    """
    path = split_path(task_dir)
    if not os.path.exists(path):
        raise SplitError(
            f"P2 (scripted delegation) requires a pinned split file at {path}; "
            f"without it there is no assignment to execute. Author one against "
            f"the contract in harness/policies/README.md."
        )
    with open(path, "rb") as fh:
        raw_bytes = fh.read()
    doc = yaml.safe_load(raw_bytes.decode("utf-8")) or {}
    _require(isinstance(doc, dict), f"{path}: top level must be a mapping")

    _require(doc.get("split_version") == SPLIT_VERSION,
             f"{path}: split_version must be {SPLIT_VERSION} (got "
             f"{doc.get('split_version')!r})")
    _require(doc.get("policy") == POLICY_ID,
             f"{path}: policy must be {POLICY_ID!r} (got {doc.get('policy')!r})")

    task_id = doc.get("task_id")
    _require(isinstance(task_id, str) and task_id.strip(), f"{path}: task_id missing")
    if expected_task_id is not None:
        _require(task_id == expected_task_id,
                 f"{path}: task_id {task_id!r} does not match the task's own "
                 f"{expected_task_id!r} — a split file pinned to the wrong task "
                 f"would route work by a stale plan")

    scopes: List[Scope] = []
    seen: set = set()
    for side, key in (("executor", "executor_scopes"), ("conductor", "conductor_scopes")):
        raw_list = doc.get(key)
        _require(isinstance(raw_list, list) and raw_list,
                 f"{path}: {key} must be a non-empty list — a split with an empty "
                 f"side is not a delegation, it is a single-model run wearing P2's label")
        for i, raw in enumerate(raw_list):
            scopes.append(_scope_from(raw, side, i, seen))

    return Split(
        path=os.path.abspath(path),
        rel_path=os.path.relpath(os.path.abspath(path), repo_root),
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
        task_id=task_id,
        scopes=tuple(scopes),
    )


# --------------------------------------------------------------------------- #
# Agreement with the task's own gate scope
# --------------------------------------------------------------------------- #
def _matches(path: str, pattern: str) -> bool:
    """Glob/prefix match. A trailing '/' means 'anything under this directory'."""
    if pattern.endswith("/"):
        return path.startswith(pattern)
    return path == pattern or fnmatch.fnmatch(path, pattern)


def task_write_scope(task_yaml: Dict[str, Any]) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """(writable globs, read-only globs) for a task, by gate type.

    The two gate types invert the meaning of ``target_paths``: for a feature/bugfix
    task they are the files the agent MAY edit; for a test-generation task they are
    product files the agent must NOT touch, and writes are confined to
    ``agent_write_scope``. Getting this backwards in a split file would author a
    plan the gate is guaranteed to reject, so it is checked, not assumed.
    """
    targets = tuple(task_yaml.get("target_paths") or ())
    write_scope = task_yaml.get("agent_write_scope")
    if write_scope:
        scope = write_scope if str(write_scope).endswith("/") else str(write_scope)
        return (scope,), targets
    return targets, ()


def validate_against_task(split: Split, task_yaml: Dict[str, Any]) -> None:
    """Refuse a split whose write scopes contradict the task's gate scope."""
    writable, read_only = task_write_scope(task_yaml)
    for scope in split.scopes:
        if not scope.writes:
            continue
        for path in scope.paths:
            if read_only and any(_matches(path, ro) for ro in read_only):
                raise SplitError(
                    f"{split.rel_path}: scope {scope.scope_id!r} declares writes to "
                    f"{path!r}, which the task marks read-only (target_paths under a "
                    f"test-generation gate). The gate's diff-scope check would fail "
                    f"every run of this split."
                )
            if writable and not any(_matches(path, w) for w in writable):
                raise SplitError(
                    f"{split.rel_path}: scope {scope.scope_id!r} declares writes to "
                    f"{path!r}, outside the task's writable scope {list(writable)}."
                )


# --------------------------------------------------------------------------- #
# Manifest pin (SPEC §2.1c: "manifest pin = split-file hash per task")
# --------------------------------------------------------------------------- #
def manifest_pin(manifest: Dict[str, Any], manifest_key: str) -> Dict[str, Any]:
    return ((manifest.get(manifest_key) or {}).get("delegation_split") or {})


def check_pin(split: Split, manifest: Dict[str, Any], manifest_key: str,
              *, require_frozen: bool) -> None:
    """Verify the split on disk is the one the manifest pins.

    ``require_frozen`` is set for live runs: a split whose ``status`` is not
    ``frozen`` has not been through human review, and P2 numbers produced under a
    draft split would be uncitable. Dry runs are allowed on a draft so the harness
    can be built and tested before the freeze.
    """
    pin = manifest_pin(manifest, manifest_key)
    if not pin:
        raise SplitError(
            f"manifest {manifest_key}.delegation_split is missing; P2's manifest pin "
            f"is the split-file hash (SPEC §2.1c) and a run cannot be reconstructed "
            f"without it"
        )
    pinned = str(pin.get("sha256") or "").replace("sha256:", "")
    if pinned != split.sha256:
        raise SplitError(
            f"{split.rel_path} sha256 {split.sha256} does not match the manifest pin "
            f"{pinned or '<empty>'} — the split file changed after it was pinned. "
            f"Re-pin it (and, if it was frozen, re-freeze it) before running."
        )
    status = pin.get("status")
    if require_frozen and status != "frozen":
        raise SplitError(
            f"manifest {manifest_key}.delegation_split.status is {status!r}, not "
            f"'frozen'; a live P2 run needs the human-reviewed, frozen split "
            f"(--dry-run is allowed on a draft)"
        )


# --------------------------------------------------------------------------- #
# What the conductor is told (deterministic; pure)
# --------------------------------------------------------------------------- #
def render_brief(split: Split, *, executor_agent: str) -> str:
    """The scripted-delegation brief appended to the task prompt.

    Deterministic in the split file's contents, so two runs of the same pinned
    split send byte-identical instructions. It never asks the model to report its
    own token usage (CLAUDE.md rule 2) and never mentions the acceptance gate's
    hidden material.
    """
    lines = [
        "",
        "--- SCRIPTED DELEGATION (policy P2; pinned split file) ---",
        f"split_file: {split.rel_path}",
        f"split_sha256: {split.sha256}",
        "",
        f"You are the CONDUCTOR. A subagent named '{executor_agent}' is available to you.",
        "The assignment below is FIXED by the pinned split file above. It is not a",
        "suggestion and it is not yours to re-plan: do not delegate work that is not",
        "listed as an executor step, and do not carry out an executor step yourself.",
        "",
        f"Delegate to '{executor_agent}', one delegation per step:",
    ]
    for scope in split.executor_scopes:
        lines.append(f"  [{scope.label}] ({scope.kind}) {scope.step}")
        lines.append(f"        paths: {', '.join(scope.paths)}"
                     f"{'' if scope.writes else '  (read-only)'}")
    lines += ["", "Carry out yourself:"]
    for scope in split.conductor_scopes:
        lines.append(f"  [{scope.label}] ({scope.kind}) {scope.step}")
        lines.append(f"        paths: {', '.join(scope.paths)}"
                     f"{'' if scope.writes else '  (read-only)'}")
    lines += [
        "",
        f"If an executor step fails, retry it once through '{executor_agent}'. If it",
        "still fails, say so plainly in your final message and continue with the",
        "remaining steps — do not reassign an executor step to yourself.",
        "--- END SCRIPTED DELEGATION ---",
    ]
    return "\n".join(lines)


def executor_agent_json(split: Split, *, agent_name: str, model_id: str) -> str:
    """The ``--agents`` JSON defining the executor subagent (pure).

    The executor is bound to the economical model by ``model``; that binding is the
    entire per-leg cost story of B3, which is why the split file may not change it
    and the manifest resolves it. Key order is fixed so the argv is deterministic.
    """
    scope_lines = "; ".join(f"[{s.label}] {s.step}" for s in split.executor_scopes)
    definition = {
        agent_name: {
            "description": (
                "Executor leg of a pinned scripted-delegation split (policy P2). "
                "Use it for exactly the steps the conductor's brief assigns to it."
            ),
            "prompt": (
                "You are the executor leg of a pinned scripted split. Carry out only "
                "the step the conductor delegates to you, confined to the paths that "
                "step names. Do not widen the change, do not touch files outside those "
                "paths, and do not redesign the plan — the split file, not your "
                "judgement, decides what is yours. Report what you changed and stop.\n"
                f"Executor-assigned steps for this task: {scope_lines}"
            ),
            "model": model_id,
        }
    }
    return json.dumps(definition, sort_keys=True, separators=(",", ":"))


def telemetry_payload(split: Split) -> Dict[str, Any]:
    """Split provenance carried on the delegated legs' events (not a new event type)."""
    return {
        "split_file": split.rel_path,
        "split_sha256": split.sha256,
        "executor_scopes": [s.scope_id for s in split.executor_scopes],
        "conductor_scopes": [s.scope_id for s in split.conductor_scopes],
    }


# Metered-model -> leg matching lives on DelegationPlan in harness/adapters/base.py:
# it is the adapter contract's business, and the plan is the thing that knows its
# own legs.
