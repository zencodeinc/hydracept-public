"""ResolvedHydraceptContext — execution project or nothing (0.3.3).

checkoutProjectId == credentialProjectId
  → executionProjectId = credentialProjectId
  → ready may be true

checkoutProjectId != credentialProjectId
  → executionProjectId = null
  → ready = false
  → fatal ProjectCredentialMismatch

homeProjectId differs
  → homeProjectDiffers=true, impact=none
  → never used as execution project
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from hydracept.cli.workspace import (
    CliOverrides,
    ResolvedWorkspace,
    WorkspaceNotReadyError,
    auth_headers,
    resolve_workspace,
    workspace_state,
    WorkspaceState,
)

SCHEMA_VERSION = "hydracept.context.v1"
PROJECT_CREDENTIAL_MISMATCH = "ProjectCredentialMismatch"


class ProjectCredentialMismatch(WorkspaceNotReadyError):
    """Checkout identity disagrees with the credential project — no execution."""

    def __init__(self, message: str, *, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = PROJECT_CREDENTIAL_MISMATCH
        self.payload = payload or {}


@dataclass(frozen=True)
class ResolvedHydraceptContext:
    schema_version: str = SCHEMA_VERSION
    checkout_project_id: str | None = None
    credential_project_id: str | None = None
    home_project_id: str | None = None
    execution_project_id: str | None = None
    product_id: str | None = None
    home_project_differs: bool = False
    home_impact: str = "none"
    ready: bool = False
    mismatch: str | None = None
    environment: str | None = None
    api_url: str | None = None
    workspace_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "checkoutProjectId": self.checkout_project_id,
            "credentialProjectId": self.credential_project_id,
            "homeProjectId": self.home_project_id,
            "executionProjectId": self.execution_project_id,
            "productId": self.product_id,
            "homeProjectDiffers": self.home_project_differs,
            "homeImpact": self.home_impact,
            "ready": self.ready,
            "mismatch": self.mismatch,
            "environment": self.environment,
            "apiUrl": self.api_url,
            "workspaceReady": self.workspace_ready,
        }


def _strip(value: Any) -> str:
    return str(value or "").strip()


def build_resolved_context(
    *,
    checkout_project_id: str = "",
    credential_project_id: str = "",
    home_project_id: str = "",
    product_id: str = "",
    environment: str = "",
    api_url: str = "",
    workspace_ready: bool = False,
) -> ResolvedHydraceptContext:
    checkout = _strip(checkout_project_id) or None
    credential = _strip(credential_project_id) or None
    home = _strip(home_project_id) or None
    product = _strip(product_id) or checkout
    home_differs = bool(home and checkout and home != checkout)
    mismatch: str | None = None
    execution: str | None = None
    ready = False
    if checkout and credential and checkout == credential:
        execution = credential
        ready = workspace_ready
    elif checkout and credential and checkout != credential:
        mismatch = PROJECT_CREDENTIAL_MISMATCH
        ready = False
        execution = None
    return ResolvedHydraceptContext(
        checkout_project_id=checkout,
        credential_project_id=credential,
        home_project_id=home,
        execution_project_id=execution,
        product_id=product,
        home_project_differs=home_differs,
        home_impact="none",
        ready=ready,
        mismatch=mismatch,
        environment=_strip(environment) or None,
        api_url=_strip(api_url) or None,
        workspace_ready=workspace_ready,
    )


def _home_from_session_context(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    project = payload.get("project")
    if isinstance(project, dict) and project.get("id"):
        return _strip(project["id"])
    return ""


def _credential_from_diagnostics(
    payload: dict[str, Any] | None,
    *,
    checkout_project_id: str = "",
    home_project_id: str = "",
) -> str:
    """Credential project is the token/principal bound project.

    Diagnostics currently aliases ``projectId`` and ``tokenProjectId`` to
    ``principal.project_id``. Compare against session home, not those two
    fields to each other. An org/user token that echoes account home is not
    a project-scoped credential unless that home is this checkout.
    """
    if not payload:
        return ""
    token = (
        _strip(payload.get("tokenProjectId"))
        or _strip(payload.get("principalProjectId"))
        or _strip(payload.get("projectId"))
    )
    home = _strip(home_project_id)
    checkout = _strip(checkout_project_id)
    if token and home and token == home and checkout and token != checkout:
        return ""
    return token


def fetch_identity_payloads(
    workspace: ResolvedWorkspace,
    *,
    timeout: float = 20.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    headers = auth_headers(workspace.token)
    diagnostics: dict[str, Any] = {}
    session: dict[str, Any] = {}
    with httpx.Client(timeout=timeout) as client:
        try:
            diag = client.get(f"{workspace.api_url}/v1/diagnostics/session", headers=headers)
            if diag.status_code == 200:
                body = diag.json()
                if isinstance(body, dict):
                    diagnostics = body
        except httpx.HTTPError:
            diagnostics = {}
        try:
            ctx = client.get(f"{workspace.api_url}/v1/session/context", headers=headers)
            if ctx.status_code == 200:
                body = ctx.json()
                if isinstance(body, dict):
                    session = body
        except httpx.HTTPError:
            session = {}
    return diagnostics, session


def _trust_ready_checkout(
    *,
    checkout: str,
    home: str,
    environment: str,
    api_url: str,
) -> ResolvedHydraceptContext:
    """Local READY checkout+token is execution truth when identity was not observed."""
    return build_resolved_context(
        checkout_project_id=checkout,
        credential_project_id=checkout,
        home_project_id=home,
        product_id=checkout,
        environment=environment,
        api_url=api_url,
        workspace_ready=True,
    )


def resolve_hydracept_context(
    project_root: Path,
    *,
    overrides: CliOverrides | None = None,
    refresh: bool = True,
    diagnostics: dict[str, Any] | None = None,
    session_context: dict[str, Any] | None = None,
) -> ResolvedHydraceptContext:
    workspace = resolve_workspace(project_root, overrides=overrides)
    checkout = workspace.project_id if workspace else ""
    environment = workspace.environment if workspace else ""
    api_url = workspace.api_url if workspace else ""
    local_ready = workspace_state(workspace) == WorkspaceState.READY
    diag = diagnostics or {}
    session = session_context or {}
    identity_observed = bool(diag) or bool(session)
    if refresh and workspace is not None and workspace.token:
        fetched_diag, fetched_session = fetch_identity_payloads(workspace)
        if fetched_diag:
            diag = fetched_diag
        if fetched_session:
            session = fetched_session
        identity_observed = bool(fetched_diag) or bool(fetched_session) or identity_observed
    home = _home_from_session_context(session)
    credential = _credential_from_diagnostics(
        diag,
        checkout_project_id=checkout,
        home_project_id=home,
    )
    ctx = build_resolved_context(
        checkout_project_id=checkout,
        credential_project_id=credential,
        home_project_id=home,
        product_id=checkout,
        environment=environment,
        api_url=api_url,
        workspace_ready=local_ready,
    )
    if (
        ctx.execution_project_id is None
        and not credential
        and checkout
        and local_ready
        and (not refresh or not identity_observed)
    ):
        return _trust_ready_checkout(
            checkout=checkout,
            home=home,
            environment=environment,
            api_url=api_url,
        )
    return ctx


def require_execution_context(
    project_root: Path,
    *,
    overrides: CliOverrides | None = None,
    refresh: bool = True,
) -> tuple[ResolvedWorkspace, ResolvedHydraceptContext]:
    from hydracept.cli.workspace import require_ready_workspace

    workspace = require_ready_workspace(project_root, overrides=overrides)
    ctx = resolve_hydracept_context(
        project_root,
        overrides=overrides,
        refresh=refresh,
    )
    if ctx.mismatch == PROJECT_CREDENTIAL_MISMATCH:
        raise ProjectCredentialMismatch(
            (
                f"Checkout project {ctx.checkout_project_id} disagrees with credential "
                f"project {ctx.credential_project_id}. Hydracept will not manufacture "
                "an execution project. Re-run python -m hydracept init in this checkout "
                "or use a credential issued for this project."
            ),
            payload=ctx.to_dict(),
        )
    if ctx.execution_project_id is None:
        raise ProjectCredentialMismatch(
            (
                "Cannot resolve an execution project — checkout and credential must match. "
                "Run python -m hydracept doctor --fix"
            ),
            payload=ctx.to_dict(),
        )
    return workspace, ctx


def assert_execution_allowed(workspace: ResolvedWorkspace) -> ResolvedHydraceptContext:
    """Fail closed when checkout and credential disagree. Same gate as `run`."""
    checkout = workspace.project_id
    local_ready = workspace_state(workspace) == WorkspaceState.READY
    diag, session = fetch_identity_payloads(workspace)
    home = _home_from_session_context(session)
    credential = _credential_from_diagnostics(
        diag,
        checkout_project_id=checkout,
        home_project_id=home,
    )
    ctx = build_resolved_context(
        checkout_project_id=checkout,
        credential_project_id=credential,
        home_project_id=home,
        product_id=checkout,
        environment=workspace.environment,
        api_url=workspace.api_url,
        workspace_ready=local_ready,
    )
    if ctx.mismatch == PROJECT_CREDENTIAL_MISMATCH:
        raise ProjectCredentialMismatch(
            (
                f"Checkout project {ctx.checkout_project_id} disagrees with credential "
                f"project {ctx.credential_project_id}. Hydracept will not manufacture "
                "an execution project. Re-run python -m hydracept init in this checkout "
                "or use a credential issued for this project."
            ),
            payload=ctx.to_dict(),
        )
    if (
        ctx.execution_project_id is None
        and not credential
        and checkout
        and local_ready
        and not diag
        and not session
    ):
        return _trust_ready_checkout(
            checkout=checkout,
            home=home,
            environment=workspace.environment,
            api_url=workspace.api_url,
        )
    if ctx.execution_project_id is None:
        raise ProjectCredentialMismatch(
            (
                "Cannot resolve an execution project — checkout and credential must match. "
                "Run python -m hydracept doctor --fix"
            ),
            payload=ctx.to_dict(),
        )
    return ctx
