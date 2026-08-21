#!/usr/bin/env python3
"""Offline RE-GRADE: re-run the HIDDEN gate against a completed run's archived diff.

Why this exists. Screening batch 1 graded every `test_generation` and `pr_review`
cell against a subject tree its gate could not read: the agent's edits live in a
Docker volume owned by the agent uid, the gate container runs as root, and git's
safe.directory guard refused the repo. A sealed runner whose first move is "which
files did the agent add?" got an empty list, which is indistinguishable from "the
agent added none". The public gate had a guard for this (G0) and passed those same
cells cleanly; the hidden gate did not, and failed them. The contradiction in the
batch-1 data — public T1-T4 all pass, hidden fail, on the same tree — is the
instrument speaking, not the agent. lib.sh's ``git_trust_subject`` is the fix;
this tool is how the already-billed runs get an honest verdict without respending.

What it does, per run: recreates the run's subject tree by seeding a fresh named
volume from the AGENT image (so the tree is owned by the agent uid, exactly as it
was) and applying the run's archived ``agent-solution.diff`` as that uid; then
runs ONLY ``check-hidden.sh`` in the GATE image against it, with the sealed set
mounted read-only and the current (fixed) harness mounted over the image's baked
copy. No model is invoked and no network is enabled: both containers are
``--network=none``. The only cost is CPU.

What it does NOT do. It never edits the original run's artifacts. The amended
verdict lands beside them as ``regrade-summary.json`` plus the gate transcript as
``regrade-gate-hidden.log``, and an existing regrade is refused rather than
overwritten (``--force`` to redo one deliberately). The public gate is NOT re-run:
its verdict stood on a tree it could read, so it is carried over verbatim from
``gate-public.json`` and combined with the new hidden result through the runner's
own ``_gate_verdict``. When the tree cannot be reconstructed (no archived diff, or
the diff will not apply) the run is recorded ``unavailable`` with the reason —
never zero-filled and never guessed (CLAUDE.md rule 3).

The sealed material is mounted, hashed and executed; it is never read or printed
by this tool. The recorded hash is what the gate itself reports.

Generation 2 (``--generation 2``) widens this: it re-runs BOTH gates, under a gate
image tagged with a hash of the gate's own content, and reports every public check
before and after. See the ``regrade-v2`` section below for why the public verdict
can no longer be carried over. Its artifacts are named ``regrade-v2-*``, so a run
can carry the original verdict, a v1 amendment and a v2 amendment side by side.

Usage:
    python -m harness.runner.regrade --results results/screening-batch1 \
        --task tasks/suite/W1-test-generation [--generation {1,2}]
        [--only RUN_DIR ...] [--force] [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from harness.analysis.archive import truncation  # noqa: E402
from harness.container.exec import (  # noqa: E402
    TARGET_AGENT,
    TARGET_GATE,
    agent_build_args,
    agent_image_tag,
    create_volume,
    docker_run_argv,
    gate_image_content_digest,
    image_exists,
    remove_volume,
    subject_image_tag,
)
from harness.runner.run import (  # noqa: E402
    CONTAINER_LAB_ROOT,
    _ensure_image,
    _gate_verdict,
    _load_yaml,
    hidden_tests_dir,
    load_task,
)

DEFAULT_MANIFEST = os.path.join(REPO_ROOT, "manifest", "delivery-manifest.yaml")

REGRADE_SUMMARY = "regrade-summary.json"
REGRADE_LOG = "regrade-gate-hidden.log"
#: Bumped when the METHOD changes in a way that makes older amended verdicts
#: non-comparable, so a summarizer can tell two regrade generations apart.
REGRADE_VERSION = "1"

#: Applying the archived diff. ``git apply`` is given the whole artifact: the
#: tracked-file diff and the new-file diffs the archiver appends for untracked
#: agent output (a test-generation agent's entire product). An empty artifact is
#: not an error — it is a run whose agent produced nothing, and the pristine tree
#: is the honest thing to grade.
_APPLY = (
    'set -e\n'
    'if [ -s /tmp/agent.diff ]; then\n'
    '  git apply --whitespace=nowarn /tmp/agent.diff\n'
    'else\n'
    '  echo "[regrade] archived diff is empty: grading the pristine tree" >&2\n'
    'fi\n'
    'git status --porcelain --untracked-files=all -- ":!node_modules" | head -200\n'
)

_TIMEOUT_APPLY_S = 300
_TIMEOUT_GATE_S = 3600


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(argv: List[str], timeout: int) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(  # noqa: S603 - argv built from repo config
            argv, capture_output=True, text=True, check=False, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", (exc.stderr or "") + f"\n[regrade] timed out after {timeout}s"


def _harness_provenance() -> Dict[str, str]:
    """Which harness bytes did the grading — the regrade's own auditability.

    The commit is recorded, but so is a content hash of the gate scripts that
    actually ran: a regrade taken from a dirty tree is still reproducible if the
    bytes are pinned, and a commit alone would not say which bytes those were.
    """
    rc, out, _ = _run(["git", "-C", REPO_ROOT, "rev-parse", "HEAD"], 30)
    head = out.strip() if rc == 0 else "unavailable"
    rc, out, _ = _run(["git", "-C", REPO_ROOT, "status", "--porcelain",
                       "--", "harness/task-tools"], 30)
    dirty = bool(out.strip()) if rc == 0 else True
    digest = hashlib.sha256()
    tools = os.path.join(REPO_ROOT, "harness", "task-tools")
    for root, dirs, files in os.walk(tools):
        dirs.sort()
        for name in sorted(files):
            path = os.path.join(root, name)
            digest.update(os.path.relpath(path, tools).encode("utf-8") + b"\0")
            with open(path, "rb") as fh:
                digest.update(fh.read())
            digest.update(b"\0")
    return {"repo_head": head,
            "task_tools_uncommitted": "yes" if dirty else "no",
            "task_tools_sha256": "sha256:" + digest.hexdigest(),
            "note": "the gate image's baked harness is overmounted with the "
                    "working tree's, so the FIXED gate does the grading"}


def _public_rc(run_dir: str) -> Tuple[Optional[int], str]:
    """The original public-gate exit code, recovered from its report.

    The runner records the report, not the exit code, but the code is a function
    of it: check-public.sh exits non-zero iff any check failed. Recovering it is
    what lets the amended verdict be produced by the SAME ``_gate_verdict`` the
    runner uses, rather than by a second, divergent rule written here.
    """
    path = os.path.join(run_dir, "gate-public.json")
    if not os.path.exists(path):
        return None, "gate-public.json is absent"
    with open(path, encoding="utf-8") as fh:
        checks = (json.load(fh) or {}).get("checks") or []
    if not checks:
        return None, "gate-public.json records no checks"
    failed = [c["id"] for c in checks if c.get("status") != "pass"]
    return (1 if failed else 0), (f"failed: {', '.join(failed)}" if failed else "all checks pass")


def _original(run_dir: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"acceptance_result": "unavailable",
                           "hidden_status": "unavailable",
                           "hidden_hash": None, "hidden_version": None}
    spath = os.path.join(run_dir, "summary.json")
    if os.path.exists(spath):
        with open(spath, encoding="utf-8") as fh:
            acc = (json.load(fh) or {}).get("acceptance") or {}
        out["acceptance_result"] = acc.get("result", "unavailable")
    hpath = os.path.join(run_dir, "gate-hidden.json")
    if os.path.exists(hpath):
        with open(hpath, encoding="utf-8") as fh:
            hid = json.load(fh) or {}
        out.update(hidden_status=hid.get("status", "unavailable"),
                   hidden_hash=hid.get("hash"), hidden_version=hid.get("version"))
    return out


def _apply_diff(volume: str, agent_tag: str, diff_path: str) -> Tuple[int, str, str]:
    argv = docker_run_argv(
        agent_tag, ["bash", "-lc", _APPLY],
        mounts=[(volume, "/subject", "rw"), (diff_path, "/tmp/agent.diff", "ro")],
        workdir="/subject", network="none")
    return _run(argv, _TIMEOUT_APPLY_S)


def _hidden_gate(volume: str, gate_tag: str, task, out_dir: str) -> Tuple[int, str, str]:
    task_c = f"{CONTAINER_LAB_ROOT}/{task.task_dir_rel}"
    hidden_host = hidden_tests_dir(task.task_dir)
    argv = docker_run_argv(
        gate_tag, ["bash", f"{CONTAINER_LAB_ROOT}/harness/task-tools/gate/check-hidden.sh"],
        mounts=[
            (volume, f"{task_c}/.work/repo", "rw"),
            # The image's baked harness predates the fix; the working tree's is
            # what must grade. Read-only: a gate run cannot alter the harness.
            (os.path.join(REPO_ROOT, "harness"), f"{CONTAINER_LAB_ROOT}/harness", "ro"),
            (hidden_host, f"{task_c}/hidden", "ro"),
            (out_dir, "/out", "rw"),
        ],
        workdir=f"{task_c}/.work/repo", network="none",
        env={"TASK_DIR": task_c, "TASK_WORKDIR": f"{task_c}/.work",
             "HIDDEN_TESTS_DIR": f"{task_c}/hidden",
             "HIDDEN_REPORT": "/out/gate-hidden.json"})
    return _run(argv, _TIMEOUT_GATE_S)


def _unavailable(run_dir: str, task, reason: str, original: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "regrade_version": REGRADE_VERSION,
        "run_id": os.path.basename(run_dir),
        "task_id": task.task_id,
        "regraded_at": _now(),
        "provenance": "amended",
        "status": "unavailable",
        "reason": reason,
        "original": original,
        "amended": {"acceptance_result": "unavailable", "hidden_status": "unavailable",
                    "hidden_hash": None, "hidden_version": None, "gate_exit_code": None},
        "changed": False,
    }


def regrade_run(run_dir: str, task, *, force: bool = False,
                dry_run: bool = False) -> Dict[str, Any]:
    """Re-grade one run. Returns the regrade record (also written to the run dir)."""
    run_id = os.path.basename(run_dir)
    target = os.path.join(run_dir, REGRADE_SUMMARY)
    if os.path.exists(target) and not force:
        with open(target, encoding="utf-8") as fh:
            existing = json.load(fh)
        existing["_skipped"] = "already regraded (use --force to redo)"
        return existing

    original = _original(run_dir)
    diff_path = os.path.join(run_dir, "agent-solution.diff")
    if not os.path.exists(diff_path):
        record = _unavailable(run_dir, task,
                              "no archived agent-solution.diff: the subject tree "
                              "cannot be reconstructed, so nothing can be graded",
                              original)
        if not dry_run:
            _write(target, record)
        return record

    if dry_run:
        return {"run_id": run_id, "task_id": task.task_id, "would_regrade": True,
                "diff_bytes": os.path.getsize(diff_path), "original": original}

    gate_tag = subject_image_tag(task.task_id, task.pinned_commit)
    agent_tag = agent_image_tag(task.task_id, task.pinned_commit)
    volume = f"lab-regrade-{run_id.lower()}"[:120]
    out_dir = os.path.join(run_dir, ".regrade-out")
    os.makedirs(out_dir, exist_ok=True)
    report_path = os.path.join(out_dir, "gate-hidden.json")
    if os.path.exists(report_path):
        os.unlink(report_path)

    remove_volume(volume)
    create_volume(volume)
    try:
        rc, out, err = _apply_diff(volume, agent_tag, diff_path)
        if rc != 0:
            record = _unavailable(
                run_dir, task,
                f"the archived diff would not apply to the pinned tree (rc={rc}): "
                f"{(err or out).strip().splitlines()[-1] if (err or out).strip() else 'no detail'}",
                original)
            _write(target, record)
            return record
        apply_log = out + err

        g_rc, g_out, g_err = _hidden_gate(volume, gate_tag, task, out_dir)
        with open(os.path.join(run_dir, REGRADE_LOG), "w", encoding="utf-8") as fh:
            fh.write("--- diff apply ---\n" + apply_log +
                     "\n--- hidden gate (stdout) ---\n" + g_out +
                     "\n--- hidden gate (stderr) ---\n" + g_err +
                     f"\n--- exit: {g_rc}\n")

        hidden: Dict[str, Any] = {}
        if os.path.exists(report_path):
            with open(report_path, encoding="utf-8") as fh:
                hidden = json.load(fh) or {}
        pub_rc, pub_detail = _public_rc(run_dir)
        if pub_rc is None:
            record = _unavailable(run_dir, task,
                                  f"the original public-gate verdict cannot be "
                                  f"recovered ({pub_detail}), so no combined "
                                  f"verdict can be stated", original)
            _write(target, record)
            return record

        _, result, _ = _gate_verdict(pub_rc, g_rc, {})
        record = {
            "regrade_version": REGRADE_VERSION,
            "run_id": run_id,
            "task_id": task.task_id,
            "regraded_at": _now(),
            "provenance": "amended",
            "status": "graded",
            "reason": "batch-1 instrument error: the hidden gate graded a subject "
                      "tree git refused to read (safe.directory), so its discovery "
                      "step returned empty. Fixed in harness/task-tools/lib.sh "
                      "(git_trust_subject); this is the same sealed set re-applied "
                      "to the same archived agent output.",
            "method": {
                "hidden_gate_only": True,
                "public_gate": f"carried over from the original run ({pub_detail})",
                "subject_tree": "fresh volume seeded from the agent image, archived "
                                "agent-solution.diff applied as the agent uid",
                "network": "none (both containers)",
                "model_spend": "none",
                "gate_image": gate_tag,
                "agent_image": agent_tag,
                "harness": _harness_provenance(),
            },
            "original": original,
            "amended": {
                "acceptance_result": result,
                "hidden_status": hidden.get("status", "unavailable"),
                "hidden_hash": hidden.get("hash"),
                "hidden_version": hidden.get("version"),
                "gate_exit_code": g_rc,
                "public_exit_code": pub_rc,
            },
            "changed": result != original.get("acceptance_result"),
        }
        # The sealed bytes that judged then and now must be the same bytes, or the
        # two verdicts are not comparable and the record must say so.
        if (original.get("hidden_hash") and record["amended"]["hidden_hash"]
                and original["hidden_hash"] != record["amended"]["hidden_hash"]):
            record["sealed_set_changed"] = (
                "the sealed set differs from the one used in the original run; the "
                "amended verdict is NOT a like-for-like correction")
        _write(target, record)
        return record
    finally:
        remove_volume(volume)
        for stale in (report_path,):
            if os.path.exists(stale):
                os.unlink(stale)
        if os.path.isdir(out_dir) and not os.listdir(out_dir):
            os.rmdir(out_dir)


def _write(path: str, record: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
        fh.write("\n")


# --------------------------------------------------------------------------- #
# regrade-v2 — BOTH gates, re-run under a content-tagged (post-fix) gate image
# --------------------------------------------------------------------------- #
#
# v1 (above) re-ran the hidden gate only and carried the public verdict over,
# because the defect it corrected was in the hidden gate alone. Two later defects
# are not confined that way:
#
#   D1 — the gate image tag was (task, pin), so a gate-logic change was served
#        from the Docker cache and the OLD grader decided the run. Fixed by
#        hashing the gate content into the tag; v2 therefore states the tag it
#        used, and an image built before the fix cannot answer to that tag.
#   D2 — `leak_found` counted the review artifact the harness itself delivers as
#        leakage, failing a PUBLIC check on `pr_review` cells. A public verdict
#        carried over verbatim would carry that artifact forward.
#
# So v2 re-runs both gates and reports each public check before and after. It
# writes `regrade-v2-*` beside — never over — the run's originals and any v1
# regrade: three generations of verdict can coexist and be told apart.
REGRADE_V2_VERSION = "2"
REGRADE_V2_SUMMARY = "regrade-v2-summary.json"
REGRADE_V2_PUBLIC_LOG = "regrade-v2-gate-public.log"
REGRADE_V2_HIDDEN_LOG = "regrade-v2-gate-hidden.log"
REGRADE_V2_PUBLIC_REPORT = "regrade-v2-gate-public.json"
REGRADE_V2_HIDDEN_REPORT = "regrade-v2-gate-hidden.json"

_V2_REASON = (
    "re-graded under the post-#27 harness: D1 (the gate image tag ignored gate "
    "content, so a fixed grader was served from cache) and D2 (the delivered "
    "review artifact was counted as leakage by a public check). Both gates were "
    "re-run against the same archived agent output; no model was invoked."
)


def _checks_by_id(path: str) -> Dict[str, str]:
    """``{check id: status}`` from a gate-public.json, or ``{}`` if absent."""
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        checks = (json.load(fh) or {}).get("checks") or []
    return {c["id"]: c.get("status", "unavailable") for c in checks if c.get("id")}


def _check_delta(before: Dict[str, str], after: Dict[str, str]) -> Dict[str, Any]:
    """Name every public check's before/after, and classify the movements.

    The classification is deliberately literal. A fail->pass is reported as
    ``cleared`` — the check now passes under the fixed grader — and NOT as
    "was an artifact": which of the two graders was right is a claim about the
    fix, made once in the report, not re-asserted per check. A fail->fail is a
    genuine failure by construction: the same check, the same tree, both graders
    agree. A pass->fail is surfaced loudest of all, because a fix that breaks a
    check that used to pass is the one outcome nobody is looking for.
    """
    ids = sorted(set(before) | set(after))
    rows = [{"id": i, "before": before.get(i, "absent"), "after": after.get(i, "absent")}
            for i in ids]
    passed = lambda s: s == "pass"  # noqa: E731
    return {
        "checks": rows,
        "cleared": [r["id"] for r in rows if not passed(r["before"]) and passed(r["after"])],
        "still_failing": [r["id"] for r in rows
                          if not passed(r["before"]) and not passed(r["after"])],
        "newly_failing": [r["id"] for r in rows if passed(r["before"]) and not passed(r["after"])],
        "unchanged_pass": [r["id"] for r in rows if passed(r["before"]) and passed(r["after"])],
    }


def _gate_container(volume: str, gate_tag: str, task, out_dir: str, script: str,
                    report_env: str, report_name: str) -> Tuple[int, str, str]:
    """Run one gate script in the gate image against the reconstructed tree.

    Same mount shape the runner's containerised gate uses, plus the working
    tree's ``harness/`` over the image's baked copy: the tag pins the gate
    CONTENT, and the overmount is what makes the bytes match the tag.
    """
    task_c = f"{CONTAINER_LAB_ROOT}/{task.task_dir_rel}"
    mounts = [
        (volume, f"{task_c}/.work/repo", "rw"),
        (os.path.join(REPO_ROOT, "harness"), f"{CONTAINER_LAB_ROOT}/harness", "ro"),
        (out_dir, "/out", "rw"),
    ]
    env = {"TASK_DIR": task_c, "TASK_WORKDIR": f"{task_c}/.work",
           report_env: f"/out/{report_name}"}
    hidden_host = hidden_tests_dir(task.task_dir)
    if os.path.isdir(hidden_host):
        mounts.append((hidden_host, f"{task_c}/hidden", "ro"))
        env["HIDDEN_TESTS_DIR"] = f"{task_c}/hidden"
    argv = docker_run_argv(
        gate_tag, ["bash", f"{CONTAINER_LAB_ROOT}/harness/task-tools/gate/{script}"],
        mounts=mounts, workdir=f"{task_c}/.work/repo", network="none", env=env)
    return _run(argv, _TIMEOUT_GATE_S)


def _v2_refused(run_dir: str, task, reason: str, original: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "regrade_version": REGRADE_V2_VERSION,
        "run_id": os.path.basename(run_dir),
        "task_id": task.task_id,
        "regraded_at": _now(),
        "provenance": "regrade-v2",
        "status": "refused",
        "reason": reason,
        "original": original,
        "amended": None,
        "changed": False,
    }


def ensure_images(task, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Build the gate image at its CONTENT tag and the agent image; name both.

    Returns the provenance block the regrade record carries. ``built`` records
    whether this call is what created the image, so a record can never be read as
    "a fresh image graded this" when the tag was already present.
    """
    digest = gate_image_content_digest(REPO_ROOT, task.task_dir_rel)
    gate_tag = subject_image_tag(task.task_id, task.pinned_commit, digest)
    agent_tag = agent_image_tag(task.task_id, task.pinned_commit)
    gate_present, agent_present = image_exists(gate_tag), image_exists(agent_tag)
    _ensure_image(task, gate_tag, TARGET_GATE)
    _ensure_image(task, agent_tag, TARGET_AGENT, agent_build_args(manifest, REPO_ROOT))
    return {
        "gate_image": gate_tag,
        "gate_content_digest": digest,
        "gate_image_built_now": not gate_present,
        "agent_image": agent_tag,
        "agent_image_built_now": not agent_present,
        "note": "the gate tag carries a hash of the gate scripts + Dockerfile + "
                "task.yaml (harness/container/exec.py: gate_image_content_digest), "
                "so a pre-fix image cannot answer to it",
    }


