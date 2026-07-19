"""Non-comparative aggregation view over per-run result records.

Scans a results directory, loads each run's compact ``result.json`` (falling back to
the canonical ``summary.json``), and produces a descriptive per-cell
(task × configuration) view. INTERNAL, NON-COMPARATIVE only: it never ranks products
or configurations against each other and emits no vendor claim (CLAUDE.md rule 4;
feasibility-protocol: outputs stay non-comparative). Unavailable costs are counted,
never zero-imputed (CLAUDE.md rule 3).
"""

from .aggregate import aggregate, load_records

__all__ = ["aggregate", "load_records"]
