"""HydraceptWorkspace.open never takes a project override."""

from __future__ import annotations

from pathlib import Path

import pytest

from hydracept.cli.bootstrap import write_secrets
from hydracept.cli.project import write_project_binding
from hydracept.workspace import HydraceptWorkspace


def test_workspace_open_uses_project_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRACEPT_PROJECT", raising=False)
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    write_project_binding(
        tmp_path,
        {"projectId": "cpr_ws", "apiOrigin": "https://api.example.com"},
    )
    write_secrets(tmp_path, {"apiKey": "hapt_ws"})
    opened = HydraceptWorkspace.open(tmp_path)
    assert opened.client.base_url == "https://api.example.com"
    assert opened.jobs is not None
