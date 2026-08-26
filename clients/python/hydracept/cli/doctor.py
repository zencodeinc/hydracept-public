"""Integration readiness checks for hydracept doctor (ADR-019)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console

from hydracept import __version__ as cli_version
from hydracept.cli.agent_status import manifest_path, refresh_agent_context_cache
from hydracept.cli.console_io import cli_console
from hydracept.cli.mcp_bind import bind_workspace_mcp
from hydracept.cli.exit_codes import AUTH, DOCTOR_FAILED, SUCCESS
from hydracept.cli.onboarding_next import (
    START_URL,
    credential_setup_next_steps,
    no_credential_detail,
)
from hydracept.cli.workspace import (
    CliOverrides,
    ResolvedWorkspace,
    WorkspaceState,
    auth_headers,
    config_path,
    read_json,
    resolve_workspace,
    secrets_path,
    workspace_state,
)

DEFAULT_SMOKE_CAPABILITY = "image.generate.v1"
_IMAGE_SMOKE_CAPABILITIES = frozenset(
    {"image.generate.v1", "image.generate.local.v1", "game.asset.image.v1"}
)


@dataclass
class DoctorCheck:
    name: str
    passed: bool
    detail: str
    fatal: bool = True
    next_action: str | None = None
    bucket: str = "platform"


@dataclass
class DoctorReport:
    checks: list[DoctorCheck] = field(default_factory=list)
    workspace: ResolvedWorkspace | None = None
    mcp: dict[str, Any] | None = None

    @property
    def passed(self) -> bool:
        return all(check.passed or not check.fatal for check in self.checks)

    def add(self, check: DoctorCheck) -> None:
        self.checks.append(check)

    def next_actions(self) -> list[str]:
        actions: list[str] = []
        for check in self.checks:
            if check.passed or not check.next_action:
                continue
            if check.next_action not in actions:
                actions.append(check.next_action)
        return actions

    def to_json_dict(self) -> dict[str, Any]:
        ws = self.workspace
        state = workspace_state(ws)
        ready = state == WorkspaceState.READY
        platform: dict[str, Any] = {}
        capabilities: dict[str, Any] = {}
        providers: dict[str, Any] = {}
        managed_trial: dict[str, Any] = {}

        for check in self.checks:
            entry = {"passed": check.passed, "detail": check.detail, "fatal": check.fatal}
            if check.bucket == "capabilities":
                capabilities[check.name] = entry
            elif check.bucket == "providers":
                providers[check.name] = entry
            elif check.bucket == "managedTrial":
                managed_trial[check.name] = entry
            else:
                platform[check.name] = entry

        payload = {
            "passed": self.passed,
            "workspace": {"state": state.value, "ready": ready},
            "platform": platform,
            "capabilities": capabilities,
            "providers": providers,
            "managedTrial": managed_trial,
            "failedChecks": [
                {
                    "name": check.name,
                    "detail": check.detail,
                    "nextAction": check.next_action,
                }
                for check in self.checks
                if not check.passed and check.fatal
            ],
            "warnings": [
                {"name": check.name, "detail": check.detail}
                for check in self.checks
                if not check.passed and not check.fatal
            ],
            "checks": [
                {
                    "name": check.name,
                    "passed": check.passed,
                    "detail": check.detail,
                    "fatal": check.fatal,
                    "nextAction": check.next_action,
                    "bucket": check.bucket,
                }
                for check in self.checks
            ],
            "nextActions": self.next_actions(),
        }
        if self.mcp is not None:
            payload["mcp"] = self.mcp
        return payload


def doctor_exit_code(report: DoctorReport) -> int:
    if report.passed:
        return SUCCESS
    if report.workspace is None:
        return AUTH
    return DOCTOR_FAILED


def project_alignment_checks(
    checkout_project: str,
    *,
    token_project: str = "",
    home_project: str = "",
) -> list[DoctorCheck]:
    """Checkout must match the bearer token project when that id is distinct from home.

    Live GET /v1/diagnostics/session currently returns the account home as
    ``projectId``. That is not the API key's project. A home mismatch is a
    warning so a new checkout can become ready. Fatal only when the session
    exposes a token project that is different from both home and checkout.
    """
    checkout = str(checkout_project or "").strip()
    token = str(token_project or "").strip()
    home = str(home_project or "").strip()
    token_is_authoritative = bool(token) and (not home or token != home)
    if token_is_authoritative and checkout != token:
        return [
            DoctorCheck(
                "local.config_project",
                False,
                f"resolved project={checkout} != token project={token}",
                next_action="python -m hydracept init --apply --yes --wait",
            )
        ]
    if home and checkout and checkout != home:
        return [
            DoctorCheck(
                "local.config_project",
                False,
                (
                    f"checkout project={checkout} != session home project={home}; "
                    "jobs use the checkout/token project"
                ),
                fatal=False,
            )
        ]
    if checkout:
        return [
            DoctorCheck(
                "local.config_project",
                True,
                f"project aligned ({checkout})",
                fatal=False,
            )
        ]
    return []


def _project_id_from_context(context: dict[str, Any]) -> str | None:
    project = context.get("project")
    if isinstance(project, dict) and project.get("id"):
        return str(project["id"])
    if context.get("productId"):
        return str(context["productId"])
    return None


def _environment_from_context(context: dict[str, Any]) -> str | None:
    environment = context.get("environment")
    if isinstance(environment, dict) and environment.get("slug"):
        return str(environment["slug"])
    if isinstance(environment, str):
        return environment
    return None


def _capability_keys(payload: Any) -> set[str]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("capabilities") or []
    else:
        return set()
    keys: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        key = item.get("key") or item.get("capabilityKey")
        if key:
            keys.add(str(key))
    return keys


def build_doctor_report(
    api: str,
    project_root: Path,
    token: str | None,
    *,
    smoke_capability: str = DEFAULT_SMOKE_CAPABILITY,
) -> DoctorReport:
    report = DoctorReport()
    api_base = api.rstrip("/")
    bind = bind_workspace_mcp(project_root)
    report.mcp = bind.to_dict()
    report.add(
        DoctorCheck(
            "local.mcp_bind",
            bind.bound,
            (
                f"stdio MCP bound ({', '.join(bind.project_config)})"
                if bind.bound
                else "could not bind project stdio MCP"
            ),
            fatal=False,
            next_action=(
                "Reload MCP in the coding agent once"
                if bind.reload_required
                else None
            ),
        )
    )

    pack_manifest = read_json(manifest_path(project_root))
    pack_installed = bool(pack_manifest)
    report.add(
        DoctorCheck(
            "agent.pack",
            pack_installed,
            (
                "agent pack installed"
                if pack_installed
                else "agent pack not installed after init"
            ),
            next_action=None if pack_installed else "python -m hydracept agents install --auto",
        )
    )
    resolved = resolve_workspace(project_root, overrides=CliOverrides(token=token, api_url=api))
    report.workspace = resolved

    if resolved is None:
        steps = credential_setup_next_steps(project_root)
        report.add(
            DoctorCheck(
                "local.credential",
                False,
                no_credential_detail(project_root),
                bucket="workspace",
                next_action=steps[0] if steps else f"Open {START_URL}",
            )
        )
        for step in steps[1:]:
            report.add(
                DoctorCheck(
                    "setup.next",
                    False,
                    "Additional setup step",
                    fatal=False,
                    bucket="workspace",
                    next_action=step,
                )
            )
        return report

    state = workspace_state(resolved)
    report.add(
        DoctorCheck(
            "workspace.state",
            state == WorkspaceState.READY,
            f"workspace state={state.value}",
            fatal=False,
            bucket="workspace",
            next_action=(
                "python -m hydracept configure"
                if state != WorkspaceState.READY
                else None
            ),
        )
    )

    headers = auth_headers(resolved.token)
    local_config = read_json(config_path(project_root))
    local_secrets = read_json(secrets_path(project_root))

    if local_config:
        report.add(
            DoctorCheck(
                "local.config",
                True,
                f"Found {config_path(project_root)}",
                fatal=False,
            )
        )
    else:
        report.add(
            DoctorCheck(
                "local.config",
                False,
                f"Missing {config_path(project_root)} — run python -m hydracept configure",
                fatal=False,
                next_action="python -m hydracept configure",
            )
        )

    credential_kind = str(local_secrets.get("kind") or "")
    if local_secrets.get("apiKey"):
        report.add(
            DoctorCheck(
                "local.credential",
                True,
                f"Project API credential present ({credential_kind or 'service_principal'})",
                fatal=False,
            )
        )
    else:
        report.add(
            DoctorCheck(
                "local.credential",
                True,
                "Using env or session credential",
                fatal=False,
            )
        )

    configured_api = str(local_config.get("apiBaseUrl") or "").rstrip("/")
    if configured_api and configured_api != api_base:
        report.add(
            DoctorCheck(
                "local.api_url",
                False,
                f"config apiBaseUrl={configured_api} differs from --api={api_base}",
                fatal=False,
            )
        )
    elif configured_api:
        report.add(
            DoctorCheck(
                "local.api_url",
                True,
                f"apiBaseUrl matches {api_base}",
                fatal=False,
            )
        )

    try:
        health = httpx.get(f"{api_base}/healthz", timeout=15.0)
        if health.status_code == 200 and (health.json() or {}).get("status") == "ok":
            report.add(DoctorCheck("api.healthz", True, "GET /healthz ok"))
        else:
            report.add(
                DoctorCheck(
                    "api.healthz",
                    False,
                    f"GET /healthz unexpected response ({health.status_code})",
                )
            )
    except httpx.HTTPError as exc:
        report.add(DoctorCheck("api.healthz", False, f"GET /healthz failed: {exc}"))

    session_payload: dict[str, Any] = {}
    try:
        session_resp = httpx.get(
            f"{api_base}/v1/diagnostics/session",
            headers=headers,
            timeout=30.0,
        )
        session_resp.raise_for_status()
        session_payload = session_resp.json()
        principal = session_payload.get("principalId")
        bundle = session_payload.get("routeBundleVersion")
        if principal and bundle:
            report.add(
                DoctorCheck(
                    "api.diagnostics_session",
                    True,
                    f"principal={principal!r} bundle={bundle!r}",
                )
            )
        else:
            report.add(
                DoctorCheck(
                    "api.diagnostics_session",
                    False,
                    "diagnostics/session missing principalId or routeBundleVersion",
                )
            )
    except httpx.HTTPError as exc:
        report.add(
            DoctorCheck(
                "api.diagnostics_session",
                False,
                f"GET /v1/diagnostics/session failed: {exc}",
            )
        )

    context_payload: dict[str, Any] = {}
    try:
        context_resp = httpx.get(
            f"{api_base}/v1/session/context",
            headers=headers,
            timeout=30.0,
        )
        if context_resp.status_code == 200:
            context_payload = context_resp.json()
            if context_payload.get("needsOnboarding"):
                report.add(
                    DoctorCheck(
                        "api.session_context",
                        False,
                        f"Account needs onboarding — complete {START_URL}",
                        next_action=f"Open {START_URL} then python -m hydracept login",
                    )
                )
            else:
                org = (context_payload.get("organization") or {}).get("displayName")
                project = (context_payload.get("project") or {}).get("displayName")
                report.add(
                    DoctorCheck(
                        "api.session_context",
                        True,
                        f"org={org!r} project={project!r}",
                    )
                )
        else:
            report.add(
                DoctorCheck(
                    "api.session_context",
                    False,
                    f"GET /v1/session/context returned {context_resp.status_code}",
                    fatal=False,
                )
            )
    except httpx.HTTPError as exc:
        report.add(
            DoctorCheck(
                "api.session_context",
                False,
                f"GET /v1/session/context failed: {exc}",
                fatal=False,
            )
        )

    if resolved.project_id and context_payload and not context_payload.get("needsOnboarding"):
        session_project = _project_id_from_context(context_payload) or ""
        token_project = str(session_payload.get("tokenProjectId") or "").strip()
        principal_project = str(session_payload.get("projectId") or "").strip()
        if not token_project and principal_project and principal_project != session_project:
            token_project = principal_project
        if not session_project:
            session_project = principal_project
        for check in project_alignment_checks(
            resolved.project_id,
            token_project=token_project,
            home_project=session_project,
        ):
            report.add(check)

    try:
        providers_resp = httpx.get(
            f"{api_base}/v1/diagnostics/providers",
            headers=headers,
            timeout=30.0,
        )
        if providers_resp.status_code == 200:
            providers_payload = providers_resp.json()
            ready = bool(providers_payload.get("imageGenerationReady"))
            byok_bound = bool(providers_payload.get("byokBound"))
            trial_remaining = float(providers_payload.get("managedTrialRemaining") or 0.0)
            smoke_available = bool(providers_payload.get("managedSmokeAvailable"))
            providers = providers_payload.get("generationProviders") or []
            detail = (
                f"imageGenerationReady={ready} byokBound={byok_bound} "
                f"managedTrialRemaining={trial_remaining:.2f} providers={providers!r}"
            )
            if smoke_capability in _IMAGE_SMOKE_CAPABILITIES:
                if ready and (byok_bound or smoke_available or trial_remaining > 0):
                    report.add(
                        DoctorCheck(
                            "api.image_generation",
                            True,
                            detail,
                            bucket="providers",
                            fatal=False,
                        )
                    )
                elif ready and not byok_bound and trial_remaining <= 0:
                    report.add(
                        DoctorCheck(
                            "api.image_generation",
                            False,
                            detail + " — connect BYOK before image jobs",
                            bucket="providers",
                            next_action="Open /v1/onboarding/byok from activation",
                        )
                    )
                elif not ready:
                    report.add(
                        DoctorCheck(
                            "api.image_generation",
                            False,
                            detail,
                            bucket="providers",
                            next_action="Platform image providers unavailable — connect OpenAI BYOK or retry later",
                        )
                    )
                else:
                    report.add(
                        DoctorCheck(
                            "api.image_generation",
                            True,
                            detail,
                            bucket="providers",
                            fatal=False,
                        )
                    )
            else:
                report.add(
                    DoctorCheck(
                        "api.diagnostics_providers",
                        True,
                        detail,
                        bucket="providers",
                        fatal=False,
                    )
                )
            if trial_remaining > 0 and not byok_bound:
                report.add(
                    DoctorCheck(
                        "api.managed_trial",
                        True,
                        f"Managed trial remaining ${trial_remaining:.2f}",
                        fatal=False,
                        bucket="managedTrial",
                        next_action="python -m hydracept smoke",
                    )
                )
        else:
            report.add(
                DoctorCheck(
                    "api.diagnostics_providers",
                    False,
                    f"GET /v1/diagnostics/providers returned {providers_resp.status_code}",
                    bucket="providers",
                )
            )
    except httpx.HTTPError as exc:
        report.add(
            DoctorCheck(
                "api.diagnostics_providers",
                False,
                f"GET /v1/diagnostics/providers failed: {exc}",
                bucket="providers",
            )
        )

    try:
        caps_resp = httpx.get(f"{api_base}/v1/capabilities", timeout=30.0)
        caps_resp.raise_for_status()
        cap_keys = _capability_keys(caps_resp.json())
        try:
            cache_info = refresh_agent_context_cache(project_root, api_base)
            added = cache_info.get("addedKeys") or []
            if cache_info.get("stale"):
                report.add(
                    DoctorCheck(
                        "local.agent_context_cache",
                        True,
                        (
                            f"rewrote stale {cache_info['path']} "
                            f"({cache_info['capabilityCount']} live keys; added {added[:8]})"
                        ),
                        fatal=False,
                    )
                )
            else:
                report.add(
                    DoctorCheck(
                        "local.agent_context_cache",
                        True,
                        f"wrote {cache_info['path']} ({cache_info['capabilityCount']} live keys)",
                        fatal=False,
                    )
                )
        except httpx.HTTPError as cache_exc:
            report.add(
                DoctorCheck(
                    "local.agent_context_cache",
                    False,
                    f"could not refresh .hydracept/agent-context.json: {cache_exc}",
                    fatal=False,
                    next_action="python -m hydracept agent-context",
                )
            )
        version_parts: list[int] = []
        for part in str(cli_version).split("+")[0].split("."):
            try:
                version_parts.append(int("".join(ch for ch in part if ch.isdigit()) or "0"))
            except ValueError:
                version_parts.append(0)
        while len(version_parts) < 3:
            version_parts.append(0)
        if tuple(version_parts[:3]) < (0, 3, 0):
            report.add(
                DoctorCheck(
                    "local.cli_version",
                    False,
                    (
                        f"CLI {cli_version} is below the 0.3 public contract. "
                        "In this checkout, use the repo CLI (`python -m hydracept`). "
                        "Outside it, `pip install -U hydracept` (0.3.2+ recommended)."
                    ),
                    fatal=False,
                    next_action="python -m hydracept --version",
                )
            )
        else:
            report.add(
                DoctorCheck(
                    "local.cli_version",
                    True,
                    f"CLI {cli_version} injects workspace context on jobs submit",
                    fatal=False,
                )
            )
        if smoke_capability in cap_keys:
            report.add(
                DoctorCheck(
                    "public_smoke",
                    True,
                    f"{smoke_capability} listed in GET /v1/capabilities",
                    bucket="capabilities",
                )
            )
        else:
            report.add(
                DoctorCheck(
                    "public_smoke",
                    False,
                    f"{smoke_capability} missing from public capability list",
                    bucket="capabilities",
                )
            )
    except httpx.HTTPError as exc:
        report.add(
            DoctorCheck(
                "public_smoke",
                False,
                f"GET /v1/capabilities failed: {exc}",
                bucket="capabilities",
            )
        )

    return report


def run_doctor(
    api: str,
    project_root: Path,
    token: str | None,
    *,
    smoke_capability: str = DEFAULT_SMOKE_CAPABILITY,
    json_output: bool = False,
    console: Console | None = None,
    repair: bool = False,
) -> int:
    """Run integration readiness checks. Returns process exit code."""
    out = console or cli_console()
    if repair:
        from hydracept.cli.project import repair_workspace_identity
        from hydracept.cli.workspace import WorkspaceIdentityError

        remote_id = None
        try:
            resolved = resolve_workspace(
                project_root, overrides=CliOverrides(token=token, api_url=api)
            )
            if resolved is not None:
                with httpx.Client(timeout=20.0) as client:
                    resp = client.get(
                        f"{resolved.api_url}/v1/session/context",
                        headers=auth_headers(resolved.token),
                    )
                    if resp.status_code == 200:
                        remote_id = _project_id_from_context(resp.json())
        except Exception:  # noqa: BLE001
            remote_id = None
        try:
            repair_workspace_identity(project_root, remote_project_id=remote_id)
        except WorkspaceIdentityError as exc:
            report = DoctorReport()
            report.add(DoctorCheck("local.identity_repair", False, str(exc)))
            return _finish(report, out, json_output)
    report = build_doctor_report(
        api,
        project_root,
        token,
        smoke_capability=smoke_capability,
    )
    return _finish(report, out, json_output)


def _finish(report: DoctorReport, console: Console, json_output: bool) -> int:
    if json_output:
        console.print_json(data=report.to_json_dict())
    else:
        payload = report.to_json_dict()
        console.print("[bold]Hydracept doctor[/bold]")
        ws = payload.get("workspace") or {}
        console.print(
            f"workspace: state={ws.get('state')} ready={ws.get('ready')}"
        )
        for check in report.checks:
            icon = "[green]PASS[/green]" if check.passed else (
                "[red]FAIL[/red]" if check.fatal else "[yellow]WARN[/yellow]"
            )
            console.print(f"{icon} {check.name}: {check.detail}")
        actions = report.next_actions()
        if actions:
            console.print("[bold]Next[/bold]")
            for action in actions:
                console.print(f"  → {action}")
        if report.passed:
            console.print(
                "[bold green]Doctor passed — run[/bold green] "
                "[bold]python -m hydracept smoke[/bold]"
            )
            mcp = payload.get("mcp") or {}
            if mcp.get("reloadRequired"):
                console.print(
                    "[yellow]Reload MCP once[/yellow] so stdio Hydracept uses this workspace."
                )
        else:
            console.print("[bold red]Doctor failed — fix checks above before submitting jobs.[/bold red]")

    return doctor_exit_code(report)
