"""Tests for Unity UPM install helper."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hydracept.cli.integrations.unity import (
    PACKAGE_NAME,
    UnityInstallError,
    install_unity_package,
    is_unity_project,
)


def _write_unity_project(root: Path) -> None:
    (root / "Assets").mkdir()
    (root / "ProjectSettings").mkdir()
    manifest = {
        "dependencies": {
            "com.unity.modules.ui": "1.0.0",
        }
    }
    manifest_dir = root / "Packages"
    manifest_dir.mkdir()
    (manifest_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_is_unity_project(tmp_path: Path) -> None:
    _write_unity_project(tmp_path)
    assert is_unity_project(tmp_path) is True
    assert is_unity_project(tmp_path / "missing") is False


def test_install_unity_package_idempotent(tmp_path: Path) -> None:
    _write_unity_project(tmp_path)
    assert install_unity_package(tmp_path) is True
    assert install_unity_package(tmp_path) is False
    manifest = json.loads((tmp_path / "Packages" / "manifest.json").read_text(encoding="utf-8"))
    assert PACKAGE_NAME in manifest["dependencies"]


def test_install_unity_package_rejects_malformed(tmp_path: Path) -> None:
    (tmp_path / "Assets").mkdir()
    (tmp_path / "ProjectSettings").mkdir()
    (tmp_path / "Packages").mkdir()
    (tmp_path / "Packages" / "manifest.json").write_text("{", encoding="utf-8")
    with pytest.raises(UnityInstallError):
        install_unity_package(tmp_path)
