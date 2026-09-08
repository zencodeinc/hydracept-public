"""Observed dollars on a receipt — provider spend vs Hydracept wallet charge.

Public client copy of hydracept_contracts.receipt_cost. The published hydracept
package does not depend on hydracept_contracts.
"""

from __future__ import annotations

from typing import Any

_MICROS_PER_USD = 1_000_000


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _money_micros(blob: Any) -> int | None:
    if not isinstance(blob, dict):
        return None
    return _as_int(blob.get("amountMicros", blob.get("amount_micros")))


def _pricing_blob(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    pricing = payload.get("pricing")
    if isinstance(pricing, dict):
        return pricing
    return payload


def customer_charge_micros(payload: dict[str, Any] | None) -> int | None:
    pricing = _pricing_blob(payload)
    charge = pricing.get("charge")
    nested = charge.get("customerCharge") if isinstance(charge, dict) else None
    micros = _money_micros(nested)
    if micros is not None:
        return micros
    return _money_micros(pricing.get("customerCharge"))


def provider_cost_micros(payload: dict[str, Any] | None) -> int | None:
    """Catalog-priced provider dollars. Independent of Hydracept wallet charge."""
    if not isinstance(payload, dict):
        return None
    pricing = _pricing_blob(payload)
    usage = pricing.get("providerUsage") or pricing.get("provider_usage")
    if isinstance(usage, dict):
        micros = _money_micros(usage.get("reportedCost") or usage.get("reported_cost"))
        if micros is not None:
            return micros
    for key in (
        "providerReportedCostMicros",
        "provider_reported_cost_micros",
        "providerBasisCostMicros",
        "provider_basis_cost_micros",
    ):
        micros = _as_int(pricing.get(key))
        if micros is not None:
            return micros
        micros = _as_int(payload.get(key))
        if micros is not None:
            return micros
    return None


def surfaced_cost_micros(payload: dict[str, Any] | None) -> int | None:
    """Wallet charge when Hydracept billed; otherwise observed provider spend.

    Does not fall back to quote/estimatedCharge.
    """
    charged = customer_charge_micros(payload)
    if charged is not None:
        return charged
    return provider_cost_micros(payload)


def micros_to_usd(micros: int | None) -> float | None:
    if micros is None:
        return None
    return micros / _MICROS_PER_USD
