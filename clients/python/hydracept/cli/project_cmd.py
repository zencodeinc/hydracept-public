"""Public CLI: `hydracept project sync` and `hydracept project watch`."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx
import typer

from hydracept.cli.console_io import cli_console
from hydracept.cli.exit_codes import AUTH, CONNECTIVITY, USAGE
from hydracept.cli.panels_cmd import _raise_for_status, _service_headers
from hydracept.cli.project_agent import (
    AGENT_ID,
    ProjectAgentError,
    build_sync_payload,
    execute_requested_operation,
    resolve_bound_project_id,
)
from hydracept.cli.project_service import (
    ProjectServiceError,
    detect_project_up_service,
    install_project_up,
)
from hydracept.cli.project_up_lock import ProjectUpLock, ProjectUpLockError
from hydracept.cli.session_client import SessionClientError
from hydracept.cli.surface_cmd import apply_project_surfaces, project_tools_fingerprint
from hydracept.cli.surface_definition import SurfaceDefinitionError
from hydracept.cli.workspace import DEFAULT_API, resolve_token

project_app = typer.Typer(help="Bind this checkout to a Hydracept project and run local operations")


def _sync_project(
    *,
    api: str,
    project_root: Path,
    token: str | None,
    project: str | None,
    http_client: Any | None = None,
) -> dict[str, Any]:
    resolved = (token or "").strip() or resolve_token(project_root, token)
    if not resolved:
        raise SessionClientError(
            "No API credential. Run python -m hydracept login or pass --token.",
            status_code=401,
        )
    project_id = resolve_bound_project_id(project_root, token=resolved, project=project)
    payload = build_sync_payload(project_root, hydracept_project_id=project_id)
    local_slug = payload.pop("localProjectSlug", "")
    headers = _service_headers(project_root, resolved)
    base = api.rstrip("/")
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=30.0)
    try:
        body = _raise_for_status(
            client.post(f"{base}/v1/projects/{project_id}/syncs", headers=headers, json=payload)
        )
    finally:
        if owns_client:
            client.close()
    allowlisted = payload.get("operationsPolicy", {}).get("allowlisted") or []
    return {
        "projectId": project_id,
        "localProjectSlug": local_slug,
        "allowlisted": allowlisted,
        "sync": body,
    }


def _watch_once(
    *,
    api: str,
    project_root: Path,
    token: str | None,
    project: str | None,
    http_client: Any | None = None,
) -> list[dict[str, Any]]:
    resolved = (token or "").strip() or resolve_token(project_root, token)
    if not resolved:
        raise SessionClientError(
            "No API credential. Run python -m hydracept login or pass --token.",
            status_code=401,
        )
    project_id = resolve_bound_project_id(project_root, token=resolved, project=project)
    headers = _service_headers(project_root, resolved)
    base = api.rstrip("/")
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=60.0)
    try:
        _post_heartbeat(client, base=base, headers=headers, project_id=project_id)
        return _process_requested(client, base=base, headers=headers, project_id=project_id, project_root=project_root)
    finally:
        if owns_client:
            client.close()


def _process_requested(
    client: Any,
    *,
    base: str,
    headers: dict[str, str],
    project_id: str,
    project_root: Path,
) -> list[dict[str, Any]]:
    listed = _raise_for_status(
        client.get(
            f"{base}/v1/projects/{project_id}/operations",
            headers=headers,
            params={"status": "requested"},
        )
    )
    operations = listed.get("items") if isinstance(listed.get("items"), list) else []
    reported: list[dict[str, Any]] = []
    for operation in operations:
        if not isinstance(operation, dict):
            continue
        operation_id = str(operation.get("id") or "")
        command = str(operation.get("command") or "")
        try:
            report = execute_requested_operation(project_root, operation)
        except Exception as exc:  # noqa: BLE001 — always report so Studio does not hang
            report = {
                "schemaVersion": "hydracept.agent-report.v1",
                "agentId": "hydracept-cli",
                "projectId": project_id,
                "kind": command or "unknown",
                "status": "failed",
                "operationRequestId": operation_id,
                "errors": [str(exc)],
                "message": str(exc),
                "details": {},
                "statusFields": [],
                "metrics": {},
            }
        body = _raise_for_status(
            client.post(
                f"{base}/v1/projects/{project_id}/operations/{operation_id}/report",
                headers=headers,
                json=report,
            )
        )
        reported.append(
            {
                "id": operation_id,
                "command": command,
                "status": report.get("status"),
                "operation": body,
            }
        )
    return reported


def _post_heartbeat(client: Any, *, base: str, headers: dict[str, str], project_id: str) -> None:
    try:
        client.post(
            f"{base}/v1/projects/{project_id}/agent-heartbeat",
            headers=headers,
            json={"agentId": AGENT_ID},
        )
    except Exception:  # noqa: BLE001 — presence is best-effort; watch must keep running
        return


@project_app.command("sync")
def project_sync_cmd(
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    project: str = typer.Option(
        "",
        "--project",
        help="Hydracept project id from Studio/login. Overrides yaml projectId.",
    ),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Record this checkout's operations allowlist as the project's execution authority."""
    out = cli_console()
    try:
        result = _sync_project(
            api=api,
            project_root=project_root,
            token=token or None,
            project=project or None,
        )
    except ProjectAgentError as exc:
        out.print(f"[red]{exc}[/red]")
        raise typer.Exit(USAGE) from exc
    except SessionClientError as exc:
        out.print(f"[red]{exc}[/red]")
        raise typer.Exit(AUTH if exc.status_code == 401 else USAGE) from exc
    except httpx.HTTPError as exc:
        out.print(f"[red]Could not reach Hydracept: {exc}[/red]")
        raise typer.Exit(CONNECTIVITY) from exc
    if json_output:
        out.print_json(data=result)
        return
    allowlisted = ", ".join(result["allowlisted"]) or "(none)"
    slug = result.get("localProjectSlug") or ""
    out.print(
        f"[green]Synced[/green] {result['projectId']} allowlisted={allowlisted}"
        + (f" localSlug={slug}" if slug and slug != result["projectId"] else "")
    )
    out.print("[dim]Next[/dim] python -m hydracept project watch")


