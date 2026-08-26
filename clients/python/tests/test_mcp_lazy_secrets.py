"""MCP lazy secrets: start without secrets, init writes them, next tool reads them."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hydracept.cli.project import write_project_binding
from hydracept.cli.workspace import WorkspaceNotReadyError, require_ready_workspace
from hydracept.mcp.server import _client, configure_workspace


def test_require_ready_after_secrets_appear_without_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.delenv("HYDRACEPT_TOKEN", raising=False)
    write_project_binding(
        tmp_path,
        {"projectId": "cpr_lazy", "apiOrigin": "https://api.example.com"},
    )
    configure_workspace(tmp_path)
    with pytest.raises(WorkspaceNotReadyError):
        require_ready_workspace(tmp_path)
    secrets = tmp_path / ".hydracept" / "secrets.json"
    secrets.write_text(json.dumps({"apiKey": "hapt_after_init"}), encoding="utf-8")
    resolved = require_ready_workspace(tmp_path)
    assert resolved.token == "hapt_after_init"
    assert resolved.project_id == "cpr_lazy"
    client = _client()
    assert client.token == "hapt_after_init"
    assert client.base_url == "https://api.example.com"
