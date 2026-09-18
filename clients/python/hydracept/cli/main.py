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
from hydracept import HydraceptClient
from hydracept.cli.package_provenance import package_provenance
from hydracept.errors import HydraceptApiError, raise_api_status
from hydracept.cli.agent_status import build_agent_status
from hydracept.cli.agents.detect import detect_all
from hydracept.cli.agents.install import install_agent_pack
from hydracept.cli.agents.uninstall import uninstall_agent_pack
from hydracept.cli.bootstrap import ConfigureError, run_configure
from hydracept.cli.console_io import cli_console
from hydracept.cli.json_file import read_json_file
from hydracept.cli.doctor import DEFAULT_SMOKE_CAPABILITY, run_doctor
from hydracept.cli.exit_codes import NOT_READY, USAGE
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
    DEFAULT_TEXT_SMOKE_CAPABILITY,
    DEFAULT_TEXT_SMOKE_PROMPT,
    DEFAULT_TEXT_SMOKE_TARGET_LOCALE,
    SmokeError,
    TextSmokeResult,
    run_sheet_smoke,
    run_smoke,
    run_text_smoke,
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
    WorkspaceNotReadyError,
    config_path,
    read_json,
    resolve_token,
    resolve_workspace,
)
from hydracept.consumer_boundary import scan_path
from hydracept.job_lifecycle import JobWaitTimeout

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


def _print_init_ready(payload: dict[str, Any]) -> None:
    identity = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
    project = payload.get("project") if isinstance(payload.get("project"), dict) else {}
    mcp = payload.get("mcp") if isinstance(payload.get("mcp"), dict) else {}
    provider = str(identity.get("provider") or "").strip()
    account = str(identity.get("account") or "").strip()
    if identity.get("authenticated"):
        label = " / ".join(part for part in (provider, account) if part) or "signed in"
        console.print(f"[green]✓[/green] identity: {label}")
    display_name = str(project.get("displayName") or project.get("name") or project.get("id") or "")
    if display_name:
        console.print(f"[green]✓[/green] project: {display_name}")
    environment = str(project.get("environment") or "development")
    console.print(f"[green]✓[/green] environment: {environment}")
    if mcp.get("configured"):
        console.print("[green]✓[/green] MCP configured")
    console.print("[green]✓[/green] ready")


