"""Safe `doctor --fix` — Hydracept-owned repairs only."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hydracept.cli.mcp_bind import (
    _is_stdio_hydracept,
    _read_json,
    bind_workspace_mcp,
    inspect_workspace_mcp,
)

HYDRACEPT_OWNED_MARKERS = (
    "python -m hydracept mcp serve",
    "https://api.hydracept.com/mcp",
)


@dataclass
class DoctorFixResult:
    repaired: list[str] = field(default_factory=list)
    blocked: list[dict[str, str]] = field(default_factory=list)
    reload_required: bool = False
    human_action_required: str | None = None
    spent: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "repaired": self.repaired,
            "repairBlocked": self.blocked,
            "reloadRequired": self.reload_required,
            "spent": self.spent,
        }
        if self.human_action_required:
            payload["humanActionRequired"] = self.human_action_required
        return payload


def _hydracept_owned_entry(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    if _is_stdio_hydracept(entry):
        return True
    url = str(entry.get("url") or "")
    return "api.hydracept.com/mcp" in url


def _user_modified_hydracept(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    if _hydracept_owned_entry(entry):
        return False
    blob = json.dumps(entry).lower()
    return "hydracept" in blob


def apply_doctor_fix(project_root: Path) -> DoctorFixResult:
    """Merge Hydracept MCP entry only. Never spend, choose a project, or overwrite peers."""
    root = Path(project_root).resolve()
    result = DoctorFixResult()
    targets = [
        (root / ".cursor" / "mcp.json", "mcpServers"),
        (root / ".mcp.json", "mcpServers"),
        (root / ".vscode" / "mcp.json", "servers"),
    ]
    blocked_any = False
    for path, key in targets:
        if not path.is_file():
            continue
        payload = _read_json(path)
        servers = payload.get(key)
        if not isinstance(servers, dict):
            continue
        existing = servers.get("hydracept")
        if existing is not None and _user_modified_hydracept(existing):
            result.blocked.append(
                {
                    "path": str(path.relative_to(root)) if path.is_relative_to(root) else str(path),
                    "reason": "user-modified hydracept MCP entry",
                }
            )
            blocked_any = True

    if blocked_any:
        result.human_action_required = "repair_blocked"
        inspected = inspect_workspace_mcp(root)
        result.reload_required = inspected.reload_required
        return result

    bind = bind_workspace_mcp(root)
    result.repaired = list(bind.written)
    result.reload_required = bind.reload_required
    if bind.reload_required:
        result.human_action_required = "reload_cursor"
    return result
