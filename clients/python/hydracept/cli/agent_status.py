"""Local-only agent readiness status for hooks and MCP (ADR-021)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from hydracept.cli.onboarding_next import credential_setup_next_steps
from hydracept.cli.session_store import load_session
from hydracept.cli.workspace import (
    ResolvedWorkspace,
    WorkspaceState,
    config_path,
    read_json,
    resolve_workspace,
    secrets_path,
    workspace_state,
)

AGENT_PACK_VERSION = "0.1.1"
STATUS_CACHE_NAME = "agent-status.json"
MANIFEST_NAME = "agent-pack.manifest.json"


def _config_dir(project_root: Path) -> Path:
    return project_root / ".hydracept"


def status_cache_path(project_root: Path) -> Path:
    return _config_dir(project_root) / STATUS_CACHE_NAME


def manifest_path(project_root: Path) -> Path:
    return _config_dir(project_root) / MANIFEST_NAME


def _read_manifest(project_root: Path) -> dict[str, Any]:
    return read_json(manifest_path(project_root))


def _credential_present(project_root: Path) -> bool:
    secrets = read_json(secrets_path(project_root))
    return bool(str(secrets.get("apiKey") or secrets.get("token") or "").strip())


def _installed_hosts(manifest: dict[str, Any]) -> list[str]:
    hosts = manifest.get("hosts") or manifest.get("installed") or []
    if isinstance(hosts, dict):
        return sorted(str(key) for key, enabled in hosts.items() if enabled)
    if isinstance(hosts, list):
        return sorted(str(item) for item in hosts)
    return []


def _load_cache(project_root: Path) -> dict[str, Any]:
    return read_json(status_cache_path(project_root))


def _write_cache(project_root: Path, payload: dict[str, Any]) -> None:
    path = status_cache_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def agent_context_cache_path(project_root: Path) -> Path:
    return _config_dir(project_root) / "agent-context.json"


def _capability_keys_from_context(payload: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for item in payload.get("capabilities") or []:
        if isinstance(item, dict):
            key = item.get("key") or item.get("capabilityKey")
            if key:
                keys.add(str(key))
    return keys


def refresh_agent_context_cache(
    project_root: Path,
    api_url: str,
    *,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Overwrite .hydracept/agent-context.json from live GET /v1/agent-context."""
    response = httpx.get(f"{api_url.rstrip('/')}/v1/agent-context", timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    path = agent_context_cache_path(project_root)
    previous = read_json(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    old_keys = _capability_keys_from_context(previous)
    new_keys = _capability_keys_from_context(payload)
    added = sorted(new_keys - old_keys)
    return {
        "path": str(path),
        "stale": bool(old_keys) and old_keys != new_keys,
        "capabilityCount": len(new_keys),
        "addedKeys": added,
    }


def _refresh_network(workspace: ResolvedWorkspace, *, timeout: float = 10.0) -> dict[str, Any]:
    result: dict[str, Any] = {"reachable": False, "authenticated": False}
    try:
        health = httpx.get(f"{workspace.api_url}/healthz", timeout=timeout)
        result["reachable"] = health.status_code == 200
    except httpx.HTTPError as exc:
        result["error"] = str(exc)
        return result
    try:
        response = httpx.get(
            f"{workspace.api_url}/v1/diagnostics/session",
            headers={
                "Authorization": f"Bearer {workspace.token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        result["authenticated"] = response.status_code == 200
        if response.status_code == 200:
            result["session"] = response.json()
    except httpx.HTTPError as exc:
        result["error"] = str(exc)
    return result


def build_agent_status(
    project_root: Path,
    *,
    refresh: bool = False,
) -> dict[str, Any]:
    """Build local agent-status payload. Network only when refresh=True."""
    resolved = resolve_workspace(project_root)
    state = workspace_state(resolved)
    config = read_json(config_path(project_root))
    manifest = _read_manifest(project_root)
    cache = _load_cache(project_root)

    payload: dict[str, Any] = {
        "configured": state != WorkspaceState.UNCONFIGURED,
        "ready": state == WorkspaceState.READY,
        "workspaceState": state.value,
        "workspaceRoot": str(Path(project_root).resolve()),
        "credentialPresent": _credential_present(project_root),
        "sessionPresent": load_session() is not None,
        "projectId": (resolved.project_id if resolved else "") or str(config.get("projectId") or ""),
        "environment": (resolved.environment if resolved else "") or str(config.get("environment") or ""),
        "apiUrl": (resolved.api_url if resolved else "") or str(config.get("apiBaseUrl") or ""),
        "agentPackVersion": str(manifest.get("version") or AGENT_PACK_VERSION),
        "agentPackInstalled": bool(manifest),
        "installedHosts": _installed_hosts(manifest),
        "lastVerifiedAt": cache.get("lastVerifiedAt"),
    }
    api_url = str(payload.get("apiUrl") or "https://api.hydracept.com").rstrip("/")
    from hydracept.cli.mcp_bind import inspect_workspace_mcp

    bind = inspect_workspace_mcp(project_root)
    payload["mcp"] = {
        "hostedUrl": f"{api_url}/mcp",
        "stdioCommand": "python -m hydracept mcp serve --workspace ${workspaceFolder}",
        "bindCommand": "python -m hydracept mcp bind",
        "note": (
            "In a project checkout, stdio MCP is the default after init/doctor/mcp bind. "
            "If hydracept_* tools are missing, skip hosted discovery; reload MCP once "
            "if reloadRequired is true. Hosted MCP is for clients with no checkout. "
            "Do not treat .hydracept/agent-context.json as the live catalog — "
            "run `python -m hydracept doctor` or `python -m hydracept agent-context`."
        ),
        **bind.to_dict(),
    }
    next_steps = credential_setup_next_steps(project_root)
    if next_steps:
        payload["nextSteps"] = next_steps

    if refresh and resolved is not None:
        network = _refresh_network(resolved)
        payload["network"] = network
        if network.get("reachable"):
            try:
                payload["agentContextCache"] = refresh_agent_context_cache(
                    project_root, str(payload["apiUrl"])
                )
            except httpx.HTTPError as exc:
                payload["agentContextCache"] = {"error": str(exc)}
        if network.get("reachable") and network.get("authenticated"):
            payload["lastVerifiedAt"] = datetime.now(timezone.utc).isoformat()
            _write_cache(
                project_root,
                {
                    "lastVerifiedAt": payload["lastVerifiedAt"],
                    "workspaceState": state.value,
                },
            )
    return payload
