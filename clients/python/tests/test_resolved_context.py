"""ResolvedHydraceptContext — execution project or nothing."""

from __future__ import annotations

from hydracept.context import (
    PROJECT_CREDENTIAL_MISMATCH,
    _credential_from_diagnostics,
    build_resolved_context,
)


def test_matching_checkout_and_credential_enables_execution() -> None:
    ctx = build_resolved_context(
        checkout_project_id="cpr_a",
        credential_project_id="cpr_a",
        home_project_id="cpr_home",
        workspace_ready=True,
    )
    assert ctx.execution_project_id == "cpr_a"
    assert ctx.ready is True
    assert ctx.mismatch is None
    assert ctx.home_project_differs is True
    assert ctx.home_impact == "none"
    assert ctx.product_id == "cpr_a"


def test_mismatch_is_fatal_and_clears_execution() -> None:
    ctx = build_resolved_context(
        checkout_project_id="cpr_checkout",
        credential_project_id="cpr_token",
        home_project_id="cpr_home",
        workspace_ready=True,
    )
    assert ctx.execution_project_id is None
    assert ctx.ready is False
    assert ctx.mismatch == PROJECT_CREDENTIAL_MISMATCH


def test_unknown_credential_does_not_invent_execution() -> None:
    ctx = build_resolved_context(
        checkout_project_id="cpr_checkout",
        credential_project_id="",
        workspace_ready=True,
    )
    assert ctx.execution_project_id is None
    assert ctx.ready is False
    assert ctx.mismatch is None


def test_context_json_shape() -> None:
    payload = build_resolved_context(
        checkout_project_id="cpr_a",
        credential_project_id="cpr_a",
        home_project_id="cpr_a",
        workspace_ready=True,
    ).to_dict()
    assert payload["schemaVersion"] == "hydracept.context.v1"
    assert "customerProjectId" not in payload
    assert payload["executionProjectId"] == "cpr_a"
    assert payload["productId"] == "cpr_a"


def test_aliased_diagnostics_fields_are_still_a_credential() -> None:
    """API echoes principal.project_id as both projectId and tokenProjectId."""
    token = _credential_from_diagnostics(
        {"projectId": "cpr_a", "tokenProjectId": "cpr_a"},
        checkout_project_id="cpr_a",
        home_project_id="cpr_home",
    )
    assert token == "cpr_a"
    ctx = build_resolved_context(
        checkout_project_id="cpr_a",
        credential_project_id=token,
        home_project_id="cpr_home",
        workspace_ready=True,
    )
    assert ctx.execution_project_id == "cpr_a"
    assert ctx.ready is True


def test_home_echo_is_not_a_credential_for_another_checkout() -> None:
    token = _credential_from_diagnostics(
        {"projectId": "cpr_home", "tokenProjectId": "cpr_home"},
        checkout_project_id="cpr_checkout",
        home_project_id="cpr_home",
    )
    assert token == ""
    ctx = build_resolved_context(
        checkout_project_id="cpr_checkout",
        credential_project_id=token,
        home_project_id="cpr_home",
        workspace_ready=True,
    )
    assert ctx.execution_project_id is None
    assert ctx.mismatch is None


def test_project_scoped_key_for_home_checkout_is_ready() -> None:
    token = _credential_from_diagnostics(
        {"projectId": "cpr_home", "tokenProjectId": "cpr_home"},
        checkout_project_id="cpr_home",
        home_project_id="cpr_home",
    )
    assert token == "cpr_home"
    ctx = build_resolved_context(
        checkout_project_id="cpr_home",
        credential_project_id=token,
        home_project_id="cpr_home",
        workspace_ready=True,
    )
    assert ctx.execution_project_id == "cpr_home"
    assert ctx.ready is True


def test_assert_execution_allowed_rejects_mismatch() -> None:
    from unittest.mock import patch

    from hydracept.cli.workspace import ResolvedWorkspace
    from hydracept.context import ProjectCredentialMismatch, assert_execution_allowed

    workspace = ResolvedWorkspace(
        api_url="https://api.hydracept.com",
        token="hapt_test",
        project_id="cpr_checkout",
        environment="development",
    )
    with patch(
        "hydracept.context.fetch_identity_payloads",
        return_value=(
            {"projectId": "cpr_token", "tokenProjectId": "cpr_token"},
            {"project": {"id": "cpr_home"}},
        ),
    ):
        try:
            assert_execution_allowed(workspace)
        except ProjectCredentialMismatch:
            return
        raise AssertionError("expected ProjectCredentialMismatch")


def test_assert_execution_allowed_accepts_matching_project() -> None:
    from unittest.mock import patch

    from hydracept.cli.workspace import ResolvedWorkspace
    from hydracept.context import assert_execution_allowed

    workspace = ResolvedWorkspace(
        api_url="https://api.hydracept.com",
        token="hapt_test",
        project_id="cpr_a",
        environment="development",
    )
    with patch(
        "hydracept.context.fetch_identity_payloads",
        return_value=(
            {"projectId": "cpr_a", "tokenProjectId": "cpr_a"},
            {"project": {"id": "cpr_home"}},
        ),
    ):
        ctx = assert_execution_allowed(workspace)
    assert ctx.execution_project_id == "cpr_a"

