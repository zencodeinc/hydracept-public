"""Observed dollars on a receipt — provider spend vs amount the customer owes.

Public client copy of hydracept_contracts.receipt_cost. The published hydracept
package does not depend on hydracept_contracts.

``pricing.charge.customerCharge`` is the amount owed for this execution.
It is $0 when Hydracept fully covers the job. Retail price is ``pricing.price``.
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
    direct = pricing.get("customerCharge")
    micros = _money_micros(direct)
    if micros is not None:
        return micros
    if isinstance(direct, dict):
        value = _as_int(direct.get("customerTotalMicros"))
        if value is not None:
            return value
    return None


def pricing_mode(payload: dict[str, Any] | None) -> str:
    return str(_pricing_blob(payload).get("mode") or "").strip().lower()


def customer_financial_state(payload: dict[str, Any] | None) -> str | None:
    """Covered / wallet / BYOK / unsettled from a consumer-facing payload."""
    mode = pricing_mode(payload)
    total = customer_charge_micros(payload)
    if mode == "byok" and total is None:
        return "byok"
    if total == 0:
        return "covered"
    if total is not None and total > 0:
        return "customer_funded"
    if mode == "managed" and total is None:
        return "unsettled"
    return None


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


def retail_charge_micros(payload: dict[str, Any] | None) -> int | None:
    """Catalog/retail dollars (actualCharge or price), not the amount owed."""
    pricing = _pricing_blob(payload)
    for key in ("actualCharge", "actual_charge", "price"):
        micros = _money_micros(pricing.get(key))
        if micros is not None:
            return micros
    return None


def present_receipt(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Presentation-only receipt view. Customer owed leads; retail is labeled separately."""
    receipt = dict(payload or {})
    pricing = dict(_pricing_blob(receipt))
    customer = customer_charge_micros(receipt)
    retail = retail_charge_micros(receipt)
    settled = customer is not None or retail is not None
    if settled:
        pricing.pop("estimatedCost", None)
        pricing.pop("estimated_cost", None)
        receipt.pop("estimatedCost", None)
        receipt.pop("estimated_cost", None)
        retail_alias = pricing.pop("actualCharge", None)
        if retail_alias is None:
            retail_alias = pricing.pop("actual_charge", None)
        if retail_alias is not None:
            pricing["retailCharge"] = retail_alias
            pricing["retailChargeNote"] = "Retail/catalog amount; not the customer debit."
        if pricing:
            receipt["pricing"] = pricing
    owed = micros_to_usd(customer)
    return {
        "customerOwedUsd": owed,
        "customerCharge": (
            {
                "customerTotalMicros": customer,
                "amountMicros": customer,
                "currency": "USD",
                "state": customer_financial_state(payload),
            }
            if customer is not None
            else None
        ),
        "retailUsd": micros_to_usd(retail),
        "providerCostUsd": micros_to_usd(provider_cost_micros(receipt)),
        "receipt": receipt,
    }


def present_job(job: dict[str, Any] | None, receipt: dict[str, Any] | None = None) -> dict[str, Any]:
    """CLI/MCP job view that leads with customerCharge instead of actualCost."""
    payload = dict(job or {})
    source = receipt if isinstance(receipt, dict) else payload
    presented = present_receipt(source)
    state = None
    charge = presented.get("customerCharge")
    if isinstance(charge, dict):
        state = charge.get("state")
    retail_usd = presented.get("retailUsd")
    customer_owed = presented.get("customerOwedUsd")
    diagnostics: dict[str, Any] = {}
    for key in ("actualCost", "actual_cost", "estimatedCost", "estimated_cost"):
        if key in payload:
            diagnostics[key] = payload.pop(key)
    payload["customerOwedUsd"] = customer_owed
    payload["customerCharge"] = charge
    payload["pricing"] = {
        "customerCharge": charge,
        "customerOwedUsd": customer_owed,
        "retailUsd": retail_usd,
        "status": state,
        "summary": _pricing_summary(customer_owed, state, retail_usd),
    }
    if diagnostics:
        diagnostics["note"] = (
            "Diagnostic accounting fields only. customerOwedUsd/customerCharge is what this customer was charged."
        )
        payload["pricingDiagnostics"] = diagnostics
    if isinstance(receipt, dict):
        payload["receipt"] = present_receipt(receipt)
    return payload


def format_pricing_summary(
    customer_owed: float | None,
    state: str | None,
    retail_usd: float | None,
) -> str:
    """One-line customer-facing charge summary for CLI/MCP completion."""
    if customer_owed is None:
        return "Customer charge unavailable on this payload."
    if state == "covered" or customer_owed == 0.0:
        retail = f" Retail price: US${retail_usd:.2f}." if retail_usd is not None else ""
        return f"Customer charged: US$0.00. Status: Covered by Hydracept.{retail}"
    return f"Customer charged: US${customer_owed:.2f}."


def _pricing_summary(
    customer_owed: float | None,
    state: str | None,
    retail_usd: float | None,
) -> str:
    return format_pricing_summary(customer_owed, state, retail_usd)


def present_quote(quote: dict[str, Any] | None) -> dict[str, Any]:
    """Label retail quotes so spending=none is not read as a $0 catalog price."""
    payload = dict(quote or {})
    blobs: list[dict[str, Any]] = [payload]
    pricing = payload.get("pricing")
    if isinstance(pricing, dict):
        blobs.append(pricing)
    spending = ""
    for blob in blobs:
        for key in ("spending", "customerSpending", "chargeExpectation"):
            value = str(blob.get(key) or "").strip().lower()
            if value:
                spending = value
                break
        if spending:
            break
    if spending in {"none", "internal", "covered"}:
        payload.setdefault(
            "customerChargeNote",
            "spending=none/covered means this customer will not be billed. "
            "The listed retail or expected charge is catalog price, not a debit.",
        )
    elif "customerChargeNote" not in payload:
        payload["customerChargeNote"] = (
            "Retail/expected charge is catalog price. "
            "The customer debit is customerCharge after the job, which may be $0 when Hydracept covers execution."
        )
    return payload
