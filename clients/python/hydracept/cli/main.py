"""Public Hydracept CLI — device login, configure, doctor, capabilities, jobs, consumer-check."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import typer
import yaml
from hydracept import HydraceptClient, __version__
from hydracept.errors import HydraceptApiError, raise_api_status
from hydracept.cli.agent_status import build_agent_status
from hydracept.cli.agents.detect import detect_all
from hydracept.cli.agents.install import install_agent_pack
from hydracept.cli.agents.uninstall import uninstall_agent_pack
from hydracept.cli.bootstrap import ConfigureError, run_configure
from hydracept.cli.console_io import cli_console
from hydracept.cli.doctor import DEFAULT_SMOKE_CAPABILITY, run_doctor
from hydracept.cli.exit_codes import NOT_READY, SMOKE_FAILED, USAGE
from hydracept.cli.keys_cmd import keys_app
from hydracept.cli.panels_cmd import panels_app
from hydracept.cli.project_cmd import project_app
from hydracept.cli.surface_cmd import surface_app
from hydracept.cli.storage_cmd import storage_app
from hydracept.cli.connections_cmd import connections_app
from hydracept.cli.integrations.unity import UnityInstallError, install_unity_package
from hydracept.cli.init_resolver import run_init, unified_bootstrap_enabled
from hydracept.cli.login_flow import LoginError, login_device, login_with_token
from hydracept.cli.quickstart import run_quickstart
from hydracept.cli.setup_grant_cmd import setup_grant_app
from hydracept.cli.session_store import DEFAULT_APP_BASE_URL
from hydracept.cli.smoke_runner import (
    DEFAULT_SMOKE_PROMPT,
    SmokeError,
    run_sheet_smoke,
    run_smoke,
)
from hydracept.cli.verify import (
    DEFAULT_LOCKFILE,
    all_passed,
    format_checks,
    is_manifest,
    load_document,
    structural_lockfile_checks,
    structural_manifest_checks,
)
from hydracept.cli.job_context import merge_workspace_job_context
from hydracept.cli.workspace import (
    DEFAULT_API,
    CliOverrides,
    config_path,
    read_json,
    resolve_token,
    resolve_workspace,
)
from hydracept.consumer_boundary import scan_path

app = typer.Typer(help="Hydracept public CLI — AI execution control plane.")
capabilities_app = typer.Typer(help="Capability discovery and invoke")
capability_request_app = typer.Typer(help="Non-binding capability implementation requests")
jobs_app = typer.Typer(help="Durable jobs")
pinned_app = typer.Typer(help="Pinned Execution (RIP)")
lockfile_app = typer.Typer(help="AI lockfile — stable execution dependency")
mcp_app = typer.Typer(help="Model Context Protocol server")
smoke_app = typer.Typer(
    help="Launch smoke contracts (trial budget or BYOK)",
    invoke_without_command=True,
)
agents_app = typer.Typer(help="Agent Pack install and detection")
integrations_app = typer.Typer(help="Game engine integrations")
integrations_install_app = typer.Typer(help="Install engine packages")
integrations_app.add_typer(integrations_install_app, name="install")
app.add_typer(capabilities_app, name="capabilities")
app.add_typer(capability_request_app, name="capability-request")
app.add_typer(jobs_app, name="jobs")
app.add_typer(pinned_app, name="pinned")
app.add_typer(lockfile_app, name="lockfile")
app.add_typer(keys_app, name="keys")
app.add_typer(storage_app, name="storage")
app.add_typer(panels_app, name="panels")
app.add_typer(surface_app, name="surface")
app.add_typer(project_app, name="project")
app.add_typer(mcp_app, name="mcp")
app.add_typer(smoke_app, name="smoke")
app.add_typer(agents_app, name="agents")
app.add_typer(integrations_app, name="integrations")
app.add_typer(connections_app, name="connections")
app.add_typer(setup_grant_app, name="setup-grant")
console = cli_console()


def _cli_json(response: httpx.Response) -> Any:
    try:
        raise_api_status(response)
    except HydraceptApiError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    return response.json()


def _version_callback(value: bool) -> None:
    if value:
        console.print(__version__)
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the hydracept package version and exit.",
    ),
) -> None:
    """Hydracept public CLI — AI execution control plane."""


def _resolve_token(project_root: Path, token: str | None) -> str:
    return resolve_token(project_root, token)


@app.command("login")
def login_cmd(
    api: str = typer.Option(DEFAULT_API, "--api", help="Runtime API URL (legacy)"),
    app_url: str = typer.Option(DEFAULT_APP_BASE_URL, "--app-url"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    open_browser: bool = typer.Option(True, "--open/--no-open"),
    token: str = typer.Option(
        "",
        "--token",
        help="Paste API key from https://hydracept.com/start (agent-friendly, no browser).",
    ),
) -> None:
    """Authenticate via device authorization or --token (API key paste)."""
    pasted = (token or "").strip()
    if pasted:
        try:
            login_with_token(project_root, pasted, console=console)
        except LoginError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(exc.exit_code) from exc
        return
    try:
        login_device(project_root, api, app_url=app_url, open_browser=open_browser, console=console)
    except LoginError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(exc.exit_code) from exc


@app.command("configure")
def configure_cmd(
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    rotate: bool = typer.Option(False, "--rotate"),
    print_env: bool = typer.Option(False, "--print-env"),
) -> None:
    """Reconcile workspace until ready (idempotent)."""
    try:
        result = run_configure(
            project_root,
            api_url=api,
            token=token or None,
            rotate=rotate,
        )
    except ConfigureError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(exc.exit_code) from exc
    console.print(f"[green]Wrote[/green] {result.config_path}")
    if print_env:
        console.print(f"HYDRACEPT_API_KEY={result.workspace.token}")
    console.print("[bold]Next[/bold] → python -m hydracept doctor → python -m hydracept smoke")


@app.command("init")
def init_cmd(
    apply: bool = typer.Option(False, "--apply"),
    yes: bool = typer.Option(False, "--yes"),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    json_output: bool = typer.Option(False, "--json"),
    ci_mode: bool = typer.Option(False, "--ci"),
    env_file: Path | None = typer.Option(None, "--env-file"),
    setup_grant_env: str = typer.Option("", "--setup-grant-env"),
    wait: bool = typer.Option(
        False,
        "--wait",
        help="Wait for browser connect flow (use with --json for agents)",
    ),
    poll_seconds: int = typer.Option(900, "--poll-seconds", help="Max seconds to wait with --wait"),
    project_name: str = typer.Option(
        "",
        "--project-name",
        help="Suggested Hydracept project name (default: folder name or HYDRACEPT_PROJECT_NAME)",
    ),
) -> None:
    """Idempotent universal bootstrap resolver (ADR-028)."""
    if unified_bootstrap_enabled():
        grant = (os.environ.get(setup_grant_env) or "").strip() if setup_grant_env else None
        suggested = (project_name or "").strip() or None
        result = run_init(
            project_root,
            api_url=api,
            apply=apply or yes,
            yes=yes,
            json_output=json_output,
            ci_mode=ci_mode,
            env_file=env_file,
            setup_grant=grant,
            wait=wait,
            poll_seconds=poll_seconds,
            project_name=suggested,
        )
        if json_output:
            console.print_json(data=result.payload)
        elif wait and result.payload.get("status") not in {"ready", "interaction_required"}:
            console.print_json(data=result.payload)
        elif result.payload.get("status") == "ready":
            console.print("[green]Hydracept ready[/green]")
        elif result.payload.get("status") == "interaction_required":
            action = result.payload.get("action") or {}
            reason = str(result.payload.get("reason") or "setup")
            url = str(action.get("url") or "").strip()
            console.print("[bold yellow]Action required[/bold yellow]")
            if reason == "authentication":
                console.print("Sign in to connect this workspace to Hydracept.")
                console.print(
                    "[dim]If you use multiple GitHub or Google accounts, pick the right one on the connect page.[/dim]"
                )
            elif reason == "bootstrap_wait_timeout":
                console.print("Browser setup did not finish in time.")
            elif reason == "project_selection":
                console.print("Choose a project and approve setup in your browser.")
            elif reason == "provider_connection_conflict":
                console.print("Resolve the provider connection conflict in your browser.")
            else:
                console.print("Complete setup in your browser.")
            if url:
                console.print(f"\n[link={url}]{url}[/link]")
            wait_cmd = str(action.get("waitCommand") or "").strip()
            if wait_cmd and not wait:
                console.print(f"\nOr run [bold]{wait_cmd}[/bold] after opening the link.")
            elif wait and reason == "bootstrap_wait_timeout":
                console.print("\n[dim]Open the link, complete setup, then retry with --wait.[/dim]")
        else:
            console.print_json(data=result.payload)
        raise typer.Exit(result.exit_code)

    if not apply:
        console.print("Run init --apply --yes (or enable unified bootstrap).")
        raise typer.Exit(USAGE)
    if not yes:
        console.print("Refusing --apply without --yes")
        raise typer.Exit(USAGE)
    configure_cmd(api=api, project_root=project_root, token="", rotate=False, print_env=False)


@app.command("quickstart")
def quickstart_cmd(
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str | None = typer.Option(
        None,
        "--token",
        help="API key from https://hydracept.com/start",
    ),
    smoke: bool = typer.Option(False, "--smoke", help="Run public smoke after doctor"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    smoke_capability: str = typer.Option(DEFAULT_SMOKE_CAPABILITY, "--smoke-capability"),
) -> None:
    """login + configure + doctor (+ optional --smoke). Monotonic, fail-fast."""
    if unified_bootstrap_enabled() and token is None and not smoke:
        init_result = run_init(
            project_root,
            api_url=api,
            apply=True,
            yes=True,
            json_output=json_output,
        )
        if json_output:
            console.print_json(data=init_result.payload)
        raise typer.Exit(init_result.exit_code)
    result = run_quickstart(
        project_root,
        api_url=api,
        token=token,
        run_smoke_step=smoke,
        smoke_capability=smoke_capability,
        json_output=json_output,
        console=console,
    )
    if json_output:
        console.print_json(data=result.payload)
    raise typer.Exit(result.exit_code)


def _print_smoke(result: Any, *, json_output: bool) -> None:
    if json_output:
        console.print_json(data=result.to_json())
        return
    if result.receipt:
        console.print_json(data=result.receipt)
    console.print(f"[green]Smoke succeeded[/green] jobId={result.job_id}")
    if result.demo_path:
        console.print(f"saved={result.demo_path}")


def _print_smoke_error(exc: SmokeError, *, json_output: bool) -> None:
    if json_output:
        console.print_json(data=exc.to_json())
        return
    console.print(f"[red]{exc}[/red]")
    if exc.job_id:
        console.print(f"jobId={exc.job_id}")
    if exc.receipt_id:
        console.print(f"receiptId={exc.receipt_id}")
    if exc.demo_path:
        console.print(f"saved={exc.demo_path}")
    for path in exc.downloads:
        console.print(f"saved={path}")


@smoke_app.callback()
def smoke_root(
    ctx: typer.Context,
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    capability: str = typer.Option(DEFAULT_SMOKE_CAPABILITY, "--capability"),
    prompt: str = typer.Option(DEFAULT_SMOKE_PROMPT, "--prompt"),
    poll_seconds: int = typer.Option(90, "--poll-seconds"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Submit the launch smoke job. Default is `image`."""
    ctx.obj = {
        "api": api,
        "project_root": project_root,
        "token": token,
        "capability": capability,
        "prompt": prompt,
        "poll_seconds": poll_seconds,
        "json_output": json_output,
    }
    if ctx.invoked_subcommand is None:
        smoke_image_cmd(ctx)


