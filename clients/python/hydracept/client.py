"""Public Hydracept HTTP client — jobs, wait/watch, and labeled artifact download."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, TextIO
from uuid import uuid4

import httpx

from hydracept.artifact_naming import (
    DownloadedArtifact,
    artifact_id_of,
    artifacts_from_payload,
    find_artifact,
    suggested_filename,
)
from hydracept.errors import raise_api_status
from hydracept.http_timeout import (
    PINNED_BULK_WAIT_TIMEOUT_SECONDS,
    PINNED_READ_TIMEOUT_SECONDS,
    READ_TIMEOUT_SECONDS,
    http_timeout,
)
from hydracept.job_lifecycle import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_WAIT_TIMEOUT_SECONDS,
    JobNotSucceeded,
    JobWaitTimeout,
    classify_job,
    job_id_from_payload,
)
from hydracept.job_progress import JobProgress, emit_progress


@dataclass(frozen=True)
class BoundWorkspace:
    api_url: str
    project_id: str
    environment: str


class HydraceptClient:
    """Synchronous public API client.

    Prefer :meth:`from_workspace` in a coding-agent checkout. That binds project
    context, injects it on submit, and exposes wait/download helpers so agents do
    not roll their own poll or copy loops.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = READ_TIMEOUT_SECONDS,
        workspace: Any | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.workspace = workspace
        self._timeout = http_timeout(timeout)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._http = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=self._timeout,
            transport=transport,
            follow_redirects=True,
        )

    @classmethod
    def from_workspace(
        cls,
        project_root: Path | None = None,
        *,
        token: str | None = None,
        api_url: str | None = None,
        timeout: float = READ_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> HydraceptClient:
        from hydracept.cli.workspace import CliOverrides, require_ready_workspace

        resolved = require_ready_workspace(
            Path(project_root or Path.cwd()),
            overrides=CliOverrides(token=token, api_url=api_url),
        )
        return cls(
            resolved.api_url,
            resolved.token,
            timeout=timeout,
            workspace=resolved,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> HydraceptClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _merge_body(self, body: dict[str, Any] | None) -> dict[str, Any]:
        payload = dict(body or {})
        if self.workspace is None:
            return payload
        from hydracept.cli.job_context import merge_workspace_job_context

        try:
            return merge_workspace_job_context(payload, self.workspace)
        except (AttributeError, TypeError):
            from hydracept.workspace_bind import inject_workspace_job_context

            return inject_workspace_job_context(payload, self.workspace)

    def _get(self, path: str) -> dict[str, Any]:
        response = self._http.get(path)
        raise_api_status(response)
        return response.json()

    def _post(
        self, path: str, body: dict[str, Any] | None = None, *, timeout: httpx.Timeout | None = None
    ) -> dict[str, Any]:
        response = self._http.post(path, json=body, timeout=timeout)
        raise_api_status(response)
        if not response.content:
            return {}
        return response.json()

    def capabilities(self) -> dict[str, Any]:
        return self._get("/v1/capabilities")

    def describe_capability(self, key: str) -> dict[str, Any]:
        return self._get(f"/v1/capabilities/{key}")

    def invoke_capability(self, key: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST /v1/capabilities/{key}/invoke.

        Job-only capabilities (creative longform, images) reject this path.
        Use :meth:`submit_capability_job` and poll :meth:`get_job`.
        """
        return self._post(f"/v1/capabilities/{key}/invoke", self._merge_body(body))

    def submit_capability_job(self, key: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST /v1/capabilities/{key}/jobs. Returns immediately with a job id."""
        return self._post(f"/v1/capabilities/{key}/jobs", self._merge_body(body))

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self._get(f"/v1/jobs/{job_id}")

    def get_job_receipt(self, job_id: str) -> dict[str, Any]:
        return self._get(f"/v1/jobs/{job_id}/receipt")

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        return self._post(f"/v1/jobs/{job_id}/cancel")

    def approve_job(self, job_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._post(f"/v1/jobs/{job_id}/approve", body)

    def reject_job(self, job_id: str) -> dict[str, Any]:
        return self._post(f"/v1/jobs/{job_id}/reject")

    def select_job_variant(self, job_id: str, artifact_id: str) -> dict[str, Any]:
        return self._post(f"/v1/jobs/{job_id}/variants/select", {"artifactId": artifact_id})

    def watch_job(
        self,
        job_id: str,
        *,
        interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        timeout: float = DEFAULT_WAIT_TIMEOUT_SECONDS,
        progress_stream: TextIO | None = None,
    ) -> Iterator[JobProgress]:
        """Yield classified progress until the job is terminal or *timeout* elapses.

        Writes one flushed JSON line per poll when *progress_stream* is set so
        piped agent shells see waits immediately. MCP tools should poll
        ``hydracept_job_status`` instead of blocking here.
        """
        started = time.monotonic()
        attempt = 0
        last_status = "unknown"
        while True:
            job = self.get_job(job_id)
            elapsed = time.monotonic() - started
            attempt += 1
            progress = JobProgress.from_job(
                job, job_id=job_id, elapsed_seconds=elapsed, attempt=attempt
            )
            last_status = progress.status
            emit_progress(progress, progress_stream)
            yield progress
            if progress.terminal:
                return
            if elapsed + interval >= timeout:
                raise JobWaitTimeout(job_id, last_status, elapsed)
            time.sleep(interval)

    def wait_for_job(
        self,
        job_id: str,
        *,
        interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        timeout: float = DEFAULT_WAIT_TIMEOUT_SECONDS,
        require_success: bool = False,
        progress_stream: TextIO | None = None,
    ) -> dict[str, Any]:
        """Block until a terminal status. Returns the last job payload."""
        final: dict[str, Any] = {}
        for progress in self.watch_job(
            job_id, interval=interval, timeout=timeout, progress_stream=progress_stream
        ):
            final = progress.job
        if require_success:
            view = classify_job(final)
            if not view.succeeded:
                raise JobNotSucceeded(job_id, view.status, final)
        return final

    def run_capability_job(
        self,
        key: str,
        body: dict[str, Any],
        *,
        wait: bool = True,
        require_success: bool = False,
        download_dir: Path | str | None = None,
        interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        timeout: float = DEFAULT_WAIT_TIMEOUT_SECONDS,
        progress_stream: TextIO | None = None,
        generate_idempotency_key: bool = True,
    ) -> dict[str, Any]:
        """Submit, optionally wait, and optionally download artifacts by label.

        This is the method coding-agent scripts should call instead of a homemade
        poll loop and PowerShell copy.
        """
        payload = dict(body)
        if generate_idempotency_key:
            payload.setdefault("idempotencyKey", str(uuid4()))
        submitted = self.submit_capability_job(key, payload)
        job_id = job_id_from_payload(submitted)
        result: dict[str, Any] = {
            "capabilityKey": key,
            "jobId": job_id,
            "submitted": submitted,
            "job": submitted,
            "downloads": [],
        }
        if not job_id or not wait:
            result["statusView"] = classify_job(submitted).as_dict()
            return result
        final = self.wait_for_job(
            job_id,
            interval=interval,
            timeout=timeout,
            require_success=require_success,
            progress_stream=progress_stream,
        )
        result["job"] = final
        result["statusView"] = classify_job(final).as_dict()
        if download_dir:
            result["downloads"] = [
                item.as_dict()
                for item in self.download_job_artifacts(job_id, Path(download_dir), job=final)
            ]
        return result

    def download_artifact(
        self,
        job_id: str,
        artifact_id: str,
        dest: Path,
    ) -> DownloadedArtifact:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._http.stream("GET", f"/v1/jobs/{job_id}/artifacts/{artifact_id}") as response:
            raise_api_status(response)
            media_type = response.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
            digest = hashlib.sha256()
            written = 0
            with dest.open("wb") as handle:
                for chunk in response.iter_bytes():
                    digest.update(chunk)
                    handle.write(chunk)
                    written += len(chunk)
        return DownloadedArtifact(
            artifact_id=artifact_id,
            label=None,
            filename=dest.name,
            path=dest,
            media_type=media_type,
            bytes_written=written,
            sha256=digest.hexdigest(),
        )

    def download_job_artifacts(
        self,
        job_id: str,
        dest_dir: Path,
        *,
        job: dict[str, Any] | None = None,
        label: str = "",
    ) -> list[DownloadedArtifact]:
        """Download artifacts into *dest_dir* using receipt/job ``label`` and ``filename``.

        Creates nested directories as needed. Agents should use this instead of
        ``Get-ChildItem | Where-Object``.
        """
        payload = job or self.get_job(job_id)
        artifacts = artifacts_from_payload(payload)
        if not artifacts:
            try:
                artifacts = artifacts_from_payload(self.get_job_receipt(job_id))
            except httpx.HTTPError:
                artifacts = []
        if label:
            match = find_artifact(artifacts, label=label)
            artifacts = [match] if match else []
        dest_dir.mkdir(parents=True, exist_ok=True)
        downloaded: list[DownloadedArtifact] = []
        for index, item in enumerate(artifacts):
            artifact_id = artifact_id_of(item)
            if not artifact_id:
                continue
            filename = suggested_filename(item, index=index)
            saved = self.download_artifact(job_id, artifact_id, dest_dir / filename)
            downloaded.append(
                DownloadedArtifact(
                    artifact_id=saved.artifact_id,
                    label=str(item.get("label") or item.get("sliceCellId") or "") or None,
                    filename=filename,
                    path=saved.path,
                    media_type=saved.media_type,
                    bytes_written=saved.bytes_written,
                    sha256=saved.sha256,
                )
            )
        return downloaded

    def quote_capability(self, key: str, body: dict[str, Any]) -> dict[str, Any]:
        return self._post(f"/v1/capabilities/{key}/quote", self._merge_body(body))

    def estimate_capability(self, key: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST /v1/capabilities/{key}/estimate — HTTP alias of quote_capability."""
        return self.quote_capability(key, body)

    def resolve_capability(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/capabilities/resolve", body)

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
        response = self._http.get(f"/v1/jobs/{job_id}/artifacts/{artifact_id}")
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
        return self._post(
            "/v1/inference/pinned",
            body,
            timeout=http_timeout(PINNED_READ_TIMEOUT_SECONDS),
        )

    def create_pinned_inference_bulk(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/inference/pinned/bulk", body)

    def get_pinned_bulk(self, bulk_id: str) -> dict[str, Any]:
        return self._get(f"/v1/inference/pinned/bulk/{bulk_id}")

    def wait_pinned_bulk(
        self,
        bulk_id: str,
        *,
        interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        timeout: float = PINNED_BULK_WAIT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + float(timeout)
        while True:
            payload = self.get_pinned_bulk(bulk_id)
            status = str(payload.get("status") or "")
            next_action = str(payload.get("nextAction") or "")
            if status in {"succeeded", "failed", "partial"} or next_action == "stop":
                return payload
            if time.monotonic() >= deadline:
                raise TimeoutError(f"pinned bulk {bulk_id} did not finish within {timeout}s")
            poll_after = payload.get("pollAfterSeconds", interval)
            try:
                sleep_for = float(poll_after)
            except (TypeError, ValueError):
                sleep_for = float(interval)
            time.sleep(max(0.5, sleep_for))

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
        response = self._http.patch(f"/v1/panel-definitions/{definition_id}", json=body)
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
