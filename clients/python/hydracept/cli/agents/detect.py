"""Detect installed coding-agent hosts in the workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import os

from hydracept.cli.agent_status import manifest_path
from hydracept.cli.workspace import read_json as _read_json

HOSTS = ("cursor", "claude", "antigravity")


@dataclass(frozen=True)
class HostDetection:
    host: str
    detected: bool
    reason: str


def _exists(path: Path) -> bool:
    return path.exists()


def _cursor_runtime_detected() -> bool:
    if os.environ.get("CURSOR_AGENT", "").strip():
        return True
    return os.environ.get("CURSOR_EXTENSION_HOST_ROLE") == "agent-exec"


def _claude_runtime_detected() -> bool:
    return bool(os.environ.get("CLAUDE_PROJECT_DIR", "").strip())


def detect_host(project_root: Path, host: str) -> HostDetection:
    root = project_root.resolve()
    if host == "cursor":
        if _cursor_runtime_detected():
            return HostDetection("cursor", True, "Running in Cursor agent (CURSOR_AGENT)")
        markers = [
            root / ".cursor",
            root / ".cursor-plugin",
            root / ".cursor" / "hooks.json",
        ]
        if any(_exists(path) for path in markers):
            return HostDetection("cursor", True, "Found .cursor workspace customization")
        return HostDetection("cursor", False, "No Cursor workspace markers")
    if host == "claude":
        if _claude_runtime_detected():
            return HostDetection("claude", True, "Running in Claude Code (CLAUDE_PROJECT_DIR)")
        markers = [
            root / ".claude",
            root / ".claude-plugin",
        ]
        if any(_exists(path) for path in markers):
            return HostDetection("claude", True, "Found Claude Code workspace customization")
        return HostDetection("claude", False, "No Claude Code workspace markers")
    if host == "antigravity":
        markers = [
            root / ".agents",
            root / ".agents" / "plugins",
        ]
        if any(_exists(path) for path in markers):
            return HostDetection("antigravity", True, "Found .agents workspace")
        return HostDetection("antigravity", False, "No Antigravity .agents workspace")
    raise ValueError(f"Unknown host: {host}")


def detect_all(project_root: Path) -> dict[str, Any]:
    manifest = _read_json(manifest_path(project_root))
    installed = set(manifest.get("hosts") or [])
    hosts: dict[str, Any] = {}
    for host in HOSTS:
        detection = detect_host(project_root, host)
        hosts[host] = {
            "detected": detection.detected,
            "installed": host in installed,
            "reason": detection.reason,
        }
    return {"hosts": hosts, "manifestPresent": bool(manifest)}


def auto_hosts(project_root: Path) -> list[str]:
    manifest = _read_json(manifest_path(project_root))
    installed = {str(item) for item in (manifest.get("hosts") or [])}
    selected: list[str] = []
    for host in HOSTS:
        if detect_host(project_root, host).detected or host in installed:
            selected.append(host)
    return selected
