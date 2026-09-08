"""Render Agent Pack host adapter files from bundled templates."""

from __future__ import annotations

import json
import shutil
import sys
from importlib import resources
from pathlib import Path
from typing import Any

from hydracept.cli.agent_status import AGENT_PACK_VERSION, MANIFEST_NAME
from hydracept.cli.mcp_bind import stdio_args, stdio_command

HOSTS = ("cursor", "claude", "antigravity")
SKILL_NAMES = (
    "hydracept",
    "hydracept-setup",
    "hydracept-smoke",
    "hydracept-image",
    "hydracept-sheet",
)


def _package_data_root() -> Path:
    return Path(resources.files("hydracept")) / "data" / "agents"


def _public_template_root(repo_root: Path | None) -> Path:
    if repo_root is not None:
        candidate = repo_root / "public" / "agents"
        if candidate.is_dir():
            return candidate
    return _package_data_root() / "templates"


def _mcp_command(*, cursor: bool = False, project_root: Path | None = None) -> tuple[str, list[str]]:
    return stdio_command(), stdio_args(project_root, cursor_placeholder=cursor)


def _session_start_hook() -> dict[str, Any]:
    return {
        "command": [sys.executable, "-m", "hydracept", "agent-status", "--json"],
        "timeoutSeconds": 5,
    }


def _copy_skills(target_dir: Path) -> list[str]:
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    source = _package_data_root() / "skills"
    for skill in SKILL_NAMES:
        src = source / skill / "SKILL.md"
        if not src.is_file():
            continue
        dest_dir = target_dir / skill
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "SKILL.md"
        shutil.copyfile(src, dest)
        written.append(str(dest))
    return written


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def render_cursor(project_root: Path, repo_root: Path | None = None) -> list[str]:
    root = project_root.resolve()
    template_root = _public_template_root(repo_root) / "cursor"
    plugin_root = root / ".cursor" / "plugins" / "hydracept"
    written = _copy_skills(plugin_root / "skills")
    for rel in (
        ".cursor-plugin/plugin.json",
        "hooks/hooks.json",
        "mcp.json",
        "README.md",
        "assets/logo.png",
    ):
        src = template_root / rel
        if src.is_file():
            dest = plugin_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            written.append(str(dest))
    command, args = _mcp_command(cursor=True, project_root=root)
    _write_json(
        plugin_root / "mcp.json",
        {
            "mcpServers": {
                "hydracept": {
                    "command": command,
                    "args": args,
                }
            }
        },
    )
    _write_json(
        plugin_root / "hooks" / "hooks.json",
        {"sessionStart": [_session_start_hook()]},
    )
    return written


def render_claude(project_root: Path, repo_root: Path | None = None) -> list[str]:
    root = project_root.resolve()
    template_root = _public_template_root(repo_root) / "claude"
    plugin_root = root / ".claude" / "plugins" / "hydracept"
    written = _copy_skills(plugin_root / "skills")
    for rel in (".claude-plugin/plugin.json", "hooks/hooks.json", "README.md"):
        src = template_root / rel
        if src.is_file():
            dest = plugin_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            written.append(str(dest))
    command, args = _mcp_command(cursor=False, project_root=root)
    _write_json(
        plugin_root / ".mcp.json",
        {
            "mcpServers": {
                "hydracept": {
                    "command": command,
                    "args": args,
                }
            }
        },
    )
    _write_json(plugin_root / "hooks" / "hooks.json", {"sessionStart": [_session_start_hook()]})
    return written


def render_antigravity(project_root: Path, repo_root: Path | None = None) -> list[str]:
    root = project_root.resolve()
    template_root = _public_template_root(repo_root) / "antigravity"
    plugin_root = root / ".agents" / "plugins" / "hydracept"
    written = _copy_skills(plugin_root / "skills")
    for rel in ("plugin.json", "hooks.json", "mcp_config.json", "README.md"):
        src = template_root / rel
        if src.is_file():
            dest = plugin_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            written.append(str(dest))
    command, args = _mcp_command(cursor=False, project_root=root)
    _write_json(
        plugin_root / "mcp_config.json",
        {
            "servers": {
                "hydracept": {
                    "command": command,
                    "args": args,
                }
            }
        },
    )
    _write_json(plugin_root / "hooks.json", {"sessionStart": [_session_start_hook()]})
    return written


RENDERERS = {
    "cursor": render_cursor,
    "claude": render_claude,
    "antigravity": render_antigravity,
}


def write_manifest(project_root: Path, host: str, files: list[str]) -> Path:
    manifest_path = project_root / ".hydracept" / MANIFEST_NAME
    existing: dict[str, Any] = {}
    if manifest_path.is_file():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    hosts = set(existing.get("hosts") or [])
    hosts.add(host)
    owned = dict(existing.get("ownedFiles") or {})
    owned[host] = files
    payload = {
        "schemaVersion": 1,
        "version": AGENT_PACK_VERSION,
        "hosts": sorted(hosts),
        "ownedFiles": owned,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path
