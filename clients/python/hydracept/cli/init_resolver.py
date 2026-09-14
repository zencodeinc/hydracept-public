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
from hydracept.cli.installed_workspace import (
    InstalledWorkspaceStatus,
    validate_installed_workspace,
)
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
    fetch_session_context,
    organization_id_from_session_context,
)
from hydracept.cli.session_store import DEFAULT_APP_BASE_URL, clear_session, load_session
from hydracept.cli.workspace import (
    CliOverrides,
    WorkspaceState,
    auth_headers,
    read_json,
    resolve_workspace,
    secrets_path,
    workspace_state,
)
from hydracept.cli.workspace_fingerprint import workspace_fingerprint
from hydracept.mcp.presentation import presentation_for_host

INIT_SCHEMA_VERSION = "hydracept.cli.init.v1"
INTERACTION_SCHEMA_VERSION = "hydracept.interaction.v1"
PROJECT_CONNECT_SURFACE = "project.connect"
MCP_APP_URI = "ui://hydracept/app.html"
INTERACTION_TOOL = "hydracept_interaction_surface"
InitStatus = Literal["ready", "interaction_required", "configuration_required"]
CANONICAL_INIT_COMMAND = "python -m hydracept init --apply --yes --json --wait"
VERBATIM_URL_INSTRUCTION = (
    "Use action.url verbatim. Do not construct, shorten, or replace this URL."
)
_REASON_STAGES = {
    "authentication": "authentication",
    "apply_required": "local_binding",
    "project_selection": "project_resolution",
    "bootstrap_wait_timeout": "local_binding",
    "missing_api_key": "authentication",
    "credential_invalid": "authentication",
    "provider_connection_missing": "provider_readiness",
    "multiple_organizations": "organization_resolution",
    "multiple_matching_projects": "project_resolution",
    "workspace_identity_unknown": "project_resolution",
}


def _stage_for_reason(reason: str) -> str:
    return _REASON_STAGES.get(reason, reason or "unknown")


