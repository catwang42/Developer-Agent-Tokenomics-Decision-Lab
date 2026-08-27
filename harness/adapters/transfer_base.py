"""Shared machinery for the three transplanted routing arms (r9 / r6 / r10).

Each arm is a LADDER: up to ``total_rungs`` attempts by an economical model, with
a single frontier attempt inserted at whatever point that arm's gate says so. The
three arms differ ONLY in the gate and the frontier's prompt mode, and both of
those live in the spec yaml — which is why the three adapter modules under this
one are four lines each. If a reader has to open a ``transfer_r*.py`` file to find
out what an arm does, the transplant has failed.

Division of labour, unchanged from every other adapter (SPEC 2.6,
``harness/adapters/base.py``):

  * The ADAPTER executes one attempt and emits its telemetry. It dispatches the
    attempt to the leg's own product adapter, so a rung is billed and telemetered
    exactly as the equivalent single-model run would be — same JSON usage capture,
    same tiering, same provider-side cross-check.
  * The RUNNER owns the ladder: it runs the acceptance gate between attempts,
    asks this module's pure functions what to do next, and emits the routing
    events (``harness/runner/run.py``, policy ``transfer_ladder``). An adapter
    that graded its own attempt and then chose its own next model would be
    marking its own homework twice over.

So this module holds the pieces the runner needs and nothing that spends: the
per-leg dispatcher, the prompt builders, and the ladder's arithmetic (which rung
runs next, has the frontier budget been spent, what does the routing event say).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .agy import AgyAdapter
from .base import Adapter, AttemptOutcome, AttemptSpec, EmitFn
from .claude_code import ClaudeCodeAdapter
from .transfer_spec import (
    Difficulty,
    TransferSpec,
    build_digest,
    build_fresh_prompt,
    build_repair_prompt,
    failing_checks,
    gate_decision,
    gate_is_degraded,
    load_spec,
)

#: Where the ladder's evidence comes from, on every routing event. Named so a
#: reader of the event log can see that the gate never touched the sealed report.
EVIDENCE_SOURCE = "gate-public.json"


# --------------------------------------------------------------------------- #
# The adapter: one attempt, dispatched to the leg's own product adapter
# --------------------------------------------------------------------------- #
class TransferLadderAdapter(Adapter):
    """Per-rung dispatcher for a transplanted ladder arm.

    Follows the C5 pattern (``hybrid_c5.py``): the strategy does not implement
    model invocation, it routes each leg to the product adapter that already does
    it correctly. Both rungs and frontier are Product A in every current spec, but
    the dispatch is by declared product surface rather than by leg name, so a spec
    that pins a Product-B rung works without touching this file.
    """

    #: Set by each subclass; selects the spec yaml.
    strategy_id: str = ""

    def __init__(self, spec: Optional[TransferSpec] = None) -> None:
        if spec is None:
            if not self.strategy_id:
                raise ValueError(
                    "TransferLadderAdapter is abstract; use TransferR9Adapter, "
                    "TransferR6Adapter or TransferR10Adapter (or pass a spec)"
                )
            spec = load_spec(self.strategy_id)
        self.spec = spec
        self._claude = ClaudeCodeAdapter()
        self._agy = AgyAdapter()

    def run_attempt(self, spec: AttemptSpec, subject_dir: str,
                    emit: EmitFn) -> AttemptOutcome:
        self._claude.container = self.container
        self._agy.container = self.container
        if spec.resolved.product_surface == "controlled_api":
            return self._claude.run_attempt(spec, subject_dir, emit)
        return self._agy.run_attempt(spec, subject_dir, emit)

    # -- prompts ----------------------------------------------------------- #
    def prompt_for(self, step: "LadderStep", task_prompt: str,
                   report: Optional[Dict[str, Any]]) -> str:
        """This arm's prompt for one ladder step. See :func:`ladder_prompt`."""
        return ladder_prompt(self.spec, step, task_prompt, report)


# --------------------------------------------------------------------------- #
# The ladder's arithmetic (pure; the runner drives it)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LadderStep:
    """One attempt the ladder has decided to make."""

    #: 0-based: 0 is the first generation, N is the Nth repair turn. Equals the
    #: source's ``loop``, and equals the number of attempts that already failed.
    attempt: int
    leg_id: str
    is_frontier: bool
    #: ``(escalate, why)`` as the gate returned it for this step; ``None`` for the
    #: first generation, which happens before any gate is consulted.
    why: Optional[str] = None


@dataclass(frozen=True)
class LadderState:
    """What the ladder knows between attempts."""

    attempt: int = 0
    frontier_calls: int = 0
    degraded: bool = False
    previous: Optional[Difficulty] = None


def ladder_prompt(spec: TransferSpec, step: "LadderStep", task_prompt: str,
                  report: Optional[Dict[str, Any]]) -> str:
    """The prompt for one ladder step, built from the spec.

    Rung 0 gets the task prompt verbatim — the probe's tasks come with their own
    briefs, and wrapping them in the source's ``Problem:\\n```python`` solver role
    would change the task rather than port the strategy (judgment call J-4). Every
    later step gets the $0 digest of the failing public checks: as a repair prompt
    (the failed artefact is still in the tree for the model to read), or, for the
    fresh-solve arm's frontier turn, as the original brief plus the source's
    byte-exact suffix against a tree that no longer contains the artefact.

    A module function rather than an adapter method because the runner builds the
    prompt, and under ``--dry-run`` the adapter in play is the stub.
    """
    if step.attempt == 0:
        return task_prompt
    digest = build_digest(report, spec)
    if step.is_frontier and spec.discards_failed_artefact:
        return build_fresh_prompt(spec, task_prompt, digest, step.attempt)
    return build_repair_prompt(spec, task_prompt, digest)


