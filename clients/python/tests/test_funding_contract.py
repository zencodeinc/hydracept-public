"""Funding contract regression tests.

The historical ``managedTrialRemaining`` field was backed by the aggregate
ManagedCreditBucket ledger. These tests prevent clients from turning an aggregate
balance back into an asserted initial-trial amount.
"""

from hydracept.cli.funding import (
    _managed_credit_from_diagnostics,
    funding_payload_from_diagnostics,
)


def test_prefers_explicit_managed_credit_balance() -> None:
    remaining, source = _managed_credit_from_diagnostics(
        {
            "managedCreditRemaining": 6.54,
            "managedTrialRemaining": 0.50,
        }
    )

    assert remaining == 6.54
    assert source == "managedCreditRemaining"


def test_legacy_managed_trial_field_is_treated_as_aggregate_alias() -> None:
    remaining, source = _managed_credit_from_diagnostics(
        {"managedTrialRemaining": 6.54}
    )

    assert remaining == 6.54
    assert source == "managedTrialRemaining_legacy_alias"


def test_missing_managed_credit_is_not_invented() -> None:
    remaining, source = _managed_credit_from_diagnostics({})

    assert remaining is None
    assert source == "unavailable"


def test_current_diagnostics_do_not_relabel_customer_zero_as_aggregate_trial() -> None:
    payload = funding_payload_from_diagnostics(
        {
            "managedCreditRemaining": 0.0,
            "managedCreditSemantics": "customer_visible_available_credit",
            "managedTrialRemaining": 0.0,
            "managedExecutionFundingAvailable": True,
            "managedExecutionFundingSources": ["operator"],
            "managedOperatorFundingPresent": True,
            "byokBound": False,
        },
        project_id="cpr_test",
        environment="development",
    )

    assert payload["managedCreditSemantics"] == "customer_visible_available_credit"
    assert payload["managedCreditRemainingUsd"] == 0.0
    assert payload["trialRemainingUsd"] == 0.0
    assert payload["trialRemainingSemantics"] == "active_trial_bucket_only"
    assert payload["managedExecutionFundingAvailable"] is True
    assert payload["managedExecutionFundingSources"] == ["operator"]
    assert payload["managedOperatorFundingPresent"] is True
    assert payload["nextAction"] == "python -m hydracept smoke"
    assert "trialRemainingUsdDeprecated" not in payload
    assert payload["managedCreditSemantics"] != "aggregate_available_credit"


def test_legacy_server_marks_aggregate_semantics_as_legacy() -> None:
    payload = funding_payload_from_diagnostics(
        {"managedCreditRemaining": 6.54, "managedTrialRemaining": 6.54},
        project_id="cpr_test",
        environment="development",
    )

    assert payload["managedCreditSemantics"] == "aggregate_available_credit_legacy"
    assert payload["managedCreditRemainingUsd"] == 6.54
    assert payload["trialRemainingUsd"] == 6.54
    assert "trialRemainingUsdDeprecated" not in payload



def test_prefers_explicit_managed_credit_balance() -> None:
    remaining, source = _managed_credit_from_diagnostics(
        {
            "managedCreditRemaining": 6.54,
            "managedTrialRemaining": 0.50,
        }
    )

    assert remaining == 6.54
    assert source == "managedCreditRemaining"


def test_legacy_managed_trial_field_is_treated_as_aggregate_alias() -> None:
    remaining, source = _managed_credit_from_diagnostics(
        {"managedTrialRemaining": 6.54}
    )

    assert remaining == 6.54
    assert source == "managedTrialRemaining_legacy_alias"


def test_missing_managed_credit_is_not_invented() -> None:
    remaining, source = _managed_credit_from_diagnostics({})

    assert remaining is None
    assert source == "unavailable"
