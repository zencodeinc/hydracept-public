"""Funding contract regression tests.

The historical ``managedTrialRemaining`` field was backed by the aggregate
ManagedCreditBucket ledger. These tests prevent clients from turning an aggregate
balance back into an asserted initial-trial amount.
"""

from hydracept.cli.funding import _managed_credit_from_diagnostics


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