def _load_json_payload(
    positional: str | None,
    input_json: str = "",
    body_file: Path | None = None,
) -> dict[str, Any]:
    from hydracept.cli.run_facade import parse_json_body

    try:
        return parse_json_body(positional, input_json=input_json, body_file=body_file)
    except (ValueError, json.JSONDecodeError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(USAGE) from exc


def _input_file_option() -> Any:
    return typer.Option(
        None,
        "--body",
        "--input-file",
        help="JSON file with capability input (PowerShell-safe). Avoid inline --input quoting.",
    )


def _cli_json(response: httpx.Response) -> Any:
    try:
        raise_api_status(response)
    except HydraceptApiError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    return response.json()


def _suggestion_catalog(api: str) -> Any:
    """Best-effort capability summary for unknown-key suggestions. Never raises."""
    from hydracept.capability_errors import fetch_catalog_summary

    return fetch_catalog_summary(api)


def _raise_capability_status(response: httpx.Response, *, key: str, api: str) -> None:
    """Raise API errors, upgrading unknown keys to UNKNOWN_CAPABILITY + suggestions."""
    if response.is_success:
        return
    from hydracept.capability_errors import error_payload_for_response

    unknown = error_payload_for_response(
        response, key=key, catalog=_suggestion_catalog(api)
    )
    if unknown is not None:
        console.print_json(data=unknown)
        raise typer.Exit(USAGE)
    try:
        raise_api_status(response)
    except HydraceptApiError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


def _version_callback(value: bool) -> None:
    if not value:
        return
    payload = package_provenance()
    if "--json" in sys.argv:
        console.print_json(data=payload)
    else:
        console.print(payload["version"])
    raise typer.Exit()


@app.callback()
def _root(
    json_output: bool = typer.Option(
        False,
        "--json",
        is_eager=True,
        help="With --version, print package provenance JSON.",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the hydracept package version and exit.",
    ),
) -> None:
    """Hydracept public CLI — AI execution control plane."""
    del json_output, version


_PROVENANCE_MIRROR_KEYS = (
    "installedClient",
    "mcpBindingVersion",
    "mcpRuntimeState",
    "apiRevision",
    "apiRevisionState",
    "agentPack",
)


@app.command("version")
def version_cmd(
    json_output: bool = typer.Option(False, "--json", help="Machine-readable provenance"),
    refresh: bool = typer.Option(
        False, "--refresh", help="Fetch the live API revision and session facts (network)."
    ),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
) -> None:
    """Installed version plus consumer provenance (MCP binding, API revision, agent pack)."""
    from hydracept.cli.consumer_versions import consumer_version_report

    payload = consumer_version_report(project_root)
    consumer = payload.get("consumer")
    if not isinstance(consumer, dict):
        consumer = {}
    if refresh:
        try:
            from hydracept.cli.agent_status import build_agent_status

            status = build_agent_status(project_root, refresh=True)
            versions = status.get("versions") if isinstance(status.get("versions"), dict) else {}
            consumer = {
                **consumer,
                **{
                    name: versions[name]
                    for name in _PROVENANCE_MIRROR_KEYS
                    if name in versions
                },
                "apiRevision": versions.get("apiRevision"),
                "apiRevisionState": (
                    "fetched" if versions.get("apiRevision") else "not_fetched"
                ),
            }
        except Exception as exc:  # noqa: BLE001 - refresh is optional; version must still print
            payload["refreshError"] = str(exc) or exc.__class__.__name__
    if consumer:
        payload["consumer"] = consumer
        for name in _PROVENANCE_MIRROR_KEYS:
            if consumer.get(name) is not None:
                payload.setdefault(name, consumer[name])
    if "apiRevision" not in payload:
        payload["apiRevision"] = consumer.get("apiRevision")
    if "apiRevisionState" not in payload:
        payload["apiRevisionState"] = consumer.get("apiRevisionState") or "not_fetched"
    if "agentPack" not in payload:
        payload["agentPack"] = consumer.get("agentPack") or "not_installed"
    if json_output:
        console.print_json(data=payload)
        return
    dist = payload.get("distribution") or {}
    console.print(payload["version"])
    console.print(f"path={payload['packagePath']}")
    console.print(f"source={dist.get('source', 'unknown')}")
    if consumer:
        console.print(f"mcpBinding={consumer.get('mcpBindingVersion')}")
        console.print(
            f"mcpRuntime={consumer.get('mcpRuntimeMessage') or consumer.get('mcpRuntimeState')}"
        )
        console.print(f"apiRevision={consumer.get('apiRevision') or 'not_fetched'}")
        console.print(f"agentPack={consumer.get('agentPack')}")
    if payload.get("refreshError"):
        console.print(f"refreshError={payload['refreshError']}")


def _resolve_token(project_root: Path, token: str | None) -> str:
    return resolve_token(project_root, token)


def _open_client(project_root: Path, api: str, token: str) -> HydraceptClient:
    try:
        return HydraceptClient.from_workspace(
            project_root,
            token=token or None,
            api_url=None if api == DEFAULT_API else api,
        )
    except WorkspaceNotReadyError:
        return HydraceptClient(api, _resolve_token(project_root, token or None))


def _execution_workspace(
    project_root: Path,
    *,
    token: str = "",
    api: str = DEFAULT_API,
):
    from hydracept.cli.workspace import WorkspaceNotReadyError
    from hydracept.context import ProjectCredentialMismatch, require_execution_context

    try:
        workspace, _ = require_execution_context(
            project_root,
            overrides=CliOverrides(
                token=token or None,
                api_url=None if api == DEFAULT_API else api,
            ),
        )
    except (ProjectCredentialMismatch, WorkspaceNotReadyError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(NOT_READY) from exc
    return workspace


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
    project: str = typer.Option(
        "",
        "--project",
        help="Bind this workspace to an explicit project id, slug, or name",
    ),
    environment: str = typer.Option(
        "",
        "--environment",
        help="Environment slug (default: development)",
    ),
    project_name: str = typer.Option(
        "",
        "--project-name",
        help="Suggested Hydracept project name (default: folder name or HYDRACEPT_PROJECT_NAME)",
    ),
) -> None:
    """Idempotent workspace bootstrap. Reuses GitHub CLI or HYDRACEPT_API_KEY when present."""
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
            explicit_project=project.strip() or None,
            explicit_environment=environment.strip() or None,
            project_name=suggested,
        )
        if json_output:
            console.print_json(data=result.payload)
        elif wait and result.payload.get("status") not in {"ready", "interaction_required"}:
            console.print_json(data=result.payload)
        elif result.payload.get("status") == "ready":
            _print_init_ready(result.payload)
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
                detail = str(result.payload.get("detail") or "").strip()
                if detail:
                    console.print(detail)
                else:
                    console.print(
                        "Hydracept could not uniquely determine which project this workspace belongs to."
                    )
                console.print("Choose a project in your browser, or run [bold]hydracept project use <project>[/bold].")
            elif reason == "provider_connection_conflict":
                console.print("Resolve the provider connection conflict in your browser.")
            else:
                console.print("Complete setup in your browser.")
            if url:
                console.print(f"\n[link={url}]{url}[/link]")
                console.print(
                    "A human must open this URL; the agent cannot complete activation unattended."
                )
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
    display = (result.to_json().get("pricing") or {}).get("display") or {}
    console.print(f"[green]Smoke succeeded[/green] jobId={result.job_id}")
    if display.get("cost"):
        console.print(f"Cost: {display['cost']}")
    if display.get("paidFrom"):
        console.print(f"Paid from: {display['paidFrom']}")
    if result.demo_path:
        console.print(f"saved={result.demo_path}")


