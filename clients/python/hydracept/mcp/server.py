"""Stdio MCP server — capability jobs plus project-surface tools (ADR-021, ADR-026)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import httpx
from mcp.server.mcpserver.server import MCPServer
from mcp_types import CallToolResult, TextContent

from hydracept import HydraceptClient
from hydracept.errors import HydraceptApiError, RunAdmissionError, raise_api_status
from hydracept.cli.agent_status import AGENT_PACK_VERSION, build_agent_status
from hydracept.cli.run_capability import ensure_workspace_for_run
from hydracept.cli.smoke_runner import DEFAULT_SMOKE_CAPABILITY, DEFAULT_SMOKE_PROMPT, SmokeError, run_smoke
from hydracept.cli.job_context import merge_workspace_job_context
from hydracept.cli.artifact_output import finalize_single_artifact_path, resolve_artifact_output
from hydracept.cli.workspace import DEFAULT_API, WorkspaceNotReadyError, require_ready_workspace, resolve_workspace
from hydracept.job_wait import decorate_job_tool_result, infer_primary_artifact_id, infer_preview_artifact_id
from hydracept.mcp.icons import hydracept_mcp_icons
from hydracept.mcp.panel import APP_URI, attach_interaction, create_apps, surface_for_job
from hydracept.mcp.register_project_tools import register_project_tools
from hydracept.mcp.capability_arg import resolve_capability_key
from hydracept.mcp.workspace_locator import (
    is_unexpanded_placeholder,
    resolve_mcp_workspace,
)

_WORKSPACE_ROOT: Path | None = None
_RESOLVED_WORKSPACE: Path | None = None
_MOUNTED_JOB_IDS: set[str] = set()
_INTERNAL_SENTINEL_COST_FLOOR = 900_000_000.0


def _first_nonempty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def configure_workspace(root: Path | str | None) -> None:
    global _WORKSPACE_ROOT, _RESOLVED_WORKSPACE
    _RESOLVED_WORKSPACE = None
    if root is None or is_unexpanded_placeholder(root):
        _WORKSPACE_ROOT = None
        return
    path = Path(root)
    _WORKSPACE_ROOT = path.resolve() if path.is_dir() else None


def reset_workspace_cache() -> None:
    """Test helper: clear memoized MCP workspace resolution."""
    global _RESOLVED_WORKSPACE
    _RESOLVED_WORKSPACE = None


server = MCPServer(
    name="hydracept",
    title="Hydracept",
    website_url="https://hydracept.com",
    icons=hydracept_mcp_icons(),
    instructions=(
        "Hydracept public capability jobs, pinned execution, and project surfaces. "
        "Credentials resolve from workspace only. "
        "One capability call is enough — do not assume repeated usage is required. "
        "hydracept_run composes init when needed and waits for terminal completion by default; "
        "pass wait=false when an immediate durable-job continuation is preferred. "
        "Project surface tools require cwd to be the game checkout. "
        "hydracept_submit_job and hydracept_job_status return immediately. "
        "If nextAction is poll, wait pollAfterSeconds and call hydracept_job_status again. "
        "Do not call hydracept_ui_* tools; those are for the Hydracept panel iframe only. "
        "For PNG transparency, never infer alpha correctness from a host image preview or vision description; "
        "trust transparencyReport or python -m hydracept verify <path.png> --json. "
        "A Hydracept App (ui://hydracept/app.html) is the visual control surface for "
        "seven semantic states: project.connect, capability.launch, "
        "connection.resolve, authorization.preflight, job.progress, artifact.review, "
        "and change.promote. "
        "When Hydracept returns presentation.agentAction=present_and_yield, present "
        "that surface and perform no subsequent unrelated tool calls or prose in the "
        "same turn. If presentation.status is mount_requested, present the App. "
        "If presentation.status is mounted or already_mounted, do not replace it "
        "with a text fallback. If presentation.status is fallback or unsupported, "
        "use the supplied fallback. "
        "Defer long assessments across blocking Hydracept interactions. "
        "When a human decision or structured input is needed, call "
        "hydracept_interaction_surface instead of synthesizing a browser or CLI flow. "
        "App-only hydracept_ui_* wrappers adapt user actions to existing primitives; they are not "
        "a second execution, pricing, or repository plane. Generic artifact review does "
        "not approve or reject jobs. Domain human gates use authorization.preflight. "
        "Promotion stays project-local. Hydracept cloud does not write repositories."
    ),
)

apps = create_apps()


def _project_root() -> Path:
    global _RESOLVED_WORKSPACE
    if _RESOLVED_WORKSPACE is not None:
        return _RESOLVED_WORKSPACE
    _RESOLVED_WORKSPACE = resolve_mcp_workspace(_WORKSPACE_ROOT)
    return _RESOLVED_WORKSPACE


def _execution_workspace():
    from hydracept.context import require_execution_context

    workspace, _ = require_execution_context(_project_root())
    return workspace


def _client() -> HydraceptClient:
    workspace = require_ready_workspace(_project_root())
    return HydraceptClient(workspace.api_url, workspace.token, workspace=workspace)


def _hydrate_result(payload: dict[str, Any], surface: str | None = None) -> dict[str, Any]:
    from hydracept.mcp.interaction_hydration import attach_hydrated_interaction

    hinted = surface or surface_for_job(payload if isinstance(payload, dict) else {})
    try:
        return attach_hydrated_interaction(
            payload,
            hinted,
            project_root=_project_root(),
            client=_client,
        )
    except Exception:  # noqa: BLE001
        return attach_interaction(payload, hinted)


def _status_payload(job_id: str, job: dict[str, Any]) -> dict[str, Any]:
    payload = decorate_job_tool_result(job)
    payload["jobId"] = job_id
    if job_id in _MOUNTED_JOB_IDS:
        from hydracept.mcp.presentation import job_presentation

        payload["presentation"] = job_presentation(payload, apps_supported=True)
    return _hydrate_result(payload)


class McpToolError(Exception):
    """MCP isError=true with a structured JSON envelope (never a bare exception string)."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        super().__init__(json.dumps(payload))


def _as_error_result(payload: dict[str, Any]) -> CallToolResult:
    """Return CallToolResult(isError=true) so the SDK does not wrap us as a generic ToolError."""
    body = dict(payload)
    body.setdefault("error", True)
    body["isError"] = True
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(body))],
        structured_content=body,
        is_error=True,
    )


