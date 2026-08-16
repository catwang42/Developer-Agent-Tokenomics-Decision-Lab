"""Warm-series driver — cache-protocol rule 2, redesigned for the FIX-A posture.

Why this module exists
----------------------
The warm-series measures cache economics on ONE task: run 1 cold, runs 2..n warm
in the SAME session (``claude ... --resume <session-id>``) so the provider
prompt-cache carries over (methodology/cache-protocol.md rule 2). Under batch 3's
subject-isolation posture (FIX A), the single-run ``run.py`` stages a *fresh* subject
tree in a NEW ``/var/tmp/lab-subject-*`` path on every invocation. Because each rep
is a separate ``run.py`` process, reps 2..n got a brand-new path with a fresh pinned
tree while ``--resume`` carried a conversation that already believed the task was
done → empty stdout / exit 1 / empty diff, and the warm-cache costing delta was lost
(telemetry-completeness report §4.4).

The fix (approved 2026-07-26): stage the subject tree **ONCE per series** and drive
all reps from a single process that OWNS the staging lifecycle. The same
``/var/tmp/lab-subject-*/repo`` path is reused across every rep (so ``--resume``'s cwd
matches), the staged tree is **reset in place** to the pinned commit BETWEEN reps
(deterministic start, discards the prior rep's solution, ``node_modules`` preserved),
and the staged dir is removed **once** at the end. The task prompt is **byte-identical**
across all reps (``execute`` always sends ``task.prompt``) so "cache is warm" is never
confounded with "prompt differs" — deliberately NOT hardened to force a re-solve.

Isolation guarantee (unchanged from FIX A). Staging still goes through
``run.run._stage_subject_outside_repo``: a ``mkdtemp`` under ``TMPDIR`` that is refused
if it resolves inside the lab repo, containing ONLY the subject repo. canonical/,
hidden/ and task.yaml are never staged, so from ``<staged>/repo`` no ``../`` chain
reaches them. Reusing the same path across reps and resetting in place introduces no
new relative-traversal path; the honest-scope caveat (same-uid, no container/fs
namespace, absolute paths not confined — Phase-4 container leg) is unchanged.

This driver performs NO model spend by itself; a live series still requires a
CP-SPEND-approved invocation (``LAB_ALLOW_SPEND=1``). ``--dry-run`` exercises the full
control flow (stage once → reset between reps → cleanup once) against a synthetic git
tree and the :class:`StubAdapter`, with no spend/clone/network.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from typing import List, Optional

from harness.runner import run as R


def _git(repo: str, *args: str) -> str:
    """Run a git command in ``repo``, returning stdout (raises on non-zero)."""
    return subprocess.run(  # noqa: S603
        ["git", "-C", repo, *args],
        check=True, capture_output=True, text=True,
    ).stdout


def _staged_head(staged_repo: str) -> str:
    """The pinned commit the subject tree was staged at (its detached HEAD)."""
    return _git(staged_repo, "rev-parse", "HEAD").strip()


def _reset_staged_repo(staged_repo: str, pin: str, run_dir: str) -> str:
    """Reset the STAGED subject tree in place to ``pin`` (reset.sh semantics).

    Mirrors ``harness/task-tools/reset.sh`` but targets ``<staged>/repo`` instead of
    ``<TASK_DIR>/.work/repo`` — the whole point of the warm-series driver is that the
    staged tree PERSISTS across reps (path preserved for ``--resume``) and is restored
    between them rather than re-staged. Discards the prior rep's working-tree changes,
    preserves ``node_modules`` (gitignored + reproducible), proves the tree is clean,
    and records the canonical tree hash so idempotency is provable (every rep must
    reset to the SAME hash). Returns that tree hash.
    """
    _git(staged_repo, "-c", "advice.detachedHead=false", "checkout", "--quiet",
         "--force", pin)
    _git(staged_repo, "clean", "-ffd", "-e", "node_modules")
    _git(staged_repo, "add", "-A")
    tree_hash = _git(staged_repo, "write-tree").strip()
    _git(staged_repo, "reset", "-q")
    status = _git(staged_repo, "status", "--porcelain")
    if status.strip():
        raise R.RunnerError(
            f"staged tree not clean after reset (pin={pin}):\n{status}"
        )
    with open(os.path.join(run_dir, "staged-reset.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"reset_ok pin={pin} tree={tree_hash}\n")
    return tree_hash


def _dry_run_source_repo() -> str:
    """A minimal synthetic git repo to stand in for a prepared subject (dry-run only).

    Staged through the REAL ``_stage_subject_outside_repo`` so the dry-run exercises
    the actual FIX-A staging + in-repo refusal, giving a real git tree the reset path
    can operate on — all offline, no clone, no spend (CLAUDE.md rule 1).
    """
    src = tempfile.mkdtemp(prefix="lab-warm-src-SYNTHETIC-")
    _git(src, "init", "-q")
    with open(os.path.join(src, "package.json"), "w", encoding="utf-8") as fh:
        fh.write("{}\n")
    os.makedirs(os.path.join(src, "src"))
    with open(os.path.join(src, "src", "app.ts"), "w", encoding="utf-8") as fh:
        fh.write("export const x = 1;\n")
    _git(src, "add", "-A")
    _git(src, "-c", "user.email=lab@local", "-c", "user.name=lab",
         "commit", "-qm", "SYNTHETIC pinned commit")
    return src


def run_series(
    *, task_arg: str, config: str, reps: int, manifest_path: str, phase: str,
    session_id: Optional[str], spend_cap_usd: float, dry_run: bool,
    out_root: Optional[str], stub_scenario: str,
) -> int:
    """Drive a warm-series of ``reps`` runs on one task; return a process exit code.

    Rep 1 is cold (fresh session); reps 2..n resume that session (warm). The subject
    tree is staged once and reset between reps; cleanup happens once at the end.
    """
    if reps < 1:
        raise R.RunnerError(f"--reps must be >= 1 (got {reps})")

    # Session id is minted ONCE and shared by every rep (rep 1 opens it, reps 2..n
    # resume it) — same UUID guard as run.py so a bad id fails clearly, not downstream.
    if session_id is not None:
        try:
            uuid.UUID(str(session_id))
        except ValueError:
            raise R.RunnerError(
                f"--session-id must be a valid UUID (got {session_id!r}); the product "
                f"CLI rejects non-UUID session ids"
            )
    base_session = session_id or str(uuid.uuid4())

    manifest = R._load_yaml(manifest_path)
    if not dry_run and os.environ.get("LAB_ALLOW_SPEND") != "1":
        raise R.RunnerError(
            "a live warm-series bills a real account and requires CP-SPEND approval; "
            "set LAB_ALLOW_SPEND=1 for an approved run, or pass --dry-run"
        )
    R.assert_recordable_configuration(config)
    task = R.load_task(task_arg, manifest)
    plan = R.build_plan(config, manifest, task=task, require_frozen=not dry_run)
    prices, pricing_snapshot = R.resolve_pricing(manifest, plan)
    manifest_rel = os.path.relpath(manifest_path, R.REPO_ROOT)

    if dry_run:
        batch_dir = out_root or tempfile.mkdtemp(prefix="lab-warm-dryrun-")
    else:
        batch_dir = os.path.join(R.REPO_ROOT, "results", phase)

    staged_repo: Optional[str] = None
    staged_root: Optional[str] = None
    pin: Optional[str] = None
    baseline_tree: Optional[str] = None
    overall_rc = 0
    try:
        for rep in range(1, reps + 1):
            run_id = R._make_run_id(task, config, rep)
            run_dir = os.path.join(batch_dir, run_id)

            # Cumulative-spend kill-switch (CP-SPEND option a), checked BEFORE each rep
            # from the realized cost of completed sibling runs in this batch dir.
            spent, n_prior, n_unavail = R.cumulative_spend_usd(batch_dir)
            if spent >= spend_cap_usd:
                floor = (f" (plus {n_unavail} prior leg(s) with unavailable cost)"
                         if n_unavail else "")
                print(
                    f"warm-series: SPEND CAP REACHED — ${spent:.2f} known spend across "
                    f"{n_prior} run(s){floor} >= ${spend_cap_usd:.2f} cap; halting before "
                    f"rep {rep}. Raise --spend-cap-usd to resume.",
                    file=sys.stderr,
                )
                overall_rc = 3
                break
            os.makedirs(run_dir, exist_ok=True)

            # Stage ONCE (rep 1); every rep resets the persisted tree to the pin first.
            if rep == 1:
                if dry_run:
                    src = _dry_run_source_repo()
                    staged_repo = R._stage_subject_outside_repo(src)
                    shutil.rmtree(src, ignore_errors=True)
                else:
                    staged_repo = R._setup_subject(task.task_dir, run_dir)
                staged_root = os.path.dirname(staged_repo)
                pin = _staged_head(staged_repo)

            assert staged_repo is not None and pin is not None  # set on rep 1
            tree_hash = _reset_staged_repo(staged_repo, pin, run_dir)
            if rep == 1:
                baseline_tree = tree_hash
            elif tree_hash != baseline_tree:
                # Non-deterministic reset breaks the "same tree every rep" guarantee —
                # fail the run loudly rather than silently measure against a drifted tree.
                raise R.RunnerError(
                    f"reset determinism violated at rep {rep}: staged tree {tree_hash} "
                    f"!= rep-1 baseline {baseline_tree}"
                )

            if dry_run:
                adapter = R.StubAdapter()
            else:
                adapter = R.REAL_ADAPTERS[plan.adapter_name]()

            # Rep 1 cold / fresh session; reps 2..n warm / resumed — same session id,
            # same staged path, same (byte-identical) task.prompt.
            resume = rep > 1
            cache_state = "cold" if rep == 1 else "warm-series"
            ok, reasons = R.execute_and_validate_run(
                run_dir=run_dir, task=task, plan=plan, adapter=adapter,
                subject_dir=staged_repo, launch=None,
                cache_state=cache_state, base_session=base_session, resume=resume,
                subject_isolation="host", subject_network="none",
                manifest_rel=manifest_rel, prices=prices,
                pricing_snapshot=pricing_snapshot, config_id=config,
                dry_run=dry_run, scenario=stub_scenario,
            )
            verdict = "PASS" if ok else "FAIL"
            print(f"warm-series rep {rep}/{reps} [{cache_state}]: run_dir={run_dir} "
                  f"validate={verdict}")
            if not ok:
                for r in reasons:
                    print(f"  - {r}", file=sys.stderr)
                overall_rc = overall_rc or 1
    finally:
        # Stage-once means clean-up ONCE, after the whole series (never per rep).
        if staged_root:
            shutil.rmtree(staged_root, ignore_errors=True)

    return overall_rc


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Warm-series driver (cache-protocol rule 2; stage once per series)")
    ap.add_argument("--task", required=True, help="task dir (e.g. tasks/pilot-realworld)")
    ap.add_argument("--config", default="C1",
                    help="warm-capable configuration id (default C1 = strong, warm-series)")
    ap.add_argument("--reps", type=int, default=3,
                    help="reps in the series: rep 1 cold, reps 2..n warm/resumed (default 3)")
    ap.add_argument("--manifest",
                    default=os.path.join(R.REPO_ROOT, "manifest", "delivery-manifest.yaml"))
    ap.add_argument("--phase", default="feasibility", help="results/<phase>/ for live runs")
    ap.add_argument("--session-id", default=None,
                    help="explicit series session UUID (minted if omitted); reused by all reps")
    ap.add_argument("--spend-cap-usd", type=float, default=60.0,
                    help="cumulative batch spend ceiling; checked before each rep (halts exit 3)")
    ap.add_argument("--dry-run", action="store_true",
                    help="synthetic subject tree + StubAdapter; no spend/clone/network")
    ap.add_argument("--out-root", default=None,
                    help="output root for --dry-run (default: a temp dir; never results/)")
    ap.add_argument("--stub-scenario", choices=("accept", "escalate", "reject"),
                    default="accept", help="dry-run gate outcome to simulate")
    args = ap.parse_args(argv)

    try:
        return run_series(
            task_arg=args.task, config=args.config, reps=args.reps,
            manifest_path=args.manifest, phase=args.phase, session_id=args.session_id,
            spend_cap_usd=args.spend_cap_usd, dry_run=args.dry_run,
            out_root=args.out_root, stub_scenario=args.stub_scenario,
        )
    except R.RunnerError as exc:
        print(f"warm-series: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
