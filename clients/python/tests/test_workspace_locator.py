"""MCP workspace locator must not latch onto the user home session store."""

from __future__ import annotations

from pathlib import Path

import pytest

from hydracept.mcp.workspace_locator import (
    CURSOR_WORKSPACE_PLACEHOLDER,
    is_unusable_mcp_cwd,
    resolve_mcp_workspace,
)
from hydracept.cli.workspace import WorkspaceNotReadyError


def test_explicit_workspace_wins(tmp_path: Path) -> None:
    checkout = tmp_path / "game"
    checkout.mkdir()
    (checkout / ".hydracept").mkdir()
    (checkout / ".hydracept" / "secrets.json").write_text("{}", encoding="utf-8")
    assert resolve_mcp_workspace(checkout, cwd=tmp_path) == checkout.resolve()


def test_unexpanded_placeholder_falls_back_to_checkout(tmp_path: Path, monkeypatch) -> None:
    checkout = tmp_path / "game"
    checkout.mkdir()
    (checkout / ".git").mkdir()
    (checkout / ".hydracept").mkdir()
    (checkout / ".hydracept" / "secrets.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(checkout)
    resolved = resolve_mcp_workspace(
        CURSOR_WORKSPACE_PLACEHOLDER,
        cwd=checkout,
        env={},
    )
    assert resolved == checkout.resolve()


def test_does_not_use_user_home_session(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / ".hydracept").mkdir()
    (home / ".hydracept" / "session.json").write_text("{}", encoding="utf-8")
    plugin = home / ".cursor" / "plugins" / "local" / "hydracept"
    plugin.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home.resolve())
    resolved = resolve_mcp_workspace(None, cwd=plugin, env={})
    assert resolved == plugin.resolve()
    assert not (home / ".hydracept" / "secrets.json").is_file()


def test_env_workspace(tmp_path: Path) -> None:
    checkout = tmp_path / "game"
    checkout.mkdir()
    resolved = resolve_mcp_workspace(
        None,
        cwd=tmp_path,
        env={"HYDRACEPT_WORKSPACE": str(checkout)},
    )
    assert resolved == checkout.resolve()


def test_walks_up_from_project_plugin_dir(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    checkout = tmp_path / "game"
    plugin = checkout / ".cursor" / "plugins" / "hydracept"
    plugin.mkdir(parents=True)
    (checkout / ".git").mkdir()
    (checkout / ".hydracept").mkdir()
    (checkout / ".hydracept" / "secrets.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: home.resolve())
    resolved = resolve_mcp_workspace(None, cwd=plugin, env={})
    assert resolved == checkout.resolve()


def test_rejects_system32_without_env(tmp_path: Path) -> None:
    system32 = tmp_path / "Windows" / "System32"
    system32.mkdir(parents=True)
    assert is_unusable_mcp_cwd(system32)
    with pytest.raises(WorkspaceNotReadyError):
        resolve_mcp_workspace(None, cwd=system32, env={})


def test_rejects_bare_cwd_without_hydracept(tmp_path: Path) -> None:
    bare = tmp_path / "nowhere"
    bare.mkdir()
    with pytest.raises(WorkspaceNotReadyError):
        resolve_mcp_workspace(None, cwd=bare, env={})
