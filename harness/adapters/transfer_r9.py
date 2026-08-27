"""r9 — escalate-on-evidence. Behaviour lives in ``policies/transfer/r9-spec.yaml``.

The arm under test: a gate that READS the cheap model's failure evidence, types it
(shallow / local / broad / stalled / environment) and escalates to the frontier
only when the evidence says the failure is broad or stalled. It is the arm the
source study reports as its cost/pass winner, and the one the prereg predicts is
most exposed to a grader the evidence cannot see.
"""

from __future__ import annotations

from .transfer_base import TransferLadderAdapter


class TransferR9Adapter(TransferLadderAdapter):
    name = "transfer_r9"
    strategy_id = "r9"
