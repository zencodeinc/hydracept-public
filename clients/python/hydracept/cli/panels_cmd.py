"""Panel definition and session management CLI."""

from __future__ import annotations

import json
import sys
import webbrowser
from pathlib import Path
from typing import Any

import httpx
import typer
from rich.console import Console

from hydracept.cli.exit_codes import AUTH, USAGE
from hydracept.cli.session_client import (
    SessionClientError,
    environment_from_session_context,
    fetch_session_context,
    project_from_session_context,
)
from hydracept.cli.session_store import DEFAULT_APP_BASE_URL, load_session
from hydracept.cli.workspace import DEFAULT_API, config_path, read_json as read_workspace_json, resolve_token

panels_app = typer.Typer(help="Panel definitions and hosted sessions")
session_app = typer.Typer(help="Panel session lifecycle")
panels_app.add_typer(session_app, name="session")


def _console() -> Console:
    return Console()


def _resolve_api_token(project_root: Path, token: str | None) -> str:
    return resolve_token(project_root, token)


def _service_headers(project_root: Path, token: str | None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_resolve_api_token(project_root, token)}",
        "Content-Type": "application/json",
    }


def _session_headers() -> dict[str, str]:
    session = load_session()
    if session is None:
        raise SessionClientError("Not signed in. Run python -m hydracept login", status_code=401)
    return {
        "Cookie": (
            f"hydracept_session={session.session_token}; "
            f"hydracept_csrf={session.csrf_token}"
        ),
        "X-CSRF-Token": session.csrf_token,
        "Content-Type": "application/json",
    }


def _request_error(response: httpx.Response) -> str:
    try:
        body = response.json()
        detail = body.get("detail")
        if isinstance(detail, str):
            return detail
        return json.dumps(body)
    except Exception:
        return response.text or f"HTTP {response.status_code}"


def _raise_for_status(response: httpx.Response) -> dict[str, Any]:
    if response.status_code == 401:
        raise SessionClientError("Authentication failed", status_code=401)
    if response.is_error:
        raise SessionClientError(_request_error(response), status_code=response.status_code)
    if not response.content:
        return {}
    payload = response.json()
    return payload if isinstance(payload, dict) else {"data": payload}


def _resolve_project(
    project_root: Path,
    project: str,
    environment: str,
) -> tuple[str, str]:
    cfg = read_workspace_json(config_path(project_root))
    project_id = (project or str(cfg.get("projectId") or "")).strip()
    environment_slug = environment.strip() or str(cfg.get("environment") or "development")
    if project_id:
        return project_id, environment_slug
    if load_session() is None:
        return "", environment_slug
    context = fetch_session_context()
    project_id = project_from_session_context(context)
    if not project or environment_slug == "development":
        environment_slug = environment_from_session_context(context, default=environment_slug)
    return project_id, environment_slug


@panels_app.command("list")
def panels_list(
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    out = _console()
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{api.rstrip('/')}/v1/panel-definitions",
            headers=_service_headers(project_root, token or None),
        )
    payload = _raise_for_status(response)
    if json_output:
        out.print_json(data=payload)
        return
    for row in payload.get("definitions", []):
        out.print(
            f"{row.get('id')}  {row.get('key')}  {row.get('displayName')}  status={row.get('status')}"
        )


