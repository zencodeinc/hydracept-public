"""Unified bootstrap resolver (ADR-028)."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import httpx

from hydracept.cli.bootstrap_session_store import (
    bootstrap_session_expired,
    clear_bootstrap_session,
    load_bootstrap_session,
    save_bootstrap_session,
    stored_bootstrap_session_matches_api,
)
from hydracept.cli.bootstrap import ConfigureError, ensure_gitignore, run_configure, write_secrets
from hydracept.cli.connections_cmd import adopt_from_env, adopt_provider_secret
from hydracept.cli.doctor import DEFAULT_SMOKE_CAPABILITY, build_doctor_report, doctor_exit_code
from hydracept.cli.mcp_bind import bind_workspace_mcp
from hydracept.cli.exit_codes import AUTH, DOCTOR_FAILED, SUCCESS, USAGE
from hydracept.cli.login_flow import LoginError, login_with_token
from hydracept.cli.project import (
    capability_profile,
    load_project_binding,
    resolve_suggested_project_name,
    write_project_binding,
)
from hydracept.cli.provider_discovery import discover_provider_labels
from hydracept.cli.session_client import (
    SessionClientError,
    create_key,
    environment_from_session_context,
    fetch_session_context,
    project_from_session_context,
)
from hydracept.cli.session_store import DEFAULT_APP_BASE_URL, load_session
from hydracept.cli.workspace import (
    CliOverrides,
    WorkspaceState,
    auth_headers,
    read_json,
    resolve_workspace,
    secrets_path,
    workspace_state,
)

INIT_SCHEMA_VERSION = "hydracept.cli.init.v1"
InitStatus = Literal["ready", "interaction_required", "configuration_required"]


@dataclass
class InitResult:
    exit_code: int
    payload: dict[str, Any] = field(default_factory=dict)


def _base_payload(status: str) -> dict[str, Any]:
    return {"schemaVersion": INIT_SCHEMA_VERSION, "status": status}


def _attach_mcp(project_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    payload["mcp"] = bind_workspace_mcp(project_root).to_dict()
    return payload


def _interaction(
    reason: str,
    url: str,
    *,
    bootstrap_session_id: str | None = None,
    wait_available: bool = True,
) -> InitResult:
    payload = _base_payload("interaction_required")
    payload["reason"] = reason
    action: dict[str, Any] = {"type": "open_url", "url": url}
    if wait_available:
        action["waitCommand"] = "python -m hydracept init --apply --yes --wait"
        if bootstrap_session_id:
            action["waitCommandJson"] = (
                "python -m hydracept init --apply --yes --json --wait"
            )
    payload["action"] = action
    if bootstrap_session_id:
        payload["bootstrapSessionId"] = bootstrap_session_id
    return InitResult(exit_code=SUCCESS, payload=payload)


def _configuration_required(reason: str, **extra: Any) -> InitResult:
    payload = _base_payload("configuration_required")
    payload["reason"] = reason
    payload.update(extra)
    return InitResult(exit_code=SUCCESS, payload=payload)


def _device_verification_url() -> str:
    app_base = os.environ.get("HYDRACEPT_APP_URL", DEFAULT_APP_BASE_URL).rstrip("/")
    return f"{app_base}/device"


def _fetch_bootstrap_session(api_url: str, session_id: str) -> dict[str, Any] | None:
    if not session_id:
        return None
    try:
        response = httpx.get(
            f"{api_url.rstrip('/')}/v1/bootstrap/sessions/{session_id}",
            timeout=30.0,
        )
        if response.status_code == 200:
            body = response.json()
            if isinstance(body, dict):
                return body
    except httpx.HTTPError:
        pass
    return None


def _post_bootstrap_session(
    project_root: Path,
    api_url: str,
    *,
    binding: dict[str, Any],
) -> tuple[str, str, str | None]:
    """Return (session_id, connect_url, expires_at)."""
    from hydracept.cli.machine import machine_fingerprint

    suggested_name = resolve_suggested_project_name(project_root, binding)
    response = httpx.post(
        f"{api_url.rstrip('/')}/v1/bootstrap/sessions",
        json={
            "repoPath": str(project_root.resolve()),
            "machineFingerprint": machine_fingerprint(),
            "projectId": binding.get("projectId"),
            "projectName": suggested_name,
            "environment": binding.get("environment") or "development",
            "detectedProviders": discover_provider_labels(project_root),
        },
        timeout=30.0,
    )
    response.raise_for_status()
    body = response.json()
    session_id = str(body.get("sessionId") or "").strip()
    connect_url = str(body.get("connectUrl") or "").strip()
    expires_at = str(body.get("expiresAt") or "").strip() or None
    if not connect_url:
        raise httpx.HTTPError("bootstrap session missing connectUrl")
    return session_id, connect_url, expires_at


def _resolve_bootstrap_session(
    project_root: Path,
    api_url: str,
    *,
    binding: dict[str, Any],
) -> tuple[str, str]:
    """Return (session_id, connect_url). Reuses a pending local session when valid."""
    api = api_url.rstrip("/")
    stored = load_bootstrap_session(project_root)
    if stored and stored_bootstrap_session_matches_api(stored, api):
        session_id = str(stored.get("sessionId") or "").strip()
        connect_url = str(stored.get("connectUrl") or "").strip()
        if session_id and not bootstrap_session_expired(stored):
            remote = _fetch_bootstrap_session(api, session_id)
            if remote is not None:
                status = str(remote.get("status") or "")
                if status == "pending":
                    if not connect_url:
                        connect_url = f"{api}/connect/{session_id}"
                    return session_id, connect_url
                if status == "approved":
                    if not connect_url:
                        connect_url = f"{api}/connect/{session_id}"
                    return session_id, connect_url
                clear_bootstrap_session(project_root)
        else:
            clear_bootstrap_session(project_root)

    try:
        session_id, connect_url, expires_at = _post_bootstrap_session(
            project_root,
            api,
            binding=binding,
        )
        save_bootstrap_session(
            project_root,
            session_id=session_id,
            connect_url=connect_url,
            api_url=api,
            expires_at=expires_at,
        )
        ensure_gitignore(project_root)
        return session_id, connect_url
    except httpx.HTTPError:
        return "", _device_verification_url()


def _create_bootstrap_session(
    project_root: Path,
    api_url: str,
    *,
    binding: dict[str, Any],
) -> tuple[str, str]:
    """Return (session_id, connect_url). Falls back to device verification URL."""
    if unified_bootstrap_enabled():
        return _resolve_bootstrap_session(project_root, api_url, binding=binding)
    return "", _device_verification_url()


def _emit_wait_progress(
    *,
    json_output: bool,
    session_id: str,
    connect_url: str,
    seconds_remaining: int,
) -> None:
    """Keep --wait observable. JSON progress goes to stderr so stdout stays one object."""
    if json_output:
        print(
            json.dumps(
                {
                    "status": "waiting",
                    "reason": "browser_setup",
                    "bootstrapSessionId": session_id,
                    "secondsRemaining": seconds_remaining,
                    "detail": "Open action.url, then this command continues",
                    "action": {"type": "open_url", "url": connect_url},
                }
            ),
            file=sys.stderr,
            flush=True,
        )
        return
    print(
        f"Waiting for browser setup… {connect_url} ({seconds_remaining}s left)",
        flush=True,
    )


def _poll_bootstrap_session(
    api_url: str,
    session_id: str,
    *,
    poll_seconds: int,
    connect_url: str = "",
    json_output: bool = False,
) -> dict[str, Any] | None:
    if not session_id:
        return None
    deadline = time.time() + max(5, poll_seconds)
    last_emit = 0.0
    while time.time() < deadline:
        remaining = max(0, int(deadline - time.time()))
        now = time.time()
        if last_emit == 0.0 or now - last_emit >= 15:
            _emit_wait_progress(
                json_output=json_output,
                session_id=session_id,
                connect_url=connect_url,
                seconds_remaining=remaining,
            )
            last_emit = now
        body = _fetch_bootstrap_session(api_url, session_id)
        if body is not None:
            status = str(body.get("status") or "")
            if status == "approved":
                return body
            if status == "expired":
                return None
        time.sleep(2)
    return None


@dataclass(frozen=True)
class _BrowserBootstrapResult:
    api_key: str
    project_id: str
    environment: str
    setup_grant: str | None
    binding: dict[str, Any]


def _apply_browser_bootstrap(
    project_root: Path,
    body: dict[str, Any],
    *,
    prior_binding: dict[str, Any],
) -> _BrowserBootstrapResult | None:
    api_key = str(body.get("installationApiKey") or "").strip()
    project_id = str(body.get("projectId") or "").strip()
    environment = str(body.get("environment") or "development").strip() or "development"
    if not api_key or not project_id:
        return None
    write_secrets(project_root, {"apiKey": api_key, "kind": "api_key", "schemaVersion": 2})
    ensure_gitignore(project_root)
    binding = {
        **prior_binding,
        "projectId": project_id,
        "environment": environment,
        "capabilityProfile": capability_profile(prior_binding),
    }
    write_project_binding(project_root, binding)
    setup_grant = str(body.get("setupGrant") or "").strip() or None
    clear_bootstrap_session(project_root)
    return _BrowserBootstrapResult(
        api_key=api_key,
        project_id=project_id,
        environment=environment,
        setup_grant=setup_grant,
        binding=binding,
    )


def _bootstrap_interaction(
    reason: str,
    project_root: Path,
    api_url: str,
    binding: dict[str, Any],
    *,
    wait: bool,
    poll_seconds: int,
    json_output: bool = False,
) -> InitResult | _BrowserBootstrapResult:
    session_id, connect_url = _create_bootstrap_session(project_root, api_url, binding=binding)
    if wait and session_id and unified_bootstrap_enabled():
        remote = _fetch_bootstrap_session(api_url, session_id)
        approved = remote if remote and str(remote.get("status") or "") == "approved" else None
        if approved is None:
            approved = _poll_bootstrap_session(
                api_url,
                session_id,
                poll_seconds=poll_seconds,
                connect_url=connect_url,
                json_output=json_output,
            )
        if approved is not None:
            applied = _apply_browser_bootstrap(project_root, approved, prior_binding=binding)
            if applied is not None:
                return applied
        return InitResult(
            exit_code=AUTH,
            payload={
                **_base_payload("interaction_required"),
                "reason": "bootstrap_wait_timeout",
                "bootstrapSessionId": session_id,
                "detail": "Browser setup did not complete within the poll window",
                "action": {
                    "type": "open_url",
                    "url": connect_url,
                    "waitCommand": "python -m hydracept init --apply --yes --wait",
                    "waitCommandJson": "python -m hydracept init --apply --yes --json --wait",
                },
            },
        )
    return _interaction(
        reason,
        connect_url,
        bootstrap_session_id=session_id or None,
    )


def _interaction_url(project_root: Path, api_url: str, binding: dict[str, Any]) -> str:
    if unified_bootstrap_enabled():
        _, connect_url = _create_bootstrap_session(project_root, api_url, binding=binding)
        return connect_url
    return _device_verification_url()


def _fetch_providers(api_url: str, token: str) -> dict[str, Any]:
    try:
        response = httpx.get(
            f"{api_url.rstrip('/')}/v1/diagnostics/providers",
            headers=auth_headers(token),
            timeout=30.0,
        )
        if response.status_code == 200:
            body = response.json()
            return body if isinstance(body, dict) else {}
    except httpx.HTTPError:
        pass
    return {}


def _fetch_readiness(
    api_url: str,
    token: str,
    capabilities: list[str],
) -> dict[str, Any]:
    try:
        response = httpx.get(
            f"{api_url.rstrip('/')}/v1/diagnostics/readiness",
            headers=auth_headers(token),
            params={"capabilities": capabilities},
            timeout=30.0,
        )
        if response.status_code == 200:
            body = response.json()
            return body if isinstance(body, dict) else {}
    except httpx.HTTPError:
        pass
    return {}


def try_install_agent_pack(project_root: Path) -> tuple[bool, str]:
    """Filesystem pack install. Failures do not unwind auth/project init."""
    try:
        from hydracept.cli.agents.install import install_agent_pack

        pack = install_agent_pack(project_root, auto=True, smoke=False)
        return bool(pack.hosts), ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def agent_pack_init_fields(
    pack_installed: bool,
    pack_error: str,
    *,
    doctor_ok: bool,
) -> dict[str, Any]:
    ready = bool(doctor_ok and pack_installed)
    fields: dict[str, Any] = {
        "initialized": True,
        "ready": ready,
        "agentPackInstalled": pack_installed,
    }
    if not pack_installed:
        fields["nextAction"] = "python -m hydracept agents install --auto"
        if pack_error:
            fields["agentPackError"] = pack_error
    return fields


def doctor_init_fields(report: Any, doctor_code: int) -> dict[str, Any]:
    checks = list(getattr(report, "checks", None) or [])
    return {
        "status": "passed" if doctor_code == SUCCESS else "failed",
        "failedChecks": [
            {
                "name": check.name,
                "detail": check.detail,
                "nextAction": check.next_action,
            }
            for check in checks
            if not check.passed and check.fatal
        ],
        "warnings": [
            {"name": check.name, "detail": check.detail}
            for check in checks
            if not check.passed and not check.fatal
        ],
    }


def _providers_section(
    readiness: dict[str, Any],
    adopt_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    section: dict[str, Any] = {}
    provider_states = readiness.get("providers") or {}
    if isinstance(provider_states, dict):
        for provider, state in provider_states.items():
            if isinstance(state, dict):
                section[str(provider)] = {
                    "status": state.get("status", "unknown"),
                    "action": state.get("action", "none"),
                }
            else:
                section[str(provider)] = {"status": str(state), "action": "none"}
    for row in adopt_results or []:
        provider = str(row.get("provider") or "")
        if not provider:
            continue
        result = str(row.get("result") or "connected")
        section[provider] = {
            "status": "ready" if result in {"connected", "reused", "created"} else result,
            "action": result,
            "source": row.get("source"),
        }
    return section


def _capabilities_section(readiness: dict[str, Any]) -> dict[str, Any]:
    section: dict[str, Any] = {}
    items = readiness.get("capabilities") or {}
    if isinstance(items, dict):
        for key, value in items.items():
            if isinstance(value, dict):
                section[str(key)] = {"status": value.get("status", "unknown")}
            else:
                section[str(key)] = {"status": str(value)}
    return section


def _ensure_installation_credential(
    project_root: Path,
    *,
    project_id: str,
    environment: str,
    api_url: str,
) -> tuple[str, str]:
    """Return (api_key, action created|reused)."""
    secrets = read_json(secrets_path(project_root))
    existing = str(secrets.get("apiKey") or secrets.get("token") or "").strip()
    if existing:
        resolved = resolve_workspace(
            project_root,
            overrides=CliOverrides(token=existing, api_url=api_url, project_id=project_id),
        )
        if resolved is not None and workspace_state(resolved) == WorkspaceState.READY:
            return existing, "reused"

    session = load_session()
    if session is None:
        env_token = (os.environ.get("HYDRACEPT_API_KEY") or os.environ.get("HYDRACEPT_TOKEN") or "").strip()
        if env_token:
            login_with_token(project_root, env_token, console=None)
            return env_token, "reused"

    if session is not None:
        created = create_key(
            name="CLI workstation",
            project_id=project_id,
            environment=environment,
        )
        api_key = str(created.get("apiKey") or "").strip()
        if not api_key:
            raise SessionClientError("keys create returned empty apiKey", status_code=USAGE)
        write_secrets(project_root, {"apiKey": api_key, "kind": "api_key", "schemaVersion": 2})
        ensure_gitignore(project_root)
        return api_key, "created"

    raise SessionClientError("authentication required", status_code=401)


def _resolve_project_binding(project_root: Path) -> dict[str, Any]:
    binding = load_project_binding(project_root)
    if binding.get("projectId"):
        return binding

    session = load_session()
    if session is not None:
        try:
            context = fetch_session_context()
        except SessionClientError:
            context = {}
        project_id = project_from_session_context(context)
        if project_id:
            binding = {
                "projectId": project_id,
                "environment": environment_from_session_context(context),
                "capabilityProfile": capability_profile(binding),
            }
            if isinstance(context.get("project"), dict):
                name = context["project"].get("displayName")
                if name:
                    binding["projectName"] = name
            write_project_binding(project_root, binding)
            return binding
    return binding


def _missing_providers(readiness: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    providers = readiness.get("providers") or {}
    if not isinstance(providers, dict):
        return missing
    for provider, state in providers.items():
        if isinstance(state, dict) and state.get("status") == "unbound":
            missing.append(str(provider))
    return missing


def _ensure_binding_suggested_name(
    project_root: Path,
    binding: dict[str, Any],
    *,
    project_name: str | None = None,
) -> dict[str, Any]:
    suggested = resolve_suggested_project_name(project_root, binding, override=project_name)
    updated = {**binding, "projectName": suggested}
    if not str(updated.get("projectId") or "").strip():
        write_project_binding(project_root, updated)
    return updated


def run_init(
    project_root: Path,
    *,
    api_url: str | None = None,
    apply: bool = False,
    yes: bool = False,
    json_output: bool = False,
    ci_mode: bool = False,
    env_file: Path | None = None,
    setup_grant: str | None = None,
    wait: bool = False,
    poll_seconds: int = 900,
    project_name: str | None = None,
) -> InitResult:
    if not apply:
        return InitResult(
            exit_code=USAGE,
            payload={
                **_base_payload("interaction_required"),
                "reason": "apply_required",
                "detail": "Pass --apply to mutate workspace",
            },
        )

    api = (api_url or os.environ.get("HYDRACEPT_API_URL") or "https://api.hydracept.com").rstrip("/")
    binding = _ensure_binding_suggested_name(
        project_root,
        _resolve_project_binding(project_root),
        project_name=project_name,
    )
    profile = capability_profile(binding)

    if ci_mode:
        token = (os.environ.get("HYDRACEPT_API_KEY") or "").strip()
        if not token:
            return _configuration_required("missing_api_key")
        readiness = _fetch_readiness(api, token, profile)
        missing = _missing_providers(readiness)
        if missing:
            return _configuration_required("provider_connection_missing", provider=missing[0])
        pack_installed, pack_error = try_install_agent_pack(project_root)
        report = build_doctor_report(api, project_root, token, smoke_capability=profile[0])
        doctor_code = doctor_exit_code(report)
        payload = _base_payload("ready" if doctor_code == SUCCESS and pack_installed else "configuration_required")
        payload.update(agent_pack_init_fields(pack_installed, pack_error, doctor_ok=doctor_code == SUCCESS))
        payload["account"] = {"authenticated": True}
        payload["project"] = {"id": binding.get("projectId", ""), "action": "reused"}
        payload["installation"] = {"configured": True, "action": "reused"}
        payload["providers"] = _providers_section(readiness)
        payload["capabilities"] = _capabilities_section(readiness)
        payload["doctor"] = doctor_init_fields(report, doctor_code)
        _attach_mcp(project_root, payload)
        return InitResult(
            exit_code=SUCCESS if payload.get("ready") else DOCTOR_FAILED,
            payload=payload,
        )

    # Auth + installation
    install_action = "reused"
    try:
        project_id = str(binding.get("projectId") or "").strip()
        environment = str(binding.get("environment") or "development").strip() or "development"
        api_key = ""

        if not project_id:
            if load_session() is None and not (os.environ.get("HYDRACEPT_API_KEY") or "").strip():
                browser_outcome = _bootstrap_interaction(
                    "authentication",
                    project_root,
                    api,
                    binding,
                    wait=wait,
                    poll_seconds=poll_seconds,
                    json_output=json_output,
                )
                if isinstance(browser_outcome, _BrowserBootstrapResult):
                    api_key = browser_outcome.api_key
                    project_id = browser_outcome.project_id
                    environment = browser_outcome.environment
                    binding = browser_outcome.binding
                    setup_grant = setup_grant or browser_outcome.setup_grant
                    install_action = "created"
                else:
                    return browser_outcome
            binding = _resolve_project_binding(project_root)
            project_id = str(binding.get("projectId") or "").strip()
            if not project_id:
                browser_outcome = _bootstrap_interaction(
                    "project_selection",
                    project_root,
                    api,
                    binding,
                    wait=wait,
                    poll_seconds=poll_seconds,
                    json_output=json_output,
                )
                if isinstance(browser_outcome, _BrowserBootstrapResult):
                    api_key = browser_outcome.api_key
                    project_id = browser_outcome.project_id
                    environment = browser_outcome.environment
                    binding = browser_outcome.binding
                    setup_grant = setup_grant or browser_outcome.setup_grant
                    install_action = "created"
                else:
                    return browser_outcome

        if not api_key:
            api_key, install_action = _ensure_installation_credential(
                project_root,
                project_id=project_id,
                environment=environment,
                api_url=api,
            )
    except SessionClientError:
        browser_outcome = _bootstrap_interaction(
            "authentication",
            project_root,
            api,
            binding,
            wait=wait,
            poll_seconds=poll_seconds,
            json_output=json_output,
        )
        if isinstance(browser_outcome, _BrowserBootstrapResult):
            api_key = browser_outcome.api_key
            project_id = browser_outcome.project_id
            environment = browser_outcome.environment
            binding = browser_outcome.binding
            setup_grant = setup_grant or browser_outcome.setup_grant
            install_action = "created"
        else:
            return browser_outcome
    except LoginError as exc:
        return InitResult(exit_code=exc.exit_code, payload={**_base_payload("interaction_required"), "detail": str(exc)})

    profile = capability_profile(binding)
    project_id = str(binding.get("projectId") or project_id).strip()
    environment = str(binding.get("environment") or environment).strip() or "development"

    try:
        run_configure(project_root, api_url=api, token=api_key)
    except ConfigureError as exc:
        return InitResult(
            exit_code=exc.exit_code,
            payload={**_base_payload("configuration_required"), "detail": str(exc)},
        )

    write_project_binding(project_root, binding)
    readiness = _fetch_readiness(api, api_key, profile)
    adopt_results: list[dict[str, Any]] = []

    if not ci_mode:
        missing = _missing_providers(readiness)
        if missing and (load_session() is not None or setup_grant):
            for provider in missing:
                discovered = None
                from hydracept.cli.provider_discovery import discover_provider

                discovered = discover_provider(provider, project_root, extra_env_file=env_file)
                if discovered is None:
                    continue
                try:
                    outcome = adopt_provider_secret(
                        provider=provider,
                        secret=discovered.secret,
                        project_id=project_id,
                        environment=environment,
                        setup_grant=setup_grant,
                    )
                    adopt_results.append(
                        {
                            "provider": provider,
                            "source": discovered.source,
                            "result": outcome.get("result", "connected"),
                        }
                    )
                except SessionClientError as exc:
                    if exc.status_code == 409:
                        return _bootstrap_interaction(
                            "provider_connection_conflict",
                            project_root,
                            api,
                            binding,
                            wait=wait,
                            poll_seconds=poll_seconds,
                            json_output=json_output,
                        )
            if missing and not adopt_results and load_session() is None and not setup_grant:
                pass
        elif missing and load_session() is not None:
            try:
                adopt_results = adopt_from_env(
                    project_root,
                    providers=missing,
                    env_file=env_file,
                    setup_grant=setup_grant,
                )
            except SessionClientError as exc:
                if exc.status_code == 409:
                    return _bootstrap_interaction(
                        "provider_connection_conflict",
                        project_root,
                        api,
                        binding,
                        wait=wait,
                        poll_seconds=poll_seconds,
                        json_output=json_output,
                    )

        readiness = _fetch_readiness(api, api_key, profile)

    smoke_cap = profile[0] if profile else DEFAULT_SMOKE_CAPABILITY
    pack_installed, pack_error = try_install_agent_pack(project_root)

    report = build_doctor_report(api, project_root, api_key, smoke_capability=smoke_cap)
    doctor_code = doctor_exit_code(report)
    payload = _base_payload("ready" if doctor_code == SUCCESS and pack_installed else "configuration_required")
    payload.update(agent_pack_init_fields(pack_installed, pack_error, doctor_ok=doctor_code == SUCCESS))
    payload["account"] = {"authenticated": load_session() is not None or bool(api_key)}
    payload["project"] = {
        "id": project_id,
        "name": str(binding.get("projectName") or ""),
        "action": "reused" if binding else "created",
    }
    payload["installation"] = {"configured": True, "action": install_action}
    payload["providers"] = _providers_section(readiness, adopt_results)
    payload["capabilities"] = _capabilities_section(readiness)
    payload["doctor"] = doctor_init_fields(report, doctor_code)
    _attach_mcp(project_root, payload)
    # Secret safety: never include api key or provider secrets
    if json_output:
        text = json.dumps(payload)
        for forbidden in ("sk-", "apiKey", "secret"):
            if forbidden in text:
                raise RuntimeError("init JSON leaked forbidden field")

    exit_code = SUCCESS if payload.get("ready") else DOCTOR_FAILED
    return InitResult(exit_code=exit_code, payload=payload)


def unified_bootstrap_enabled() -> bool:
    return os.environ.get("HYDRACEPT_UNIFIED_BOOTSTRAP", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }
