"""Bind project MCP configs to stdio `hydracept mcp serve` (ADR-021).

Coding agents in a checkout authenticate via `.hydracept/secrets.json`.
Hosted HTTP MCP is for clients with no project checkout. This module never
copies API keys into plugin userConfig.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hydracept.mcp.workspace_locator import is_user_home

HOSTED_MCP_URL = "https://api.hydracept.com/mcp"
USE_HOSTED_WHEN = (
    "No project checkout (ChatGPT, remote MCP clients, MCP Registry). "
    "In a git repo, use stdio after `python -m hydracept init` — do not copy "
    "the workspace key into Plugins → Configure."
)


@dataclass(frozen=True)
class McpBindResult:
    bound: bool
    transport: str
    project_config: tuple[str, ...]
    reload_required: bool
    hosted_url: str = HOSTED_MCP_URL
    use_hosted_when: str = USE_HOSTED_WHEN
    written: tuple[str, ...] = ()
    generation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "bound": self.bound,
            "transport": self.transport,
            "projectConfig": list(self.project_config),
            "reloadRequired": self.reload_required,
            "hostedUrl": self.hosted_url,
            "useHostedWhen": self.use_hosted_when,
            "generation": self.generation,
        }


def stdio_command() -> str:
    """Prefer `python` on PATH so project mcp.json stays portable across machines."""
    if shutil.which("python"):
        return "python"
    return sys.executable


CURSOR_WORKSPACE_PLACEHOLDER = "${workspaceFolder}"


def credential_fingerprint(project_root: Path | str | None) -> str:
    """Non-secret binding identity. Never writes secret bytes into mcp.json."""
    if project_root is None:
        return "none"
    secrets = _read_json(Path(project_root) / ".hydracept" / "secrets.json")
    token = str(secrets.get("apiKey") or secrets.get("token") or "").strip()
    if not token:
        return "none"
    return f"{len(token)}:{token[:4]}:{token[-4:]}"


def binding_generation(
    project_root: Path | str | None,
    args: list[str],
    *,
    fingerprint: str | None = None,
) -> str:
    root = str(Path(project_root).resolve()) if project_root is not None else ""
    cred = fingerprint if fingerprint is not None else credential_fingerprint(project_root)
    blob = json.dumps({"workspace": root, "cred": cred, "args": args}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def stdio_args(
    project_root: Path | str | None = None,
    *,
    cursor_placeholder: bool = False,
) -> list[str]:
    args = ["-m", "hydracept", "mcp", "serve"]
    if cursor_placeholder or project_root is None:
        args.extend(["--workspace", CURSOR_WORKSPACE_PLACEHOLDER])
    else:
        args.extend(["--workspace", str(Path(project_root).resolve())])
    return args


def cursor_host_mcp_targets() -> list[tuple[Path, str]]:
    """Configs Cursor actually launches (plugin + user-global), not project bind files.

    Skipped under pytest so unit tests do not rewrite the developer machine.
    """
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return []
    home = Path.home()
    return [
        (home / ".cursor" / "mcp.json", "mcpServers"),
        (home / ".cursor" / "plugins" / "local" / "hydracept" / "mcp.json", "mcpServers"),
        (home / ".cursor" / "plugins" / "hydracept" / "mcp.json", "mcpServers"),
    ]


def stdio_server_entry(
    *,
    vscode: bool = False,
    project_root: Path | str | None = None,
    cursor_placeholder: bool = False,
) -> dict[str, Any]:
    args = stdio_args(project_root, cursor_placeholder=cursor_placeholder)
    env: dict[str, str] = {
        "HYDRACEPT_MCP_GENERATION": binding_generation(project_root, args),
    }
    if cursor_placeholder or project_root is None:
        env["HYDRACEPT_WORKSPACE"] = CURSOR_WORKSPACE_PLACEHOLDER
    else:
        env["HYDRACEPT_WORKSPACE"] = str(Path(project_root).resolve())
    entry: dict[str, Any] = {
        "command": stdio_command(),
        "args": args,
        "env": env,
    }
    if vscode:
        entry["type"] = "stdio"
    return entry


def _rel(project_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> bool:
    text = json.dumps(payload, indent=2) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _is_stdio_hydracept(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    if str(entry.get("url") or "").strip():
        return False
    args = [str(part) for part in (entry.get("args") or [])]
    command = str(entry.get("command") or "")
    blob = " ".join([command, *args]).lower()
    return "hydracept" in blob and "serve" in blob and "-m" in args


def _is_hydracept_owned_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    if _is_stdio_hydracept(entry):
        return True
    return "api.hydracept.com/mcp" in str(entry.get("url") or "")


def _upsert_stdio(
    servers: dict[str, Any],
    *,
    vscode: bool = False,
    project_root: Path | str | None = None,
    cursor_placeholder: bool = False,
) -> dict[str, Any]:
    merged = dict(servers)
    merged.pop("hydracept-local", None)
    merged["hydracept"] = stdio_server_entry(
        vscode=vscode,
        project_root=project_root,
        cursor_placeholder=cursor_placeholder,
    )
    return merged


def _merge_mcp_servers_file(
    path: Path,
    *,
    servers_key: str,
    vscode: bool = False,
    project_root: Path | str | None = None,
    cursor_placeholder: bool = False,
) -> bool:
    payload = _read_json(path)
    existing = payload.get(servers_key)
    servers = dict(existing) if isinstance(existing, dict) else {}
    updated = _upsert_stdio(
        servers,
        vscode=vscode,
        project_root=project_root,
        cursor_placeholder=cursor_placeholder,
    )
    next_payload = dict(payload)
    next_payload[servers_key] = updated
    return _write_json(path, next_payload)


def _root(project_root: Path | str) -> Path:
    return Path(project_root).resolve()


def inspect_workspace_mcp(project_root: Path | str) -> McpBindResult:
    """Report whether project MCP configs already point at stdio Hydracept."""
    root = _root(project_root)
    configs: list[str] = []
    bound = False

    cursor = root / ".cursor" / "mcp.json"
    if cursor.is_file():
        servers = (_read_json(cursor).get("mcpServers") or {})
        if _is_stdio_hydracept(servers.get("hydracept") or servers.get("hydracept-project")):
            configs.append(_rel(root, cursor))
            bound = True

    claude = root / ".mcp.json"
    if claude.is_file():
        servers = (_read_json(claude).get("mcpServers") or {})
        if _is_stdio_hydracept(servers.get("hydracept")):
            configs.append(_rel(root, claude))
            bound = True

    vscode = root / ".vscode" / "mcp.json"
    if vscode.is_file():
        servers = (_read_json(vscode).get("servers") or {})
        if _is_stdio_hydracept(servers.get("hydracept")):
            configs.append(_rel(root, vscode))
            bound = True

    return McpBindResult(
        bound=bound,
        transport="stdio",
        project_config=tuple(configs),
        reload_required=False,
    )


def bind_workspace_mcp(project_root: Path | str) -> McpBindResult:
    """Write/merge project MCP configs so `hydracept` is stdio. Idempotent."""
    root = _root(project_root)
    written: list[str] = []
    configs: list[str] = []
    home_root = is_user_home(root)

    targets: list[tuple[Path, str, bool, bool, bool]] = []
    if not home_root:
        targets.extend(
            [
                (root / ".cursor" / "mcp.json", "mcpServers", False, True, True),
                (root / ".mcp.json", "mcpServers", False, True, False),
            ]
        )
        if (root / ".vscode").is_dir():
            targets.append((root / ".vscode" / "mcp.json", "servers", True, True, False))

        plugin_targets: list[tuple[Path, str, bool, bool]] = [
            (root / ".cursor" / "plugins" / "hydracept" / "mcp.json", "mcpServers", False, True),
            (root / ".claude" / "plugins" / "hydracept" / ".mcp.json", "mcpServers", False, False),
            (root / ".agents" / "plugins" / "hydracept" / "mcp_config.json", "servers", False, False),
        ]
        for path, key, vscode, cursor_placeholder in plugin_targets:
            if path.is_file() or path.parent.is_dir():
                targets.append((path, key, vscode, False, cursor_placeholder))

    for path, key in cursor_host_mcp_targets():
        if not path.is_file():
            continue
        payload = _read_json(path)
        servers = payload.get(key)
        existing = servers.get("hydracept") if isinstance(servers, dict) else None
        if existing is not None and not _is_hydracept_owned_entry(existing):
            continue
        targets.append((path, key, False, False, True))

    generation = ""
    for path, key, vscode, always, cursor_placeholder in targets:
        if not always and not path.is_file() and not path.parent.is_dir():
            continue
        changed = _merge_mcp_servers_file(
            path,
            servers_key=key,
            vscode=vscode,
            project_root=root,
            cursor_placeholder=cursor_placeholder,
        )
        rel = _rel(root, path)
        configs.append(rel)
        if changed:
            written.append(rel)
        if not generation:
            payload = _read_json(path)
            servers = payload.get(key) if isinstance(payload.get(key), dict) else {}
            env = (servers.get("hydracept") or {}).get("env") if isinstance(servers.get("hydracept"), dict) else {}
            generation = str((env or {}).get("HYDRACEPT_MCP_GENERATION") or "")

    return McpBindResult(
        bound=bool(configs),
        transport="stdio",
        project_config=tuple(configs),
        reload_required=bool(written),
        written=tuple(written),
        generation=generation,
    )


def user_apps_record_path() -> Path:
    return Path.home() / ".cursor" / "hydracept-user-apps.json"


PROJECT_SCOPE_APPS_SHADOW = "hydracept-project"


def user_apps_server_entry(project_root: Path | str) -> dict[str, Any]:
    """User/plugin MCP entry: absolute workspace, this interpreter, checkout PYTHONPATH."""
    root = Path(project_root).resolve()
    entry = stdio_server_entry(project_root=root, cursor_placeholder=False)
    entry["command"] = sys.executable
    env = dict(entry.get("env") or {})
    env["PYTHONPATH"] = str(root / "clients" / "python")
    env["HYDRACEPT_MCP_GENERATION"] = binding_generation(
        root,
        entry["args"],
        fingerprint=f"{credential_fingerprint(root)}:user-apps-shadow-v3",
    )
    entry["env"] = env
    return entry


def _user_apps_config_targets() -> list[tuple[Path, str]]:
    home = Path.home()
    targets = [
        (home / ".cursor" / "mcp.json", "mcpServers"),
        (home / ".cursor" / "plugins" / "local" / "hydracept" / "mcp.json", "mcpServers"),
    ]
    extra = home / ".cursor" / "plugins" / "hydracept" / "mcp.json"
    if extra.is_file() or extra.parent.is_dir():
        targets.append((extra, "mcpServers"))
    return targets


def _write_hydracept_server(path: Path, key: str, entry: dict[str, Any]) -> bool:
    payload = _read_json(path)
    servers = payload.get(key)
    if not isinstance(servers, dict):
        servers = {}
        payload[key] = servers
    servers["hydracept"] = entry
    return _write_json(path, payload)


def _sibling_primary_mcp(root: Path) -> Path | None:
    """If root is a git worktree, Cursor may still have the primary checkout open."""
    for parent in [root, *root.parents]:
        if parent.name.endswith(".worktrees"):
            repo = parent.name[: -len(".worktrees")]
            candidate = parent.parent / repo / ".cursor" / "mcp.json"
            return candidate if candidate.is_file() else None
    return None


def _shadow_project_hydracept(project_mcp: Path) -> bool:
    """Rename project hydracept so Cursor can Apps-read the user-global server."""
    if not project_mcp.is_file():
        return False
    payload = _read_json(project_mcp)
    servers = payload.get("mcpServers")
    if not isinstance(servers, dict) or "hydracept" not in servers:
        return False
    entry = servers.pop("hydracept")
    if PROJECT_SCOPE_APPS_SHADOW not in servers:
        servers[PROJECT_SCOPE_APPS_SHADOW] = entry
    payload["mcpServers"] = servers
    _write_json(project_mcp, payload)
    return True


def _restore_project_hydracept(project_mcp: Path) -> bool:
    if not project_mcp.is_file():
        return False
    payload = _read_json(project_mcp)
    servers = payload.get("mcpServers")
    if not isinstance(servers, dict) or "hydracept" in servers:
        return False
    shadow = servers.pop(PROJECT_SCOPE_APPS_SHADOW, None)
    if shadow is None:
        return False
    servers["hydracept"] = shadow
    payload["mcpServers"] = servers
    _write_json(project_mcp, payload)
    return True


def bind_user_apps_workaround(project_root: Path | str) -> dict[str, Any]:
    """Explicit Cursor global MCP bind with an absolute workspace. Never called by init/doctor."""
    root = _root(project_root)
    entry = user_apps_server_entry(root)
    written: list[str] = []
    for path, key in _user_apps_config_targets():
        _write_hydracept_server(path, key, entry)
        written.append(str(path))
    project_mcp = root / ".cursor" / "mcp.json"
    renamed_paths: list[str] = []
    for path in [project_mcp, _sibling_primary_mcp(root)]:
        if path is None:
            continue
        if _shadow_project_hydracept(path):
            renamed_paths.append(str(path))
    record = {
        "workspace": str(root.resolve()),
        "mcpJson": str(Path.home() / ".cursor" / "mcp.json"),
        "written": written,
        "projectMcpJson": str(project_mcp),
        "projectMcpJsons": renamed_paths,
        "projectMcpRenamed": bool(renamed_paths),
        "cleanup": "python -m hydracept mcp bind --user-apps-remove",
    }
    record_path = user_apps_record_path()
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def remove_user_apps_workaround() -> dict[str, Any]:
    record_path = user_apps_record_path()
    record = _read_json(record_path)
    removed = False
    placeholder = stdio_server_entry(cursor_placeholder=True)
    user_mcp = Path.home() / ".cursor" / "mcp.json"
    payload = _read_json(user_mcp)
    servers = payload.get("mcpServers")
    if isinstance(servers, dict) and "hydracept" in servers:
        entry = servers.get("hydracept")
        if _is_hydracept_owned_entry(entry):
            servers.pop("hydracept", None)
            payload["mcpServers"] = servers
            _write_json(user_mcp, payload)
            removed = True
    for path, key in _user_apps_config_targets():
        if path == user_mcp:
            continue
        if not path.is_file():
            continue
        plugin_payload = _read_json(path)
        plugin_servers = plugin_payload.get(key)
        if isinstance(plugin_servers, dict) and "hydracept" in plugin_servers:
            plugin_servers["hydracept"] = placeholder
            plugin_payload[key] = plugin_servers
            _write_json(path, plugin_payload)
    for raw in record.get("projectMcpJsons") or [record.get("projectMcpJson")]:
        project_mcp = Path(str(raw or ""))
        if project_mcp.is_file():
            _restore_project_hydracept(project_mcp)
    if record_path.is_file():
        record_path.unlink()
    return {"removed": removed, "record": record}
