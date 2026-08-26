"""Stdio MCP server — capability jobs plus project-surface tools (ADR-021, ADR-026)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import httpx
from mcp.server.mcpserver.server import MCPServer

from hydracept import HydraceptClient
from hydracept.errors import HydraceptApiError, raise_api_status
from hydracept.cli.agent_status import build_agent_status
from hydracept.cli.smoke_runner import DEFAULT_SMOKE_CAPABILITY, DEFAULT_SMOKE_PROMPT, run_smoke
from hydracept.cli.job_context import merge_workspace_job_context
from hydracept.cli.workspace import require_ready_workspace
from hydracept.job_wait import decorate_job_tool_result
from hydracept.mcp.icons import hydracept_mcp_icons
from hydracept.mcp.register_project_tools import register_project_tools

_WORKSPACE_ROOT: Path | None = None
_WALK_UP_MAX = 8


def configure_workspace(root: Path | str | None) -> None:
    global _WORKSPACE_ROOT
    _WORKSPACE_ROOT = Path(root).resolve() if root else None


def _bounded_walk_up(start: Path) -> Path:
    current = start.resolve()
    for _ in range(_WALK_UP_MAX):
        if (current / ".hydracept" / "project.json").is_file():
            return current
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return start.resolve()


server = MCPServer(
    name="hydracept",
    title="Hydracept",
    website_url="https://hydracept.com",
    icons=hydracept_mcp_icons(),
    instructions=(
        "Hydracept public capability jobs, pinned execution, and project surfaces. "
        "Credentials resolve from workspace only. "
        "Project surface tools require cwd to be the game checkout."
    ),
)


def _project_root() -> Path:
    if _WORKSPACE_ROOT is not None:
        return _WORKSPACE_ROOT
    return _bounded_walk_up(Path.cwd())


def _client() -> HydraceptClient:
    workspace = require_ready_workspace(_project_root())
    return HydraceptClient(workspace.api_url, workspace.token)


def _tool_call(fn):
    try:
        return fn()
    except HydraceptApiError as exc:
        return exc.as_tool_result()
    except ValueError as exc:
        return {"error": True, "code": "INVALID_ARGUMENT", "message": str(exc)}


def _receipt_summary(receipt: dict[str, Any]) -> dict[str, Any]:
    pricing = receipt.get("pricing") or {}
    charge = (pricing.get("charge") or {}).get("customerCharge") or {}
    quote = (pricing.get("quote") or {}).get("customerTotal") or {}
    micros = charge.get("amountMicros")
    if micros is None:
        micros = quote.get("amountMicros")
    cost_usd = None
    if micros is not None:
        cost_usd = int(micros) / 1_000_000
    return {
        "receiptId": receipt.get("receiptId") or receipt.get("id"),
        "jobId": receipt.get("jobId"),
        "pricing": pricing or None,
        "costUsd": cost_usd,
        "durationMs": receipt.get("durationMs") or receipt.get("latencyMs"),
        "artifacts": receipt.get("artifacts") or [],
    }


@server.tool()
def hydracept_status(refresh: bool = False) -> dict[str, Any]:
    """Local workspace readiness. Set refresh=true for optional network verify."""
    return build_agent_status(_project_root(), refresh=refresh)


@server.tool()
def hydracept_capabilities(key: str = "") -> dict[str, Any]:
    """List capabilities or describe one when key is provided."""
    def _run() -> dict[str, Any]:
        client = _client()
        if key.strip():
            return client.describe_capability(key.strip())
        return client.capabilities()

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
    capability_key: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """HTTP alias of hydracept_quote_capability. Same 0.3 retail quote (pricing.quote)."""
    return hydracept_quote_capability(capability_key, body)


@server.tool()
def hydracept_quote_capability(
    capability_key: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST /v1/capabilities/{key}/quote — optional preview; does not reserve or charge funds."""
    result = _tool_call(lambda: _client().quote_capability(capability_key, dict(body or {})))
    if isinstance(result, dict) and not result.get("error"):
        result.setdefault("nextAction", "omit_execution_quoteId_on_submit")
        result.setdefault(
            "note",
            "Retail preview only. Omit execution.quoteId on submit unless the job body is unchanged. "
            "This quoteId is not a commission quote from request_capability_quote.",
        )
    return result


