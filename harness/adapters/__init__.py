"""Runner adapters (Phase 3). Real product adapters + a synthetic stub.

``REAL_ADAPTERS`` maps a config's ``adapter`` name to its class; ``--dry-run``
uses :class:`StubAdapter` instead (no spend, no network). Import the classes
lazily-free here — none of them spend at import time.
"""

from .agy import AgyAdapter
from .base import (
    Adapter,
    AttemptOutcome,
    AttemptSpec,
    ResolvedModel,
)
from .claude_code import ClaudeCodeAdapter
from .hybrid_c5 import HybridC5Adapter
from .stub import StubAdapter
from .transfer_r6 import TransferR6Adapter
from .transfer_r9 import TransferR9Adapter
from .transfer_r10 import TransferR10Adapter

REAL_ADAPTERS = {
    ClaudeCodeAdapter.name: ClaudeCodeAdapter,
    AgyAdapter.name: AgyAdapter,
    HybridC5Adapter.name: HybridC5Adapter,
    # Transplanted routing arms (transfer probe). Registered so a plan can name
    # them; a LIVE run still needs the schema's configuration_id enum widened and
    # a manifest policy pin, both of which are human decisions the driver refuses
    # to proceed without (harness/runner/transfer_probe.py).
    TransferR9Adapter.name: TransferR9Adapter,
    TransferR6Adapter.name: TransferR6Adapter,
    TransferR10Adapter.name: TransferR10Adapter,
}

__all__ = [
    "Adapter",
    "AttemptOutcome",
    "AttemptSpec",
    "ResolvedModel",
    "ClaudeCodeAdapter",
    "AgyAdapter",
    "HybridC5Adapter",
    "StubAdapter",
    "TransferR9Adapter",
    "TransferR6Adapter",
    "TransferR10Adapter",
    "REAL_ADAPTERS",
]
