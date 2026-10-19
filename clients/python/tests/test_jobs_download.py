"""JobRunner download SHA prefix and media filename helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path

from hydracept.jobs import (
    expected_artifact_download_sha256,
    filename_for_download,
    normalize_sha256_digest,
    JobRunner,
)
from hydracept_contracts.passive_artifact_metadata import embed_png_export_metadata


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
        def download_job_artifact_with_headers(self, job_id: str, artifact_id: str) -> tuple[bytes, dict[str, str]]:
            assert job_id == "job_1"
            assert artifact_id == "art_1"
            return payload, {}

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
        def download_job_artifact_with_headers(self, job_id: str, artifact_id: str) -> tuple[bytes, dict[str, str]]:
            return payload, {}

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


def test_download_artifacts_verifies_export_sha256(tmp_path: Path) -> None:
    canonical = b"\x89PNG\r\n\x1a\n" + b"rest-of-png"
    exported = embed_png_export_metadata(canonical, include_generator=True)
    export_digest = hashlib.sha256(exported).hexdigest()
    canonical_digest = hashlib.sha256(canonical).hexdigest()

    class _Client:
        def download_job_artifact_with_headers(self, job_id: str, artifact_id: str) -> tuple[bytes, dict[str, str]]:
            assert job_id == "job_1"
            assert artifact_id == "art_1"
            return exported, {"X-Hydracept-Export-Sha256": export_digest}

    runner = JobRunner(_Client(), workspace=None)  # type: ignore[arg-type]
    paths = runner.download_artifacts(
        "job_1",
        {
            "artifacts": [
                {
                    "artifactId": "art_1",
                    "sha256": canonical_digest,
                    "exportSha256": export_digest,
                    "mediaType": "image/png",
                    "filename": "out",
                }
            ]
        },
        tmp_path,
    )
    assert paths == [tmp_path / "out.png"]
    assert paths[0].read_bytes() == exported


def test_expected_artifact_download_sha256_prefers_export_header() -> None:
    item = {"sha256": "a" * 64, "exportSha256": "b" * 64}
    assert expected_artifact_download_sha256(item, export_header="c" * 64) == "c" * 64
    assert expected_artifact_download_sha256(item) == "b" * 64