def _print_smoke_error(exc: SmokeError, *, json_output: bool) -> None:
    if json_output:
        console.print_json(data=exc.to_json())
        return
    console.print(f"[red]{exc}[/red]")
    if exc.status in {"contract_failed", "generation_succeeded_receipt_invalid"}:
        console.print("[yellow]Generation succeeded, but smoke validation failed. Inspect execution and validation separately.[/yellow]")
    if exc.job_id:
        console.print(f"jobId={exc.job_id}")
    if exc.receipt_id:
        console.print(f"receiptId={exc.receipt_id}")
    if exc.failing_path:
        console.print(f"failingPath={exc.failing_path}")
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
    """Submit the launch smoke job. Subcommands: `image` (default), `sheet`, `text`."""
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
def smoke_image_cmd(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Image smoke: generation, pricing, durability, SHA-256, PNG alpha, receipt."""
    opts = ctx.obj or {}
    json_output = json_output or bool(opts.get("json_output"))
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
        _print_smoke_error(exc, json_output=json_output)
        raise typer.Exit(exc.exit_code) from exc
    _print_smoke(result, json_output=json_output)


@smoke_app.command("sheet")
def smoke_sheet_cmd(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Sheet & Slice smoke: image.generate.v1 + sheet.slice (min 816×816 per cell)."""
    opts = ctx.obj or {}
    json_output = json_output or bool(opts.get("json_output"))
    try:
        result = run_sheet_smoke(
            opts["project_root"],
            api_url=opts["api"],
            token=opts["token"] or None,
            prompt=opts.get("prompt") or DEFAULT_SMOKE_PROMPT,
            poll_seconds=opts.get("poll_seconds") or 300,
        )
    except SmokeError as exc:
        _print_smoke_error(exc, json_output=json_output)
        raise typer.Exit(exc.exit_code) from exc
    _print_smoke(result, json_output=json_output)


def _print_text_smoke(result: TextSmokeResult, *, json_output: bool) -> None:
    if json_output:
        console.print_json(data=result.to_json())
        return
    display = (result.to_json().get("pricing") or {}).get("display") or {}
    console.print(f"[green]Text smoke succeeded[/green] capability={result.capability}")
    if result.execution_id:
        console.print(f"executionId={result.execution_id}")
    if result.output_preview:
        console.print(f"output={result.output_preview}")
    if display.get("cost"):
        console.print(f"Cost: {display['cost']}")
    if display.get("paidFrom"):
        console.print(f"Paid from: {display['paidFrom']}")


@smoke_app.command("text")
def smoke_text_cmd(
    ctx: typer.Context,
    capability: str = typer.Option(
        DEFAULT_TEXT_SMOKE_CAPABILITY,
        "--capability",
        help="Text capability to probe (synchronous invoke).",
    ),
    prompt: str = typer.Option(DEFAULT_TEXT_SMOKE_PROMPT, "--prompt"),
    target_locale: str = typer.Option(DEFAULT_TEXT_SMOKE_TARGET_LOCALE, "--target-locale"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Text smoke: synchronous invoke, non-empty output, receipt pricing."""
    opts = ctx.obj or {}
    json_output = json_output or bool(opts.get("json_output"))
    try:
        result = run_text_smoke(
            opts["project_root"],
            api_url=opts["api"],
            token=opts["token"] or None,
            capability=capability,
            prompt=prompt,
            target_locale=target_locale,
        )
    except SmokeError as exc:
        _print_smoke_error(exc, json_output=json_output)
        raise typer.Exit(exc.exit_code) from exc
    _print_text_smoke(result, json_output=json_output)


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
    fix: bool = typer.Option(
        False,
        "--fix",
        help="Safe Hydracept-owned repairs only (MCP bind). Never spend or overwrite peers.",
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
        fix=fix,
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


@app.command("context")
def context_cmd(
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Machine-readable context"),
    local_only: bool = typer.Option(False, "--local-only", help="Skip diagnostics/session"),
) -> None:
    """Show ResolvedHydraceptContext for this checkout."""
    from hydracept.context import resolve_hydracept_context

    payload = resolve_hydracept_context(project_root, refresh=not local_only).to_dict()
    if json_output:
        console.print_json(data=payload)
        return
    console.print(f"ready={payload['ready']} execution={payload['executionProjectId']}")
    if payload.get("mismatch"):
        console.print(f"[red]{payload['mismatch']}[/red]")


@app.command("run")
def run_cmd(
    capability: str = typer.Argument(..., help="Capability key"),
    prompt: str = typer.Option("", "--prompt", help="Capability-specific quick input when supported"),
    target_locale: str = typer.Option("", "--target-locale", help="BCP 47 target locale for text.translate.v1"),
    input_json: str = typer.Option("", "--input", help="JSON object or prompt string"),
    body: Path | None = _input_file_option(),
    wait: bool = typer.Option(True, "--wait/--no-wait"),
    timeout: float | None = typer.Option(None, "--timeout", help="Stop local waiting; never cancel remote"),
    max_cost: float | None = typer.Option(None, "--max-cost", help="Admission ceiling (server-enforced)"),
    idempotency_key: str = typer.Option("", "--idempotency-key"),
    out: Path | None = typer.Option(None, "--out"),
    set_values: list[str] = typer.Option(
        [], "--set", help="Set a capability input field: key=value (repeatable)"
    ),
    json_output: bool = typer.Option(False, "--json"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    api: str = typer.Option(DEFAULT_API, "--api"),
) -> None:
    """Find, admit, wait, persist. Canonical public execution primitive."""
    from hydracept.cli.run_facade import execute_run, parse_input_argument

    try:
        payload = parse_input_argument(input_json or None, body)
    except (ValueError, json.JSONDecodeError) as exc:
        console.print_json(
            data={
                "error": True,
                "code": "InvalidInput",
                "message": str(exc),
                "recovery": {
                    "nextAction": "python -m hydracept run <key> --prompt \"...\" --json"
                },
            }
        )
        raise typer.Exit(USAGE) from exc
    if set_values:
        from hydracept.cli.run_input_coercion import InputValidationError, parse_set_values

        try:
            payload.update(parse_set_values(set_values))
        except InputValidationError as exc:
            console.print_json(data=exc.to_payload())
            raise typer.Exit(USAGE) from exc
    if prompt:
        payload.setdefault("prompt", prompt)
    if target_locale:
        payload.setdefault("targetLocale", target_locale)
    if payload.get("prompt") and str(capability).startswith("image."):
        payload.setdefault("requestTransparentOutput", True)
    if (
        not json_output
        and str(capability).startswith("image.")
        and payload.get("prompt")
    ):
        from hydracept.cli.image_canvas import MIN_PIXELS, MIN_SQUARE, canvas_size

        if canvas_size(payload) is None:
            console.print(
                f"note: image generation uses model-native sizing; minimum canvas is "
                f"{MIN_SQUARE}×{MIN_SQUARE} ({MIN_PIXELS:,} px) and output may be larger."
            )
    outcome = execute_run(
        project_root,
        capability,
        payload,
        overrides=CliOverrides(
            token=token or None,
            api_url=None if api == DEFAULT_API else api,
        ),
        wait=wait,
        timeout=timeout,
        max_cost=max_cost,
        idempotency_key=idempotency_key or None,
        out=out,
    )
    _print_run_outcome(outcome, json_output=json_output)
    if outcome.exit_code:
        raise typer.Exit(outcome.exit_code)


def _print_run_outcome(outcome: Any, *, json_output: bool) -> None:
    payload = outcome.payload()
    if json_output:
        console.print_json(data=payload)
        return
    if outcome.error is not None:
        console.print(f"[red]{outcome.error.message}[/red]")
        recovery = outcome.error.recovery or {}
        next_action = recovery.get("nextAction") or recovery.get("cli")
        if next_action:
            console.print(f"next: {next_action}")
        return
    status = str(payload.get("status") or "unknown")
    capability = str(payload.get("capability") or "")
    console.print(f"[green]status={status}[/green] capability={capability}")
    pricing = payload.get("pricing") if isinstance(payload.get("pricing"), dict) else {}
    summary = pricing.get("summary")
    if summary:
        console.print(str(summary))
    from hydracept.cli.run_output_preview import human_run_preview

    preview = human_run_preview(payload)
    if preview:
        console.print(preview)
    for artifact in payload.get("artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        path = artifact.get("localPath") or artifact.get("filename")
        if path:
            console.print(f"artifact: {path}")
    if payload.get("jobId"):
        console.print(f"job: {payload['jobId']}")


def _print_funding_status(payload: dict, *, json_output: bool) -> None:
    if json_output:
        console.print_json(data=payload)
        return
    credit = payload.get("managedCreditRemainingUsd")
    trial = payload.get("trialRemainingUsd")
    source = payload.get("managedExecutionFundingSource") or "unavailable"
    coverage = payload.get("managedExecutionCoverage") or payload.get("managedChargeExpectation")
    byok = bool(payload.get("byokConnected"))
    credit_text = "unknown" if credit is None else f"${float(credit):.2f}"
    trial_text = "unknown" if trial is None else f"${float(trial):.2f}"
    if payload.get("summary"):
        console.print(str(payload["summary"]))
    console.print(
        f"canExecute={str(bool(payload.get('canExecute'))).lower()} "
        f"customerCredit={credit_text} trial={trial_text} "
        f"executionFunding={source} coverage={coverage or 'unknown'} byok={str(byok).lower()}"
    )
    if payload.get("nextAction"):
        console.print(f"next={payload['nextAction']}")


funding_app = typer.Typer(
    help="How this workspace pays (trial + BYOK).",
    invoke_without_command=True,
    no_args_is_help=False,
)
app.add_typer(funding_app, name="funding")
providers_app = typer.Typer(help="Provider credentials (alias of funding).")
app.add_typer(providers_app, name="providers")


@funding_app.callback()
def funding_default(
    ctx: typer.Context,
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    from hydracept.cli.funding import funding_status

    _print_funding_status(funding_status(project_root), json_output=json_output)


@funding_app.command("status")
def funding_status_cmd(
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    from hydracept.cli.funding import funding_status

    _print_funding_status(funding_status(project_root), json_output=json_output)


@funding_app.command("setup")
def funding_setup_cmd(
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    json_output: bool = typer.Option(False, "--json"),
    open_browser: bool = typer.Option(True, "--open-browser/--no-open-browser"),
) -> None:
    from hydracept.cli.funding import funding_setup

    payload = funding_setup(project_root, open_browser=open_browser)
    if json_output:
        console.print_json(data=payload)
        return
    console.print(payload["connectUrl"])


@providers_app.command("connect")
def providers_connect_cmd(
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    json_output: bool = typer.Option(False, "--json"),
    open_browser: bool = typer.Option(True, "--open-browser/--no-open-browser"),
) -> None:
    """Alias of `funding setup`."""
    funding_setup_cmd(project_root, json_output, open_browser)


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

    configure_workspace(workspace or Path.cwd())
    serve_stdio()


@mcp_app.command("bind")
def mcp_bind_cmd(
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    json_output: bool = typer.Option(False, "--json"),
    user_apps: bool = typer.Option(
        False,
        "--user-apps",
        help="Explicit Cursor global-scope Apps workaround with an absolute workspace. Not used by init/doctor.",
    ),
    user_apps_remove: bool = typer.Option(
        False,
        "--user-apps-remove",
        help="Remove the explicit user-global Hydracept MCP workaround.",
    ),
) -> None:
    """Write project MCP configs so coding agents use stdio + workspace secrets."""
    from hydracept.cli.mcp_bind import bind_user_apps_workaround, bind_workspace_mcp, remove_user_apps_workaround

    if user_apps_remove:
        payload = remove_user_apps_workaround()
        if json_output:
            console.print_json(data=payload)
            return
        console.print(f"user-apps removed={payload.get('removed')}")
        return
    if user_apps:
        payload = bind_user_apps_workaround(project_root)
        if json_output:
            console.print_json(data=payload)
            return
        console.print("Wrote user-global Cursor MCP with an absolute workspace.")
        console.print(payload.get("cleanup") or "")
        return
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
    json_output: bool = typer.Option(False, "--json"),
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
    if json_output:
        console.print_json(data=payload)
        return
    console.print(f"[green]Wrote[/green] {output} (snapshot — use GET /v1/agent-context live)")


@app.command("health")
def health_cmd(api: str = typer.Option(DEFAULT_API, "--api")) -> None:
    response = httpx.get(f"{api.rstrip('/')}/healthz", timeout=15.0)
    console.print_json(data=_cli_json(response))


@app.command("consumer-check")
def consumer_check_cmd(
    path: Path = typer.Option(Path.cwd(), "--path"),
    strict: bool = typer.Option(False, "--strict"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    code, detail = scan_path(path, strict=strict)
    payload = {
        "schemaVersion": "hydracept.cli.consumer-check.v1",
        "passed": code == 0,
        "strict": strict,
        "path": str(path.resolve()),
        "detail": detail,
    }
    if json_output:
        console.print_json(data=payload)
    elif code != 0:
        console.print(detail)
    else:
        console.print(f"[green]{detail}[/green]")
        if strict:
            console.print("[green]Strict consumer boundary check passed[/green]")
    if code != 0:
        raise typer.Exit(1)


@capabilities_app.command("list")
def capabilities_list(
    api: str = typer.Option(DEFAULT_API, "--api"),
    compact: bool = typer.Option(
        False,
        "--compact",
        help="Identity-free browse (GET /v1/capabilities?view=summary).",
    ),
    json_output: bool = typer.Option(False, "--json", help="No-op; list is already JSON"),
) -> None:
    del json_output
    params = {"view": "summary"} if compact else None
    response = httpx.get(f"{api.rstrip('/')}/v1/capabilities", params=params, timeout=30.0)
    console.print_json(data=_cli_json(response))


@capabilities_app.command("describe")
def capabilities_describe(
    key: str = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    json_output: bool = typer.Option(False, "--json", help="No-op; describe is already JSON"),
) -> None:
    """Describe a capability. The server owns the projection; the CLI renders it verbatim."""
    del json_output
    response = httpx.get(f"{api.rstrip('/')}/v1/capabilities/{key}", timeout=30.0)
    _raise_capability_status(response, key=key, api=api)
    console.print_json(data=_cli_json(response))


@capabilities_app.command("get")
def capabilities_get(
    key: str = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    json_output: bool = typer.Option(False, "--json", help="No-op; get is already JSON"),
) -> None:
    """Alias of `capabilities describe`."""
    capabilities_describe(key, api=api, json_output=json_output)


@capabilities_app.command("find")
def capabilities_find(
    intent: str = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    json_output: bool = typer.Option(False, "--json", help="No-op; find is already JSON"),
) -> None:
    del json_output
    response = httpx.post(
        f"{api.rstrip('/')}/v1/capabilities/resolve",
        json={"intent": intent},
        timeout=30.0,
    )
    data = _cli_json(response)
    if isinstance(data, dict) and isinstance(data.get("candidates"), list):
        data["candidates"] = data["candidates"][:5]
    console.print_json(data=data)


@app.command("quote")
@capabilities_app.command("quote")
def capabilities_quote(
    key: str = typer.Argument(...),
    body: str = typer.Argument(
        None,
        help="JSON file path, inline JSON object, or - for stdin",
    ),
    prompt: str = typer.Option("", "--prompt", help="Capability-specific quick input when supported"),
    target_locale: str = typer.Option("", "--target-locale", help="BCP 47 target locale for text.translate.v1"),
    input_json: str = typer.Option("", "--input", help="Inline JSON object"),
    body_file: Path | None = _input_file_option(),
    set_values: list[str] = typer.Option(
        [], "--set", help="Set a capability input field: key=value (repeatable)"
    ),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    json_output: bool = typer.Option(False, "--json", help="No-op; quote is already JSON"),
) -> None:
    del json_output
    from hydracept.cli.run_input_coercion import (
        InputValidationError,
        coerce_capability_input,
        parse_set_values,
    )

    workspace = _execution_workspace(project_root, token=token, api=api)
    if prompt and not (body or input_json or body_file):
        payload: dict[str, Any] = {"prompt": prompt}
    else:
        payload = _load_json_payload(body, input_json, body_file)
        if prompt:
            payload.setdefault("prompt", prompt)
    if set_values:
        try:
            payload.update(parse_set_values(set_values))
        except InputValidationError as exc:
            console.print_json(data=exc.to_payload())
            raise typer.Exit(USAGE) from exc
    if target_locale:
        payload.setdefault("targetLocale", target_locale)
    if payload.get("prompt") and str(key).startswith("image."):
        payload.setdefault("requestTransparentOutput", True)
    try:
        payload = coerce_capability_input(key, payload)
    except InputValidationError as exc:
        console.print_json(data=exc.to_payload())
        raise typer.Exit(USAGE) from exc
    payload = merge_workspace_job_context(payload, workspace)
    from hydracept.cli.image_canvas import preflight_image_canvas
    from hydracept.receipt_cost import present_quote

    blocked = preflight_image_canvas(key, payload)
    if blocked is not None:
        console.print_json(data=blocked)
        raise typer.Exit(USAGE)
    client = HydraceptClient(workspace.api_url, workspace.token, workspace=workspace)
    console.print_json(data=present_quote(client.quote_capability(key, payload)))


@capabilities_app.command("estimate")
def capabilities_estimate(
    key: str = typer.Argument(...),
    body: str = typer.Argument(
        None,
        help="JSON file path, inline JSON object, or - for stdin",
    ),
    prompt: str = typer.Option("", "--prompt", help="Capability-specific quick input when supported"),
    target_locale: str = typer.Option("", "--target-locale", help="BCP 47 target locale for text.translate.v1"),
    input_json: str = typer.Option("", "--input", help="Inline JSON object"),
    body_file: Path | None = _input_file_option(),
    set_values: list[str] = typer.Option(
        [], "--set", help="Set a capability input field: key=value (repeatable)"
    ),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
) -> None:
    """HTTP alias of `capabilities quote` (same 0.3 response)."""
    capabilities_quote(
        key,
        body,
        prompt=prompt,
        target_locale=target_locale,
        input_json=input_json,
        body_file=body_file,
        set_values=set_values,
        api=api,
        project_root=project_root,
        token=token,
    )


@capabilities_app.command("invoke")
def capabilities_invoke(
    key: str = typer.Argument(...),
    body: str = typer.Argument(
        None,
        help="JSON file path, inline JSON object, or - for stdin",
    ),
    input_json: str = typer.Option("", "--input", help="Inline JSON object"),
    body_file: Path | None = _input_file_option(),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
) -> None:
    workspace = _execution_workspace(project_root, token=token, api=api)
    payload = _load_json_payload(body, input_json, body_file)
    config = read_json(config_path(project_root))
    payload = merge_workspace_job_context(payload, workspace, config=config)
    client = HydraceptClient(workspace.api_url, workspace.token, workspace=workspace)
    console.print_json(data=client.invoke_capability(key, payload))


@capability_request_app.command("create")
def capability_request_create(
    body: Path = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
) -> None:
    resolved = _resolve_token(project_root, token or None)
    payload = read_json_file(body)
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


@capability_request_app.command("quote")
def capability_request_quote(
    request_id: str = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
) -> None:
    """Show the human-paid commission quote for a capability request (non-binding)."""
    resolved = _resolve_token(project_root, token or None)
    client = HydraceptClient(api, resolved)
    console.print_json(data=client.get_capability_request_quote(request_id))


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
    body: str = typer.Argument(
        None,
        help="JSON file path, inline JSON object, or - for stdin",
    ),
    input_json: str = typer.Option("", "--input", help="Inline JSON object"),
    body_file: Path | None = _input_file_option(),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    watch: bool = typer.Option(False, "--watch"),
) -> None:
    payload = _load_json_payload(body, input_json, body_file)
    workspace = _execution_workspace(project_root, token=token, api=api)
    config = read_json(config_path(project_root))
    payload = merge_workspace_job_context(payload, workspace, config=config)
    with _open_client(project_root, api, token) as client:
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
        if not job_id:
            return
        try:
            for progress in client.watch_job(str(job_id)):
                sys.stdout.write(f"{progress.status}\n")
                sys.stdout.flush()
                if progress.terminal:
                    console.print_json(data=progress.job)
                    try:
                        console.file.flush()
                    except Exception:
                        pass
                    sys.stdout.flush()
                    break
        except JobWaitTimeout as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1) from exc


@jobs_app.command("get")
def jobs_get(
    job_id: str = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
) -> None:
    client = HydraceptClient(api, _resolve_token(project_root, token or None))
    job = client.get_job(job_id)
    receipt = None
    try:
        receipt = client.get_job_receipt(job_id)
    except Exception:  # noqa: BLE001 — job JSON still useful if the receipt is unavailable
        receipt = None
    from hydracept.receipt_cost import present_job

    console.print_json(data=present_job(job, receipt))


@jobs_app.command("recover")
def jobs_recover(
    job_id: str = typer.Argument(...),
    wait: bool = typer.Option(True, "--wait/--no-wait"),
    timeout: float | None = typer.Option(None, "--timeout"),
    out: Path | None = typer.Option(None, "--out"),
    json_output: bool = typer.Option(False, "--json"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    api: str = typer.Option(DEFAULT_API, "--api"),
) -> None:
    """Wait to terminal and materialize artifacts (same as run)."""
    del json_output
    from hydracept.cli.run_facade import recover_job
    from hydracept.cli.workspace import require_ready_workspace

    workspace = require_ready_workspace(
        project_root,
        overrides=CliOverrides(
            token=token or None,
            api_url=None if api == DEFAULT_API else api,
        ),
    )
    outcome = recover_job(
        workspace,
        job_id,
        project_root=project_root,
        wait=wait,
        timeout=timeout,
        out=out,
    )
    console.print_json(data=outcome.payload())
    if outcome.exit_code:
        raise typer.Exit(outcome.exit_code)


@jobs_app.command("download")
def jobs_download(
    job_id: str = typer.Argument(...),
    out: Path | None = typer.Option(None, "--out"),
    json_output: bool = typer.Option(False, "--json"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    api: str = typer.Option(DEFAULT_API, "--api"),
) -> None:
    """Alias of `jobs recover --no-wait`."""
    jobs_recover(
        job_id,
        wait=False,
        timeout=None,
        out=out,
        json_output=json_output,
        project_root=project_root,
        token=token,
        api=api,
    )


@jobs_app.command("receipt")
def jobs_receipt(
    job_id: str = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
) -> None:
    client = HydraceptClient(api, _resolve_token(project_root, token or None))
    from hydracept.receipt_cost import present_receipt

    console.print_json(data=present_receipt(client.get_job_receipt(job_id)))


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
    payload = read_json_file(body)
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
    try:
        console.print_json(data=client.get_pinned_receipt(receipt_id))
    except HydraceptApiError as exc:
        payload = {
            "error": True,
            "code": exc.code or "NOT_FOUND",
            "message": str(exc),
            "nextAction": (
                f"python -m hydracept jobs receipt {receipt_id} --json"
                if str(receipt_id).startswith("wfr_")
                else "python -m hydracept jobs receipt <jobId> --json"
            ),
            "note": "pinned get is for pinned inference receipts. Smoke/run receipts use jobs receipt <jobId>.",
        }
        console.print_json(data=payload)
        raise typer.Exit(1) from exc


@pinned_app.command("bulk")
def pinned_bulk(
    body: Path = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
    wait: bool = typer.Option(False, "--wait"),
) -> None:
    """POST /v1/inference/pinned/bulk — concurrent pinned items, one logical execution each."""
    resolved = _resolve_token(project_root, token or None)
    payload = read_json_file(body)
    client = HydraceptClient(api, resolved)
    submitted = client.create_pinned_inference_bulk(payload)
    if not wait:
        console.print_json(data=submitted)
        return
    bulk_id = str(submitted.get("bulkId") or "")
    console.print_json(data=client.wait_pinned_bulk(bulk_id))


@pinned_app.command("bulk-get")
def pinned_bulk_get(
    bulk_id: str = typer.Argument(...),
    api: str = typer.Option(DEFAULT_API, "--api"),
    project_root: Path = typer.Option(Path.cwd(), "--project-root"),
    token: str = typer.Option("", "--token"),
) -> None:
    """GET /v1/inference/pinned/bulk/{bulk_id}."""
    client = HydraceptClient(api, _resolve_token(project_root, token or None))
    console.print_json(data=client.get_pinned_bulk(bulk_id))


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
