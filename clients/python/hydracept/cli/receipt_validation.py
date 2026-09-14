"""Public terminal-receipt pricing contract for CLI smoke.

Quote/admission → estimatedCharge / maximumAuthorizedCharge
Settled execution → actualCharge / price (retail)
Terminal managed success → pricing.charge.customerCharge (amount owed)

When Hydracept covers the execution, customerCharge is $0 even if retail price
is nonzero. actualCharge, top-level actualCost, and quote estimates are not
substitutes for owed charge. BYOK may omit customerCharge.
"""

from __future__ import annotations

from typing import Any

CUSTOMER_CHARGE_PATH = "pricing.charge.customerCharge"
GENERATION_SUCCEEDED_RECEIPT_INVALID = "generation_succeeded_receipt_invalid"


class ReceiptValidationError(ValueError):
    """Terminal receipt failed the public pricing contract."""

    def __init__(self, message: str, *, failing_path: str = CUSTOMER_CHARGE_PATH) -> None:
        super().__init__(message)
        self.failing_path = failing_path


def _pricing(receipt: dict[str, Any] | None) -> dict[str, Any]:
    if not receipt:
        return {}
    pricing = receipt.get("pricing")
    return pricing if isinstance(pricing, dict) else {}


def _pricing_mode(pricing: dict[str, Any]) -> str:
    nested = pricing.get("policy")
    policy_mode = ""
    if isinstance(nested, dict):
        policy_mode = str(nested.get("pricingMode") or "")
    return str(pricing.get("mode") or policy_mode).lower()


def _customer_charge(pricing: dict[str, Any]) -> dict[str, Any]:
    charge = pricing.get("charge")
    if not isinstance(charge, dict):
        return {}
    customer = charge.get("customerCharge")
    return customer if isinstance(customer, dict) else {}


def _money_present(blob: dict[str, Any]) -> bool:
    return blob.get("amountMicros") is not None or blob.get("amountMinor") is not None or blob.get("amount") is not None


def terminal_customer_charge(receipt: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the sealed customer charge without promoting estimates/actualCost aliases."""
    pricing = _pricing(receipt)
    if _pricing_mode(pricing) == "byok":
        return None
    customer = _customer_charge(pricing)
    return dict(customer) if _money_present(customer) else None


def validate_terminal_receipt_pricing(receipt: dict[str, Any] | None) -> None:
    """Raise ReceiptValidationError when a managed success receipt lacks sealed charge.

    Does not promote estimatedCharge, actualCharge, or actualCost into customerCharge.
    """
    if not receipt:
        raise ReceiptValidationError("missing receipt", failing_path="receipt")
    pricing = _pricing(receipt)
    if _pricing_mode(pricing) == "byok":
        return
    if terminal_customer_charge(receipt) is not None:
        return
    raise ReceiptValidationError(
        "Receipt missing pricing.charge.customerCharge",
        failing_path=CUSTOMER_CHARGE_PATH,
    )


def terminal_customer_charge_valid(receipt: dict[str, Any] | None) -> bool:
    try:
        validate_terminal_receipt_pricing(receipt)
        return True
    except ReceiptValidationError:
        return False