def _tool_call(fn):
    try:
        return fn()
    except McpToolError as exc:
        return _as_error_result(exc.payload)
    except RunAdmissionError as exc:
        return _as_error_result(exc.as_tool_result())
    except HydraceptApiError as exc:
        return _as_error_result(exc.as_tool_result())
    except WorkspaceNotReadyError as exc:
        return _as_error_result(
            {
                "error": True,
                "code": getattr(exc, "code", None) or "WorkspaceNotReady",
                "message": str(exc),
                "nextAction": "python -m hydracept doctor --fix",
            }
        )
    except SmokeError as exc:
        return _as_error_result(
            {
                "error": True,
                "code": "SmokeFailed",
                "message": str(exc),
                "jobId": getattr(exc, "job_id", None),
                "receiptId": getattr(exc, "receipt_id", None),
            }
        )
    except ValueError as exc:
        return _as_error_result(
            {"error": True, "code": "INVALID_ARGUMENT", "message": str(exc)}
        )
    except httpx.RequestError as exc:
        return _as_error_result(
            {
                "error": True,
                "code": "TRANSPORT_ERROR",
                "message": str(exc),
                "retryable": True,
                "nextAction": "retry_after_backoff",
                "retryAfterSeconds": 2,
            }
        )
    except Exception as exc:  # noqa: BLE001
        # Public MCP tools must never collapse into an opaque SDK/bare exception.
        # Keep the error typed while leaving traceback detail to server logs.
        return _as_error_result(
            {
                "error": True,
                "code": "MCP_CLIENT_ERROR",
                "message": str(exc) or exc.__class__.__name__,
                "retryable": False,
            }
        )


def _client_for_run() -> HydraceptClient | dict[str, Any]:
    workspace, payload = ensure_workspace_for_run(_project_root())
    if workspace is None:
        return payload or {"status": "configuration_required"}
    return HydraceptClient(workspace.api_url, workspace.token)


def _anonymous_api_url() -> str:
    resolved = resolve_workspace(_project_root())
    if resolved is not None and resolved.api_url:
        return resolved.api_url.rstrip("/")
    return (os.environ.get("HYDRACEPT_API_URL") or DEFAULT_API).rstrip("/")


def _sanitize_public_payload(value: Any, *, key: str = "") -> Any:
    """Remove historical internal monetary sentinels from public MCP JSON."""
    if isinstance(value, dict):
        return {
            name: _sanitize_public_payload(item, key=str(name))
            for name, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_public_payload(item, key=key) for item in value]
    lowered = key.lower()
    if isinstance(value, (int, float)) and any(
        token in lowered for token in ("cost", "charge", "amount")
    ):
        if abs(float(value)) >= _INTERNAL_SENTINEL_COST_FLOOR:
            return None
    return value


def _receipt_summary(receipt: dict[str, Any]) -> dict[str, Any]:
    from hydracept.receipt_cost import present_receipt, micros_to_usd, surfaced_cost_micros

    presented = present_receipt(receipt)
    inner = presented.get("receipt") if isinstance(presented.get("receipt"), dict) else receipt
    pricing = inner.get("pricing") if isinstance(inner, dict) else {}
    charge = presented.get("customerCharge")
    if not isinstance(charge, dict) and isinstance(pricing, dict):
        nested = pricing.get("customerCharge")
        if nested is None and isinstance(pricing.get("charge"), dict):
            nested = pricing["charge"].get("customerCharge")
        if isinstance(nested, dict):
            charge = nested
    mode = pricing.get("mode") if isinstance(pricing, dict) else None
    charge_state = presented.get("chargeState") or "unavailable"
    return {
        "receiptId": inner.get("receiptId") or inner.get("id") if isinstance(inner, dict) else None,
        "jobId": inner.get("jobId") if isinstance(inner, dict) else None,
        "customerChargeUsd": presented.get("customerChargeUsd"),
        "customerOwedUsd": presented.get("customerChargeUsd"),
        "customerCharge": charge,
        "chargeState": charge_state,
        "billingMode": presented.get("billingMode"),
        "managedEquivalentChargeUsd": presented.get("managedEquivalentChargeUsd"),
        "estimatedCustomerChargeUsd": presented.get("estimatedCustomerChargeUsd"),
        "costUsd": micros_to_usd(surfaced_cost_micros(receipt)),
        "providerCostUsd": presented.get("providerCostUsd"),
        "providerCostBasis": "upstream-price-basis",
        "estimatedProviderCostUsd": presented.get("estimatedProviderCostUsd"),
        "customerChargeNote": (
            "customerChargeUsd is what this customer was charged; providerCostUsd is the "
            "upstream provider price basis the charge was computed from, not a retail price. "
            "Hydracept's procurement cost is never a customer field (ADR-022)."
        ),
        "pricing": {
            "customerCharge": charge,
            "customerChargeUsd": presented.get("customerChargeUsd"),
            "chargeState": charge_state,
            "mode": mode,
            "billingMode": str(mode or "").strip().lower() or None,
            "managedEquivalentChargeUsd": presented.get("managedEquivalentChargeUsd"),
            "providerCostUsd": presented.get("providerCostUsd"),
            "providerCostBasis": "upstream-price-basis",
            "estimatedProviderCostUsd": presented.get("estimatedProviderCostUsd"),
            "estimatedCustomerChargeUsd": presented.get("estimatedCustomerChargeUsd"),
            "providerUsage": pricing.get("providerUsage") if isinstance(pricing, dict) else None,
            "note": (
                "customerChargeUsd is the amount owed; providerCostUsd is a price basis, and "
                "providerUsage is provider-reported usage, not a substitute for either; "
                "managedEquivalentChargeUsd is provider cost + 6%, not a retail list price."
            ),
        },
        "durationMs": inner.get("durationMs") or inner.get("latencyMs") if isinstance(inner, dict) else None,
        "artifacts": inner.get("artifacts") or [] if isinstance(inner, dict) else [],
    }


def _unresolved_status_payload(message: str) -> dict[str, Any]:
    return {
        "configured": False,
        "ready": False,
        "workspaceState": "unconfigured",
        "workspaceRoot": "",
        "credentialPresent": False,
        "sessionPresent": False,
        "projectId": "",
        "environment": "",
        "apiUrl": "https://api.hydracept.com",
        "agentPackVersion": AGENT_PACK_VERSION,
        "agentPackInstalled": False,
        "installedHosts": [],
        "lastVerifiedAt": None,
        "mcp": {
            "bound": False,
            "transport": "stdio",
            "projectConfig": [],
            "reloadRequired": False,
            "hostedUrl": "https://api.hydracept.com/mcp",
            "useHostedWhen": (
                "No project checkout (ChatGPT, remote MCP clients, MCP Registry). "
                "In a git repo, use stdio after `python -m hydracept init`."
            ),
            "generation": "",
            "stdioCommand": "python -m hydracept mcp serve --workspace ${workspaceFolder}",
            "bindCommand": "python -m hydracept mcp bind",
            "note": message,
        },
        "nextSteps": [
            "Set HYDRACEPT_WORKSPACE in the MCP server env to ${workspaceFolder} (or an absolute checkout path).",
            "Run `python -m hydracept mcp bind` in the project checkout, then reload MCP.",
            "Run `python -m hydracept doctor --fix` if credentials are missing after workspace resolves.",
        ],
    }


