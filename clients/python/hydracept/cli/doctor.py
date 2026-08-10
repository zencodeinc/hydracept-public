"""Integration readiness checks for hydracept doctor."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console

from hydracept.cli.workspace import (
    auth_headers,
    config_path,
    read_json,
    resolve_token,
    secrets_path,
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


@dataclass
class DoctorReport:
    checks: list[DoctorCheck] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(check.passed or not check.fatal for check in self.checks)

    def add(self, check: DoctorCheck) -> None:
        self.checks.append(check)


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


def run_doctor(
    api: str,
    project_root: Path,
    token: str | None,
    *,
    smoke_capability: str = DEFAULT_SMOKE_CAPABILITY,
    json_output: bool = False,
    console: Console | None = None,
) -> int:
    """Run integration readiness checks. Returns process exit code."""
    out = console or Console()
    report = DoctorReport()
    api_base = api.rstrip("/")
    resolved = resolve_token(project_root, token)

    if not resolved:
        report.add(
            DoctorCheck(
                "local.credential",
                False,
                "No API credential — run hydracept login && hydracept init --apply --yes",
            )
        )
        return _finish(report, out, json_output)

    headers = auth_headers(resolved)
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
                f"Missing {config_path(project_root)} — run hydracept init",
                fatal=False,
            )
        )

    credential_kind = str(local_secrets.get("kind") or "")
    if local_secrets.get("apiKey"):
        report.add(
            DoctorCheck(
                "local.credential",
                True,
                f"Project API credential present ({credential_kind or 'service_principal'})",
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

    # --- API probes ---
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
                        "Account needs onboarding — complete /start provisioning",
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

    # Align local config with server session
    if local_config and context_payload and not context_payload.get("needsOnboarding"):
        config_project = str(local_config.get("projectId") or "")
        session_project = _project_id_from_context(context_payload) or ""
        config_env = str(local_config.get("environment") or "")
        session_env = _environment_from_context(context_payload) or ""
        session_diag_project = str(session_payload.get("projectId") or "")

        if config_project and session_project and config_project != session_project:
            report.add(
                DoctorCheck(
                    "local.config_project",
                    False,
                    f"config projectId={config_project} != session project={session_project}",
                )
            )
        elif config_project and session_diag_project and config_project != session_diag_project:
            report.add(
                DoctorCheck(
                    "local.config_project",
                    False,
                    f"config projectId={config_project} != diagnostics project={session_diag_project}",
                )
            )
        elif config_project:
            report.add(
                DoctorCheck(
                    "local.config_project",
                    True,
                    f"projectId aligned ({config_project})",
                    fatal=False,
                )
            )

        if config_env and session_env and config_env != session_env:
            report.add(
                DoctorCheck(
                    "local.config_environment",
                    False,
                    f"config environment={config_env} != session environment={session_env}",
                    fatal=False,
                )
            )
        elif config_env and session_env:
            report.add(
                DoctorCheck(
                    "local.config_environment",
                    True,
                    f"environment aligned ({config_env})",
                    fatal=False,
                )
            )

    providers_payload: dict[str, Any] = {}
    try:
        providers_resp = httpx.get(
            f"{api_base}/v1/diagnostics/providers",
            headers=headers,
            timeout=30.0,
        )
        if providers_resp.status_code == 200:
            providers_payload = providers_resp.json()
            ready = bool(providers_payload.get("imageGenerationReady"))
            providers = providers_payload.get("generationProviders") or []
            detail = f"imageGenerationReady={ready} providers={providers!r}"
            if smoke_capability in _IMAGE_SMOKE_CAPABILITIES:
                report.add(
                    DoctorCheck(
                        "api.image_generation",
                        ready,
                        detail,
                    )
                )
            else:
                report.add(
                    DoctorCheck(
                        "api.diagnostics_providers",
                        True,
                        detail,
                        fatal=False,
                    )
                )
        else:
            report.add(
                DoctorCheck(
                    "api.diagnostics_providers",
                    False,
                    f"GET /v1/diagnostics/providers returned {providers_resp.status_code}",
                )
            )
    except httpx.HTTPError as exc:
        report.add(
            DoctorCheck(
                "api.diagnostics_providers",
                False,
                f"GET /v1/diagnostics/providers failed: {exc}",
            )
        )

    try:
        caps_resp = httpx.get(f"{api_base}/v1/capabilities", timeout=30.0)
        caps_resp.raise_for_status()
        cap_keys = _capability_keys(caps_resp.json())
        if smoke_capability in cap_keys:
            report.add(
                DoctorCheck(
                    "api.smoke_capability",
                    True,
                    f"{smoke_capability} listed in GET /v1/capabilities",
                )
            )
        else:
            report.add(
                DoctorCheck(
                    "api.smoke_capability",
                    False,
                    f"{smoke_capability} missing from public capability list",
                )
            )
    except httpx.HTTPError as exc:
        report.add(
            DoctorCheck(
                "api.smoke_capability",
                False,
                f"GET /v1/capabilities failed: {exc}",
            )
        )

    return _finish(report, out, json_output)


def _finish(report: DoctorReport, console: Console, json_output: bool) -> int:
    if json_output:
        payload = {
            "passed": report.passed,
            "checks": [
                {
                    "name": check.name,
                    "passed": check.passed,
                    "detail": check.detail,
                    "fatal": check.fatal,
                }
                for check in report.checks
            ],
        }
        console.print_json(data=payload)
    else:
        console.print("[bold]Hydracept doctor[/bold]")
        for check in report.checks:
            icon = "[green]PASS[/green]" if check.passed else (
                "[red]FAIL[/red]" if check.fatal else "[yellow]WARN[/yellow]"
            )
            console.print(f"{icon} {check.name}: {check.detail}")
        if report.passed:
            console.print("[bold green]Doctor passed — integration ready for launch smoke.[/bold green]")
        else:
            console.print("[bold red]Doctor failed — fix checks above before submitting jobs.[/bold red]")

    return 0 if report.passed else 1
