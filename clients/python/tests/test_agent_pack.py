"""Init agent-pack readiness and idempotent install."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import json

import pytest

from hydracept.cli.agents.install import install_agent_pack
from hydracept.cli.init_resolver import agent_pack_init_fields, try_install_agent_pack


def test_agent_pack_init_fields_ready_false_when_pack_missing() -> None:
    fields = agent_pack_init_fields(False, "disk full", doctor_ok=True)
    assert fields["initialized"] is True
    assert fields["ready"] is False
    assert fields["agentPackInstalled"] is False
    assert fields["nextAction"] == "python -m hydracept agents install --auto"
    assert fields["agentPackError"] == "disk full"


def test_agent_pack_init_fields_ready_true_when_pack_and_doctor_ok() -> None:
    fields = agent_pack_init_fields(True, "", doctor_ok=True)
    assert fields["ready"] is True
    assert fields["agentPackInstalled"] is True
    assert "nextAction" not in fields


def test_try_install_agent_pack_does_not_raise() -> None:
    with patch(
        "hydracept.cli.agents.install.install_agent_pack",
        side_effect=RuntimeError("pack write failed"),
    ):
        installed, error = try_install_agent_pack(Path("."))
    assert installed is False
    assert "pack write failed" in error


def test_install_agent_pack_auto_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CURSOR_AGENT", raising=False)
    monkeypatch.delenv("CURSOR_EXTENSION_HOST_ROLE", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    first = install_agent_pack(tmp_path, auto=True, smoke=False)
    second = install_agent_pack(tmp_path, auto=True, smoke=False)
    assert first.hosts
    assert second.hosts == first.hosts
    assert second.files
    plugin_mcp = tmp_path / ".cursor" / "plugins" / "hydracept" / "mcp.json"
    payload = json.loads(plugin_mcp.read_text(encoding="utf-8"))
    args = payload["mcpServers"]["hydracept"]["args"]
    assert "--workspace" in args
    assert "${workspaceFolder}" in args
