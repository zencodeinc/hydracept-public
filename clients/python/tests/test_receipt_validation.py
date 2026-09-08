"""CLI terminal-receipt pricing contract."""

from __future__ import annotations

import pytest

from hydracept.cli.receipt_validation import (
    CUSTOMER_CHARGE_PATH,
    ReceiptValidationError,
    terminal_customer_charge_valid,
    validate_terminal_receipt_pricing,
)


def test_managed_receipt_requires_nested_customer_charge() -> None:
    validate_terminal_receipt_pricing(
        {
            "pricing": {
                "mode": "managed",
                "charge": {"customerCharge": {"amountMicros": 44_000, "currency": "USD"}},
            }
        }
    )


def test_byok_without_customer_charge_is_valid() -> None:
    validate_terminal_receipt_pricing({"pricing": {"mode": "byok"}})
    assert terminal_customer_charge_valid({"pricing": {"mode": "byok"}})


def test_actual_charge_is_not_a_customer_charge_substitute() -> None:
    with pytest.raises(ReceiptValidationError) as caught:
        validate_terminal_receipt_pricing(
            {
                "pricing": {
                    "mode": "managed",
                    "actualCharge": {"amountMicros": 44_000, "currency": "USD"},
                }
            }
        )
    assert caught.value.failing_path == CUSTOMER_CHARGE_PATH
    assert terminal_customer_charge_valid(
        {"pricing": {"actualCharge": {"amountMicros": 44_000}}}
    ) is False


def test_top_level_actual_cost_is_not_a_customer_charge_substitute() -> None:
    with pytest.raises(ReceiptValidationError):
        validate_terminal_receipt_pricing(
            {"actualCost": 0.044, "pricing": {"mode": "managed"}}
        )


def test_quote_estimate_must_not_populate_terminal_customer_charge() -> None:
    with pytest.raises(ReceiptValidationError) as caught:
        validate_terminal_receipt_pricing(
            {
                "pricing": {
                    "mode": "managed",
                    "estimatedCharge": {"amountMicros": 44_000, "currency": "USD"},
                    "maximumAuthorizedCharge": {"amountMicros": 44_000, "currency": "USD"},
                }
            }
        )
    assert caught.value.failing_path == CUSTOMER_CHARGE_PATH
    assert "estimatedCharge" not in str(caught.value)


def test_missing_receipt_fails() -> None:
    with pytest.raises(ReceiptValidationError) as caught:
        validate_terminal_receipt_pricing(None)
    assert caught.value.failing_path == "receipt"
