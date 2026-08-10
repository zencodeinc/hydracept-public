"""Public Hydracept CLI — device login, init, doctor, capabilities, jobs, consumer-check."""

from __future__ import annotations

import json
import os
import stat
import time
import webbrowser
from pathlib import Path
from typing import Any

import httpx
import typer
from rich.console import Console

from hydracept import HydraceptClient
from hydracept.cli.doctor import DEFAULT_SMOKE_CAPABILITY, run_doctor
from hydracept.cli.workspace import (
    auth_headers,
    config_dir,
    config_path,
    DEFAULT_API,
    read_json,
    resolve_token,
    secrets_path,
)
from hydracept.consumer_boundary import scan_path

app = typer.Typer(help="Hydracept public CLI — AI execution infrastructure for games.")
capabilities_app = typer.Typer(help="Capability discovery and invoke")
jobs_app = typer.Typer(help="Durable jobs")
app.add_typer(capabilities_app, name="capabilities")
app.add_typer(jobs_app, name="jobs")
console = Console()


def _write_secrets(project_root: Path, payload: dict[str, Any]) -> Path:
    path = secrets_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_json(path)
    existing.update(payload)
    path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return path


def _ensure_gitignore(project_root: Path) -> None:
    gitignore = project_root / ".gitignore"
    hints = [".hydracept/secrets.json", ".hydracept/*.env", ".env.hydracept"]
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    additions = [h for h in hints if h not in existing]
    if not additions:
        return
    with gitignore.open("a", encoding="utf-8") as handle:
        handle.write("\n# Hydracept local secrets\n")
        for hint in additions:
            handle.write(f"{hint}\n")
    console.print(f"[green]Updated[/green] {gitignore}")


def _resolve_token(project_root: Path, token: str | None) -> str:
    return resolve_token(project_root, token)


def _auth_headers(token: str) -> dict[str, str]:
    return auth_headers(token)


@app.command("login")
def login_cmd(
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
) -> None:
    """Authenticate a human via device authorization (headless-friendly)."""
    start = httpx.post(f"{api.rstrip('/')}/v1/auth/device/start", timeout=30.0)
    start.raise_for_status()
    payload = start.json()
    user_code = payload.get("userCode") or payload.get("user_code")
    verification = (
        payload.get("verificationUri")
        or payload.get("verification_uri")
        or f"{api.rstrip('/')}/device"
    )
    console.print("[bold]Starting Hydracept authentication...[/bold]")
    if user_code and "user_code=" not in str(verification):
        sep = "&" if "?" in str(verification) else "?"
        verification = f"{verification}{sep}user_code={user_code}"
    console.print(f"Open: [cyan]{verification}[/cyan]")
    console.print(f"Code: [bold]{user_code}[/bold]")
    if open_browser:
        try:
            webbrowser.open(str(verification))
        except Exception:
            pass
    device_code = payload.get("deviceCode") or payload.get("device_code")
    while True:
        token_resp = httpx.post(
            f"{api.rstrip('/')}/v1/auth/device/token",
            json={"deviceCode": device_code},
            timeout=30.0,
        )
        if token_resp.status_code == 428:
            time.sleep(2)
            continue
        token_resp.raise_for_status()
        data = token_resp.json()
        token = data.get("token")
        if not token:
            console.print("[red]No token in device response[/red]")
            raise typer.Exit(1)
        _write_secrets(project_root, {"token": token, "kind": "human_session"})
        _ensure_gitignore(project_root)
        console.print("[green]Signed in[/green] (human session). Run [bold]hydracept init[/bold] next.")
        break


