"""doctor --fix preserves peer MCP servers and refuses foreign hydracept bytes."""

from __future__ import annotations

import json
from pathlib import Path

from hydracept.cli.doctor_fix import apply_doctor_fix
from hydracept.cli.mcp_bind import bind_workspace_mcp


def test_fix_merges_hydracept_and_preserves_peers(tmp_path: Path) -> None:
    cursor = tmp_path / ".cursor" / "mcp.json"
    cursor.parent.mkdir(parents=True)
    cursor.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "other": {"command": "npx", "args": ["-y", "other-mcp"]},
                    "hydracept": {"url": "https://api.hydracept.com/mcp"},
                }
            }
        ),
        encoding="utf-8",
    )
    result = apply_doctor_fix(tmp_path)
    payload = json.loads(cursor.read_text(encoding="utf-8"))
    assert payload["mcpServers"]["other"]["command"] == "npx"
    assert payload["mcpServers"]["hydracept"]["command"]
    assert "url" not in payload["mcpServers"]["hydracept"]
    assert result.reload_required
    assert result.human_action_required == "reload_cursor"
    assert result.spent is False


def test_fix_blocks_user_modified_hydracept_entry(tmp_path: Path) -> None:
    cursor = tmp_path / ".cursor" / "mcp.json"
    cursor.parent.mkdir(parents=True)
    cursor.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "hydracept": {"command": "node", "args": ["custom-hydracept.js"]},
                    "other": {"command": "npx"},
                }
            }
        ),
        encoding="utf-8",
    )
    result = apply_doctor_fix(tmp_path)
    payload = json.loads(cursor.read_text(encoding="utf-8"))
    assert payload["mcpServers"]["hydracept"]["command"] == "node"
    assert payload["mcpServers"]["other"]["command"] == "npx"
    assert result.blocked
    assert result.human_action_required == "repair_blocked"


def test_fix_idempotent_after_bind(tmp_path: Path) -> None:
    bind_workspace_mcp(tmp_path)
    first = apply_doctor_fix(tmp_path)
    second = apply_doctor_fix(tmp_path)
    assert not second.reload_required
    assert first.spent is False
