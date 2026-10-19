from __future__ import annotations

import hashlib
from pathlib import Path

from hydracept.cli.artifacts import materialize_job_artifacts


def test_cli_materialize_verifies_export_sha256(tmp_path: Path) -> None:
    canonical = b"png"
    exported = b"png-with-metadata"
    export_digest = hashlib.sha256(exported).hexdigest()
    canonical_digest = hashlib.sha256(canonical).hexdigest()

    class _Client:
        def download_job_artifact_with_headers(self, job_id: str, artifact_id: str) -> tuple[bytes, dict[str, str]]:
            return exported, {"X-Hydracept-Export-Sha256": export_digest}

    result = materialize_job_artifacts(
        _Client(),
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
    assert not result.failed
    assert len(result.artifacts) == 1
    assert result.artifacts[0].verified is True