@app.command("init")
def init_cmd(
    apply: bool = typer.Option(False, "--apply"),
    yes: bool = typer.Option(False, "--yes"),
    print_env: bool = typer.Option(False, "--print-env"),
    rotate: bool = typer.Option(False, "--rotate"),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
) -> None:
    """Idempotent project bootstrap. login = human; init = service principal."""
    cfg_dir = config_dir(project_root)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = config_path(project_root)
    secrets = read_json(secrets_path(project_root))
    human_token = str(secrets.get("token") or "")
    if not human_token:
        console.print("[red]No human session. Run hydracept login first.[/red]")
        raise typer.Exit(1)

    config: dict[str, Any] = {
        "apiBaseUrl": api.rstrip("/"),
        "environment": "development",
        "detectedStack": _detect_stack(project_root),
    }
    if cfg_path.exists():
        config = {**read_json(cfg_path), **config}

    try:
        context = httpx.get(
            f"{api.rstrip('/')}/v1/session/context",
            headers=_auth_headers(human_token),
            timeout=30.0,
        )
        if context.status_code == 200:
            ctx = context.json()
            if ctx.get("productId"):
                config["productId"] = ctx["productId"]
            env = ctx.get("environment")
            if isinstance(env, dict) and env.get("slug"):
                config["environment"] = env["slug"]
            project = ctx.get("project")
            if isinstance(project, dict):
                config["projectId"] = project.get("id")
                config["projectName"] = project.get("displayName")
            org = ctx.get("organization")
            if isinstance(org, dict):
                config["organizationId"] = org.get("id")
                config["organizationName"] = org.get("displayName")
    except httpx.HTTPError as exc:
        console.print(f"[yellow]session/context unavailable:[/yellow] {exc}")

    cfg_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    console.print(f"[green]Wrote[/green] {cfg_path}")

    existing_key = str(secrets.get("apiKey") or "")
    if existing_key and not rotate and apply:
        console.print("[green]Reusing existing project API credential[/green]")
        if print_env:
            console.print(f"HYDRACEPT_API_KEY={existing_key}")
        return

    if not apply:
        console.print("Run with --apply to create/select a project API credential.")
        return
    if not yes:
        console.print("Refusing --apply without --yes")
        raise typer.Exit(1)

    # Prefer Free bootstrap when org missing
    api_key: str | None = existing_key or None
    if not api_key or rotate:
        bootstrap = httpx.post(
            f"{api.rstrip('/')}/v1/onboarding/bootstrap-free",
            headers=_auth_headers(human_token),
            json={},
            timeout=60.0,
        )
        if bootstrap.status_code < 400:
            body = bootstrap.json()
            api_key = (
                body.get("apiKey")
                or body.get("token")
                or (body.get("credential") or {}).get("secret")
            )
            if body.get("projectId"):
                config["projectId"] = body["projectId"]
            if body.get("organizationId"):
                config["organizationId"] = body["organizationId"]
            cfg_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        elif not api_key:
            console.print(
                f"[red]bootstrap-free failed ({bootstrap.status_code}). "
                "Create an API key in Studio or retry after Free activation.[/red]"
            )
            raise typer.Exit(1)

    if api_key:
        written_secrets = _write_secrets(
            project_root,
            {"apiKey": api_key, "kind": "service_principal"},
        )
        _ensure_gitignore(project_root)
        env_path = cfg_dir / "local.env"
        env_path.write_text(
            f"HYDRACEPT_API_URL={api.rstrip('/')}\n"
            f"HYDRACEPT_API_KEY={api_key}\n"
            f"HYDRACEPT_PROJECT={config.get('projectId') or ''}\n"
            f"HYDRACEPT_ENVIRONMENT={config.get('environment') or 'development'}\n",
            encoding="utf-8",
        )
        try:
            env_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        console.print(f"[green]Wrote credential to[/green] {written_secrets} and {env_path}")
        if print_env:
            console.print(f"HYDRACEPT_API_KEY={api_key}")
        else:
            console.print("[dim]API key not printed (use --print-env to display).[/dim]")


def _detect_stack(project_root: Path) -> str:
    is_dotnet = any(project_root.glob("*.csproj")) or (project_root / "Assets").exists()
    is_unity = (project_root / "Assets").exists() and (project_root / "ProjectSettings").exists()
    if is_unity:
        return "unity"
    if is_dotnet:
        return "dotnet"
    if (project_root / "package.json").exists():
        return "node"
    if (project_root / "pyproject.toml").exists() or (project_root / "requirements.txt").exists():
        return "python"
    return "unknown"


