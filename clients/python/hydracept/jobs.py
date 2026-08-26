"""JobRunner — submit, nextAction, poll, download, receipt for capability jobs."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from hydracept import HydraceptClient
    from hydracept.cli.workspace import ResolvedWorkspace

_MEDIA_EXTENSIONS = {
    "audio/ogg": ".ogg",
    "application/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/mpeg": ".mp3",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "model/gltf-binary": ".glb",
    "video/mp4": ".mp4",
    "application/json": ".json",
}


def normalize_sha256_digest(value: str | None) -> str:
    """Return lowercase hex, stripping a ``sha256:`` prefix when present."""
    raw = str(value or "").strip().lower()
    if raw.startswith("sha256:"):
        raw = raw[7:]
    return raw


def filename_for_download(item: dict[str, Any], artifact_id: str) -> str:
    media = str(item.get("mediaType") or item.get("mimeType") or "").split(";")[0].strip().lower()
    raw = str(item.get("filename") or item.get("label") or artifact_id or "artifact").strip() or "artifact"
    name = Path(raw.replace("\\", "/")).name or "artifact"
    ext = _MEDIA_EXTENSIONS.get(media, "")
    if ext and not name.lower().endswith(ext):
        name = f"{name}{ext}"
    return name


def next_action_for_job(job: dict[str, Any], *, has_artifacts: bool = False) -> str:
    status = str(job.get("status") or "").lower()
    if status in {"queued", "running", "awaiting_approval", "canceling"}:
        return "poll"
    if status == "succeeded":
        if has_artifacts:
            return "download"
        return "receipt"
    return "done"


@dataclass
class JobRunResult:
    job_id: str
    status: str
    job: dict[str, Any]
    receipt: dict[str, Any] | None
    downloads: list[Path] = field(default_factory=list)
    next_action: str = "poll"


class JobRunner:
    """Capability-job orchestration. Does not speak invocations or visual jobs."""

    def __init__(self, client: HydraceptClient, workspace: ResolvedWorkspace) -> None:
        self._client = client
        self._workspace = workspace

    def submit(self, capability_key: str, body: dict[str, Any]) -> dict[str, Any]:
        from hydracept.cli.job_context import merge_workspace_job_context

        payload = merge_workspace_job_context(dict(body), self._workspace)
        return self._client.submit_capability_job(capability_key, payload)

    def poll(self, job_id: str) -> dict[str, Any]:
        return self._client.get_job(job_id)

    def receipt(self, job_id: str) -> dict[str, Any]:
        return self._client.get_job_receipt(job_id)

    def next_action(self, job: dict[str, Any]) -> str:
        artifacts = job.get("artifacts") or []
        has_artifacts = isinstance(artifacts, list) and bool(artifacts)
        return next_action_for_job(job, has_artifacts=has_artifacts)

    def run(
        self,
        capability_key: str,
        body: dict[str, Any],
        *,
        download_dir: str | Path | None = None,
        poll_seconds: float = 120.0,
        poll_interval: float = 2.0,
    ) -> JobRunResult:
        submitted = self.submit(capability_key, body)
        job_id = str(submitted.get("jobId") or submitted.get("id") or "")
        if not job_id:
            raise RuntimeError(f"No jobId in submit response: {submitted!r}")
        deadline = time.time() + max(5.0, poll_seconds)
        job = submitted
        status = str(job.get("status") or "queued")
        while time.time() < deadline:
            job = self.poll(job_id)
            status = str(job.get("status") or "unknown")
            if status in {"succeeded", "failed", "canceled", "cancelled"}:
                break
            time.sleep(max(0.2, poll_interval))
        receipt: dict[str, Any] | None = None
        if status == "succeeded":
            try:
                receipt = self.receipt(job_id)
            except Exception:  # noqa: BLE001
                receipt = None
        downloads: list[Path] = []
        if download_dir and status == "succeeded":
            downloads = self.download_artifacts(job_id, receipt or job, Path(download_dir))
        has_artifacts = bool(downloads) or bool((receipt or {}).get("artifacts"))
        return JobRunResult(
            job_id=job_id,
            status=status,
            job=job,
            receipt=receipt,
            downloads=downloads,
            next_action=next_action_for_job(job, has_artifacts=has_artifacts),
        )

    def download_artifacts(
        self,
        job_id: str,
        receipt_or_job: dict[str, Any],
        download_dir: Path,
    ) -> list[Path]:
        download_dir.mkdir(parents=True, exist_ok=True)
        artifacts = receipt_or_job.get("artifacts") or []
        paths: list[Path] = []
        if not isinstance(artifacts, list):
            return paths
        for item in artifacts:
            artifact_id = ""
            filename = ""
            expected_sha = ""
            if isinstance(item, dict):
                artifact_id = str(item.get("artifactId") or item.get("id") or "")
                filename = filename_for_download(item, artifact_id)
                nested = item.get("digest") if isinstance(item.get("digest"), dict) else {}
                expected_sha = normalize_sha256_digest(
                    str(item.get("sha256") or nested.get("sha256") or "")
                )
            elif item:
                artifact_id = str(item)
                filename = artifact_id
            if not artifact_id:
                continue
            data = self._client.download_job_artifact(job_id, artifact_id)
            actual_sha = hashlib.sha256(data).hexdigest()
            if expected_sha and expected_sha != actual_sha:
                raise RuntimeError(
                    f"SHA-256 mismatch for {artifact_id}: receipt={expected_sha} downloaded={actual_sha}"
                )
            target = download_dir / Path(filename).name
            target.write_bytes(data)
            paths.append(target)
        return paths
