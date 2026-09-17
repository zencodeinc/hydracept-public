"""Register stdio project-surface tools on the Hydracept MCP server."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server.mcpserver.server import MCPServer

from hydracept import HydraceptClient
from hydracept.cli.workspace import require_ready_workspace
from hydracept.history import find_project_jobs, inspect_job
from hydracept.mcp.interactions import register_interaction_tools
from hydracept.mcp.project_mcp import ProjectMcpService

ProjectRootFn = Callable[[], Path]


def register_project_tools(
    server: MCPServer,
    *,
    project_root_fn: ProjectRootFn,
    apps: Any | None = None,
) -> None:
    def service() -> ProjectMcpService:
        return ProjectMcpService(project_root_fn())

    def invoke(fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — keep the MCP session alive
            return {
                "error": True,
                "code": exc.__class__.__name__,
                "message": str(exc),
                "retryable": False,
            }

    def history_client() -> HydraceptClient:
        workspace = require_ready_workspace(project_root_fn())
        return HydraceptClient(
            workspace.api_url,
            workspace.token,
            workspace=workspace,
        )

    @server.tool()
    def hydracept_jobs_find(
        intent: str = "recent",
        capability_key: str = "",
        limit: int = 10,
    ) -> dict[str, Any]:
        """Find recent, failed, or reusable jobs in this checkout without asking for a job id."""
        def _run() -> dict[str, Any]:
            client = history_client()
            try:
                return find_project_jobs(
                    client,
                    intent=intent,
                    capability_key=capability_key.strip() or None,
                    limit=limit,
                )
            finally:
                client.close()

        return invoke(_run)

    @server.tool()
    def hydracept_job_inspect(job_id: str) -> dict[str, Any]:
        """Inspect one job's error, diagnostics, receipt summary, request snapshot, and reuse candidate."""
        def _run() -> dict[str, Any]:
            client = history_client()
            try:
                return inspect_job(client, job_id)
            finally:
                client.close()

        return invoke(_run)

    @server.tool()
    def hydracept_project_status() -> dict[str, Any]:
        """Login-persistent project up status. Stdio only; cwd must be the game repo."""
        return invoke(service().status)

    @server.tool()
    def hydracept_project_up_install() -> dict[str, Any]:
        """Same as project up --install; credentials come from workspace, not arguments."""
        return invoke(service().install_up)

    @server.tool()
    def hydracept_surface_apply(path: str = "") -> dict[str, Any]:
        """Apply one surface JSON or all project surfaces. Does not grant the allowlist."""
        return invoke(lambda: service().apply_surfaces(path))

    @server.tool()
    def hydracept_project_sync() -> dict[str, Any]:
        """Sync the operations allowlist from tools/hydracept/manifest.json. Wholesale replace."""
        return invoke(service().sync)

    @server.tool()
    def hydracept_project_watch_once() -> dict[str, Any]:
        """Execute requested operations once unless login-persistent project up is running."""
        return invoke(service().watch_once)

    @server.tool()
    def hydracept_project_request_operation(
        command: str,
        action_key: str = "",
        input: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Request an allowlisted project operation; watcher or watch_once executes it."""
        return invoke(
            lambda: service().request_operation(
                command,
                action_key=action_key,
                input=input,
                context=context,
            )
        )

    @server.tool()
    def hydracept_project_get_operation(operation_id: str) -> dict[str, Any]:
        """GET a project operation by id. Poll until reported when a watcher is running."""
        return invoke(lambda: service().get_operation(operation_id))

    register_interaction_tools(server, apps=apps)
