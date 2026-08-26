"""Canonical committable workspace binding (.hydracept/project.json)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from hydracept.cli.workspace import WorkspaceIdentityError, config_dir, config_path, read_json

PROJECT_SCHEMA_VERSION = "hydracept.workspace.v1"
DEFAULT_CAPABILITY_PROFILE = ["image.generate.v1"]
IDENTITY_CONFIG_KEYS = ("projectId", "environment", "apiBaseUrl")


def looks_like_path(value: str | None) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if "\\" in text or ":" in text:
        return True
    normalized = text.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part and part not in {".", ".."}]
    return len(parts) >= 3


def resolve_suggested_project_name(
    project_root: Path,
    binding: dict[str, Any] | None = None,
    *,
    override: str | None = None,
) -> str:
    env_name = (override or os.environ.get("HYDRACEPT_PROJECT_NAME") or "").strip()
    if env_name:
        return env_name
    binding = binding or {}
    binding_name = str(binding.get("projectName") or "").strip()
    if binding_name and not looks_like_path(binding_name):
        return binding_name
    folder_name = project_root.resolve().name.strip()
    if folder_name and folder_name not in {".", ""}:
        return folder_name
    return "My Game"


def pretty_project_folder_name(folder_name: str) -> str:
    text = folder_name.strip()
    if not text:
        return "My Game"
    if re.search(r"[A-Z]", text) and " " in text:
        return text
    pretty = text.replace("-", " ").replace("_", " ").strip()
    return pretty.title() if pretty else "My Game"


def project_path(project_root: Path) -> Path:
    return config_dir(project_root) / "project.json"


def strip_identity_from_config(config: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(config)
    for key in IDENTITY_CONFIG_KEYS:
        cleaned.pop(key, None)
    return cleaned


def persist_config_without_identity(project_root: Path) -> None:
    path = config_path(project_root)
    if not path.is_file():
        return
    data = read_json(path)
    cleaned = strip_identity_from_config(data)
    if cleaned == data:
        return
    path.write_text(json.dumps(cleaned, indent=2) + "\n", encoding="utf-8")


def load_project_binding(project_root: Path) -> dict[str, Any]:
    path = project_path(project_root)
    if path.is_file():
        data = read_json(path)
        if data and str(data.get("projectId") or "").strip():
            return data
    return {}


def legacy_identity_from_config(project_root: Path) -> dict[str, Any]:
    legacy = read_json(config_path(project_root))
    project_id = str(legacy.get("projectId") or "").strip()
    if not project_id:
        return {}
    api_origin = str(legacy.get("apiBaseUrl") or "").strip()
    environment = str(legacy.get("environment") or "development").strip() or "development"
    payload: dict[str, Any] = {
        "schemaVersion": PROJECT_SCHEMA_VERSION,
        "projectId": project_id,
        "environment": environment,
        "capabilityProfile": list(legacy.get("capabilityProfile") or DEFAULT_CAPABILITY_PROFILE),
    }
    if api_origin:
        payload["apiOrigin"] = api_origin
    if legacy.get("projectName"):
        payload["projectName"] = str(legacy["projectName"])
    return payload


def capability_profile(binding: dict[str, Any]) -> list[str]:
    profile = binding.get("capabilityProfile")
    if isinstance(profile, list) and profile:
        return [str(item) for item in profile if str(item).strip()]
    return list(DEFAULT_CAPABILITY_PROFILE)


def repair_workspace_identity(
    project_root: Path,
    *,
    remote_project_id: str | None = None,
    remote_environment: str | None = None,
    remote_api_origin: str | None = None,
) -> str:
    """Migrate 0.2 config identity into project.json. Fail when remote evidence cannot decide."""
    binding = load_project_binding(project_root)
    legacy = legacy_identity_from_config(project_root)
    bound_id = str(binding.get("projectId") or "").strip()
    legacy_id = str(legacy.get("projectId") or "").strip()
    remote = str(remote_project_id or "").strip()

    if bound_id and (not legacy_id or bound_id == legacy_id):
        persist_config_without_identity(project_root)
        return "project_json"
    if not bound_id and legacy_id:
        payload = dict(legacy)
        if remote_environment:
            payload["environment"] = remote_environment
        if remote_api_origin:
            payload["apiOrigin"] = remote_api_origin
        write_project_binding(project_root, payload)
        return "migrated_config"
    if bound_id and legacy_id and bound_id != legacy_id:
        if remote and remote == bound_id:
            persist_config_without_identity(project_root)
            return "remote_confirmed_project_json"
        if remote and remote == legacy_id:
            payload = dict(legacy)
            if remote_environment:
                payload["environment"] = remote_environment
            if remote_api_origin:
                payload["apiOrigin"] = remote_api_origin
            write_project_binding(project_root, payload)
            return "remote_confirmed_config"
        raise WorkspaceIdentityError(
            "project.json and config.json disagree on projectId and remote key binding "
            "could not decide. Re-run python -m hydracept init."
        )
    persist_config_without_identity(project_root)
    return "none"


def write_project_binding(project_root: Path, binding: dict[str, Any]) -> Path:
    path = project_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": PROJECT_SCHEMA_VERSION,
        "projectId": str(binding.get("projectId") or "").strip(),
        "environment": str(binding.get("environment") or "development").strip() or "development",
        "apiOrigin": str(binding.get("apiOrigin") or binding.get("apiBaseUrl") or "https://api.hydracept.com").strip()
        or "https://api.hydracept.com",
        "capabilityProfile": capability_profile(binding),
    }
    if binding.get("projectName"):
        payload["projectName"] = str(binding["projectName"])
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    persist_config_without_identity(project_root)
    return path
