"""Unit tests for run façade wait/error/idempotency semantics."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import httpx

from hydracept.cli.run_facade import execute_run, recover_job
from hydracept.cli.workspace import ResolvedWorkspace
from hydracept.errors import HydraceptApiError


def _workspace() -> ResolvedWorkspace:
    return ResolvedWorkspace(
        api_url="https://api.hydracept.com",
        token="hapt_test",
        project_id="cpr_a",
        environment="development",
    )


def test_no_wait_returns_running_schema(tmp_path: Path) -> None:
    class FakeClient:
        def describe_capability(self, key: str) -> dict:
            return {"executionModes": ["job_async"]}

        def submit_capability_job(self, key: str, body: dict) -> dict:
            assert body["idempotencyKey"]
            assert body["execution"]["executionConstraints"]["maxCostUsd"] == 1.0
            return {"jobId": "wfr_1", "status": "queued", "estimatedCost": 0.05}

    with patch(
        "hydracept.cli.run_facade.require_execution_context",
        return_value=(_workspace(), None),
    ), patch("hydracept.cli.run_facade.HydraceptClient", return_value=FakeClient()):
        outcome = execute_run(
            tmp_path,
            "image.generate.v1",
            {"prompt": "icon"},
            wait=False,
            max_cost=1.0,
            refresh_context=False,
        )
    assert outcome.exit_code == 0
    payload = outcome.payload()
    assert payload["status"] == "running"
    assert payload["artifacts"] == []
    assert payload["pricing"]["actualCost"] is None
    assert payload["idempotencyKey"]
    assert payload["jobId"] == "wfr_1"


def test_missing_job_id_is_typed_error_not_run_result(tmp_path: Path) -> None:
    class FakeClient:
        def describe_capability(self, key: str) -> dict:
            return {"executionModes": ["job_async"]}

        def submit_capability_job(self, key: str, body: dict) -> dict:
            return {"status": "queued"}

    with patch(
        "hydracept.cli.run_facade.require_execution_context",
        return_value=(_workspace(), None),
    ), patch("hydracept.cli.run_facade.HydraceptClient", return_value=FakeClient()):
        outcome = execute_run(
            tmp_path,
            "image.generate.v1",
            {"prompt": "icon"},
            wait=False,
            refresh_context=False,
        )
    assert outcome.exit_code != 0
    assert outcome.result is None
    assert outcome.error is not None
    assert outcome.error.code == "InvalidInput"


def test_pre_admission_is_typed_error_not_run_result(tmp_path: Path) -> None:
    request = httpx.Request(
        "POST", "https://api.hydracept.com/v1/capabilities/image.generate.v1/jobs"
    )
    response = httpx.Response(
        402,
        request=request,
        json={"detail": {"code": "EstimateExceedsMaxCost", "message": "too expensive"}},
    )

    class FakeClient:
        def describe_capability(self, key: str) -> dict:
            return {"executionModes": ["job_async"]}

        def submit_capability_job(self, key: str, body: dict) -> dict:
            raise HydraceptApiError(
                "402 EstimateExceedsMaxCost: too expensive",
                request=request,
                response=response,
                payload={
                    "detail": {"code": "EstimateExceedsMaxCost", "message": "too expensive"}
                },
                code="EstimateExceedsMaxCost",
            )

    with patch(
        "hydracept.cli.run_facade.require_execution_context",
        return_value=(_workspace(), None),
    ), patch("hydracept.cli.run_facade.HydraceptClient", return_value=FakeClient()):
        outcome = execute_run(
            tmp_path,
            "image.generate.v1",
            {"prompt": "icon"},
            wait=False,
            refresh_context=False,
        )
    assert outcome.exit_code != 0
    assert outcome.result is None
    assert outcome.error is not None
    assert outcome.error.code == "EstimateExceedsMaxCost"


def test_recover_materializes_default_output_dir(tmp_path: Path) -> None:
    png = b"\x89PNG\r\n\x1a\n"

    class FakeClient:
        def get_job(self, job_id: str) -> dict:
            return {"status": "succeeded", "capabilityKey": "image.generate.v1", "artifacts": []}

        def get_job_receipt(self, job_id: str) -> dict:
            return {
                "artifacts": [
                    {
                        "artifactId": "art_1",
                        "mediaType": "image/png",
                        "sha256": hashlib.sha256(png).hexdigest(),
                    }
                ]
            }

        def download_job_artifact(self, job_id: str, artifact_id: str) -> bytes:
            return png

    with patch("hydracept.cli.run_facade.HydraceptClient", return_value=FakeClient()):
        outcome = recover_job(_workspace(), "wfr_1", project_root=tmp_path)
    assert outcome.exit_code == 0
    assert outcome.result is not None
    local = Path(outcome.result.artifacts[0].local_path or "")
    assert local.is_file()
    assert ".hydracept" in str(local)
    assert "wfr_1" in str(local)


def test_materialize_does_not_write_on_sha_mismatch(tmp_path: Path) -> None:
    from hydracept.cli.artifacts import materialize_job_artifacts

    class FakeClient:
        def download_job_artifact(self, job_id: str, artifact_id: str) -> bytes:
            return b"not-the-receipt-bytes"

    dest = tmp_path / "out"
    result = materialize_job_artifacts(
        FakeClient(),
        "wfr_1",
        {
            "artifacts": [
                {
                    "artifactId": "art_1",
                    "mediaType": "image/png",
                    "sha256": "a" * 64,
                    "filename": "sprite.png",
                }
            ]
        },
        dest,
    )
    assert result.failed is True
    assert not (dest / "sprite.png").exists()
    assert result.artifacts[0].local_path is None
    assert result.artifacts[0].verified is False


def test_parse_input_argument_reads_structured_json_file(tmp_path: Path) -> None:
    from hydracept.cli.run_facade import parse_input_argument

    path = tmp_path / "extract.json"
    path.write_text(
        '{"document": "invoice 42", "schema": {"type": "object", "properties": {"id": {"type": "string"}}}}',
        encoding="utf-8",
    )
    payload = parse_input_argument(None, path)
    assert payload["document"] == "invoice 42"
    assert payload["schema"]["properties"]["id"]["type"] == "string"
    assert parse_input_argument('{"prompt": "x"}', None) == {"prompt": "x"}

