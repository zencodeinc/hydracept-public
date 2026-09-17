"""Canonical pricing vocabulary: provider cost, customer charge, coverage."""

from __future__ import annotations

from hydracept.receipt_cost import present_quote, present_receipt
from hydracept.run_result import RunPricing, RunResult

_LEGACY_CHARGE_STATES = frozenset({"byok", "customer_funded", "unsettled"})
_CANONICAL_CHARGE_STATES = frozenset(
    {"charged", "covered", "provider_billed_directly", "unavailable"}
)


def test_managed_charge_reconciles_to_provider_cost_plus_six_percent() -> None:
    pricing = RunPricing(
        mode="managed",
        customer_total_micros=42_400,
        provider_cost_micros=40_000,
        managed_equivalent_micros=42_400,
        financial_state="charged",
        service_fee_bps=600,
    )
    payload = pricing.to_dict()
    assert payload["billingMode"] == "managed"
    assert payload["chargeState"] == "charged"
    assert payload["chargeExpectation"] == "charged"
    assert payload["customerChargeUsd"] == 0.0424
    assert payload["providerCostUsd"] == 0.04
    assert payload["managedFeePercent"] == 6.0
    assert round(payload["providerCostUsd"] * 1.06, 6) == payload["customerChargeUsd"]


def test_covered_execution_is_distinct_from_managed_billing() -> None:
    pricing = RunPricing(
        mode="managed",
        customer_total_micros=0,
        provider_cost_micros=17_700,
        managed_equivalent_micros=18_762,
        financial_state="covered",
    )
    payload = pricing.to_dict()
    assert payload["chargeState"] == "covered"
    assert payload["chargeExpectation"] == "covered"
    assert payload["customerChargeUsd"] == 0.0
    assert payload["managedEquivalentChargeUsd"] == 0.018762


def test_byok_reports_zero_hydracept_fee() -> None:
    pricing = RunPricing(
        mode="byok",
        customer_total_micros=None,
        provider_cost_micros=3_000_000,
        service_fee_bps=0,
    )
    payload = pricing.to_dict()
    assert payload["billingMode"] == "byok"
    assert payload["chargeState"] == "provider_billed_directly"
    assert payload["chargeExpectation"] == "provider_billed_directly"
    assert payload["customerChargeUsd"] is None
    assert payload["managedFeePercent"] == 0.0


def test_unsettled_charge_state_is_unavailable_not_zero() -> None:
    payload = RunPricing(mode="managed").to_dict()
    assert payload["chargeState"] == "unavailable"


def test_byok_zero_customer_total_is_provider_billed_directly_everywhere() -> None:
    receipt = {
        "pricing": {
            "mode": "byok",
            "charge": {"customerCharge": {"amountMicros": 0, "currency": "USD"}},
        }
    }
    run_state = RunResult(
        capability="text.general.fast.v1",
        pricing=RunPricing(
            mode="byok",
            customer_total_micros=0,
            financial_state="provider_billed_directly",
        ),
    ).to_dict()["pricing"]["chargeState"]
    receipt_state = present_receipt(receipt)["chargeState"]
    assert run_state == "provider_billed_directly"
    assert receipt_state == "provider_billed_directly"


def test_no_surface_emits_legacy_charge_state_vocabulary() -> None:
    states = {
        RunPricing(mode="byok", customer_total_micros=0).to_dict()["chargeState"],
        RunPricing(mode="managed", customer_total_micros=42_400).to_dict()["chargeState"],
        RunPricing(mode="managed", customer_total_micros=0).to_dict()["chargeState"],
        RunPricing(mode="managed").to_dict()["chargeState"],
        present_receipt(
            {"pricing": {"mode": "byok", "charge": {"customerCharge": {"amountMicros": 0}}}}
        )["chargeState"],
        present_receipt(
            {"pricing": {"mode": "managed", "charge": {"customerCharge": {"amountMicros": 10}}}}
        )["chargeState"],
    }
    assert not (states & _LEGACY_CHARGE_STATES)
    assert states <= _CANONICAL_CHARGE_STATES


def test_managed_fee_percent_is_projected_from_sealed_policy() -> None:
    from hydracept.cli.run_facade import _pricing_from_job

    unsealed = _pricing_from_job(
        {"status": "succeeded"}, {"pricing": {"mode": "managed"}}
    ).to_dict()
    assert "managedFeePercent" not in unsealed
    sealed = _pricing_from_job(
        {"status": "succeeded"},
        {"pricing": {"mode": "managed", "policy": {"serviceFeeBps": 600}}},
    ).to_dict()
    assert sealed["managedFeePercent"] == 6.0
    hydracept_sealed = _pricing_from_job(
        {"status": "succeeded"},
        {"pricing": {"mode": "managed", "hydracept": {"serviceFeeRateBps": 600}}},
    ).to_dict()
    assert hydracept_sealed["managedFeePercent"] == 6.0


def test_estimated_provider_cost_only_when_sealed() -> None:
    from hydracept.cli.run_facade import _pricing_from_job

    absent = _pricing_from_job({"status": "succeeded"}, {"pricing": {"mode": "managed"}}).to_dict()
    assert "estimatedProviderCostUsd" not in absent
    sealed = _pricing_from_job(
        {"status": "succeeded"},
        {"pricing": {"mode": "managed", "estimatedProviderPriceBasisMicros": 40_000}},
    ).to_dict()
    assert sealed["estimatedProviderCostUsd"] == 0.04


def test_quote_uses_charge_expectation_vocabulary() -> None:
    covered = present_quote({"spending": "none", "expectedCharge": 0.05})
    assert covered["chargeExpectation"] == "covered"
    assert "managed equivalent" in covered["customerChargeNote"].lower()
    managed = present_quote({"spending": "customer", "expectedCharge": 0.05})
    assert managed["chargeExpectation"] == "charged"
    assert "6%" in managed["customerChargeNote"]
    byok = present_quote({"spending": "customer", "billingMode": "byok"})
    assert byok["chargeExpectation"] == "provider_billed_directly"
    assert "0%" in byok["customerChargeNote"]
