"""Setup grant CLI (advanced / CI bootstrap)."""

from __future__ import annotations

import json
import sys

import httpx
import typer
from rich.console import Console

from hydracept.cli.exit_codes import AUTH, USAGE
from hydracept.cli.session_client import SessionClientError, _session_headers
from hydracept.cli.session_store import SESSION_EXPIRED_MESSAGE, load_session

setup_grant_app = typer.Typer(help="Issue short-lived setup grants.")


@setup_grant_app.command("create")
def setup_grant_create(
    project: str = typer.Option(..., "--project"),
    environment: str = typer.Option("development", "--environment"),
    provider: str = typer.Option("", "--provider"),
    single_use: bool = typer.Option(False, "--single-use"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    out = Console()
    session = load_session()
    if session is None:
        out.print(f"[red]{SESSION_EXPIRED_MESSAGE}[/red]")
        raise typer.Exit(AUTH)
    body: dict[str, object] = {
        "projectId": project,
        "environment": environment,
        "singleUse": single_use or bool(provider),
    }
    if provider:
        body["provider"] = provider.strip().lower()
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{session.app_base_url}/v1/setup/grants",
            headers=_session_headers(session),
            json=body,
        )
    if response.status_code == 401:
        out.print(f"[red]{SESSION_EXPIRED_MESSAGE}[/red]")
        raise typer.Exit(AUTH)
    if response.is_error:
        out.print(f"[red]{response.text}[/red]")
        raise typer.Exit(USAGE)
    payload = response.json()
    if json_output:
        safe = {
            "grantId": payload.get("grantId"),
            "setupGrant": payload.get("setupGrant"),
            "expiresAt": payload.get("expiresAt"),
            "grantType": payload.get("grantType"),
        }
        print(json.dumps(safe), file=sys.stdout)
        return
    out.print("[green]Setup grant issued[/green]")
    out.print("Export [bold]HYDRACEPT_SETUP_GRANT[/bold] from the token below for CI.")
    token = str(payload.get("setupGrant") or "").strip()
    if token:
        out.print(token)
    out.print("Use [bold]--json[/bold] to print the grant in machine-readable form.")
