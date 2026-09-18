"""Text capability smoke runner tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from hydracept.cli.smoke_runner import SmokeError, run_text_smoke
from hydracept.cli.workspace import ResolvedWorkspace


def _workspace() -> ResolvedWorkspace:
    return ResolvedWorkspace(
        api_url="https://api.hydracept.com",
        token="hapt_test",
        project_id="cpr_text_smoke",
        environment="development",
    )


def _receipt(receipt_id: str = "rcpt_text") -> dict:
    return {
        "receiptId": receipt_id,
        "pricing": {
            "charge": {"customerCharge": {"amountMicros": 0, "currency": "USD"}},
        },
    }


def test_run_text_smoke_validates_output_and_receipt(tmp_path: Path) -> None:
    captured: dict = {}

    class FakeClient:
        def invoke_capability(self, key: str, body: dict) -> dict:
            captured["key"] = key
            captured["body"] = body
            return {
                "status": "succeeded",
                "executionId": "ex_text_1",
                "output": {"items": [{"id": "1", "translation": "Hola mundo"}]},
                "receipt": _receipt(),
            }

    with patch("hydracept.cli.smoke_runner.require_ready_workspace", return_value=_workspace()), patch(
        "hydracept.cli.smoke_runner.HydraceptClient", return_value=FakeClient()
    ):
        result = run_text_smoke(tmp_path)

    assert captured["key"] == "text.translate.v1"
    assert captured["body"]["input"]["targetLocale"] == "es"
    assert captured["body"]["input"]["items"] == [{"id": "1", "text": "Hello world"}]
    assert captured["body"]["idempotencyKey"]
    assert result.output_preview == "Hola mundo"
    assert result.pricing_ok
    assert result.receipt_id == "rcpt_text"
    payload = result.to_json()
    assert payload["status"] == "ok"
    assert payload["execution"]["jobId"] == "ex_text_1"
    assert payload["validation"]["pricingOk"] is True
    assert payload["exitCode"] == 0


def test_run_text_smoke_fails_loudly_on_empty_output(tmp_path: Path) -> None:
    class FakeClient:
        def invoke_capability(self, key: str, body: dict) -> dict:
            return {"status": "succeeded", "executionId": "ex_text_2"}

        def get_job_receipt(self, job_id: str) -> dict:
            return _receipt("rcpt_empty")

    with patch("hydracept.cli.smoke_runner.require_ready_workspace", return_value=_workspace()), patch(
        "hydracept.cli.smoke_runner.HydraceptClient", return_value=FakeClient()
    ):
        with pytest.raises(SmokeError) as caught:
            run_text_smoke(tmp_path)

    assert caught.value.status == "contract_failed"
    assert caught.value.validation_code == "text_output_empty"
    assert caught.value.job_id == "ex_text_2"


def test_run_text_smoke_reports_execution_failure(tmp_path: Path) -> None:
    class FakeClient:
        def invoke_capability(self, key: str, body: dict) -> dict:
            return {
                "status": "failed",
                "executionId": "ex_text_3",
                "error": {"message": "all providers unavailable"},
            }

    with patch("hydracept.cli.smoke_runner.require_ready_workspace", return_value=_workspace()), patch(
        "hydracept.cli.smoke_runner.HydraceptClient", return_value=FakeClient()
    ):
        with pytest.raises(SmokeError) as caught:
            run_text_smoke(tmp_path)

    assert caught.value.status == "execution_failed"
    assert "all providers unavailable" in str(caught.value)
