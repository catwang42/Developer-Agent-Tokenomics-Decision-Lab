"""Transfer-probe driver — the 27 registered cells, and the gate in front of them.

Registered scope (``manifest/preregistrations/2026-08-27-transfer-probe.md``):
``{W6, W4b, W4} x {r9, r6, r10} x rep1-3 = 27 cells``, dataset ``results/transfer-probe``,
spend cap ``$300`` **shared with the calibration path**
(``manifest/cp-spend-transfer-probe.md``).

What this module is for
-----------------------
Everything that makes a batch of 27 live cells a *registered experiment* rather
than a loop: the cell list and its order, the resume rule, the dataset marker,
and — most of the module — the PREFLIGHT that refuses to start. It deliberately
owns none of the per-run machinery. Each cell is executed by shelling out to
``python3 -m harness.runner.run``, the same entry point every other batch used,
so the probe inherits subject staging, the container posture, the gate, the
event log, the cost derivation and the in-runner spend kill-switch without a
second implementation of any of them. A driver that reimplemented staging would
be a third staging path to keep in step with two others; the screening batch-1
driver shells out for exactly this reason.

The preflight is the point
--------------------------
Three of the four refusals below are things that would otherwise be discovered
*after* the money was spent:

  1. **Calibration.** The probe's whole claim is that these are the source's
     strategies, not our paraphrase of them. That claim is only tested by
     ``harness/runner/transfer_calibration.py`` running them under the SOURCE's
     own unit-test oracle. Until every strategy has a passing, non-dry-run
     calibration report, a probe result measures an unvalidated reimplementation
     and cannot be attributed to the published strategies at all. This gate is
     automatic (prompt section D) and there is no flag to skip it.
  2. **The schema enum.** ``configuration_id`` is frozen under CP-SCHEMA and does
     not contain R9/R6/R10. A run whose id the schema will not accept executes,
     bills, and *then* fails validation at the summary step — 27 times. Widening
     the enum is a human CP-SCHEMA decision, so this module refuses rather than
     widens.
  3. **The manifest policy pins.** ``routing_policies.{R9,R6,R10}`` do not exist.
     SPEC 2.1c makes a policy's manifest hash the thing that answers "which rules
     did this run execute?", and CLAUDE.md rule 7 keeps model/price detail in the
     manifest. Pinning the three spec yamls is a human freeze, not a driver's job.

Refusals 2 and 3 are therefore expected to fire today: **this driver cannot
launch as shipped, by design.** It prints what a human must do. The fourth
refusal is the ordinary one (``LAB_ALLOW_SPEND=1`` + a CP-SPEND approval).

Timing
------
Every cell runs under the ``transfer-probe`` driver profile
(``harness/runner/profiles.py``): the task's ``agent_timeout_s`` becomes a SOFT
budget that is stamped and crossed rather than enforced, the hard kill moves to
3x, and Product B's ``--print-timeout`` is re-pinned per task. That is a NEW ARM
CONDITION — these cells are not comparable with batch-1/batch-2 timing — and the
driver writes ``TIMING-PROFILE.md`` into the dataset directory at launch saying
so, with the resolved numbers.

This module performs no spend by itself and launches nothing unless asked. Its
default mode is ``--plan-only``: print the cells, the resolved timeouts, the
preflight verdict and the two launch commands, and exit.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from harness.runner import profiles as P
from harness.runner import transfer_calibration as CAL

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_MANIFEST = os.path.join(REPO_ROOT, "manifest", "delivery-manifest.yaml")

#: The dataset this driver creates. NAMED here; created only at launch, and only
#: by ``run.py`` (via ``--phase``). Listing it in ``results/README.md`` is a
#: precondition of launch (CLAUDE.md rule 8) and is checked in the preflight.
DATASET = "transfer-probe"
DATASET_DIR = os.path.join(REPO_ROOT, "results", DATASET)

#: The calibration dataset this driver's gate reads. Same $300 cap.
CALIBRATION_DIR = CAL.DEFAULT_OUT

#: Shared with calibration (``manifest/cp-spend-transfer-probe.md``). Passed
#: straight through to ``run.py --spend-cap-usd``, which measures realized spend
#: in the PROBE dataset only — see :func:`shared_cap_note`.
DEFAULT_SPEND_CAP_USD = 300.0

#: Registered run order: W4 -> W6 -> W4b. Not alphabetical and not the order the
#: prereg lists the tasks in (it names them {W6, W4b, W4}); the prereg's own
#: "Run order" line is the authority and it is this one. W4 first is the cheapest
#: way to find out the machinery works: it is a 1200s task on which the prereg
#: predicts all three arms land together, so a first-task result that is wildly
#: split is a harness fault, not a finding.
TASKS: Tuple[Tuple[str, str], ...] = (
    ("W4", "tasks/suite/W4-complex-bugfix"),
    ("W6", "tasks/suite/W6-pr-review"),
    ("W4b", "tasks/suite/W4b-zarr-consolidated-order"),
)

#: Configuration ids as ``run.py --config`` takes them (uppercase), in the
#: prereg's order. ``TRANSFER_CONFIGS`` in run.py maps these to the spec ids.
CONFIGS: Tuple[str, ...] = ("R9", "R6", "R10")
REPS: Tuple[int, ...] = (1, 2, 3)

#: House posture, unchanged from screening batch 1 (scripts/screening-batch1-driver.sh):
#: cold cache, container isolation, allowlisted egress.
CACHE_STATE = "cold"
SUBJECT_ISOLATION = "container"
SUBJECT_EGRESS = "allowlist"

PROFILE = P.TRANSFER_PROBE

EXIT_OK = 0          # every cell ran and validated
EXIT_CELL_FAILED = 1 # at least one cell failed to validate (it still billed)
EXIT_REFUSED = 2     # preflight refused, or a bad invocation — nothing started
EXIT_SPEND_CAP = 3   # the in-runner cap halted the batch; re-invoke to resume
EXIT_PLAN_ONLY = 4   # plan printed, nothing launched


class ProbeError(RuntimeError):
    """A refusal the operator must act on. Never raised mid-batch."""


# --------------------------------------------------------------------------- #
# The cell list
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Cell:
    """One registered cell: one task, one arm, one repetition."""

    index: int          # 1-based position in the registered order
    task_key: str       # W4 / W6 / W4b
    task_dir: str       # repo-relative, as run.py --task takes it
    config_id: str      # R9 / R6 / R10
    rep: int

    @property
    def label(self) -> str:
        return f"{self.task_key}/{self.config_id}/rep{self.rep}"


def plan_cells(tasks: Sequence[Tuple[str, str]] = TASKS,
               configs: Sequence[str] = CONFIGS,
               reps: Sequence[int] = REPS) -> List[Cell]:
    """The 27 cells in the order they will be run.

    Task-major (the registered run order), then REP, then arm. The rep-before-arm
    nesting is the one free choice here and it is made for interruption safety:
    a batch cut off at any point has run the same number of reps of all three
    arms on the task in flight, so the arms stay comparable on partial data. The
    alternative (arm-major) would leave, say, three reps of r9 and none of r10 —
    a partial dataset that cannot be read at all. Interruption is the expected
    case, not the exceptional one: the idle reaper on this VM can stop a long
    batch, which is why resume exists (:func:`completed_cells`).
    """
    cells: List[Cell] = []
    n = 0
    for task_key, task_dir in tasks:
        for rep in reps:
            for config_id in configs:
                n += 1
                cells.append(Cell(index=n, task_key=task_key, task_dir=task_dir,
                                  config_id=config_id, rep=rep))
    return cells


def task_timeouts(tasks: Sequence[Tuple[str, str]] = TASKS,
                  *, repo_root: str = REPO_ROOT) -> Dict[str, int]:
    """``task_id -> agent_timeout_s``, read from each task's own ``task.yaml``.

    Read from the task file rather than restated here so the marker cannot claim
    a budget the runner will not use; ``run.py`` separately refuses if the task
    file and the manifest disagree (``resolve_agent_timeout``).
    """
    import yaml  # local: keeps the module importable for --plan-only without PyYAML

    out: Dict[str, int] = {}
    for _key, rel in tasks:
        path = os.path.join(repo_root, rel, "task.yaml")
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        task_id = str(doc.get("task_id") or os.path.basename(rel))
        seconds = doc.get("agent_timeout_s")
        if not isinstance(seconds, int) or isinstance(seconds, bool) or seconds <= 0:
            raise ProbeError(
                f"{rel}/task.yaml: agent_timeout_s is {seconds!r}; the probe profile "
                f"derives both the soft budget and the 3x hard kill from it, so a "
                f"missing or non-integer value has no safe default"
            )
        out[task_id] = seconds
    return out


def task_ids(tasks: Sequence[Tuple[str, str]] = TASKS,
             *, repo_root: str = REPO_ROOT) -> Dict[str, str]:
    """``task_key -> task_id`` (the id run.py builds run directory names from)."""
    import yaml

    out: Dict[str, str] = {}
    for key, rel in tasks:
        path = os.path.join(repo_root, rel, "task.yaml")
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
        out[key] = str(doc.get("task_id") or os.path.basename(rel))
    return out


# --------------------------------------------------------------------------- #
# Preflight
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Refusal:
    """One reason the batch may not start, and what a human must do about it."""

    code: str
    detail: str
    remedy: str

    def render(self) -> str:
        return f"  [{self.code}] {self.detail}\n      -> {self.remedy}"


def _calibration_refusals(calibration_dir: str) -> List[Refusal]:
    ok, reasons = CAL.calibration_is_clear(calibration_dir)
    if ok:
        return []
    return [Refusal(
        code="CALIBRATION",
        detail=("the transplanted strategies are not calibrated against the source's "
                "own oracle: " + "; ".join(reasons)),
        remedy=("run the calibration command printed below to completion and check "
                "its report; a probe run before it measures our reimplementation, "
                "not the published strategies"),
    )]


def _schema_refusals(configs: Sequence[str] = CONFIGS) -> List[Refusal]:
    from harness.runner.run import schema_configuration_ids

    allowed = set(schema_configuration_ids())
    missing = [c for c in configs if c not in allowed]
    if not missing:
        return []
    return [Refusal(
        code="SCHEMA-ENUM",
        detail=(f"harness/telemetry/schema-v2.json configuration_id enum does not "
                f"accept {', '.join(missing)} (it allows "
                f"{', '.join(sorted(allowed))})"),
        remedy=("CP-SCHEMA: a human must additively widen the enum, as was done for "
                "C3-prev/P2 on 2026-08-16. Without it every cell would execute, bill, "
                "and then fail summary validation"),
    )]


def _manifest_pin_refusals(manifest: Dict[str, Any],
                           configs: Sequence[str] = CONFIGS) -> List[Refusal]:
    from harness.runner.run import policy_manifest_pin

    out: List[Refusal] = []
    for config_id in configs:
        pin = policy_manifest_pin(manifest, config_id)
        if not pin:
            out.append(Refusal(
                code="MANIFEST-PIN",
                detail=f"manifest routing_policies.{config_id} is absent",
                remedy=(f"a human must pin {config_id}'s spec file "
                        f"(harness/policies/transfer/{config_id.lower()}-spec.yaml) with "
                        f"its sha256 and status, as routing_policies.P3 is pinned "
                        f"(SPEC 2.1c). Unpinned, no cell may be cited"),
            ))
            continue
        declared = str(pin.get("sha256") or "").replace("sha256:", "")
        actual = _spec_sha(config_id)
        if declared != actual:
            out.append(Refusal(
                code="MANIFEST-PIN",
                detail=(f"manifest routing_policies.{config_id}.sha256 is "
                        f"{declared or '<empty>'} but the spec file hashes to {actual}"),
                remedy="re-pin (and re-freeze) the spec in the manifest before running",
            ))
    return out


def _spec_sha(config_id: str) -> str:
    """sha256 of the arm's spec yaml, via the loader that also verifies extracts."""
    from harness.adapters.transfer_spec import load_spec
    from harness.runner.run import TRANSFER_CONFIGS

    return load_spec(TRANSFER_CONFIGS[config_id]).spec_sha256


