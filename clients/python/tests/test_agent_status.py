"""agent-status payload must keep configured for doctor --local-only."""

from __future__ import annotations

from pathlib import Path

import pytest

from hydracept.cli.agent_status import build_agent_status


def test_agent_status_keeps_configured_and_workspace_root(tmp_path: Path) -> None:
    payload = build_agent_status(tmp_path)
    assert payload["configured"] is False
    assert payload["ready"] is False
    assert payload["workspaceRoot"] == str(tmp_path.resolve())
    assert "--workspace" in payload["mcp"]["stdioCommand"]


def test_agent_status_inspects_without_binding(tmp_path: Path) -> None:
    build_agent_status(tmp_path)
    assert not (tmp_path / ".cursor" / "mcp.json").exists()
    assert not (tmp_path / ".mcp.json").exists()