def _retryable_watch_error(exc: SessionClientError) -> bool:
    code = exc.status_code
    return code is not None and (code >= 500 or code in {404, 408, 429})


def _run_watch_loop(
    *,
    api: str,
    project_root: Path,
    token: str | None,
    project: str | None,
    interval: float,
    once: bool,
    refresh_surfaces: bool = False,
) -> None:
    out = cli_console()
    lock = ProjectUpLock(project_root)
    try:
        lock.acquire()
    except ProjectUpLockError as exc:
        out.print(f"[red]{exc}[/red]")
        raise typer.Exit(USAGE) from exc
    try:
        try:
            resolved = (token or "").strip() or resolve_token(project_root, token)
            if not resolved:
                raise SessionClientError(
                    "No API credential. Run python -m hydracept login or pass --token.",
                    status_code=401,
                )
            project_id = resolve_bound_project_id(project_root, token=resolved, project=project)
        except ProjectAgentError as exc:
            out.print(f"[red]{exc}[/red]")
            raise typer.Exit(USAGE) from exc
        except SessionClientError as exc:
            out.print(f"[red]{exc}[/red]")
            raise typer.Exit(AUTH if exc.status_code == 401 else USAGE) from exc
        headers = _service_headers(project_root, resolved)
        base = api.rstrip("/")
        out.print(f"[cyan]Watching[/cyan] {project_id} (Ctrl+C to stop)")
        tools_fingerprint = project_tools_fingerprint(project_root) if refresh_surfaces else ""
        try:
            with httpx.Client(timeout=60.0) as client:
                while True:
                    _post_heartbeat(client, base=base, headers=headers, project_id=project_id)
                    if refresh_surfaces:
                        current = project_tools_fingerprint(project_root)
                        if current and current != tools_fingerprint:
                            tools_fingerprint = current
                            try:
                                synced = _sync_project(
                                    api=api,
                                    project_root=project_root,
                                    token=resolved,
                                    project=project_id,
                                    http_client=client,
                                )
                                applied = apply_project_surfaces(
                                    api=api,
                                    project_root=project_root,
                                    token=resolved,
                                    http_client=client,
                                )
                            except (ProjectAgentError, SurfaceDefinitionError, SessionClientError, httpx.HTTPError) as exc:
                                out.print(f"[yellow]Reload deferred[/yellow] {exc}")
                            else:
                                allowlisted = ", ".join(synced["allowlisted"]) or "(none)"
                                out.print(
                                    f"[green]Reloaded[/green] {synced['projectId']} "
                                    f"allowlisted={allowlisted} surfaces={len(applied)}"
                                )
                    try:
                        reported = _process_requested(
                            client,
                            base=base,
                            headers=headers,
                            project_id=project_id,
                            project_root=project_root,
                        )
                    except SessionClientError as exc:
                        if _retryable_watch_error(exc) and not once:
                            out.print(f"[yellow]Retrying[/yellow] {exc}")
                        else:
                            out.print(f"[red]{exc}[/red]")
                            raise typer.Exit(AUTH if exc.status_code == 401 else USAGE) from exc
                    except httpx.HTTPError as exc:
                        out.print(f"[yellow]Retrying[/yellow] {exc}")
                        if once:
                            raise typer.Exit(CONNECTIVITY) from exc
                    else:
                        for item in reported:
                            out.print(
                                f"[green]Reported[/green] {item['id']} {item['command']} -> {item['status']}"
                            )
                        if once:
                            return
                    time.sleep(interval)
        except KeyboardInterrupt:
            out.print("Stopped")
    finally:
        lock.release()


