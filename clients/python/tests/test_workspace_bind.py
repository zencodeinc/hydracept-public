"""Workspace context injection fills missing keys only."""

from __future__ import annotations

from types import SimpleNamespace

from hydracept.workspace_bind import inject_workspace_job_context


def test_inject_fills_missing_context() -> None:
    workspace = SimpleNamespace(project_id="prj_1", environment="development")
    payload = inject_workspace_job_context({"input": {"prompt": "x"}}, workspace)
    assert payload["context"] == {
        "projectId": "prj_1",
        "productId": "prj_1",
        "environment": "development",
    }
    assert payload["input"] == {"prompt": "x"}


def test_inject_does_not_overwrite_existing_context() -> None:
    workspace = SimpleNamespace(project_id="prj_1", environment="development")
    payload = inject_workspace_job_context(
        {
            "context": {
                "projectId": "explicit",
                "productId": "product",
                "environment": "staging",
            }
        },
        workspace,
    )
    assert payload["context"]["projectId"] == "explicit"
    assert payload["context"]["productId"] == "product"
    assert payload["context"]["environment"] == "staging"
