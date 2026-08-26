"""Hydracept Python client — public API surface."""

from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any, Iterator

import httpx

from hydracept.errors import HydraceptApiError, raise_api_status


def _package_version() -> str:
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if pyproject.is_file():
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("version ="):
                value = stripped.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    try:
        return package_version("hydracept")
    except PackageNotFoundError:
        return "0.0.0+local"


__version__ = _package_version()


class HydraceptClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 120.0,
        workspace: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._workspace = workspace
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._timeout = timeout

    def _merge_body(self, body: dict[str, Any] | None) -> dict[str, Any]:
        payload = dict(body or {})
        if self._workspace is None:
            return payload
        from hydracept.cli.job_context import merge_workspace_job_context

        return merge_workspace_job_context(payload, self._workspace)

    def invoke_capability(self, key: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._post(f"/v1/capabilities/{key}/invoke", self._merge_body(body))

    def submit_capability_job(self, key: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._post(f"/v1/capabilities/{key}/jobs", self._merge_body(body))

    def quote_capability(self, key: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._post(f"/v1/capabilities/{key}/quote", self._merge_body(body))

    def _get(self, path: str) -> dict[str, Any]:
        response = httpx.get(
            f"{self.base_url}{path}",
            headers=self._headers,
            timeout=self._timeout,
        )
        raise_api_status(response)
        return response.json()

    def _post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}{path}",
            headers=self._headers,
            json=body,
            timeout=self._timeout,
        )
        raise_api_status(response)
        if not response.content:
            return {}
        return response.json()

    def capabilities(self) -> dict[str, Any]:
        return self._get("/v1/capabilities")

    def describe_capability(self, key: str) -> dict[str, Any]:
        return self._get(f"/v1/capabilities/{key}")

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self._get(f"/v1/jobs/{job_id}")

    def get_job_receipt(self, job_id: str) -> dict[str, Any]:
        return self._get(f"/v1/jobs/{job_id}/receipt")

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        return self._post(f"/v1/jobs/{job_id}/cancel")

    def resolve_capability(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/capabilities/resolve", body)

    def estimate_capability(self, key: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST /v1/capabilities/{key}/estimate — HTTP alias of quote_capability."""
        return self.quote_capability(key, body)

    def list_jobs(self, project_id: str | None = None, *, limit: int = 25, cursor: str | None = None) -> dict[str, Any]:
        if project_id:
            path = f"/v1/projects/{project_id}/jobs?limit={limit}"
            if cursor:
                path = f"{path}&cursor={cursor}"
            return self._get(path)
        path = f"/v1/jobs?limit={limit}"
        if cursor:
            path = f"{path}&cursor={cursor}"
        return self._get(path)

    def download_job_artifact(self, job_id: str, artifact_id: str) -> bytes:
        response = httpx.get(
            f"{self.base_url}/v1/jobs/{job_id}/artifacts/{artifact_id}",
            headers={"Authorization": self._headers["Authorization"]},
            timeout=self._timeout,
            follow_redirects=True,
        )
        raise_api_status(response)
        return response.content

    def create_capability_request(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/capability-requests", body)

    def revise_capability_request(self, request_id: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._post(f"/v1/capability-requests/{request_id}/revisions", body)

    def submit_capability_request(self, request_id: str) -> dict[str, Any]:
        return self._post(f"/v1/capability-requests/{request_id}/submit")

    def get_capability_request(self, request_id: str) -> dict[str, Any]:
        return self._get(f"/v1/capability-requests/{request_id}")

    def get_capability_request_quote(self, request_id: str) -> dict[str, Any]:
        return self._get(f"/v1/capability-requests/{request_id}/quote")

    def get_wallet(self) -> dict[str, Any]:
        return self._get("/v1/billing/wallet")

    def create_pinned_inference(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/inference/pinned", body)

    def get_pinned_receipt(self, receipt_id: str) -> dict[str, Any]:
        return self._get(f"/v1/inference/pinned/{receipt_id}")

    def list_pinned_receipts(self) -> dict[str, Any]:
        return self._get("/v1/inference/pinned")

    def create_run_manifest(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/provenance/manifests", body)

    def get_run_manifest(self, manifest_id: str) -> dict[str, Any]:
        return self._get(f"/v1/provenance/manifests/{manifest_id}")

    def verify_run_manifest(self, manifest_id: str) -> dict[str, Any]:
        return self._post(f"/v1/provenance/manifests/{manifest_id}/verify")

    def get_lockfile(self, receipt_id: str) -> dict[str, Any]:
        return self._get(f"/v1/provenance/lockfile?receipt_id={receipt_id}")

    def verify_lockfile(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/provenance/lockfile/verify", body)

    def list_wallet_transactions(self) -> dict[str, Any]:
        return self._get("/v1/billing/wallet/transactions")

    def agent_context(self) -> dict[str, Any]:
        return self._get("/v1/agent-context")

    def diagnostics_session(self) -> dict[str, Any]:
        return self._get("/v1/diagnostics/session")

    def policy_dry_run(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/policy-evaluations", body)

    def create_panel_definition(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/panel-definitions", body)

    def list_panel_definitions(self, project_id: str | None = None) -> dict[str, Any]:
        path = "/v1/panel-definitions"
        if project_id:
            path = f"{path}?projectId={project_id}"
        return self._get(path)

    def get_panel_definition(self, definition_id: str) -> dict[str, Any]:
        return self._get(f"/v1/panel-definitions/{definition_id}")

    def patch_panel_definition(self, definition_id: str, body: dict[str, Any]) -> dict[str, Any]:
        response = httpx.patch(
            f"{self.base_url}/v1/panel-definitions/{definition_id}",
            headers=self._headers,
            json=body,
            timeout=self._timeout,
        )
        raise_api_status(response)
        return response.json()

    def create_panel_session(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/panel-sessions", body)

    def get_panel_session(self, session_id: str) -> dict[str, Any]:
        return self._get(f"/v1/panel-sessions/{session_id}")

    def revoke_panel_session(self, session_id: str) -> dict[str, Any]:
        return self._post(f"/v1/panel-sessions/{session_id}/revoke")

    def create_panel_launch_code(self, session_id: str) -> dict[str, Any]:
        return self._post(f"/v1/panel-sessions/{session_id}/launch-codes")

    def get_panel_bootstrap(self) -> dict[str, Any]:
        return self._get("/v1/panel/bootstrap")

    def exchange_panel_launch_code(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/panel/launch-codes/exchange", body)


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
        raise_api_status(response)
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


from hydracept.workspace import HydraceptWorkspace

__all__ = ["HydraceptClient", "HydraceptWorkspace", "iter_invocation_events", "__version__"]
