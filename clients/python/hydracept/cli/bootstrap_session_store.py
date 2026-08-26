"""Persist pending bootstrap connect sessions for init continuity."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hydracept.cli.secure_store import write_json_atomic
from hydracept.cli.workspace import config_dir, read_json

BOOTSTRAP_SESSION_SCHEMA_VERSION = 1


def bootstrap_session_path(project_root: Path) -> Path:
    return config_dir(project_root) / "bootstrap-session.json"


def load_bootstrap_session(project_root: Path) -> dict[str, Any]:
    data = read_json(bootstrap_session_path(project_root))
    if not isinstance(data, dict):
        return {}
    return data


def save_bootstrap_session(
    project_root: Path,
    *,
    session_id: str,
    connect_url: str,
    api_url: str,
    expires_at: str | None = None,
) -> Path:
    path = bootstrap_session_path(project_root)
    payload: dict[str, Any] = {
        "schemaVersion": BOOTSTRAP_SESSION_SCHEMA_VERSION,
        "sessionId": session_id.strip(),
        "connectUrl": connect_url.strip(),
        "apiUrl": api_url.rstrip("/"),
        "savedAt": datetime.now(UTC).isoformat(),
    }
    if expires_at:
        payload["expiresAt"] = expires_at
    write_json_atomic(path, payload)
    return path


def clear_bootstrap_session(project_root: Path) -> None:
    path = bootstrap_session_path(project_root)
    if path.is_file():
        path.unlink()


def bootstrap_session_expired(stored: dict[str, Any]) -> bool:
    raw = str(stored.get("expiresAt") or "").strip()
    if not raw:
        return False
    try:
        normalized = raw.replace("Z", "+00:00")
        expires = datetime.fromisoformat(normalized)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        return expires <= datetime.now(UTC)
    except ValueError:
        return False


def stored_bootstrap_session_matches_api(stored: dict[str, Any], api_url: str) -> bool:
    stored_api = str(stored.get("apiUrl") or "").rstrip("/")
    return stored_api == api_url.rstrip("/")
