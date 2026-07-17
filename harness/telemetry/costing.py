"""Cost derivation for run summaries (SPEC 2.7).

Turns token usage into USD under a declared ``cost_basis`` and two economic
views: **marginal operating** (additional observable cost incurred by the task)
and **fully allocated** (task cost under the declared seat/subscription/committed
allocation). No finding is economically robust unless it survives the relevant
cost-basis sensitivity (SPEC 2.7).

Non-negotiable rules honoured here (CLAUDE.md):
  * Never fabricate prices — prices are loaded from a pinned pricing snapshot
    that the caller supplies; this module ships none.
  * Unavailable != 0 — if any billed token class is unavailable, the derived
    cost is *unavailable*, not a partial sum that silently treats the missing
    class as zero.
  * A marginal API cost is never placed beside an allocated subscription cost
    without the basis declared — every returned view carries its cost_basis.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from .telemetry import tiered, unavailable

# The four *billed* token classes and their price keys. reasoning_tokens and
# tool_result_tokens are diagnostic / typically folded into these by providers,
# so they are excluded from the cost sum to avoid double-counting.
_BILLED_CLASSES: Tuple[Tuple[str, str], ...] = (
    ("input_tokens", "input"),
    ("cache_creation_tokens", "cache_write"),
    ("cache_read_tokens", "cache_read"),
    ("output_tokens", "output"),
)

_MTOK = 1_000_000


def load_prices(path: str) -> Dict[str, Any]:
    """Load a pinned pricing snapshot (``pricing/prices-<date>.json``)."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _rate_table(prices: Dict[str, Any], provider: str, model_id: str) -> Dict[str, float]:
    try:
        return prices["providers"][provider][model_id]
    except KeyError as exc:
        raise KeyError(
            f"no pricing for provider={provider!r} model={model_id!r} in snapshot"
        ) from exc


def token_cost_usd(
    usage: Dict[str, Any],
    provider: str,
    model_id: str,
    prices: Dict[str, Any],
) -> Dict[str, Any]:
    """Derive USD cost of one leg's token usage. Returns a tiered field.

    If any billed token class is missing/unavailable, the result is
    *unavailable* (with a reason listing the missing classes) — we never treat
    an unavailable class as zero. A ``components`` breakdown is attached when the
    cost is computable, for auditability.
    """
    rates = _rate_table(prices, provider, model_id)
    components: Dict[str, float] = {}
    missing: List[str] = []
    all_auth = True

    for usage_key, rate_key in _BILLED_CLASSES:
        field = usage.get(usage_key)
        if not isinstance(field, dict) or field.get("confidence") == "unavailable" \
                or field.get("value") is None:
            missing.append(usage_key)
            continue
        if field.get("confidence") != "authoritative":
            all_auth = False
        rate = rates.get(rate_key)
        if rate is None:
            missing.append(f"{usage_key}(no rate)")
            continue
        components[usage_key] = field["value"] * rate / _MTOK

    if missing:
        return unavailable(
            "cannot derive cost; unavailable/missing billed classes: " + ", ".join(missing)
        )

    total = round(sum(components.values()), 10)
    field = tiered(total, "derived")
    field["components"] = {k: round(v, 10) for k, v in components.items()}
    field["basis"] = "marginal_api_cost"
    return field


