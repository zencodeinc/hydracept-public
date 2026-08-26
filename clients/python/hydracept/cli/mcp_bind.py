"""Bind project MCP configs to stdio `hydracept mcp serve` (ADR-021).

Coding agents in a checkout authenticate via `.hydracept/secrets.json`.
Hosted HTTP MCP is for clients with no project checkout. This module never
copies API keys into plugin userConfig.
"""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "bound": self.bound,
            "transport": self.transport,
            "projectConfig": list(self.project_config),
            "reloadRequired": self.reload_required,
            "hostedUrl": self.hosted_url,
            "useHostedWhen": self.use_hosted_when,
        }


def stdio_command() -> str:
    """Prefer `python` on PATH so project mcp.json stays portable across machines."""
    if shutil.which("python"):
        return "python"
    return sys.executable


def stdio_args(project_root: Path | str | None = None) -> list[str]:
    args = ["-m", "hydracept", "mcp", "serve"]
    if project_root is not None:
        args.extend(["--workspace", str(Path(project_root).resolve())])
    return args


def stdio_server_entry(*, vscode: bool = False, project_root: Path | str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "command": stdio_command(),
        "args": stdio_args(project_root),
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


def _upsert_stdio(
    servers: dict[str, Any],
    *,
    vscode: bool = False,
    project_root: Path | str | None = None,
) -> dict[str, Any]:
    merged = dict(servers)
    merged.pop("hydracept-local", None)
    merged["hydracept"] = stdio_server_entry(vscode=vscode, project_root=project_root)
    return merged


def _merge_mcp_servers_file(
    path: Path,
    *,
    servers_key: str,
    vscode: bool = False,
    project_root: Path | str | None = None,
) -> bool:
    payload = _read_json(path)
    existing = payload.get(servers_key)
    servers = dict(existing) if isinstance(existing, dict) else {}
    updated = _upsert_stdio(servers, vscode=vscode, project_root=project_root)
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
        if _is_stdio_hydracept(servers.get("hydracept")):
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

    targets: list[tuple[Path, str, bool, bool]] = [
        (root / ".cursor" / "mcp.json", "mcpServers", False, True),
        (root / ".mcp.json", "mcpServers", False, True),
    ]
    if (root / ".vscode").is_dir():
        targets.append((root / ".vscode" / "mcp.json", "servers", True, True))

    plugin_targets: list[tuple[Path, str, bool]] = [
        (root / ".cursor" / "plugins" / "hydracept" / "mcp.json", "mcpServers", False),
        (root / ".claude" / "plugins" / "hydracept" / ".mcp.json", "mcpServers", False),
        (root / ".agents" / "plugins" / "hydracept" / "mcp_config.json", "servers", False),
    ]
    for path, key, vscode in plugin_targets:
        if path.is_file() or path.parent.is_dir():
            targets.append((path, key, vscode, False))

    for path, key, vscode, always in targets:
        if not always and not path.is_file() and not path.parent.is_dir():
            continue
        changed = _merge_mcp_servers_file(
            path, servers_key=key, vscode=vscode, project_root=root
        )
        rel = _rel(root, path)
        configs.append(rel)
        if changed:
            written.append(rel)

    return McpBindResult(
        bound=bool(configs),
        transport="stdio",
        project_config=tuple(configs),
        reload_required=bool(written),
        written=tuple(written),
    )
