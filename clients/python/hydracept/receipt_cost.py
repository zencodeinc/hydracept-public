"""Dollars on a receipt — the customer charge vs the provider price basis.

Public client copy of hydracept_contracts.receipt_cost. The published hydracept
package does not depend on hydracept_contracts, so the two copies must classify
the same input identically.

ADR-022 defines four money truths, and this module never conflates them:

``pricing.basisEstimated`` / ``estimatedCharge``
    Pre-execution upstream provider price basis and the managed customer charge
    derived from it (basis + Hydracept fee).
``pricing.basisActual`` / ``pricing.actualCharge``
    The sealed upstream provider price basis that the customer charge was
    computed from. This is the only customer-visible provider number.
``pricing.charge.customerCharge``
    The amount the customer owes, decomposed as upstream + Hydracept fee.
    It is $0 when Hydracept fully covers the execution.
``ProviderUsage.actual_cost``
    What Hydracept actually paid the provider. Private and admin-only; it must
    never be presented as a customer cost.

Hydracept has no retail, list, or catalog *price*: the provider price basis is
not a markup, and the managed margin is the spread between that basis and
Hydracept's own procurement cost.
"""

from __future__ import annotations

from typing import Any

_MICROS_PER_USD = 1_000_000

# Keys that have silently meant the customer charge, a retail amount, and
# provider spend across producers. Public consumer contracts never emit them.
_AMBIGUOUS_COST_KEYS = ("actualCost", "actual_cost")


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _usd_to_micros(value: Any) -> int | None:
    """Interpret a bare dollar amount as micros. ``None`` when not numeric."""
    number = _as_float(value)
    if number is None:
        return None
    return round(number * _MICROS_PER_USD)


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


def _total_micros(blob: Any) -> int | None:
    """Amount from either a projected ``amountMicros`` money or a ``CustomerCharge``."""
    if not isinstance(blob, dict):
        return None
    micros = _money_micros(blob)
    if micros is not None:
        return micros
    return _as_int(blob.get("customerTotalMicros", blob.get("customer_total_micros")))


def customer_charge_micros(payload: dict[str, Any] | None) -> int | None:
    """The amount owed, decomposed upstream + fee. ``None`` when not settled."""
    pricing = _pricing_blob(payload)
    charge = pricing.get("charge")
    nested = charge.get("customerCharge") if isinstance(charge, dict) else None
    micros = _total_micros(nested)
    if micros is not None:
        return micros
    return _total_micros(pricing.get("customerCharge"))


def customer_charge_breakdown(payload: dict[str, Any] | None) -> dict[str, int | None]:
    """Hydracept's own decomposition of the customer charge: basis + fee = total."""
    pricing = _pricing_blob(payload)
    charge = pricing.get("charge")
    blob = charge.get("customerCharge") if isinstance(charge, dict) else None
    if not isinstance(blob, dict):
        direct = pricing.get("customerCharge")
        blob = direct if isinstance(direct, dict) else {}
    return {
        "upstreamMicros": _as_int(blob.get("upstreamMicros") or blob.get("upstream_micros")),
        "hydraceptFeeMicros": _as_int(
            blob.get("hydraceptFeeMicros") or blob.get("hydracept_fee_micros")
        ),
        "customerTotalMicros": _as_int(
            blob.get("customerTotalMicros") or blob.get("customer_total_micros")
        ),
    }


def pricing_mode(payload: dict[str, Any] | None) -> str:
    return str(_pricing_blob(payload).get("mode") or "").strip().lower()


def canonical_charge_state(mode: str | None, customer_total_micros: int | None) -> str:
    """The single public charge vocabulary: charged | covered | provider_billed_directly | unavailable."""
    if str(mode or "").strip().lower() == "byok":
        return "provider_billed_directly"
    if customer_total_micros == 0:
        return "covered"
    if customer_total_micros is not None and customer_total_micros > 0:
        return "charged"
    return "unavailable"


def charge_state(payload: dict[str, Any] | None) -> str:
    """Canonical charge state for a consumer-facing receipt/pricing payload."""
    return canonical_charge_state(pricing_mode(payload), customer_charge_micros(payload))


def customer_financial_state(payload: dict[str, Any] | None) -> str | None:
    """Internal alias for :func:`charge_state`; single public vocabulary."""
    return charge_state(payload)


