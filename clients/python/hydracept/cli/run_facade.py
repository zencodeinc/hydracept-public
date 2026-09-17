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
# Historical internal "unbounded" values were never customer prices. Treat any
# value in that sentinel range as unavailable on public projections.
_INTERNAL_SENTINEL_COST_FLOOR = 900_000_000.0
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
    """Whether this capability runs synchronously.

    The API owns this classification (``execution.mode``); re-deriving it here
    would let the two copies drift. The prefix heuristic is a last resort for an
    unavailable descriptor only.
    """
    if isinstance(descriptor, dict):
        execution = descriptor.get("execution")
        if isinstance(execution, dict):
            mode = str(execution.get("mode") or "").strip().lower()
            if mode in {"invoke", "job"}:
                return mode == "invoke"
        modes = descriptor.get("executionModes")
        if isinstance(modes, list) and modes:
            return any(str(mode).startswith("invoke") for mode in modes) and not any(
                "job" in str(mode) for mode in modes
            )
    return key.startswith(_SYNC_PREFIXES)


def _pricing_from_job(job: dict[str, Any], receipt: dict[str, Any] | None) -> RunPricing:
    from hydracept.receipt_cost import (
        customer_charge_micros,
        customer_financial_state,
        estimated_customer_charge_micros,
        estimated_provider_cost_micros,
        micros_to_usd,
        pricing_mode,
        provider_cost_micros,
        retail_charge_micros,
        service_fee_bps,
        surfaced_cost_micros,
    )

    estimated = job.get("estimatedCost")
    actual = job.get("actualCost")
    source = receipt if isinstance(receipt, dict) else job
    customer_total = customer_charge_micros(source)
    state = customer_financial_state(source)
    mode = pricing_mode(source) or None
    if receipt:
        pricing = receipt.get("pricing") or {}
        quote = (pricing.get("quote") or {}).get("customerTotal") or {}
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
    return RunPricing(
        estimated_cost=_as_float(estimated),
        actual_cost=_as_float(actual),
        customer_total_micros=customer_total,
        provider_basis_micros=provider_cost_micros(source),
        estimated_provider_micros=estimated_provider_cost_micros(source),
        estimated_charge_micros=estimated_customer_charge_micros(source),
        financial_state=state,
        mode=mode,
        provider_cost_micros=provider_cost_micros(source),
        managed_equivalent_micros=retail_charge_micros(source),
        estimated_provider_cost_micros=estimated_provider_cost_micros(source),
        service_fee_bps=service_fee_bps(source),
    )


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        return None
    if abs(resolved) >= _INTERNAL_SENTINEL_COST_FLOOR:
        return None
    return resolved


_VALIDATION_ERROR_TYPES = frozenset({"missing", "required", "value_error.missing"})


