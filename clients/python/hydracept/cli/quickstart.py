"""Monotonic quickstart orchestration (ADR-019)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console

from hydracept.cli.bootstrap import ConfigureError, run_configure
from hydracept.cli.doctor import build_doctor_report, doctor_exit_code
from hydracept.cli.exit_codes import (
    AUTH,
    DOCTOR_FAILED,
    SMOKE_FAILED,
    SUCCESS,
    USAGE,
)
from hydracept.cli.login_flow import LoginError, login_with_token
from hydracept.cli.smoke_runner import SmokeError, run_smoke
from hydracept.cli.workspace import (
    CliOverrides,
    WorkspaceState,
    resolve_workspace,
    workspace_state,
)

QUICKSTART_SCHEMA_VERSION = "hydracept.cli.quickstart.v1"

_CREDENTIAL_REQUIRED_DETAIL = (
    "No API credential available. "
    "Use `hydracept login`, pass `--token`, or set HYDRACEPT_API_KEY."
)
_CREDENTIAL_REQUIRED_NEXT_ACTIONS = [
    "python -m hydracept login --token <HYDRACEPT_API_KEY>",
    "python -m hydracept quickstart --token <HYDRACEPT_API_KEY> --json",
    "export HYDRACEPT_API_KEY=<key>",
]


@dataclass
class QuickstartResult:
    exit_code: int
    payload: dict[str, Any] = field(default_factory=dict)


def _base_payload(workspace_state_value: WorkspaceState, workspace: Any | None) -> dict[str, Any]:
    ready = workspace_state_value == WorkspaceState.READY
    return {
        "schemaVersion": QUICKSTART_SCHEMA_VERSION,
        "status": workspace_state_value.value,
        "workspace": {"state": workspace_state_value.value, "ready": ready},
        "apiUrl": workspace.api_url if workspace else "",
        "projectId": workspace.project_id if workspace else "",
        "environment": workspace.environment if workspace else "",
        "steps": {},
    }


def _credential_failure(
    *,
    error: str,
    detail: str,
    next_actions: list[str] | None = None,
) -> QuickstartResult:
    payload = _base_payload(WorkspaceState.UNCONFIGURED, None)
    payload["steps"] = {"login": {"status": "failed", "detail": detail}}
    payload["error"] = error
    if next_actions is not None:
        payload["nextActions"] = next_actions
    return QuickstartResult(exit_code=USAGE, payload=payload)


def run_quickstart(
    project_root: Path,
    *,
    api_url: str | None = None,
    token: str | None = None,
    run_smoke_step: bool = False,
    smoke_capability: str | None = None,
    json_output: bool = False,
    console: Console | None = None,
) -> QuickstartResult:
    steps: dict[str, Any] = {}

    if token is None:
        effective_token = (os.environ.get("HYDRACEPT_API_KEY") or "").strip()
        if not effective_token:
            return _credential_failure(
                error="credential_required",
                detail=_CREDENTIAL_REQUIRED_DETAIL,
                next_actions=_CREDENTIAL_REQUIRED_NEXT_ACTIONS,
            )
    elif not token.strip():
        return _credential_failure(error="empty_token", detail="Empty --token")
    else:
        effective_token = token.strip()

    overrides = CliOverrides(token=effective_token or None, api_url=api_url)

    try:
        login_with_token(project_root, effective_token, console=None if json_output else console)
        steps["login"] = {"status": "succeeded"}
    except LoginError as exc:
        payload = _base_payload(WorkspaceState.UNCONFIGURED, None)
        payload["steps"] = {"login": {"status": "failed", "detail": str(exc)}}
        payload["error"] = str(exc)
        return QuickstartResult(exit_code=exc.exit_code, payload=payload)

    workspace = resolve_workspace(project_root, overrides=overrides)
    payload = _base_payload(workspace_state(workspace), workspace)

    try:
        result = run_configure(project_root, api_url=api_url, token=effective_token)
        steps["configure"] = {"status": "succeeded"}
        workspace = result.workspace
        payload = _base_payload(workspace_state(workspace), workspace)
    except ConfigureError as exc:
        steps["configure"] = {"status": "failed", "detail": str(exc)}
        payload["steps"] = steps
        payload["error"] = str(exc)
        payload["status"] = workspace_state(workspace).value
        return QuickstartResult(exit_code=exc.exit_code, payload=payload)

    report = build_doctor_report(
        workspace.api_url,
        project_root,
        workspace.token,
        smoke_capability=smoke_capability,
    )
    doctor_code = doctor_exit_code(report)
    steps["doctor"] = {
        "status": "succeeded" if doctor_code == SUCCESS else "failed",
        "exitCode": doctor_code,
        "report": report.to_json_dict(),
    }
    payload["steps"] = steps
    payload["status"] = workspace_state(workspace).value
    payload["workspace"] = {
        "state": workspace_state(workspace).value,
        "ready": workspace_state(workspace) == WorkspaceState.READY,
    }

    if doctor_code != SUCCESS:
        payload["error"] = "Doctor failed"
        return QuickstartResult(exit_code=DOCTOR_FAILED, payload=payload)

    try:
        from hydracept.cli.agents.detect import auto_hosts, detect_all

        detection = detect_all(project_root)
        payload["agentIntegrations"] = detection.get("hosts", {})
        if console and not json_output:
            for name, info in (detection.get("hosts") or {}).items():
                if info.get("detected") and not info.get("installed"):
                    console.print(
                        f"Detected {name}. Install: "
                        f"python -m hydracept agents install {name}"
                    )
    except Exception:
        pass

    if not run_smoke_step:
        if console and not json_output:
            console.print("[green]Quickstart ready[/green] — run python -m hydracept smoke")
        return QuickstartResult(exit_code=SUCCESS, payload=payload)

    try:
        smoke = run_smoke(
            project_root,
            api_url=workspace.api_url,
            token=workspace.token,
            capability=smoke_capability or "image.generate.v1",
        )
        receipt_id = ""
        if smoke.receipt:
            receipt_id = str(smoke.receipt.get("receiptId") or smoke.receipt.get("id") or "")
        steps["smoke"] = {
            "status": "succeeded",
            "jobId": smoke.job_id,
            "receiptId": receipt_id,
            "artifactIds": smoke.artifact_ids,
        }
        payload["steps"] = steps
        if console and not json_output:
            console.print(f"[green]Smoke succeeded[/green] jobId={smoke.job_id}")
        return QuickstartResult(exit_code=SUCCESS, payload=payload)
    except SmokeError as exc:
        steps["smoke"] = {"status": "failed", "detail": str(exc)}
        payload["steps"] = steps
        payload["error"] = str(exc)
        return QuickstartResult(exit_code=SMOKE_FAILED, payload=payload)