def _sum_costs(fields: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Sum several tiered cost fields. Any unavailable leg => unavailable total."""
    if any(f.get("confidence") == "unavailable" or f.get("value") is None for f in fields):
        return unavailable("one or more legs had unavailable cost; total not zero-filled")
    total = round(sum(f["value"] for f in fields), 10)
    return tiered(total, "derived")


def compute_cost_views(
    usage: Dict[str, Any],
    provider: str,
    model_id: str,
    prices: Dict[str, Any],
    cost_basis: str,
    *,
    seat_allocation_usd: Optional[float] = None,
    provider_reported_usd: Optional[float] = None,
    machine_cost_usd: Optional[float] = None,
) -> Dict[str, Any]:
    """Compute the two economic views for a single leg under a declared basis.

    Returns a dict with ``cost_basis``, ``token_cost_usd``,
    ``marginal_operating_usd`` and ``fully_allocated_usd`` (all tiered).

    Basis semantics:
      * ``marginal_api_cost`` — PAYG. marginal = token cost; fully allocated =
        token cost + machine cost (if supplied).
      * ``allocated_subscription_cost`` — licensed seat. There is no observable
        per-task marginal out-of-pocket, so marginal_operating is *unavailable*;
        fully_allocated uses the declared seat allocation (unavailable if none
        declared — never invented).
      * ``provider_reported_cost`` — trust a product-reported figure for both
        views (unavailable if not supplied).
      * ``cost_unavailable`` — both views unavailable.
    """
    if cost_basis not in ("marginal_api_cost", "allocated_subscription_cost",
                          "provider_reported_cost", "cost_unavailable"):
        raise ValueError(f"invalid cost_basis: {cost_basis!r}")

    machine = (
        tiered(machine_cost_usd, "derived")
        if machine_cost_usd is not None
        else unavailable("machine cost not measured")
    )

    if cost_basis == "marginal_api_cost":
        tc = token_cost_usd(usage, provider, model_id, prices)
        marginal = tc
        if tc.get("confidence") == "unavailable":
            fully = unavailable("token cost unavailable; fully-allocated not zero-filled")
        elif machine_cost_usd is not None:
            fully = tiered(round(tc["value"] + machine_cost_usd, 10), "derived")
        else:
            fully = tiered(tc["value"], "derived")
        return {
            "cost_basis": cost_basis,
            "token_cost_usd": tc,
            "marginal_operating_usd": marginal,
            "fully_allocated_usd": fully,
            "machine_cost_usd": machine,
        }

    if cost_basis == "allocated_subscription_cost":
        # Token cost is still derivable for diagnostics, but under a seat basis
        # it is NOT the marginal out-of-pocket cost.
        tc = token_cost_usd(usage, provider, model_id, prices)
        marginal = unavailable(
            "licensed seat: no observable per-task marginal cost (SPEC 2.7 subscription rule)"
        )
        if seat_allocation_usd is not None:
            fully = tiered(round(seat_allocation_usd, 10), "derived")
            fully["basis"] = "allocated_subscription_cost"
        else:
            fully = unavailable("seat allocation not declared; not estimated")
        return {
            "cost_basis": cost_basis,
            "token_cost_usd": tc,
            "marginal_operating_usd": marginal,
            "fully_allocated_usd": fully,
            "machine_cost_usd": machine,
        }

    if cost_basis == "provider_reported_cost":
        if provider_reported_usd is None:
            rep: Dict[str, Any] = unavailable("provider did not expose a cost figure")
        else:
            rep = tiered(round(provider_reported_usd, 10), "proxy_observed")
        return {
            "cost_basis": cost_basis,
            "token_cost_usd": unavailable("provider-reported basis; token breakdown not used"),
            "marginal_operating_usd": rep,
            "fully_allocated_usd": rep,
            "machine_cost_usd": machine,
        }

    # cost_unavailable
    return {
        "cost_basis": cost_basis,
        "token_cost_usd": unavailable("cost basis is cost_unavailable"),
        "marginal_operating_usd": unavailable("cost basis is cost_unavailable"),
        "fully_allocated_usd": unavailable("cost basis is cost_unavailable"),
        "machine_cost_usd": machine,
    }


def cost_for_legs(
    legs: List[Dict[str, Any]],
    prices: Dict[str, Any],
    *,
    leg_options: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Aggregate cost across billing legs (dual-bill C5).

    Each leg must carry ``leg_id``, ``provider.value``, ``model_or_selector.value``,
    ``cost_basis`` and ``usage``. ``leg_options`` maps ``leg_id`` -> kwargs for
    :func:`compute_cost_views` (seat_allocation_usd, provider_reported_usd,
    machine_cost_usd). Returns per-leg views plus summed
    marginal_operating/fully_allocated across legs (unavailable if any leg is
    unavailable — never zero-filled).
    """
    leg_options = leg_options or {}
    per_leg: List[Dict[str, Any]] = []
    for leg in legs:
        leg_id = leg.get("leg_id", "?")
        provider = _unwrap(leg.get("provider"))
        model_id = _unwrap(leg.get("model_or_selector"))
        basis = leg.get("cost_basis", "cost_unavailable")
        opts = leg_options.get(leg_id, {})
        views = compute_cost_views(
            leg.get("usage", {}), provider, model_id, prices, basis, **opts
        )
        views["leg_id"] = leg_id
        per_leg.append(views)

    total_marginal = _sum_costs([v["marginal_operating_usd"] for v in per_leg])
    total_fully = _sum_costs([v["fully_allocated_usd"] for v in per_leg])
    return {
        "legs": per_leg,
        "marginal_operating_usd": total_marginal,
        "fully_allocated_usd": total_fully,
    }


def _unwrap(field: Any) -> Any:
    """Return .value from a tiered field, or the field itself if plain."""
    if isinstance(field, dict) and "value" in field:
        return field["value"]
    return field
