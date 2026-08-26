"""Uninstall Hydracept Agent Pack using the ownership manifest."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hydracept.cli.agent_status import MANIFEST_NAME


@dataclass
class UninstallResult:
    removed: list[str]
    hosts: list[str]


def _manifest_path(project_root: Path) -> Path:
    return project_root / ".hydracept" / MANIFEST_NAME


def uninstall_agent_pack(
    project_root: Path,
    *,
    host: str | None = None,
    auto: bool = False,
) -> UninstallResult:
    manifest_file = _manifest_path(project_root)
    if not manifest_file.is_file():
        return UninstallResult(removed=[], hosts=[])

    manifest: dict[str, Any] = json.loads(manifest_file.read_text(encoding="utf-8"))
    owned = dict(manifest.get("ownedFiles") or {})
    hosts = list(manifest.get("hosts") or owned.keys())
    if auto:
        targets = hosts
    elif host:
        targets = [host]
    else:
        raise ValueError("Specify host or --auto")

    removed: list[str] = []
    for name in targets:
        for path_str in owned.get(name, []):
            path = Path(path_str)
            if path.is_file():
                path.unlink()
                removed.append(str(path))
            elif path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
                removed.append(str(path))
        owned.pop(name, None)
        if name in hosts:
            hosts.remove(name)

    if owned:
        manifest["ownedFiles"] = owned
        manifest["hosts"] = sorted(hosts)
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    else:
        manifest_file.unlink(missing_ok=True)

    plugin_dirs = [
        project_root / ".cursor" / "plugins" / "hydracept",
        project_root / ".claude" / "plugins" / "hydracept",
        project_root / ".agents" / "plugins" / "hydracept",
    ]
    for directory in plugin_dirs:
        if directory.is_dir() and not any(directory.rglob("*")):
            shutil.rmtree(directory, ignore_errors=True)

    return UninstallResult(removed=removed, hosts=targets)
