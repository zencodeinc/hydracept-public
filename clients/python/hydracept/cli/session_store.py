"""Global human session storage (~/.hydracept/session.json)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hydracept.cli.secure_store import read_json, write_json_atomic

DEFAULT_APP_BASE_URL = "https://app.hydracept.com"
SESSION_SCHEMA_VERSION = 1
SESSION_EXPIRED_MESSAGE = (
    "Your Hydracept login session has expired. Run python -m hydracept login and retry."
)


@dataclass(frozen=True)
class HumanSession:
    session_token: str
    csrf_token: str
    principal_id: str
    app_base_url: str = DEFAULT_APP_BASE_URL
    schema_version: int = SESSION_SCHEMA_VERSION


def global_hydracept_dir() -> Path:
    return Path.home() / ".hydracept"


def session_path() -> Path:
    return global_hydracept_dir() / "session.json"


def load_session() -> HumanSession | None:
    data = read_json(session_path())
    token = str(data.get("sessionToken") or "").strip()
    csrf = str(data.get("csrfToken") or "").strip()
    principal = str(data.get("principalId") or "").strip()
    if not token or not csrf or not principal:
        return None
    return HumanSession(
        session_token=token,
        csrf_token=csrf,
        principal_id=principal,
        app_base_url=str(data.get("appBaseUrl") or DEFAULT_APP_BASE_URL).rstrip("/"),
        schema_version=int(data.get("schemaVersion") or SESSION_SCHEMA_VERSION),
    )


def save_session(session: HumanSession) -> Path:
    payload: dict[str, Any] = {
        "schemaVersion": SESSION_SCHEMA_VERSION,
        "sessionToken": session.session_token,
        "csrfToken": session.csrf_token,
        "principalId": session.principal_id,
        "appBaseUrl": session.app_base_url.rstrip("/"),
    }
    path = session_path()
    write_json_atomic(path, payload)
    return path


def clear_session() -> None:
    path = session_path()
    if path.is_file():
        path.unlink()
