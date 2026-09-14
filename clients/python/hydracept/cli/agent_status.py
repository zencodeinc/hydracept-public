"""Local-only agent readiness status for hooks and MCP (ADR-021)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
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
AGENT_CONTEXT_MAX_AGE = timedelta(hours=6)


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
    for key in payload.get("featuredCapabilities") or []:
        if key:
            keys.add(str(key))
    return keys


def _context_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def inspect_agent_context_cache(project_root: Path) -> dict[str, Any]:
    """Local-only staleness of .hydracept/agent-context.json."""
    path = agent_context_cache_path(project_root)
    if not path.is_file():
        return {
            "path": str(path),
            "present": False,
            "stale": True,
            "reason": "missing",
        }
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return {
            "path": str(path),
            "present": False,
            "stale": True,
            "reason": "unreadable",
        }
    age = datetime.now(timezone.utc) - mtime
    stale = age > AGENT_CONTEXT_MAX_AGE
    payload = read_json(path)
    return {
        "path": str(path),
        "present": True,
        "stale": stale,
        "reason": "expired" if stale else "fresh",
        "ageSeconds": int(age.total_seconds()),
        "capabilityCount": len(_capability_keys_from_context(payload)),
        "contentHash": _context_fingerprint(payload) if payload else None,
    }


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
    if not isinstance(payload, dict):
        raise httpx.HTTPError("agent-context returned a non-object payload")
    live_keys = _capability_keys_from_context(payload)
    if not live_keys:
        raise httpx.HTTPError("agent-context catalog was empty")
    path = agent_context_cache_path(project_root)
    previous = read_json(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    old_keys = _capability_keys_from_context(previous)
    new_keys = live_keys
    added = sorted(new_keys - old_keys)
    previous_hash = _context_fingerprint(previous) if previous else None
    live_hash = _context_fingerprint(payload)
    return {
        "path": str(path),
        "stale": bool(previous) and previous_hash != live_hash,
        "capabilityCount": len(new_keys),
        "addedKeys": added,
        "contentHash": live_hash,
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
    from hydracept.cli.consumer_versions import consumer_version_report, consumer_versions

    versions = consumer_versions(project_root)
    payload["installedClientVersion"] = versions["installedClient"]
    payload["runningMcpVersion"] = versions["runningMcp"]
    payload["apiRevision"] = versions["apiRevision"]
    payload["versions"] = versions
    payload["packageProvenance"] = consumer_version_report(project_root)
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
    payload["agentContextCache"] = inspect_agent_context_cache(project_root)
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
            session = network.get("session") if isinstance(network.get("session"), dict) else None
            versions = consumer_versions(project_root, session=session)
            payload["versions"] = versions
            payload["runningMcpVersion"] = versions["runningMcp"]
            payload["apiRevision"] = versions["apiRevision"]
            _write_cache(
                project_root,
                {
                    "lastVerifiedAt": payload["lastVerifiedAt"],
                    "workspaceState": state.value,
                },
            )
    return payload
