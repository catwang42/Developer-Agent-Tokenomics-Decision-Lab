"""r10 — opus-fresh-solve. Behaviour lives in ``policies/transfer/r10-spec.yaml``.

The arm under test: identical to r6 except for one spec key — the frontier turn
DISCARDS the cheap model's failed artefact and solves from scratch, carrying over
only the attempt count and the bounded digest. It is the control for "is the cheap
ladder's output worth handing to the frontier, or worth only having paid for?".
"""

from __future__ import annotations

from .transfer_base import TransferLadderAdapter


class TransferR10Adapter(TransferLadderAdapter):
    name = "transfer_r10"
    strategy_id = "r10"
