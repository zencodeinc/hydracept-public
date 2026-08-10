"""Hydracept Python client — public API surface."""

from __future__ import annotations

import json
from typing import Any, Iterator

import httpx


class HydraceptClient:
    def __init__(self, base_url: str, token: str, *, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._timeout = timeout

    def _get(self, path: str) -> dict[str, Any]:
        response = httpx.get(
            f"{self.base_url}{path}",
            headers=self._headers,
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}{path}",
            headers=self._headers,
            json=body,
            timeout=self._timeout,
        )
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    def capabilities(self) -> dict[str, Any]:
        return self._get("/v1/capabilities")

    def describe_capability(self, key: str) -> dict[str, Any]:
        return self._get(f"/v1/capabilities/{key}")

    def invoke_capability(self, key: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._post(f"/v1/capabilities/{key}/invoke", body)

    def submit_capability_job(self, key: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._post(f"/v1/capabilities/{key}/jobs", body)

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self._get(f"/v1/jobs/{job_id}")

    def get_job_receipt(self, job_id: str) -> dict[str, Any]:
        return self._get(f"/v1/jobs/{job_id}/receipt")

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        return self._post(f"/v1/jobs/{job_id}/cancel")

    def agent_context(self) -> dict[str, Any]:
        return self._get("/v1/agent-context")

    def diagnostics_session(self) -> dict[str, Any]:
        return self._get("/v1/diagnostics/session")

    def policy_dry_run(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/policy-evaluations", body)


def iter_invocation_events(
    base_url: str,
    token: str,
    execution_id: str,
    *,
    last_event_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Maintained SSE helper for legacy invocation streams."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream",
    }
    if last_event_id:
        headers["Last-Event-ID"] = last_event_id
    with httpx.stream(
        "GET",
        f"{base_url.rstrip('/')}/v1/invocations/{execution_id}/events",
        headers=headers,
        timeout=None,
    ) as response:
        response.raise_for_status()
        event_name = "message"
        data_lines: list[str] = []
        event_id: str | None = None
        for line in response.iter_lines():
            if line == "":
                if data_lines:
                    yield {
                        "id": event_id,
                        "event": event_name,
                        "data": json.loads("\n".join(data_lines)),
                    }
                event_name = "message"
                data_lines = []
                event_id = None
                continue
            if line.startswith(":"):
                continue
            if line.startswith("id:"):
                event_id = line[3:].strip()
            elif line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
