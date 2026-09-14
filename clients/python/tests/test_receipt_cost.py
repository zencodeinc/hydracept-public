"""Client receipt cost helper mirrors the contract helper for published packages."""

from hydracept.mcp.server import _receipt_summary
from hydracept.receipt_cost import format_pricing_summary, provider_cost_micros, surfaced_cost_micros


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
    assert summary["customerOwedUsd"] is None
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
    assert summary["customerOwedUsd"] == 0.044
    assert summary["costUsd"] == 0.044
    assert summary["customerChargeUsd"] == 0.044
    assert summary["customerCharge"]["customerTotalMicros"] == 44_000
    assert summary["providerCostUsd"] == 0.04


def test_receipt_summary_covered_zero_charge_does_not_use_provider_cost() -> None:
    summary = _receipt_summary(
        {
            "receiptId": "rcpt_internal",
            "jobId": "job_internal",
            "pricing": {
                "mode": "managed",
                "fundingSource": "internal",
                "price": {"amountMicros": 50_000, "currency": "USD"},
                "charge": {"customerCharge": {"amountMicros": 0, "currency": "USD"}},
                "providerUsage": {
                    "reportedCost": {"amountMicros": 40_000, "currency": "USD"},
                    "costBearer": "hydracept",
                },
            },
        }
    )
    assert summary["customerOwedUsd"] == 0.0
    assert summary["retailUsd"] == 0.05
    assert summary["customerChargeUsd"] == 0.0
    assert summary["customerCharge"]["customerTotalMicros"] == 0
    assert summary["costUsd"] == 0.0
    assert summary["providerCostUsd"] == 0.04


def test_present_receipt_leads_with_customer_owed_and_labels_retail() -> None:
    from hydracept.receipt_cost import present_receipt

    presented = present_receipt(
        {
            "receiptId": "rcpt_internal",
            "estimatedCost": 0.12,
            "pricing": {
                "estimatedCost": 0.12,
                "price": {"amountMicros": 50_000, "currency": "USD"},
                "actualCharge": {"amountMicros": 50_000, "currency": "USD"},
                "charge": {"customerCharge": {"amountMicros": 0, "currency": "USD"}},
            },
        }
    )
    assert list(presented.keys())[0] == "customerOwedUsd"
    assert presented["customerOwedUsd"] == 0.0
    assert presented["retailUsd"] == 0.05
    assert presented["customerCharge"]["customerTotalMicros"] == 0
    assert presented["customerCharge"]["state"] == "covered"
    assert "estimatedCost" not in presented["receipt"]
    assert "estimatedCost" not in (presented["receipt"].get("pricing") or {})
    assert "actualCharge" not in (presented["receipt"].get("pricing") or {})
    assert presented["receipt"]["pricing"]["retailCharge"]["amountMicros"] == 50_000


def test_present_job_leads_with_customer_charge_not_actual_cost() -> None:
    from hydracept.receipt_cost import present_job

    presented = present_job(
        {"id": "wfr_1", "actualCost": 0.05, "status": "succeeded"},
        {
            "pricing": {
                "charge": {"customerCharge": {"amountMicros": 0, "currency": "USD"}},
                "price": {"amountMicros": 50_000, "currency": "USD"},
            }
        },
    )
    assert presented["pricingDiagnostics"]["actualCost"] == 0.05
    assert presented["customerOwedUsd"] == 0.0
    assert presented["customerCharge"]["customerTotalMicros"] == 0
    assert "Covered by Hydracept" in presented["pricing"]["summary"]
    assert "actualCost" not in presented


def test_format_pricing_summary_covered_vs_customer_funded() -> None:
    covered = format_pricing_summary(0.0, "covered", 0.05)
    assert "US$0.00" in covered
    assert "Covered by Hydracept" in covered
    assert "Retail price: US$0.05" in covered
    funded = format_pricing_summary(0.12, "customer_funded", 0.05)
    assert funded == "Customer charged: US$0.12."


def test_present_quote_explains_spending_none() -> None:
    from hydracept.receipt_cost import present_quote

    presented = present_quote({"spending": "none", "expectedCharge": 0.05})
    assert "will not be billed" in presented["customerChargeNote"]
