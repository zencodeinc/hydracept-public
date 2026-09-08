"""Unity UPM install helper."""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_UNITY_PACKAGE_URL = (
    "https://github.com/zencodeinc/hydracept-public.git?path=/packages/unity#v0.1.0"
)
PACKAGE_NAME = "com.hydracept.unity"


class UnityInstallError(Exception):
    pass


def is_unity_project(project_root: Path) -> bool:
    manifest = project_root / "Packages" / "manifest.json"
    assets = project_root / "Assets"
    settings = project_root / "ProjectSettings"
    return manifest.is_file() and assets.is_dir() and settings.is_dir()


def package_url(version: str | None = None) -> str:
    if not version:
        return DEFAULT_UNITY_PACKAGE_URL
    base = DEFAULT_UNITY_PACKAGE_URL.rsplit("#", 1)[0]
    return f"{base}#v{version.lstrip('v')}"


def install_unity_package(
    project_root: Path,
    *,
    version: str | None = None,
) -> bool:
    """Add Hydracept UPM dependency to Packages/manifest.json. Returns True if changed."""
    if not is_unity_project(project_root):
        raise UnityInstallError(
            "Not a Unity project — expected Packages/manifest.json, Assets/, and ProjectSettings/."
        )

    manifest_path = project_root / "Packages" / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UnityInstallError(f"Malformed Packages/manifest.json: {exc}") from exc

    dependencies = manifest.setdefault("dependencies", {})
    if not isinstance(dependencies, dict):
        raise UnityInstallError("Packages/manifest.json dependencies must be an object.")

    target = package_url(version)
    existing = dependencies.get(PACKAGE_NAME)
    if existing == target:
        return False

    dependencies[PACKAGE_NAME] = target
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return True