def _validation_errors(payload: Any) -> list[dict[str, Any]]:
    """Collect pydantic-style validation errors from any Hydracept 4xx body shape."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    detail = payload.get("detail")
    if isinstance(detail, list):
        return [item for item in detail if isinstance(item, dict)]
    for blob in (detail, payload):
        if not isinstance(blob, dict):
            continue
        for key in ("errors", "validationErrors"):
            value = blob.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _missing_input_fields(payload: Any) -> list[str]:
    """Dotted input paths that were required but absent from a submitted body."""
    missing: list[str] = []
    for error in _validation_errors(payload):
        if str(error.get("type") or "") not in _VALIDATION_ERROR_TYPES:
            continue
        loc = [
            str(part)
            for part in (error.get("loc") or [])
            if str(part) not in {"body", "input", "__root__"}
        ]
        if loc:
            path = ".".join(loc)
            if path not in missing:
                missing.append(path)
    return missing


def _recovery_for_missing_input(capability: str, missing: list[str]) -> dict[str, Any]:
    """Tell the caller exactly how to supply the missing value."""
    fields = ", ".join(missing)
    leaves = {path.split(".")[-1] for path in missing}
    key = capability or "<capability>"
    if "prompt" in leaves:
        command = f'python -m hydracept run {key} --prompt "..." --json'
    else:
        command = f"python -m hydracept run {key} --input-file request.json --json"
    return {
        "nextAction": command,
        "cli": command,
        "missingInputFields": list(missing),
        "message": f"Provide the missing input field(s): {fields}.",
    }


def _map_api_error(
    exc: HydraceptApiError,
    *,
    capability: str = "",
    catalog: Any = (),
    scope: str = "capability",
) -> TypedRunError:
    from hydracept.capability_errors import (
        UNKNOWN_CAPABILITY,
        classify_capability_error,
        suggest_capability_keys,
    )

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
    error_class = classify_capability_error(
        status=http_status, code=code, message=message, scope=scope
    )
    if error_class is not None:
        details.setdefault("errorClass", error_class)
    key = str(capability or detail.get("capabilityKey") or detail.get("capability") or "").strip()
    if error_class == UNKNOWN_CAPABILITY:
        code = UNKNOWN_CAPABILITY
        details["unknownCapability"] = key
        details["suggestions"] = suggest_capability_keys(key, catalog)
    missing = _missing_input_fields(exc.payload)
    if missing:
        code = "InvalidInput"
        fields = ", ".join(missing)
        mentions_prompt = any(path.split(".")[-1] == "prompt" for path in missing)
        hint = (
            "Pass --prompt on the CLI, or input.prompt in the request body."
            if mentions_prompt
            else "Pass the field in the input body."
        )
        message = f"{capability or 'This capability'} needs input field(s): {fields}. {hint}"
        details = {**details, "missingInputFields": missing}
    recovery = (
        _recovery_for_missing_input(capability, missing)
        if missing
        else _recovery_for_mapped_error(
            code,
            http_status,
            detail if isinstance(detail, dict) else {},
            capability=capability,
        )
    )
    return TypedRunError(
        code=code,
        message=message,
        details=details,
        http_status=http_status,
        error_class=error_class,
        recovery=recovery,
    )


def _recovery_for_mapped_error(
    code: str,
    http_status: int | None,
    detail: dict[str, Any],
    *,
    capability: str = "",
) -> dict[str, Any]:
    next_action = str(detail.get("nextAction") or "").strip()
    lowered = f"{code} {detail.get('message') or ''}".lower()
    key = str(capability or detail.get("capabilityKey") or detail.get("capability") or "").strip()
    describe = (
        f"python -m hydracept capabilities describe {key} --json"
        if key
        else "python -m hydracept capabilities describe --json"
    )
    if not next_action:
        if code == "UNKNOWN_CAPABILITY":
            next_action = (
                f'python -m hydracept capabilities find "{key}" --json'
                if key
                else "python -m hydracept capabilities find --json"
            )
        elif code == "WORKSPACE_CAPABILITY_DISABLED":
            next_action = describe
        elif code == "EstimateExceedsMaxCost":
            next_action = (
                f"python -m hydracept run {key} --input-file request.json --max-cost <higher-usd> --json"
                if key
                else "python -m hydracept run <capability> --input-file request.json --max-cost <higher-usd> --json"
            )
        elif code == "FundingRequired":
            next_action = "python -m hydracept funding status --json"
        elif code in {"UnsupportedTld", "UNSUPPORTED_TLD"} or "unsupported tld" in lowered:
            next_action = "python -m hydracept capabilities describe domain.search.v1 --json"
        elif code == "HTTP_ERROR":
            next_action = "python -m hydracept capabilities find --json"
        elif http_status in {400, 422} or code in {"InvalidInput", "USE_JOBS", "USE_INVOKE"}:
            next_action = describe
        else:
            next_action = "python -m hydracept doctor --json"
    return {"nextAction": next_action, "cli": next_action}


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
    *,
    client: HydraceptClient | None = None,
) -> RunResult:
    status = str(invoked.get("status") or "succeeded")
    execution_id = str(invoked.get("executionId") or invoked.get("id") or "") or None
    receipt = invoked.get("receipt") if isinstance(invoked.get("receipt"), dict) else None
    if receipt is None and client is not None and execution_id:
        try:
            receipt = client.get_job_receipt(execution_id)
        except Exception:  # noqa: BLE001
            receipt = None
    return RunResult(
        capability=capability,
        job_id=execution_id,
        execution_id=execution_id,
        status=status,
        output=invoked.get("output"),
        typed_output=invoked.get("typedOutput") or invoked.get("output"),
        pricing=_pricing_from_job(invoked, receipt),
        receipt=receipt,
        idempotency_key=idempotency_key,
        error=invoked.get("error") if isinstance(invoked.get("error"), dict) else None,
        diagnostics=invoked.get("diagnostics") if isinstance(invoked.get("diagnostics"), dict) else None,
    )


def _persist_sync_result(project_root: Path, out: Path, result: RunResult) -> Path:
    """Honor `run --out` for invoke-only capabilities. Text renders as text."""
    from hydracept.cli.result_persistence import persist_run_result

    return persist_run_result(project_root, out, result)


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
        return RunOutcome(
            error=_map_api_error(exc, capability=capability, scope="job"), exit_code=1
        )
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
        dest = resolved_dest
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
    if out is not None:
        from hydracept.cli.result_persistence import (
            output_not_persisted_note,
            persist_run_result,
        )

        requested = str(out)
        persisted = artifacts[0].local_path if artifacts else None
        if persisted is None and persist and status == "succeeded":
            try:
                persisted = str(persist_run_result(project_root, out, result))
            except Exception as exc:  # noqa: BLE001
                result.error = {
                    "code": "OutputPersistFailed",
                    "message": str(exc),
                }
                result.diagnostics = {
                    **(result.diagnostics or {}),
                    "requestedOutputPath": requested,
                    "persistedOutputPath": None,
                }
                return RunOutcome(result=result, exit_code=1)
        result.diagnostics = {
            **(result.diagnostics or {}),
            "requestedOutputPath": requested,
            "persistedOutputPath": persisted,
        }
        if persisted is None:
            result.diagnostics["outputNote"] = output_not_persisted_note(
                status=status,
                persist=persist,
                has_remote_artifacts=has_remote,
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
    from hydracept.cli.structured_output_guard import empty_structured_output_error

    empty = empty_structured_output_error(cap, result)
    if empty is not None:
        return RunOutcome(error=empty, result=result, exit_code=1)
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

    from hydracept.capability_errors import INVALID_INPUT
    from hydracept.cli.run_input_coercion import InputValidationError, coerce_capability_input

    try:
        normalized_input = coerce_capability_input(capability, dict(input_body))
    except InputValidationError as exc:
        details: dict[str, Any] = {"errorClass": INVALID_INPUT}
        if exc.field:
            details["field"] = exc.field
        if exc.expected:
            details["expected"] = exc.expected
        return RunOutcome(
            error=TypedRunError(
                code="InvalidInput",
                message=exc.message,
                details=details,
                error_class=INVALID_INPUT,
                recovery=exc.recovery
                or {"nextAction": f"python -m hydracept capabilities describe {capability} --json"},
            ),
            exit_code=1,
        )

    key = mint_idempotency_key() if not idempotency_key else idempotency_key.strip()
    client = HydraceptClient(workspace.api_url, workspace.token, workspace=workspace)
    raw = dict(normalized_input)
    if "input" not in raw and not any(k in raw for k in ("context", "execution", "idempotencyKey")):
        raw = {"input": raw}
    payload = merge_workspace_job_context(raw, workspace)
    payload = _attach_max_cost_and_idempotency(payload, max_cost=max_cost, idempotency_key=key)
    from hydracept.cli.image_canvas import preflight_image_canvas

    blocked = preflight_image_canvas(capability, payload)
    if blocked is not None:
        return RunOutcome(
            error=TypedRunError(
                code=str(blocked.get("code") or "InvalidInput"),
                message=str(blocked.get("message") or "invalid image canvas"),
                details=blocked,
            ),
            exit_code=1,
        )

    descriptor: dict[str, Any] | None = None
    describe_error: HydraceptApiError | None = None
    catalog: Any = ()
    try:
        descriptor = client.describe_capability(capability)
    except HydraceptApiError as exc:
        describe_error = exc
    except Exception:  # noqa: BLE001
        descriptor = None

    if describe_error is not None:
        from hydracept.capability_errors import (
            UNKNOWN_CAPABILITY,
            classify_capability_error,
            fetch_suggestion_catalog,
        )

        describe_status = (
            describe_error.response.status_code if describe_error.response is not None else None
        )
        if (
            classify_capability_error(
                status=describe_status,
                code=describe_error.code,
                message=str(describe_error),
            )
            == UNKNOWN_CAPABILITY
        ):
            catalog = fetch_suggestion_catalog(client)
            return RunOutcome(
                error=_map_api_error(
                    describe_error, capability=capability, catalog=catalog
                ),
                exit_code=1,
            )
    sync = _is_sync_capability(capability, descriptor)

    try:
        if sync:
            invoked = client.invoke_capability(capability, payload)
            result = _result_from_sync(capability, invoked, key, client=client)
            from hydracept.cli.structured_output_guard import empty_structured_output_error

            empty = empty_structured_output_error(capability, result)
            if empty is not None:
                return RunOutcome(error=empty, result=result, exit_code=1)
            if str(result.status).lower() == "failed":
                return RunOutcome(result=result, exit_code=1)
            if out is not None:
                if persist:
                    try:
                        _persist_sync_result(project_root, out, result)
                    except Exception as exc:  # noqa: BLE001
                        result.error = {
                            "code": "OutputPersistFailed",
                            "message": str(exc),
                        }
                        result.diagnostics = {
                            **(result.diagnostics or {}),
                            "requestedOutputPath": str(out),
                            "persistedOutputPath": None,
                        }
                        return RunOutcome(result=result, exit_code=1)
                else:
                    from hydracept.cli.result_persistence import output_not_persisted_note

                    result.diagnostics = {
                        **(result.diagnostics or {}),
                        "requestedOutputPath": str(out),
                        "persistedOutputPath": None,
                        "outputNote": output_not_persisted_note(
                            status=str(result.status), persist=False
                        ),
                    }
            return RunOutcome(result=result, exit_code=0)
        submitted = client.submit_capability_job(capability, payload)
    except HydraceptApiError as exc:
        mapped = _map_api_error(exc, capability=capability, catalog=catalog)
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
        if out is not None:
            from hydracept.cli.result_persistence import output_not_persisted_note

            result.diagnostics = {
                **(result.diagnostics or {}),
                "requestedOutputPath": str(out),
                "persistedOutputPath": None,
                "outputNote": output_not_persisted_note(
                    status=str(result.status), persist=persist
                ),
            }
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
    from hydracept.cli.json_file import read_json_file

    if file is not None:
        payload = read_json_file(file)
        if not isinstance(payload, dict):
            raise ValueError("JSON file must contain an object")
        return payload
    if value:
        stripped = value.strip()
        if stripped.startswith("{"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "Invalid JSON. PowerShell often mangles --input '{...}'. "
                    "Use --prompt or --input-file path.json."
                ) from exc
        return {"prompt": stripped}
    return {}


def parse_json_body(
    positional: str | None,
    *,
    input_json: str = "",
    body_file: Path | None = None,
) -> dict[str, Any]:
    """File path, inline JSON object, --input, or '-' for stdin. No prompt coercion."""
    from hydracept.cli.json_file import read_json_file

    if body_file is not None:
        payload = read_json_file(body_file)
        if not isinstance(payload, dict):
            raise ValueError("JSON file must contain an object")
        return payload
    raw = (input_json or positional or "").strip()
    if not raw:
        raise ValueError(
            "JSON body required. Use --prompt \"...\", --input-file path.json, inline JSON, or - for stdin."
        )
    if raw == "-":
        import sys

        return json.loads(sys.stdin.read())
    if raw.startswith("{"):
        return json.loads(raw)
    path = Path(raw)
    if path.is_file():
        payload = read_json_file(path)
        if not isinstance(payload, dict):
            raise ValueError("JSON file must contain an object")
        return payload
    raise ValueError(f"Not a JSON object or file: {raw[:80]}")