def regrade_run_v2(run_dir: str, task, images: Dict[str, Any], *,
                   force: bool = False, dry_run: bool = False) -> Dict[str, Any]:
    """Re-grade one run through BOTH gates. Writes ``regrade-v2-*`` beside it."""
    run_id = os.path.basename(run_dir)
    target = os.path.join(run_dir, REGRADE_V2_SUMMARY)
    if os.path.exists(target) and not force:
        with open(target, encoding="utf-8") as fh:
            existing = json.load(fh)
        existing["_skipped"] = "already regraded at v2 (use --force to redo)"
        return existing

    original = _original(run_dir)
    before = _checks_by_id(os.path.join(run_dir, "gate-public.json"))

    # Refuse truncated cells. A run the harness cut off mid-flight has no finished
    # product, so re-grading it would produce a verdict on a fragment and print it
    # in the same table as verdicts on complete work.
    cut = truncation(run_dir)
    if cut:
        record = _v2_refused(run_dir, task,
                             f"run truncated ({cut}); there is no completed agent "
                             f"product to re-grade", original)
        if not dry_run:
            _write(target, record)
        return record

    diff_path = os.path.join(run_dir, "agent-solution.diff")
    if dry_run:
        return {"run_id": run_id, "task_id": task.task_id, "would_regrade": True,
                "diff_bytes": os.path.getsize(diff_path), "original": original,
                "gate_image": images["gate_image"]}

    volume = f"lab-regrade2-{run_id.lower()}"[:120]
    out_dir = os.path.join(run_dir, ".regrade-v2-out")
    os.makedirs(out_dir, exist_ok=True)
    pub_report = os.path.join(out_dir, "gate-public.json")
    hid_report = os.path.join(out_dir, "gate-hidden.json")
    for stale in (pub_report, hid_report):
        if os.path.exists(stale):
            os.unlink(stale)

    remove_volume(volume)
    create_volume(volume)
    try:
        rc, out, err = _apply_diff(volume, images["agent_image"], diff_path)
        if rc != 0:
            tail = (err or out).strip().splitlines()
            record = _v2_refused(
                run_dir, task,
                f"the archived diff would not apply to the pinned tree (rc={rc}): "
                f"{tail[-1] if tail else 'no detail'}", original)
            _write(target, record)
            return record
        apply_log = out + err

        p_rc, p_out, p_err = _gate_container(volume, images["gate_image"], task, out_dir,
                                             "check-public.sh", "GATE_REPORT",
                                             "gate-public.json")
        _write_log(os.path.join(run_dir, REGRADE_V2_PUBLIC_LOG),
                   "public", apply_log, p_out, p_err, p_rc)
        h_rc, h_out, h_err = _gate_container(volume, images["gate_image"], task, out_dir,
                                             "check-hidden.sh", "HIDDEN_REPORT",
                                             "gate-hidden.json")
        _write_log(os.path.join(run_dir, REGRADE_V2_HIDDEN_LOG),
                   "hidden", apply_log, h_out, h_err, h_rc)

        after = _checks_by_id(pub_report)
        hidden: Dict[str, Any] = {}
        if os.path.exists(hid_report):
            with open(hid_report, encoding="utf-8") as fh:
                hidden = json.load(fh) or {}
        for src, dst in ((pub_report, REGRADE_V2_PUBLIC_REPORT),
                         (hid_report, REGRADE_V2_HIDDEN_REPORT)):
            if os.path.exists(src):
                os.replace(src, os.path.join(run_dir, dst))

        _, result, _ = _gate_verdict(p_rc, h_rc, {})
        record = {
            "regrade_version": REGRADE_V2_VERSION,
            "run_id": run_id,
            "task_id": task.task_id,
            "regraded_at": _now(),
            "provenance": "regrade-v2",
            "status": "graded",
            "reason": _V2_REASON,
            "method": {
                "gates_re_run": ["public", "hidden"],
                "subject_tree": "fresh volume seeded from the agent image, archived "
                                "agent-solution.diff applied as the agent uid",
                "network": "none (all containers)",
                "model_spend": "none",
                "images": images,
                "harness": _harness_provenance(),
            },
            "original": {**original, "public_checks": before},
            "amended": {
                "acceptance_result": result,
                "hidden_status": hidden.get("status", "unavailable"),
                "hidden_hash": hidden.get("hash"),
                "hidden_version": hidden.get("version"),
                "gate_exit_code": h_rc,
                "public_exit_code": p_rc,
                "public_checks": after,
            },
            "public_check_delta": _check_delta(before, after),
            "changed": result != original.get("acceptance_result"),
        }
        if (original.get("hidden_hash") and record["amended"]["hidden_hash"]
                and original["hidden_hash"] != record["amended"]["hidden_hash"]):
            record["sealed_set_changed"] = (
                "the sealed set differs from the one used in the original run; the "
                "amended verdict is NOT a like-for-like correction")
        _write(target, record)
        return record
    finally:
        remove_volume(volume)
        for stale in (pub_report, hid_report):
            if os.path.exists(stale):
                os.unlink(stale)
        if os.path.isdir(out_dir) and not os.listdir(out_dir):
            os.rmdir(out_dir)


