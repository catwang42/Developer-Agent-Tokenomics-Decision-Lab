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

REAL_ADAPTERS = {
    ClaudeCodeAdapter.name: ClaudeCodeAdapter,
    AgyAdapter.name: AgyAdapter,
    HybridC5Adapter.name: HybridC5Adapter,
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
    "REAL_ADAPTERS",
]
