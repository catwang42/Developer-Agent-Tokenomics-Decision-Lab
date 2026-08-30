"""Calibration path for the transfer probe — the AUTOMATIC fidelity gate.

Before this lab is allowed to report anything about whether the source's routing
strategies transfer, it has to show that what it reimplemented IS those
strategies. That is what this module does, and it does it the only way that
means anything: it runs our reimplementation over the source's own tasks, grades
it with the source's own unit-test oracle, and compares the result against the
source's own published rows.

    Grading is THEIRS. Cost is OURS.

Nothing here re-grades with a lab acceptance gate, and no lab gate script is
involved. The 5-task BigCodeBench-Hard slice, the published reference rows, the
two gating criteria and the three non-gating diagnostics are all pinned in
``harness/policies/transfer/calibration-slice.yaml``; this module reads them and
implements the criteria EXACTLY as the pre-registration words them
(``manifest/preregistrations/2026-08-27-transfer-probe.md``):

    "Each reimplemented strategy runs a 5-task BigCodeBench-Hard slice under the
     source's own unit-test oracle and must (a) match the published per-task
     pass/fail on >=4 of 5 and (b) land within +-30% of the published arm cost.
     The runner evaluates this itself and exits non-zero on failure; the probe
     driver refuses to start without a passing report for every strategy.
     Fail -> stop. The fidelity finding is published instead of a transfer verdict."

**Criterion (b) is known to be unpassable on the lab ladder before a single
token is spent.** The published costs are a Gemini ladder's; ours is a
Product-A ladder's, and re-pricing the published token VOLUMES at this lab's own
rate card already lands 1.5x-3.1x high. The arithmetic, and the three options
for resolving it, are written out under ``cost_criterion_blocker`` in the slice
file. No criterion has been quietly redefined here to make it passable: this
runner computes (b) as worded, fails on it, and says why in the report. Choosing
between the options is a human decision and a prereg amendment.

What this module will NOT do:

  * Invent a number. Every figure in a report is either measured from product
    usage metadata, read out of the pinned published results, or explicitly
    labelled ``derived_``/``published_``. Unavailable usage makes a cost
    *unavailable* — never zero (CLAUDE.md rules 1 and 3).
  * Spend without being told to. A live run needs ``LAB_ALLOW_SPEND=1`` AND
    ``--live`` AND a cost cap it enforces as it goes. ``--dry-run`` calls no
    model at all and stamps every artefact it writes as not-a-measurement.
  * Grade the probe's tasks. The probe's ladder reads ``gate-public.json``; this
    path reads unittest stderr (judgment call J-11). They share the spec, the
    gate logic and the ladder arithmetic, and differ in their evidence source
    and their prompts — by design, and pinned in the specs as two profiles.

Usage (neither of these launches anything from this file; see the probe driver):

    python3 -m harness.runner.transfer_calibration --dry-run --out /tmp/cal
    python3 -m harness.runner.transfer_calibration --live --source-root <checkout>
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import yaml

from harness.adapters.base import AttemptSpec
from harness.adapters.claude_code import ClaudeCodeAdapter
from harness.adapters.transfer_base import (
    LadderState,
    LadderStep,
    degraded_now,
    next_step,
    routing_payload,
)
from harness.adapters.transfer_capture import (
    CaptureError,
    capture_config,
    interpreter as capture_interpreter,
    preflight as capture_preflight,
    run_contained,
)
from harness.adapters.transfer_spec import (
    SPEC_DIR,
    Difficulty,
    TransferSpec,
    TransferSpecError,
    classify_from_evidence_graph,
    classify_from_unittest,
    load_spec,
)
from harness.runner.profiles import dataset_marker, get_profile
from harness.telemetry.costing import CACHE_BLIND, token_cost_usd
from harness.telemetry.telemetry import EventLog, tiered, unavailable

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SLICE_PATH = os.path.join(SPEC_DIR, "calibration-slice.yaml")
DEFAULT_MANIFEST = os.path.join(REPO_ROOT, "manifest", "delivery-manifest.yaml")

#: Named, not created here. The dataset directory is made by a live run only, and
#: it must be listed in results/README.md with the report that documents it
#: (CLAUDE.md rule 8) before that run happens.
DEFAULT_OUT = os.path.join(REPO_ROOT, "results", "transfer-probe-calibration")

#: The source's own oracle timeout (`_run_bigcodebench_native`, timeout=120).
ORACLE_TIMEOUT_S = 120

#: Shared with the probe. A calibration that eats the probe's budget has failed
#: at its job even if it passes.
DEFAULT_SPEND_CAP_USD = 300.0

STRATEGIES = ("r9", "r6", "r10")

#: Exit codes. Four outcomes, four codes, because "the gate failed" and "the
#: inputs were refused" and "nothing was evaluated" are three different things
#: and a single non-zero would let a caller treat them alike.
EXIT_PASS = 0           # every requested strategy passed both gating criteria
EXIT_GATE_FAILED = 1    # a criterion failed — the prereg's "Fail -> stop"
EXIT_REFUSED = 2        # a pin did not verify, or the run was not allowed to start
EXIT_DRY_RUN = 4        # machinery ran, no model was called, nothing was evaluated


class CalibrationError(RuntimeError):
    """A pin did not verify, an input is missing, or the run may not proceed."""


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


# --------------------------------------------------------------------------- #
# Pinned inputs: verify before use, refuse on mismatch
# --------------------------------------------------------------------------- #
def load_slice(path: str = SLICE_PATH) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    for key in ("source", "tasks", "published_slice_reference", "gate", "run_conditions"):
        if key not in doc:
            raise CalibrationError(f"{path}: calibration slice is missing {key!r}")
    return doc


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def sha256_file(path: str) -> Tuple[str, int]:
    with open(path, "rb") as fh:
        blob = fh.read()
    return sha256_bytes(blob), len(blob)


def verify_pinned_file(path: str, pin: Dict[str, Any], label: str) -> Dict[str, Any]:
    """Re-hash one pinned file. Raises rather than warning.

    A calibration whose inputs drifted is worse than no calibration: it produces
    a number that looks like a fidelity check and is not one.
    """
    if not os.path.exists(path):
        raise CalibrationError(
            f"{label}: pinned file not found at {path}. Calibration needs the "
            f"source checkout at sha {pin.get('_sha', '')}; pass --source-root."
        )
    sha, nbytes = sha256_file(path)
    expected = str(pin.get("sha256") or "")
    if sha != expected:
        raise CalibrationError(
            f"{label}: sha256 {sha} does not match the pin {expected} ({path}). "
            f"The input changed after it was pinned; re-pin it deliberately or "
            f"check out the pinned revision — do not calibrate against drift."
        )
    if pin.get("bytes") is not None and nbytes != int(pin["bytes"]):
        raise CalibrationError(
            f"{label}: {nbytes} bytes, pinned {pin['bytes']} ({path})")
    return {"path": path, "sha256": sha, "bytes": nbytes}


def verify_source_artifacts(source_root: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    """Verify the source's task jsonl and published results at the pinned sha."""
    src = doc["source"]
    out: Dict[str, Any] = {"repo": src["repo"], "sha": src["sha"],
                           "licence": src.get("licence"), "files": []}
    for key in ("task_data", "published_results"):
        pin = dict(src[key])
        pin["_sha"] = src["sha"]
        path = os.path.join(source_root, pin["path"])
        rec = verify_pinned_file(path, pin, f"source.{key}")
        rec["repo_path"] = pin["path"]
        out["files"].append(rec)
    return out


