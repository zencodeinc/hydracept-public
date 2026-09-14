from __future__ import annotations

import hashlib
from pathlib import Path

from hydracept.cli.artifacts import materialize_job_artifacts
from hydracept.cli.run_facade import _pricing_from_job


class _ArtifactClient:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def download_job_artifact(self, job_id: str, artifact_id: str) -> bytes:
        assert job_id == "job_test"
        assert artifact_id == "art_test"
        return self.data


def _artifact_source(data: bytes) -> dict:
    return {
        "artifacts": [
            {
                "artifactId": "art_test",
                "filename": "sound.ogg",
                "mediaType": "audio/ogg",
                "sha256": hashlib.sha256(data).hexdigest(),
                "byteLength": len(data),
            }
        ]
    }


def test_completed_run_prefers_sealed_receipt_quote_over_job_estimate() -> None:
    pricing = _pricing_from_job(
        {"status": "succeeded", "estimatedCost": 999999999.0, "actualCost": 0.000029},
        {
            "pricing": {
                "quote": {"customerTotal": {"amountMicros": 30_000}},
                "charge": {"customerCharge": {"amountMicros": 0}},
            }
        },
    )

    assert pricing.estimated_cost == 0.03
    assert pricing.actual_cost == 0.0
    assert pricing.customer_total_micros == 0
    assert pricing.financial_state == "covered"
    assert pricing.to_dict()["customerCharge"]["customerTotalMicros"] == 0


def test_materialized_artifact_is_verified_from_disk(tmp_path: Path) -> None:
    data = b"audio-bytes"
    result = materialize_job_artifacts(
        _ArtifactClient(data),
        "job_test",
        _artifact_source(data),
        tmp_path,
    )

    assert result.failed is False
    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.verified is True
    assert artifact.local_path is not None
    local = Path(artifact.local_path)
    assert local.is_absolute()
    assert local.is_file()
    assert local.read_bytes() == data
    assert artifact.sha256 == hashlib.sha256(data).hexdigest()


def test_materialize_honors_file_destination(tmp_path: Path) -> None:
    data = b"audio-bytes"
    target = tmp_path / "coin-pickup.ogg"
    result = materialize_job_artifacts(
        _ArtifactClient(data),
        "job_test",
        _artifact_source(data),
        target,
    )
    assert result.failed is False
    assert target.is_file()
    assert target.read_bytes() == data
    assert Path(result.artifacts[0].local_path or "").name == "coin-pickup.ogg"
    assert result.artifacts[0].filename == "coin-pickup.ogg"


def test_materialization_fails_closed_when_local_write_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data = b"audio-bytes"
    original = Path.write_bytes

    def _broken_write(self: Path, payload: bytes) -> int:
        if self.name == "sound.ogg":
            raise OSError("disk full")
        return original(self, payload)

    monkeypatch.setattr(Path, "write_bytes", _broken_write)

    result = materialize_job_artifacts(
        _ArtifactClient(data),
        "job_test",
        _artifact_source(data),
        tmp_path,
    )

    assert result.failed is True
    assert "persist failed" in str(result.error)
    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.verified is False
    assert artifact.local_path is None
