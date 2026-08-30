"""Client for the source's capture harness, from this lab's 3.10 harness.

The whole module is a transport. It owns no rule: it hands a candidate program
to ``harness/vendor/sj_capture.py`` (which runs under the pinned >= 3.11
interpreter, because ``ctx-harness`` requires one and this harness does not have
one) and hands back what that process captured. Every routing decision made from
the result is made by ``transfer_spec.classify_from_evidence_graph`` against the
level rules the frozen spec declares.

Why a subprocess and not an import: see ``harness/vendor/sj_capture.py``. Why a
vendored wrapper and not a direct ``ctx`` call: see ``harness/vendor/NOTICE.md``.

Which arms use it: only those whose spec declares
``evidence.calibration.capture_harness``. r6 and r10 do not, and their
calibration path is unchanged — their committed reports stay comparable.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Optional

VENDOR_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vendor",
)
CAPTURE_SCRIPT = os.path.join(VENDOR_DIR, "sj_capture.py")

#: Overrides the interpreter the spec records. The spec's value is a path on
#: the machine the calibration ran on; a second machine sets this rather than
#: editing a frozen spec to say where its own venv lives.
INTERPRETER_ENV = "LAB_CTX_PYTHON"


class CaptureError(RuntimeError):
    """The capture harness could not run, or ran and refused.

    Never caught and turned into an empty digest. A calibration row whose
    evidence came from a harness that did not run is the exact failure mode the
    source's own ``require()`` exists to prevent.
    """


@dataclass(frozen=True)
class ContainedCapture:
    """One execution captured through the source's ``ContainedRun`` flow."""

    exit_code: Optional[int]
    timed_out: bool
    #: ``ContainedRun.digest`` — the bounded, profile-detected, model-visible
    #: payload. Not summarised here, not filtered here.
    digest: str
    #: ``ContainedRun.native_payload()`` — what an *uncontained* arm would have
    #: sent for this same failure. Kept so a routing decision can be read
    #: against the raw text it was made from.
    native_payload: str
    #: The typed evidence graph as plain JSON, or ``None`` for no fact tier.
    #: ``None`` is a fact: nothing recognised the output as a test run.
    graph: Optional[Dict[str, Any]]
    metrics: Dict[str, Any]
    handle: str
    profile: str
    backend: str

    @property
    def passed(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    @property
    def typed(self) -> bool:
        return self.graph is not None


def capture_config(spec: Any) -> Optional[Dict[str, Any]]:
    """``evidence.calibration.capture_harness`` from a spec, or ``None``."""
    cal = ((spec.doc.get("evidence") or {}).get("calibration") or {})
    cfg = cal.get("capture_harness")
    return dict(cfg) if isinstance(cfg, dict) else None


def interpreter(config: Dict[str, Any]) -> str:
    """The interpreter the capture runs under. Env override wins."""
    return os.path.expanduser(
        os.environ.get(INTERPRETER_ENV) or str(config.get("interpreter") or ""))


def preflight(config: Dict[str, Any]) -> Dict[str, Any]:
    """Prove the harness is installed and importable before anything is spent.

    Returns ``sj.status()`` from the capture process. Raises rather than
    degrading: an evidence gate reading a fallback is r6 wearing r9's label, and
    discovering that after a live slice has been billed is discovering it too
    late.
    """
    python = interpreter(config)
    if not python or not os.path.exists(python):
        raise CaptureError(
            f"capture interpreter {python or '<unset>'!r} does not exist; set "
            f"${INTERPRETER_ENV} to a Python >= 3.11 with ctx-harness installed")
    probe = subprocess.run(
        [python, "-c",
         "import json,ctx;"
         "from ctx.digest import detect_profile;"
         "from ctx.digest.base import DigestContext;"
         "print(json.dumps({'ctx_version': ctx.__version__}))"],
        capture_output=True, text=True, timeout=120)
    if probe.returncode != 0:
        raise CaptureError(
            f"ctx is not importable under {python}: "
            f"{(probe.stderr or probe.stdout).strip()[-500:]}")
    installed = json.loads(probe.stdout.strip().splitlines()[-1])
    want = str(config.get("package_version") or "")
    if want and installed.get("ctx_version") != want:
        raise CaptureError(
            f"spec pins ctx-harness {want}, interpreter has "
            f"{installed.get('ctx_version')}")
    return installed


def run_contained(program: str, *, config: Dict[str, Any], grading_python: str,
                  timeout_s: float) -> ContainedCapture:
    """Execute ``program`` under the source's harness and return its capture.

    ``grading_python`` is the interpreter the *candidate* runs under, and it is
    deliberately not the one the harness runs under: the BigCodeBench tasks need
    this lab's scientific stack, which lives in the 3.10 environment. Only the
    capture moved interpreters, not the oracle.
    """
    python = interpreter(config)
    fd, out_path = tempfile.mkstemp(prefix="sj_capture_", suffix=".json")
    os.close(fd)
    try:
        request = json.dumps({
            "program": program,
            "grading_python": grading_python,
            "timeout_s": timeout_s,
            "out_path": out_path,
        })
        # The child's own timeout is `timeout_s`; this one only bounds the
        # capture machinery around it, so a hung store cannot hang the slice.
        proc = subprocess.run([python, CAPTURE_SCRIPT], input=request,
                              capture_output=True, text=True,
                              timeout=timeout_s + 120)
        try:
            with open(out_path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, ValueError) as exc:
            raise CaptureError(
                f"capture process wrote no readable result ({exc}); "
                f"rc={proc.returncode} stderr={proc.stderr.strip()[-500:]}"
            ) from exc
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass

    if not payload.get("ok"):
        raise CaptureError(str(payload.get("error") or "capture failed"))
    return ContainedCapture(
        exit_code=payload.get("exit_code"),
        timed_out=bool(payload.get("timed_out")),
        digest=str(payload.get("digest") or ""),
        native_payload=str(payload.get("native_payload") or ""),
        graph=payload.get("graph"),
        metrics=dict(payload.get("metrics") or {}),
        handle=str(payload.get("handle") or ""),
        profile=str(payload.get("profile") or ""),
        backend=str(payload.get("backend") or ""),
    )
