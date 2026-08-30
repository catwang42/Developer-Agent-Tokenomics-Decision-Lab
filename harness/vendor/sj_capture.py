"""Capture one candidate program through the source's own ContainedRun flow.

This file is the ONLY thing in this repository that talks to ``ctx``. It runs
inside a dedicated interpreter (see ``evidence.calibration.capture_harness`` in
``harness/policies/transfer/r9-spec.yaml``), not the one that runs the harness,
for a reason that is not stylistic: ``ctx-harness`` declares
``requires-python >= 3.11`` and this lab's harness runs on 3.10. Importing
``ctx`` from the harness process is therefore not possible, and forcing it would
mean either upgrading every other measurement path or patching a third-party
package until it imports — both of which change more than the evidence path.

So the split is: the harness process stays on 3.10 and owns the routing, the
grading rule and the bill; this process owns nothing but the capture, and hands
back the two facts the source's ``classify`` reads — the digest and the typed
evidence graph.

The flow reproduced here is ``evaluator._run_bigcodebench_contained`` at the
pinned source revision, including ``record_argv``, ``env_extra`` and the
sandbox lifecycle. Nothing is selected, summarised or re-derived: the digest is
whatever ``ContainedRun.digest`` returns and the facts are whatever
``ContainedRun.evidence_graph()`` typed. If this file ever starts making a
decision, the fidelity claim it exists to support is gone.

Stdlib plus the vendored ``straitjacket`` module only. Importing anything from
``harness`` here would drag a 3.10 codebase into a 3.12 interpreter for no
reason, and would give this process an opinion it is not supposed to have.

Protocol — a JSON request on stdin, a JSON response written to ``out_path``::

    {"program": str,          # the full candidate program, runner tail included
     "grading_python": str,   # interpreter the CHILD runs under (numpy et al.)
     "timeout_s": float,
     "out_path": str}

The response goes to a file rather than stdout because ``ctx`` and the
harness's own ``_warn_once`` both write diagnostics to the console, and a
protocol that has to be separated from log noise by parsing is a protocol that
will one day parse the noise.
"""

from __future__ import annotations

import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import straitjacket as sj  # noqa: E402  (vendored; path set immediately above)


def _graph_facts(run) -> dict | None:
    """The typed evidence graph as plain JSON, or ``None`` for no fact tier.

    ``None`` is a signal, not an absence to paper over: it means no profile
    recognised the output as a test run, and the source's ``classify`` treats
    it as untyped. Returning ``{}`` here instead would silently turn a degraded
    run into a clean one with zero failing identities.
    """
    graph = run.evidence_graph()
    if graph is None:
        return None
    return {
        "family": graph.family,
        "profile_version": graph.profile_version,
        "outcome": graph.outcome,
        "aggregate": dict(graph.aggregate or {}),
        "items": [
            {
                "id": item.id,
                "kind": item.kind,
                "severity": item.severity,
                "failure_class": item.failure_class or "",
                "location": item.location or "",
                "summary": item.summary or "",
            }
            for item in graph.items
        ],
        "coverage": dict(graph.coverage or {}),
        "parser_warnings": list(graph.parser_warnings or ()),
    }


def capture(req: dict) -> dict:
    """``evaluator._run_bigcodebench_contained``, with the facts serialised."""
    sandbox = sj.new_sandbox("bcb")
    try:
        (sandbox / "prog.py").write_text(req["program"], encoding="utf-8")
        run = sj.contained_run(
            [req["grading_python"], "prog.py"],
            cwd=sandbox,
            timeout=float(req.get("timeout_s", 120.0)),
            # The source's own argument: keep the host's absolute interpreter
            # path out of the manifest and out of the model-visible digest, so
            # the same failing program digests identically on another machine.
            record_argv=["python3", "prog.py"],
            env_extra=sj.CAPTURE_ENV,
        )
        return {
            "ok": True,
            "handle": run.handle,
            "profile": run.profile,
            "backend": run.backend,
            "exit_code": run.exit_code,
            "timed_out": bool(run.timed_out),
            "digest": run.digest,
            "native_payload": run.native_payload(),
            "graph": _graph_facts(run),
            "metrics": run.metrics(),
        }
    finally:
        sj.drop_sandbox(sandbox)


def main() -> int:
    req = json.load(sys.stdin)
    out_path = req["out_path"]
    try:
        # Refuse rather than fall back. The source's `require()` exists because
        # a row labelled as a straitjacket digest has to have been produced by
        # one; the same rule applies to a calibration whose whole claim is that
        # the evidence came from their flow.
        sj.require()
        payload = capture(req)
        payload["status"] = sj.status()
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed
        payload = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