def _spec_refusals(configs: Sequence[str] = CONFIGS) -> List[Refusal]:
    """The specs must load and every pinned source extract must still hash true."""
    from harness.adapters.transfer_spec import TransferSpecError

    out: List[Refusal] = []
    for config_id in configs:
        try:
            _spec_sha(config_id)
        except (TransferSpecError, OSError) as exc:
            out.append(Refusal(
                code="SPEC",
                detail=f"{config_id}: {exc}",
                remedy=("the frozen strategy spec or one of its pinned source "
                        "extracts has drifted; re-extract and re-freeze before running"),
            ))
    return out


def _results_readme_refusals(dataset: str = DATASET,
                             *, repo_root: str = REPO_ROOT) -> List[Refusal]:
    """CLAUDE.md rule 8: every dataset under results/ is listed in results/README.md.

    Checked here rather than left to review because the listing has to exist
    BEFORE the directory does — a dataset that appears without a README entry
    naming the report that documents it is an orphan the moment it is written.
    """
    path = os.path.join(repo_root, "results", "README.md")
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        return [Refusal(code="RESULTS-README",
                        detail=f"results/README.md cannot be read: {exc}",
                        remedy="restore it; rule 8 has no exception")]
    if dataset in text:
        return []
    return [Refusal(
        code="RESULTS-README",
        detail=f"results/README.md does not mention `{dataset}`",
        remedy=(f"add an entry for results/{dataset} (and for "
                f"results/{os.path.basename(CALIBRATION_DIR)}) naming the report that "
                f"will document it, per CLAUDE.md rule 8"),
    )]


