"""Opportunistic capability run — compose init + existing job/invoke execution."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from hydracept import HydraceptClient
from hydracept.cli.exit_codes import NOT_READY, USAGE
from hydracept.cli.init_resolver import run_init
from hydracept.cli.workspace import (
    CliOverrides,
    ResolvedWorkspace,
    WorkspaceState,
    resolve_workspace,
    workspace_state,
)

DEFAULT_POLL_SECONDS = 600
DEFAULT_POLL_INTERVAL = 4.0
FUNDING_REQUIRED_CLI = (
    "This capability is ready, but your managed first-use allowance has been used.\n"
    "Continue with:\n"
    "- managed funding\n"
    "- BYOK"
)


class RunCapabilityError(Exception):
    def __init__(self, message: str, exit_code: int = USAGE, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.payload = payload or {}


def ensure_workspace_for_run(
    project_root: Path,
    *,
    api_url: str | None = None,
    token: str | None = None,
) -> tuple[ResolvedWorkspace | None, dict[str, Any] | None]:
    """Return a ready workspace, or an init payload if a human/config boundary remains.

    Composes existing `run_init` — does not invent a second bootstrap.
    """
    resolved = resolve_workspace(
        project_root,
        overrides=CliOverrides(token=token, api_url=api_url),
    )
    if resolved is not None and workspace_state(resolved) == WorkspaceState.READY:
        return resolved, None

    init_result = run_init(
        project_root,
        api_url=api_url,
        apply=True,
        yes=True,
        json_output=True,
    )
    status = str(init_result.payload.get("status") or "")
    if status == "ready":
        resolved = resolve_workspace(
            project_root,
            overrides=CliOverrides(token=token, api_url=api_url),
        )
        if resolved is not None and workspace_state(resolved) == WorkspaceState.READY:
            payload = dict(init_result.payload)
            payload["bootstrapComposed"] = True
            return resolved, payload

    payload = dict(init_result.payload)
    payload["bootstrapComposed"] = True
    return None, payload


def build_run_input(
    *,
    prompt: str | None,
    input_json: str | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = dict(extra or {})
    if input_json:
        parsed = json.loads(input_json)
        if not isinstance(parsed, dict):
            raise RunCapabilityError("--input must be a JSON object")
        payload.update(parsed)
    if prompt:
        payload.setdefault("prompt", prompt)
    return payload


def _http_boundary_payload(exc: BaseException) -> dict[str, Any] | None:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if response is None or status_code not in {402, 403, 429}:
        return None
    try:
        body = response.json()
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(body, dict):
        return None
    detail = body.get("detail")
    payload = detail if isinstance(detail, dict) else body
    details = payload.get("details") if isinstance(payload.get("details"), dict) else payload
    code = str(payload.get("code") or (details or {}).get("code") or "")
    status = str((details or {}).get("status") or payload.get("status") or "")
    if code in {"trial_concurrency_exceeded", "trial_daily_limit_exceeded"} or status in {
        "trial_concurrency_exceeded",
        "trial_daily_limit_exceeded",
    }:
        message = str(payload.get("message") or (details or {}).get("message") or "")
        return {
            "status": code or status,
            "code": code or status,
            "message": message or "Managed first-use rate limit reached. Wait and retry.",
            "details": details,
        }
    if code not in {"funding_required", "billing_managed_usage_exhausted"} and status != "funding_required":
        return None
    options = (details or {}).get("fundingOptions") or ["managed", "byok"]
    return {
        "status": "funding_required",
        "code": "funding_required",
        "message": FUNDING_REQUIRED_CLI,
        "fundingOptions": options,
        "details": details,
    }


def _raise_funding_required(exc: BaseException) -> None:
    payload = _http_boundary_payload(exc)
    if payload is None:
        return
    raise RunCapabilityError(payload["message"], exit_code=NOT_READY, payload=payload) from exc


def _job_body(workspace: ResolvedWorkspace, capability_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "context": {
            "productId": workspace.project_id,
            "projectId": workspace.project_id,
            "environment": workspace.environment,
        },
        "input": capability_input,
        "execution": {"executionPreference": "automatic"},
        "idempotencyKey": f"cli-run-{int(time.time())}",
    }


def _execution_modes(client: HydraceptClient, capability_key: str) -> list[str]:
    try:
        described = client.describe_capability(capability_key)
    except Exception:  # noqa: BLE001
        return ["job_async"]
    modes = described.get("executionModes") or []
    return [str(mode) for mode in modes]


def _watch_job(
    client: HydraceptClient,
    job_id: str,
    *,
    poll_seconds: int,
) -> dict[str, Any]:
    deadline = time.time() + max(5, poll_seconds)
    status = "unknown"
    current: dict[str, Any] = {}
    while time.time() < deadline:
        current = client.get_job(job_id)
        status = str(current.get("status") or current.get("currentStatus") or "unknown")
        if status.lower() in {
            "succeeded",
            "failed",
            "canceled",
            "cancelled",
            "awaiting_approval",
            "needs_attention",
        }:
            break
        time.sleep(DEFAULT_POLL_INTERVAL)
    result: dict[str, Any] = {"jobId": job_id, "status": status, "job": current}
    if status.lower() == "succeeded":
        try:
            result["receipt"] = client.get_job_receipt(job_id)
        except Exception:  # noqa: BLE001
            result["receipt"] = None
        artifacts = current.get("artifacts") or (result.get("receipt") or {}).get("artifacts") or []
        result["artifacts"] = artifacts
    return result


def run_capability(
    project_root: Path,
    capability_key: str,
    *,
    prompt: str | None = None,
    input_json: str | None = None,
    input_data: dict[str, Any] | None = None,
    api_url: str | None = None,
    token: str | None = None,
    watch: bool = True,
    poll_seconds: int = DEFAULT_POLL_SECONDS,
) -> dict[str, Any]:
    capability_input = build_run_input(prompt=prompt, input_json=input_json, extra=input_data)
    if not capability_input:
        raise RunCapabilityError("Pass --prompt or --input JSON")

    workspace, bootstrap = ensure_workspace_for_run(
        project_root, api_url=api_url, token=token
    )
    if workspace is None:
        payload = bootstrap or {}
        status = str(payload.get("status") or "configuration_required")
        if status == "interaction_required":
            return payload
        raise RunCapabilityError(
            str(payload.get("detail") or payload.get("reason") or "Workspace not ready"),
            exit_code=NOT_READY,
            payload=payload,
        )

    client = HydraceptClient(workspace.api_url, workspace.token)
    modes = _execution_modes(client, capability_key)
    body = _job_body(workspace, capability_input)
    envelope: dict[str, Any] = {"capabilityKey": capability_key}
    if bootstrap and bootstrap.get("bootstrapComposed"):
        envelope["bootstrapComposed"] = True

    try:
        if "invoke_sync" in modes and "job_async" not in modes:
            invoked = client.invoke_capability(capability_key, body)
            envelope["mode"] = "invoke"
            envelope["result"] = invoked
            envelope["status"] = "succeeded"
            return envelope

        submitted = client.submit_capability_job(capability_key, body)
    except httpx.HTTPStatusError as exc:
        _raise_funding_required(exc)
        raise

    job_id = str(submitted.get("jobId") or submitted.get("executionId") or "")
    envelope["mode"] = "job"
    envelope["jobId"] = job_id
    envelope["submitted"] = submitted
    if not watch or not job_id:
        envelope["nextAction"] = "poll" if job_id else "inspect_error"
        envelope["status"] = submitted.get("status") or "queued"
        return envelope
    watched = _watch_job(client, job_id, poll_seconds=poll_seconds)
    envelope.update(watched)
    return envelope
