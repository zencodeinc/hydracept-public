"""Local Hydracept CLI workspace paths, resolution, and readiness."""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal

DEFAULT_API = "https://api.hydracept.com"

_LEGACY_PROJECT_WARNED = False

FieldSourceKind = Literal["cli", "env", "config", "legacy_env", "default", "session"]


class WorkspaceState(str, Enum):
    UNCONFIGURED = "unconfigured"
    AUTHENTICATED = "authenticated"
    READY = "ready"


@dataclass(frozen=True)
class FieldSource:
    kind: FieldSourceKind


@dataclass(frozen=True)
class CliOverrides:
    token: str | None = None
    api_url: str | None = None
    project_id: str | None = None
    environment: str | None = None
    session_context: dict[str, Any] | None = None


@dataclass(frozen=True)
class ResolvedWorkspace:
    api_url: str
    token: str
    project_id: str
    environment: str
    sources: dict[str, FieldSource] = field(default_factory=dict)

    def state(self) -> WorkspaceState:
        return workspace_state(self)


def config_dir(project_root: Path) -> Path:
    return Path(project_root) / ".hydracept"


def secrets_path(project_root: Path) -> Path:
    return config_dir(project_root) / "secrets.json"


def config_path(project_root: Path) -> Path:
    return config_dir(project_root) / "config.json"


def local_env_path(project_root: Path) -> Path:
    return config_dir(project_root) / "local.env"


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _first_non_empty(*values: str | None) -> str:
    for value in values:
        if value and str(value).strip():
            return str(value).strip()
    return ""


def _project_from_session(context: dict[str, Any] | None) -> str:
    if not context:
        return ""
    project = context.get("project")
    if isinstance(project, dict) and project.get("id"):
        return str(project["id"])
    if context.get("productId"):
        return str(context["productId"])
    return ""


def _environment_from_session(context: dict[str, Any] | None) -> str:
    if not context:
        return ""
    environment = context.get("environment")
    if isinstance(environment, dict) and environment.get("slug"):
        return str(environment["slug"])
    if isinstance(environment, str):
        return environment
    return ""


def resolve_token(project_root: Path, token: str | None) -> str:
    overrides = CliOverrides(token=token)
    resolved = resolve_workspace(project_root, overrides=overrides)
    return resolved.token if resolved else ""


class WorkspaceIdentityError(Exception):
    """Raised when env/CLI identity disagrees with project.json."""


