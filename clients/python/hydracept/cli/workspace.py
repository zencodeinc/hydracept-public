"""Local Hydracept CLI workspace paths and credential resolution."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_API = os.environ.get("HYDRACEPT_API_URL", "https://api.hydracept.com")


def config_dir(project_root: Path) -> Path:
    return project_root / ".hydracept"


def secrets_path(project_root: Path) -> Path:
    return config_dir(project_root) / "secrets.json"


def config_path(project_root: Path) -> Path:
    return config_dir(project_root) / "config.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_token(project_root: Path, token: str | None) -> str:
    if token:
        return token
    env = (
        os.environ.get("HYDRACEPT_API_KEY")
        or os.environ.get("HYDRACEPT_TOKEN")
        or ""
    ).strip()
    if env:
        return env
    secrets = read_json(secrets_path(project_root))
    return str(secrets.get("apiKey") or secrets.get("token") or "")


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
