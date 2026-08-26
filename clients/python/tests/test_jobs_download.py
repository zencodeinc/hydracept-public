"""JobRunner download SHA prefix and media filename helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path

from hydracept.jobs import filename_for_download, normalize_sha256_digest, JobRunner


def test_normalize_sha256_strips_prefix() -> None:
    digest = "a" * 64
    assert normalize_sha256_digest(f"sha256:{digest}") == digest
    assert normalize_sha256_digest(digest.upper()) == digest
    assert normalize_sha256_digest("") == ""


def test_filename_for_download_adds_ogg_suffix() -> None:
    name = filename_for_download(
        {"mediaType": "audio/ogg", "filename": "art_1"},
        "art_1",
    )
    assert name.endswith(".ogg")
    assert filename_for_download({"mediaType": "audio/ogg", "filename": "click.ogg"}, "x") == "click.ogg"


def test_download_artifacts_accepts_sha256_prefix(tmp_path: Path) -> None:
    payload = b"png-bytes"
    digest = hashlib.sha256(payload).hexdigest()

    class _Client:
        def download_job_artifact(self, job_id: str, artifact_id: str) -> bytes:
            assert job_id == "job_1"
            assert artifact_id == "art_1"
            return payload

    runner = JobRunner(_Client(), workspace=None)  # type: ignore[arg-type]
    paths = runner.download_artifacts(
        "job_1",
        {
            "artifacts": [
                {
                    "artifactId": "art_1",
                    "sha256": f"sha256:{digest}",
                    "mediaType": "image/png",
                    "filename": "mark",
                }
            ]
        },
        tmp_path,
    )
    assert paths == [tmp_path / "mark.png"]
    assert paths[0].read_bytes() == payload


def test_download_artifacts_accepts_nested_digest(tmp_path: Path) -> None:
    payload = b"ogg-bytes"
    digest = hashlib.sha256(payload).hexdigest()

    class _Client:
        def download_job_artifact(self, job_id: str, artifact_id: str) -> bytes:
            return payload

    runner = JobRunner(_Client(), workspace=None)  # type: ignore[arg-type]
    paths = runner.download_artifacts(
        "job_1",
        {
            "artifacts": [
                {
                    "artifactId": "art_ogg",
                    "digest": {"sha256": f"sha256:{digest}"},
                    "mediaType": "audio/ogg",
                }
            ]
        },
        tmp_path,
    )
    assert paths == [tmp_path / "art_ogg.ogg"]
