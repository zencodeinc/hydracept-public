"""Tests for project stdio MCP bind (init/doctor/agents install)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from hydracept.cli.mcp_bind import bind_workspace_mcp, inspect_workspace_mcp, stdio_args, stdio_command, stdio_server_entry
from hydracept.mcp.runtime_binding import attest_runtime_binding, inspect_runtime_binding


def test_stdio_command_uses_installing_interpreter() -> None:
    assert stdio_command() == sys.executable


def test_inspect_runtime_missing_generation_is_not_mismatch(tmp_path: Path) -> None:
    attest_runtime_binding(tmp_path, source="test")
    status = inspect_runtime_binding(tmp_path, expected_generations=("configured-gen",))
    assert status.verified is True
    assert status.status == "verified"


def test_stdio_args_always_include_workspace() -> None:
    args = stdio_args(None)
    assert args[:4] == ["-m", "hydracept", "mcp", "serve"]
    assert "--workspace" in args
    assert "${workspaceFolder}" in args


def test_stdio_args_include_absolute_workspace(tmp_path: Path) -> None:
    args = stdio_args(tmp_path)
    assert args[:4] == ["-m", "hydracept", "mcp", "serve"]
    assert "--workspace" in args
    assert str(tmp_path.resolve()) in args


def test_stdio_server_entry_sets_workspace_env(tmp_path: Path) -> None:
    cursor = stdio_server_entry(cursor_placeholder=True)
    assert cursor["env"]["HYDRACEPT_WORKSPACE"] == "${workspaceFolder}"
    absolute = stdio_server_entry(project_root=tmp_path)
    assert absolute["env"]["HYDRACEPT_WORKSPACE"] == str(tmp_path.resolve())


def test_bind_writes_cursor_and_claude_stdio(tmp_path: Path) -> None:
    result = bind_workspace_mcp(tmp_path)
    assert result.bound
    assert result.transport == "stdio"
    assert result.reload_required
    assert result.runtime is not None
    assert result.runtime.status == "missing"
    cursor = json.loads((tmp_path / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    claude = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    cursor_hydra = cursor["mcpServers"]["hydracept"]
    claude_hydra = claude["mcpServers"]["hydracept"]
    assert cursor_hydra["command"] in {"python", sys.executable}
    assert cursor_hydra["args"] == stdio_args(tmp_path, cursor_placeholder=True)
    assert "${workspaceFolder}" in cursor_hydra["args"]
    assert claude_hydra["args"] == stdio_args(tmp_path)
    assert str(tmp_path.resolve()) in claude_hydra["args"]
    assert cursor_hydra["env"]["HYDRACEPT_MCP_GENERATION"]
    assert cursor_hydra["env"]["HYDRACEPT_WORKSPACE"] == "${workspaceFolder}"
    assert claude_hydra["env"]["HYDRACEPT_WORKSPACE"] == str(tmp_path.resolve())
    assert "url" not in cursor_hydra
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


def test_bind_requires_live_runtime_even_when_config_is_idempotent(tmp_path: Path) -> None:
    first = bind_workspace_mcp(tmp_path)
    second = bind_workspace_mcp(tmp_path)
    assert first.reload_required
    assert second.reload_required
    assert first.generation == second.generation
    inspected = inspect_workspace_mcp(tmp_path)
    assert inspected.bound
    assert inspected.reload_required
    assert inspected.runtime is not None
    assert inspected.runtime.status == "missing"

    attest_runtime_binding(
        tmp_path,
        source="test",
        env={"HYDRACEPT_MCP_GENERATION": first.generation},
    )
    live = inspect_workspace_mcp(tmp_path)
    assert live.bound
    assert not live.reload_required
    assert live.runtime is not None
    assert live.runtime.verified
    assert live.runtime.status == "verified"


def test_bind_bumps_generation_when_credential_identity_changes(tmp_path: Path) -> None:
    secrets = tmp_path / ".hydracept" / "secrets.json"
    secrets.parent.mkdir(parents=True)
    secrets.write_text('{"apiKey": "hapt_aaaa1111"}', encoding="utf-8")
    first = bind_workspace_mcp(tmp_path)
    attest_runtime_binding(
        tmp_path,
        source="test",
        env={"HYDRACEPT_MCP_GENERATION": first.generation},
    )
    assert not inspect_workspace_mcp(tmp_path).reload_required
    secrets.write_text('{"apiKey": "hapt_bbbb2222"}', encoding="utf-8")
    second = bind_workspace_mcp(tmp_path)
    assert second.reload_required
    assert first.generation != second.generation
    assert second.runtime is not None
    assert second.runtime.status == "generation_mismatch"


def test_bind_does_not_rewrite_user_level_cursor_targets(tmp_path: Path, monkeypatch) -> None:
    host = tmp_path / "host-mcp.json"
    host.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "hydracept": {
                        "command": "python",
                        "args": ["-m", "hydracept", "mcp", "serve"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "hydracept.cli.mcp_bind.cursor_host_mcp_targets",
        lambda: [(host, "mcpServers")],
    )
    bind_workspace_mcp(tmp_path)
    payload = json.loads(host.read_text(encoding="utf-8"))
    assert payload["mcpServers"]["hydracept"]["args"] == ["-m", "hydracept", "mcp", "serve"]


def test_bind_skips_custom_host_hydracept_entry(tmp_path: Path, monkeypatch) -> None:
    host = tmp_path / "host-mcp.json"
    host.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "hydracept": {"command": "node", "args": ["custom-hydracept.js"]},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "hydracept.cli.mcp_bind.cursor_host_mcp_targets",
        lambda: [(host, "mcpServers")],
    )
    bind_workspace_mcp(tmp_path)
    payload = json.loads(host.read_text(encoding="utf-8"))
    assert payload["mcpServers"]["hydracept"]["command"] == "node"


def test_bind_does_not_rewrite_owned_host_stdio(tmp_path: Path, monkeypatch) -> None:
    host = tmp_path / "host-mcp.json"
    original = {
        "mcpServers": {
            "hydracept": {
                "command": "python",
                "args": ["-m", "hydracept", "mcp", "serve"],
            }
        }
    }
    host.write_text(json.dumps(original), encoding="utf-8")
    monkeypatch.setattr(
        "hydracept.cli.mcp_bind.cursor_host_mcp_targets",
        lambda: [(host, "mcpServers")],
    )
    bind_workspace_mcp(tmp_path)
    payload = json.loads(host.read_text(encoding="utf-8"))
    assert payload == original


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


def test_user_apps_workaround_is_explicit_and_removable(tmp_path: Path, monkeypatch) -> None:
    from hydracept.cli.mcp_bind import bind_user_apps_workaround, remove_user_apps_workaround

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("hydracept.cli.mcp_bind.Path.home", classmethod(lambda cls: home))
    workspace = tmp_path / "repo"
    workspace.mkdir()
    project_mcp = workspace / ".cursor" / "mcp.json"
    project_mcp.parent.mkdir(parents=True)
    project_mcp.write_text(
        json.dumps({"mcpServers": {"hydracept": {"command": "python", "args": ["-m", "hydracept", "mcp", "serve"]}}}),
        encoding="utf-8",
    )
    record = bind_user_apps_workaround(workspace)
    shadowed = json.loads(project_mcp.read_text(encoding="utf-8"))
    assert "hydracept" not in shadowed["mcpServers"]
    assert "hydracept-project" in shadowed["mcpServers"]
    assert record["projectMcpRenamed"] is True
    cursor = json.loads((home / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    entry = cursor["mcpServers"]["hydracept"]
    assert str(workspace.resolve()) in entry["args"]
    assert "${workspaceFolder}" not in entry["args"]
    assert record["workspace"] == str(workspace.resolve())
    assert entry["command"] == sys.executable
    assert str(workspace.resolve() / "clients" / "python") == entry["env"]["PYTHONPATH"]
    plugin = json.loads(
        (home / ".cursor" / "plugins" / "local" / "hydracept" / "mcp.json").read_text(encoding="utf-8")
    )
    assert plugin["mcpServers"]["hydracept"]["args"] == entry["args"]
    assert "${workspaceFolder}" not in plugin["mcpServers"]["hydracept"]["args"]
    removed = remove_user_apps_workaround()
    assert removed["removed"] is True
    leftover = json.loads((home / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    assert "hydracept" not in leftover.get("mcpServers", {})
    restored_plugin = json.loads(
        (home / ".cursor" / "plugins" / "local" / "hydracept" / "mcp.json").read_text(encoding="utf-8")
    )
    assert restored_plugin["mcpServers"]["hydracept"]["env"]["HYDRACEPT_WORKSPACE"] == "${workspaceFolder}"
    restored_project = json.loads(project_mcp.read_text(encoding="utf-8"))
    assert "hydracept" in restored_project["mcpServers"]
    assert "hydracept-project" not in restored_project["mcpServers"]
    assert not (home / ".cursor" / "hydracept-user-apps.json").exists()


def test_inspect_runtime_binding_same_process_is_verified(tmp_path: Path) -> None:
    payload = attest_runtime_binding(tmp_path, source="test")
    status = inspect_runtime_binding(tmp_path)
    assert status.verified is True
    assert status.status == "verified"
    assert payload["version"]
    assert payload["mcpVersion"] == payload["version"]


def test_inspect_runtime_binding_dead_pid_is_stale(tmp_path: Path) -> None:
    attest_runtime_binding(tmp_path, source="test")
    path = tmp_path / ".hydracept" / "mcp-runtime.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["pid"] = 1_000_000_001
    path.write_text(json.dumps(payload), encoding="utf-8")
    status = inspect_runtime_binding(tmp_path)
    assert status.verified is False
    assert status.status in {"stale", "pid_reused"}
