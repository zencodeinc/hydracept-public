"""CLI storage policy and backend commands."""

from __future__ import annotations

from pathlib import Path

import httpx
import typer

from hydracept.cli.console_io import cli_console
from hydracept.cli.workspace import resolve_token, resolve_workspace

storage_app = typer.Typer(help="Organization storage configuration")
console = cli_console()


@storage_app.command("show")
def storage_show(
    organization_id: str = typer.Argument(..., help="Organization id"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
) -> None:
    """Show storage policy and accounting summary."""
    ws = resolve_workspace(project_root)
    if ws is None:
        console.print("[red]Workspace not ready — run hydracept configure[/red]")
        raise typer.Exit(1)
    token = resolve_token(project_root, None)
    base = ws.api_url.rstrip("/")
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=base, headers=headers, timeout=30.0) as client:
        policy = client.get(f"/v1/organizations/{organization_id}/storage/policy")
        accounting = client.get(f"/v1/organizations/{organization_id}/storage/accounting")
    console.print({"policy": policy.json() if policy.status_code == 200 else None})
    if accounting.status_code == 200:
        console.print(accounting.json())


@storage_app.command("test-backend")
def storage_test_backend(
    organization_id: str = typer.Argument(...),
    backend_id: str = typer.Argument(...),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
) -> None:
    """Run health check against a configured storage backend."""
    ws = resolve_workspace(project_root)
    if ws is None:
        console.print("[red]Workspace not ready — run hydracept configure[/red]")
        raise typer.Exit(1)
    token = resolve_token(project_root, None)
    base = ws.api_url.rstrip("/")
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=base, headers=headers, timeout=60.0) as client:
        resp = client.post(f"/v1/organizations/{organization_id}/storage/backends/{backend_id}/test")
    if resp.status_code >= 400:
        console.print(f"[red]{resp.status_code} {resp.text}[/red]")
        raise typer.Exit(1)
    console.print(resp.json())
