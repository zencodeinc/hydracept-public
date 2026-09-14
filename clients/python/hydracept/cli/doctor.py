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
from hydracept.cli.mcp_bind import bind_workspace_mcp, inspect_workspace_mcp
from hydracept.cli.exit_codes import AUTH, DOCTOR_FAILED, SUCCESS
from hydracept.cli.onboarding_next import (
    START_URL,
    credential_setup_next_steps,
    no_credential_detail,
)
from hydracept.cli.project import load_project_binding
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
    identity: dict[str, Any] = field(default_factory=dict)
    project_binding: dict[str, Any] = field(default_factory=dict)
    mcp: dict[str, Any] | None = None
    funding: dict[str, Any] | None = None
    project_root: Path | None = None
    session_payload: dict[str, Any] = field(default_factory=dict)

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
        if isinstance(self.mcp, dict) and self.mcp.get("reloadRequired"):
            reload_action = "Start or reload Hydracept MCP in the coding agent once"
            if reload_action not in actions:
                actions.append(reload_action)
        return actions

    def _section_status(self, names: tuple[str, ...]) -> dict[str, Any]:
        matches = [check for check in self.checks if check.name in names]
        if not matches:
            return {"status": "unknown", "detail": "not checked"}
        failed = [check for check in matches if not check.passed]
        if failed:
            fatal = any(check.fatal for check in failed)
            return {
                "status": "failed" if fatal else "warning",
                "detail": failed[0].detail,
            }
        return {"status": "ready", "detail": matches[-1].detail}

    def sections(self) -> dict[str, Any]:
        ws = self.workspace
        identity = self._section_status(("local.credential", "api.diagnostics_session"))
        workspace = self._section_status(("workspace.state", "local.config", "local.api_url"))
        # Checkout binding is execution truth. Account home context is informational
        # and must never replace the project section just because Studio remembers a
        # different home project.
        project = self._section_status(("local.config_project",))
        managed = self._section_status(("api.managed_trial",))
        byok = self._section_status(("api.image_generation", "api.diagnostics_providers"))
        if isinstance(self.funding, dict):
            if self.funding.get("byokConnected"):
                byok = {"status": "ready", "detail": "BYOK bound"}
            elif self.funding.get("managedExecutionFundingAvailable"):
                byok = {
                    "status": "not_required",
                    "detail": "BYOK not bound; managed execution covers this workspace",
                }
        mcp_status = "ready" if isinstance(self.mcp, dict) and self.mcp else "unknown"
        mcp_detail = "configured" if mcp_status == "ready" else "not checked"
        if isinstance(self.mcp, dict):
            if self.mcp.get("reloadRequired"):
                mcp_status = "warning"
                mcp_detail = "configured; start or reload MCP once"
        environment = {
            "status": "ready" if ws and ws.environment else "unknown",
            "detail": (ws.environment if ws and ws.environment else "not bound"),
        }
        if ws and ws.project_id and project["status"] == "unknown":
            project = {"status": "ready", "detail": ws.project_id}
        return {
            "identity": identity,
            "workspace": workspace,
            "project": project,
            "environment": environment,
            "managedInference": managed,
            "byok": byok,
            "mcp": {"status": mcp_status, "detail": mcp_detail},
        }

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
            "identity": self.identity,
            "projectBinding": self.project_binding,
            "platform": platform,
            "capabilities": capabilities,
            "providers": providers,
            "managedTrial": managed_trial,
            "sections": self.sections(),
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
            ]
            + (
                [
                    {
                        "name": "mcp.reload",
                        "detail": "stdio MCP is bound; start or reload the MCP process once so it matches this checkout. CLI still works.",
                    }
                ]
                if isinstance(self.mcp, dict) and self.mcp.get("reloadRequired")
                else []
            ),
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
        if self.funding is not None:
            payload["funding"] = self.funding
        if self.project_root is not None:
            try:
                from hydracept.context import resolve_hydracept_context

                payload["context"] = resolve_hydracept_context(
                    self.project_root,
                    refresh=False,
                ).to_dict()
            except Exception:  # noqa: BLE001
                pass
            from hydracept.cli.consumer_versions import consumer_versions

            payload["versions"] = consumer_versions(
                self.project_root,
                session=self.session_payload,
            )
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
    """Execution requires checkout == credential. Home mismatch is informational.

    ``tokenProjectId`` (or a principal project distinct from session home) is the
    credential project. Session home is never used as the execution project.
    """
    from hydracept.context import PROJECT_CREDENTIAL_MISMATCH, build_resolved_context

    checkout = str(checkout_project or "").strip()
    token = str(token_project or "").strip()
    home = str(home_project or "").strip()
    credential = token
    if token and home and token == home and checkout and token != checkout:
        credential = ""
    ctx = build_resolved_context(
        checkout_project_id=checkout,
        credential_project_id=credential,
        home_project_id=home,
        workspace_ready=True,
    )
    checks: list[DoctorCheck] = []
    if ctx.mismatch == PROJECT_CREDENTIAL_MISMATCH:
        checks.append(
            DoctorCheck(
                "local.config_project",
                False,
                (
                    f"checkout project={checkout} != credential project={token}; "
                    "no execution project"
                ),
                next_action="python -m hydracept init --apply --yes --wait",
            )
        )
    elif checkout:
        checks.append(
            DoctorCheck(
                "local.config_project",
                True,
                f"execution project aligned to checkout ({checkout})",
                fatal=False,
            )
        )
    if ctx.home_project_differs:
        checks.append(
            DoctorCheck(
                "api.account_home_context",
                True,
                (
                    "Account home context is informational. "
                    f"home project={home} differs from checkout={checkout}; "
                    "checkout binding remains authoritative for execution."
                ),
                fatal=False,
            )
        )
    return checks


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


