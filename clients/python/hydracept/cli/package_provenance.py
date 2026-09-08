"""Diagnose whether the running hydracept module is a published package."""

from __future__ import annotations

import json
import sys
from importlib import metadata
from pathlib import Path
from typing import Any, Literal

DistributionSource = Literal["installed-package", "editable-install", "source-checkout", "unknown"]


def _package_root() -> Path:
    import hydracept

    return Path(hydracept.__file__).resolve().parent


def _read_direct_url(dist: metadata.Distribution) -> dict[str, Any] | None:
    try:
        raw = dist.read_text("direct_url.json")
    except (FileNotFoundError, OSError):
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _is_editable(dist: metadata.Distribution | None, package_root: Path) -> bool:
    if dist is None:
        return False
    if not _distribution_covers(dist, package_root):
        return False
    direct = _read_direct_url(dist)
    if isinstance(direct, dict):
        dir_info = direct.get("dir_info")
        if isinstance(dir_info, dict) and dir_info.get("editable"):
            return True
    try:
        located = Path(str(dist.locate_file("")))
    except Exception:
        return False
    return any(path.name.endswith(".egg-link") for path in located.glob("*.egg-link"))


def _distribution_covers(dist: metadata.Distribution, package_root: Path) -> bool:
    try:
        located = Path(str(dist.locate_file(""))).resolve()
    except Exception:
        return False
    root = package_root.resolve()
    try:
        root.relative_to(located)
        return True
    except ValueError:
        try:
            located.relative_to(root)
            return True
        except ValueError:
            return located == root


def _looks_like_source_checkout(package_root: Path) -> bool:
    for parent in (package_root, *package_root.parents):
        architecture = parent / "architecture" / "pricing-catalog.yaml"
        clients_python = parent / "clients" / "python" / "pyproject.toml"
        if architecture.is_file() and clients_python.is_file():
            return True
        if parent.name.lower() in {"hydracept.worktrees", "hydracept"} and architecture.is_file():
            return True
    lowered = str(package_root).replace("\\", "/").lower()
    return "/clients/python/hydracept" in lowered or "\\clients\\python\\hydracept" in lowered.lower()


def classify_distribution(package_root: Path | None = None) -> DistributionSource:
    root = package_root or _package_root()
    dist: metadata.Distribution | None
    try:
        dist = metadata.distribution("hydracept")
    except metadata.PackageNotFoundError:
        dist = None
    parts = {part.lower() for part in root.parts}
    in_site = "site-packages" in parts or "dist-packages" in parts
    if in_site:
        return "installed-package"
    if dist is not None and _is_editable(dist, root):
        return "editable-install"
    if _looks_like_source_checkout(root):
        return "source-checkout"
    if dist is not None and _distribution_covers(dist, root):
        return "installed-package"
    return "unknown"


def package_provenance() -> dict[str, Any]:
    import hydracept

    package_root = Path(hydracept.__file__).resolve().parent
    version = str(getattr(hydracept, "__version__", "") or "")
    dist_name = "hydracept"
    dist_version = version
    try:
        dist = metadata.distribution("hydracept")
        dist_name = dist.metadata["Name"] or dist_name
        dist_version = dist.version or dist_version
    except metadata.PackageNotFoundError:
        dist = None
    source = classify_distribution(package_root)
    return {
        "version": version or dist_version or "0.0.0+local",
        "packagePath": str(package_root),
        "moduleFile": str(Path(hydracept.__file__).resolve()),
        "python": sys.executable,
        "distribution": {
            "name": dist_name,
            "version": dist_version,
            "source": source,
        },
    }


def points_at_repository(package_path: str, repository_roots: list[Path]) -> bool:
    resolved = Path(package_path).resolve()
    for root in repository_roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    lowered = str(resolved).replace("\\", "/").lower()
    return "hydracept.worktrees" in lowered