@smoke_app.command("image")
def smoke_image_cmd(ctx: typer.Context) -> None:
    """Image smoke: generation, pricing, durability, SHA-256, PNG alpha, receipt."""
    opts = ctx.obj or {}
    try:
        result = run_smoke(
            opts["project_root"],
            api_url=opts["api"],
            token=opts["token"] or None,
            capability=opts.get("capability") or DEFAULT_SMOKE_CAPABILITY,
            prompt=opts.get("prompt") or DEFAULT_SMOKE_PROMPT,
            poll_seconds=opts.get("poll_seconds") or 90,
        )
    except SmokeError as exc:
        _print_smoke_error(exc, json_output=bool(opts.get("json_output")))
        raise typer.Exit(exc.exit_code) from exc
    _print_smoke(result, json_output=bool(opts.get("json_output")))


@smoke_app.command("sheet")
def smoke_sheet_cmd(ctx: typer.Context) -> None:
    """Sheet & Slice smoke: image.generate.v1 + sheet.slice (min 816×816 per cell)."""
    opts = ctx.obj or {}
    try:
        result = run_sheet_smoke(
            opts["project_root"],
            api_url=opts["api"],
            token=opts["token"] or None,
            prompt=opts.get("prompt") or DEFAULT_SMOKE_PROMPT,
            poll_seconds=opts.get("poll_seconds") or 300,
        )
    except SmokeError as exc:
        _print_smoke_error(exc, json_output=bool(opts.get("json_output")))
        raise typer.Exit(exc.exit_code) from exc
    _print_smoke(result, json_output=bool(opts.get("json_output")))


