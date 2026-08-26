"""Session-authenticated connections adopt (advanced plumbing)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import typer
from rich.console import Console

from hydracept.cli.exit_codes import AUTH, USAGE
from hydracept.cli.provider_discovery import PROVIDER_ENV_ALLOWLIST, discover_provider
from hydracept.cli.project import load_project_binding
from hydracept.cli.session_client import SessionClientError, _session_headers
from hydracept.cli.session_store import SESSION_EXPIRED_MESSAGE, load_session
from hydracept.cli.workspace import DEFAULT_API

connections_app = typer.Typer(help="Provider connections (human session or setup grant).")


def _adopt_payload(
    *,
    provider: str,
    secret: str,
    project_id: str,
    environment: str,
    replace: bool,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "secret": secret,
        "label": "default",
        "bootstrapMode": "manual_api_key",
        "autoBind": True,
        "replaceExisting": replace,
        "projectId": project_id,
        "environment": environment,
    }


def adopt_provider_secret(
    *,
    provider: str,
    secret: str,
    project_id: str,
    environment: str,
    replace: bool = False,
    setup_grant: str | None = None,
) -> dict[str, Any]:
    if setup_grant:
        headers = {
            "Authorization": f"Bearer {setup_grant.strip()}",
            "Content-Type": "application/json",
        }
        url = f"{DEFAULT_API.rstrip('/')}/v1/connections"
    else:
        session = load_session()
        if session is None:
            raise SessionClientError(SESSION_EXPIRED_MESSAGE, status_code=401)
        headers = _session_headers(session)
        url = f"{session.app_base_url}/v1/connections"

    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            url,
            headers=headers,
            json=_adopt_payload(
                provider=provider,
                secret=secret,
                project_id=project_id,
                environment=environment,
                replace=replace,
            ),
        )
    if response.status_code == 401:
        raise SessionClientError(SESSION_EXPIRED_MESSAGE, status_code=401)
    if response.status_code == 409:
        body = response.json()
        detail = body.get("detail") if isinstance(body, dict) else body
        raise SessionClientError(str(detail), status_code=409)
    if response.is_error:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise SessionClientError(str(detail), status_code=response.status_code)
    payload = response.json()
    if not isinstance(payload, dict):
        return {"result": "connected"}
    connection = payload.get("connection") or payload
    action = str(connection.get("action") or "connected")
    return {
        "provider": provider,
        "result": action,
        "connectionId": connection.get("id"),
    }


def adopt_from_env(
    project_root: Path,
    *,
    providers: list[str] | None = None,
    env_file: Path | None = None,
    replace: bool = False,
    setup_grant: str | None = None,
) -> list[dict[str, Any]]:
    binding = load_project_binding(project_root)
    project_id = str(binding.get("projectId") or "").strip()
    environment = str(binding.get("environment") or "development").strip() or "development"
    if not project_id:
        raise SessionClientError("projectId required in .hydracept/project.json", status_code=USAGE)

    target_providers = providers or list(PROVIDER_ENV_ALLOWLIST.keys())
    results: list[dict[str, Any]] = []
    for provider in target_providers:
        discovered = discover_provider(provider, project_root, extra_env_file=env_file)
        if discovered is None:
            results.append({"provider": provider, "result": "skipped", "reason": "not_found"})
            continue
        outcome = adopt_provider_secret(
            provider=provider,
            secret=discovered.secret,
            project_id=project_id,
            environment=environment,
            replace=replace,
            setup_grant=setup_grant,
        )
        results.append(
            {
                "provider": provider,
                "source": discovered.source,
                "envVar": discovered.env_var,
                **outcome,
            }
        )
    return results


@connections_app.command("adopt")
def connections_adopt_cmd(
    from_env: bool = typer.Option(False, "--from-env"),
    from_env_file: Path | None = typer.Option(None, "--from-env-file"),
    provider: str = typer.Option("", "--provider"),
    replace: bool = typer.Option(False, "--replace"),
    setup_grant_env: str = typer.Option("", "--setup-grant-env"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    out = Console()
    if not from_env and from_env_file is None:
        out.print("[red]Specify --from-env or --from-env-file[/red]")
        raise typer.Exit(USAGE)

    grant = (os.environ.get(setup_grant_env) or "").strip() if setup_grant_env else ""
    providers = [provider] if provider else None
    try:
        if from_env_file is not None:
            results = adopt_from_env(
                project_root,
                providers=providers,
                env_file=from_env_file,
                replace=replace,
                setup_grant=grant or None,
            )
        else:
            results = adopt_from_env(
                project_root,
                providers=providers,
                replace=replace,
                setup_grant=grant or None,
            )
    except SessionClientError as exc:
        out.print(f"[red]{exc}[/red]")
        raise typer.Exit(AUTH if exc.status_code == 401 else USAGE) from exc

    payload = {"adopted": results}
    if json_output:
        print(json.dumps(payload), file=sys.stdout)
        return
    for row in results:
        out.print(f"{row.get('provider')}: {row.get('result')}")
