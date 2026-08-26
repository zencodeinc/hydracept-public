"""Workspace identity is absolute inside a bound checkout."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hydracept.cli.project import repair_workspace_identity, write_project_binding
from hydracept.cli.workspace import (
    CliOverrides,
    WorkspaceIdentityError,
    WorkspaceState,
    resolve_workspace,
    workspace_state,
)


def test_env_only_workspace_reaches_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HYDRACEPT_API_KEY", "test-key")
    monkeypatch.setenv("HYDRACEPT_PROJECT", "cpr_env")
    monkeypatch.setenv("HYDRACEPT_API_URL", "https://api.example.com")
    resolved = resolve_workspace(tmp_path)
    assert resolved is not None
    assert resolved.project_id == "cpr_env"
    assert workspace_state(resolved) == WorkspaceState.READY


def test_resolve_workspace_accepts_string_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HYDRACEPT_API_KEY", "test-key")
    monkeypatch.setenv("HYDRACEPT_PROJECT", "cpr_env")
    resolved = resolve_workspace(str(tmp_path))  # type: ignore[arg-type]
    assert resolved is not None
    assert resolved.project_id == "cpr_env"


def test_legacy_project_env_warns_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import warnings

    monkeypatch.delenv("HYDRACEPT_PROJECT", raising=False)
    monkeypatch.setenv("HYDRACEPT_API_KEY", "test-key")
    monkeypatch.setenv("HYDRACEPT_PROJECT_ID", "cpr_legacy")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        resolved = resolve_workspace(tmp_path)
    assert resolved is not None
    assert resolved.project_id == "cpr_legacy"
    assert any("HYDRACEPT_PROJECT_ID is deprecated" in str(w.message) for w in caught)


def test_cli_project_does_not_override_project_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HYDRACEPT_API_KEY", "test-key")
    write_project_binding(
        tmp_path,
        {"projectId": "cpr_file", "apiOrigin": "https://api.example.com"},
    )
    resolved = resolve_workspace(
        tmp_path,
        overrides=CliOverrides(project_id="cpr_cli"),
    )
    assert resolved is not None
    assert resolved.project_id == "cpr_file"


def test_env_disagrees_with_project_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HYDRACEPT_API_KEY", "test-key")
    monkeypatch.setenv("HYDRACEPT_PROJECT", "cpr_env")
    write_project_binding(tmp_path, {"projectId": "cpr_file", "apiOrigin": "https://api.example.com"})
    with pytest.raises(WorkspaceIdentityError):
        resolve_workspace(tmp_path)


def test_repair_migrates_legacy_config(tmp_path: Path) -> None:
    cfg = tmp_path / ".hydracept"
    cfg.mkdir()
    (cfg / "config.json").write_text(
        json.dumps({"projectId": "cpr_legacy", "apiBaseUrl": "https://api.example.com", "theme": "dark"}),
        encoding="utf-8",
    )
    assert repair_workspace_identity(tmp_path) == "migrated_config"
    binding = json.loads((cfg / "project.json").read_text(encoding="utf-8"))
    assert binding["projectId"] == "cpr_legacy"
    config = json.loads((cfg / "config.json").read_text(encoding="utf-8"))
    assert "projectId" not in config
    assert config.get("theme") == "dark"


def test_repair_disagreement_without_remote_fails(tmp_path: Path) -> None:
    write_project_binding(tmp_path, {"projectId": "cpr_a"})
    cfg = tmp_path / ".hydracept" / "config.json"
    cfg.write_text(json.dumps({"projectId": "cpr_b"}), encoding="utf-8")
    with pytest.raises(WorkspaceIdentityError):
        repair_workspace_identity(tmp_path)
    repair_workspace_identity(tmp_path, remote_project_id="cpr_a")
    config = json.loads(cfg.read_text(encoding="utf-8"))
    assert "projectId" not in config