def provider_cost_micros(payload: dict[str, Any] | None) -> int | None:
    """The customer-facing upstream provider price basis — never procurement cost.

    ADR-022: ``ProviderPriceSnapshot`` is the only customer-visible provider
    number. ``ProviderUsage.actual_cost`` is what Hydracept actually paid and is
    admin-only, so it is not a fallback here.
    """
    if not isinstance(payload, dict):
        return None
    pricing = _pricing_blob(payload)
    micros = _money_micros(pricing.get("basisActual") or pricing.get("basis_actual"))
    if micros is not None:
        return micros
    micros = _money_micros(pricing.get("actualCharge") or pricing.get("actual_charge"))
    if micros is not None:
        return micros
    # `project_public_settlement` mirrors the sealed basis into `price`; it is a
    # basis, never a retail price.
    micros = _money_micros(pricing.get("price"))
    if micros is not None:
        return micros
    for blob in (pricing.get("providerUsage"), pricing.get("provider_usage")):
        if not isinstance(blob, dict):
            continue
        micros = _money_micros(blob.get("reportedCost") or blob.get("reported_cost"))
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


def estimated_provider_cost_micros(payload: dict[str, Any] | None) -> int | None:
    """Pre-execution upstream provider price basis (``pricing.basisEstimated``)."""
    pricing = _pricing_blob(payload)
    micros = _money_micros(pricing.get("basisEstimated") or pricing.get("basis_estimated"))
    if micros is not None:
        return micros
    for key in ("estimatedProviderPriceBasisMicros", "estimated_provider_price_basis_micros"):
        micros = _as_int(pricing.get(key))
        if micros is not None:
            return micros
        if isinstance(payload, dict):
            micros = _as_int(payload.get(key))
            if micros is not None:
                return micros
    return None


def estimated_customer_charge_micros(payload: dict[str, Any] | None) -> int | None:
    """Pre-execution managed customer charge: provider basis + Hydracept fee."""
    pricing = _pricing_blob(payload)
    micros = _money_micros(pricing.get("estimatedCharge") or pricing.get("estimated_charge"))
    if micros is not None:
        return micros
    quote = pricing.get("quote")
    if isinstance(quote, dict):
        micros = _money_micros(quote.get("customerTotal") or quote.get("customer_total"))
        if micros is not None:
            return micros
    return _money_micros(
        pricing.get("maximumAuthorizedCharge") or pricing.get("maximum_authorized_charge")
    )


def surfaced_cost_micros(payload: dict[str, Any] | None) -> int | None:
    """Wallet charge when Hydracept billed; otherwise the provider price basis.

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


_LEGACY_COST_NOTE = (
    "Legacy ambiguous cost fields, removed from the public contract. "
    "customerChargeUsd is what this customer was charged (0 when Hydracept covers it); "
    "providerCostUsd is the upstream provider price basis the charge was computed from; "
    "estimatedCustomerChargeUsd is a quote. Do not treat legacyActualCostUsd as the "
    "customer charge, and never present providerProcurementCostUsd to a customer — it is "
    "Hydracept's private cost (ADR-022)."
)


def _strip_ambiguous_costs(blob: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Drop bare ``actualCost``/``actual_cost``; return (cleaned, removed values).

    A numeric value is preserved under the single unambiguous name
    ``legacyActualCostUsd`` so nothing is silently discarded.
    """
    cleaned = dict(blob)
    removed: dict[str, Any] = {}
    for key in _AMBIGUOUS_COST_KEYS:
        if key not in cleaned:
            continue
        value = cleaned.pop(key)
        amount = _as_float(value)
        if amount is None:
            removed[key] = value
        else:
            removed.setdefault("legacyActualCostUsd", amount)
    return cleaned, removed


