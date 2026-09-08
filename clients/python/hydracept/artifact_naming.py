"""Map job/receipt artifacts to local filenames without guessing nested folders."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def artifacts_from_payload(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    artifacts = payload.get("artifacts")
    if isinstance(artifacts, list):
        return [item for item in artifacts if isinstance(item, dict)]
    return []


def artifact_id_of(item: dict[str, Any]) -> str:
    return str(item.get("artifactId") or item.get("id") or "").strip()


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "artifact"


def suffix_for_media_type(media_type: str | None, fallback: str = "bin") -> str:
    ctype = (media_type or "").lower()
    if "png" in ctype:
        return "png"
    if "jpeg" in ctype or "jpg" in ctype:
        return "jpg"
    if "webp" in ctype:
        return "webp"
    if "mpeg" in ctype or "mp3" in ctype:
        return "mp3"
    if "wav" in ctype:
        return "wav"
    if "ogg" in ctype:
        return "ogg"
    if "json" in ctype:
        return "json"
    return fallback


def suggested_filename(item: dict[str, Any], *, index: int) -> str:
    raw_name = str(item.get("filename") or "").strip()
    if raw_name:
        return Path(raw_name).name
    label = str(item.get("label") or item.get("sliceCellId") or "").strip()
    suffix = suffix_for_media_type(str(item.get("mediaType") or item.get("media_type") or ""))
    if label:
        return f"{_slug(label)}.{suffix}"
    return f"artifact-{index}.{suffix}"


def find_artifact(
    artifacts: list[dict[str, Any]],
    *,
    artifact_id: str = "",
    label: str = "",
) -> dict[str, Any] | None:
    wanted_id = artifact_id.strip()
    wanted_label = label.strip().lower()
    for item in artifacts:
        if wanted_id and artifact_id_of(item) == wanted_id:
            return item
        if wanted_label:
            candidates = (
                str(item.get("label") or ""),
                str(item.get("sliceCellId") or ""),
                str(item.get("filename") or ""),
                Path(str(item.get("filename") or "")).stem,
            )
            if wanted_label in {value.strip().lower() for value in candidates if value}:
                return item
    return None


@dataclass(frozen=True)
class DownloadedArtifact:
    artifact_id: str
    label: str | None
    filename: str
    path: Path
    media_type: str
    bytes_written: int
    sha256: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifactId": self.artifact_id,
            "label": self.label,
            "filename": self.filename,
            "path": str(self.path),
            "mediaType": self.media_type,
            "bytes": self.bytes_written,
            "sha256": self.sha256,
        }