def _write_log(path: str, label: str, apply_log: str, out: str, err: str, rc: int) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("--- diff apply ---\n" + apply_log +
                 f"\n--- {label} gate (stdout) ---\n" + out +
                 f"\n--- {label} gate (stderr) ---\n" + err +
                 f"\n--- exit: {rc}\n")


def find_runs(results_dir: str, task_id: str, only: Optional[List[str]] = None) -> List[str]:
    names = sorted(n for n in os.listdir(results_dir)
                   if n.startswith(task_id + "__")
                   and os.path.isdir(os.path.join(results_dir, n)))
    if only:
        wanted = set(only)
        names = [n for n in names if n in wanted]
    return [os.path.join(results_dir, n) for n in names]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", required=True, help="results/<batch> directory")
    ap.add_argument("--task", required=True, help="task directory (tasks/suite/W1-...)")
    ap.add_argument("--only", nargs="*", help="regrade only these run-dir names")
    ap.add_argument("--force", action="store_true", help="redo an existing regrade")
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST,
                    help="delivery manifest (supplies the task's pinned commit)")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be regraded; run no containers")
    ap.add_argument("--generation", type=int, choices=(1, 2), default=1,
                    help="1 = hidden gate only (the batch-1 correction); "
                         "2 = both gates under a content-tagged post-fix image")
    args = ap.parse_args(argv)

    manifest = _load_yaml(args.manifest)
    task = load_task(os.path.abspath(args.task), manifest)
    runs = find_runs(os.path.abspath(args.results), task.task_id, args.only)
    if not runs:
        print(f"no runs for {task.task_id} under {args.results}", file=sys.stderr)
        return 1

    images: Dict[str, Any] = {}
    if args.generation == 2 and not args.dry_run:
        images = ensure_images(task, manifest)
        print(f"gate image: {images['gate_image']} "
              f"({'built now' if images['gate_image_built_now'] else 'already present'})")
    elif args.generation == 2:
        images = {"gate_image": subject_image_tag(
            task.task_id, task.pinned_commit,
            gate_image_content_digest(REPO_ROOT, task.task_dir_rel))}

    print(f"regrading {len(runs)} run(s) of {task.task_id} at generation "
          f"{args.generation} [gate_type={task.gate_type}]"
          f"{' (dry run)' if args.dry_run else ''}")
    changed = 0
    for run_dir in runs:
        if args.generation == 2:
            rec = regrade_run_v2(run_dir, task, images,
                                 force=args.force, dry_run=args.dry_run)
        else:
            rec = regrade_run(run_dir, task, force=args.force, dry_run=args.dry_run)
        name = os.path.basename(run_dir)
        if rec.get("would_regrade"):
            print(f"  {name}: would regrade "
                  f"(original={rec['original']['acceptance_result']}, "
                  f"{rec['diff_bytes']}B diff)")
            continue
        if rec.get("_skipped"):
            print(f"  {name}: {rec['_skipped']}")
            continue
        if rec["status"] in ("unavailable", "refused"):
            print(f"  {name}: {rec['status'].upper()} — {rec['reason']}")
            continue
        arrow = "->" if rec["changed"] else "=="
        changed += 1 if rec["changed"] else 0
        print(f"  {name}: {rec['original']['acceptance_result']} {arrow} "
              f"{rec['amended']['acceptance_result']} "
              f"(hidden {rec['original']['hidden_status']} -> "
              f"{rec['amended']['hidden_status']})")
        delta = rec.get("public_check_delta")
        if delta:
            for key, mark in (("cleared", "cleared"), ("newly_failing", "NEWLY FAILING"),
                              ("still_failing", "still failing")):
                if delta[key]:
                    print(f"      public {mark}: {', '.join(delta[key])}")
    if not args.dry_run:
        print(f"{changed}/{len(runs)} verdict(s) amended")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
