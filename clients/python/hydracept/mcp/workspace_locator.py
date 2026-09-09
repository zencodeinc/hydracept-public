"""Resolve the project checkout for stdio MCP.

Cursor plugin MCP does not start with cwd = the workspace. Never treat the
user home session store (~/.hydracept/session.json) as a project.
"""

from __future__ import annotations

import os
from pathlib import Path

_WALK_UP_MAX = 8
_WORKSPACE_ENV_KEYS = (
    "HYDRACEPT_WORKSPACE",
    "CURSOR_PROJECT_DIR",
    "VSCODE_CWD",
)
CURSOR_WORKSPACE_PLACEHOLDER = "${workspaceFolder}"

_WINDOWS_SYSTEM_PARTS = frozenset(
    {
        "windows",
        "system32",
        "syswow64",
        "program files",
        "program files (x86)",
        "programdata",
    }
)


def is_unexpanded_placeholder(value: Path | str | None) -> bool:
    if value is None:
        return False
    text = str(value)
    return "${" in text or text.strip() == CURSOR_WORKSPACE_PLACEHOLDER


def is_user_home(path: Path | str | None) -> bool:
    if path is None:
        return False
    try:
        return Path(path).resolve() == Path.home().resolve()
    except OSError:
        return False


def is_cursor_plugin_dir(path: Path) -> bool:
    parts = [part.lower() for part in path.resolve().parts]
    for index in range(len(parts) - 1):
        if parts[index] in {".cursor", ".claude", ".agents"} and parts[index + 1] == "plugins":
            return True
    return False


def is_unusable_mcp_cwd(path: Path | str) -> bool:
    """True when MCP likely started with a host launcher cwd (e.g. System32)."""
    try:
        resolved = Path(path).resolve()
    except OSError:
        return True
    parts = [part.lower() for part in resolved.parts]
    if any(part in _WINDOWS_SYSTEM_PARTS for part in parts):
        return True
    unix_roots = (("/",), ("/", "usr"), ("/", "bin"), ("/", "sbin"))
    if tuple(parts) in unix_roots:
        return True
    if len(parts) >= 3 and parts[0] == "/" and parts[1] == "usr" and parts[2] in {
        "bin",
        "sbin",
        "lib",
        "libexec",
        "share",
    }:
        return True
    return False


def _has_project_secrets(root: Path) -> bool:
    secrets = root / ".hydracept" / "secrets.json"
    return secrets.is_file()


def _has_project_binding(root: Path) -> bool:
    return (root / ".hydracept" / "project.json").is_file()


def _bounded_walk_up(start: Path) -> Path | None:
    current = start.resolve()
    home = Path.home().resolve()
    for _ in range(_WALK_UP_MAX):
        if current == home:
            return None
        if is_cursor_plugin_dir(current):
            current = current.parent
            continue
        if _has_project_secrets(current) or _has_project_binding(current):
            return current
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _from_env(env: dict[str, str]) -> Path | None:
    for key in _WORKSPACE_ENV_KEYS:
        raw = str(env.get(key) or "").strip()
        if not raw or is_unexpanded_placeholder(raw):
            continue
        path = Path(raw)
        if path.is_dir() and not is_user_home(path) and not is_cursor_plugin_dir(path):
            return path.resolve()
    return None


def _unresolved_workspace_error() -> Exception:
    from hydracept.cli.workspace import WorkspaceNotReadyError

    return WorkspaceNotReadyError(
        "Could not resolve Hydracept workspace for MCP. "
        "Set HYDRACEPT_WORKSPACE in the MCP server env (Cursor expands "
        f"{CURSOR_WORKSPACE_PLACEHOLDER} there even when --workspace is not expanded), "
        "or run `python -m hydracept mcp bind` in the project checkout and reload MCP."
    )


def _acceptable_fallback(root: Path) -> bool:
    if _has_project_secrets(root) or _has_project_binding(root):
        return True
    return (root / ".git").is_dir()


def _maybe_attest(root: Path, *, source: str, env: dict[str, str]) -> Path:
    """Publish a lease only for configured MCP launches, not locator library calls."""
    if str(env.get("HYDRACEPT_MCP_GENERATION") or "").strip():
        from hydracept.mcp.runtime_binding import attest_runtime_binding

        attest_runtime_binding(root, source=source, env=env)
    return root


def resolve_mcp_workspace(
    explicit: Path | str | None = None,
    *,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
) -> Path:
    """Return the checkout MCP should read secrets from.

    Precedence: --workspace (expanded) → env → walk-up from cwd. Never latches
    onto the user home session store. Configured MCP launches also publish a
    non-secret runtime lease so CLI status can attest the live checkout rather
    than infer it from files on disk.
    """
    environ = env if env is not None else dict(os.environ)
    if explicit is not None and not is_unexpanded_placeholder(explicit):
        path = Path(explicit)
        if path.is_dir():
            return _maybe_attest(path.resolve(), source="explicit", env=environ)
    from_env = _from_env(environ)
    if from_env is not None:
        return _maybe_attest(from_env, source="environment", env=environ)
    start = Path(cwd) if cwd is not None else Path.cwd()
    found = _bounded_walk_up(start)
    if found is not None:
        return _maybe_attest(found, source="walk_up", env=environ)
    fallback = start.resolve()
    if is_user_home(fallback) or is_cursor_plugin_dir(fallback):
        return fallback
    if is_unusable_mcp_cwd(fallback) or not _acceptable_fallback(fallback):
        raise _unresolved_workspace_error()
    return _maybe_attest(fallback, source="fallback", env=environ)
