"""Tests for project stdio MCP bind (init/doctor/agents install)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from hydracept.cli.mcp_bind import bind_workspace_mcp, inspect_workspace_mcp, stdio_args


def test_stdio_args_include_absolute_workspace(tmp_path: Path) -> None:
    args = stdio_args(tmp_path)
    assert args[:4] == ["-m", "hydracept", "mcp", "serve"]
    assert "--workspace" in args
    assert str(tmp_path.resolve()) in args


def test_bind_writes_cursor_and_claude_stdio(tmp_path: Path) -> None:
    result = bind_workspace_mcp(tmp_path)
    assert result.bound
    assert result.transport == "stdio"
    assert result.reload_required
    cursor = json.loads((tmp_path / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    claude = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    for payload in (cursor, claude):
        hydra = payload["mcpServers"]["hydracept"]
        assert hydra["command"] in {"python", sys.executable}
        assert hydra["args"] == stdio_args(tmp_path)
        assert "url" not in hydra
        assert "headers" not in hydra
    assert ".cursor/mcp.json" in result.project_config
    assert ".mcp.json" in result.project_config


def test_bind_replaces_hosted_and_preserves_other_servers(tmp_path: Path) -> None:
    cursor_path = tmp_path / ".cursor" / "mcp.json"
    cursor_path.parent.mkdir(parents=True)
    cursor_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "other": {"command": "npx", "args": ["-y", "other-mcp"]},
                    "hydracept": {
                        "url": "https://api.hydracept.com/mcp",
                        "headers": {"Authorization": "Bearer ${HYDRACEPT_API_KEY}"},
                    },
                    "hydracept-local": {"command": "python", "args": ["-m", "hydracept", "mcp", "serve"]},
                }
            }
        ),
        encoding="utf-8",
    )
    result = bind_workspace_mcp(tmp_path)
    assert result.reload_required
    payload = json.loads(cursor_path.read_text(encoding="utf-8"))
    servers = payload["mcpServers"]
    assert "hydracept-local" not in servers
    assert servers["other"]["command"] == "npx"
    assert servers["hydracept"]["command"] in {"python", sys.executable}
    assert "url" not in servers["hydracept"]


def test_bind_is_idempotent(tmp_path: Path) -> None:
    first = bind_workspace_mcp(tmp_path)
    second = bind_workspace_mcp(tmp_path)
    assert first.reload_required
    assert not second.reload_required
    inspected = inspect_workspace_mcp(tmp_path)
    assert inspected.bound
    assert not inspected.reload_required


def test_bind_writes_vscode_only_when_vscode_exists(tmp_path: Path) -> None:
    bind_workspace_mcp(tmp_path)
    assert not (tmp_path / ".vscode" / "mcp.json").exists()
    (tmp_path / ".vscode").mkdir()
    result = bind_workspace_mcp(tmp_path)
    vscode = json.loads((tmp_path / ".vscode" / "mcp.json").read_text(encoding="utf-8"))
    hydra = vscode["servers"]["hydracept"]
    assert hydra["type"] == "stdio"
    assert hydra["command"] in {"python", sys.executable}
    assert ".vscode/mcp.json" in result.project_config