def _scripts_path_check() -> DoctorCheck:
    """Canonical invocation is `python -m hydracept`. Diagnose user-site Scripts on Windows."""
    import os
    import sys
    from pathlib import Path as PathLib

    if os.name != "nt":
        return DoctorCheck(
            "cli.path",
            True,
            "Use python -m hydracept (canonical)",
            fatal=False,
        )
    scripts_dirs: list[PathLib] = []
    for candidate in (PathLib(sys.prefix) / "Scripts", PathLib(sys.base_prefix) / "Scripts"):
        if candidate.is_dir():
            scripts_dirs.append(candidate)
    try:
        import site

        user_site = PathLib(site.getusersitepackages())
        user_scripts = user_site.parent / "Scripts"
        if user_scripts.is_dir():
            scripts_dirs.append(user_scripts)
    except Exception:
        user_scripts = None
    path_entries = [PathLib(part) for part in os.environ.get("PATH", "").split(os.pathsep) if part]
    resolved_path = []
    for entry in path_entries:
        try:
            resolved_path.append(entry.resolve())
        except OSError:
            continue
    missing = [
        directory
        for directory in scripts_dirs
        if directory.resolve() not in resolved_path
    ]
    if not missing:
        return DoctorCheck(
            "cli.path",
            True,
            "Python Scripts directories are on PATH; still prefer python -m hydracept",
            fatal=False,
        )
    return DoctorCheck(
        "cli.path",
        True,
        "Canonical invocation is python -m hydracept. A Scripts directory on PATH is optional.",
        fatal=False,
        next_action="python -m hydracept",
    )


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
    report.project_root = project_root
    api_base = api.rstrip("/")
    resolved = resolve_workspace(project_root, overrides=CliOverrides(token=token, api_url=api))
    bind = bind_workspace_mcp(project_root) if resolved is not None else inspect_workspace_mcp(project_root)
    report.mcp = bind.to_dict()
    report.add(_scripts_path_check())
    reload_or_start = (
        "Hydracept CLI is ready. Reload MCP once to enable IDE tools."
        if bind.reload_required and bind.bound
        else (
            "Run python -m hydracept doctor --fix to repair stale MCP config generations"
            if getattr(bind, "config_stale", False)
            else (
                "Start or reload Hydracept MCP in the coding agent once"
                if bind.reload_required
                else None
            )
        )
    )
    report.add(
        DoctorCheck(
            "local.mcp_bind",
            bind.bound,
            (
                f"stdio MCP bound ({', '.join(bind.project_config)})"
                if bind.bound
                else "project stdio MCP is not bound yet; run init or python -m hydracept mcp bind"
            ),
            fatal=False,
            next_action=reload_or_start,
        )
    )
    runtime_status = bind.runtime.status if bind.runtime else "missing"
    if runtime_status in {
        "workspace_mismatch",
        "project_mismatch",
        "generation_mismatch",
        "pid_reused",
        "stale",
    }:
        report.add(
            DoctorCheck(
                "local.mcp_runtime",
                False,
                (
                    f"stdio MCP runtime is {runtime_status}; CLI still works. "
                    "Start or reload MCP so the live process matches this checkout."
                ),
                fatal=False,
                next_action="Start or reload Hydracept MCP in the coding agent once, or use python -m hydracept run",
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
                else "Agent pack missing. CLI still works; run python -m hydracept agents install --auto."
            ),
            fatal=False,
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
                "python -m hydracept init --apply --yes"
                if state != WorkspaceState.READY
                else None
            ),
        )
    )

    headers = auth_headers(resolved.token)
    local_config = read_json(config_path(project_root))
    local_secrets = read_json(secrets_path(project_root))
    binding = load_project_binding(project_root)

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
                f"Missing {config_path(project_root)} — run python -m hydracept init --apply --yes",
                fatal=False,
                next_action="python -m hydracept init --apply --yes",
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
        report.session_payload = session_payload if isinstance(session_payload, dict) else {}
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
    except httpx.HTTPStatusError as exc:
        rejected = exc.response.status_code in {401, 403}
        report.add(
            DoctorCheck(
                "api.diagnostics_session",
                False,
                (
                    "Installed credential was rejected. Recover with "
                    "python -m hydracept init --apply --yes --json"
                    if rejected
                    else f"GET /v1/diagnostics/session failed: {exc}"
                ),
                next_action=(
                    "python -m hydracept init --apply --yes --json" if rejected else None
                ),
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
                        "api.account_home_context",
                        False,
                        f"Account needs onboarding — complete {START_URL}",
                        next_action=f"Open {START_URL} then python -m hydracept doctor --fix",
                    )
                )
            else:
                org = (context_payload.get("organization") or {}).get("displayName")
                home_project = (context_payload.get("project") or {}).get("displayName")
                checkout_name = str(
                    binding.get("projectName") or resolved.project_id or ""
                ).strip()
                report.add(
                    DoctorCheck(
                        "api.account_home_context",
                        True,
                        (
                            f"account home org={org!r} project={home_project!r}; "
                            f"checkout project={checkout_name!r} is authoritative for project-scoped execution"
                        ),
                        fatal=False,
                    )
                )
        else:
            report.add(
                DoctorCheck(
                    "api.account_home_context",
                    False,
                    f"GET /v1/session/context returned {context_resp.status_code}",
                    fatal=False,
                )
            )
    except httpx.HTTPError as exc:
        report.add(
            DoctorCheck(
                "api.account_home_context",
                False,
                f"GET /v1/session/context failed: {exc}",
                fatal=False,
            )
        )

    identity_block = context_payload.get("identity") if isinstance(context_payload.get("identity"), dict) else {}
    report.identity = {
        "status": "ready" if session_payload or identity_block or resolved.token else "action_required",
        "provider": identity_block.get("provider"),
        "account": identity_block.get("account") or identity_block.get("displayName"),
        "authenticated": bool(identity_block.get("authenticated") or session_payload or resolved.token),
    }
    bound_id = str(binding.get("projectId") or resolved.project_id or "").strip()
    resolution = str(binding.get("resolution") or "").strip()
    if bound_id:
        source = {
            "existing_binding": "existing binding",
            "repository_match": "repository match",
            "workspace_match": "workspace match",
            "created_from_repository": "created from repository",
            "created_from_workspace": "created from workspace",
            "explicit_selection": "explicit selection",
        }.get(resolution, resolution.replace("_", " ") or "existing binding")
        report.project_binding = {
            "status": "ready",
            "projectId": bound_id,
            "displayName": binding.get("projectName"),
            "environment": binding.get("environment") or resolved.environment or "development",
            "source": source,
            "resolution": resolution or "existing_binding",
        }
        report.add(
            DoctorCheck(
                "local.config_project",
                True,
                (
                    f"execution project={binding.get('projectName') or bound_id!r} "
                    f"({bound_id}) from {source}"
                ),
                fatal=False,
            )
        )
    else:
        report.project_binding = {
            "status": "action_required",
            "reason": "project not bound",
            "environment": resolved.environment or "development",
        }

    # Session "current project" is Studio/account-home state, not this checkout.
    if (
        not str(binding.get("projectId") or "").strip()
        and resolved.project_id
        and context_payload
        and not context_payload.get("needsOnboarding")
    ):
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
            provider_ready = bool(
                providers_payload.get("imageProviderReady", providers_payload.get("imageGenerationReady"))
            )
            byok_bound = bool(providers_payload.get("byokBound"))
            trial_remaining = float(providers_payload.get("managedTrialRemaining") or 0.0)
            customer_credit = float(providers_payload.get("managedCreditRemaining") or 0.0)
            smoke_available = bool(providers_payload.get("managedSmokeAvailable"))
            execution_available = bool(providers_payload.get("managedExecutionFundingAvailable"))
            funding_source = str(providers_payload.get("managedExecutionFundingSource") or "unknown")
            coverage = str(providers_payload.get("managedExecutionCoverage") or "").strip()
            providers = providers_payload.get("generationProviders") or []
            from hydracept.cli.funding import funding_payload_from_diagnostics

            report.funding = funding_payload_from_diagnostics(
                providers_payload if isinstance(providers_payload, dict) else {},
                project_id=str(resolved.project_id or ""),
                environment=str(resolved.environment or ""),
            )
            detail = (
                f"imageGenerationReady={ready} imageProviderReady={provider_ready} "
                f"byokBound={byok_bound} managedCreditRemaining={customer_credit:.2f} "
                f"managedExecutionFundingAvailable={execution_available or smoke_available} "
                f"managedExecutionFundingSource={funding_source!r} "
                f"managedTrialRemaining={trial_remaining:.2f} providers={providers!r}"
            )
            if coverage:
                detail += f" — {coverage}"

            if smoke_capability in _IMAGE_SMOKE_CAPABILITIES:
                if ready:
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
                    access = (
                        providers_payload.get("imageGenerationAccess")
                        if isinstance(providers_payload.get("imageGenerationAccess"), dict)
                        else {}
                    )
                    action = access.get("requiredAction") if isinstance(access.get("requiredAction"), dict) else {}
                    next_action = str(action.get("url") or "").strip() or None
                    reason = str(access.get("reason") or "not_runnable")
                    report.add(
                        DoctorCheck(
                            "api.image_generation",
                            False,
                            detail + f" — workspace reason={reason}",
                            bucket="providers",
                            next_action=next_action,
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
                        "Outside it, `pip install -U hydracept` (0.3.17+ required for current init, receipts, funding display, and PowerShell --input-file)."
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
    fix: bool = False,
) -> int:
    """Run integration readiness checks. Returns process exit code."""
    out = console or cli_console()
    if fix:
        from hydracept.cli.doctor_fix import apply_doctor_fix
        from hydracept.cli.exit_codes import DOCTOR_FAILED, SUCCESS

        fix_result = apply_doctor_fix(project_root)
        report = build_doctor_report(
            api,
            project_root,
            token,
            smoke_capability=smoke_capability,
        )
        payload = report.to_json_dict()
        payload["fix"] = fix_result.to_dict()
        if json_output:
            out.print_json(data=payload)
        else:
            _finish(report, out, False)
            if fix_result.blocked:
                out.print("[yellow]repair_blocked — Hydracept will not overwrite user-owned MCP bytes[/yellow]")
            if fix_result.reload_required:
                out.print("[yellow]Start or reload MCP once (humanActionRequired=reload_cursor)[/yellow]")
        if fix_result.blocked or not report.passed:
            return DOCTOR_FAILED
        return SUCCESS
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
        identity = payload.get("identity") or {}
        binding = payload.get("projectBinding") or {}
        console.print("[bold]Hydracept doctor[/bold]")
        identity_status = str(identity.get("status") or "unknown")
        identity_label = identity_status.replace("_", " ")
        provider = identity.get("provider")
        account = identity.get("account")
        identity_bits = " / ".join(part for part in (provider, account) if part)
        if identity_bits:
            console.print(f"Identity: {identity_label} ({identity_bits})")
        else:
            console.print(f"Identity: {identity_label}")
        binding_status = str(binding.get("status") or "unknown").replace("_", " ")
        console.print(f"Project binding: {binding_status}")
        if binding.get("displayName") or binding.get("projectId"):
            console.print(
                f"Execution project: {binding.get('displayName') or binding.get('projectId')} "
                f"({binding.get('projectId') or 'unbound'})"
            )
        if binding.get("source"):
            console.print(f"Project source: {binding.get('source')}")
        if binding.get("reason") and binding.get("status") != "ready":
            console.print(f"Reason: {binding.get('reason')}")
        if binding.get("environment"):
            console.print(f"Environment: {binding.get('environment')}")
        funding = payload.get("funding") if isinstance(payload.get("funding"), dict) else {}
        if funding:
            console.print(
                "Funding: customer credit="
                f"{funding.get('managedCreditRemainingUsd')} "
                f"executionFunding={funding.get('managedExecutionFundingAvailable')} "
                f"source={funding.get('managedExecutionFundingSource')}"
            )
            if funding.get("managedExecutionCoverage"):
                console.print(f"  {funding.get('managedExecutionCoverage')}")
        ws = payload.get("workspace") or {}
        console.print(
            f"workspace: state={ws.get('state')} ready={ws.get('ready')}"
        )
        labels = (
            ("identity", "Identity"),
            ("workspace", "Workspace"),
            ("project", "Hydracept project"),
            ("environment", "Environment"),
            ("managedInference", "Managed inference"),
            ("byok", "BYOK"),
            ("mcp", "MCP"),
        )
        sections = payload.get("sections") or {}
        for key, title in labels:
            section = sections.get(key) or {}
            status = str(section.get("status") or "unknown")
            detail = str(section.get("detail") or "")
            if status == "ready":
                icon = "[green]✓[/green]"
            elif status == "not_required":
                icon = "[dim]✓[/dim]"
            elif status == "warning":
                icon = "[yellow]○[/yellow]"
            elif status == "unknown":
                icon = "[dim]○[/dim]"
            else:
                icon = "[red]✗[/red]"
            console.print(f"[bold]{title}[/bold]")
            console.print(f"  {icon} {detail}")
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
                    "[yellow]Start or reload MCP once[/yellow] so stdio Hydracept uses this workspace."
                )
        else:
            console.print("[bold red]Doctor failed — fix checks above before submitting jobs.[/bold red]")

    return doctor_exit_code(report)