def resolve_workspace(
    project_root: Path,
    *,
    overrides: CliOverrides | None = None,
) -> ResolvedWorkspace | None:
    """Resolve workspace from project.json (ADR-028). Identity is not overridable."""
    global _LEGACY_PROJECT_WARNED
    ovr = overrides or CliOverrides()
    secrets = read_json(secrets_path(project_root))
    sources: dict[str, FieldSource] = {}

    token = _first_non_empty(
        ovr.token,
        os.environ.get("HYDRACEPT_API_KEY"),
        os.environ.get("HYDRACEPT_TOKEN"),
        str(secrets.get("apiKey") or ""),
        str(secrets.get("token") or ""),
    )
    if not token:
        return None
    if ovr.token:
        sources["token"] = FieldSource("cli")
    elif os.environ.get("HYDRACEPT_API_KEY") or os.environ.get("HYDRACEPT_TOKEN"):
        sources["token"] = FieldSource("env")
    else:
        sources["token"] = FieldSource("config")

    from hydracept.cli.project import load_project_binding, legacy_identity_from_config

    binding = load_project_binding(project_root)
    if not binding:
        binding = legacy_identity_from_config(project_root)

    bound_project = str(binding.get("projectId") or "").strip()
    bound_env = str(binding.get("environment") or "").strip()
    bound_origin = str(binding.get("apiOrigin") or binding.get("apiBaseUrl") or "").strip()

    env_project = _first_non_empty(
        os.environ.get("HYDRACEPT_PROJECT"),
        os.environ.get("HYDRACEPT_PROJECT_ID"),
    )
    legacy_project = os.environ.get("HYDRACEPT_PROJECT_ID", "").strip()
    if legacy_project and not os.environ.get("HYDRACEPT_PROJECT") and not _LEGACY_PROJECT_WARNED:
        warnings.warn(
            "HYDRACEPT_PROJECT_ID is deprecated; use HYDRACEPT_PROJECT",
            DeprecationWarning,
            stacklevel=2,
        )
        _LEGACY_PROJECT_WARNED = True

    if bound_project and env_project and env_project != bound_project:
        raise WorkspaceIdentityError(
            f"HYDRACEPT_PROJECT={env_project} disagrees with project.json projectId={bound_project}. "
            "The checkout binding is absolute. Unset the env var or re-run init."
        )
    env_api = os.environ.get("HYDRACEPT_API_URL", "").strip()
    if bound_origin and env_api and env_api.rstrip("/") != bound_origin.rstrip("/"):
        raise WorkspaceIdentityError(
            f"HYDRACEPT_API_URL disagrees with project.json apiOrigin={bound_origin}."
        )
    env_environment = os.environ.get("HYDRACEPT_ENVIRONMENT", "").strip()
    if bound_env and env_environment and env_environment != bound_env:
        raise WorkspaceIdentityError(
            f"HYDRACEPT_ENVIRONMENT={env_environment} disagrees with project.json environment={bound_env}."
        )
    # CliOverrides.project_id is never applied to checkout identity.
    # `--project` on a one-shot CLI command is an ephemeral HTTP target only.

    api_url = _first_non_empty(
        bound_origin,
        ovr.api_url,
        env_api,
        DEFAULT_API,
    )
    if bound_origin:
        sources["api_url"] = FieldSource("config")
    elif ovr.api_url:
        sources["api_url"] = FieldSource("cli")
    elif env_api:
        sources["api_url"] = FieldSource("env")
    else:
        sources["api_url"] = FieldSource("default")

    project_id = _first_non_empty(
        bound_project,
        env_project,
        _project_from_session(ovr.session_context),
    )
    if bound_project:
        sources["project_id"] = FieldSource("config")
    elif env_project:
        sources["project_id"] = FieldSource("env")
    elif _project_from_session(ovr.session_context):
        sources["project_id"] = FieldSource("session")
    else:
        sources["project_id"] = FieldSource("default")

    environment = _first_non_empty(
        bound_env,
        ovr.environment,
        env_environment,
        _environment_from_session(ovr.session_context),
        "development",
    )
    if bound_env:
        sources["environment"] = FieldSource("config")
    elif ovr.environment:
        sources["environment"] = FieldSource("cli")
    elif env_environment:
        sources["environment"] = FieldSource("env")
    elif _environment_from_session(ovr.session_context):
        sources["environment"] = FieldSource("session")
    else:
        sources["environment"] = FieldSource("default")

    return ResolvedWorkspace(
        api_url=api_url.rstrip("/"),
        token=token,
        project_id=project_id,
        environment=environment,
        sources=sources,
    )


def workspace_state(resolved: ResolvedWorkspace | None) -> WorkspaceState:
    if resolved is None or not resolved.token:
        return WorkspaceState.UNCONFIGURED
    if not resolved.project_id or not resolved.api_url:
        return WorkspaceState.AUTHENTICATED
    return WorkspaceState.READY


def require_ready_workspace(
    project_root: Path,
    *,
    overrides: CliOverrides | None = None,
) -> ResolvedWorkspace:
    try:
        resolved = resolve_workspace(project_root, overrides=overrides)
    except WorkspaceIdentityError as exc:
        raise WorkspaceNotReadyError(str(exc)) from exc
    if resolved is None:
        raise WorkspaceNotReadyError(
            "No workspace API key — run: python -m hydracept login "
            "then python -m hydracept keys create --configure"
        )
    if workspace_state(resolved) != WorkspaceState.READY:
        raise WorkspaceNotReadyError(
            "Workspace not ready — run python -m hydracept configure or quickstart"
        )
    return resolved


class WorkspaceNotReadyError(Exception):
    """Raised when a command requires READY workspace state."""