@app.command("doctor")
def doctor_cmd(
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    smoke_capability: str = typer.Option(
        DEFAULT_SMOKE_CAPABILITY,
        "--smoke-capability",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print machine-readable report"),
    local_only: bool = typer.Option(
        False,
        "--local-only",
        help="Local workspace checks only (no network)",
    ),
    repair: bool = typer.Option(
        False,
        "--repair",
        help="Migrate config.json identity into project.json; fail if remote cannot decide.",
    ),
) -> None:
    """Verify API health, auth, config alignment, providers, and launch smoke readiness."""
    if local_only:
        payload = build_agent_status(project_root, refresh=False)
        if json_output:
            console.print_json(data=payload)
            return
        console.print(f"configured={payload['configured']} ready={payload['ready']}")
        if payload.get("projectId"):
            console.print(f"project={payload['projectId']} environment={payload['environment']}")
        return
    code = run_doctor(
        api,
        project_root,
        token or None,
        smoke_capability=smoke_capability,
        json_output=json_output,
        console=console,
        repair=repair,
    )
    if code != 0:
        raise typer.Exit(code)


@app.command("agent-status")
def agent_status_cmd(
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
    refresh: bool = typer.Option(False, "--refresh", help="Optional network verify"),
) -> None:
    """Local workspace readiness for hooks and agents. Default: no network."""
    payload = build_agent_status(project_root, refresh=refresh)
    if json_output:
        console.print_json(data=payload)
        return
    console.print(f"configured={payload['configured']} ready={payload['ready']}")
    if payload.get("projectId"):
        console.print(f"project={payload['projectId']} environment={payload['environment']}")
    if payload.get("installedHosts"):
        console.print(f"hosts={', '.join(payload['installedHosts'])}")


@mcp_app.command("serve")
def mcp_serve_cmd(
    workspace: Path | None = typer.Option(
        None,
        "--workspace",
        help="Absolute project root. Authoritative locator for stdio MCP.",
    ),
) -> None:
    """Run the Hydracept stdio MCP server."""
    from hydracept.mcp.server import configure_workspace, serve_stdio

    configure_workspace(workspace)
    serve_stdio()


@mcp_app.command("bind")
def mcp_bind_cmd(
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Write project MCP configs so coding agents use stdio + workspace secrets."""
    from hydracept.cli.mcp_bind import bind_workspace_mcp

    result = bind_workspace_mcp(project_root)
    if json_output:
        console.print_json(data=result.to_dict())
        return
    console.print(f"bound={result.bound} transport={result.transport}")
    for path in result.project_config:
        console.print(path)
    if result.reload_required:
        console.print("Reload MCP in the coding agent once.")


@agents_app.command("detect")
def agents_detect_cmd(
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Detect coding-agent hosts and installed Agent Pack state."""
    payload = detect_all(project_root)
    if json_output:
        console.print_json(data=payload)
        return
    for host, detail in payload["hosts"].items():
        flags = []
        if detail["detected"]:
            flags.append("detected")
        if detail["installed"]:
            flags.append("installed")
        console.print(f"{host}: {', '.join(flags) or 'not found'}")


@agents_app.command("install")
def agents_install_cmd(
    host: str = typer.Argument("", help="cursor | claude | antigravity"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    auto: bool = typer.Option(False, "--auto"),
    smoke: bool = typer.Option(False, "--smoke"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Install Hydracept Agent Pack into a coding-agent host."""
    try:
        result = install_agent_pack(
            project_root,
            host=host or None,
            auto=auto or not host,
            smoke=smoke,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(USAGE) from exc
    payload = {
        "hosts": result.hosts,
        "files": result.files,
        "smoke": result.smoke,
    }
    if json_output:
        console.print_json(data=payload)
    else:
        console.print(f"[green]Installed[/green] hosts={', '.join(result.hosts)}")
        if result.smoke:
            console.print_json(data=result.smoke)


@agents_app.command("uninstall")
def agents_uninstall_cmd(
    host: str = typer.Argument("", help="cursor | claude | antigravity"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    auto: bool = typer.Option(False, "--auto"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Remove Hydracept Agent Pack files tracked by the ownership manifest."""
    try:
        result = uninstall_agent_pack(
            project_root,
            host=host or None,
            auto=auto or not host,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(USAGE) from exc
    payload = {"hosts": result.hosts, "removed": result.removed}
    if json_output:
        console.print_json(data=payload)
    else:
        console.print(f"[green]Uninstalled[/green] hosts={', '.join(result.hosts)}")


@app.command("agent-context")
def agent_context_cmd(
    api: str = typer.Option(DEFAULT_API, "--api"),
    output: Path = typer.Option(Path(".hydracept/agent-context.json"), "--output"),
    profile: str | None = typer.Option(
        None,
        "--profile",
        help="Projection profile: compact, integration, or omit for full bundle.",
    ),
) -> None:
    params: dict[str, str] = {}
    if profile:
        params["profile"] = profile
    response = httpx.get(
        f"{api.rstrip('/')}/v1/agent-context",
        params=params,
        timeout=60.0,
    )
    payload = _cli_json(response)
    if isinstance(payload, dict):
        payload.setdefault(
            "catalogNotice",
            "GET /v1/agent-context is live. This file is a snapshot — never treat it as the capability catalog.",
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    console.print(f"[green]Wrote[/green] {output} (snapshot — use GET /v1/agent-context live)")


@app.command("health")
def health_cmd(api: str = typer.Option(DEFAULT_API, "--api")) -> None:
    response = httpx.get(f"{api.rstrip('/')}/healthz", timeout=15.0)
    console.print_json(data=_cli_json(response))


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
def capabilities_list(api: str = typer.Option(DEFAULT_API, "--api")) -> None:
    response = httpx.get(f"{api.rstrip('/')}/v1/capabilities", timeout=30.0)
    console.print_json(data=_cli_json(response))


@capabilities_app.command("describe")
def capabilities_describe(
    key: str = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
) -> None:
    response = httpx.get(f"{api.rstrip('/')}/v1/capabilities/{key}", timeout=30.0)
    console.print_json(data=_cli_json(response))


@capabilities_app.command("find")
def capabilities_find(
    intent: str = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
) -> None:
    response = httpx.post(
        f"{api.rstrip('/')}/v1/capabilities/resolve",
        json={"intent": intent},
        timeout=30.0,
    )
    console.print_json(data=_cli_json(response))


@capabilities_app.command("quote")
def capabilities_quote(
    key: str = typer.Argument(...),
    body: Path = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
) -> None:
    resolved = _resolve_token(project_root, token or None)
    payload = json.loads(body.read_text(encoding="utf-8"))
    client = HydraceptClient(api, resolved)
    console.print_json(data=client.quote_capability(key, payload))


@capabilities_app.command("estimate")
def capabilities_estimate(
    key: str = typer.Argument(...),
    body: Path = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
) -> None:
    """HTTP alias of `capabilities quote` (same 0.3 response)."""
    capabilities_quote(key, body, api, project_root, token)


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
    workspace = resolve_workspace(
        project_root,
        overrides=CliOverrides(
            token=token or None,
            api_url=None if api == DEFAULT_API else api,
        ),
    )
    config = read_json(config_path(project_root))
    payload = merge_workspace_job_context(payload, workspace, config=config)
    client = HydraceptClient(api, resolved)
    console.print_json(data=client.invoke_capability(key, payload))


@capability_request_app.command("create")
def capability_request_create(
    body: Path = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
) -> None:
    resolved = _resolve_token(project_root, token or None)
    payload = json.loads(body.read_text(encoding="utf-8"))
    client = HydraceptClient(api, resolved)
    console.print_json(data=client.create_capability_request(payload))


@capability_request_app.command("show")
def capability_request_show(
    request_id: str = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
) -> None:
    resolved = _resolve_token(project_root, token or None)
    client = HydraceptClient(api, resolved)
    console.print_json(data=client.get_capability_request(request_id))


@capability_request_app.command("submit")
def capability_request_submit(
    request_id: str = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
) -> None:
    resolved = _resolve_token(project_root, token or None)
    client = HydraceptClient(api, resolved)
    console.print_json(data=client.submit_capability_request(request_id))


@integrations_install_app.command("unity")
def integrations_install_unity(
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    version: str = typer.Option("", "--version", help="Optional UPM git tag (v0.1.0)"),
) -> None:
    """Add the Hydracept Unity package to Packages/manifest.json."""
    try:
        changed = install_unity_package(
            project_root,
            version=version or None,
        )
    except UnityInstallError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(USAGE) from exc
    if changed:
        console.print("[green]Installed Hydracept Unity package[/green]")
    else:
        console.print("Hydracept Unity package already present")


@jobs_app.command("list")
def jobs_list(
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    limit: int = typer.Option(25, "--limit"),
    cursor: str = typer.Option("", "--cursor"),
) -> None:
    workspace = resolve_workspace(
        project_root,
        overrides=CliOverrides(
            token=token or None,
            api_url=None if api == DEFAULT_API else api,
        ),
    )
    if workspace is None:
        console.print("[red]Workspace is not ready[/red]")
        raise typer.Exit(NOT_READY)
    client = HydraceptClient(workspace.api_url, workspace.token, workspace=workspace)
    data = client.list_jobs(limit=limit, cursor=cursor or None)
    console.print_json(data=data)


@jobs_app.command("submit")
def jobs_submit(
    capability_key: str = typer.Argument(...),
    body: Path = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    watch: bool = typer.Option(False, "--watch"),
) -> None:
    import time

    resolved = _resolve_token(project_root, token or None)
    payload = json.loads(body.read_text(encoding="utf-8"))
    workspace = resolve_workspace(
        project_root,
        overrides=CliOverrides(
            token=token or None,
            api_url=None if api == DEFAULT_API else api,
        ),
    )
    config = read_json(config_path(project_root))
    payload = merge_workspace_job_context(payload, workspace, config=config)
    client = HydraceptClient(api, resolved)
    data = client.submit_capability_job(capability_key, payload)
    console.print_json(data=data)
    try:
        console.file.flush()
    except Exception:
        pass
    sys.stdout.flush()
    if not watch:
        return
    job_id = data.get("jobId") or data.get("executionId")
    while job_id:
        status = client.get_job(str(job_id))
        state = status.get("status") or status.get("currentStatus")
        sys.stdout.write(f"{state}\n")
        sys.stdout.flush()
        if str(state).lower() in {"succeeded", "failed", "canceled", "cancelled"}:
            console.print_json(data=status)
            try:
                console.file.flush()
            except Exception:
                pass
            sys.stdout.flush()
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


@pinned_app.command("run")
def pinned_run(
    body: Path = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
) -> None:
    """POST /v1/inference/pinned — exact pin, scientific receipt."""
    resolved = _resolve_token(project_root, token or None)
    payload = json.loads(body.read_text(encoding="utf-8"))
    client = HydraceptClient(api, resolved)
    console.print_json(data=client.create_pinned_inference(payload))


@pinned_app.command("get")
def pinned_get(
    receipt_id: str = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
) -> None:
    client = HydraceptClient(api, _resolve_token(project_root, token or None))
    console.print_json(data=client.get_pinned_receipt(receipt_id))


@app.command("verify")
def verify_cmd(
    path: Path | None = typer.Argument(None, help="hydracept.lock or a run manifest JSON/YAML"),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Verify an AI lockfile or run manifest (Receipt → Manifest → Lock)."""
    target = path or (project_root / DEFAULT_LOCKFILE)
    if not target.is_file():
        console.print(f"[red]missing {target}[/red]")
        raise typer.Exit(NOT_READY)
    try:
        document = load_document(target)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(USAGE) from exc
    manifest = is_manifest(target, document)
    checks = structural_manifest_checks(document) if manifest else structural_lockfile_checks(document)
    live: dict[str, Any] | None = None
    resolved = ""
    try:
        resolved = _resolve_token(project_root, token or None)
    except Exception:
        resolved = ""
    if resolved:
        client = HydraceptClient(api, resolved)
        try:
            if manifest:
                manifest_id = document.get("manifestId") or document.get("manifest_id")
                if manifest_id:
                    live = client.verify_run_manifest(str(manifest_id))
                    checks = list(live.get("checks") or checks)
                else:
                    found = 0
                    pin_valid = 0
                    for item in document.get("receipts") or []:
                        if not isinstance(item, dict):
                            continue
                        rid = item.get("receipt_id") or item.get("receiptId")
                        if not rid:
                            continue
                        receipt = client.get_pinned_receipt(str(rid))
                        found += 1
                        if receipt.get("pinVerified") is True:
                            pin_valid += 1
                    total = len(document.get("receipts") or [])
                    checks.extend(
                        [
                            {
                                "name": "receipts_found",
                                "passed": found == total,
                                "detail": f"{found}/{total} receipts found",
                            },
                            {
                                "name": "pins_valid",
                                "passed": pin_valid == found,
                                "detail": f"{pin_valid}/{total} pin-valid",
                            },
                        ]
                    )
            else:
                live = client.verify_lockfile(document)
                checks = list(live.get("checks") or checks)
                checks.append(
                    {
                        "name": "credentials",
                        "passed": True,
                        "detail": "Hydracept credentials available",
                    }
                )
        except httpx.HTTPError as exc:
            checks.append({"name": "live_verify", "passed": False, "detail": str(exc)})
    else:
        checks.append(
            {
                "name": "credentials",
                "passed": True,
                "detail": "skipped (offline - no Hydracept token)",
            }
        )
    passed = all_passed(checks)
    payload = {"path": str(target), "kind": "manifest" if manifest else "lockfile", "passed": passed, "checks": checks}
    if live:
        payload["live"] = live
    if json_output:
        console.print_json(data=payload)
    else:
        console.print(format_checks(checks))
        console.print("manifest valid" if manifest and passed else ("lockfile valid" if passed else "verify failed"))
    if not passed:
        raise typer.Exit(NOT_READY)


@lockfile_app.command("emit")
def lockfile_emit(
    receipt_id: str = typer.Argument(...),
    out: Path = typer.Option(DEFAULT_LOCKFILE, "--out"),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
) -> None:
    """Write hydracept.lock from a pinned receipt."""
    client = HydraceptClient(api, _resolve_token(project_root, token or None))
    lock = client.get_lockfile(receipt_id)
    out.write_text(yaml.safe_dump(lock, sort_keys=False, allow_unicode=True), encoding="utf-8")
    console.print(f"wrote {out}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
