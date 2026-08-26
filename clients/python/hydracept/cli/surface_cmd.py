"""Public CLI for installing project surfaces.

Supported path: `hydracept surface apply PATH`.
Does not expose project-operations persistence as the agent authoring API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import typer
from rich.console import Console

from hydracept.cli.exit_codes import AUTH, USAGE
from hydracept.cli.panels_cmd import _raise_for_status, _service_headers
from hydracept.cli.project_agent import ProjectAgentError, resolve_bound_project_id
from hydracept.cli.session_client import SessionClientError
from hydracept.cli.surface_definition import (
    SURFACE_APPLY_SCHEMA_VERSION,
    SurfaceDefinitionError,
    apply_body_from_definition,
    load_surface_file,
)
from hydracept.cli.workspace import DEFAULT_API, resolve_token

surface_app = typer.Typer(help="Author and install project surfaces")


def _console() -> Console:
    return Console()


def apply_surface(
    path: Path,
    *,
    api: str,
    project_root: Path,
    token: str | None,
    http_client: Any | None = None,
) -> dict[str, Any]:
    body = apply_body_from_definition(load_surface_file(path))
    resolved = (token or "").strip() or resolve_token(project_root, token)
    if not resolved:
        raise SessionClientError(
            "No API credential. Run python -m hydracept login or pass --token.",
            status_code=401,
        )
    try:
        project_id = resolve_bound_project_id(project_root, token=resolved)
    except ProjectAgentError as exc:
        raise SurfaceDefinitionError(str(exc)) from exc
    body["projectId"] = project_id
    headers = _service_headers(project_root, resolved)
    base = api.rstrip("/")
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=30.0)
    list_url = f"{base}/v1/panel-definitions?projectId={project_id}"
    try:
        listed = _raise_for_status(client.get(list_url, headers=headers))
        existing = _definition_by_key(listed, body["key"])
        if existing is not None:
            origin = str(existing.get("origin") or "")
            if origin == "hydracept":
                raise SurfaceDefinitionError(
                    f"Refusing to overwrite Hydracept-owned surface {body['key']!r}"
                )
            definition_id = str(existing.get("id") or "")
            if not definition_id:
                raise SurfaceDefinitionError("Existing surface is missing id")
            payload = _raise_for_status(
                client.patch(
                    f"{base}/v1/panel-definitions/{definition_id}",
                    headers=headers,
                    json=_patch_body(body),
                )
            )
            return _apply_result(payload, status="updated")
        created = client.post(
            f"{base}/v1/panel-definitions",
            headers=headers,
            json=body,
        )
        if created.status_code == 409:
            listed = _raise_for_status(client.get(list_url, headers=headers))
            raced = _definition_by_key(listed, body["key"])
            if raced is None or not raced.get("id"):
                raise SessionClientError(
                    "Panel definition key already exists", status_code=409
                )
            payload = _raise_for_status(
                client.patch(
                    f"{base}/v1/panel-definitions/{raced['id']}",
                    headers=headers,
                    json=_patch_body(body),
                )
            )
            return _apply_result(payload, status="updated")
        payload = _raise_for_status(created)
        return _apply_result(payload, status="created")
    finally:
        if owns_client:
            client.close()


def _patch_body(body: dict[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {
        "displayName": body["displayName"],
        "origin": "project",
        "actions": body["actions"],
    }
    for field in ("allowedOrigins", "presentation", "policy"):
        if field in body:
            patch[field] = body[field]
    return patch


def _definition_by_key(listed: dict[str, Any], key: str) -> dict[str, Any] | None:
    rows = listed.get("definitions")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and row.get("key") == key:
            return row
    return None


def project_tools_fingerprint(project_root: Path) -> str:
    """Detect local surface JSON or manifest allowlist edits during `project up`."""
    root = Path(project_root) / "tools" / "hydracept"
    parts: list[str] = []
    manifest = root / "manifest.json"
    if manifest.is_file():
        stat = manifest.stat()
        parts.append(f"manifest:{stat.st_mtime_ns}:{stat.st_size}")
    surfaces = root / "surfaces"
    if surfaces.is_dir():
        for path in sorted(surfaces.glob("*.json")):
            stat = path.stat()
            parts.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
    return "|".join(parts)


def apply_project_surfaces(
    *,
    api: str,
    project_root: Path,
    token: str | None,
    http_client: Any | None = None,
) -> list[dict[str, Any]]:
    """Apply every JSON file in tools/hydracept/surfaces/."""
    surfaces_dir = Path(project_root) / "tools" / "hydracept" / "surfaces"
    if not surfaces_dir.is_dir():
        return []
    results: list[dict[str, Any]] = []
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=30.0)
    try:
        for path in sorted(surfaces_dir.glob("*.json")):
            results.append(
                apply_surface(
                    path,
                    api=api,
                    project_root=project_root,
                    token=token,
                    http_client=client,
                )
            )
    finally:
        if owns_client:
            client.close()
    return results


def _apply_result(payload: dict[str, Any], *, status: str) -> dict[str, Any]:
    current = payload.get("currentVersion")
    version = current.get("version") if isinstance(current, dict) else None
    return {
        "schemaVersion": SURFACE_APPLY_SCHEMA_VERSION,
        "status": status,
        "id": payload.get("id"),
        "key": payload.get("key"),
        "displayName": payload.get("displayName"),
        "origin": payload.get("origin") or "project",
        "version": version,
    }


@surface_app.command("apply")
def surface_apply_cmd(
    path: Path = typer.Argument(..., exists=True, readable=True, dir_okay=False),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Validate a surface JSON file and create or update it idempotently."""
    out = _console()
    try:
        result = apply_surface(
            path,
            api=api,
            project_root=project_root,
            token=token or None,
        )
    except SurfaceDefinitionError as exc:
        out.print(f"[red]{exc}[/red]")
        raise typer.Exit(USAGE) from exc
    except SessionClientError as exc:
        out.print(f"[red]{exc}[/red]")
        raise typer.Exit(AUTH if exc.status_code == 401 else USAGE) from exc
    if json_output:
        out.print_json(data=result)
        return
    verb = "Updated" if result["status"] == "updated" else "Created"
    out.print(
        f"[green]{verb}[/green] {result.get('id')} key={result.get('key')} "
        f"origin={result.get('origin')} version={result.get('version')}"
    )
