"""Tests for suggested project name resolution."""

from __future__ import annotations

from pathlib import Path

from hydracept.cli.project import looks_like_path, resolve_suggested_project_name


def test_looks_like_path_detects_windows_paths() -> None:
    assert looks_like_path("D:\\foo\\bar\\my-game")
    assert not looks_like_path("Key And Sigil")


def test_resolve_suggested_project_name_uses_folder(tmp_path: Path) -> None:
    project_root = tmp_path / "Key And Sigil"
    project_root.mkdir()
    assert resolve_suggested_project_name(project_root, {}) == "Key And Sigil"


def test_resolve_suggested_project_name_ignores_path_like_binding(tmp_path: Path) -> None:
    project_root = tmp_path / "my-game"
    project_root.mkdir()
    binding = {"projectName": "D:\\foo\\bar\\my-game"}
    assert resolve_suggested_project_name(project_root, binding) == "my-game"