@panels_app.command("create")
def panels_create(
    key: str = typer.Option(..., "--key"),
    display_name: str = typer.Option(..., "--display-name"),
    capability_key: str = typer.Option("image.generate.v1", "--capability-key"),
    origin: list[str] = typer.Option([], "--origin", help="Allowed origin (repeatable)"),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    out = _console()
    if not origin:
        out.print("[red]At least one --origin is required[/red]")
        raise typer.Exit(USAGE)
    body = {
        "key": key,
        "displayName": display_name,
        "capabilityKey": capability_key,
        "allowedOrigins": origin,
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{api.rstrip('/')}/v1/panel-definitions",
            headers=_service_headers(project_root, token or None),
            json=body,
        )
    payload = _raise_for_status(response)
    if json_output:
        out.print_json(data=payload)
        return
    out.print(f"[green]Created[/green] {payload.get('id')} key={payload.get('key')}")


@panels_app.command("show")
def panels_show(
    definition_id: str = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    out = _console()
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{api.rstrip('/')}/v1/panel-definitions/{definition_id}",
            headers=_service_headers(project_root, token or None),
        )
    payload = _raise_for_status(response)
    if json_output:
        out.print_json(data=payload)
        return
    out.print_json(data=payload)


@session_app.command("create")
def panels_session_create(
    project: str = typer.Option("", "--project"),
    environment: str = typer.Option("development", "--environment"),
    definition_id: str = typer.Option("", "--definition-id"),
    definition_key: str = typer.Option("", "--definition-key"),
    origin: list[str] = typer.Option([], "--origin", help="Allowed origin (repeatable)"),
    max_spend_micros: int = typer.Option(2_000_000, "--max-spend-micros"),
    max_jobs: int = typer.Option(10, "--max-jobs"),
    expires_in_minutes: int = typer.Option(60, "--expires-in-minutes"),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    out = _console()
    if not origin:
        out.print("[red]At least one --origin is required[/red]")
        raise typer.Exit(USAGE)
    if not definition_id and not definition_key:
        out.print("[red]Pass --definition-id or --definition-key[/red]")
        raise typer.Exit(USAGE)
    try:
        project_id, environment_slug = _resolve_project(project_root, project, environment)
    except SessionClientError as exc:
        out.print(f"[red]{exc}[/red]")
        raise typer.Exit(AUTH if exc.status_code == 401 else USAGE) from exc
    if not project_id:
        out.print("[red]No projectId. Pass --project or run configure.[/red]")
        raise typer.Exit(USAGE)
    body: dict[str, Any] = {
        "projectId": project_id,
        "environment": environment_slug,
        "allowedOrigins": origin,
        "maxSpendMicros": max_spend_micros,
        "maxJobs": max_jobs,
        "expiresInMinutes": expires_in_minutes,
    }
    if definition_id:
        body["panelDefinitionId"] = definition_id
    if definition_key:
        body["panelDefinitionKey"] = definition_key
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{api.rstrip('/')}/v1/panel-sessions",
            headers=_service_headers(project_root, token or None),
            json=body,
        )
    payload = _raise_for_status(response)
    if json_output:
        print(json.dumps(payload), file=sys.stdout)
        print(
            "WARNING: stdout contains a secret access token.",
            file=sys.stderr,
        )
        return
    out.print(f"[green]Session[/green] {payload.get('sessionId')}")
    out.print(f"Access token (show once): {payload.get('accessToken')}")


@session_app.command("show")
def panels_session_show(
    session_id: str = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    out = _console()
    with httpx.Client(timeout=30.0) as client:
        response = client.get(
            f"{api.rstrip('/')}/v1/panel-sessions/{session_id}",
            headers=_service_headers(project_root, token or None),
        )
    payload = _raise_for_status(response)
    if json_output:
        out.print_json(data=payload)
        return
    out.print_json(data=payload)


@session_app.command("open")
def panels_session_open(
    session_id: str = typer.Argument(...),
    app_url: str = typer.Option(DEFAULT_APP_BASE_URL, "--app-url"),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    out = _console()
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{api.rstrip('/')}/v1/panel-sessions/{session_id}/launch-codes",
            headers=_service_headers(project_root, token or None),
        )
    payload = _raise_for_status(response)
    launch_code = str(payload.get("launchCode") or "")
    url = f"{app_url.rstrip('/')}/panel/{session_id}#lc={launch_code}"
    if json_output:
        out.print_json(data={"url": url, "launchCode": launch_code, "sessionId": session_id})
        return
    out.print(f"[green]Opening[/green] {url}")
    webbrowser.open(url)


@session_app.command("revoke")
def panels_session_revoke(
    session_id: str = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    out = _console()
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{api.rstrip('/')}/v1/panel-sessions/{session_id}/revoke",
            headers=_service_headers(project_root, token or None),
        )
    payload = _raise_for_status(response)
    if json_output:
        out.print_json(data=payload)
        return
    out.print(f"[green]Revoked[/green] {payload.get('id')}")
