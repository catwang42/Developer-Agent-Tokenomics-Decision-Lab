"""r6 — opus-after-ladder. Behaviour lives in ``policies/transfer/r6-spec.yaml``.

The arm under test: a gate that COUNTS failures rather than reading them. The
cheap ladder runs to exhaustion and the frontier gets the fourth call regardless
of what the failures looked like. It is r9's control for "does reading the
evidence buy anything?".
"""

from __future__ import annotations

from .transfer_base import TransferLadderAdapter


class TransferR6Adapter(TransferLadderAdapter):
    name = "transfer_r6"
    strategy_id = "r6"