@server.tool()
def hydracept_status(refresh: bool = False) -> dict[str, Any]:
    """Local workspace readiness. Set refresh=true for optional network verify."""
    def _run() -> dict[str, Any]:
        try:
            root = _project_root()
        except WorkspaceNotReadyError as exc:
            return _unresolved_status_payload(str(exc))
        payload = build_agent_status(root, refresh=refresh)
        from hydracept import __version__ as installed_client_version

        payload["runningMcpVersion"] = installed_client_version
        versions = payload.get("versions")
        if isinstance(versions, dict):
            versions["runningMcp"] = installed_client_version
        mcp = payload.get("mcp")
        if isinstance(mcp, dict):
            mcp.setdefault(
                "app",
                {
                    "uri": "ui://hydracept/app.html",
                    "tool": "hydracept_interaction_surface",
                    "note": "Built-in Hydracept App. hydracept panels list is for custom hosted panels only.",
                },
            )
            mcp.setdefault(
                "toolCatalogNote",
                "hydracept_ui_* tools are App iframe adapters. Agent-facing tools match GET /v1/agent-context mcp.tools.",
            )
        return payload

    # An advertised primitive must fail typed, never as an opaque SDK error.
    return _tool_call(_run)


@server.tool()
def hydracept_capabilities(key: str = "", query: str = "") -> dict[str, Any]:
    """List, find, or describe capabilities. Includes one-shot readiness facts. Text job_async descriptors may include features.deferredProcessing (50% off standard token rates). Works before workspace init (anonymous discovery)."""
    def _run() -> dict[str, Any]:
        api = _anonymous_api_url()
        resolved = resolve_workspace(_project_root())
        headers: dict[str, str] = {}
        if resolved is not None and resolved.token:
            headers["Authorization"] = f"Bearer {resolved.token}"
        if key.strip():
            requested = key.strip()
            # The API owns the descriptor projection; every MCP surface renders it verbatim.
            response = httpx.get(
                f"{api}/v1/capabilities/{requested}", headers=headers, timeout=30.0
            )
            if not response.is_success:
                from hydracept.capability_errors import (
                    UNKNOWN_CAPABILITY,
                    classify_capability_error,
                    fetch_catalog_summary,
                    unknown_capability_payload,
                )
                from hydracept.errors import parse_error_fields

                code, message = parse_error_fields(response.json() if response.content else {})
                if (
                    classify_capability_error(
                        status=response.status_code, code=code, message=message
                    )
                    == UNKNOWN_CAPABILITY
                ):
                    raise McpToolError(
                        unknown_capability_payload(
                            requested, fetch_catalog_summary(api, headers)
                        )
                    )
            raise_api_status(response)
            return response.json()
        if query.strip() and resolved is not None and resolved.token:
            response = httpx.post(
                f"{api}/v1/capabilities/resolve",
                headers=headers,
                json={"intent": query.strip(), "requirements": {}},
                timeout=30.0,
            )
            raise_api_status(response)
            payload = response.json()
            matches = payload.get("matches") if isinstance(payload, dict) else []
            if (not matches) and str((payload or {}).get("resolution") or "") in {
                "no_match_requestable",
                "no_match",
                "",
            }:
                from hydracept.cli.catalog_match import catalog_matches

                fallback = catalog_matches(query.strip(), api=api, headers=headers)
                if fallback:
                    payload = {
                        "resolution": "matched",
                        "matchSource": "catalog_fallback",
                        "matches": fallback,
                    }
                    matches = fallback
            if isinstance(payload, dict) and matches:
                from hydracept.cli.catalog_match import prefer_intent_matches

                payload = dict(payload)
                payload["matches"] = prefer_intent_matches(query.strip(), list(matches))
            return payload
        params = {"q": query.strip()} if query.strip() else {"view": "summary"}
        response = httpx.get(f"{api}/v1/capabilities", headers=headers, params=params, timeout=30.0)
        raise_api_status(response)
        return response.json()

    return _tool_call(_run)


@server.tool()
def resolve_capability(intent: str, requirements: dict[str, Any] | None = None) -> dict[str, Any]:
    """Determine whether Hydracept already provides a suitable capability. Does not spend money."""
    payload: dict[str, Any] = {"intent": intent}
    if requirements:
        payload["requirements"] = requirements
    return _tool_call(lambda: _client().resolve_capability(payload))


