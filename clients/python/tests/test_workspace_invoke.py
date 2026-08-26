"""Workspace-bound client merge and invoke façade."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hydracept import HydraceptClient
from hydracept.cli.job_context import WorkspaceContextError
from hydracept.cli.workspace import ResolvedWorkspace
from hydracept.workspace import HydraceptWorkspace


def _workspace() -> ResolvedWorkspace:
    return ResolvedWorkspace(
        api_url="https://api.hydracept.com",
        token="hapt_test",
        project_id="cpr_bound",
        environment="development",
    )


def test_bound_client_invoke_merges_workspace_context() -> None:
    client = HydraceptClient("https://api.hydracept.com", "hapt_test", workspace=_workspace())
    with patch.object(client, "_post", return_value={"ok": True}) as post:
        client.invoke_capability("text.general.fast.v1", {"input": {"prompt": "hi"}})
    body = post.call_args.args[1]
    assert body["context"]["projectId"] == "cpr_bound"
    assert body["context"]["productId"] == "cpr_bound"


def test_bound_client_rejects_explicit_project_mismatch() -> None:
    client = HydraceptClient("https://api.hydracept.com", "hapt_test", workspace=_workspace())
    with pytest.raises(WorkspaceContextError):
        client.invoke_capability(
            "text.general.fast.v1",
            {"context": {"projectId": "cpr_other"}, "input": {"prompt": "hi"}},
        )


def test_workspace_invoke_is_client_facade() -> None:
    client = MagicMock()
    jobs = MagicMock()
    workspace = HydraceptWorkspace(client, jobs, Path("."))
    body = {"input": {"prompt": "hi"}}
    workspace.invoke("text.general.fast.v1", body)
    client.invoke_capability.assert_called_once_with("text.general.fast.v1", body)
    jobs.submit.assert_not_called()
