"""Client receipt cost helper mirrors the contract helper for published packages."""

from hydracept.mcp.server import _receipt_summary
from hydracept.receipt_cost import provider_cost_micros, surfaced_cost_micros


def test_receipt_summary_byok_uses_provider_usage_not_quote() -> None:
    summary = _receipt_summary(
        {
            "receiptId": "rcpt_astra",
            "jobId": "job_astra",
            "pricing": {
                "mode": "byok",
                "quote": {"customerTotal": {"amountMicros": 1, "currency": "USD"}},
                "providerUsage": {
                    "reportedCost": {"amountMicros": 3_088_700, "currency": "USD"},
                    "costBearer": "customer",
                },
            },
        }
    )
    assert summary["costUsd"] == 3.0887
    assert summary["providerCostUsd"] == 3.0887
    assert summary["customerChargeUsd"] is None
    assert surfaced_cost_micros(summary) == provider_cost_micros(
        {
            "pricing": {
                "providerUsage": {
                    "reportedCost": {"amountMicros": 3_088_700, "currency": "USD"}
                }
            }
        }
    )


def test_receipt_summary_managed_keeps_wallet_charge_and_provider_cost() -> None:
    summary = _receipt_summary(
        {
            "receiptId": "rcpt_managed",
            "jobId": "job_managed",
            "pricing": {
                "mode": "managed",
                "charge": {"customerCharge": {"amountMicros": 44_000, "currency": "USD"}},
                "providerUsage": {
                    "reportedCost": {"amountMicros": 40_000, "currency": "USD"},
                    "costBearer": "hydracept",
                },
            },
        }
    )
    assert summary["costUsd"] == 0.044
    assert summary["customerChargeUsd"] == 0.044
    assert summary["providerCostUsd"] == 0.04
