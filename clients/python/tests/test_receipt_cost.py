"""Client receipt cost helper mirrors the contract helper for published packages.

Hydracept has no retail/list price (ADR-022). The customer-visible provider
number is the upstream price *basis*; Hydracept's own procurement cost is private.
"""

import json

import pytest

from hydracept.mcp.server import _receipt_summary
from hydracept.receipt_cost import (
    format_pricing_summary,
    present_job,
    present_receipt,
    provider_cost_micros,
    surfaced_cost_micros,
)


def test_receipt_summary_byok_uses_provider_basis_not_quote() -> None:
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
    assert summary["providerCostBasis"] == "upstream-price-basis"
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


def test_receipt_summary_managed_keeps_wallet_charge_and_provider_basis() -> None:
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
    assert summary["customerChargeUsd"] == 0.044
    assert summary["chargeState"] == "charged"
    assert summary["billingMode"] == "managed"
    assert summary["costUsd"] == 0.044
    assert summary["customerCharge"]["customerTotalMicros"] == 44_000
    assert summary["providerCostUsd"] == 0.04


def test_receipt_summary_covered_zero_charge_does_not_use_provider_basis() -> None:
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
    assert summary["customerChargeUsd"] == 0.0
    assert summary["chargeState"] == "covered"
    assert summary["customerCharge"]["customerTotalMicros"] == 0
    assert summary["costUsd"] == 0.0
    # The sealed basis (`price` after project_public_settlement) is the
    # customer-facing provider number and outranks provider-reported cost.
    assert summary["providerCostUsd"] == 0.05
    assert "retailUsd" not in summary


def test_present_receipt_leads_with_customer_charge_and_labels_the_basis() -> None:
    presented = present_receipt(
        {
            "receiptId": "rcpt_internal",
            "estimatedCost": 0.12,
            "pricing": {
                "estimatedCost": 0.12,
                "mode": "managed",
                "price": {"amountMicros": 50_000, "currency": "USD"},
                "actualCharge": {"amountMicros": 50_000, "currency": "USD"},
                "charge": {
                    "customerCharge": {
                        "upstreamMicros": 50_000,
                        "hydraceptFeeMicros": 3_000,
                        "customerTotalMicros": 0,
                    }
                },
            },
        }
    )
    assert list(presented.keys())[0] == "customerChargeUsd"
    assert presented["customerChargeUsd"] == 0.0
    assert presented["customerOwedUsd"] == 0.0
    assert presented["chargeState"] == "covered"
    assert presented["billingMode"] == "managed"
    assert presented["providerCostUsd"] == 0.05
    assert presented["providerCostBasis"] == "upstream-price-basis"
    assert presented["customerCharge"]["customerTotalMicros"] == 0
    assert presented["customerCharge"]["state"] == "covered"
    assert presented["customerCharge"]["hydraceptFeeMicros"] == 3_000
    assert "estimatedCost" not in presented["receipt"]
    assert "estimatedCost" not in (presented["receipt"].get("pricing") or {})
    # The sealed basis stays visible under its own name; it is not renamed "retail".
    assert presented["receipt"]["pricing"]["actualCharge"]["amountMicros"] == 50_000
    assert "retail" not in json.dumps(presented).lower()


def test_present_receipt_byok_zero_total_is_provider_billed_directly() -> None:
    from hydracept.receipt_cost import present_receipt

    presented = present_receipt(
        {
            "pricing": {
                "mode": "byok",
                "charge": {"customerCharge": {"amountMicros": 0, "currency": "USD"}},
            }
        }
    )
    assert presented["chargeState"] == "provider_billed_directly"
    assert presented["customerCharge"]["state"] == "provider_billed_directly"
    assert presented["customerOwedUsd"] == 0.0


def test_present_job_leads_with_customer_charge_not_actual_cost() -> None:
    presented = present_job(
        {"id": "wfr_1", "actualCost": 0.05, "status": "succeeded"},
        {
            "pricing": {
                "mode": "managed",
                "charge": {"customerCharge": {"amountMicros": 0, "currency": "USD"}},
                "price": {"amountMicros": 50_000, "currency": "USD"},
            }
        },
    )
    assert presented["pricingDiagnostics"]["legacyActualCostUsd"] == 0.05
    assert presented["customerChargeUsd"] == 0.0
    assert presented["customerOwedUsd"] == 0.0
    assert presented["chargeState"] == "covered"
    assert presented["providerCostUsd"] == 0.05
    assert presented["customerCharge"]["customerTotalMicros"] == 0
    assert "Covered by Hydracept" in presented["pricing"]["summary"]
    assert "actualCost" not in presented
    assert "actualCost" not in presented["pricingDiagnostics"]


def test_format_pricing_summary_covered_vs_charged() -> None:
    covered = format_pricing_summary(0.0, "covered", 0.05)
    assert "US$0.00" in covered
    assert "Covered by Hydracept" in covered
    assert "Managed equivalent: US$0.05" in covered
    assert "Retail" not in covered
    charged = format_pricing_summary(0.12, "charged", 0.05)
    assert charged == "Customer charged: US$0.12."
    unavailable = format_pricing_summary(None, "unavailable", None)
    assert unavailable == "Customer charge unavailable on this payload."
    byok = format_pricing_summary(0.0, "provider_billed_directly", None)
    assert "Hydracept charge: US$0.00" in byok
    assert "billed directly" in byok


