"""Installed-checkout validation for init authority (0.3.11 consumer-trust)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import httpx

from hydracept.cli.project import load_project_binding
from hydracept.cli.workspace import auth_headers, read_json, resolve_workspace, secrets_path
from hydracept.context import PROJECT_CREDENTIAL_MISMATCH, resolve_hydracept_context

INSTALLED_WORKSPACE_SCHEMA = "hydracept.cli.installed_workspace.v1"


class InstalledWorkspaceStatus(str, Enum):
    NOT_INSTALLED = "NOT_INSTALLED"
    INVALID_LOCAL_BINDING = "INVALID_LOCAL_BINDING"
    INSTALLED_VALID = "INSTALLED_VALID"
    PROJECT_CREDENTIAL_MISMATCH = "PROJECT_CREDENTIAL_MISMATCH"
    CREDENTIAL_INVALID = "CREDENTIAL_INVALID"
    VALIDATION_UNAVAILABLE = "VALIDATION_UNAVAILABLE"


@dataclass(frozen=True)
class InstalledWorkspaceValidation:
    status: InstalledWorkspaceStatus
    project_id: str | None = None
    environment: str | None = None
    api_url: str | None = None
    token: str | None = None
    detail: str | None = None
    context: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": INSTALLED_WORKSPACE_SCHEMA,
            "status": self.status.value,
            "projectId": self.project_id,
            "environment": self.environment,
            "apiUrl": self.api_url,
            "detail": self.detail,
            "context": self.context,
        }


def _local_install_state(project_root: Path) -> InstalledWorkspaceValidation | None:
    binding = load_project_binding(project_root)
    if binding.get("corruptLocalBinding"):
        return InstalledWorkspaceValidation(
            status=InstalledWorkspaceStatus.INVALID_LOCAL_BINDING,
            detail="Local project binding is unreadable.",
        )
    project_id = str(binding.get("projectId") or "").strip()
    secrets = read_json(secrets_path(project_root))
    token = str(secrets.get("apiKey") or secrets.get("token") or "").strip()
    if not project_id or not token:
        return InstalledWorkspaceValidation(status=InstalledWorkspaceStatus.NOT_INSTALLED)
    return None


def _session_context_payload(
    api_url: str,
    token: str,
    *,
    timeout: float = 20.0,
) -> dict[str, Any] | None:
    try:
        response = httpx.get(
            f"{api_url.rstrip('/')}/v1/session/context",
            headers=auth_headers(token),
            timeout=timeout,
        )
    except httpx.HTTPError:
        return None
    if response.status_code in {401, 403}:
        return None
    if response.status_code != 200:
        return None
    body = response.json()
    return body if isinstance(body, dict) else {}


def validate_installed_workspace(project_root: Path) -> InstalledWorkspaceValidation:
    """Remote-validate an installed checkout without treating local READY as proof."""
    local = _local_install_state(project_root)
    if local is not None:
        return local

    binding = load_project_binding(project_root)
    project_id = str(binding.get("projectId") or "").strip()
    environment = str(binding.get("environment") or "development").strip() or "development"
    secrets = read_json(secrets_path(project_root))
    token = str(secrets.get("apiKey") or secrets.get("token") or "").strip()

    try:
        workspace = resolve_workspace(project_root)
    except Exception:  # noqa: BLE001
        return InstalledWorkspaceValidation(
            status=InstalledWorkspaceStatus.INVALID_LOCAL_BINDING,
            detail="Local workspace binding could not be resolved.",
        )
    if workspace is None or not workspace.token:
        return InstalledWorkspaceValidation(status=InstalledWorkspaceStatus.NOT_INSTALLED)

    api_url = workspace.api_url.rstrip("/")
    try:
        response = httpx.get(
            f"{api_url}/v1/diagnostics/session",
            headers=auth_headers(workspace.token),
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        return InstalledWorkspaceValidation(
            status=InstalledWorkspaceStatus.VALIDATION_UNAVAILABLE,
            project_id=project_id,
            environment=environment,
            api_url=api_url,
            token=token,
            detail=f"Remote credential validation unavailable: {exc}",
        )

    if response.status_code in {401, 403}:
        return InstalledWorkspaceValidation(
            status=InstalledWorkspaceStatus.CREDENTIAL_INVALID,
            project_id=project_id,
            environment=environment,
            api_url=api_url,
            detail="Installed credential was rejected by the API.",
        )
    if response.status_code >= 500 or response.status_code == 408:
        return InstalledWorkspaceValidation(
            status=InstalledWorkspaceStatus.VALIDATION_UNAVAILABLE,
            project_id=project_id,
            environment=environment,
            api_url=api_url,
            token=token,
            detail=f"Remote credential validation failed with HTTP {response.status_code}.",
        )
    if response.status_code != 200:
        return InstalledWorkspaceValidation(
            status=InstalledWorkspaceStatus.VALIDATION_UNAVAILABLE,
            project_id=project_id,
            environment=environment,
            api_url=api_url,
            token=token,
            detail=f"Remote credential validation failed with HTTP {response.status_code}.",
        )

    diagnostics = response.json()
    if not isinstance(diagnostics, dict):
        return InstalledWorkspaceValidation(
            status=InstalledWorkspaceStatus.VALIDATION_UNAVAILABLE,
            project_id=project_id,
            environment=environment,
            api_url=api_url,
            token=token,
            detail="Remote credential validation returned an invalid payload.",
        )

    session_context = _session_context_payload(api_url, workspace.token)
    if session_context is None:
        return InstalledWorkspaceValidation(
            status=InstalledWorkspaceStatus.VALIDATION_UNAVAILABLE,
            project_id=project_id,
            environment=environment,
            api_url=api_url,
            token=token,
            detail="Remote session context could not be loaded.",
        )

    ctx = resolve_hydracept_context(
        project_root,
        refresh=False,
        diagnostics=diagnostics,
        session_context=session_context,
    )
    context_payload = ctx.to_dict()
    if ctx.mismatch == PROJECT_CREDENTIAL_MISMATCH:
        return InstalledWorkspaceValidation(
            status=InstalledWorkspaceStatus.PROJECT_CREDENTIAL_MISMATCH,
            project_id=project_id,
            environment=environment,
            api_url=api_url,
            token=token,
            detail=(
                f"Checkout project {ctx.checkout_project_id} disagrees with credential "
                f"project {ctx.credential_project_id}."
            ),
            context=context_payload,
        )
    if ctx.execution_project_id and ctx.checkout_project_id == ctx.credential_project_id:
        return InstalledWorkspaceValidation(
            status=InstalledWorkspaceStatus.INSTALLED_VALID,
            project_id=project_id,
            environment=environment,
            api_url=api_url,
            token=token,
            context=context_payload,
        )

    return InstalledWorkspaceValidation(
        status=InstalledWorkspaceStatus.VALIDATION_UNAVAILABLE,
        project_id=project_id,
        environment=environment,
        api_url=api_url,
        token=token,
        detail="Remote credential validation did not confirm checkout binding.",
        context=context_payload,
    )
