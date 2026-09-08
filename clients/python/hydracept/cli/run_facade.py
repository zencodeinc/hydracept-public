"""`hydracept run` façade — quote/invoke/jobs + wait + materialize. No second job engine."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from hydracept import HydraceptClient
from hydracept.cli.artifacts import default_output_dir, materialize_job_artifacts, _artifact_items
from hydracept.cli.artifact_output import resolve_artifact_output
from hydracept.cli.job_context import merge_workspace_job_context
from hydracept.cli.workspace import CliOverrides, ResolvedWorkspace
from hydracept.context import (
    ProjectCredentialMismatch,
    require_execution_context,
)
from hydracept.errors import HydraceptApiError
from hydracept.run_result import RunPricing, RunResult, TypedRunError

_TERMINAL = frozenset({"succeeded", "failed", "canceled", "cancelled"})
_SYNC_PREFIXES = ("text.", "domain.", "dns.")
_PRE_ADMISSION_CODES = frozenset(
    {
        "EstimateExceedsMaxCost",
        "EstimateUnavailable",
        "FundingRequired",
        "ProjectCredentialMismatch",
        "CONNECTION_REQUIRED",
        "billing_managed_usage_exhausted",
        "MANAGED_INFERENCE_UNAVAILABLE",
        "PROJECT_REQUIRED",
        "InvalidInput",
        "USE_JOBS",
        "USE_INVOKE",
    }
)


@dataclass
class RunOutcome:
    result: RunResult | None = None
    error: TypedRunError | None = None
    exit_code: int = 0

    def payload(self) -> dict[str, Any]:
        if self.error is not None:
            body = self.error.to_dict()
            if self.result is not None:
                body["runResult"] = self.result.to_dict()
            return body
        assert self.result is not None
        return self.result.to_dict()


def mint_idempotency_key() -> str:
    return f"run-{uuid4().hex}"


def _is_sync_capability(key: str, descriptor: dict[str, Any] | None) -> bool:
    modes = descriptor.get("executionModes") if isinstance(descriptor, dict) else None
    if isinstance(modes, list) and modes:
        return any(str(mode).startswith("invoke") for mode in modes) and not any(
            "job" in str(mode) for mode in modes
        )
    return key.startswith(_SYNC_PREFIXES)


def _pricing_from_job(job: dict[str, Any], receipt: dict[str, Any] | None) -> RunPricing:
    from hydracept.receipt_cost import micros_to_usd, surfaced_cost_micros

    estimated = job.get("estimatedCost")
    actual = job.get("actualCost")
    if receipt:
        pricing = receipt.get("pricing") or {}
        quote = (pricing.get("quote") or {}).get("customerTotal") or {}
        # The sealed receipt quote is financial authority for completed execution.
        # Never let an earlier job estimate or internal sentinel override it.
        micros = quote.get("amountMicros")
        if micros is not None:
            estimated = int(micros) / 1_000_000
        sealed = micros_to_usd(surfaced_cost_micros(receipt))
        if sealed is not None:
            actual = sealed
        elif str(job.get("status") or "").lower() != "succeeded":
            actual = None
    elif str(job.get("status") or "").lower() not in {"succeeded", "failed"}:
        actual = None
    return RunPricing(estimated_cost=_as_float(estimated), actual_cost=_as_float(actual))


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _map_api_error(exc: HydraceptApiError) -> TypedRunError:
    payload = exc.payload if isinstance(exc.payload, dict) else {}
    detail = payload.get("detail") if isinstance(payload.get("detail"), dict) else payload
    code = exc.code or str(detail.get("code") or "HTTP_ERROR")
    if code in {
        "CONNECTION_REQUIRED",
        "billing_managed_usage_exhausted",
        "MANAGED_INFERENCE_UNAVAILABLE",
    }:
        code = "FundingRequired"
    details = dict(detail.get("details") or {}) if isinstance(detail, dict) else {}
    if code == "FundingRequired":
        details.setdefault("managedWalletTopUpLive", False)
        details.setdefault("options", ["trial", "byok"])
    message = str(detail.get("message") or exc)
    http_status = exc.response.status_code if exc.response is not None else None
    pre = code in _PRE_ADMISSION_CODES or (http_status is not None and http_status in {400, 401, 402, 403, 409, 422})
    return TypedRunError(
        code=code,
        message=message,
        details=details,
        http_status=http_status,
        recovery={} if pre else {},
    )


def _attach_max_cost_and_idempotency(
    body: dict[str, Any],
    *,
    max_cost: float | None,
    idempotency_key: str,
) -> dict[str, Any]:
    payload = dict(body)
    execution = dict(payload.get("execution") or {})
    if max_cost is not None:
        constraints = dict(execution.get("executionConstraints") or {})
        constraints["maxCostUsd"] = max_cost
        execution["executionConstraints"] = constraints
    payload["execution"] = execution
    payload["idempotencyKey"] = idempotency_key
    return payload


def watch_job(
    client: HydraceptClient,
    job_id: str,
    *,
    timeout: float | None,
    poll_interval: float = 2.0,
) -> dict[str, Any]:
    deadline = None if timeout is None else time.time() + max(0.0, timeout)
    job = client.get_job(job_id)
    status = str(job.get("status") or "queued")
    while status not in _TERMINAL:
        if deadline is not None and time.time() >= deadline:
            return job
        time.sleep(max(0.2, poll_interval))
        job = client.get_job(job_id)
        status = str(job.get("status") or "unknown")
    return job


def _result_from_sync(
    capability: str,
    invoked: dict[str, Any],
    idempotency_key: str,
) -> RunResult:
    status = str(invoked.get("status") or "succeeded")
    execution_id = str(invoked.get("executionId") or invoked.get("id") or "") or None
    return RunResult(
        capability=capability,
        job_id=execution_id,
        execution_id=execution_id,
        status=status,
        output=invoked.get("output"),
        typed_output=invoked.get("typedOutput") or invoked.get("output"),
        pricing=_pricing_from_job(invoked, invoked.get("receipt") if isinstance(invoked.get("receipt"), dict) else None),
        receipt=invoked.get("receipt") if isinstance(invoked.get("receipt"), dict) else None,
        idempotency_key=idempotency_key,
        error=invoked.get("error") if isinstance(invoked.get("error"), dict) else None,
        diagnostics=invoked.get("diagnostics") if isinstance(invoked.get("diagnostics"), dict) else None,
    )


def recover_job(
    workspace: ResolvedWorkspace,
    job_id: str,
    *,
    project_root: Path,
    wait: bool = True,
    timeout: float | None = None,
    out: Path | None = None,
    capability: str = "",
    persist: bool = True,
    idempotency_key: str | None = None,
) -> RunOutcome:
    client = HydraceptClient(workspace.api_url, workspace.token, workspace=workspace)
    try:
        job = client.get_job(job_id)
    except HydraceptApiError as exc:
        return RunOutcome(error=_map_api_error(exc), exit_code=1)
    status = str(job.get("status") or "queued")
    if wait and status not in _TERMINAL:
        job = watch_job(client, job_id, timeout=timeout)
        status = str(job.get("status") or "unknown")
    receipt: dict[str, Any] | None = None
    if status in {"succeeded", "failed"}:
        try:
            receipt = client.get_job_receipt(job_id)
        except Exception:  # noqa: BLE001
            receipt = None
    artifacts: list = []
    persist_failed = False
    persist_error: str | None = None
    dest = default_output_dir(project_root, job_id)
    source = receipt or job
    has_remote = bool((source or {}).get("artifacts"))
    if persist and has_remote and status == "succeeded":
        items = _artifact_items(source)
        artifact_count = len(items) if items else 1
        filename = ""
        if items:
            from hydracept.jobs import filename_for_download

            filename = filename_for_download(
                items[0],
                str(items[0].get("artifactId") or items[0].get("id") or ""),
            )
        try:
            resolved_dest = resolve_artifact_output(
                project_root,
                str(out) if out else None,
                filename,
                artifact_count,
                job_id=job_id,
            )
        except Exception as exc:  # noqa: BLE001
            from hydracept.cli.artifact_output import ArtifactOutputError

            if isinstance(exc, ArtifactOutputError):
                result = RunResult(
                    capability=capability or str(job.get("capabilityKey") or ""),
                    job_id=job_id,
                    execution_id=job_id,
                    status=status,
                    artifacts=[],
                    pricing=_pricing_from_job(job, receipt),
                    receipt=receipt,
                    idempotency_key=idempotency_key or str(job.get("idempotencyKey") or "") or None,
                    error={"code": exc.code, "message": exc.message},
                )
                return RunOutcome(result=result, exit_code=1)
            raise
        dest = resolved_dest.parent if resolved_dest.suffix else resolved_dest
        materialized = materialize_job_artifacts(client, job_id, source, dest)
        artifacts = materialized.artifacts
        persist_failed = materialized.failed
        persist_error = materialized.error
    cap = capability or str(job.get("capabilityKey") or "")
    result = RunResult(
        capability=cap,
        job_id=job_id,
        execution_id=job_id,
        status="running" if status not in _TERMINAL else status,
        output=job.get("output") or (receipt or {}).get("output"),
        typed_output=job.get("typedOutput"),
        artifacts=artifacts,
        pricing=_pricing_from_job(job, receipt),
        receipt=receipt,
        idempotency_key=idempotency_key or str(job.get("idempotencyKey") or "") or None,
        error=job.get("error") if isinstance(job.get("error"), dict) else None,
        diagnostics=job.get("diagnostics") if isinstance(job.get("diagnostics"), dict) else None,
    )
    if persist_failed:
        result.error = {
            "code": "ArtifactPersistFailed",
            "message": persist_error or "local artifact contract failed",
        }
        result.diagnostics = {
            **(result.diagnostics or {}),
            "recovery": {
                "jobId": job_id,
                "out": str(dest),
                "cli": f"python -m hydracept jobs recover {job_id}",
            },
        }
        return RunOutcome(result=result, exit_code=1)
    if status == "failed":
        return RunOutcome(result=result, exit_code=1)
    return RunOutcome(result=result, exit_code=0)


def execute_run(
    project_root: Path,
    capability: str,
    input_body: dict[str, Any],
    *,
    overrides: CliOverrides | None = None,
    wait: bool = True,
    timeout: float | None = None,
    max_cost: float | None = None,
    idempotency_key: str | None = None,
    out: Path | None = None,
    persist: bool = True,
    refresh_context: bool = True,
) -> RunOutcome:
    try:
        workspace, _ctx = require_execution_context(
            project_root, overrides=overrides, refresh=refresh_context
        )
    except ProjectCredentialMismatch as exc:
        return RunOutcome(
            error=TypedRunError(
                code=exc.code,
                message=str(exc),
                details=exc.payload,
            ),
            exit_code=1,
        )
    except Exception as exc:  # noqa: BLE001
        from hydracept.cli.workspace import WorkspaceNotReadyError

        if isinstance(exc, WorkspaceNotReadyError):
            return RunOutcome(
                error=TypedRunError(code="WorkspaceNotReady", message=str(exc)),
                exit_code=4,
            )
        raise

    key = mint_idempotency_key() if not idempotency_key else idempotency_key.strip()
    client = HydraceptClient(workspace.api_url, workspace.token, workspace=workspace)
    raw = dict(input_body)
    if "input" not in raw and not any(k in raw for k in ("context", "execution", "idempotencyKey")):
        raw = {"input": raw}
    payload = merge_workspace_job_context(raw, workspace)
    payload = _attach_max_cost_and_idempotency(payload, max_cost=max_cost, idempotency_key=key)

    descriptor: dict[str, Any] | None = None
    try:
        descriptor = client.describe_capability(capability)
    except Exception:  # noqa: BLE001
        descriptor = None
    sync = _is_sync_capability(capability, descriptor)

    try:
        if sync:
            invoked = client.invoke_capability(capability, payload)
            result = _result_from_sync(capability, invoked, key)
            if str(result.status).lower() == "failed":
                return RunOutcome(result=result, exit_code=1)
            return RunOutcome(result=result, exit_code=0)
        submitted = client.submit_capability_job(capability, payload)
    except HydraceptApiError as exc:
        mapped = _map_api_error(exc)
        return RunOutcome(error=mapped, exit_code=1)

    job_id = str(submitted.get("jobId") or submitted.get("id") or submitted.get("executionId") or "")
    if not job_id:
        return RunOutcome(
            error=TypedRunError(code="InvalidInput", message="No jobId in submit response"),
            exit_code=1,
        )
    status = str(submitted.get("status") or "queued")
    if not wait:
        result = RunResult(
            capability=capability,
            job_id=job_id,
            execution_id=job_id,
            status="running" if status not in _TERMINAL else status,
            artifacts=[],
            pricing=RunPricing(
                estimated_cost=_as_float(submitted.get("estimatedCost")),
                actual_cost=None,
            ),
            idempotency_key=key,
            diagnostics=submitted.get("diagnostics")
            if isinstance(submitted.get("diagnostics"), dict)
            else None,
        )
        return RunOutcome(result=result, exit_code=0)
    outcome = recover_job(
        workspace,
        job_id,
        project_root=project_root,
        wait=True,
        timeout=timeout,
        out=out,
        capability=capability,
        persist=persist,
        idempotency_key=key,
    )
    if outcome.result is not None and not outcome.result.idempotency_key:
        outcome.result.idempotency_key = key
    return outcome


def parse_input_argument(value: str | None, file: Path | None) -> dict[str, Any]:
    if file is not None:
        text = file.read_text(encoding="utf-8")
        return json.loads(text)
    if value:
        stripped = value.strip()
        if stripped.startswith("{"):
            return json.loads(stripped)
        return {"prompt": stripped}
    return {}


def parse_json_body(
    positional: str | None,
    *,
    input_json: str = "",
    body_file: Path | None = None,
) -> dict[str, Any]:
    """File path, inline JSON object, --input, or '-' for stdin. No prompt coercion."""
    if body_file is not None:
        return json.loads(body_file.read_text(encoding="utf-8"))
    raw = (input_json or positional or "").strip()
    if not raw:
        raise ValueError("JSON body required (file path, inline object, --input, or -)")
    if raw == "-":
        import sys

        return json.loads(sys.stdin.read())
    if raw.startswith("{"):
        return json.loads(raw)
    path = Path(raw)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    raise ValueError(f"Not a JSON object or file: {raw[:80]}")