def test_present_quote_explains_spending_none() -> None:
    from hydracept.receipt_cost import present_quote

    presented = present_quote({"spending": "none", "expectedCharge": 0.05})
    assert "will not be billed" in presented["customerChargeNote"]


def test_provider_usage_actual_cost_is_private_procurement_not_a_customer_cost() -> None:
    """ADR-022: actual_cost is what Hydracept paid; never a customer cost field."""
    presented = present_receipt(
        {
            "receiptId": "rcpt_three_numbers",
            "actualCost": 0.05,
            "pricing": {
                "mode": "managed",
                "basisEstimated": {"amountMicros": 50_000},
                "estimatedCharge": {"amountMicros": 53_000},
                "basisActual": {"amountMicros": 50_000},
                "charge": {"customerCharge": {"amountMicros": 0, "currency": "USD"}},
                "providerUsage": {"actual_cost": 0.017715, "costBearer": "hydracept"},
            },
        }
    )
    assert presented["customerChargeUsd"] == 0.0
    assert presented["chargeState"] == "covered"
    assert presented["providerCostUsd"] == 0.05
    assert presented["providerCostBasis"] == "upstream-price-basis"
    assert presented["estimatedProviderCostUsd"] == 0.05
    assert presented["estimatedCustomerChargeUsd"] == 0.053
    assert presented["legacyCostAliases"]["providerProcurementCostUsd"] == 0.017715
    assert "retailUsd" not in presented
    assert "retailPriceUsd" not in presented


def test_no_retail_or_list_price_survives_anywhere_in_the_presented_view() -> None:
    raw = {
        "id": "wfr_1",
        "actualCost": 0.05,
        "status": "succeeded",
        "pricing": {
            "price": {"amountMicros": 50_000, "currency": "USD"},
            "charge": {"customerCharge": {"amountMicros": 0, "currency": "USD"}},
            "providerUsage": {"actualCost": 0.017715},
        },
    }
    for presented in (present_receipt(raw), present_job(dict(raw))):
        rendered = json.dumps(presented)
        assert "retail" not in rendered.lower()
        assert "actualCost" not in rendered


def test_provider_usage_internal_cost_is_preserved_when_reported_cost_also_present() -> None:
    """Procurement cost is quarantined, never promoted, and never silently dropped."""
    presented = present_receipt(
        {
            "pricing": {
                "mode": "managed",
                "charge": {"customerCharge": {"amountMicros": 0, "currency": "USD"}},
                "providerUsage": {"reportedCost": {"amountMicros": 500}, "actualCost": 3.0},
            }
        }
    )
    assert presented["providerCostUsd"] == 0.0005
    assert presented["receipt"]["pricing"]["providerUsage"] == {
        "reportedCost": {"amountMicros": 500}
    }
    assert presented["legacyCostAliases"]["providerProcurementCostUsd"] == 3.0


def test_non_numeric_ambiguous_cost_is_never_silently_discarded() -> None:
    presented = present_receipt(
        {
            "pricing": {
                "charge": {"customerCharge": {"amountMicros": 0, "currency": "USD"}},
                "providerUsage": {"actual_cost": "unavailable"},
            }
        }
    )
    assert presented["receipt"]["pricing"]["providerUsage"]["actual_cost"] == "unavailable"


def test_customer_charge_breakdown_exposes_the_hydracept_fee() -> None:
    from hydracept.receipt_cost import customer_charge_breakdown

    breakdown = customer_charge_breakdown(
        {
            "pricing": {
                "charge": {
                    "customerCharge": {
                        "upstreamMicros": 1_000_000,
                        "hydraceptFeeMicros": 60_000,
                        "customerTotalMicros": 1_060_000,
                    }
                }
            }
        }
    )
    assert breakdown == {
        "upstreamMicros": 1_000_000,
        "hydraceptFeeMicros": 60_000,
        "customerTotalMicros": 1_060_000,
    }


def test_client_and_contract_cost_copies_agree() -> None:
    """The published client copy and hydracept_contracts must classify identically."""
    contracts = pytest.importorskip("hydracept_contracts.receipt_cost")
    import hydracept.receipt_cost as client

    receipts = [
        {
            "pricing": {
                "mode": "managed",
                "basisActual": {"amountMicros": 50_000},
                "basisEstimated": {"amountMicros": 50_000},
                "estimatedCharge": {"amountMicros": 53_000},
                "charge": {"customerCharge": {"amountMicros": 0}},
                "providerUsage": {"reportedCost": {"amountMicros": 50_000}, "actual_cost": 0.017715},
            }
        },
        {
            "pricing": {
                "mode": "byok",
                "providerUsage": {"reportedCost": {"amountMicros": 3_088_700}},
            }
        },
        {"pricing": {"mode": "managed", "actualCharge": {"amountMicros": 40_000}}},
        {"pricing": {"mode": "managed", "providerReportedCostMicros": 12_345}},
        {"pricing": {}},
    ]
    for name in (
        "customer_charge_micros",
        "provider_cost_micros",
        "estimated_provider_cost_micros",
        "estimated_customer_charge_micros",
        "surfaced_cost_micros",
    ):
        for receipt in receipts:
            assert getattr(client, name)(receipt) == getattr(contracts, name)(receipt), (
                name,
                receipt,
            )
