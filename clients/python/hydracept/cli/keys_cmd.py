"""Workspace API key management via human session."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console

from hydracept.cli.bootstrap import ConfigureError, ensure_gitignore, run_configure
from hydracept.cli.exit_codes import AUTH, USAGE
from hydracept.cli.secure_store import read_json, write_json_atomic
from hydracept.cli.session_client import (
    SessionClientError,
    create_key,
    environment_from_session_context,
    fetch_session_context,
    list_keys,
    project_from_session_context,
    revoke_key,
)
from hydracept.cli.session_store import load_session
from hydracept.cli.workspace import config_path, read_json as read_workspace_json, secrets_path

keys_app = typer.Typer(help="Manage Hydracept API keys (human session required).")


@keys_app.command("list")
def keys_list(
    json_output: bool = typer.Option(False, "--json"),
    include_revoked: bool = typer.Option(False, "--include-revoked"),
) -> None:
    out = Console()
    try:
        payload = list_keys(include_revoked=include_revoked)
    except SessionClientError as exc:
        out.print(f"[red]{exc}[/red]")
        raise typer.Exit(AUTH if exc.status_code == 401 else USAGE) from exc
    if json_output:
        out.print_json(data=payload)
        return
    for row in payload.get("keys", []):
        out.print(
            f"{row.get('keyId')}  {row.get('prefix')}…  "
            f"{row.get('environment')}  revoked={row.get('revoked')}"
        )


@keys_app.command("create")
def keys_create(
    name: str = typer.Option("CLI workstation", "--name"),
    project: str = typer.Option("", "--project"),
    environment: str = typer.Option("development", "--environment"),
    configure: bool = typer.Option(False, "--configure"),
    json_output: bool = typer.Option(False, "--json"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
) -> None:
    out = Console()
    if load_session() is None:
        out.print("[red]Not signed in. Run python -m hydracept login[/red]")
        raise typer.Exit(AUTH)

    cfg = read_workspace_json(config_path(project_root))
    project_id = (project or str(cfg.get("projectId") or "")).strip()
    environment_slug = environment.strip() or str(cfg.get("environment") or "development")

    if not project_id:
        try:
            context = fetch_session_context()
            project_id = project_from_session_context(context)
            if not project or environment_slug == "development":
                environment_slug = environment_from_session_context(
                    context,
                    default=environment_slug,
                )
        except SessionClientError as exc:
            out.print(f"[red]{exc}[/red]")
            raise typer.Exit(AUTH if exc.status_code == 401 else USAGE) from exc

    if not project_id:
        out.print(
            "[red]No projectId. Pass --project, run configure, or complete onboarding at "
            "https://hydracept.com/start[/red]"
        )
        raise typer.Exit(USAGE)

    try:
        created = create_key(
            name=name,
            project_id=project_id,
            environment=environment_slug,
        )
    except SessionClientError as exc:
        out.print(f"[red]{exc}[/red]")
        raise typer.Exit(AUTH if exc.status_code == 401 else USAGE) from exc

    api_key = str(created.get("apiKey") or "")
    prefix = str(created.get("prefix") or api_key[:16])

    if json_output:
        print(
            json.dumps(
                {
                    "keyId": created.get("keyId"),
                    "prefix": prefix,
                    "apiKey": api_key,
                    "projectId": created.get("projectId"),
                    "environment": created.get("environment"),
                }
            ),
            file=sys.stdout,
        )
        print(
            "WARNING: stdout contains a secret.\n"
            "Do not paste it into chat, logs, issue trackers, or documentation.",
            file=sys.stderr,
        )
        if configure:
            _configure_workspace(project_root, api_key, out)
        return

    if configure:
        _configure_workspace(project_root, api_key, out)
        out.print(f"[green]API key created:[/green] {prefix}…")
        out.print(f"Project: {created.get('projectId')}")
        out.print(f"Environment: {created.get('environment')}")
        out.print("\nCredential saved to this Hydracept workspace.")
        out.print("\nNext:\n  python -m hydracept agents install --auto")
    else:
        out.print(f"[green]API key created[/green] (show once): {api_key}")
        out.print(f"Prefix: {prefix}…")


@keys_app.command("revoke")
def keys_revoke(
    key_id: str = typer.Argument(...),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    out = Console()
    try:
        payload = revoke_key(key_id)
    except SessionClientError as exc:
        out.print(f"[red]{exc}[/red]")
        raise typer.Exit(AUTH if exc.status_code == 401 else USAGE) from exc
    if json_output:
        out.print_json(data=payload)
        return
    out.print(f"[green]Revoked[/green] {payload.get('keyId')}")


def _configure_workspace(project_root: Path, api_key: str, out: Console) -> None:
    secrets_file = secrets_path(project_root)
    prior = read_json(secrets_file) if secrets_file.is_file() else {}
    staged = {
        "schemaVersion": 2,
        "kind": "api_key",
        "apiKey": api_key,
    }
    try:
        run_configure(project_root, token=api_key)
    except ConfigureError as exc:
        out.print(
            f"[yellow]Key was created on the server but local configure failed:[/yellow] {exc}\n"
            "The key exists remotely — list or revoke it with hydracept keys list."
        )
        raise typer.Exit(exc.exit_code) from exc
    try:
        write_json_atomic(secrets_file, {**prior, **staged})
        ensure_gitignore(project_root)
    except Exception as exc:
        out.print(
            f"[yellow]Configure succeeded but could not write secrets.json:[/yellow] {exc}"
        )
        raise typer.Exit(AUTH) from exc