def preflight(manifest: Dict[str, Any], *, calibration_dir: str = CALIBRATION_DIR,
              configs: Sequence[str] = CONFIGS,
              dataset: str = DATASET) -> List[Refusal]:
    """Everything that must be true before a single dollar is spent.

    All checks run and ALL refusals are returned, never just the first: an
    operator fixing a schema enum only to be told about a manifest pin, then
    about calibration, is three round-trips where one would do.
    """
    return (_spec_refusals(configs)
            + _calibration_refusals(calibration_dir)
            + _schema_refusals(configs)
            + _manifest_pin_refusals(manifest, configs)
            + _results_readme_refusals(dataset))


# --------------------------------------------------------------------------- #
# Resume
# --------------------------------------------------------------------------- #
def completed_cells(batch_dir: str, ids: Dict[str, str]) -> Dict[Tuple[str, str, int], str]:
    """Cells already bought in ``batch_dir``, keyed ``(task_id, config_id, rep)``.

    ``run.py`` stamps a UTC timestamp into every run id, so a cell cannot be
    recognised by an exact directory name — it is matched on the
    ``<task_id>__<config>__rep<n>__`` prefix. A cell counts as SETTLED when its
    directory holds a ``result.json``, i.e. the run produced a validated summary.

    Settled means BILLED, not necessarily good. A run that completed and then
    failed validation is still settled and is not re-run, because re-running it
    would spend the money twice to reach the same broken artifact; the failure is
    a human's problem, and :func:`run_probe` reports it. Only a cell that left no
    ``result.json`` at all — killed mid-flight by the idle reaper, or halted at
    the spend cap — is retried.
    """
    found: Dict[Tuple[str, str, int], str] = {}
    if not os.path.isdir(batch_dir):
        return found
    by_task = {v: k for k, v in ids.items()}
    for name in sorted(os.listdir(batch_dir)):
        if not os.path.isfile(os.path.join(batch_dir, name, "result.json")):
            continue
        parts = name.split("__")
        if len(parts) < 4:
            continue
        task_id, config_id, rep_part = parts[0], parts[1], parts[2]
        if task_id not in by_task or not rep_part.startswith("rep"):
            continue
        try:
            rep = int(rep_part[3:])
        except ValueError:
            continue
        found[(task_id, config_id, rep)] = name
    return found


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cell_command(cell: Cell, *, spend_cap_usd: float, dry_run: bool,
                 out_root: Optional[str] = None,
                 manifest: Optional[str] = None,
                 isolation: str = SUBJECT_ISOLATION,
                 egress: str = SUBJECT_EGRESS) -> List[str]:
    """The exact ``run.py`` argv for one cell.

    Shelling out is the design (see the module docstring): the probe owns the
    cell list, not the runner. Every flag here is a registered run condition, so
    the argv is written into the ledger verbatim.
    """
    argv = [
        sys.executable, "-m", "harness.runner.run",
        "--task", cell.task_dir,
        "--config", cell.config_id,
        "--rep", str(cell.rep),
        "--phase", DATASET,
        "--cache-state", CACHE_STATE,
        "--profile", PROFILE.name,
        "--spend-cap-usd", f"{spend_cap_usd:g}",
        "--subject-isolation", isolation,
    ]
    if isolation == "container":
        argv += ["--subject-egress", egress]
    if manifest:
        argv += ["--manifest", manifest]
    if dry_run:
        argv += ["--dry-run"]
        if out_root:
            argv += ["--out-root", out_root]
    return argv


