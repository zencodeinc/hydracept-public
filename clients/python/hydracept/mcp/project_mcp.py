"""Stdio MCP facade over the public project-surface CLI.

Does not invent a second execution path. Apply does not grant the allowlist.
Hosted MCP must not call this — it needs the customer checkout.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from hydracept.cli.panels_cmd import _raise_for_status, _service_headers
from hydracept.cli.project_agent import resolve_bound_project_id
from hydracept.cli.project_cmd import _sync_project, _watch_once
from hydracept.cli.project_service import detect_project_up_service, install_project_up
from hydracept.cli.project_up_lock import ProjectUpLock, ProjectUpLockError, watcher_running
from hydracept.cli.session_client import SessionClientError
from hydracept.cli.surface_cmd import apply_project_surfaces, apply_surface
from hydracept.cli.surface_definition import SurfaceDefinitionError
from hydracept.cli.workspace import DEFAULT_API, resolve_token, resolve_workspace

STDIO_PROJECT_TOOL_NAMES = (
    "hydracept_project_status",
    "hydracept_project_up_install",
    "hydracept_surface_apply",
    "hydracept_project_sync",
    "hydracept_project_watch_once",
    "hydracept_project_request_operation",
    "hydracept_project_get_operation",
)


class ProjectMcpService:
    """Wraps apply / sync / watch / request using workspace credentials only."""

    def __init__(self, project_root: Path, *, http_client: Any | None = None) -> None:
        self.project_root = Path(project_root).resolve()
        self._http_client = http_client

    def status(self) -> dict[str, Any]:
        os_status = detect_project_up_service().status(self.project_root)
        workspace = resolve_workspace(self.project_root)
        return {
            "name": os_status.name,
            "installed": os_status.installed,
            "running": os_status.running,
            "detail": os_status.detail,
            "watcherRunning": watcher_running(self.project_root),
            "projectRoot": str(self.project_root),
            "projectId": workspace.project_id if workspace else "",
            "api": workspace.api_url if workspace else "",
        }

    def apply_surfaces(self, path: str = "") -> dict[str, Any]:
        api, token = self._api_and_token()
        target = path.strip()
        if not target:
            applied = apply_project_surfaces(
                api=api,
                project_root=self.project_root,
                token=token,
                http_client=self._http_client,
            )
            result: dict[str, Any] = {"applied": applied}
            if not applied:
                result["message"] = "No tools/hydracept/surfaces/*.json to apply"
            return result
        file_path = Path(target)
        if not file_path.is_absolute():
            file_path = self.project_root / file_path
        if file_path.is_dir():
            applied = [
                apply_surface(
                    json_path,
                    api=api,
                    project_root=self.project_root,
                    token=token,
                    http_client=self._http_client,
                )
                for json_path in sorted(file_path.glob("*.json"))
            ]
            return {"applied": applied}
        if not file_path.is_file():
            raise SurfaceDefinitionError(f"Surface file not found: {file_path}")
        return {
            "applied": [
                apply_surface(
                    file_path,
                    api=api,
                    project_root=self.project_root,
                    token=token,
                    http_client=self._http_client,
                )
            ]
        }

    def sync(self) -> dict[str, Any]:
        api, token, project_id = self._api_token_project()
        return _sync_project(
            api=api,
            project_root=self.project_root,
            token=token,
            project=project_id,
            http_client=self._http_client,
        )

    def install_up(self) -> dict[str, Any]:
        api, token, project_id = self._api_token_project()
        status = install_project_up(
            api=api,
            project_root=self.project_root,
            token=token,
            project=project_id,
        )
        return {
            "name": status.name,
            "installed": status.installed,
            "running": status.running,
            "detail": status.detail,
        }

    def watch_once(self) -> dict[str, Any]:
        if watcher_running(self.project_root):
            return {
                "deferred": True,
                "reason": "login-persistent project up is already running",
            }
        api, token, project_id = self._api_token_project()
        try:
            with ProjectUpLock(self.project_root):
                reported = _watch_once(
                    api=api,
                    project_root=self.project_root,
                    token=token,
                    project=project_id,
                    http_client=self._http_client,
                )
        except ProjectUpLockError as exc:
            return {"deferred": True, "reason": str(exc)}
        return {"deferred": False, "reported": reported}

    def request_operation(
        self,
        command: str,
        action_key: str = "",
        input: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        api, token, project_id = self._api_token_project()
        named = command.strip()
        if not named:
            raise SessionClientError("command is required", status_code=400)
        key = (action_key or named).strip()
        body: dict[str, Any] = {
            "actionKey": key,
            "command": named,
            "input": input or {},
        }
        if context:
            body["context"] = context
        return self._request(
            "POST",
            f"{api}/v1/projects/{project_id}/operations",
            json=body,
            token=token,
        )

    def get_operation(self, operation_id: str) -> dict[str, Any]:
        api, token, project_id = self._api_token_project()
        oid = operation_id.strip()
        if not oid:
            raise SessionClientError("operation_id is required", status_code=400)
        return self._request(
            "GET",
            f"{api}/v1/projects/{project_id}/operations/{oid}",
            token=token,
        )

    def _api_and_token(self) -> tuple[str, str]:
        workspace = resolve_workspace(self.project_root)
        token = resolve_token(self.project_root, None)
        if not token:
            raise SessionClientError(
                "No API credential. Run python -m hydracept login.",
                status_code=401,
            )
        api = (workspace.api_url if workspace else DEFAULT_API).rstrip("/")
        return api, token

    def _api_token_project(self) -> tuple[str, str, str]:
        api, token = self._api_and_token()
        workspace = resolve_workspace(self.project_root)
        bound = (workspace.project_id if workspace else "").strip()
        if bound:
            return api, token, bound
        return api, token, resolve_bound_project_id(self.project_root, token=token)

    def _request(
        self,
        method: str,
        url: str,
        *,
        token: str,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = _service_headers(self.project_root, token)
        owns_client = self._http_client is None
        client = self._http_client or httpx.Client(timeout=30.0)
        try:
            if method == "GET":
                response = client.get(url, headers=headers)
            else:
                response = client.post(url, headers=headers, json=json)
            return _raise_for_status(response)
        finally:
            if owns_client:
                client.close()