def next_step(spec: TransferSpec, state: LadderState,
              difficulty: Optional[Difficulty]) -> Tuple[Optional[LadderStep], Dict[str, Any]]:
    """Decide the next attempt after a failure, or ``None`` to stop.

    A direct port of the source's loop body (``run_tiered_router``), in its order,
    including the two behaviours that are easy to lose in a rewrite:

      1. **Escalation consumes a rung slot.** Escalating at attempt 1 does not
         append the frontier to the ladder, it *replaces* rung 1 — so an arm that
         escalates early runs fewer cheap rungs, and the total attempt count is
         not a constant across arms.
      2. **A spent frontier budget falls back to a cheap rung**, with the gate's
         verdict overwritten by ``frontier_budget_override_why``. This is visible
         in the source's own published data and is why an escalating arm can end
         on a cheap model.

    Returns ``(step_or_None, decision)`` where ``decision`` is the routing record
    for the event log — including the gate's raw verdict *before* any budget
    override, because "the gate wanted the frontier and could not have it" and
    "the gate did not want the frontier" are different events.
    """
    attempt = state.attempt          # failures so far == the source's `loop`
    escalate, why = gate_decision(spec, difficulty, attempt + 1)
    gate_said = escalate
    budget_spent = False
    if escalate and state.frontier_calls >= spec.frontier_max_calls:
        budget_spent = True
        escalate, why = False, spec.frontier_budget_override_why.format(
            max_calls=spec.frontier_max_calls)

    decision: Dict[str, Any] = {
        "attempt": attempt + 1,
        "gate_kind": spec.gate_kind,
        "gate_escalate": gate_said,
        "escalate": escalate,
        "why": why,
        "frontier_budget_spent": budget_spent,
        "frontier_calls_used": state.frontier_calls,
        "frontier_max_calls": spec.frontier_max_calls,
        "total_rungs": spec.total_rungs,
    }

    if escalate:
        step = LadderStep(attempt=attempt + 1, leg_id=spec.frontier.leg_id,
                          is_frontier=True, why=why)
    elif attempt + 1 < spec.total_rungs:
        rung = spec.rungs[attempt + 1]
        step = LadderStep(attempt=attempt + 1, leg_id=rung.leg_id,
                          is_frontier=False, why=why)
    else:
        # Cheap rungs exhausted and the gate said no. The source breaks here; the
        # run ends on its last failure and is recorded as such.
        decision["stop_reason"] = "cheap rungs exhausted and the gate said no"
        return None, decision

    decision["next_leg"] = step.leg_id
    decision["next_is_frontier"] = step.is_frontier
    return step, decision


def routing_payload(spec: TransferSpec, decision: Dict[str, Any],
                    difficulty: Optional[Difficulty],
                    report: Optional[Dict[str, Any]],
                    *, degraded: bool,
                    evidence_source: str = EVIDENCE_SOURCE,
                    evidence: Optional[Any] = None) -> Dict[str, Any]:
    """The payload every routing event carries.

    Rides on the frozen event types (``retry``/``escalation``) — the vocabulary is
    frozen under CP-SCHEMA and payload keys are open, so a new kind of decision
    does not need a new kind of event.

    ``evidence`` is the gate's input VERBATIM: the failing public checks, ids and
    detail strings unedited. That is the whole point of the transfer probe —
    someone reading the log must be able to see what the gate saw and judge the
    decision themselves, rather than take a level label on trust.

    The calibration path reads a different evidence source (the source's own
    unittest stderr — there is no acceptance-check report on a BigCodeBench task),
    so it overrides both ``evidence_source`` and ``evidence``. The override exists
    so the two paths cannot drift apart on everything else in this payload; it
    never lets a caller omit the evidence, only say where it came from.
    """
    payload: Dict[str, Any] = {
        "strategy": spec.strategy_id,
        "spec_sha256": spec.spec_sha256,
        "gate": {k: decision[k] for k in
                 ("gate_kind", "attempt", "gate_escalate", "escalate", "why",
                  "frontier_budget_spent") if k in decision},
        "evidence_source": evidence_source,
        "evidence": failing_checks(report) if evidence is None else evidence,
        "difficulty": difficulty.as_dict() if difficulty is not None else None,
        "degraded": degraded,
    }
    for key in ("next_leg", "next_is_frontier", "stop_reason"):
        if key in decision:
            payload[key] = decision[key]
    return payload


def degraded_now(spec: TransferSpec, state: LadderState,
                 difficulty: Optional[Difficulty]) -> bool:
    """True the first time an evidence gate runs without typed evidence.

    The source warns once and marks the whole trace degraded, because an evidence
    gate with nothing to read silently becomes a ladder-exhaustion gate — the arm
    keeps its name and stops testing its mechanism. We carry the same flag onto
    every routing event so a degraded run cannot be read as a clean r9 run.
    """
    return not state.degraded and gate_is_degraded(spec, difficulty)


def ladder_legs(spec: TransferSpec) -> List[Tuple[str, str, str]]:
    """``(leg_id, role, model_ref)`` for every leg the arm may bill, in order.

    Every rung plus the frontier. Legs that never run emit no events and so never
    appear in the summary — a leg present in the plan is a leg that *could* have
    been billed, not one that was.
    """
    legs = [(r.leg_id, r.role, r.model_ref) for r in spec.rungs]
    legs.append((spec.frontier.leg_id, spec.frontier.role, spec.frontier.model_ref))
    return legs