def _strip_internal_procurement(
    pricing: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Remove Hydracept's private procurement cost from a customer-facing view.

    ``ProviderUsage.actual_cost`` is what Hydracept paid, not what the customer
    pays. It is never promoted into a customer cost field; a numeric value is
    retained only under an explicitly labelled private key so the data is not
    lost from the payload while remaining unusable as a customer price.
    """
    internal: dict[str, Any] = {}
    for container in ("providerUsage", "provider_usage"):
        usage = pricing.get(container)
        if not isinstance(usage, dict):
            continue
        normalized = dict(usage)
        for key in _AMBIGUOUS_COST_KEYS:
            if key not in normalized:
                continue
            value = normalized.pop(key)
            amount = _usd_to_micros(value)
            if amount is None:
                normalized[key] = value
            else:
                internal["providerProcurementCostUsd"] = micros_to_usd(amount)
        pricing[container] = normalized
    return pricing, internal


def retail_charge_micros(payload: dict[str, Any] | None) -> int | None:
    """Managed-equivalent amount (actual charge or sealed price), not the amount owed."""
    pricing = _pricing_blob(payload)
    for key in ("actualCharge", "actual_charge", "price"):
        micros = _money_micros(pricing.get(key))
        if micros is not None:
            return micros
    return None


def service_fee_bps(payload: dict[str, Any] | None) -> int | None:
    """Sealed service-fee rate in basis points, when the payload exposes one."""
    if not isinstance(payload, dict):
        return None
    pricing = _pricing_blob(payload)
    for blob in (pricing, payload):
        if not isinstance(blob, dict):
            continue
        policy = blob.get("policy")
        if isinstance(policy, dict):
            bps = _as_int(policy.get("serviceFeeBps", policy.get("service_fee_bps")))
            if bps is not None:
                return bps
        hydracept = blob.get("hydracept")
        if isinstance(hydracept, dict):
            bps = _as_int(
                hydracept.get("serviceFeeRateBps", hydracept.get("service_fee_rate_bps"))
            )
            if bps is not None:
                return bps
    return None


def estimated_provider_price_basis_micros(payload: dict[str, Any] | None) -> int | None:
    """Sealed estimated provider price basis, when the payload exposes one."""
    if not isinstance(payload, dict):
        return None
    pricing = _pricing_blob(payload)
    for key in (
        "estimatedProviderPriceBasisMicros",
        "estimated_provider_price_basis_micros",
    ):
        micros = _as_int(pricing.get(key))
        if micros is not None:
            return micros
        micros = _as_int(payload.get(key))
        if micros is not None:
            return micros
    return None


def present_receipt(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Presentation-only receipt view.

    The customer charge leads. The provider price basis is labeled as a basis,
    never as a retail or list price, and Hydracept's procurement cost is kept out
    of the customer fields entirely.
    """
    receipt = dict(payload or {})
    pricing = dict(_pricing_blob(receipt))
    customer = customer_charge_micros(receipt)
    basis = provider_cost_micros(receipt)
    estimated_basis = estimated_provider_cost_micros(receipt)
    estimated_charge = estimated_customer_charge_micros(receipt)
    breakdown = customer_charge_breakdown(receipt)
    settled = customer is not None or basis is not None
    legacy: dict[str, Any] = {}
    if settled:
        for key in ("estimatedCost", "estimated_cost"):
            pricing.pop(key, None)
            receipt.pop(key, None)
    receipt, receipt_legacy = _strip_ambiguous_costs(receipt)
    legacy.update(receipt_legacy)
    if pricing:
        pricing, pricing_legacy = _strip_ambiguous_costs(pricing)
        legacy.update(pricing_legacy)
        pricing, internal_legacy = _strip_internal_procurement(pricing)
        legacy.update(internal_legacy)
        receipt["pricing"] = pricing
    owed = micros_to_usd(customer)
    state = charge_state(payload)
    equivalent = micros_to_usd(retail_charge_micros(receipt))
    presented = {
        "customerChargeUsd": owed,
        "customerOwedUsd": owed,
        "customerCharge": (
            {
                "customerTotalMicros": customer,
                "amountMicros": customer,
                "upstreamMicros": breakdown["upstreamMicros"],
                "hydraceptFeeMicros": breakdown["hydraceptFeeMicros"],
                "currency": "USD",
                "state": state,
            }
            if customer is not None
            else None
        ),
        "chargeState": state,
        "billingMode": pricing_mode(receipt) or None,
        "managedEquivalentChargeUsd": equivalent,
        "providerCostUsd": micros_to_usd(basis),
        "providerCostBasis": "upstream-price-basis",
        "estimatedProviderCostUsd": micros_to_usd(estimated_basis),
        "estimatedCustomerChargeUsd": micros_to_usd(estimated_charge),
        "receipt": receipt,
    }
    if legacy:
        presented["legacyCostAliases"] = {**legacy, "note": _LEGACY_COST_NOTE}
    return presented


def present_job(job: dict[str, Any] | None, receipt: dict[str, Any] | None = None) -> dict[str, Any]:
    """CLI/MCP job view that leads with customerChargeUsd instead of a bare actualCost."""
    payload = dict(job or {})
    source = receipt if isinstance(receipt, dict) else payload
    presented = present_receipt(source)
    state = presented.get("chargeState")
    charge = presented.get("customerCharge")
    customer_owed = presented.get("customerChargeUsd")
    basis_usd = presented.get("providerCostUsd")
    estimated_charge_usd = presented.get("estimatedCustomerChargeUsd")
    estimated_basis_usd = presented.get("estimatedProviderCostUsd")
    diagnostics: dict[str, Any] = {}
    for key in ("actualCost", "actual_cost", "estimatedCost", "estimated_cost"):
        if key in payload:
            diagnostics[key] = payload.pop(key)
    diagnostics, legacy = _strip_ambiguous_costs(diagnostics)
    renamed = {**diagnostics, **legacy}
    payload["customerChargeUsd"] = customer_owed
    payload["customerOwedUsd"] = customer_owed
    payload["customerCharge"] = charge
    payload["chargeState"] = state
    payload["billingMode"] = presented.get("billingMode")
    payload["providerCostUsd"] = basis_usd
    payload["providerCostBasis"] = "upstream-price-basis"
    payload["estimatedProviderCostUsd"] = estimated_basis_usd
    payload["estimatedCustomerChargeUsd"] = estimated_charge_usd
    payload["pricing"] = {
        "customerCharge": charge,
        "customerChargeUsd": customer_owed,
        "customerOwedUsd": customer_owed,
        "chargeState": state,
        "billingMode": presented.get("billingMode"),
        "providerCostUsd": basis_usd,
        "providerCostBasis": "upstream-price-basis",
        "estimatedProviderCostUsd": estimated_basis_usd,
        "estimatedCustomerChargeUsd": estimated_charge_usd,
        "status": state,
        "summary": _pricing_summary(customer_owed, state, estimated_charge_usd),
    }
    if renamed:
        renamed["note"] = (
            _LEGACY_COST_NOTE
            if "legacyActualCostUsd" in renamed
            else "Diagnostic accounting fields only. customerChargeUsd is what this customer was charged."
        )
        payload["pricingDiagnostics"] = renamed
    if isinstance(receipt, dict):
        payload["receipt"] = present_receipt(receipt)
    return payload


def format_pricing_summary(
    customer_owed: float | None,
    state: str | None,
    estimated_charge_usd: float | None = None,
) -> str:
    """One-line customer-facing charge summary for CLI/MCP completion."""
    if state == "provider_billed_directly":
        return (
            "Hydracept charge: US$0.00. "
            "Provider usage is billed directly to your provider account."
        )
    if state == "covered" or customer_owed == 0.0:
        managed = (
            f" Managed equivalent: US${estimated_charge_usd:.2f}."
            if estimated_charge_usd is not None
            else ""
        )
        return f"Customer charged: US$0.00. Status: Covered by Hydracept.{managed}"
    if customer_owed is None:
        if estimated_charge_usd is not None:
            return (
                "Customer charge not settled. "
                f"Estimated managed charge: US${estimated_charge_usd:.2f}."
            )
        return "Customer charge unavailable on this payload."
    return f"Customer charged: US${customer_owed:.2f}."


def _pricing_summary(
    customer_owed: float | None,
    state: str | None,
    estimated_charge_usd: float | None = None,
) -> str:
    return format_pricing_summary(customer_owed, state, estimated_charge_usd)


def present_quote(quote: dict[str, Any] | None) -> dict[str, Any]:
    """Label the quote so spending=none is not read as a $0 charge."""
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
    covered = spending in {"none", "internal", "covered"}
    billing_mode = str(
        payload.get("billingMode") or payload.get("mode") or ""
    ).strip().lower() or None
    if billing_mode == "byok":
        expectation = "provider_billed_directly"
    elif covered:
        expectation = "covered"
    else:
        expectation = "charged"
    payload.setdefault("billingMode", billing_mode)
    payload.setdefault("chargeExpectation", expectation)
    payload.setdefault("chargeState", "unavailable")
    if covered:
        payload.setdefault(
            "customerChargeNote",
            "spending=none/covered means this customer will not be billed. "
            "The estimated charge is the managed equivalent (provider cost + 6%), not a debit.",
        )
    elif billing_mode == "byok":
        payload.setdefault(
            "customerChargeNote",
            "BYOK: Hydracept fee is 0%. Provider usage is billed directly to your provider account.",
        )
    elif "customerChargeNote" not in payload:
        payload["customerChargeNote"] = (
            "Estimated customer charge is provider cost + 6%. "
            "The customer debit is customerChargeUsd after the job, which may be US$0.00 when Hydracept covers execution."
        )
    return payload