def _bootstrap_progress(
    reason: str,
    local_identity_candidates: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Make bootstrap stages readable without inferring from interaction_required."""
    stage = _stage_for_reason(reason)
    identity: dict[str, Any] = {"status": "pending"}
    if local_identity_candidates:
        first = local_identity_candidates[0]
        account = first.get("account") or first.get("login") or first.get("username")
        identity = {
            "status": "ready" if len(local_identity_candidates) == 1 else "ambiguous",
            "provider": str(first.get("provider") or "github"),
        }
        if account:
            identity["account"] = account
    elif stage == "authentication":
        identity = {"status": "pending"}
    elif stage in {"local_binding", "unknown"}:
        identity = {"status": "pending"}
    else:
        identity = {"status": "ready"}
    project_status = "pending"
    if stage in {"provider_readiness", "mcp_installation", "agent_pack_installation"}:
        project_status = "ready"
    if stage == "organization_resolution":
        organization_status = "pending"
    elif stage == "authentication":
        organization_status = "pending"
    else:
        organization_status = "ready"
    return {
        "identity": identity,
        "organization": {"status": organization_status},
        "project": {"status": project_status},
    }


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
    expires_at: str | None = None,
    wait_available: bool = True,
    exit_code: int = SUCCESS,
    detail: str | None = None,
    local_identity_candidates: list[dict[str, str]] | None = None,
    local_identity: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    project_name: str | None = None,
    environment: str | None = None,
    workspace_fp: str | None = None,
) -> InitResult:
    """Return the stable machine contract for a human-blocking bootstrap step.

    Existing fields are retained for older agents. New fields make the interaction
    self-contained so a weaker agent does not need to infer a URL, workflow, or
    recovery command.
    """
    payload = _base_payload("interaction_required")
    activation_detail = detail or (
        "A human must open the connect URL and approve this workspace "
        "before the agent can continue."
    )
    has_activation_url = bool(url)
    if has_activation_url:
        agent_instruction = (
            "Stop automation now. If hydracept_interaction_surface is available in this "
            "session, invoke it once with surface project.connect and the supplied "
            "interaction.context. Do not ask the human to name the project when "
            "interaction.context.displayName is already set — the panel opens the "
            "connect URL and completes with that name. When presentation.agentAction is "
            "present_and_yield, present that surface, make it the final tool call of this "
            "turn, and perform no subsequent unrelated tool calls or prose. Otherwise "
            "present action.url verbatim and stop. Do not start --wait or run doctor, "
            "consumer-check, status, or other diagnostics before the human confirms "
            "activation. After confirmation "
            f"run {CANONICAL_INIT_COMMAND}."
        )
        recommended_action = "present_project_connect"
    else:
        agent_instruction = activation_detail
        recommended_action = "retry_init"

    payload.update(
        {
            "type": "interaction_required",
            "kind": "activation",
            "blocking": True,
            "code": reason,
            "reason": reason,
            "stage": _stage_for_reason(reason),
            "detail": activation_detail,
            "instruction": VERBATIM_URL_INSTRUCTION if has_activation_url else activation_detail,
            "agentInstruction": agent_instruction,
            "recommendedAction": recommended_action,
            "expiresAt": expires_at,
            "afterCompletion": {
                "kind": "run_command",
                "command": CANONICAL_INIT_COMMAND,
            },
        }
    )
    action: dict[str, Any] = {
        "type": "open_url",
        "kind": "open_url",
        "label": "Activate workspace",
        "url": url,
        "instruction": "Use this URL verbatim. Do not construct, shorten, or replace it.",
    }
    if bootstrap_session_id:
        action["sessionId"] = bootstrap_session_id
    if wait_available:
        action["waitCommand"] = "python -m hydracept init --apply --yes --wait"
        action["waitCommandJson"] = CANONICAL_INIT_COMMAND
    payload["action"] = action
    payload.update(_bootstrap_progress(reason, local_identity_candidates))
    if bootstrap_session_id:
        payload["bootstrapSessionId"] = bootstrap_session_id
    payload["bootstrapSession"] = {
        "sessionId": bootstrap_session_id or "",
        "activationUrl": url,
        "expiresAt": expires_at,
    }
    if local_identity_candidates:
        payload["localIdentityCandidates"] = local_identity_candidates
    if local_identity:
        payload["localIdentity"] = local_identity
    if has_activation_url:
        payload["agentControl"] = {
            "mustStop": True,
            "resumeAfter": "human_activation_complete",
            "doNotPollBeforeResume": True,
        }
        interaction_context = {
            "status": "interaction_required",
            "actionUrl": url,
            "bootstrapSessionId": bootstrap_session_id or "",
            "expiresAt": expires_at,
        }
        suggested = (project_name or "").strip()
        env = (environment or "").strip()
        if workspace_fp:
            interaction_context["fingerprint"] = workspace_fp
            interaction_context["workspace"] = {"fingerprint": workspace_fp}
        if suggested:
            interaction_context["displayName"] = suggested
            interaction_context["suggestedName"] = suggested
        if env:
            interaction_context["environment"] = env
        payload["interaction"] = {
            "schemaVersion": INTERACTION_SCHEMA_VERSION,
            "surface": PROJECT_CONNECT_SURFACE,
            "tool": INTERACTION_TOOL,
            "appUri": MCP_APP_URI,
            "preferredWhenAvailable": True,
            "context": interaction_context,
        }
        payload["presentation"] = presentation_for_host(
            PROJECT_CONNECT_SURFACE,
            apps_supported=True,
            confirmation_required=False,
            status="mount_requested",
            context=interaction_context,
        )
    if extra:
        payload.update(extra)
    return InitResult(exit_code=exit_code, payload=payload)


def _configuration_required(reason: str, **extra: Any) -> InitResult:
    payload = _base_payload("configuration_required")
    payload["reason"] = reason
    payload["code"] = reason
    payload["stage"] = _stage_for_reason(reason)
    payload.update(_bootstrap_progress(reason))
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
    """Return the server-issued session id, exact activation URL, and expiry."""
    from hydracept.cli.machine import machine_fingerprint

    suggested_name = resolve_suggested_project_name(project_root, binding)
    response = httpx.post(
        f"{api_url.rstrip('/')}/v1/bootstrap/sessions",
        json={
            "repoPath": str(project_root.resolve()),
            "machineFingerprint": machine_fingerprint(),
            "workspaceFingerprint": workspace_fingerprint(project_root, binding),
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
    connect_url = str(body.get("connectUrl") or body.get("activationUrl") or "").strip()
    expires_at = str(body.get("expiresAt") or "").strip() or None
    if not connect_url:
        raise httpx.HTTPError("bootstrap session missing connectUrl/activationUrl")
    return session_id, connect_url, expires_at


def _stored_expiry(stored: dict[str, Any]) -> str | None:
    return str(stored.get("expiresAt") or "").strip() or None


def _remote_expiry(remote: dict[str, Any], fallback: str | None) -> str | None:
    return str(remote.get("expiresAt") or "").strip() or fallback


def _resolve_bootstrap_session(
    project_root: Path,
    api_url: str,
    *,
    binding: dict[str, Any],
) -> tuple[str, str, str | None]:
    """Reuse a valid pending session; never make the agent reconstruct its URL."""
    api = api_url.rstrip("/")
    stored = load_bootstrap_session(project_root)
    if stored and stored_bootstrap_session_matches_api(stored, api):
        session_id = str(stored.get("sessionId") or "").strip()
        connect_url = str(stored.get("connectUrl") or stored.get("activationUrl") or "").strip()
        expires_at = _stored_expiry(stored)
        if session_id and connect_url and not bootstrap_session_expired(stored):
            remote = _fetch_bootstrap_session(api, session_id)
            if remote is not None:
                status = str(remote.get("status") or "")
                if status in {"pending", "approved"}:
                    remote_url = str(remote.get("connectUrl") or remote.get("activationUrl") or "").strip()
                    return session_id, remote_url or connect_url, _remote_expiry(remote, expires_at)
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
        return session_id, connect_url, expires_at
    except httpx.HTTPError:
        # Compatibility fallback for older/unavailable bootstrap APIs. This is a
        # real app URL, not a guessed /connect/{id} route.
        return "", _device_verification_url(), None


def _create_bootstrap_session(
    project_root: Path,
    api_url: str,
    *,
    binding: dict[str, Any],
) -> tuple[str, str, str | None]:
    if unified_bootstrap_enabled():
        return _resolve_bootstrap_session(project_root, api_url, binding=binding)
    return "", _device_verification_url(), None


def _emit_wait_progress(
    *,
    json_output: bool,
    session_id: str,
    connect_url: str,
    seconds_remaining: int,
) -> None:
    """Keep --wait observable without contaminating JSON stdout."""
    if json_output:
        print(
            json.dumps(
                {
                    "status": "waiting",
                    "reason": "browser_setup",
                    "code": "browser_setup",
                    "bootstrapSessionId": session_id,
                    "secondsRemaining": seconds_remaining,
                    "instruction": VERBATIM_URL_INSTRUCTION,
                    "detail": "Open action.url; this command continues polling the same session.",
                    "action": {"type": "open_url", "url": connect_url},
                }
            ),
            file=sys.stderr,
            flush=True,
        )
        return
    print(f"Waiting for browser setup… {connect_url} ({seconds_remaining}s left)", flush=True)


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


def _discard_expired_session() -> None:
    """Drop a leftover session file the server no longer accepts.

    A stale ~/.hydracept/session.json looks like a live login to init, which
    skips gh/gcloud identity and forces a browser connect URL.
    """
    if load_session() is None:
        return
    try:
        fetch_session_context()
    except SessionClientError as exc:
        if exc.status_code == 401:
            clear_session()


def _try_local_identity_bootstrap(
    project_root: Path,
    api_url: str,
    binding: dict[str, Any],
    *,
    session_id: str,
    requested_provider: str | None = None,
) -> tuple[_BrowserBootstrapResult | None, list[dict[str, str]], dict[str, Any]]:
    """Try one unambiguous local identity without exposing its proof to callers."""
    from hydracept.cli.identity import (
        assert_local_identity,
        complete_bootstrap_with_session,
        detect_local_identities,
        issue_local_identity_proof,
        ordered_local_identity_hints,
    )

    local_identity_state: dict[str, Any] = {"attempted": False}
    try:
        hints = detect_local_identities()
    except Exception:  # noqa: BLE001
        return None, [], {
            "attempted": True,
            "outcome": "fallback_required",
            "reason": "provider_unavailable",
        }
    candidates = [hint.to_public_dict() for hint in hints]
    selected_hints = ordered_local_identity_hints(hints, requested_provider)
    if not selected_hints:
        return None, candidates, {
            "attempted": bool(candidates),
            "outcome": "fallback_required",
            "reason": "proof_unavailable",
        }

    for selected in selected_hints:
        local_identity_state = {
            "attempted": True,
            "provider": str(selected.provider or ""),
            "account": str(selected.account or selected.login or ""),
        }
        try:
            proof = issue_local_identity_proof(selected)
            try:
                asserted = assert_local_identity(
                    hint=selected,
                    proof=proof,
                    bootstrap_session_id=session_id,
                )
            except Exception:  # noqa: BLE001
                local_identity_state.update(
                    {"outcome": "fallback_required", "reason": "proof_rejected"}
                )
                continue
            finally:
                del proof
            project_id = str(asserted.get("projectId") or "").strip()
            if not project_id:
                # Identity is bound to this bootstrap session. Do not try a second
                # local provider; browser project selection must use the same
                # principal.
                local_identity_state.update(
                    {"outcome": "fallback_required", "reason": "project_selection_required"}
                )
                return None, candidates, local_identity_state
            environment = str(
                asserted.get("environment") or binding.get("environment") or "development"
            ).strip() or "development"
            try:
                complete_bootstrap_with_session(
                    api_url=api_url,
                    bootstrap_session_id=session_id,
                    project_id=project_id,
                    environment=environment,
                )
            except Exception:  # noqa: BLE001
                local_identity_state.update(
                    {"outcome": "fallback_required", "reason": "identity_transport_failed"}
                )
                continue
            approved = _fetch_bootstrap_session(api_url, session_id)
            if not approved or str(approved.get("status") or "") != "approved":
                local_identity_state.update(
                    {"outcome": "fallback_required", "reason": "identity_transport_failed"}
                )
                continue
            applied = _apply_browser_bootstrap(
                project_root,
                approved,
                prior_binding=binding,
            )
            if applied is None:
                local_identity_state.update(
                    {"outcome": "fallback_required", "reason": "identity_not_linked"}
                )
                continue
            local_identity_state.update({"outcome": "succeeded"})
            return applied, candidates, local_identity_state
        except Exception:  # noqa: BLE001
            local_identity_state.update(
                {"outcome": "fallback_required", "reason": "identity_transport_failed"}
            )
            continue
    local_identity_state.setdefault("outcome", "fallback_required")
    local_identity_state.setdefault("reason", "provider_unavailable")
    return None, candidates, local_identity_state


def _bootstrap_interaction(
    reason: str,
    project_root: Path,
    api_url: str,
    binding: dict[str, Any],
    *,
    wait: bool,
    poll_seconds: int,
    json_output: bool = False,
    identity_provider: str | None = None,
    extra: dict[str, Any] | None = None,
) -> InitResult | _BrowserBootstrapResult:
    session_id, connect_url, expires_at = _create_bootstrap_session(
        project_root, api_url, binding=binding
    )
    local_candidates: list[dict[str, str]] = []
    local_identity_state: dict[str, Any] = {"attempted": False}
    workspace_fp = workspace_fingerprint(project_root, binding)
    if reason == "authentication":
        _discard_expired_session()
    if (
        reason == "authentication"
        and session_id
        and unified_bootstrap_enabled()
        and load_session() is None
    ):
        local_applied, local_candidates, local_identity_state = _try_local_identity_bootstrap(
            project_root,
            api_url,
            binding,
            session_id=session_id,
            requested_provider=identity_provider,
        )
        if local_applied is not None:
            return local_applied

    project_name = str(binding.get("projectName") or "").strip() or None
    environment = str(binding.get("environment") or "").strip() or None
    if session_id and unified_bootstrap_enabled():
        remote = _fetch_bootstrap_session(api_url, session_id)
        approved = remote if remote and str(remote.get("status") or "") == "approved" else None
        if approved is None and wait:
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
        if wait:
            # Timeout deliberately retains the same session and exact URL. A retry can
            # continue instead of forcing a weaker agent to restart activation.
            return _interaction(
                "bootstrap_wait_timeout",
                connect_url,
                bootstrap_session_id=session_id,
                expires_at=expires_at,
                exit_code=AUTH,
                detail="Browser setup did not complete within the poll window; the activation session is still recoverable until expiresAt.",
                local_identity_candidates=local_candidates,
                local_identity=local_identity_state,
                extra=extra,
                project_name=project_name,
                environment=environment,
                workspace_fp=workspace_fp,
            )
    return _interaction(
        reason,
        connect_url,
        bootstrap_session_id=session_id or None,
        expires_at=expires_at,
        local_identity_candidates=local_candidates,
        local_identity=local_identity_state,
        extra=extra,
        project_name=project_name,
        environment=environment,
        workspace_fp=workspace_fp,
    )


def _interaction_url(project_root: Path, api_url: str, binding: dict[str, Any]) -> str:
    if unified_bootstrap_enabled():
        _, connect_url, _ = _create_bootstrap_session(project_root, api_url, binding=binding)
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


def _fetch_readiness(api_url: str, token: str, capabilities: list[str]) -> dict[str, Any]:
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


def agent_pack_init_fields(pack_installed: bool, pack_error: str, *, doctor_ok: bool) -> dict[str, Any]:
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
    payload = report.to_json_dict() if hasattr(report, "to_json_dict") else {}
    checks = list(getattr(report, "checks", None) or [])
    failed = list(payload.get("failedChecks") or [])
    warnings = list(payload.get("warnings") or [])
    if not failed:
        failed = [
            {"name": check.name, "detail": check.detail, "nextAction": check.next_action}
            for check in checks
            if not check.passed and check.fatal
        ]
    if not warnings:
        warnings = [
            {"name": check.name, "detail": check.detail}
            for check in checks
            if not check.passed and not check.fatal
        ]
    return {
        "status": "passed" if doctor_code == SUCCESS else "failed",
        "failedChecks": failed,
        "warnings": warnings,
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
    allow_reuse: bool = True,
) -> tuple[str, str]:
    secrets = read_json(secrets_path(project_root))
    existing = str(secrets.get("apiKey") or secrets.get("token") or "").strip()
    if allow_reuse and existing:
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
        created = create_key(name="CLI workstation", project_id=project_id, environment=environment)
        api_key = str(created.get("apiKey") or "").strip()
        if not api_key:
            raise SessionClientError("keys create returned empty apiKey", status_code=USAGE)
        write_secrets(project_root, {"apiKey": api_key, "kind": "api_key", "schemaVersion": 2})
        ensure_gitignore(project_root)
        return api_key, "created"

    raise SessionClientError("authentication required", status_code=401)


def _credential_project_id_from_token(api_url: str, token: str) -> str:
    """Project the API key is issued for. Empty when it cannot be observed."""
    try:
        response = httpx.get(
            f"{api_url.rstrip('/')}/v1/diagnostics/session",
            headers=auth_headers(token),
            timeout=20.0,
        )
    except httpx.HTTPError:
        return ""
    if response.status_code != 200:
        return ""
    try:
        body = response.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    return str(body.get("tokenProjectId") or body.get("projectId") or "").strip()


def _align_checkout_to_api_key(
    project_root: Path,
    api_url: str,
    binding: dict[str, Any],
    token: str,
) -> tuple[dict[str, Any], str] | None:
    """Bind an empty or mismatched checkout to the project the supplied API key belongs to."""
    cred = _credential_project_id_from_token(api_url, token)
    if not cred:
        return None
    bound = {
        **binding,
        "projectId": cred,
        "resolution": "credential_project",
        "apiOrigin": api_url.rstrip("/"),
    }
    write_project_binding(project_root, bound)
    write_secrets(project_root, {"apiKey": token, "kind": "api_key", "schemaVersion": 2})
    ensure_gitignore(project_root)
    return bound, cred


def _resolve_project_binding(project_root: Path) -> dict[str, Any]:
    return load_project_binding(project_root)


def _missing_providers(readiness: dict[str, Any]) -> list[str]:
    providers = readiness.get("providers") or {}
    if not isinstance(providers, dict):
        return []
    return [
        str(provider)
        for provider, state in providers.items()
        if isinstance(state, dict) and state.get("status") == "unbound"
    ]


def _identity_payload(
    context: dict[str, Any] | None,
    *,
    authenticated: bool,
) -> dict[str, Any]:
    from hydracept.cli.local_project_context import github_cli_login
    from hydracept.cli.session_client import identity_from_session_context

    identity = identity_from_session_context(context)
    if authenticated:
        identity["authenticated"] = True
    login = github_cli_login()
    if login:
        identity["provider"] = identity.get("provider") or "github"
        identity["account"] = identity.get("account") or login
        identity["githubCliReuse"] = True
        identity["method"] = identity.get("method") or "github_cli"
        identity["note"] = (
            "Init reused the authenticated GitHub CLI session; a browser login was not required."
        )
    if not identity.get("authenticated"):
        identity["authenticated"] = bool(authenticated)
    return identity


def _project_selection_detail(identity: dict[str, Any], resolution: dict[str, Any]) -> str:
    account = str(identity.get("account") or "").strip()
    provider = str(identity.get("provider") or "GitHub").strip() or "GitHub"
    prefix = ""
    if identity.get("authenticated") and account:
        prefix = f"Authenticated with {provider} as {account}. "
    reason = str(resolution.get("reason") or "")
    if reason == "multiple_matching_projects":
        return (
            prefix
            + "Hydracept could not uniquely determine which existing project this workspace belongs to."
        )
    if reason == "multiple_organizations":
        return prefix + "Hydracept could not determine which organization should own this project."
    if reason == "inaccessible_project":
        return prefix + "The bound project is not accessible with the current identity."
    if reason == "corrupt_local_binding":
        return prefix + "The local project binding file is unreadable. Repair or replace .hydracept/project.json before Hydracept creates a new project."
    if reason == "workspace_identity_unknown":
        return prefix + "Hydracept could not determine the current workspace identity."
    return prefix + "Hydracept could not uniquely determine which project this workspace belongs to."


def _binding_from_resolution(
    resolution: Any,
    prior: dict[str, Any],
    context: Any,
) -> dict[str, Any]:
    binding = {
        **prior,
        "projectId": resolution.project_id,
        "environment": resolution.environment or "development",
        "capabilityProfile": capability_profile(prior),
        "projectName": resolution.display_name or context.inferred_name,
        "resolution": resolution.resolution,
    }
    repository = context.repository_payload()
    if repository:
        binding["repository"] = repository
    return binding


def _resolve_authenticated_project(
    project_root: Path,
    *,
    explicit_project: str | None = None,
    explicit_environment: str | None = None,
    preferred_organization_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (binding, resolution_dict) using local context + Hydracept catalog."""
    from hydracept.cli.local_project_context import resolve_local_project_context
    from hydracept.cli.project_resolution import (
        ProjectResolution,
        apply_automatic_project,
        find_explicit_project,
        load_accessible_catalog,
    )

    context = resolve_local_project_context(project_root)
    binding = load_project_binding(project_root)
    environment = (
        str(explicit_environment or binding.get("environment") or "development").strip()
        or "development"
    )
    organizations, projects = load_accessible_catalog()

    if explicit_project:
        resolution = find_explicit_project(explicit_project, projects)
        resolution.environment = environment
        if resolution.state == "resolved" and resolution.project_id:
            bound = _binding_from_resolution(resolution, binding, context)
            write_project_binding(project_root, bound)
            return bound, resolution.as_dict()
        return binding, resolution.as_dict()

    existing_id = str(binding.get("projectId") or "").strip()
    if binding.get("corruptLocalBinding") and not existing_id:
        return binding, ProjectResolution(
            state="ambiguous",
            reason="corrupt_local_binding",
            environment=environment,
        ).as_dict()
    if existing_id:
        accessible = {item.id for item in projects}
        # Empty catalog is indistinguishable from a fetch failure — keep the
        # local binding. Invalidate only when the catalog loaded other projects.
        if projects and existing_id not in accessible:
            return binding, ProjectResolution(
                state="ambiguous",
                reason="inaccessible_project",
                environment=environment,
                candidates=[{"id": existing_id, "match": "existing_binding"}],
            ).as_dict()
        bound = {
            **binding,
            "environment": environment,
            "resolution": binding.get("resolution") or "existing_binding",
        }
        write_project_binding(project_root, bound)
        return bound, {
            "state": "resolved",
            "resolution": "existing_binding",
            "projectId": existing_id,
            "displayName": str(binding.get("projectName") or ""),
            "environment": environment,
            "created": False,
        }

    applied = apply_automatic_project(
        context,
        organizations=organizations,
        projects=projects,
        environment=environment,
        preferred_organization_id=preferred_organization_id,
    )
    if applied.state == "resolved" and applied.project_id:
        bound = _binding_from_resolution(applied, binding, context)
        write_project_binding(project_root, bound)
        return bound, applied.as_dict()
    return binding, applied.as_dict()


def _ensure_binding_suggested_name(
    project_root: Path,
    binding: dict[str, Any],
    *,
    project_name: str | None = None,
    environment: str | None = None,
) -> dict[str, Any]:
    suggested = resolve_suggested_project_name(project_root, binding, override=project_name)
    updated = {**binding, "projectName": suggested}
    env = str(environment or "").strip()
    if env:
        updated["environment"] = env
    if binding.get("corruptLocalBinding"):
        return updated
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
    environment: str | None = None,
    identity_provider: str | None = None,
    explicit_project: str | None = None,
    explicit_environment: str | None = None,
) -> InitResult:
    if not apply:
        return _interaction(
            "apply_required",
            "",
            wait_available=False,
            exit_code=USAGE,
            detail="Pass --apply to mutate workspace.",
        )

    api = (api_url or os.environ.get("HYDRACEPT_API_URL") or "https://api.hydracept.com").rstrip("/")
    binding = _ensure_binding_suggested_name(
        project_root,
        _resolve_project_binding(project_root),
        project_name=project_name,
        environment=environment,
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
        smoke_cap = profile[0] if profile else DEFAULT_SMOKE_CAPABILITY
        report = build_doctor_report(api, project_root, token, smoke_capability=smoke_cap)
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
        return InitResult(exit_code=SUCCESS if payload.get("ready") else DOCTOR_FAILED, payload=payload)

    installed = validate_installed_workspace(project_root)
    if installed.status == InstalledWorkspaceStatus.INVALID_LOCAL_BINDING:
        return _configuration_required(
            "corrupt_local_binding",
            detail=installed.detail or "The local project binding file is unreadable.",
        )
    if installed.status == InstalledWorkspaceStatus.PROJECT_CREDENTIAL_MISMATCH:
        env_token = (
            os.environ.get("HYDRACEPT_API_KEY") or os.environ.get("HYDRACEPT_TOKEN") or ""
        ).strip()
        if env_token:
            aligned = _align_checkout_to_api_key(project_root, api, binding, env_token)
            if aligned is not None:
                binding, _project_id = aligned
                installed = validate_installed_workspace(project_root)
        if installed.status == InstalledWorkspaceStatus.PROJECT_CREDENTIAL_MISMATCH:
            return _configuration_required(
                "project_credential_mismatch",
                detail=installed.detail,
                context=installed.context,
                retryable=True,
            )
    if installed.status == InstalledWorkspaceStatus.VALIDATION_UNAVAILABLE:
        return _configuration_required(
            "validation_unavailable",
            detail=installed.detail or "Remote credential validation is unavailable.",
            retryable=True,
        )
    credential_invalid = installed.status == InstalledWorkspaceStatus.CREDENTIAL_INVALID

    _discard_expired_session()
    install_action = "reused"
    identity: dict[str, Any] = {"authenticated": False, "provider": None, "account": None}
    project_resolution: dict[str, Any] = {"state": "unavailable"}
    requested_env = str(explicit_environment or environment or "").strip()
    try:
        project_id = str(binding.get("projectId") or "").strip()
        environment = str(requested_env or binding.get("environment") or "development").strip() or "development"
        api_key = ""
        installed_ready = installed.status == InstalledWorkspaceStatus.INSTALLED_VALID

        if installed_ready:
            api_key = str(installed.token or "").strip()
            project_id = str(installed.project_id or project_id).strip()
            environment = str(installed.environment or environment).strip() or "development"
            install_action = "reused"
            project_resolution = {
                "state": "resolved",
                "resolution": "existing_binding",
                "projectId": project_id,
                "displayName": str(binding.get("projectName") or ""),
                "environment": environment,
                "created": False,
            }
            identity = _identity_payload(None, authenticated=True)
        elif load_session() is None and not (os.environ.get("HYDRACEPT_API_KEY") or "").strip():
            browser_outcome = _bootstrap_interaction(
                "authentication",
                project_root,
                api,
                binding,
                wait=wait,
                poll_seconds=poll_seconds,
                json_output=json_output,
                identity_provider=identity_provider,
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

        env_token = (
            os.environ.get("HYDRACEPT_API_KEY") or os.environ.get("HYDRACEPT_TOKEN") or ""
        ).strip()
        aligned_to_key = False
        if not installed_ready and env_token:
            aligned = _align_checkout_to_api_key(project_root, api, binding, env_token)
            if aligned is not None:
                binding, project_id = aligned
                api_key = env_token
                aligned_to_key = True
                install_action = "reused"
                project_resolution = {
                    "state": "resolved",
                    "resolution": "credential_project",
                    "projectId": project_id,
                    "displayName": str(binding.get("projectName") or ""),
                    "environment": environment,
                    "created": False,
                }
                identity = _identity_payload(None, authenticated=True)

        if (
            not installed_ready
            and not aligned_to_key
            and (load_session() is not None or env_token)
        ):
            session_context: dict[str, Any] = {}
            if load_session() is not None:
                try:
                    session_context = fetch_session_context()
                except SessionClientError:
                    session_context = {}
            identity = _identity_payload(session_context, authenticated=True)
            try:
                bound, project_resolution = _resolve_authenticated_project(
                    project_root,
                    explicit_project=explicit_project,
                    explicit_environment=environment,
                    preferred_organization_id=organization_id_from_session_context(
                        session_context
                    ),
                )
            except SessionClientError as exc:
                if exc.status_code == 401:
                    raise
                return _configuration_required(
                    "project_resolution_failed",
                    detail=str(exc),
                    identity=identity,
                )
            if project_resolution.get("state") == "resolved" and project_resolution.get("projectId"):
                binding = bound
                project_id = str(bound.get("projectId") or "").strip()
                environment = str(bound.get("environment") or environment).strip() or "development"
                if project_resolution.get("created"):
                    install_action = "created"
            elif not project_id or project_resolution.get("reason") == "inaccessible_project":
                browser_outcome = _bootstrap_interaction(
                    "project_selection",
                    project_root,
                    api,
                    binding,
                    wait=wait,
                    poll_seconds=poll_seconds,
                    json_output=json_output,
                    extra={
                        "identity": identity,
                        "projectResolution": project_resolution,
                        "detail": _project_selection_detail(identity, project_resolution),
                    },
                )
                if isinstance(browser_outcome, _BrowserBootstrapResult):
                    api_key = browser_outcome.api_key
                    project_id = browser_outcome.project_id
                    environment = browser_outcome.environment
                    binding = browser_outcome.binding
                    setup_grant = setup_grant or browser_outcome.setup_grant
                    install_action = "created"
                else:
                    if isinstance(browser_outcome, InitResult):
                        browser_outcome.payload.setdefault("identity", identity)
                        browser_outcome.payload.setdefault("projectResolution", project_resolution)
                    return browser_outcome

        if not api_key and not installed_ready:
            api_key, install_action = _ensure_installation_credential(
                project_root,
                project_id=project_id,
                environment=environment,
                api_url=api,
                allow_reuse=not credential_invalid,
            )
    except SessionClientError:
        _discard_expired_session()
        browser_outcome = _bootstrap_interaction(
            "authentication",
            project_root,
            api,
            binding,
            wait=wait,
            poll_seconds=poll_seconds,
            json_output=json_output,
            identity_provider=identity_provider,
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
        return _interaction(
            "authentication",
            _device_verification_url(),
            exit_code=exc.exit_code,
            detail=str(exc),
        )

    profile = capability_profile(binding)
    project_id = str(binding.get("projectId") or project_id).strip()
    environment = str(binding.get("environment") or environment).strip() or "development"

    try:
        run_configure(project_root, api_url=api, token=api_key)
    except ConfigureError as exc:
        return InitResult(
            exit_code=exc.exit_code,
            payload={
                **_base_payload("configuration_required"),
                "code": "configure_failed",
                "reason": "configure_failed",
                "detail": str(exc),
            },
        )

    write_project_binding(project_root, binding)
    readiness = _fetch_readiness(api, api_key, profile)
    adopt_results: list[dict[str, Any]] = []

    if not ci_mode:
        missing = _missing_providers(readiness)
        if missing and (load_session() is not None or setup_grant):
            for provider in missing:
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
    payload["identity"] = identity if identity.get("authenticated") else _identity_payload(
        None, authenticated=load_session() is not None or bool(api_key)
    )
    payload["projectResolution"] = project_resolution
    resolution_name = (
        project_resolution.get("resolution")
        or binding.get("resolution")
        or ("created" if project_resolution.get("created") else "existing_binding")
    )
    payload["project"] = {
        "id": project_id,
        "name": str(binding.get("projectName") or project_resolution.get("displayName") or ""),
        "displayName": str(binding.get("projectName") or project_resolution.get("displayName") or ""),
        "environment": environment,
        "resolution": str(resolution_name or "existing_binding"),
        "action": "created" if project_resolution.get("created") else "reused",
    }
    payload["installation"] = {"configured": True, "action": install_action}
    payload["providers"] = _providers_section(readiness, adopt_results)
    payload["capabilities"] = _capabilities_section(readiness)
    payload["doctor"] = doctor_init_fields(report, doctor_code)
    _attach_mcp(project_root, payload)

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
