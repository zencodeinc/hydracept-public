"""Funding contract regression tests.

The historical ``managedTrialRemaining`` field was backed by the aggregate
ManagedCreditBucket ledger. These tests prevent clients from turning an aggregate
balance or internal unbounded sentinel back into asserted customer money.
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
    assert payload["canExecute"] is True
    assert "can run jobs" in payload["summary"]
    assert "$0.00" in payload["summary"]
    assert "not required" in payload["summary"]
    assert "trialRemainingUsdDeprecated" not in payload
    assert payload["managedCreditSemantics"] != "aggregate_available_credit"


def test_legacy_server_marks_real_aggregate_semantics_as_legacy() -> None:
    payload = funding_payload_from_diagnostics(
        {"managedCreditRemaining": 6.54, "managedTrialRemaining": 6.54},
        project_id="cpr_test",
        environment="development",
    )

    assert payload["managedCreditSemantics"] == "aggregate_available_credit_legacy"
    assert payload["managedCreditRemainingUsd"] == 6.54
    assert payload["trialRemainingUsd"] == 6.54
    assert "trialRemainingUsdDeprecated" not in payload


def test_internal_unbounded_sentinel_is_never_presented_as_customer_credit() -> None:
    payload = funding_payload_from_diagnostics(
        {
            "managedCreditRemaining": 999_999_930.0,
            "managedTrialRemaining": 999_999_930.0,
            "managedExecutionFundingAvailable": True,
            "managedExecutionFundingSource": "internal",
            "managedExecutionFundingSources": ["operator"],
            "managedOperatorFundingPresent": True,
        },
        project_id="cpr_test",
        environment="development",
    )

    assert payload["managedCreditRemainingUsd"] is None
    assert payload["trialRemainingUsd"] is None
    assert payload["managedCreditSemantics"] == "unavailable"
    assert payload["managedCreditSource"] == "unavailable_internal_value"
    assert payload["managedExecutionFundingAvailable"] is True
    assert payload["managedExecutionFundingSource"] == "internal"
    assert payload["managedChargeExpectation"] == "covered_by_hydracept"
    assert payload["nextAction"] == "python -m hydracept smoke"


def test_sentinel_without_explicit_funding_facts_does_not_infer_internal_coverage() -> None:
    payload = funding_payload_from_diagnostics(
        {"managedCreditRemaining": 999_999_930.0},
        project_id="cpr_test",
        environment="development",
    )

    assert payload["managedCreditRemainingUsd"] is None
    assert payload["managedExecutionFundingAvailable"] is None
    assert payload["managedExecutionFundingSource"] == "unavailable"
    assert payload["managedChargeExpectation"] == "unavailable"
    assert payload["nextAction"] == "python -m hydracept funding setup"


def test_funding_group_runs_without_click_mixin(monkeypatch) -> None:
    from click.testing import CliRunner

    from hydracept.cli.entrypoint import build_app

    monkeypatch.setattr(
        "hydracept.cli.funding.funding_status",
        lambda project_root: {
            "managedCreditRemainingUsd": 0.0,
            "trialRemainingUsd": 0.0,
            "managedExecutionFundingSource": "unavailable",
            "byokConnected": False,
        },
    )
    runner = CliRunner()
    app = build_app()
    bare = runner.invoke(app, ["funding"])
    assert bare.exception is None, bare.output
    assert bare.exit_code == 0
    help_result = runner.invoke(app, ["funding", "status", "--help"])
    assert help_result.exit_code == 0
    assert "_param_default_explicit" not in (help_result.output or "")
