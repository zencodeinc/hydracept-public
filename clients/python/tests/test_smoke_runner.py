"""Smoke runner unit tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hydracept.cli.smoke_runner import (
    DEFAULT_SMOKE_CAPABILITY,
    SHEET_MIN_CELL_PX,
    SHEET_SMOKE_COLUMNS,
    SHEET_SMOKE_ROWS,
    SmokeError,
    run_sheet_smoke,
    run_smoke,
    sheet_minimum_canvas,
    sheet_smoke_input,
)
from hydracept.cli.workspace import ResolvedWorkspace
from hydracept.png_alpha import PngTransparency


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00"
    b"\x18\xdd\x8d\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _workspace() -> ResolvedWorkspace:
    return ResolvedWorkspace(
        api_url="https://api.hydracept.com",
        token="hapt_test",
        project_id="cpr_smoke_test",
        environment="development",
    )


def _fake_transparency() -> PngTransparency:
    return PngTransparency(
        width=1,
        height=1,
        has_alpha_channel=True,
        has_alpha_below_255=True,
        has_alpha_above_0=True,
        opaque_bbox_nonempty=True,
    )


def test_sheet_minimum_canvas_derives_from_cell_grid() -> None:
    width, height = sheet_minimum_canvas(rows=SHEET_SMOKE_ROWS, columns=SHEET_SMOKE_COLUMNS)
    assert width == SHEET_SMOKE_COLUMNS * SHEET_MIN_CELL_PX
    assert height == SHEET_SMOKE_ROWS * SHEET_MIN_CELL_PX
    assert width % 16 == 0
    assert height % 16 == 0
    payload = sheet_smoke_input(prompt="icons")
    assert payload["sheet"]["slice"] is True
    assert payload["width"] == width
    assert payload["height"] == height


def test_run_smoke_uses_project_id_as_product_id(tmp_path: Path) -> None:
    captured: dict = {}
    digest = hashlib.sha256(PNG_BYTES).hexdigest()

    class FakeClient:
        def submit_capability_job(self, key: str, body: dict) -> dict:
            captured["key"] = key
            captured["body"] = body
            return {"jobId": "wfr_test"}

        def get_job(self, job_id: str) -> dict:
            return {"status": "succeeded"}

        def download_job_artifact(self, job_id: str, artifact_id: str) -> bytes:
            return PNG_BYTES

        def get_job_receipt(self, job_id: str) -> dict:
            return {
                "receiptId": "rcpt_ok",
                "artifacts": [{"id": "art_test", "sha256": digest}],
                "pricing": {
                    "charge": {
                        "customerCharge": {"amountMicros": 44000, "currency": "USD"}
                    }
                },
            }

    with patch(
        "hydracept.cli.smoke_runner.require_ready_workspace",
        return_value=_workspace(),
    ), patch(
        "hydracept.cli.smoke_runner.HydraceptClient",
        return_value=FakeClient(),
    ), patch("hydracept.cli.smoke_runner.time.sleep", MagicMock()), patch(
        "hydracept.cli.smoke_contract.inspect_png_transparency",
        return_value=_fake_transparency(),
    ):
        result = run_smoke(tmp_path)

    assert captured["key"] == "image.generate.v1"
    assert captured["body"]["context"]["productId"] == "cpr_smoke_test"
    assert captured["body"]["context"]["projectId"] == "cpr_smoke_test"
    assert captured["body"]["input"]["requestTransparentOutput"] is True
    assert result.job_id == "wfr_test"
    assert result.sha256_ok
    assert result.pricing_ok
    assert (tmp_path / ".hydracept" / "output" / "art_test.png").is_file()
    assert (tmp_path / ".hydracept" / "demo" / "first-asset.png").is_file()
    payload = result.to_json()
    assert payload["status"] == "ok"
    assert payload["jobId"] == "wfr_test"
    assert payload["exitCode"] == 0


def test_run_smoke_persists_png_when_receipt_contract_fails(tmp_path: Path) -> None:
    class FakeClient:
        def submit_capability_job(self, key: str, body: dict) -> dict:
            return {"jobId": "wfr_malformed"}

        def get_job(self, job_id: str) -> dict:
            return {"status": "succeeded"}

        def download_job_artifact(self, job_id: str, artifact_id: str) -> bytes:
            return PNG_BYTES

        def get_job_receipt(self, job_id: str) -> dict:
            digest = hashlib.sha256(PNG_BYTES).hexdigest()
            return {
                "receiptId": "rcpt_bad",
                "artifacts": [{"id": "art_kept", "sha256": digest}],
                "pricing": {"actualCharge": {"amountMicros": 50000, "currency": "USD"}},
            }

    with patch(
        "hydracept.cli.smoke_runner.require_ready_workspace",
        return_value=_workspace(),
    ), patch(
        "hydracept.cli.smoke_runner.HydraceptClient",
        return_value=FakeClient(),
    ), patch("hydracept.cli.smoke_runner.time.sleep", MagicMock()), patch(
        "hydracept.cli.smoke_contract.inspect_png_transparency",
        return_value=_fake_transparency(),
    ):
        with pytest.raises(SmokeError) as caught:
            run_smoke(tmp_path)

    exc = caught.value
    assert exc.job_id == "wfr_malformed"
    assert exc.receipt_id == "rcpt_bad"
    assert "art_kept" in exc.artifact_ids
    saved = tmp_path / ".hydracept" / "output" / "art_kept.png"
    assert saved.is_file()
    assert saved.read_bytes() == PNG_BYTES
    demo = tmp_path / ".hydracept" / "demo" / "first-asset.png"
    assert demo.is_file()
    assert demo.read_bytes() == PNG_BYTES
    payload = exc.to_json()
    assert payload["jobId"] == "wfr_malformed"
    assert payload["receiptId"] == "rcpt_bad"
    assert payload["exitCode"] == 7
    assert payload["demoPath"] == str(demo)
    assert any(str(saved) == path for path in payload["downloads"])


def test_run_smoke_fails_when_receipt_sha256_missing(tmp_path: Path) -> None:
    class FakeClient:
        def submit_capability_job(self, key: str, body: dict) -> dict:
            return {"jobId": "wfr_test"}

        def get_job(self, job_id: str) -> dict:
            return {"status": "succeeded"}

        def download_job_artifact(self, job_id: str, artifact_id: str) -> bytes:
            return PNG_BYTES

        def get_job_receipt(self, job_id: str) -> dict:
            return {
                "artifacts": [{"artifactId": "art_test"}],
                "pricing": {
                    "charge": {
                        "customerCharge": {"amountMicros": 44000, "currency": "USD"}
                    }
                },
            }

    with patch(
        "hydracept.cli.smoke_runner.require_ready_workspace",
        return_value=_workspace(),
    ), patch(
        "hydracept.cli.smoke_runner.HydraceptClient",
        return_value=FakeClient(),
    ), patch("hydracept.cli.smoke_runner.time.sleep", MagicMock()):
        with pytest.raises(SmokeError) as caught:
            run_smoke(tmp_path)
        assert "SHA-256" in str(caught.value)
        assert caught.value.job_id == "wfr_test"
        assert (tmp_path / ".hydracept" / "output" / "art_test.png").is_file()


def test_run_sheet_smoke_uses_public_image_capability(tmp_path: Path) -> None:
    captured: dict = {}
    digest = hashlib.sha256(PNG_BYTES).hexdigest()

    class FakeClient:
        def submit_capability_job(self, key: str, body: dict) -> dict:
            captured["key"] = key
            captured["body"] = body
            return {"jobId": "wfr_sheet"}

        def get_job(self, job_id: str) -> dict:
            return {"status": "succeeded"}

        def download_job_artifact(self, job_id: str, artifact_id: str) -> bytes:
            return PNG_BYTES

        def get_job_receipt(self, job_id: str) -> dict:
            artifacts = [{"id": f"art_{i}", "sha256": digest} for i in range(4)]
            return {
                "receiptId": "rcpt_sheet",
                "artifacts": artifacts,
                "media": {"sheet": {"rows": 2, "columns": 2, "cells": [{}, {}, {}, {}]}},
                "pricing": {
                    "charge": {
                        "customerCharge": {"amountMicros": 44000, "currency": "USD"}
                    }
                },
            }

    with patch(
        "hydracept.cli.smoke_runner.require_ready_workspace",
        return_value=_workspace(),
    ), patch(
        "hydracept.cli.smoke_runner.HydraceptClient",
        return_value=FakeClient(),
    ), patch("hydracept.cli.smoke_runner.time.sleep", MagicMock()), patch(
        "hydracept.cli.smoke_contract.inspect_png_transparency",
        return_value=_fake_transparency(),
    ):
        result = run_sheet_smoke(tmp_path)

    assert captured["key"] == DEFAULT_SMOKE_CAPABILITY
    assert captured["body"]["input"]["sheet"]["slice"] is True
    assert captured["body"]["input"]["width"] == SHEET_SMOKE_COLUMNS * SHEET_MIN_CELL_PX
    assert result.job_id == "wfr_sheet"
    assert len(result.artifact_ids) == 4
