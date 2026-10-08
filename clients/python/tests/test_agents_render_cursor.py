"""Cursor plugin render writes MCP env for signup attribution."""

from __future__ import annotations

import json
from pathlib import Path

from hydracept.cli.agents.render import render_cursor


def test_render_cursor_writes_plugin_client_component(tmp_path: Path) -> None:
    render_cursor(tmp_path)
    mcp_path = tmp_path / ".cursor" / "plugins" / "hydracept" / "mcp.json"
    assert mcp_path.is_file()
    payload = json.loads(mcp_path.read_text(encoding="utf-8"))
    env = payload["mcpServers"]["hydracept"].get("env") or {}
    assert env.get("HYDRACEPT_CLIENT_COMPONENT") == "plugin"
    assert "HYDRACEPT_WORKSPACE" in env
