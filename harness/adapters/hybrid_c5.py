"""C5 integrated-workflow adapter — dual-bill conductor + executor (SPEC 2.1).

C5 is a *black-box integrated workflow*, NOT a controlled routing-policy experiment
(that is P1). A strong conductor (Product A) delegates to an economical executor
(Product B); BOTH legs are metered and reported, and the workflow total includes
failed delegations and verification. ``frontier_token_share`` (conductor share of
tokens) is computed by the runner as a diagnostic only — never a vendor claim.

This adapter is a per-leg dispatcher: it routes each attempt to the leg's own
product adapter (conductor -> ClaudeCodeAdapter, executor -> AgyAdapter) so both
legs are billed and telemetered independently and the runner's dual-bill costing
(``cost_for_legs``) aggregates them. Live execution inherits each sub-adapter's
``LAB_ALLOW_SPEND`` guard.
"""

from __future__ import annotations

from .agy import AgyAdapter
from .base import Adapter, AttemptOutcome, AttemptSpec, EmitFn
from .claude_code import ClaudeCodeAdapter


class HybridC5Adapter(Adapter):
    name = "hybrid_c5"

    def __init__(self) -> None:
        self._conductor = ClaudeCodeAdapter()
        self._executor = AgyAdapter()

    def run_attempt(self, spec: AttemptSpec, subject_dir: str, emit: EmitFn) -> AttemptOutcome:
        # Route by the leg's product surface: controlled_api legs go to the
        # Product A adapter; product_blackbox legs to the Product B wrapper.
        if spec.resolved.product_surface == "controlled_api":
            return self._conductor.run_attempt(spec, subject_dir, emit)
        return self._executor.run_attempt(spec, subject_dir, emit)
