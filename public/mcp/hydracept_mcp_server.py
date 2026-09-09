"""Deprecated public MCP shim. Do not paste secrets here.

Use `python -m hydracept init --apply --yes --json` then
`python -m hydracept mcp serve` (stdio). Hosted MCP is for clients with no checkout.

This module stays on the publication allowlist so old installs fail closed instead of
asking agents to paste provider keys.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

API_URL = os.environ.get("HYDRACEPT_API_URL", "https://api.hydracept.com").rstrip("/")
API_KEY = os.environ.get("HYDRACEPT_API_KEY", "")

USE_STDIO = {
    "error": True,
    "code": "USE_STDIO_MCP",
    "message": (
        "public/mcp/hydracept_mcp_server.py is deprecated. "
        "Run python -m hydracept mcp serve after python -m hydracept init --apply --yes --json."
    ),
    "nextAction": "python -m hydracept mcp serve",
}

USE_INIT_OR_STUDIO = {
    "error": True,
    "code": "USE_INIT_OR_STUDIO",
    "message": (
        "Do not paste provider secrets into MCP. "
        "Run python -m hydracept init --apply --yes --json or connect a provider in Studio."
    ),
    "nextAction": "python -m hydracept init --apply --yes --json",
}

MCP_TOOLS = [
    "plan_connections",
    "start_provider_connection",
    "get_connection_status",
    "list_capabilities",
    "describe_capability",
    "submit_job",
    "get_job",
    "get_receipt",
]


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }


def _http_json(resp: httpx.Response) -> dict[str, Any]:
    try:
        body: Any = resp.json()
    except Exception:
        body = {"message": (resp.text or "")[:500]}
    if resp.is_error:
        if isinstance(body, dict):
            detail = body.get("detail")
            if isinstance(detail, dict):
                return {"error": True, **detail, **USE_STDIO}
            if body.get("code"):
                return {"error": True, **body, "useInstead": USE_STDIO["nextAction"]}
        return {
            "error": True,
            "code": f"HTTP_{resp.status_code}",
            "message": str(body),
            "useInstead": USE_STDIO["nextAction"],
        }
    if isinstance(body, dict):
        body.setdefault("deprecated", True)
        body.setdefault("useInstead", USE_STDIO["nextAction"])
        return body
    return {"data": body, "deprecated": True, "useInstead": USE_STDIO["nextAction"]}


def plan_connections(capabilities: list[str], account_class: str = "individual") -> dict[str, Any]:
    return {**USE_STDIO, "legacyTool": "plan_connections"}


def start_provider_connection(
    provider: str,
    secret: str = "",
    *,
    bootstrap_mode: str = "manual_api_key",
) -> dict[str, Any]:
    """Refuse secrets. Connections belong in init or Studio."""
    return {**USE_INIT_OR_STUDIO, "legacyTool": "start_provider_connection"}


def get_connection_status(session_id: str | None = None) -> dict[str, Any]:
    return {**USE_STDIO, "legacyTool": "get_connection_status"}


def list_capabilities() -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(f"{API_URL}/v1/capabilities", headers=_headers())
        return _http_json(resp)


def describe_capability(key: str) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(f"{API_URL}/v1/capabilities/{key}", headers=_headers())
        return _http_json(resp)


def submit_job(capability_key: str, body: dict[str, Any]) -> dict[str, Any]:
    return {**USE_STDIO, "legacyTool": "submit_job", "useTool": "hydracept_submit_job"}


def get_job(job_id: str) -> dict[str, Any]:
    return {**USE_STDIO, "legacyTool": "get_job", "useTool": "hydracept_job_status"}


def get_receipt(job_id: str) -> dict[str, Any]:
    return {**USE_STDIO, "legacyTool": "get_receipt", "useTool": "hydracept_get_receipt"}


TOOL_HANDLERS = {
    "plan_connections": lambda args: plan_connections(
        list(args.get("capabilities") or []),
        str(args.get("accountClass") or "individual"),
    ),
    "start_provider_connection": lambda args: start_provider_connection(
        str(args.get("provider") or ""),
        str(args.get("secret") or ""),
        bootstrap_mode=str(args.get("bootstrapMode") or "manual_api_key"),
    ),
    "get_connection_status": lambda args: get_connection_status(args.get("sessionId")),
    "list_capabilities": lambda args: list_capabilities(),
    "describe_capability": lambda args: describe_capability(str(args.get("key") or "")),
    "submit_job": lambda args: submit_job(
        str(args.get("capabilityKey") or ""), dict(args.get("body") or {})
    ),
    "get_job": lambda args: get_job(str(args.get("jobId") or "")),
    "get_receipt": lambda args: get_receipt(str(args.get("jobId") or "")),
}


def dispatch_tool(name: str, arguments: dict[str, Any] | None = None) -> str:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return json.dumps({**USE_STDIO, "code": "UNKNOWN_TOOL", "legacyTool": name}, indent=2)
    return json.dumps(handler(arguments or {}), indent=2)


if __name__ == "__main__":
    print(json.dumps({"tools": MCP_TOOLS, "api": API_URL, **USE_STDIO}, indent=2))