@server.tool()
def hydracept_invoke(
    capability_key: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Invoke a synchronous capability (read-only domain/DNS and text)."""
    workspace = require_ready_workspace(_project_root())
    payload = merge_workspace_job_context(dict(body or {}), workspace)
    return _tool_call(
        lambda: HydraceptClient(workspace.api_url, workspace.token).invoke_capability(
            capability_key, payload
        )
    )


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
def hydracept_submit_job(
    capability_key: str,
    body: dict[str, Any] | None = None,
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Submit a capability job. Omit quoteId; the API seals pricing at admission. Returns nextAction."""
    workspace = require_ready_workspace(_project_root())
    payload = merge_workspace_job_context(dict(body or {}), workspace)
    if idempotency_key:
        payload.setdefault("idempotencyKey", idempotency_key)
    if not str(payload.get("idempotencyKey") or "").strip():
        from uuid import uuid4

        payload["idempotencyKey"] = f"job-{uuid4().hex}"
    result = _tool_call(
        lambda: HydraceptClient(workspace.api_url, workspace.token).submit_capability_job(
            capability_key, payload
        )
    )
    if isinstance(result, dict) and not result.get("error"):
        return decorate_job_tool_result(result)
    return result


@server.tool()
def hydracept_job_status(job_id: str) -> dict[str, Any]:
    """GET /v1/jobs/{jobId} once. If nextAction is poll, wait pollAfterSeconds and call again."""
    return _tool_call(lambda: decorate_job_tool_result(_client().get_job(job_id)))


@server.tool()
def hydracept_get_receipt(job_id: str) -> dict[str, Any]:
    """Fetch sealed receipt summary for a job."""
    result = _tool_call(lambda: _client().get_job_receipt(job_id))
    if isinstance(result, dict) and result.get("error"):
        return result
    return _receipt_summary(result)


@server.tool()
def hydracept_download_artifact(
    job_id: str,
    artifact_id: str = "",
    label: str = "",
    output_path: str = "",
) -> dict[str, Any]:
    """Download a job artifact by id or sheet label into the workspace."""
    return _tool_call(lambda: _download_artifact(job_id, artifact_id, label, output_path))


def _download_artifact(
    job_id: str,
    artifact_id: str,
    label: str,
    output_path: str,
) -> dict[str, Any]:
    workspace = require_ready_workspace(_project_root())
    resolved_id = artifact_id.strip()
    filename_hint = resolved_id
    if not resolved_id:
        if not label.strip():
            raise ValueError("artifact_id or label is required")
        job = _client().get_job(job_id)
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
            for value in candidates:
                key = str(value or "").strip().lower().replace("_", "").replace("-", "")
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
    if not resolved_id:
        raise ValueError("artifact_id is required")
    target = (
        Path(output_path)
        if output_path
        else _project_root() / ".hydracept" / "artifacts" / Path(filename_hint).name
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
        "path": str(target),
        "mediaType": content_type.split(";")[0].strip(),
        "sha256": digest.hexdigest(),
    }


@server.tool()
def hydracept_smoke(
    capability: str = DEFAULT_SMOKE_CAPABILITY,
    prompt: str = DEFAULT_SMOKE_PROMPT,
    poll_seconds: int = 90,
    output_path: str = ".hydracept/demo/first-asset.png",
) -> dict[str, Any]:
    """Explicit managed-trial smoke. Downloads first artifact when available."""
    def _run() -> dict[str, Any]:
        result = run_smoke(
            _project_root(),
            capability=capability,
            prompt=prompt,
            poll_seconds=poll_seconds,
        )
        receipt = result.receipt or {}
        artifacts: list[dict[str, Any]] = []
        if result.artifact_ids:
            downloaded = hydracept_download_artifact(
                result.job_id,
                result.artifact_ids[0],
                output_path=output_path,
            )
            artifacts.append(downloaded)
        summary = _receipt_summary(receipt) if receipt else {}
        return {
            "jobId": result.job_id,
            "state": result.status,
            "artifacts": artifacts,
            "receiptId": summary.get("receiptId"),
            "pricing": summary.get("pricing"),
            "costUsd": summary.get("costUsd"),
            "durationMs": summary.get("durationMs"),
            "sha256Ok": result.sha256_ok,
            "transparencyOk": result.transparency_ok,
            "pricingOk": result.pricing_ok,
        }

    return _tool_call(_run)


@server.tool()
def hydracept_pinned_run(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """POST /v1/inference/pinned — exact pin, scientific receipt. RIP; no rewrite or fallback."""
    workspace = require_ready_workspace(_project_root())
    payload = merge_workspace_job_context(dict(body or {}), workspace)
    return _tool_call(
        lambda: HydraceptClient(workspace.api_url, workspace.token).create_pinned_inference(payload)
    )


@server.tool()
def hydracept_pinned_get(receipt_id: str) -> dict[str, Any]:
    """GET /v1/inference/pinned/{receipt_id}."""
    return _tool_call(lambda: _client().get_pinned_receipt(receipt_id))


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


register_project_tools(server, project_root_fn=_project_root)


def serve_stdio() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    serve_stdio()
