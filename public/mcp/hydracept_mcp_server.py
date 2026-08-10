"""Hydracept MCP server — bootstrap orchestration + public capability tools.

Run (stdio): python -m hydracept_mcp_server
Env: HYDRACEPT_API_URL, HYDRACEPT_API_KEY
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

API_URL = os.environ.get("HYDRACEPT_API_URL", "https://api.hydracept.com").rstrip("/")
API_KEY = os.environ.get("HYDRACEPT_API_KEY", "")

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


def plan_connections(capabilities: list[str], account_class: str = "individual") -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{API_URL}/v1/connections/onboarding/plan",
            headers=_headers(),
            json={"capabilities": capabilities, "accountClass": account_class},
        )
        resp.raise_for_status()
        return resp.json()


def start_provider_connection(
    provider: str,
    secret: str,
    *,
    bootstrap_mode: str = "manual_api_key",
) -> dict[str, Any]:
    """Complete a connection with a user-supplied inference credential.

    For local_admin_bootstrap, the CLI performs management API calls; MCP only
    uploads the resulting inference credential.
    """
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{API_URL}/v1/connections",
            headers=_headers(),
            json={
                "provider": provider,
                "secret": secret,
                "bootstrapMode": bootstrap_mode,
                "autoBind": True,
            },
        )
        resp.raise_for_status()
        return resp.json()


def get_connection_status(session_id: str | None = None) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        if session_id:
            resp = client.get(
                f"{API_URL}/v1/connections/onboarding/sessions/{session_id}/result",
                headers=_headers(),
            )
        else:
            resp = client.get(f"{API_URL}/v1/connections", headers=_headers())
        resp.raise_for_status()
        return resp.json()


def list_capabilities() -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(f"{API_URL}/v1/capabilities", headers=_headers())
        resp.raise_for_status()
        return resp.json()


def describe_capability(key: str) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(f"{API_URL}/v1/capabilities/{key}", headers=_headers())
        resp.raise_for_status()
        return resp.json()


def submit_job(capability_key: str, body: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=60.0) as client:
        resp = client.post(
            f"{API_URL}/v1/capabilities/{capability_key}/jobs",
            headers=_headers(),
            json=body,
        )
        resp.raise_for_status()
        return resp.json()


def get_job(job_id: str) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(f"{API_URL}/v1/jobs/{job_id}", headers=_headers())
        resp.raise_for_status()
        return resp.json()


def get_receipt(job_id: str) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(f"{API_URL}/v1/jobs/{job_id}/receipt", headers=_headers())
        resp.raise_for_status()
        return resp.json()


TOOL_HANDLERS = {
    "plan_connections": lambda args: plan_connections(
        list(args.get("capabilities") or []),
        str(args.get("accountClass") or "individual"),
    ),
    "start_provider_connection": lambda args: start_provider_connection(
        str(args["provider"]),
        str(args["secret"]),
        bootstrap_mode=str(args.get("bootstrapMode") or "manual_api_key"),
    ),
    "get_connection_status": lambda args: get_connection_status(args.get("sessionId")),
    "list_capabilities": lambda args: list_capabilities(),
    "describe_capability": lambda args: describe_capability(str(args["key"])),
    "submit_job": lambda args: submit_job(str(args["capabilityKey"]), dict(args.get("body") or {})),
    "get_job": lambda args: get_job(str(args["jobId"])),
    "get_receipt": lambda args: get_receipt(str(args["jobId"])),
}


def dispatch_tool(name: str, arguments: dict[str, Any] | None = None) -> str:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        raise KeyError(f"Unknown MCP tool: {name}")
    return json.dumps(handler(arguments or {}), indent=2)


if __name__ == "__main__":
    print(json.dumps({"tools": MCP_TOOLS, "api": API_URL}, indent=2))
