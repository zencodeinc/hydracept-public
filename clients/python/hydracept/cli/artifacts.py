"""Shared artifact materializer for `run` and `jobs recover`."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hydracept.jobs import filename_for_download, normalize_sha256_digest
from hydracept.run_result import RunArtifact


@dataclass
class MaterializeResult:
    artifacts: list[RunArtifact] = field(default_factory=list)
    failed: bool = False
    error: str | None = None


def default_output_dir(project_root: Path, job_id: str) -> Path:
    return Path(project_root) / ".hydracept" / "output" / job_id


def _artifact_items(receipt_or_job: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not receipt_or_job:
        return []
    items = receipt_or_job.get("artifacts") or []
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            normalized.append(item)
        elif item:
            normalized.append({"artifactId": str(item), "id": str(item)})
    return normalized


def _failed_artifact(
    *,
    artifact_id: str,
    media: str,
    expected_sha: str,
    remote: str | None,
    filename: str,
    item: dict[str, Any],
    actual_sha: str | None = None,
    byte_length: int | None = None,
) -> RunArtifact:
    return RunArtifact(
        artifact_id=artifact_id,
        media_type=media,
        sha256=actual_sha or expected_sha or None,
        byte_length=byte_length if byte_length is not None else item.get("byteLength"),
        remote_ref=remote,
        local_path=None,
        verified=False,
        filename=filename,
        label=str(item.get("label") or "") or None,
    )


def materialize_job_artifacts(
    client: Any,
    job_id: str,
    receipt_or_job: dict[str, Any] | None,
    dest: Path,
) -> MaterializeResult:
    dest.mkdir(parents=True, exist_ok=True)
    result = MaterializeResult()
    items = _artifact_items(receipt_or_job)
    if not items:
        return result
    for item in items:
        artifact_id = str(item.get("artifactId") or item.get("id") or "")
        if not artifact_id:
            continue
        filename = filename_for_download(item, artifact_id)
        nested = item.get("digest") if isinstance(item.get("digest"), dict) else {}
        expected_sha = normalize_sha256_digest(
            str(item.get("sha256") or nested.get("sha256") or "")
        )
        media = str(item.get("mediaType") or item.get("mimeType") or "application/octet-stream")
        remote = str(item.get("downloadPath") or item.get("url") or "") or None
        target = dest / Path(filename).name
        try:
            data = client.download_job_artifact(job_id, artifact_id)
        except Exception as exc:  # noqa: BLE001
            result.failed = True
            result.error = f"download failed for {artifact_id}: {exc}"
            result.artifacts.append(
                _failed_artifact(
                    artifact_id=artifact_id,
                    media=media,
                    expected_sha=expected_sha,
                    remote=remote,
                    filename=filename,
                    item=item,
                )
            )
            continue

        downloaded_sha = hashlib.sha256(data).hexdigest()
        if expected_sha and expected_sha != downloaded_sha:
            result.failed = True
            result.error = (
                f"SHA-256 mismatch for {artifact_id}: "
                f"receipt={expected_sha} downloaded={downloaded_sha}"
            )
            result.artifacts.append(
                _failed_artifact(
                    artifact_id=artifact_id,
                    media=media,
                    expected_sha=expected_sha,
                    remote=remote,
                    filename=filename,
                    item=item,
                    actual_sha=downloaded_sha,
                    byte_length=len(data),
                )
            )
            continue

        try:
            target.write_bytes(data)
            if not target.is_file():
                raise OSError("written path is not a file")
            persisted = target.read_bytes()
        except Exception as exc:  # noqa: BLE001
            result.failed = True
            result.error = f"persist failed for {artifact_id} at {target}: {exc}"
            result.artifacts.append(
                _failed_artifact(
                    artifact_id=artifact_id,
                    media=media,
                    expected_sha=expected_sha,
                    remote=remote,
                    filename=filename,
                    item=item,
                    actual_sha=downloaded_sha,
                    byte_length=len(data),
                )
            )
            continue

        persisted_sha = hashlib.sha256(persisted).hexdigest()
        if persisted_sha != downloaded_sha or len(persisted) != len(data):
            result.failed = True
            result.error = f"persist verification failed for {artifact_id} at {target}"
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
            result.artifacts.append(
                _failed_artifact(
                    artifact_id=artifact_id,
                    media=media,
                    expected_sha=expected_sha,
                    remote=remote,
                    filename=filename,
                    item=item,
                    actual_sha=persisted_sha,
                    byte_length=len(persisted),
                )
            )
            continue

        result.artifacts.append(
            RunArtifact(
                artifact_id=artifact_id,
                media_type=media,
                sha256=persisted_sha,
                byte_length=len(persisted),
                remote_ref=remote,
                local_path=str(target.resolve()),
                verified=True,
                filename=filename,
                label=str(item.get("label") or "") or None,
            )
        )
    return result