def launch_commands(*, spend_cap_usd: float = DEFAULT_SPEND_CAP_USD,
                    source_root: str = "<path-to-source-checkout>") -> List[Tuple[str, str]]:
    """``(label, command)`` for the two live launches, in the order they must run.

    Calibration first and probe second is not a preference: the probe's preflight
    reads the calibration report, so a probe launched first refuses. Printed
    verbatim and never executed by this module.
    """
    calib = (
        "LAB_ALLOW_SPEND=1 python3 -m harness.runner.transfer_calibration \\\n"
        "  --live \\\n"
        f"  --source-root {source_root} \\\n"
        f"  --out {os.path.relpath(CALIBRATION_DIR, REPO_ROOT)} \\\n"
        f"  --spend-cap-usd {spend_cap_usd:g}"
    )
    probe = (
        "LAB_ALLOW_SPEND=1 python3 -m harness.runner.transfer_probe \\\n"
        "  --live --launch \\\n"
        f"  --spend-cap-usd {spend_cap_usd:g}"
    )
    return [("1. calibration (gates the probe)", calib),
            ("2. probe (27 cells)", probe)]


def shared_cap_note(spend_cap_usd: float) -> str:
    """Why the $300 cap needs an operator, not just a flag.

    The cap is registered as calibration + probe COMBINED, but the kill-switch it
    is passed to (``run.py --spend-cap-usd``) sums realized cost inside ONE
    dataset directory. Passing 300 to both therefore permits up to 300 in each.
    Rather than silently redefine the registered number, the driver states the
    arithmetic and leaves the split to the operator, who knows what calibration
    actually cost by the time the probe is launched.
    """
    spent, n_runs, n_unavail = _known_spend(CALIBRATION_DIR)
    floor = (f" (plus {n_unavail} leg(s) with unavailable cost, so this is a known "
             f"floor)") if n_unavail else ""
    return (
        f"Spend cap ${spend_cap_usd:g} is registered as calibration + probe COMBINED "
        f"(manifest/cp-spend-transfer-probe.md), but --spend-cap-usd is enforced "
        f"per dataset directory. Calibration has so far recorded ${spent:.2f} of "
        f"known spend across {n_runs} run(s){floor}; pass the probe a cap of "
        f"${spend_cap_usd:g} minus that figure to keep the registered total."
    )