def load_oracle_tail(doc: Dict[str, Any], spec_dir: str = SPEC_DIR) -> str:
    """The source's ``DETERMINISTIC_UNITTEST_TAIL``, verified against its pin.

    Returned as the exact bytes that will be appended to every candidate program,
    because the pin is only worth something if the pinned thing is the thing that
    runs.
    """
    tail = ""
    for pin in doc["source"]["oracle"].get("extracts", []):
        path = os.path.join(spec_dir, pin["file"])
        verify_pinned_file(path, pin, f"oracle.{pin['file']}")
        if pin.get("symbol") == "DETERMINISTIC_UNITTEST_TAIL":
            with open(path, encoding="utf-8") as fh:
                tail = fh.read()
    if not tail:
        raise CalibrationError(
            "calibration slice pins no DETERMINISTIC_UNITTEST_TAIL extract; "
            "the oracle cannot be rebuilt without it")
    return tail


def load_records(source_root: str, doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Load the five pinned slice records, verifying each one's own sha256.

    The per-record hash is over the raw jsonl LINE with its trailing newline
    stripped, which is the convention the pins in the slice file were taken
    under. Verifying the whole file is not enough on its own: it proves the
    corpus, not that we selected out of it the rows we said we would.
    """
    want = {t["task_id"]: t for t in doc["tasks"]}
    path = os.path.join(source_root, doc["source"]["task_data"]["path"])
    found: Dict[str, Dict[str, Any]] = {}
    with open(path, "rb") as fh:
        for raw in fh:
            line = raw.rstrip(b"\n")
            if not line:
                continue
            rec = json.loads(line.decode("utf-8"))
            task_id = rec.get("task_id")
            if task_id not in want or task_id in found:
                continue
            pin = want[task_id]
            sha = sha256_bytes(line)
            if sha != pin["record_sha256"]:
                raise CalibrationError(
                    f"{task_id}: record sha256 {sha} != pin {pin['record_sha256']}")
            if len(line) != int(pin["record_bytes"]):
                raise CalibrationError(
                    f"{task_id}: record is {len(line)} bytes, pinned {pin['record_bytes']}")
            for key in ("complete_prompt", "test", "entry_point", "canonical_solution"):
                if not rec.get(key):
                    raise CalibrationError(f"{task_id}: record has no {key!r}")
            found[task_id] = rec
    missing = [t for t in want if t not in found]
    if missing:
        raise CalibrationError(
            f"slice task ids absent from {path}: {', '.join(missing)}")
    # `tasks` order is the order the published pass_vectors are written in.
    return [found[t["task_id"]] for t in doc["tasks"]]


# --------------------------------------------------------------------------- #
# The source's oracle, ported from the pinned extract
# --------------------------------------------------------------------------- #
# source/bcb-oracle.py.txt, `extract_code`. Same pattern, same fallback-to-whole-
# text, same strip. A model that answers with prose and one fenced block gets the
# block; one that answers with bare code gets its own text.
_CODE_FENCE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL)


def extract_code(text: str) -> str:
    m = _CODE_FENCE.search(text or "")
    return (m.group(1) if m else (text or "")).strip()


def missing_code_error(code: str, entry_point: str) -> Optional[str]:
    """The source's birth gate: no ``def <entry_point>`` => refused unexecuted."""
    if f"def {entry_point}" in code:
        return None
    return f"model response contains no `def {entry_point}` code block"


def tail_to_cap(text: str, cap: int) -> str:
    """``sj.tail_to_cap``: keep the LAST ``cap`` characters, not the first.

    A traceback's information is at the end. Truncating from the front is how a
    digest ends up containing only the import block.
    """
    text = text or ""
    if len(text) <= cap:
        return text
    return text[-cap:]


@dataclass(frozen=True)
class OracleResult:
    """One grading of one candidate by the source's own suite."""

    passed: bool
    #: Verbatim failure text the repair turn will be digested from. Empty on pass.
    #: On the contained path this is ``ContainedRun.native_payload()`` — the same
    #: stream, tail-truncated the same way, so the record is comparable.
    evidence: str
    returncode: Optional[int]
    timed_out: bool
    #: True when the candidate was refused before execution (birth gate).
    birth_gate: bool
    #: Contained path only: the harness's own bounded digest. Empty elsewhere,
    #: in which case the caller digests ``evidence`` as it always did.
    digest: str = ""
    #: Contained path only: the typed evidence graph, or ``None`` for no fact
    #: tier. ``None`` and "the path was not contained" are different states and
    #: the caller distinguishes them with :attr:`contained`.
    graph: Optional[Dict[str, Any]] = None
    contained: bool = False
    #: The harness's own accounting for this capture (raw vs digest tokens,
    #: handle, profile). Recorded per attempt; never used for routing.
    capture: Dict[str, Any] = dataclasses.field(default_factory=dict)


def grade(record: Dict[str, Any], solution_code: str, tail: str,
          *, timeout_s: int = ORACLE_TIMEOUT_S,
          capture: Optional[Dict[str, Any]] = None) -> OracleResult:
    """Run the source's unit-test suite over one candidate. Their rule, unchanged.

    ``program = solution + "\\n\\n" + record["test"] + TAIL``; exit 0 is a pass;
    120s is a failure, not an error. The scratch dir is removed either way.

    ``capture`` is the spec's ``evidence.calibration.capture_harness`` block when
    the arm declares one. With it, the program runs through the source's own
    ``ContainedRun`` flow (``evaluator._run_bigcodebench_contained``) and the
    failure comes back as the harness's digest plus a typed evidence graph;
    without it, the plain subprocess below is unchanged. The GRADING RULE is the
    same in both: exit 0 passes, and nothing else decides.
    """
    err = missing_code_error(solution_code, record["entry_point"])
    if err is not None:
        return OracleResult(passed=False, evidence=err, returncode=None,
                            timed_out=False, birth_gate=True)
    program = solution_code + "\n\n" + record["test"] + tail

    if capture:
        # No fallback. A row whose evidence is labelled as the source's digest
        # has to have been produced by the source's harness; substituting our
        # regex when the harness is missing is the failure Amendment 4 exists to
        # repair, silently repeated.
        run = run_contained(program, config=capture,
                            grading_python=sys.executable, timeout_s=float(timeout_s))
        if run.timed_out:
            return OracleResult(
                passed=False, evidence=f"timeout: execution exceeded {timeout_s}s",
                returncode=run.exit_code, timed_out=True, birth_gate=False,
                digest=run.digest, graph=run.graph, contained=True,
                capture=dict(run.metrics))
        if run.passed:
            return OracleResult(passed=True, evidence="", returncode=0,
                                timed_out=False, birth_gate=False, contained=True,
                                capture=dict(run.metrics))
        return OracleResult(
            passed=False, evidence=run.native_payload.strip() or "test failed",
            returncode=run.exit_code, timed_out=False, birth_gate=False,
            digest=run.digest, graph=run.graph, contained=True,
            capture=dict(run.metrics))

    workdir = tempfile.mkdtemp(prefix="bcb_cal_")
    path = os.path.join(workdir, "prog.py")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(program)
        try:
            proc = subprocess.run([sys.executable, path], capture_output=True,
                                  text=True, timeout=timeout_s, cwd=workdir)
        except subprocess.TimeoutExpired:
            return OracleResult(passed=False,
                                evidence=f"timeout: execution exceeded {timeout_s}s",
                                returncode=None, timed_out=True, birth_gate=False)
        if proc.returncode == 0:
            return OracleResult(passed=True, evidence="", returncode=0,
                                timed_out=False, birth_gate=False)
        return OracleResult(passed=False,
                            evidence=(proc.stderr or "").strip() or "test failed",
                            returncode=proc.returncode, timed_out=False,
                            birth_gate=False)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def verify_oracle_environment(records: Sequence[Dict[str, Any]], tail: str,
                              *, timeout_s: int = ORACLE_TIMEOUT_S,
                              capture: Optional[Dict[str, Any]] = None
                              ) -> List[Dict[str, Any]]:
    """Grade each task's OWN reference answer. Every one of them must pass.

    This preflight is not a formality, and it is not about tidiness. The gate the
    calibration is testing classifies ``ModuleNotFoundError`` as a SHALLOW
    failure — the source's ``_SHALLOW_CLASSES``, transcribed verbatim. So on a
    grading interpreter that is missing ``numpy``, every candidate for every task
    fails with a shallow error, r9's evidence gate correctly declines to
    escalate, every arm runs its cheap rungs and stops, and the report says the
    reimplementation does not reproduce the published rows.

    That report would be entirely wrong, entirely self-consistent, and would have
    cost a live model budget to produce. Three of the five pinned tasks fail this
    way on a bare interpreter (they need pandas, numpy, matplotlib, seaborn,
    sklearn). So: score the source's own canonical solution first, with no model
    involved and at no cost, and refuse to start unless the oracle can recognise
    a known-good answer.

    Returns one row per task. The caller refuses on any ``canonical_passed:
    False``.

    It runs through ``capture`` when the arm declares one, so the preflight also
    proves the capture harness can execute the real programs end to end — an
    oracle check that skipped the harness would clear a path the slice does not
    take.
    """
    rows: List[Dict[str, Any]] = []
    for record in records:
        code = record["complete_prompt"] + record["canonical_solution"]
        result = grade(record, code, tail, timeout_s=timeout_s, capture=capture)
        last = (result.evidence or "").strip().splitlines()
        rows.append({
            "task_id": record["task_id"],
            "libs": record.get("libs"),
            "canonical_passed": result.passed,
            "detail": ("" if result.passed else (last[-1] if last else "no output")),
        })
    return rows


# --------------------------------------------------------------------------- #
# The source's prompts, from the pinned role extracts
# --------------------------------------------------------------------------- #
def _pinned_literal(spec_dir: str, filename: str) -> str:
    """The string value of a pinned ``NAME = (...)`` extract.

    Read out of the extract with ``ast.literal_eval`` rather than retyped here,
    so the prose the model sees is the source's bytes and a re-hash of the
    extract is a re-hash of the prompt.
    """
    path = os.path.join(spec_dir, filename)
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            return str(ast.literal_eval(node.value))
    raise CalibrationError(f"{path}: no assignment to read a role string from")


def initial_prompt(record: Dict[str, Any], spec_dir: str = SPEC_DIR) -> str:
    """``_build_initial_prompt(problem, role_type="solver")``, verbatim."""
    role = _pinned_literal(spec_dir, "source/solver-role.py.txt")
    prompt_text = record.get("complete_prompt", "")
    return role + f"Problem:\n```python\n{prompt_text}\n```\n\nWrite the complete solution."


def repair_prompt(record: Dict[str, Any], sol: str, digest: str,
                  label: str, spec_dir: str = SPEC_DIR) -> str:
    """``_repair_prompt(problem, sol, digest, label)``, verbatim."""
    role = _pinned_literal(spec_dir, "source/repair-role.py.txt")
    statement = record.get("complete_prompt", "")
    return (
        role
        + f"Problem:\n```\n{statement}\n```\n\n"
        + f"Current solution:\n```\n{sol}\n```\n\n"
        + f"{label}:\n```\n{digest}\n```\n\n"
        + "Write the complete corrected solution."
    )


def fresh_prompt(record: Dict[str, Any], digest: str, attempts: int,
                 spec_dir: str = SPEC_DIR) -> str:
    """``_fresh_prompt(problem, digest, attempts)``, verbatim.

    r10's frontier turn. The previous candidate is NOT passed — that omission is
    the whole arm.
    """
    return (
        initial_prompt(record, spec_dir)
        + f"\n\nNOTE: {attempts} cheaper model attempts failed on this task. "
        + "The most recent failure, as a bounded test digest:\n"
        + f"```\n{digest}\n```\n\n"
        + "Do not assume the previous approach was close. Solve it your own way."
    )


def calibration_prompt(spec: TransferSpec, step: LadderStep, record: Dict[str, Any],
                       *, previous_code: str, digest: str,
                       spec_dir: str = SPEC_DIR) -> str:
    """The prompt for one calibration ladder step, in the source's own words."""
    if step.attempt == 0:
        return initial_prompt(record, spec_dir)
    if step.is_frontier and spec.discards_failed_artefact:
        return fresh_prompt(record, digest, step.attempt, spec_dir)
    label = str(
        (spec.doc.get("prompts", {}).get("calibration", {}).get("repair", {}) or {})
        .get("evidence_label") or "Straitjacket Triaged Error Digest")
    return repair_prompt(record, previous_code, digest, label, spec_dir)


# --------------------------------------------------------------------------- #
# Solvers — where a candidate solution comes from
# --------------------------------------------------------------------------- #
class Solver:
    """Turns a prompt into a candidate response. The only thing that can spend."""

    spends = False

    def solve(self, *, leg_id: str, role: str, resolved: Any, prompt: str,
              emit: Any, workdir: str, timeouts: Any) -> str:
        raise NotImplementedError


class NullSolver(Solver):
    """``--dry-run``: calls no model and returns nothing.

    Every task then fails the source's birth gate, every ladder runs to its own
    stopping rule, and the report is stamped as not-a-measurement. This exercises
    the whole path — pins, oracle, gate arithmetic, report shape — for $0. It
    does NOT tell you anything about fidelity, and the report says so in its
    first five lines rather than in a footnote.
    """

    def solve(self, *, leg_id: str, role: str, resolved: Any, prompt: str,
              emit: Any, workdir: str, timeouts: Any) -> str:
        emit("model_call_started", leg=leg_id, role=role, dry_run=True)
        emit("model_call_completed", leg=leg_id, role=role, dry_run=True,
             usage={cls: unavailable("dry run: no model was called")
                    for cls in ("input_tokens", "output_tokens",
                                "cache_creation_tokens", "cache_read_tokens")},
             detail="dry run: no model was called, no candidate was produced")
        return ""


class ProductASolver(Solver):
    """Live Product-A calls through the normal adapter. Spends.

    The adapter is the same one every other Product-A leg in this lab uses, so a
    calibration leg is billed, timed and telemetered identically to a probe leg —
    which is the point: criterion (b) compares OUR bill, and a bill measured a
    special way would not be ours.
    """

    spends = True

    def __init__(self) -> None:
        self.adapter = ClaudeCodeAdapter()
        self._last: Dict[str, str] = {}
        self.adapter.on_response = self._capture

    def _capture(self, leg_id: str, text: str) -> None:
        self._last[leg_id] = text

    def solve(self, *, leg_id: str, role: str, resolved: Any, prompt: str,
              emit: Any, workdir: str, timeouts: Any) -> str:
        spec = AttemptSpec(leg_id, role, resolved, prompt,
                           cache_state="cold", session_id=str(uuid.uuid4()),
                           resume=False, timeout_s=timeouts.kill_s,
                           budget_s=timeouts.budget_s)
        self._last.pop(leg_id, None)
        self.adapter.run_attempt(spec, workdir, emit)
        # Absent (timeout, unparseable product JSON) is an empty candidate, which
        # the birth gate refuses — not a crash, and not a silent pass.
        return self._last.get(leg_id, "")


# --------------------------------------------------------------------------- #
# One cell: one strategy over one task
# --------------------------------------------------------------------------- #
@dataclass
class AttemptRecord:
    attempt: int
    leg_id: str
    is_frontier: bool
    why: Optional[str]
    passed: bool
    birth_gate: bool
    timed_out: bool
    returncode: Optional[int]
    response_chars: int
    code_chars: int
    #: Capped verbatim failure text — what the gate read, kept so a routing
    #: decision can be judged rather than trusted.
    evidence: str
    difficulty: Optional[Dict[str, Any]] = None


@dataclass
class CellResult:
    strategy_id: str
    task_id: str
    passed: bool
    attempts: List[AttemptRecord]
    degraded: bool
    frontier_calls: int
    stop_reason: str
    cost: Dict[str, Any]
    tokens: Dict[str, Any]
    events_path: str

    @property
    def shape(self) -> List[str]:
        """``["cheap", "cheap", "frontier"]`` — the routing shape, model-free."""
        return ["frontier" if a.is_frontier else "cheap" for a in self.attempts]


def _leg_usage(events: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for ev in events:
        if ev.get("event_type") == "model_call_completed" and ev.get("usage"):
            out.setdefault(str(ev.get("leg")), []).append(ev["usage"])
    return out


def cell_cost(events: Sequence[Dict[str, Any]], legs_by_id: Dict[str, Any],
              prices: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Price one cell from its own event log. Returns ``(cost, tokens)``.

    Any leg whose usage is unavailable makes the CELL cost unavailable. That is
    deliberate and it is the rule everywhere else in this harness: a slice total
    assembled from the legs that happened to report would understate the bill and
    would still be printed as a number (CLAUDE.md rule 3).
    """
    total = 0.0
    tokens = {"input_tokens": 0, "output_tokens": 0}
    tokens_ok = True
    for leg_id, usages in _leg_usage(events).items():
        leg = legs_by_id.get(leg_id)
        if leg is None:
            return (unavailable(f"leg {leg_id!r} billed but not declared in the plan"),
                    {"confidence": "unavailable"})
        r = leg.resolved
        if not r.model_id:
            return (unavailable(f"leg {leg_id!r} has no priceable model_id"),
                    {"confidence": "unavailable"})
        for usage in usages:
            field_ = token_cost_usd(usage, r.provider, r.model_id, prices,
                                    cache_blind=(r.cost_basis_qualifier == CACHE_BLIND))
            if field_.get("confidence") == "unavailable" or field_.get("value") is None:
                return (unavailable(
                    f"leg {leg_id!r}: {field_.get('reason', 'usage unavailable')}"),
                    {"confidence": "unavailable"})
            total += float(field_["value"])
            for cls in tokens:
                slot = usage.get(cls)
                if isinstance(slot, dict) and slot.get("value") is not None:
                    tokens[cls] += int(slot["value"])
                else:
                    tokens_ok = False
    if not _leg_usage(events):
        return (unavailable("no leg reported usage"), {"confidence": "unavailable"})
    cost = tiered(round(total, 10), "derived")
    cost["basis"] = "marginal_api_cost"
    token_field: Dict[str, Any] = (
        tiered(tokens, "derived") if tokens_ok
        else unavailable("at least one leg did not report a token class"))
    return cost, token_field


def run_cell(spec: TransferSpec, record: Dict[str, Any], solver: Solver,
             legs_by_id: Dict[str, Any], out_dir: str, tail: str,
             prices: Dict[str, Any], *, timeouts: Any, cap_chars: int,
             spec_dir: str = SPEC_DIR) -> CellResult:
    """Run one strategy's ladder over one BigCodeBench task, graded by their oracle.

    The ladder arithmetic is the SAME code the probe runs
    (``transfer_base.next_step``) — if it were reimplemented here, calibration
    would be validating a second implementation and certifying the first.
    """
    cap_cfg = capture_config(spec)
    task_slug = record["task_id"].replace("/", "_")
    cell_dir = os.path.join(out_dir, spec.strategy_id, task_slug)
    os.makedirs(cell_dir, exist_ok=True)
    log = EventLog(os.path.join(cell_dir, "events.jsonl"))

    def emit(event_type: str, **payload: Any) -> None:
        log.append(event_type, _now_iso(), **payload)

    state = LadderState()
    step = LadderStep(attempt=0, leg_id=spec.rungs[0].leg_id, is_frontier=False)
    difficulty: Optional[Difficulty] = None
    attempts: List[AttemptRecord] = []
    previous_code = ""
    digest = ""
    stop_reason = "passed"
    passed = False

    while True:
        prompt = calibration_prompt(spec, step, record, previous_code=previous_code,
                                    digest=digest, spec_dir=spec_dir)
        leg = legs_by_id[step.leg_id]
        workdir = tempfile.mkdtemp(prefix=f"cal_{spec.strategy_id}_")
        try:
            response = solver.solve(leg_id=step.leg_id, role=leg.role,
                                    resolved=leg.resolved, prompt=prompt,
                                    emit=emit, workdir=workdir, timeouts=timeouts)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        code = extract_code(response)
        result = grade(record, code, tail, capture=cap_cfg)
        emit("test_run", leg=step.leg_id, task_id=record["task_id"],
             oracle="source_bigcodebench_unittest", passed=result.passed,
             returncode=result.returncode, timed_out=result.timed_out,
             birth_gate_refusal=result.birth_gate,
             capture=(result.capture or None))
        with open(os.path.join(cell_dir, f"attempt{step.attempt}-response.txt"),
                  "w", encoding="utf-8") as fh:
            fh.write(response)

        rec = AttemptRecord(
            attempt=step.attempt, leg_id=step.leg_id, is_frontier=step.is_frontier,
            why=step.why, passed=result.passed, birth_gate=result.birth_gate,
            timed_out=result.timed_out, returncode=result.returncode,
            response_chars=len(response), code_chars=len(code),
            evidence=tail_to_cap(result.evidence, cap_chars))
        attempts.append(rec)
        previous_code = code

        if result.passed:
            passed = True
            break

        if result.contained:
            # The source's `triage_error_straitjacket`: return the digest the
            # harness already produced. Nothing is re-summarised and no line is
            # selected by keyword. `tail_to_cap` is the spec's declared cap and
            # is idempotent — a digest is far under it, so this is a no-op that
            # keeps the declared bound enforced rather than assumed.
            digest = tail_to_cap(result.digest, cap_chars)
            difficulty = classify_from_evidence_graph(result.graph, spec,
                                                      previous=difficulty)
            evidence_source = "ctx_harness_evidence_graph"
        else:
            digest = tail_to_cap(result.evidence, cap_chars)
            difficulty = classify_from_unittest(result.evidence, spec,
                                                previous=difficulty)
            evidence_source = "unittest_stderr"
        rec.difficulty = difficulty.as_dict() if difficulty else None
        if degraded_now(spec, state, difficulty):
            state = dataclasses.replace(state, degraded=True)
            print(f"[calibration] {spec.strategy_id}/{record['task_id']}: no typed "
                  f"evidence; this run is DEGRADED and is not testing its evidence gate",
                  file=sys.stderr)
        nxt, decision = next_step(spec, state, difficulty)
        payload = routing_payload(spec, decision, difficulty, None,
                                  degraded=state.degraded,
                                  evidence_source=evidence_source,
                                  evidence={"text": digest,
                                            "birth_gate_refusal": result.birth_gate})
        if nxt is None:
            stop_reason = str(decision.get("stop_reason") or "ladder exhausted")
            emit("failure", category="ladder_exhausted", leg=step.leg_id,
                 routing=payload)
            break
        if nxt.is_frontier:
            emit("escalation", from_route=step.leg_id, to_route=nxt.leg_id,
                 reason="gate_escalate", failed_leg=step.leg_id, routing=payload)
        else:
            emit("retry", leg=nxt.leg_id, reason="gate_fail", routing=payload)
        state = dataclasses.replace(
            state, attempt=nxt.attempt, previous=difficulty,
            frontier_calls=state.frontier_calls + (1 if nxt.is_frontier else 0))
        step = nxt

    emit("acceptance", task_id=record["task_id"], strategy=spec.strategy_id,
         passed=passed, attempts=len(attempts), oracle="source_bigcodebench_unittest",
         graded_by="source", stop_reason=stop_reason)
    events = log.read()
    cost, tokens = cell_cost(events, legs_by_id, prices)
    frontier_calls = sum(1 for a in attempts if a.is_frontier)
    return CellResult(strategy_id=spec.strategy_id, task_id=record["task_id"],
                      passed=passed, attempts=attempts, degraded=state.degraded,
                      frontier_calls=frontier_calls, stop_reason=stop_reason,
                      cost=cost, tokens=tokens, events_path=log.path)


# --------------------------------------------------------------------------- #
# The gate: the prereg's criteria, as worded
# --------------------------------------------------------------------------- #
def _published(doc: Dict[str, Any], strategy_id: str) -> Dict[str, Any]:
    return doc["published_slice_reference"][strategy_id]


def reference_consistency(doc: Dict[str, Any], strategy_id: str) -> Dict[str, Any]:
    """Cross-check the slice file's own totals against its per-task rows.

    Not a criterion — an integrity check on the reference itself. A gate that
    compares against a total nobody ever re-derived can pass or fail for a
    transcription reason.
    """
    ref = _published(doc, strategy_id)
    per_task = [t["published"][strategy_id] for t in doc["tasks"]]
    summed = round(sum(float(p["as_run_usd"]) for p in per_task), 6)
    vector = [bool(p["passed"]) for p in per_task]
    return {
        "as_run_usd_total_matches_rows": abs(summed - float(ref["as_run_usd"])) < 1e-6,
        "summed_rows_usd": summed,
        "declared_total_usd": float(ref["as_run_usd"]),
        "pass_vector_matches_rows": vector == list(ref["pass_vector"]),
    }


def routing_shape(published_rungs: Sequence[str], frontier_model: str) -> List[str]:
    """Published rung list -> model-free shape, so J-2 does not fake a mismatch."""
    return ["frontier" if frontier_model in r else "cheap" for r in published_rungs]


def evaluate_strategy(spec: TransferSpec, cells: Sequence[CellResult],
                      doc: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate both gating criteria and the three diagnostics for one strategy."""
    sid = spec.strategy_id
    ref = _published(doc, sid)
    by_task = {c.task_id: c for c in cells}
    rows: List[Dict[str, Any]] = []
    matches = 0
    for t in doc["tasks"]:
        pub = t["published"][sid]
        cell = by_task.get(t["task_id"])
        measured = None if cell is None else cell.passed
        match = measured is not None and measured == bool(pub["passed"])
        matches += 1 if match else 0
        rows.append({
            "task_id": t["task_id"],
            "category": t["category"],
            "published_passed": bool(pub["passed"]),
            "measured_passed": measured,
            "pass_match": match,
            "published_shape": routing_shape(
                pub.get("rungs", []),
                str(spec.doc["source_definition"]["frontier"])),
            "measured_shape": None if cell is None else cell.shape,
            "measured_cost": None if cell is None else cell.cost,
            "degraded": None if cell is None else cell.degraded,
            "stop_reason": None if cell is None else cell.stop_reason,
        })

    # (a) pass_match — >= 4 of 5.
    n_tasks = len(doc["tasks"])
    threshold = 4
    pass_match = {
        "id": "pass_match", "gating": True,
        "rule": f"per-task pass/fail matches the published row on >= {threshold} of {n_tasks}",
        "matches": matches, "of": n_tasks,
        "status": "pass" if matches >= threshold else "fail",
    }

    # (b) cost_within_30pct — unavailable is a FAIL, never a skip and never a 0.
    published_usd = float(ref["as_run_usd"])
    costs = [c.cost for c in cells]
    if len(cells) != n_tasks or any(
            c.get("confidence") == "unavailable" or c.get("value") is None for c in costs):
        cost_crit = {
            "id": "cost_within_30pct", "gating": True,
            "rule": "abs(measured - published) / published <= 0.30",
            "measured_slice_usd": None,
            "published_slice_usd": published_usd,
            "status": "fail",
            "detail": ("slice cost is unavailable (a cell did not run, or a leg's "
                       "usage was unavailable); an unavailable cost is not zero and "
                       "not a pass"),
        }
    else:
        measured_usd = round(sum(float(c["value"]) for c in costs), 10)
        delta = abs(measured_usd - published_usd) / published_usd if published_usd else None
        cost_crit = {
            "id": "cost_within_30pct", "gating": True,
            "rule": "abs(measured - published) / published <= 0.30",
            "measured_slice_usd": measured_usd,
            "published_slice_usd": published_usd,
            "relative_delta": None if delta is None else round(delta, 6),
            "status": "pass" if (delta is not None and delta <= 0.30) else "fail",
        }
        if cost_crit["status"] == "fail":
            cost_crit["detail"] = (
                "See cost_criterion_blocker in calibration-slice.yaml: this "
                "criterion compares a Product-A ladder's bill against a Gemini "
                "ladder's and was shown unpassable before the run. A failure here "
                "is expected and is NOT evidence that the routing logic differs — "
                "read routing_shape_match for that.")

    frontier_calls = sum(c.frontier_calls for c in cells)
    diagnostics = [
        {"id": "routing_shape_match", "gating": False,
         "rule": "per-task escalation decisions and rung count vs the published rungs",
         "matches": sum(1 for r in rows if r["measured_shape"] == r["published_shape"]),
         "of": n_tasks,
         "per_task": [{"task_id": r["task_id"], "published": r["published_shape"],
                       "measured": r["measured_shape"]} for r in rows]},
        {"id": "token_volume_delta", "gating": False,
         "rule": "measured input/output tokens vs published_slice_reference",
         "published": {"input_tokens": ref.get("input_tokens"),
                       "output_tokens": ref.get("output_tokens")},
         "measured": _sum_tokens(cells)},
        {"id": "frontier_reachability", "gating": False,
         "rule": "the frontier was called at least once across the slice",
         "frontier_calls": frontier_calls,
         "status": "pass" if frontier_calls > 0 else "fail",
         "detail": ("a calibration in which the frontier never fires is void "
                    "regardless of what it scores")},
    ]

    criteria = [pass_match, cost_crit]
    verdict = "pass" if all(c["status"] == "pass" for c in criteria) else "fail"
    return {
        "strategy_id": sid,
        "configuration_id": spec.configuration_id,
        "spec_sha256": spec.spec_sha256,
        "gate_kind": spec.gate_kind,
        "verdict": verdict,
        "criteria": criteria,
        "diagnostics": diagnostics,
        "per_task": rows,
        "degraded_cells": [c.task_id for c in cells if c.degraded],
        "reference_consistency": reference_consistency(doc, sid),
    }


def _sum_tokens(cells: Sequence[CellResult]) -> Dict[str, Any]:
    total = {"input_tokens": 0, "output_tokens": 0}
    for c in cells:
        if c.tokens.get("confidence") == "unavailable" or not c.tokens.get("value"):
            return unavailable("at least one cell's token volume was unavailable")
        for cls in total:
            total[cls] += int(c.tokens["value"][cls])
    return tiered(total, "derived")


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #
def _status_banner(dry_run: bool, verdict: str) -> str:
    if dry_run:
        return ("STATUS: NOT A MEASUREMENT — dry run. No model was called, no "
                "candidate was produced, and every pass/fail below is the "
                "machinery running against an empty response.")
    return (f"STATUS: PENDING (awaiting CP-DATA review) — calibration verdict: "
            f"{verdict.upper()}")


def _evidence_caveat(spec: TransferSpec, provenance: Dict[str, Any]) -> str:
    """Which evidence tier this arm's gate actually read — J-11, or its repair.

    An arm that ran the source's capture harness must not carry J-11's wording,
    and an arm that did not must not carry the repair's. The caveat is derived
    from the provenance the run recorded rather than written by hand, so the two
    can never drift apart.
    """
    harness = (provenance.get("capture_harness") or {}).get(spec.strategy_id)
    if not harness:
        return ("J-11: the evidence the gate reads is reconstructed from unittest "
                "stderr; the source's typed evidence came from an external capture "
                "harness that is not vendored.")
    return (
        "J-13 (supersedes J-11 for this arm): the evidence the gate reads is the "
        f"typed evidence graph and digest produced by {harness['repo']}"
        f"@{harness['commit'][:7]} ({harness.get('package', 'ctx-harness')} "
        f"{harness.get('ctx_version', '?')}) through the source's own wrapper. "
        "The identification of that package as the harness behind the published "
        "rows is this lab's inference from the digest header and API surface and "
        "is NOT confirmed by the upstream author.")


def build_report(spec: TransferSpec, cells: Sequence[CellResult],
                 doc: Dict[str, Any], *, dry_run: bool, provenance: Dict[str, Any],
                 manifest_pricing: str, incomplete: Optional[str] = None
                 ) -> Dict[str, Any]:
    evaluation = evaluate_strategy(spec, cells, doc)
    if dry_run:
        # A dry run cannot pass. Stated as a value, not implied by a footnote:
        # the probe driver reads this field.
        evaluation["verdict"] = "fail"
    report = {
        "report_type": "transfer-probe-calibration",
        "status_banner": _status_banner(dry_run, evaluation["verdict"]),
        "generated_utc": _now_iso(),
        "dry_run": dry_run,
        "incomplete": incomplete,
        "slice_id": doc["slice_id"],
        "prereg": doc["gate"]["authority"],
        "grading": "the source's own BigCodeBench unit-test oracle; no lab gate ran",
        "pricing_snapshot": manifest_pricing,
        "driver_profile": doc["run_conditions"]["driver_profile"],
        "source_provenance": provenance,
        "fidelity_caveats": [
            "J-2: rung identity differs (three Product-A economical rungs vs three "
            "Gemini tiers). Rung COUNT and the frontier are preserved.",
            _evidence_caveat(spec, provenance),
            "J-12: the subject is an agentic CLI, not a chat completion. Its final "
            "response text is graded; agentic overhead is in the bill.",
            "cost_criterion_blocker: criterion (b) compares two model families' "
            "prices and was shown unpassable before the run.",
        ],
        **evaluation,
    }
    return report


def render_markdown(reports: Sequence[Dict[str, Any]]) -> str:
    lines: List[str] = []
    first = reports[0] if reports else {}
    lines += [
        "# Transfer-probe calibration",
        "",
        first.get("status_banner", "STATUS: PENDING"),
        "",
        f"Slice: `{first.get('slice_id', '')}` — 5 pinned BigCodeBench-Hard tasks.",
        f"Prereg: `{first.get('prereg', '')}`",
        "",
        "Grading is the SOURCE's own unit-test oracle. Cost is OURS. Nothing in "
        "this report is a claim about either product's general capability, and "
        "the slice is five tasks.",
        "",
        "## Verdicts",
        "",
        "| strategy | verdict | pass_match | cost (measured vs published) | frontier calls |",
        "|---|---|---|---|---|",
    ]
    for r in reports:
        crit = {c["id"]: c for c in r.get("criteria", [])}
        diag = {d["id"]: d for d in r.get("diagnostics", [])}
        pm = crit.get("pass_match", {})
        cc = crit.get("cost_within_30pct", {})
        measured = cc.get("measured_slice_usd")
        cost_cell = (f"${measured:.4f} vs ${cc.get('published_slice_usd', 0):.4f}"
                     if measured is not None else
                     f"unavailable vs ${cc.get('published_slice_usd', 0):.4f}")
        lines.append(
            f"| {r['strategy_id']} | **{r['verdict']}** | "
            f"{pm.get('matches')}/{pm.get('of')} | {cost_cell} | "
            f"{diag.get('frontier_reachability', {}).get('frontier_calls')} |")
    lines += ["", "## Per task", ""]
    for r in reports:
        lines += [f"### {r['strategy_id']}", "",
                  "| task | category | published | measured | shape (pub / ours) |",
                  "|---|---|---|---|---|"]
        for row in r.get("per_task", []):
            lines.append(
                f"| {row['task_id']} | {row['category']} | "
                f"{'pass' if row['published_passed'] else 'fail'} | "
                f"{'pass' if row['measured_passed'] else 'fail'} | "
                f"{'-'.join(row['published_shape'] or [])} / "
                f"{'-'.join(row['measured_shape'] or [])} |")
        lines.append("")
    lines += ["## Fidelity caveats", ""]
    for caveat in first.get("fidelity_caveats", []):
        lines.append(f"- {caveat}")
    lines.append("")
    return "\n".join(lines)


def write_reports(out_dir: str, reports: Sequence[Dict[str, Any]]) -> List[str]:
    written = []
    for r in reports:
        path = os.path.join(out_dir, r["strategy_id"], "calibration-report.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(r, fh, indent=2, sort_keys=True)
            fh.write("\n")
        written.append(path)
    md = os.path.join(out_dir, "calibration-report.md")
    with open(md, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(reports))
    written.append(md)
    return written


def read_calibration_report(out_dir: str, strategy_id: str) -> Optional[Dict[str, Any]]:
    """Read one strategy's report, or ``None``. Used by the probe driver's preflight."""
    path = os.path.join(out_dir, strategy_id, "calibration-report.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def calibration_is_clear(out_dir: str, strategies: Sequence[str] = STRATEGIES
                         ) -> Tuple[bool, List[str]]:
    """Is every strategy calibrated and passing? The probe driver's gate.

    Returns ``(ok, reasons)``. A missing report, a dry-run report, an incomplete
    report or a failing verdict all block, and each says which.
    """
    reasons: List[str] = []
    for sid in strategies:
        report = read_calibration_report(out_dir, sid)
        if report is None:
            reasons.append(f"{sid}: no calibration report at {out_dir}")
            continue
        if report.get("dry_run"):
            reasons.append(f"{sid}: calibration report is from a dry run")
        if report.get("incomplete"):
            reasons.append(f"{sid}: calibration incomplete ({report['incomplete']})")
        if report.get("verdict") != "pass":
            reasons.append(f"{sid}: calibration verdict is "
                           f"{report.get('verdict', 'missing')!r}, not 'pass'")
    return (not reasons), reasons


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def _cells_cost(cells: Sequence[CellResult]) -> float:
    """Realized spend so far, for the running cap. Unavailable legs count 0 here.

    That is a deliberate exception to unavailable-!=-0 and it is safe in ONE
    direction only: this figure exists to STOP spending, so under-counting can
    only make the cap fire late in a way the caller sees. It is never reported.
    """
    total = 0.0
    for c in cells:
        if c.cost.get("value") is not None:
            total += float(c.cost["value"])
    return total


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Transfer-probe calibration: run each transplanted arm over the "
                    "pinned 5-task BigCodeBench-Hard slice under the SOURCE's own "
                    "unit-test oracle and evaluate the prereg's fidelity criteria.")
    ap.add_argument("--strategy", action="append", choices=STRATEGIES, default=None,
                    help="repeatable; default is all three")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help=f"dataset directory (default {DEFAULT_OUT}). It must be "
                         f"listed in results/README.md with the report that "
                         f"documents it before a live run.")
    ap.add_argument("--source-root", default=None,
                    help="checkout of the source repo at the pinned sha (required "
                         "for --live; the task jsonl and results json are re-hashed)")
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST)
    ap.add_argument("--slice", dest="slice_path", default=SLICE_PATH)
    ap.add_argument("--spec-dir", default=SPEC_DIR)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true",
                      help="no model call, no spend; exercises pins, oracle, gate "
                           "arithmetic and report shape. Cannot produce a pass.")
    mode.add_argument("--live", action="store_true",
                      help="real Product-A calls. Refused unless LAB_ALLOW_SPEND=1 "
                           "and a CP-SPEND checkpoint approved this batch.")
    ap.add_argument("--spend-cap-usd", type=float, default=DEFAULT_SPEND_CAP_USD,
                    help="hard ceiling on realized marginal cost across this run, "
                         "shared with the probe. Checked between cells; at/over "
                         "the cap the run stops and the report is marked incomplete.")
    args = ap.parse_args(argv)

    strategies = args.strategy or list(STRATEGIES)

    try:
        doc = load_slice(args.slice_path)
        tail = load_oracle_tail(doc, args.spec_dir)
    except (CalibrationError, OSError, yaml.YAMLError) as exc:
        print(f"[calibration] refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED

    if args.live and os.environ.get("LAB_ALLOW_SPEND") != "1":
        print("[calibration] refused: --live needs LAB_ALLOW_SPEND=1 and a "
              "CP-SPEND-approved batch (CLAUDE.md rule 5).", file=sys.stderr)
        return EXIT_REFUSED
    if args.live and not args.source_root:
        print("[calibration] refused: --live needs --source-root (the pinned "
              "source checkout) to read the tasks and verify their hashes.",
              file=sys.stderr)
        return EXIT_REFUSED

    # Imported here so a --dry-run on a machine with no manifest still exercises
    # the pins and the oracle; a live run needs the manifest to resolve models.
    from harness.runner.run import RunnerError, resolve_pricing, transfer_plan  # noqa: PLC0415

    with open(args.manifest, encoding="utf-8") as fh:
        manifest = yaml.safe_load(fh) or {}

    profile = get_profile(doc["run_conditions"]["driver_profile"])
    timeouts = profile.timeouts(int(doc["run_conditions"]["agent_timeout_s"]))
    cap_chars = int(doc["run_conditions"]["error_treatment"]["cap_chars"])

    provenance: Dict[str, Any] = {"source": doc["source"]["repo"],
                                  "sha": doc["source"]["sha"],
                                  "verified": False}
    records: List[Dict[str, Any]] = []
    if args.source_root:
        try:
            provenance = verify_source_artifacts(args.source_root, doc)
            provenance["verified"] = True
            records = load_records(args.source_root, doc)
        except (CalibrationError, OSError, json.JSONDecodeError) as exc:
            print(f"[calibration] refused: {exc}", file=sys.stderr)
            return EXIT_REFUSED
    else:
        print("[calibration] no --source-root: the slice tasks are unavailable, so "
              "this dry run exercises the pins, the gate arithmetic and the report "
              "shape only.", file=sys.stderr)

    # Is the capture harness actually there? Only arms that DECLARE one are
    # checked, so r6 and r10 are untouched by this. Refusing here rather than
    # degrading is the source's own `require()` rule: an evidence gate reading a
    # fallback is a counter gate wearing the wrong label, and finding that out
    # after a live slice has been billed is finding it out too late.
    capture_cfg: Optional[Dict[str, Any]] = None
    capture_status: Dict[str, Any] = {}
    for sid in strategies:
        try:
            cfg = capture_config(load_spec(sid, args.spec_dir))
        except TransferSpecError as exc:
            print(f"[calibration] refused ({sid}): {exc}", file=sys.stderr)
            return EXIT_REFUSED
        if not cfg:
            continue
        try:
            status = capture_preflight(cfg)
        except (CaptureError, OSError, ValueError) as exc:
            print(f"[calibration] refused ({sid}): capture harness unusable: {exc}",
                  file=sys.stderr)
            return EXIT_REFUSED
        status["interpreter"] = capture_interpreter(cfg)
        status["repo"] = cfg.get("repo")
        status["commit"] = cfg.get("commit")
        capture_status[sid] = status
        capture_cfg = cfg
        print(f"[calibration] {sid}: capture harness "
              f"{cfg.get('package')} {status.get('ctx_version')} under "
              f"{status['interpreter']}", file=sys.stderr)
    if capture_status:
        provenance["capture_harness"] = capture_status

    # Can this interpreter recognise a known-good answer? If not, nothing below
    # means anything — see verify_oracle_environment. $0, no model, always run.
    if records:
        env_rows = verify_oracle_environment(records, tail, capture=capture_cfg)
        provenance["oracle_environment"] = env_rows
        broken = [r for r in env_rows if not r["canonical_passed"]]
        if broken:
            print("[calibration] refused: the grading interpreter cannot score the "
                  "source's own canonical solutions as passes, so every candidate "
                  "would fail for an environment reason (and ModuleNotFoundError "
                  "classifies as SHALLOW, so the gates would decline to escalate "
                  "and the report would blame the reimplementation):",
                  file=sys.stderr)
            for row in broken:
                print(f"    {row['task_id']}: {row['detail']}  libs={row['libs']}",
                      file=sys.stderr)
            print("[calibration] install the slice's libs into the grading "
                  "interpreter and re-run.", file=sys.stderr)
            return EXIT_REFUSED

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "TIMING-PROFILE.md"), "w", encoding="utf-8") as fh:
        fh.write(dataset_marker(profile, dataset=os.path.basename(args.out),
                                tasks={t["task_id"]: int(
                                    doc["run_conditions"]["agent_timeout_s"])
                                    for t in doc["tasks"]}))

    solver: Solver = NullSolver() if args.dry_run else ProductASolver()
    reports: List[Dict[str, Any]] = []
    exit_code = 0

    for sid in strategies:
        try:
            spec = load_spec(sid, args.spec_dir)
            plan = transfer_plan(spec.configuration_id, manifest)
            prices, pricing_snapshot = resolve_pricing(manifest, plan)
        except (TransferSpecError, RunnerError, KeyError) as exc:
            print(f"[calibration] refused ({sid}): {exc}", file=sys.stderr)
            return EXIT_REFUSED
        legs_by_id = {leg.leg_id: leg for leg in plan.legs}

        cells: List[CellResult] = []
        incomplete: Optional[str] = None
        for record in records:
            if solver.spends and _cells_cost(cells) >= args.spend_cap_usd:
                incomplete = (f"spend cap ${args.spend_cap_usd:.2f} reached after "
                              f"{len(cells)} of {len(records)} tasks")
                print(f"[calibration] {incomplete}", file=sys.stderr)
                break
            cells.append(run_cell(spec, record, solver, legs_by_id, args.out, tail,
                                  prices, timeouts=timeouts, cap_chars=cap_chars,
                                  spec_dir=args.spec_dir))
        if not records:
            incomplete = "no slice records loaded (--source-root not given)"

        report = build_report(spec, cells, doc, dry_run=args.dry_run,
                              provenance=provenance,
                              manifest_pricing=pricing_snapshot,
                              incomplete=incomplete)
        reports.append(report)
        if report["verdict"] != "pass":
            exit_code = EXIT_GATE_FAILED

    for path in write_reports(args.out, reports):
        print(f"[calibration] wrote {path}")
    for r in reports:
        print(f"[calibration] {r['strategy_id']}: {r['verdict']}")
    if args.dry_run:
        # Not a gate failure and not a pass — no evaluation happened. Distinct
        # from both so an operator (and a CI log) cannot read one as the other.
        print("[calibration] DRY RUN — no model was called; nothing was evaluated.",
              file=sys.stderr)
        return EXIT_DRY_RUN
    if exit_code:
        print("[calibration] FAIL — the probe driver will refuse to start. Per the "
              "prereg: 'Fail -> stop. The fidelity finding is published instead of "
              "a transfer verdict.'", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