@app.command("doctor")
def doctor_cmd(
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    smoke_capability: str = typer.Option(
        DEFAULT_SMOKE_CAPABILITY,
        "--smoke-capability",
        help="Launch smoke capability to verify (default: image.generate.v1)",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable report"),
) -> None:
    """Verify API health, auth, config alignment, providers, and launch smoke readiness."""
    code = run_doctor(
        api,
        project_root,
        token or None,
        smoke_capability=smoke_capability,
        json_output=json_output,
        console=console,
    )
    if code != 0:
        raise typer.Exit(code)


@app.command("agent-context")
def agent_context_cmd(
    api: str = typer.Option(DEFAULT_API, "--api"),
    output: Path = typer.Option(Path(".hydracept/agent-context.json"), "--output"),
) -> None:
    response = httpx.get(f"{api.rstrip('/')}/v1/agent-context", timeout=60.0)
    response.raise_for_status()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(response.json(), indent=2), encoding="utf-8")
    console.print(f"[green]Wrote[/green] {output}")


@app.command("health")
def health_cmd(api: str = typer.Option(DEFAULT_API, "--api")) -> None:
    response = httpx.get(f"{api.rstrip('/')}/healthz", timeout=15.0)
    response.raise_for_status()
    console.print_json(data=response.json())


@app.command("consumer-check")
def consumer_check_cmd(
    path: Path = typer.Option(Path.cwd(), "--path"),
    strict: bool = typer.Option(False, "--strict"),
) -> None:
    code, detail = scan_path(path)
    if code != 0:
        console.print(detail)
        raise typer.Exit(1)
    console.print(f"[green]{detail}[/green]")
    if strict:
        console.print("[green]Consumer boundary check passed[/green]")


@capabilities_app.command("list")
def capabilities_list(
    api: str = typer.Option(DEFAULT_API, "--api"),
) -> None:
    response = httpx.get(f"{api.rstrip('/')}/v1/capabilities", timeout=30.0)
    response.raise_for_status()
    console.print_json(data=response.json())


@capabilities_app.command("describe")
def capabilities_describe(
    key: str = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
) -> None:
    response = httpx.get(f"{api.rstrip('/')}/v1/capabilities/{key}", timeout=30.0)
    response.raise_for_status()
    console.print_json(data=response.json())


@capabilities_app.command("invoke")
def capabilities_invoke(
    key: str = typer.Argument(...),
    body: Path = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
) -> None:
    resolved = _resolve_token(project_root, token or None)
    payload = json.loads(body.read_text(encoding="utf-8"))
    client = HydraceptClient(api, resolved)
    console.print_json(data=client.invoke_capability(key, payload))


@jobs_app.command("submit")
def jobs_submit(
    capability_key: str = typer.Argument(...),
    body: Path = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    watch: bool = typer.Option(False, "--watch"),
) -> None:
    resolved = _resolve_token(project_root, token or None)
    payload = json.loads(body.read_text(encoding="utf-8"))
    client = HydraceptClient(api, resolved)
    data = client.submit_capability_job(capability_key, payload)
    console.print_json(data=data)
    if not watch:
        return
    job_id = data.get("jobId") or data.get("executionId")
    while job_id:
        status = client.get_job(str(job_id))
        state = status.get("status") or status.get("currentStatus")
        console.print(state)
        if str(state).lower() in {"succeeded", "failed", "canceled", "cancelled"}:
            console.print_json(data=status)
            break
        time.sleep(2)


@jobs_app.command("get")
def jobs_get(
    job_id: str = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
) -> None:
    client = HydraceptClient(api, _resolve_token(project_root, token or None))
    console.print_json(data=client.get_job(job_id))


@jobs_app.command("receipt")
def jobs_receipt(
    job_id: str = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
) -> None:
    client = HydraceptClient(api, _resolve_token(project_root, token or None))
    console.print_json(data=client.get_job_receipt(job_id))


@jobs_app.command("cancel")
def jobs_cancel(
    job_id: str = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
) -> None:
    client = HydraceptClient(api, _resolve_token(project_root, token or None))
    console.print_json(data=client.cancel_job(job_id))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