def _known_spend(batch_dir: str) -> Tuple[float, int, int]:
    from harness.runner.run import cumulative_spend_usd

    return cumulative_spend_usd(batch_dir)


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def render_plan(cells: Sequence[Cell], timeouts: Dict[str, int],
                ids: Dict[str, str], refusals: Sequence[Refusal],
                settled: Dict[Tuple[str, str, int], str],
                *, spend_cap_usd: float, dry_run: bool,
                out_root: Optional[str], manifest_path: Optional[str]) -> str:
    """The whole plan as text: cells, timing, resume state, preflight, commands."""
    lines: List[str] = []
    lines.append(f"transfer probe — {len(cells)} registered cells "
                 f"(dataset results/{DATASET})")
    lines.append("prereg: manifest/preregistrations/2026-08-27-transfer-probe.md")
    lines.append("CP-SPEND: manifest/cp-spend-transfer-probe.md")
    lines.append("")
    lines.append(f"profile: {PROFILE.name} — {PROFILE.summary}")
    lines.append("  NEW ARM CONDITION: not comparable with batch-1/batch-2 timing.")
    lines.append(f"posture: cache-state={CACHE_STATE} isolation={SUBJECT_ISOLATION} "
                 f"egress={SUBJECT_EGRESS}")
    lines.append("")
    lines.append("resolved timing")
    lines.append("  task                             agent_timeout_s  soft     hard kill  "
                 "--print-timeout")
    for task_id in sorted(timeouts):
        t = PROFILE.timeouts(timeouts[task_id])
        lines.append(f"  {task_id:<32} {timeouts[task_id]:>15}  "
                     f"{str(t.budget_s) + 's':<8} {str(t.kill_s) + 's':<10} "
                     f"{t.print_timeout}")
    lines.append("")
    lines.append("cells, in run order")
    for cell in cells:
        task_id = ids[cell.task_key]
        prior = settled.get((task_id, cell.config_id, cell.rep))
        mark = f"SETTLED ({prior})" if prior else "pending"
        lines.append(f"  {cell.index:>2}. {cell.label:<16} {mark}")
    n_settled = sum(1 for c in cells
                    if (ids[c.task_key], c.config_id, c.rep) in settled)
    lines.append(f"  -> {n_settled} settled, {len(cells) - n_settled} to run")
    lines.append("")
    lines.append(shared_cap_note(spend_cap_usd))
    lines.append("")
    if refusals:
        lines.append(f"PREFLIGHT: {len(refusals)} refusal(s) — a live batch will not start")
        for r in refusals:
            lines.append(r.render())
    else:
        lines.append("PREFLIGHT: clear")
    lines.append("")
    lines.append("launch commands (verbatim; this driver does not run them)")
    for label, command in launch_commands(spend_cap_usd=spend_cap_usd):
        lines.append("")
        lines.append(f"  # {label}")
        for line in command.splitlines():
            lines.append(f"  {line}")
    lines.append("")
    lines.append("per-cell command (cell 1, as this invocation would issue it)")
    if cells:
        argv = cell_command(cells[0], spend_cap_usd=spend_cap_usd, dry_run=dry_run,
                            out_root=out_root, manifest=manifest_path)
        lines.append("  " + " ".join(argv))
    return "\n".join(lines) + "\n"