@server.tool()
def estimate_capability(
    capability_key: str = "",
    body: dict[str, Any] | None = None,
    capability: str = "",
    capabilityKey: str = "",
    input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """HTTP alias of hydracept_quote_capability. Same 0.3 retail quote (pricing.quote). 'input' is an alias for 'body'."""
    key = resolve_capability_key(
        capability_key=capability_key,
        capability=capability,
        capabilityKey=capabilityKey,
    )
    return hydracept_quote_capability(key, body, input=input)


def _capability_body(
    body: dict[str, Any] | None,
    input_value: dict[str, Any] | None,
) -> dict[str, Any]:
    """Accept ``input`` as an alias for ``body``; refuse ambiguous calls loudly.

    Agents reach for ``input`` because the job API nests capability fields under
    it. Silently ignoring one of the two would validate the wrong object and blame
    the capability schema.
    """
    alias = input_value if isinstance(input_value, dict) else None
    if body is not None and alias is not None:
        raise ValueError(
            "Pass either 'body' or 'input', not both. 'input' is an alias for 'body'."
        )
    return dict(body if body is not None else (alias or {}))


@server.tool()
def hydracept_quote_capability(
    capability_key: str = "",
    body: dict[str, Any] | None = None,
    capability: str = "",
    capabilityKey: str = "",
    input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST /v1/capabilities/{key}/quote — optional preview; does not reserve or charge funds. 'input' is an alias for 'body'."""
    key = resolve_capability_key(
        capability_key=capability_key,
        capability=capability,
        capabilityKey=capabilityKey,
    )

    def _run() -> dict[str, Any]:
        from hydracept.cli.run_input_coercion import InputValidationError, coerce_capability_input

        workspace = _execution_workspace()
        try:
            coerced = coerce_capability_input(key, _capability_body(body, input))
        except InputValidationError as exc:
            raise McpToolError(exc.to_payload()) from exc
        payload = merge_workspace_job_context(coerced, workspace)
        from hydracept.cli.image_canvas import preflight_image_canvas

        blocked = preflight_image_canvas(key, payload)
        if blocked is not None:
            return blocked
        quoted = HydraceptClient(workspace.api_url, workspace.token).quote_capability(
            key, payload
        )
        from hydracept.receipt_cost import present_quote

        return present_quote(quoted)

    result = _tool_call(_run)
    if isinstance(result, dict) and not result.get("error"):
        result.setdefault("nextAction", "omit_execution_quoteId_on_submit")
        result.setdefault(
            "note",
            "Retail preview only. Omit execution.quoteId on submit unless the job body is unchanged. "
            "This quoteId is not a commission quote from request_capability_quote. "
            "spending=none means this customer will not be billed.",
        )
    return result


@server.tool()
def hydracept_invoke(
    capability_key: str = "",
    body: dict[str, Any] | None = None,
    capability: str = "",
    capabilityKey: str = "",
    input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Invoke a synchronous capability (read-only domain/DNS and text). 'input' is an alias for 'body'."""
    key = resolve_capability_key(
        capability_key=capability_key,
        capability=capability,
        capabilityKey=capabilityKey,
    )

    def _run() -> dict[str, Any]:
        from hydracept.cli.run_input_coercion import InputValidationError, coerce_capability_input

        workspace = _execution_workspace()
        try:
            coerced = coerce_capability_input(key, _capability_body(body, input))
        except InputValidationError as exc:
            raise McpToolError(exc.to_payload()) from exc
        payload = merge_workspace_job_context(coerced, workspace)
        invoked = HydraceptClient(workspace.api_url, workspace.token).invoke_capability(
            key, payload
        )
        return _sanitize_public_payload(invoked)

    return _tool_call(_run)


@apps.tool(resource_uri=APP_URI)
def hydracept_run(
    capability_key: str = "",
    body: dict[str, Any] | None = None,
    wait: bool = True,
    timeout: float | None = None,
    max_cost: float | None = None,
    idempotency_key: str = "",
    out: str = "",
    capability: str = "",
    capabilityKey: str = "",
    input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Canonical run. Waits for terminal completion by default; pass wait=false for a continuation. 'input' is an alias for 'body'."""
    from hydracept.cli.run_facade import execute_run

    key = resolve_capability_key(
        capability_key=capability_key,
        capability=capability,
        capabilityKey=capabilityKey,
    )
    root = _project_root()

    def _run() -> dict[str, Any]:
        outcome = execute_run(
            root,
            key,
            _capability_body(body, input),
            wait=wait,
            timeout=timeout,
            max_cost=max_cost,
            idempotency_key=idempotency_key or None,
            out=Path(out) if out else None,
        )
        payload = _sanitize_public_payload(outcome.payload())
        if outcome.error is not None and outcome.result is None:
            raise McpToolError(payload)
        if outcome.exit_code and outcome.result is not None:
            raise McpToolError({**payload, "isError": True})
        status = str(payload.get("status") or "").lower()
        job_id = str(payload.get("jobId") or payload.get("executionId") or "")
        if out:
            payload["requestedOutputPath"] = out
            diagnostics = (
                payload.get("diagnostics")
                if isinstance(payload.get("diagnostics"), dict)
                else {}
            )
            for name in ("persistedOutputPath", "persistedMediaType", "persistedSha256"):
                value = diagnostics.get(name)
                if value:
                    payload[name] = value
            artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else []
            if not payload.get("persistedOutputPath"):
                for item in artifacts:
                    if isinstance(item, dict) and item.get("localPath"):
                        payload["persistedOutputPath"] = item["localPath"]
                        payload.setdefault("persistedMediaType", item.get("mediaType"))
                        payload.setdefault("persistedSha256", item.get("sha256"))
                        break
        if job_id and status in {"running", "queued", "pending", "submitted"}:
            payload["nextAction"] = "poll"
            payload["pollAfterSeconds"] = 2
            payload["continuation"] = {
                "tool": "hydracept_job_status",
                "arguments": {"job_id": job_id},
            }
            payload["requestedWait"] = bool(wait)
            payload["transportWaited"] = bool(wait)
            if wait:
                payload["waitNote"] = (
                    "The requested wait ended before the durable job became terminal; "
                    "continue with hydracept_job_status."
                )
            if out and not payload.get("persistedOutputPath"):
                from hydracept.cli.result_persistence import output_not_persisted_note

                # One helper owns this message; MCP only appends its own transport
                # hint so the two surfaces cannot disagree.
                payload["outputNote"] = (
                    f"{output_not_persisted_note(status=status)} "
                    "On success use hydracept_download_artifact with output_path to "
                    "persist the artifact."
                )
        if str(payload.get("status") or "").lower() in {"succeeded", "partial"}:
            # An ordinary successful run needs no human decision, so the App
            # interaction/presentation envelope is noise: keep the leading contract
            # (status, typedOutput/artifacts, pricing, jobId, receiptId, nextAction)
            # and leave the sealed receipt and provenance to hydracept_get_receipt
            # and hydracept_job_inspect.
            receipt = payload.get("receipt")
            if isinstance(receipt, dict):
                payload.setdefault("receiptId", receipt.get("receiptId") or receipt.get("id"))
            payload.setdefault(
                "nextAction",
                "download_artifacts" if payload.get("artifacts") else "stop",
            )
            return payload
        return _hydrate_result(payload, surface_for_job(payload.get("job") or payload))

    return _tool_call(_run)


@server.tool()
def request_capability_quote(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a non-binding capability implementation request. Humans must accept commission quotes. Do not pass commission quoteId as execution.quoteId."""
    def _run() -> dict[str, Any]:
        created = _client().create_capability_request(dict(body or {}))
        request_id = str(created.get("id") or "")
        if request_id:
            submitted = _client().submit_capability_request(request_id)
            created = {**created, **submitted}
        return created

    result = _tool_call(_run)
    if isinstance(result, dict) and not result.get("error"):
        result.setdefault("nextAction", "human_pays_commission_quote")
        result.setdefault(
            "note",
            "Commission request only. Humans pay. Never pass the commission quoteId as execution.quoteId.",
        )
    return result


@server.tool()
def get_capability_request_quote(request_id: str) -> dict[str, Any]:
    """Read the human-paid commission quote for a capability request.

    This quoteId is never an execution.quoteId.
    """

    def _run() -> dict[str, Any]:
        return _client().get_capability_request_quote(request_id)

    return _tool_call(_run)


def _submit_job_payload(
    capability_key: str,
    body: dict[str, Any] | None,
    idempotency_key: str,
) -> dict[str, Any]:
    workspace = _execution_workspace()
    payload = merge_workspace_job_context(dict(body or {}), workspace)
    if idempotency_key:
        payload.setdefault("idempotencyKey", idempotency_key)
    if not str(payload.get("idempotencyKey") or "").strip():
        from uuid import uuid4

        payload["idempotencyKey"] = f"job-{uuid4().hex}"
    submitted = HydraceptClient(workspace.api_url, workspace.token).submit_capability_job(
        capability_key, payload
    )
    return _hydrate_result(
        decorate_job_tool_result(submitted),
        surface_for_job(submitted if isinstance(submitted, dict) else {}),
    )


@apps.tool(resource_uri=APP_URI)
def hydracept_submit_job(
    capability_key: str = "",
    body: dict[str, Any] | None = None,
    idempotency_key: str = "",
    capability: str = "",
    capabilityKey: str = "",
    input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Submit a capability job. Omit quoteId; the API seals pricing at admission. Eligible durable text jobs use deferred processing at 50% of standard token rates. Returns nextAction. 'input' is an alias for 'body'."""
    key = resolve_capability_key(
        capability_key=capability_key,
        capability=capability,
        capabilityKey=capabilityKey,
    )
    return _tool_call(
        lambda: _submit_job_payload(key, _capability_body(body, input), idempotency_key)
    )


@apps.tool(resource_uri=APP_URI)
def hydracept_job_status(job_id: str = "", jobId: str = "") -> dict[str, Any]:
    """GET /v1/jobs/{jobId} once. If nextAction is poll, wait pollAfterSeconds and call again."""
    identifier = _first_nonempty(job_id, jobId)
    return _tool_call(lambda: _status_payload(identifier, _client().get_job(identifier)))


def _receipt_from_identifier(identifier: str) -> dict[str, Any]:
    """Resolve either the job/execution id or a receiptId emitted by Hydracept."""
    value = str(identifier or "").strip()
    if not value:
        raise ValueError("job_id or receipt_id is required")
    client = _client()
    try:
        receipt = client.get_job_receipt(value)
        if isinstance(receipt, dict):
            return receipt
    except HydraceptApiError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status != 404:
            raise

    jobs = client.list_jobs(limit=100)
    items = []
    if isinstance(jobs, dict):
        for candidate_key in ("jobs", "items", "results"):
            candidate = jobs.get(candidate_key)
            if isinstance(candidate, list):
                items = candidate
                break
    for item in items:
        if not isinstance(item, dict):
            continue
        job_id = str(item.get("jobId") or item.get("id") or item.get("executionId") or "")
        if not job_id:
            continue
        if str(item.get("receiptId") or "") == value:
            return client.get_job_receipt(job_id)
        try:
            receipt = client.get_job_receipt(job_id)
        except HydraceptApiError:
            continue
        if str(receipt.get("receiptId") or receipt.get("id") or "") == value:
            return receipt
    raise McpToolError(
        {
            "code": "RECEIPT_NOT_FOUND",
            "message": f"No receipt found for identifier {value}",
            "identifier": value,
        }
    )


@server.tool()
def hydracept_get_receipt(job_id: str = "", receipt_id: str = "", jobId: str = "", receiptId: str = "") -> dict[str, Any]:
    """Fetch a sealed receipt by job/execution id or by receiptId returned from a prior result."""
    identifier = _first_nonempty(receipt_id, receiptId, job_id, jobId)
    result = _tool_call(lambda: _receipt_from_identifier(identifier))
    if isinstance(result, CallToolResult):
        return result
    if isinstance(result, dict) and result.get("error"):
        return result
    return _receipt_summary(result)


@server.tool()
def hydracept_download_artifact(
    job_id: str,
    artifact_id: str = "",
    label: str = "",
    output_path: str = "",
    out: str = "",
    outputPath: str = "",
) -> dict[str, Any]:
    """Download an artifact into the workspace; out/output_path select the destination."""
    return _tool_call(
        lambda: _download_artifact(
            job_id,
            artifact_id,
            label,
            _artifact_output_alias(out=out, output_path=output_path, outputPath=outputPath),
        )
    )


def _artifact_output_alias(*, out: str, output_path: str, outputPath: str) -> str:
    requested = [
        value.strip()
        for value in (out, output_path, outputPath)
        if value.strip()
    ]
    if len(set(requested)) > 1:
        raise ValueError(
            "out, output_path, and outputPath must name the same destination when combined"
        )
    return requested[0] if requested else ""


def _suffix_for_media_type(media_type: str | None) -> str:
    normalized = str(media_type or "").split(";", 1)[0].strip().lower()
    exact = {
        "application/json": ".json",
        "text/plain": ".txt",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "audio/ogg": ".ogg",
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "model/gltf-binary": ".glb",
        "model/gltf+json": ".gltf",
    }
    if normalized in exact:
        return exact[normalized]
    if normalized.endswith("+json"):
        return ".json"
    return ".bin"


def _download_artifact(
    job_id: str,
    artifact_id: str,
    label: str,
    output_path: str,
) -> dict[str, Any]:
    workspace = require_ready_workspace(_project_root())
    resolved_id = artifact_id.strip()
    filename_hint = resolved_id
    media_type_hint = ""
    job: dict[str, Any] | None = None
    if not resolved_id:
        job = _client().get_job(job_id)
        if not isinstance(job, dict):
            job = {}
        if label.strip():
            artifacts = job.get("artifacts") if isinstance(job.get("artifacts"), list) else []
            needle = label.strip().lower().replace("_", "").replace("-", "")
            if needle.endswith(".png"):
                needle = needle[:-4]
            match = None
            for item in artifacts:
                if not isinstance(item, dict):
                    continue
                candidates = (
                    item.get("label"),
                    item.get("filename"),
                    item.get("sliceCellId"),
                )
                for candidate_value in candidates:
                    key = str(candidate_value or "").strip().lower().replace("_", "").replace("-", "")
                    if key.endswith(".png"):
                        key = key[:-4]
                    if key and key == needle:
                        match = item
                        break
                if match is not None:
                    break
            if match is None:
                raise ValueError(f"no artifact labeled {label!r} on job {job_id}")
            resolved_id = str(match.get("artifactId") or "")
            filename_hint = str(match.get("filename") or match.get("label") or resolved_id)
            media_type_hint = str(match.get("mediaType") or match.get("media_type") or "")
        else:
            primary = infer_primary_artifact_id(job) or ""
            if not primary:
                artifacts = job.get("artifacts") if isinstance(job.get("artifacts"), list) else []
                raise McpToolError(
                    {
                        "code": "ARTIFACT_SELECTION_REQUIRED",
                        "jobId": job_id,
                        "artifacts": artifacts,
                        "nextAction": "select_artifact",
                        "message": "Job has no primaryArtifactId; select an artifact explicitly.",
                    }
                )
            resolved_id = primary
            artifacts = job.get("artifacts") if isinstance(job.get("artifacts"), list) else []
            for item in artifacts:
                if isinstance(item, dict) and str(item.get("artifactId") or "") == resolved_id:
                    filename_hint = str(item.get("filename") or item.get("label") or resolved_id)
                    media_type_hint = str(item.get("mediaType") or item.get("media_type") or "")
                    break
    if not resolved_id:
        raise ValueError("artifact_id is required")
    if Path(filename_hint).suffix == "":
        fetched = job if isinstance(job, dict) else {}
        if not fetched:
            fetched = _client().get_job(job_id)
            if not isinstance(fetched, dict):
                fetched = {}
        artifacts = fetched.get("artifacts") if isinstance(fetched.get("artifacts"), list) else []
        for item in artifacts:
            if isinstance(item, dict) and str(item.get("artifactId") or "") == resolved_id:
                filename_hint = str(item.get("filename") or item.get("label") or resolved_id)
                media_type_hint = str(item.get("mediaType") or item.get("media_type") or media_type_hint)
                break
        if Path(filename_hint).suffix == "":
            filename_hint = f"{resolved_id}{_suffix_for_media_type(media_type_hint)}"
    target = finalize_single_artifact_path(
        resolve_artifact_output(
            _project_root(),
            output_path,
            Path(filename_hint).name,
            1,
            job_id=job_id,
        ),
        Path(filename_hint).name,
    )
    target.parent.mkdir(parents=True, exist_ok=True)

    url = f"{workspace.api_url}/v1/jobs/{job_id}/artifacts/{resolved_id}"
    with httpx.stream(
        "GET",
        url,
        headers={"Authorization": f"Bearer {workspace.token}"},
        timeout=120.0,
        follow_redirects=True,
    ) as response:
        raise_api_status(response)
        content_type = response.headers.get("content-type", "application/octet-stream")
        digest = hashlib.sha256()
        with target.open("wb") as handle:
            for chunk in response.iter_bytes():
                digest.update(chunk)
                handle.write(chunk)

    return {
        "jobId": job_id,
        "artifactId": resolved_id,
        "label": label.strip() or None,
        "filename": Path(filename_hint).name,
        "path": str(target),
        "mediaType": content_type.split(";")[0].strip(),
        "sha256": digest.hexdigest(),
        "message": f"Saved {Path(filename_hint).name} to {target}",
    }


@server.tool()
def hydracept_smoke(
    capability: str = "",
    capability_key: str = "",
    capabilityKey: str = "",
    prompt: str = DEFAULT_SMOKE_PROMPT,
    poll_seconds: int = 90,
    output_path: str = ".hydracept/demo/first-asset.png",
) -> dict[str, Any]:
    """Explicit managed-trial smoke. Downloads first artifact when available."""
    key = resolve_capability_key(
        capability_key=capability_key or capability or DEFAULT_SMOKE_CAPABILITY,
        capability=capability,
        capabilityKey=capabilityKey,
    )

    def _run() -> dict[str, Any]:
        result = run_smoke(
            _project_root(),
            capability=key,
            prompt=prompt,
            poll_seconds=poll_seconds,
        )
        receipt = result.receipt or {}
        artifacts: list[dict[str, Any]] = []
        if result.artifact_ids:
            downloaded = _download_artifact(
                result.job_id,
                result.artifact_ids[0],
                "",
                output_path,
            )
            artifacts.append(downloaded)
        summary = _receipt_summary(receipt) if receipt else {}
        payload = {
            "jobId": result.job_id,
            "state": result.status,
            "status": result.status,
            "artifacts": artifacts,
            "receiptId": summary.get("receiptId"),
            "pricing": summary.get("pricing"),
            "costUsd": summary.get("costUsd"),
            "durationMs": summary.get("durationMs"),
            "sha256Ok": result.sha256_ok,
            "transparencyOk": result.transparency_ok,
            "transparencyReport": result.transparency_report,
            "pricingOk": result.pricing_ok,
            "capabilityKey": capability,
        }
        json_payload = result.to_json()
        if json_payload.get("artifact"):
            payload["artifact"] = json_payload["artifact"]
        if json_payload.get("presentation"):
            payload["presentation"] = json_payload["presentation"]
        return _hydrate_result(payload, "artifact.review")

    return _tool_call(_run)


@server.tool()
def hydracept_pinned_run(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """POST /v1/inference/pinned — exact pin, scientific receipt. Standard processing by default. Opt in with processing=deferred on eligible OpenAI Responses pins (50% Flex). One logical model execution, no truncation rewrite, no Flex→Standard fallback. Pre-inference capacity 429s may retry."""
    def _run() -> dict[str, Any]:
        workspace = _execution_workspace()
        payload = merge_workspace_job_context(dict(body or {}), workspace)
        return HydraceptClient(workspace.api_url, workspace.token).create_pinned_inference(payload)

    return _tool_call(_run)


@server.tool()
def hydracept_pinned_bulk(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """POST /v1/inference/pinned/bulk — concurrent pinned items, one logical execution each."""
    def _run() -> dict[str, Any]:
        workspace = _execution_workspace()
        payload = merge_workspace_job_context(dict(body or {}), workspace)
        return HydraceptClient(workspace.api_url, workspace.token).create_pinned_inference_bulk(payload)

    return _tool_call(_run)


@server.tool()
def hydracept_pinned_get(receipt_id: str) -> dict[str, Any]:
    """GET /v1/inference/pinned/{receipt_id}."""
    return _tool_call(lambda: _client().get_pinned_receipt(receipt_id))


@server.tool()
def hydracept_pinned_bulk_get(bulk_id: str) -> dict[str, Any]:
    """GET /v1/inference/pinned/bulk/{bulk_id} once. If nextAction is poll, wait pollAfterSeconds and call again."""
    return _tool_call(lambda: _client().get_pinned_bulk(bulk_id))


@server.tool()
def hydracept_manifest_create(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """POST /v1/provenance/manifests — hash related pinned receipts into a run manifest."""
    return _tool_call(lambda: _client().create_run_manifest(dict(body or {})))


@server.tool()
def hydracept_manifest_verify(manifest_id: str) -> dict[str, Any]:
    """POST /v1/provenance/manifests/{manifest_id}/verify."""
    return _tool_call(lambda: _client().verify_run_manifest(manifest_id))


@server.tool()
def hydracept_lockfile_emit(receipt_id: str) -> dict[str, Any]:
    """GET /v1/provenance/lockfile?receipt_id= — AI lockfile from a pinned receipt."""
    return _tool_call(lambda: _client().get_lockfile(receipt_id))


@server.tool()
def hydracept_verify_lockfile(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """POST /v1/provenance/lockfile/verify. Prefer `python -m hydracept verify` for local hydracept.lock."""
    return _tool_call(lambda: _client().verify_lockfile(dict(body or {})))


register_project_tools(server, project_root_fn=_project_root, apps=apps)


_MAX_PREVIEW_BYTES = 2_000_000


def _artifact_bytes(job_id: str, artifact_id: str) -> tuple[bytes, str]:
    workspace = require_ready_workspace(_project_root())
    url = f"{workspace.api_url}/v1/jobs/{job_id}/artifacts/{artifact_id}"
    with httpx.stream(
        "GET",
        url,
        headers={"Authorization": f"Bearer {workspace.token}"},
        timeout=120.0,
        follow_redirects=True,
    ) as response:
        raise_api_status(response)
        content_type = response.headers.get("content-type", "application/octet-stream")
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > _MAX_PREVIEW_BYTES:
                raise McpToolError(
                    {
                        "code": "PREVIEW_TOO_LARGE",
                        "message": f"Preview exceeds {_MAX_PREVIEW_BYTES} bytes",
                        "jobId": job_id,
                        "artifactId": artifact_id,
                    }
                )
            chunks.append(chunk)
    return b"".join(chunks), content_type.split(";")[0].strip()


_APP_ONLY_META = {"ui": {"visibility": ["app"]}}


def _normalize_job_approve_body(body: dict[str, Any] | None) -> dict[str, Any] | None:
    """Map hydrated approval projection keys onto POST /v1/jobs/{id}/approve."""
    if not isinstance(body, dict):
        return body
    quote = body.get("quote") if isinstance(body.get("quote"), dict) else {}
    prompt = body.get("prompt") if isinstance(body.get("prompt"), dict) else {}
    merged = {**quote, **prompt, **{k: v for k, v in body.items() if k not in {"quote", "prompt"}}}
    out: dict[str, Any] = {}
    if merged.get("domain"):
        out["domain"] = merged["domain"]
    if isinstance(merged.get("registrant"), dict):
        out["registrant"] = merged["registrant"]
    if merged.get("firstYearPriceUsd") is not None:
        out["firstYearPriceUsd"] = merged["firstYearPriceUsd"]
    if merged.get("renewalPriceUsd") is not None:
        out["renewalPriceUsd"] = merged["renewalPriceUsd"]
    version = merged.get("porkbunAgreementVersion") or merged.get("agreementVersion")
    if version:
        out["porkbunAgreementVersion"] = version
    if merged.get("agreeToPorkbunRegistrationAgreement") is not None:
        out["agreeToPorkbunRegistrationAgreement"] = merged["agreeToPorkbunRegistrationAgreement"]
    elif out.get("domain") or out.get("firstYearPriceUsd") is not None:
        out["agreeToPorkbunRegistrationAgreement"] = True
    if merged.get("authorizedMaxAmount") is not None:
        out["authorizedMaxAmount"] = merged["authorizedMaxAmount"]
    if merged.get("recipientPorkbunUsername"):
        out["recipientPorkbunUsername"] = merged["recipientPorkbunUsername"]
    return out or None


@server.tool(meta=_APP_ONLY_META)
def hydracept_ui_submit_job(
    capability_key: str = "image.generate.v1",
    body: dict[str, Any] | None = None,
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Panel submit. Same execution as hydracept_submit_job; no App remount (no resourceUri)."""
    return _tool_call(lambda: _submit_job_payload(capability_key, body, idempotency_key))


@server.tool(meta=_APP_ONLY_META)
def hydracept_ui_poll_job(job_id: str) -> dict[str, Any]:
    """Panel job poll. Same projection as hydracept_job_status; proves the App is mounted."""
    _MOUNTED_JOB_IDS.add(job_id)
    return _tool_call(lambda: _status_payload(job_id, _client().get_job(job_id)))


@server.tool(meta=_APP_ONLY_META)
def hydracept_ui_download_artifact(
    jobId: str = "",
    artifactId: str = "",
    job_id: str = "",
    artifact_id: str = "",
    output_path: str = "",
) -> dict[str, Any]:
    """Panel workspace save. Iframe has no API token; server uses the workspace client."""
    resolved_job = (jobId or job_id).strip()
    resolved_artifact = (artifactId or artifact_id).strip()
    dest = output_path.strip()

    def _run() -> dict[str, Any]:
        artifact = resolved_artifact
        if resolved_job and not artifact:
            job = _client().get_job(resolved_job)
            if not isinstance(job, dict):
                job = {}
            artifact = infer_preview_artifact_id(job) or infer_primary_artifact_id(job) or ""
        return _download_artifact(resolved_job, artifact, "", dest)

    return _tool_call(_run)


@server.tool(meta=_APP_ONLY_META)
def hydracept_ui_artifact_preview(jobId: str = "", artifactId: str = "", job_id: str = "", artifact_id: str = "") -> dict[str, Any]:
    """App-only bounded media preview. Server uses the workspace client; iframe has no API token."""
    import base64

    resolved_job = (jobId or job_id).strip()
    resolved_artifact = (artifactId or artifact_id).strip()

    def _run() -> dict[str, Any]:
        if not resolved_job:
            raise ValueError("jobId is required")
        artifact = resolved_artifact
        if not artifact:
            job = _client().get_job(resolved_job)
            if not isinstance(job, dict):
                job = {}
            artifact = infer_preview_artifact_id(job) or infer_primary_artifact_id(job) or ""
        if not artifact:
            raise ValueError("jobId and artifactId are required")
        data, media_type = _artifact_bytes(resolved_job, artifact)
        if not (media_type.startswith("image/") or media_type.startswith("audio/")):
            return {
                "jobId": resolved_job,
                "artifactId": artifact,
                "mediaType": media_type,
                "unsupported": True,
                "message": "This panel previews images and audio. Download or Use still work for other media.",
            }
        return {
            "jobId": resolved_job,
            "artifactId": artifact,
            "mediaType": media_type,
            "byteLength": len(data),
            "bytesBase64": base64.b64encode(data).decode("ascii"),
        }

    return _tool_call(_run)


@server.tool(meta=_APP_ONLY_META)
def hydracept_ui_quote(
    capability_key: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """App-only quote adapter. Same primitive as hydracept_quote_capability."""
    return hydracept_quote_capability(capability_key, body)


@server.tool(meta=_APP_ONLY_META)
def hydracept_ui_run(
    capability_key: str,
    body: dict[str, Any] | None = None,
    max_cost: float | None = None,
    idempotency_key: str = "",
) -> dict[str, Any]:
    """App-only run adapter. Uses the existing run façade (invoke vs jobs from executionModes)."""
    from hydracept.cli.run_facade import execute_run
    from hydracept.mcp.interaction_hydration import attach_hydrated_interaction

    def _run() -> dict[str, Any]:
        raw = dict(body or {})
        outcome = execute_run(
            _project_root(),
            capability_key,
            raw,
            wait=False,
            persist=False,
            max_cost=max_cost,
            idempotency_key=idempotency_key or None,
        )
        payload = _sanitize_public_payload(outcome.payload())
        if outcome.error is not None:
            raise McpToolError(payload)
        return attach_hydrated_interaction(
            payload,
            project_root=_project_root(),
            client=_client,
        )

    return _tool_call(_run)


@server.tool(meta=_APP_ONLY_META)
def hydracept_ui_connect_project(
    displayName: str = "",
    environment: str = "",
    project_name: str = "",
) -> dict[str, Any]:
    """App-only init adapter. Canonical init owns binding writes."""
    from hydracept.cli.init_resolver import run_init
    from hydracept.mcp.interaction_hydration import attach_hydrated_interaction

    def _run() -> dict[str, Any]:
        result = run_init(
            _project_root(),
            apply=True,
            yes=True,
            json_output=True,
            wait=False,
            project_name=(displayName or project_name or None) or None,
            environment=environment or None,
        )
        payload = dict(result.payload or {})
        payload.setdefault("exitCode", result.exit_code)
        return attach_hydrated_interaction(
            payload,
            "project.connect",
            {
                "displayName": displayName or project_name,
                "environment": environment,
            },
            project_root=_project_root(),
            client=None,
        )

    return _tool_call(_run)


@server.tool(meta=_APP_ONLY_META)
def hydracept_ui_connection_recheck(capability_key: str = "") -> dict[str, Any]:
    """Re-read authoritative connection/runnability. Never accepts secrets."""
    from hydracept.mcp.interaction_hydration import hydrate_interaction_surface

    def _run() -> dict[str, Any]:
        return hydrate_interaction_surface(
            "connection.resolve",
            {"capabilityKey": capability_key},
            project_root=_project_root(),
            client=_client,
        )

    return _tool_call(_run)


@server.tool(meta=_APP_ONLY_META)
def hydracept_ui_approve_job(
    job_id: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Exact POST /v1/jobs/{id}/approve. For awaiting_approval human gates only."""
    from hydracept.mcp.interaction_hydration import attach_hydrated_interaction

    def _run() -> dict[str, Any]:
        job = _client().approve_job(job_id, _normalize_job_approve_body(body))
        payload = job if isinstance(job, dict) else {"jobId": job_id}
        payload.setdefault("jobId", job_id)
        return attach_hydrated_interaction(
            payload,
            project_root=_project_root(),
            client=_client,
        )

    return _tool_call(_run)


@server.tool(meta=_APP_ONLY_META)
def hydracept_ui_reject_job(job_id: str) -> dict[str, Any]:
    """Exact POST /v1/jobs/{id}/reject."""
    from hydracept.mcp.interaction_hydration import attach_hydrated_interaction

    def _run() -> dict[str, Any]:
        job = _client().reject_job(job_id)
        payload = job if isinstance(job, dict) else {"jobId": job_id}
        payload.setdefault("jobId", job_id)
        return attach_hydrated_interaction(
            payload,
            project_root=_project_root(),
            client=_client,
        )

    return _tool_call(_run)


@server.tool(meta=_APP_ONLY_META)
def hydracept_ui_select_variant(job_id: str, artifact_id: str) -> dict[str, Any]:
    """Exact POST /v1/jobs/{id}/variants/select."""
    from hydracept.mcp.interaction_hydration import attach_hydrated_interaction

    def _run() -> dict[str, Any]:
        job = _client().select_job_variant(job_id, artifact_id)
        payload = job if isinstance(job, dict) else {"jobId": job_id}
        payload.setdefault("jobId", job_id)
        return attach_hydrated_interaction(
            payload,
            "artifact.review",
            project_root=_project_root(),
            client=_client,
        )

    return _tool_call(_run)


@server.tool(meta=_APP_ONLY_META)
def hydracept_ui_cancel_job(job_id: str) -> dict[str, Any]:
    """Explicit job cancel. Stop watching must not call this."""
    from hydracept.mcp.interaction_hydration import attach_hydrated_interaction

    def _run() -> dict[str, Any]:
        job = _client().cancel_job(job_id)
        payload = job if isinstance(job, dict) else {"jobId": job_id}
        payload.setdefault("jobId", job_id)
        return attach_hydrated_interaction(
            payload,
            project_root=_project_root(),
            client=_client,
        )

    return _tool_call(_run)


@server.tool(meta=_APP_ONLY_META)
def hydracept_ui_promote(path: str) -> dict[str, Any]:
    """Project-local apply_surfaces(path). Cloud never writes the repository."""
    from hydracept.mcp.project_mcp import ProjectMcpService

    def _run() -> dict[str, Any]:
        target = str(path or "").strip()
        if not target:
            raise ValueError("path is required")
        result = ProjectMcpService(_project_root()).apply_surfaces(target)
        result.setdefault(
            "note",
            "Hydracept cloud does not write this repository. Promotion runs through the project-local Hydracept authority.",
        )
        return result

    return _tool_call(_run)


# Apps tools/resources are collected on `apps` first; the SDK binds them at apply time.
server._apply_extension(apps)
server._install_extension_interceptor()


def serve_stdio() -> None:
    try:
        import os

        from hydracept.mcp.runtime_binding import attest_runtime_binding
        from hydracept.mcp.workspace_locator import resolve_mcp_workspace

        root = _WORKSPACE_ROOT or resolve_mcp_workspace(None)
        env = dict(os.environ)
        if not str(env.get("HYDRACEPT_MCP_GENERATION") or "").strip():
            from hydracept.cli.mcp_bind import binding_generation, stdio_args

            env["HYDRACEPT_MCP_GENERATION"] = binding_generation(root, stdio_args(root))
        attest_runtime_binding(root, source="stdio", env=env)
    except Exception:  # noqa: BLE001 — status still works if the lease cannot be written
        pass
    server.run(transport="stdio")


if __name__ == "__main__":
    serve_stdio()
