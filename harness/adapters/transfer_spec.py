"""Loader and decision engine for the transplanted routing strategies.

Everything the three transfer adapters decide is decided here, and everything
decided here comes out of ``harness/policies/transfer/<id>-spec.yaml``. No
threshold, no rung count, no prompt fragment and no gate rule is written in this
file: it reads them. That is the point — the specs are pinned by sha256 against
byte-exact extracts from the source repo, so a reader can check the transplant
against the original without reading Python.

What this module owns:

  * :class:`TransferSpec` — the loaded, verified spec.
  * :class:`Difficulty` — our port of the source's ``routing.Difficulty``.
  * :func:`classify` — public acceptance-check report -> ``Difficulty``.
  * :func:`gate_decision` — ``(escalate, why)``, with the source's own ``why``
    strings, which land verbatim in the routing events.
  * :func:`build_digest` — the $0 contained digest of a failing report.

What it does NOT own: running the acceptance gate. The runner does that
(SPEC 2.6, harness/adapters/base.py) and hands the report in. An adapter that
graded its own attempt would be the one thing this whole instrument exists to
avoid.

EVIDENCE CONTRACT. ``classify`` reads the PUBLIC gate report and nothing else.
The sealed report, the defect map and the hidden test output are never opened
here — routing may only use signals that would be visible to a real deployment.
That restriction is the registered mechanism, not an implementation shortcut:
the prereg predicts transfer breaks on W6 precisely because a rejected review
can pass every public check.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

import yaml

SPEC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "policies", "transfer",
)

#: Levels, in the source's order (``routing.LEVELS``).
LEVELS = ("shallow", "local", "broad", "stalled", "environment")


class TransferSpecError(RuntimeError):
    """A spec is missing, malformed, or no longer matches its pinned extracts."""


# --------------------------------------------------------------------------- #
# Difficulty — our port of the source's dataclass
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Difficulty:
    """What the public acceptance report says about how hard this failure is.

    Field-for-field the source's ``routing.Difficulty``, with ``identities``
    holding failing CHECK IDS where the source held failing test identities
    (judgment call J-3, recorded in every spec).
    """

    level: str
    reasons: Tuple[str, ...] = ()
    failing: int = 0
    failure_classes: Tuple[str, ...] = ()
    identities: FrozenSet[str] = frozenset()
    typed: bool = True
    guard: str = ""

    @property
    def is_hard(self) -> bool:
        """Worth a frontier model, if the policy allows one."""
        return self.level in ("broad", "stalled")

    @property
    def is_environment(self) -> bool:
        """Nothing a different model would have changed."""
        return self.level == "environment"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "reasons": list(self.reasons),
            "failing": self.failing,
            "failure_classes": list(self.failure_classes),
            "identities": sorted(self.identities),
            "typed": self.typed,
            "guard": self.guard,
        }


# --------------------------------------------------------------------------- #
# The spec
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RungSpec:
    rung: int
    leg_id: str
    role: str
    model_ref: str


@dataclass(frozen=True)
class TransferSpec:
    strategy_id: str
    configuration_id: str
    adapter: str
    rungs: Tuple[RungSpec, ...]
    frontier: RungSpec
    frontier_mode: str            # "repair" | "fresh"
    frontier_max_calls: int
    gate_kind: str                # "evidence" | "after_ladder"
    gate_min_attempt: Optional[int]
    requires_typed_evidence: bool
    frontier_budget_override_why: str
    check_classes: Dict[str, str]
    unmapped_check_class: str
    broad_failure_items: int
    stalled_overrides: bool
    report_path: str
    repair_role_text: str
    repair_evidence_label: str
    fresh_suffix: Optional[str]
    digest_cap_chars: int
    carries_over: Tuple[str, ...]
    spec_path: str
    spec_sha256: str
    extracts: Tuple[Dict[str, str], ...] = field(default=())
    doc: Dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def total_rungs(self) -> int:
        """``len(tiers)`` in the source — the frontier is NOT a rung."""
        return len(self.rungs)

    @property
    def discards_failed_artefact(self) -> bool:
        """True for the fresh-solve arm: the frontier turn starts from pristine."""
        return self.frontier_mode == "fresh"


def _req(doc: Dict[str, Any], path: str) -> Any:
    """Fetch a dotted key or raise — a spec missing a field is never defaulted."""
    node: Any = doc
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise TransferSpecError(f"spec is missing required key {path!r}")
        node = node[part]
    return node


def _opt(doc: Dict[str, Any], path: str, default: Any = None) -> Any:
    node: Any = doc
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def load_spec(strategy_id: str, spec_dir: str = SPEC_DIR,
              *, verify_extracts: bool = True) -> TransferSpec:
    """Load and verify ``<strategy_id>-spec.yaml``.

    ``verify_extracts`` re-hashes every ``source/*.py.txt`` the spec pins. It
    defaults ON and should stay on for anything that spends money: a spec whose
    extracts have drifted no longer describes the strategy it names, and
    discovering that from a cost table months later is not recoverable.
    """
    path = os.path.join(spec_dir, f"{strategy_id}-spec.yaml")
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        raise TransferSpecError(f"cannot read transfer spec {path}: {exc}") from exc
    doc = yaml.safe_load(raw.decode("utf-8")) or {}
    spec_sha = hashlib.sha256(raw).hexdigest()

    extracts = tuple(doc.get("extracts") or ())
    if verify_extracts:
        verify_spec_extracts(extracts, spec_dir, strategy_id)

    rungs = tuple(
        RungSpec(rung=int(r["rung"]), leg_id=str(r["leg_id"]),
                 role=str(r["role"]), model_ref=str(r["model_ref"]))
        for r in _req(doc, "lab_execution.rungs")
    )
    if not rungs:
        raise TransferSpecError(f"{strategy_id}: lab_execution.rungs is empty")
    fr = _req(doc, "lab_execution.frontier")
    frontier = RungSpec(rung=len(rungs), leg_id=str(fr["leg_id"]),
                        role=str(fr["role"]), model_ref=str(fr["model_ref"]))
    frontier_mode = str(fr["mode"])
    if frontier_mode not in ("repair", "fresh"):
        raise TransferSpecError(
            f"{strategy_id}: frontier mode {frontier_mode!r} is not repair|fresh")

    gate_kind = str(_req(doc, "gate.kind"))
    if gate_kind not in ("evidence", "after_ladder"):
        raise TransferSpecError(
            f"{strategy_id}: gate.kind {gate_kind!r} is not evidence|after_ladder")

    # r6/r10 also write the trigger out longhand. If the two ever disagree the
    # spec is ambiguous about when the frontier fires, so refuse rather than pick.
    trigger = _opt(doc, "gate.failure_count_trigger")
    if trigger and int(trigger.get("total_rungs", len(rungs))) != len(rungs):
        raise TransferSpecError(
            f"{strategy_id}: gate.failure_count_trigger.total_rungs "
            f"{trigger.get('total_rungs')} disagrees with {len(rungs)} declared rungs"
        )
    if trigger and int(trigger.get("frontier_fires_on_attempt", len(rungs))) != len(rungs):
        raise TransferSpecError(
            f"{strategy_id}: gate.failure_count_trigger.frontier_fires_on_attempt "
            f"{trigger.get('frontier_fires_on_attempt')} disagrees with "
            f"attempt >= total_rungs ({len(rungs)})"
        )

    fresh_suffix = _opt(doc, "prompts.probe.frontier.fresh_suffix_verbatim")
    if frontier_mode == "fresh" and not fresh_suffix:
        raise TransferSpecError(
            f"{strategy_id}: frontier mode is 'fresh' but no "
            f"prompts.probe.frontier.fresh_suffix_verbatim is pinned"
        )

    digest_cfg = (_opt(doc, "prompts.probe.digest")
                  or _opt(doc, "prompts.probe.repair.digest") or {})
    carries = (_opt(doc, "prompts.carries_over")
               or [c["id"] for c in (_opt(doc, "discard_rule.carries_over") or [])])

    return TransferSpec(
        strategy_id=str(_req(doc, "strategy_id")),
        configuration_id=str(_req(doc, "configuration_id")),
        adapter=str(_req(doc, "lab_execution.adapter")),
        rungs=rungs,
        frontier=frontier,
        frontier_mode=frontier_mode,
        frontier_max_calls=int(fr.get("max_calls", 1)),
        gate_kind=gate_kind,
        gate_min_attempt=(None if _opt(doc, "gate.min_attempt") is None
                          else int(_opt(doc, "gate.min_attempt"))),
        requires_typed_evidence=bool(_opt(doc, "gate.requires_typed_evidence", False)),
        frontier_budget_override_why=str(
            _req(doc, "gate.frontier_budget_override_why")),
        check_classes=dict(_req(doc, "evidence.check_classes")),
        unmapped_check_class=str(_opt(doc, "evidence.unmapped_check_class",
                                      "behavioural")),
        broad_failure_items=int(_req(doc, "evidence.broad_failure_items")),
        stalled_overrides=bool(_opt(doc, "evidence.stalled_overrides", True)),
        report_path=str(_opt(doc, "evidence.report_path", "gate-public.json")),
        repair_role_text=str(
            _req(doc, "prompts.probe.repair.role_substitution.text")),
        repair_evidence_label=str(_req(doc, "prompts.probe.repair.evidence_label")),
        fresh_suffix=(str(fresh_suffix) if fresh_suffix else None),
        digest_cap_chars=int(digest_cfg.get("cap_chars", 2500)),
        carries_over=tuple(str(c) for c in carries),
        spec_path=path,
        spec_sha256=spec_sha,
        extracts=extracts,
        doc=doc,
    )


def verify_spec_extracts(extracts: Sequence[Dict[str, Any]], spec_dir: str,
                         strategy_id: str) -> None:
    """Re-hash every pinned source extract; raise on the first mismatch.

    The pins are the whole reason the spec is citable. A drifted extract is not
    a warning: it means the yaml beside it describes something that is no longer
    in the repository at the sha it names.
    """
    if not extracts:
        raise TransferSpecError(f"{strategy_id}: spec pins no source extracts")
    for entry in extracts:
        rel = str(entry.get("file") or "")
        want = str(entry.get("sha256") or "")
        path = os.path.join(spec_dir, rel)
        try:
            with open(path, "rb") as fh:
                got = hashlib.sha256(fh.read()).hexdigest()
        except OSError as exc:
            raise TransferSpecError(
                f"{strategy_id}: pinned extract {rel} cannot be read: {exc}") from exc
        if got != want:
            raise TransferSpecError(
                f"{strategy_id}: extract {rel} sha256 {got} does not match the "
                f"spec's pin {want} — the transplant no longer matches its source"
            )


# --------------------------------------------------------------------------- #
# Evidence: the public acceptance report -> Difficulty
# --------------------------------------------------------------------------- #
def read_public_report(run_dir: str, spec: TransferSpec) -> Optional[Dict[str, Any]]:
    """Load the PUBLIC gate report the runner just wrote, or ``None``.

    ``None`` means the report is absent or unparseable — recorded as untyped
    evidence, never as "no failures".
    """
    path = os.path.join(run_dir, spec.report_path)
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    return doc if isinstance(doc, dict) else None


def failing_checks(report: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    """The report's non-passing checks, in report order, verbatim."""
    checks = (report or {}).get("checks") or []
    return [
        {"id": str(c.get("id") or ""), "status": str(c.get("status") or ""),
         "detail": str(c.get("detail") or "")}
        for c in checks
        if isinstance(c, dict) and str(c.get("status") or "") != "pass"
    ]


def classify(report: Optional[Dict[str, Any]], spec: TransferSpec,
             previous: Optional[Difficulty] = None) -> Difficulty:
    """Type one failure from the public report (port of ``routing.classify``).

    Order matters and follows the source: environment short-circuits everything;
    an all-shallow failure set stays shallow however large; ``broad`` needs
    ``broad_failure_items`` distinct failing identities; and a repeat of the
    identical failing set after a repair turn is a stall, which overrides
    whatever the level would otherwise have been.
    """
    if report is None:
        # The source's no-fact-tier branch: nothing recognised the output, so
        # there is no census to reason over. Shallow and explicitly UNTYPED — an
        # evidence gate that requires typed evidence degrades rather than fires.
        return Difficulty(
            level="shallow",
            reasons=("no typed evidence (public report absent or unparseable)",),
            typed=False,
        )

    items = failing_checks(report)
    identities = frozenset(c["id"] for c in items)
    classes = tuple(sorted({
        spec.check_classes.get(c["id"], spec.unmapped_check_class) for c in items
    }))
    failing = len(items)

    if not items:
        # Every public check passed. The gate is being consulted anyway (the run
        # failed something the public report cannot see — on W6 that is the whole
        # registered mechanism), and the honest classification is that the
        # visible evidence shows nothing.
        return Difficulty(
            level="shallow",
            reasons=("public report shows no failing checks",),
            failing=0, typed=True,
        )

    if "environment" in classes:
        guard = next(c["id"] for c in items
                     if spec.check_classes.get(c["id"]) == "environment")
        return Difficulty(
            level="environment",
            reasons=(f"{guard}: the environment failed, not the model",),
            failing=failing, failure_classes=classes, identities=identities,
            typed=True, guard=guard,
        )

    reasons: List[str] = []
    if all(c == "shallow" for c in classes):
        level = "shallow"
        reasons.append(f"failure classes are all shallow: {', '.join(classes)}")
    elif all(c == "malformed" for c in classes):
        # The source's guard branch: the response was not a usable artefact. A
        # cheap rung fixes these as readily as an expensive one.
        level = "shallow"
        reasons.append("response was not a usable artefact: "
                       + ", ".join(c["id"] for c in items))
    elif failing >= spec.broad_failure_items:
        level = "broad"
        reasons.append(f"{failing} distinct failing identities "
                       f"(>= {spec.broad_failure_items})")
    else:
        level = "local"
        reasons.append(f"{failing} failing identity/identities")

    if (spec.stalled_overrides and previous is not None and identities
            and identities == previous.identities):
        level = "stalled"
        reasons.append("identical failing identities survived the last repair turn")

    return Difficulty(
        level=level, reasons=tuple(reasons), failing=failing,
        failure_classes=classes, identities=identities, typed=True,
    )


# --------------------------------------------------------------------------- #
# Calibration evidence: the source's oracle output -> Difficulty
# --------------------------------------------------------------------------- #
def classify_from_unittest(stderr: str, spec: TransferSpec,
                           previous: Optional[Difficulty] = None) -> Difficulty:
    """Type one BigCodeBench failure from the unit-test runner's own stderr.

    The calibration counterpart of :func:`classify`. Same level rules, different
    evidence: calibration runs the source's tasks under the source's suite, so
    there is no acceptance-check report to read.

    In the source these facts come from an external capture harness that returns
    a per-test evidence graph. That harness is not vendored and is not installed
    here, and the source's own fallback (no fact tier) marks the run degraded and
    turns r9 into r6 — which would make r9's calibration meaningless. So the two
    facts are reconstructed from the deterministic unittest tail's output, which
    is pinned byte-exact precisely so this parse is reproducible. Judgment call
    J-11, recorded in all three specs; the parse patterns live there too.
    """
    cal = _opt(spec.doc, "evidence.calibration") or {}
    id_re = re.compile(str(cal.get("identity_pattern") or r"^(?:FAIL|ERROR): (\S+)"),
                       re.MULTILINE)
    exc_re = re.compile(
        str(cal.get("exception_pattern")
            or r"^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Warning))\b"),
        re.MULTILINE)
    shallow = set(cal.get("shallow_classes") or ())
    environment = set(cal.get("environment_classes") or ())

    text = stderr or ""
    identities = frozenset(id_re.findall(text))
    classes = tuple(sorted(set(exc_re.findall(text))))

    if not identities and not classes:
        return Difficulty(
            level="shallow",
            reasons=("no typed evidence (nothing in the runner output parsed as a "
                     "failing identity or an exception class)",),
            typed=False,
        )

    if classes and set(classes) & environment:
        guard = sorted(set(classes) & environment)[0]
        return Difficulty(
            level="environment",
            reasons=(f"{guard}: the environment failed, not the model",),
            failing=len(identities), failure_classes=classes,
            identities=identities, typed=True, guard=guard,
        )

    failing = len(identities) or len(classes)
    reasons: List[str] = []
    if classes and all(c in shallow for c in classes):
        level = "shallow"
        reasons.append(f"failure classes are all shallow: {', '.join(classes)}")
    elif failing >= spec.broad_failure_items:
        level = "broad"
        reasons.append(f"{failing} distinct failing identities "
                       f"(>= {spec.broad_failure_items})")
    else:
        level = "local"
        reasons.append(f"{failing} failing identity/identities")

    if (spec.stalled_overrides and previous is not None and identities
            and identities == previous.identities):
        level = "stalled"
        reasons.append("identical failing identities survived the last repair turn")

    return Difficulty(level=level, reasons=tuple(reasons), failing=failing,
                      failure_classes=classes, identities=identities, typed=True)


# --------------------------------------------------------------------------- #
# Gates
# --------------------------------------------------------------------------- #
def gate_decision(spec: TransferSpec, difficulty: Optional[Difficulty],
                  attempt: int) -> Tuple[bool, str]:
    """``(escalate, why)`` for one gate evaluation.

    ``attempt`` is 1-based and counts FAILED attempts so far, exactly as the
    source's loop passes ``loop + 1``. The ``why`` strings are the source's own,
    reproduced with its wording and its numbers, because they are what lands in
    the routing event and what a reader will compare against the original.
    """
    total = spec.total_rungs
    if spec.gate_kind == "after_ladder":
        if difficulty is not None and difficulty.is_environment:
            return False, (f"environment failure ({difficulty.guard}); "
                           f"no model fixes this")
        if attempt >= total:
            return True, f"all {total} cheap rungs exhausted"
        return False, f"cheap rungs remain ({attempt}/{total})"

    # evidence
    min_attempt = spec.gate_min_attempt if spec.gate_min_attempt is not None else 1
    if attempt < min_attempt:
        return False, f"attempt {attempt} < min_attempt {min_attempt}"
    if difficulty is None:
        return False, "no difficulty signal"
    if difficulty.is_environment:
        return False, (f"environment failure ({difficulty.guard}); "
                       f"no model fixes this")
    if difficulty.is_hard:
        return True, (f"evidence says {difficulty.level}: "
                      f"{'; '.join(difficulty.reasons)}")
    if attempt >= total:
        return True, f"cheap rungs exhausted ({attempt}/{total})"
    return False, f"evidence says {difficulty.level}; keep it cheap"


def gate_is_degraded(spec: TransferSpec, difficulty: Optional[Difficulty]) -> bool:
    """True when an evidence gate ran without the typed evidence it requires.

    The source declares ``requires_typed_evidence`` so a sweep can refuse to
    present an evidence-gated arm that silently behaved as a counter gate. Same
    purpose here: a degraded attempt is stamped on its routing event, and the
    strategy's whole point is not quietly unmeasured.
    """
    return bool(spec.requires_typed_evidence
                and difficulty is not None and not difficulty.typed)


# --------------------------------------------------------------------------- #
# The $0 contained digest
# --------------------------------------------------------------------------- #
def build_digest(report: Optional[Dict[str, Any]], spec: TransferSpec) -> str:
    """One line per failing public check, capped. No model call, $0.00.

    This is the probe's stand-in for the source's straitjacket digest: bounded,
    produced by the harness, and costing nothing. It is deliberately NOT an LLM
    triage summary — that is a different arm of the source study and would add
    an unbilled model call to every repair turn (judgment call J-5).
    """
    items = failing_checks(report)
    if not items:
        return "(no failing public checks were reported)"
    text = "\n".join(f"{c['id']}: {c['detail']}".rstrip() for c in items)
    if len(text) <= spec.digest_cap_chars:
        return text
    keep = spec.digest_cap_chars - len("\n[digest truncated at N chars]") - 4
    return text[:max(0, keep)] + f"\n[digest truncated at {spec.digest_cap_chars} chars]"


def build_repair_prompt(spec: TransferSpec, task_prompt: str, digest: str) -> str:
    """The repair-turn prompt: substituted role text, task, labelled digest.

    Shape follows the source's ``_repair_prompt`` (role, problem, evidence label,
    digest, closing instruction). The role TEXT is substituted rather than
    reproduced, because the source's names unit tests and demands a Python code
    block and two of the three probe tasks have neither (judgment call J-4). The
    substitution lives in the spec, not here.
    """
    return (
        f"{spec.repair_role_text.rstrip()}\n\n"
        f"{task_prompt.rstrip()}\n\n"
        f"--- {spec.repair_evidence_label} ---\n{digest}\n\n"
        f"Produce the complete corrected deliverable."
    )


def build_fresh_prompt(spec: TransferSpec, task_prompt: str, digest: str,
                       attempts: int) -> str:
    """The fresh-solve prompt: the ORIGINAL task prompt plus the pinned suffix.

    The suffix is carried byte-exact from the source, including its wording
    about a "test digest" (judgment call J-9). Nothing of the failed attempt is
    included beyond the digest and the attempt count — the discard is enforced by
    the caller staging a pristine tree, not requested in this text.
    """
    if not spec.fresh_suffix:
        raise TransferSpecError(
            f"{spec.strategy_id}: build_fresh_prompt called but no fresh suffix is pinned")
    suffix = spec.fresh_suffix.format(attempts=attempts, digest=digest)
    return f"{task_prompt.rstrip()}\n\n{suffix.strip()}"
