"""Independently observable consumer version facts (CLI, MCP, API, agent pack)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hydracept import __version__ as installed_client_version
from hydracept.cli.agent_status import manifest_path
from hydracept.cli.mcp_bind import inspect_workspace_mcp
from hydracept.cli.package_provenance import package_provenance
from hydracept.cli.workspace import read_json


def consumer_version_report(project_root: Path | None = None) -> dict[str, Any]:
    """Package provenance plus workspace consumer versions when a checkout is present."""
    payload: dict[str, Any] = dict(package_provenance())
    if project_root is None:
        return payload
    root = Path(project_root)
    if (root / ".hydracept").is_dir():
        payload["consumer"] = consumer_versions(root)
    return payload


def consumer_versions(
    project_root: Path,
    *,
    session: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Return independently named version facts a consumer can quote."""
    bind = inspect_workspace_mcp(project_root)
    manifest = read_json(manifest_path(project_root))
    pack = str(manifest.get("version") or manifest.get("agentPackVersion") or "").strip()
    api_revision = ""
    if isinstance(session, dict):
        api_revision = str(session.get("routeBundleVersion") or session.get("apiRevision") or "").strip()
    binding_version = bind.generation or str(installed_client_version)
    return {
        "installedClient": str(installed_client_version),
        "mcpBindingVersion": binding_version,
        "mcpRuntimeState": bind.readiness(),
        "runningMcp": binding_version,
        "apiRevision": api_revision or "unavailable",
        "agentPack": pack or "not_installed",
    }
