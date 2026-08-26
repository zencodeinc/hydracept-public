"""CLI workspace context merge for portable job files."""

from __future__ import annotations

from hydracept.cli.job_context import WorkspaceContextError, merge_workspace_job_context
from hydracept.cli.workspace import ResolvedWorkspace


def test_merge_workspace_job_context_fills_missing_project() -> None:
    workspace = ResolvedWorkspace(
        api_url="https://api.hydracept.com",
        token="hapt_test",
        project_id="prj_ready",
        environment="development",
    )
    merged = merge_workspace_job_context(
        {"input": {"prompt": "hud"}, "idempotencyKey": "k1"},
        workspace,
    )
    assert merged["context"]["projectId"] == "prj_ready"
    assert merged["context"]["productId"] == "prj_ready"
    assert merged["context"]["environment"] == "development"


def test_merge_workspace_job_context_skips_config_identity() -> None:
    merged = merge_workspace_job_context(
        {"input": {"prompt": "hud"}},
        None,
        config={"projectId": "prj_cfg", "environment": "staging"},
    )
    assert "projectId" not in (merged.get("context") or {})


def test_merge_workspace_job_context_same_project_is_idempotent() -> None:
    workspace = ResolvedWorkspace(
        api_url="https://api.hydracept.com",
        token="hapt_test",
        project_id="prj_ready",
        environment="development",
    )
    once = merge_workspace_job_context({"input": {"prompt": "hud"}}, workspace)
    twice = merge_workspace_job_context(once, workspace)
    assert twice["context"]["projectId"] == "prj_ready"
    assert twice["context"] == once["context"]


def test_merge_workspace_job_context_rejects_project_mismatch() -> None:
    workspace = ResolvedWorkspace(
        api_url="https://api.hydracept.com",
        token="hapt_test",
        project_id="prj_ready",
        environment="development",
    )
    try:
        merge_workspace_job_context(
            {"context": {"projectId": "prj_other"}},
            workspace,
        )
        raise AssertionError("expected WorkspaceContextError")
    except WorkspaceContextError as exc:
        assert "prj_other" in str(exc)
        assert "prj_ready" in str(exc)


def test_merge_workspace_job_context_preserves_matching_explicit_context() -> None:
    workspace = ResolvedWorkspace(
        api_url="https://api.hydracept.com",
        token="hapt_test",
        project_id="prj_ready",
        environment="development",
    )
    merged = merge_workspace_job_context(
        {
            "context": {
                "projectId": "prj_ready",
                "productId": "prd_explicit",
                "environment": "staging",
            }
        },
        workspace,
    )
    assert merged["context"]["projectId"] == "prj_ready"
    assert merged["context"]["productId"] == "prd_explicit"
    assert merged["context"]["environment"] == "staging"


def test_merge_workspace_job_context_omits_quote_ids() -> None:
    workspace = ResolvedWorkspace(
        api_url="https://api.hydracept.com",
        token="hapt_test",
        project_id="prj_ready",
        environment="development",
    )
    merged = merge_workspace_job_context(
        {
            "input": {"prompt": "hud"},
            "execution": {
                "executionPreference": "automatic",
                "quoteId": "gquote_stale",
                "estimateId": "est_stale",
            },
        },
        workspace,
    )
    assert "quoteId" not in merged["execution"]
    assert "estimateId" not in merged["execution"]
    assert merged["execution"]["executionPreference"] == "automatic"