@project_app.command("watch")
def project_watch_cmd(
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    project: str = typer.Option(
        "",
        "--project",
        help="Hydracept project id from Studio/login. Overrides yaml projectId.",
    ),
    interval: float = typer.Option(2.0, "--interval", help="Polling interval seconds"),
    once: bool = typer.Option(False, "--once", help="Process currently requested operations and exit"),
) -> None:
    """Run requested project operations from this checkout and report results."""
    _run_watch_loop(
        api=api,
        project_root=project_root,
        token=token or None,
        project=project or None,
        interval=interval,
        once=once,
    )


@project_app.command("up")
def project_up_cmd(
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    project: str = typer.Option(
        "",
        "--project",
        help="Hydracept project id from Studio/login. Overrides yaml projectId.",
    ),
    interval: float = typer.Option(2.0, "--interval", help="Polling interval seconds"),
    install: bool = typer.Option(
        False,
        "--install",
        help="Register a login-persistent OS service and start it, then exit.",
    ),
) -> None:
    """Apply local surfaces, sync this checkout's allowlist, then watch."""
    out = cli_console()
    root = project_root.resolve()
    if install:
        _install_project_up(
            api=api,
            project_root=root,
            token=token or None,
            project=project or None,
        )
        return
    try:
        result = _sync_project(
            api=api,
            project_root=root,
            token=token or None,
            project=project or None,
        )
        applied = apply_project_surfaces(
            api=api,
            project_root=root,
            token=token or None,
        )
    except ProjectAgentError as exc:
        out.print(f"[red]{exc}[/red]")
        raise typer.Exit(USAGE) from exc
    except SurfaceDefinitionError as exc:
        out.print(f"[red]{exc}[/red]")
        raise typer.Exit(USAGE) from exc
    except SessionClientError as exc:
        out.print(f"[red]{exc}[/red]")
        raise typer.Exit(AUTH if exc.status_code == 401 else USAGE) from exc
    except httpx.HTTPError as exc:
        out.print(f"[red]Could not reach Hydracept: {exc}[/red]")
        raise typer.Exit(CONNECTIVITY) from exc
    allowlisted = ", ".join(result["allowlisted"]) or "(none)"
    out.print(f"[green]Synced[/green] {result['projectId']} allowlisted={allowlisted}")
    if not applied:
        out.print("[dim]No tools/hydracept/surfaces/*.json to apply[/dim]")
    for surface in applied:
        verb = "Updated" if surface["status"] == "updated" else "Created"
        out.print(
            f"[green]{verb}[/green] surface {surface.get('key')} "
            f"origin={surface.get('origin')} version={surface.get('version')}"
        )
    _run_watch_loop(
        api=api,
        project_root=root,
        token=token or None,
        project=result["projectId"],
        interval=interval,
        once=False,
        refresh_surfaces=True,
    )


@project_app.command("uninstall")
def project_uninstall_cmd(
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
) -> None:
    """Remove the login-persistent project up service for this checkout."""
    out = cli_console()
    try:
        detect_project_up_service().uninstall(project_root.resolve())
    except ProjectServiceError as exc:
        out.print(f"[red]{exc}[/red]")
        raise typer.Exit(USAGE) from exc
    out.print("[green]Uninstalled[/green] project up service")


@project_app.command("status")
def project_status_cmd(
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
) -> None:
    """Show whether the login-persistent project up service is installed and running."""
    out = cli_console()
    status = detect_project_up_service().status(project_root.resolve())
    state = "running" if status.running else ("installed" if status.installed else "not installed")
    out.print(f"{status.name} {state}")


def _install_project_up(
    *,
    api: str,
    project_root: Path,
    token: str | None,
    project: str | None,
) -> None:
    out = cli_console()
    try:
        status = install_project_up(
            api=api,
            project_root=project_root,
            token=token,
            project=project,
        )
    except ProjectServiceError as exc:
        out.print(f"[red]{exc}[/red]")
        raise typer.Exit(USAGE) from exc
    out.print(f"[green]Installed[/green] {status.name} ({status.detail})")
    out.print("[dim]Survives Cursor exit and user logon. python -m hydracept project uninstall to stop.[/dim]")