def write_marker(batch_dir: str, timeouts: Dict[str, int]) -> str:
    """Write the dataset's NEW-ARM timing marker. Called only at launch."""
    os.makedirs(batch_dir, exist_ok=True)
    path = os.path.join(batch_dir, "TIMING-PROFILE.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(P.dataset_marker(PROFILE, dataset=f"results/{DATASET}", tasks=timeouts))
    return path


def append_ledger(batch_dir: str, record: Dict[str, Any]) -> None:
    """Append one cell outcome to the batch ledger.

    A run artifact, not telemetry: it records what the driver did (argv, exit
    code, whether the cell was skipped as settled) so an interrupted batch's
    history is readable without diffing directory listings. It never carries a
    cost or token figure — those live in the runs' own summaries.
    """
    with open(os.path.join(batch_dir, "driver-ledger.jsonl"), "a",
              encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def run_probe(*, mode: str, spend_cap_usd: float, manifest_path: str,
              out_root: Optional[str], calibration_dir: str,
              cells: Optional[Sequence[Cell]] = None) -> int:
    """Plan, preflight and (only if asked) execute the registered cells."""
    import yaml

    with open(manifest_path, encoding="utf-8") as fh:
        manifest = yaml.safe_load(fh) or {}

    cells = list(cells if cells is not None else plan_cells())
    timeouts = task_timeouts()
    ids = task_ids()
    dry_run = mode == "dry-run"

    if dry_run:
        batch_dir = out_root or tempfile.mkdtemp(prefix="lab-probe-dryrun-")
        out_root = batch_dir
    else:
        batch_dir = DATASET_DIR

    settled = completed_cells(batch_dir, ids)
    refusals = preflight(manifest, calibration_dir=calibration_dir)
    manifest_arg = (manifest_path
                    if os.path.abspath(manifest_path) != os.path.abspath(DEFAULT_MANIFEST)
                    else None)

    print(render_plan(cells, timeouts, ids, refusals, settled,
                      spend_cap_usd=spend_cap_usd, dry_run=dry_run,
                      out_root=out_root, manifest_path=manifest_arg))

    if mode == "plan-only":
        print("[probe] PLAN ONLY — nothing was launched.", file=sys.stderr)
        return EXIT_PLAN_ONLY

    if refusals:
        if not dry_run:
            print(f"[probe] REFUSED — {len(refusals)} preflight refusal(s); "
                  f"no cell started, nothing was billed.", file=sys.stderr)
            return EXIT_REFUSED
        # A dry run exercises the control flow with stub adapters and no spend, so
        # the refusals are reported and stepped over rather than enforced. They are
        # NOT waived: the same refusals block --live, and there is no flag that
        # would let a live batch past them.
        print(f"[probe] dry run: {len(refusals)} preflight refusal(s) would block a "
              f"live batch; proceeding with stub adapters and no spend.",
              file=sys.stderr)

    if not dry_run and os.environ.get("LAB_ALLOW_SPEND") != "1":
        print("[probe] REFUSED — a live batch bills a real account and requires "
              "CP-SPEND approval; set LAB_ALLOW_SPEND=1, or pass --dry-run.",
              file=sys.stderr)
        return EXIT_REFUSED

    os.makedirs(batch_dir, exist_ok=True)
    marker = write_marker(batch_dir, timeouts)
    print(f"[probe] timing marker: {marker}")

    overall = EXIT_OK
    failed: List[str] = []
    for cell in cells:
        task_id = ids[cell.task_key]
        key = (task_id, cell.config_id, cell.rep)
        if key in settled:
            print(f"[probe] {cell.index:>2}/{len(cells)} {cell.label}: SETTLED "
                  f"({settled[key]}) — skipped")
            append_ledger(batch_dir, {"cell": cell.label, "index": cell.index,
                                      "action": "skipped-settled",
                                      "run_dir": settled[key]})
            continue
        argv = cell_command(cell, spend_cap_usd=spend_cap_usd, dry_run=dry_run,
                            out_root=out_root, manifest=manifest_arg)
        print(f"[probe] {cell.index:>2}/{len(cells)} {cell.label}: {' '.join(argv)}")
        proc = subprocess.run(argv, cwd=REPO_ROOT, check=False)  # noqa: S603
        append_ledger(batch_dir, {"cell": cell.label, "index": cell.index,
                                  "action": "ran", "argv": argv,
                                  "returncode": proc.returncode})
        if proc.returncode == EXIT_SPEND_CAP:
            print(f"[probe] SPEND CAP reached before {cell.label}; halting. "
                  f"Re-invoke (optionally with a raised --spend-cap-usd) to resume: "
                  f"settled cells are skipped.", file=sys.stderr)
            return EXIT_SPEND_CAP
        if proc.returncode != 0:
            failed.append(f"{cell.label} (run.py exit {proc.returncode})")
            overall = EXIT_CELL_FAILED

    if failed:
        print(f"[probe] {len(failed)} cell(s) did not complete cleanly:",
              file=sys.stderr)
        for line in failed:
            print(f"  - {line}", file=sys.stderr)
        if any(r.code == "SCHEMA-ENUM" for r in refusals):
            # Expected, and the point: with R9/R6/R10 outside the frozen enum every
            # cell runs, produces a summary, and fails schema validation on the
            # configuration_id alone. In a dry run that is the DEMONSTRATION of the
            # SCHEMA-ENUM refusal, not a defect in the ladder; live, it would be 27
            # billed cells' worth of the same thing, which is why the refusal blocks.
            print("[probe] every one of those is expected while SCHEMA-ENUM stands: "
                  "the run completes and then fails on configuration_id. Widen the "
                  "enum (CP-SCHEMA) and re-run.", file=sys.stderr)
        print("[probe] a cell that billed and then failed validation is NOT retried "
              "on resume; inspect it before re-invoking.", file=sys.stderr)
    if dry_run:
        print("[probe] DRY RUN — stub adapters, no model was called, nothing was "
              f"billed. Output under {batch_dir}", file=sys.stderr)
    return overall


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description=("Transfer-probe driver: 27 registered cells "
                     "({W6,W4b,W4} x {r9,r6,r10} x rep1-3) into results/transfer-probe. "
                     "Default mode prints the plan and launches nothing."))
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--plan-only", action="store_true",
                      help="print the cells, timing, preflight and launch commands, "
                           "then exit 4 (the default)")
    mode.add_argument("--dry-run", action="store_true",
                      help="execute every pending cell with stub adapters into a temp "
                           "dir; no spend, no clone, no network")
    mode.add_argument("--live", action="store_true",
                      help="execute pending cells for real (needs --launch, "
                           "LAB_ALLOW_SPEND=1 and a clear preflight)")
    ap.add_argument("--launch", action="store_true",
                    help="required alongside --live; without it --live prints the plan "
                         "and exits without starting anything")
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST)
    ap.add_argument("--calibration-dir", default=CALIBRATION_DIR,
                    help="where the calibration reports live (the preflight gate)")
    ap.add_argument("--out-root", default=None,
                    help="output root for --dry-run (default: a temp dir; never results/)")
    ap.add_argument("--spend-cap-usd", type=float, default=DEFAULT_SPEND_CAP_USD,
                    help=f"passed to each run.py invocation (default "
                         f"{DEFAULT_SPEND_CAP_USD:g}; registered as calibration + probe "
                         f"COMBINED — see the plan's spend-cap note)")
    args = ap.parse_args(argv)

    if args.live and not args.launch:
        selected = "plan-only"
        print("[probe] --live without --launch: printing the plan only.",
              file=sys.stderr)
    elif args.live:
        selected = "live"
    elif args.dry_run:
        selected = "dry-run"
    else:
        selected = "plan-only"

    try:
        return run_probe(mode=selected, spend_cap_usd=args.spend_cap_usd,
                         manifest_path=args.manifest, out_root=args.out_root,
                         calibration_dir=args.calibration_dir)
    except (ProbeError, OSError) as exc:
        print(f"[probe] {exc}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
