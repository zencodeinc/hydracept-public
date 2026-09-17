"""Conformance fixtures for hydracept.run-result.v1."""

from __future__ import annotations

from hydracept.run_result import RunArtifact, RunPricing, RunResult, TypedRunError


def _assert_common(payload: dict) -> None:
    assert payload["schemaVersion"] == "hydracept.run-result.v1"
    assert "capability" in payload
    assert "status" in payload
    assert "pricing" in payload
    assert "customerChargeUsd" in payload["pricing"]
    assert "chargeState" in payload["pricing"]
    assert "billingMode" in payload["pricing"]
    assert "providerCostUsd" in payload["pricing"]
    assert payload["pricing"]["providerCostBasis"] == "upstream-price-basis"
    assert "estimatedProviderCostUsd" in payload["pricing"]
    assert "estimatedCustomerChargeUsd" in payload["pricing"]
    # Generic actualCost/estimatedCost are not part of the consumer contract, and
    # no pricing field is named as a retail/list price (ADR-022).
    assert "actualCost" not in payload["pricing"]
    assert "estimatedCost" not in payload["pricing"]
    assert not [key for key in payload["pricing"] if "retail" in key.lower()]
    assert "summary" in payload["pricing"]
    assert "customerCharge" in payload["pricing"]
    assert "customerTotalMicros" in payload["pricing"]["customerCharge"]
    assert "idempotencyKey" in payload
    assert isinstance(payload["artifacts"], list)


def test_fixture_sync_text_success() -> None:
    result = RunResult(
        capability="text.general.fast.v1",
        job_id="fex_text",
        execution_id="fex_text",
        status="succeeded",
        output={"text": "ok"},
        typed_output={"text": "ok"},
        pricing=RunPricing(estimated_cost=0.000006, actual_cost=0.000006),
        idempotency_key="run-1",
    )
    payload = result.to_dict()
    _assert_common(payload)
    assert payload["status"] == "succeeded"
    assert payload["artifacts"] == []
    assert payload["pricing"]["estimatedCustomerChargeUsd"] == 0.000006
    assert payload["pricing"]["customerChargeUsd"] is None


def test_fixture_durable_image_success() -> None:
    result = RunResult(
        capability="image.generate.v1",
        job_id="wfr_img",
        status="succeeded",
        artifacts=[
            RunArtifact(
                artifact_id="art_1",
                media_type="image/png",
                sha256="abc",
                byte_length=12,
                remote_ref="/v1/jobs/wfr_img/artifacts/art_1",
                local_path=".hydracept/output/wfr_img/art_1.png",
                verified=True,
            )
        ],
        pricing=RunPricing(estimated_cost=0.05, actual_cost=0.05),
        receipt={"receiptId": "rcpt_1"},
        idempotency_key="run-2",
    )
    payload = result.to_dict()
    _assert_common(payload)
    assert payload["artifacts"][0]["localPath"]
    assert payload["artifacts"][0]["verified"] is True


def test_fixture_no_wait_running() -> None:
    result = RunResult(
        capability="image.generate.v1",
        job_id="wfr_run",
        status="running",
        artifacts=[],
        pricing=RunPricing(estimated_cost=0.05, actual_cost=None),
        idempotency_key="run-3",
    )
    payload = result.to_dict()
    _assert_common(payload)
    assert payload["status"] == "running"
    assert payload["artifacts"] == []
    assert payload["pricing"]["customerChargeUsd"] is None
    assert payload["pricing"]["providerCostUsd"] is None


def test_fixture_terminal_provider_failure() -> None:
    result = RunResult(
        capability="image.generate.v1",
        job_id="wfr_fail",
        status="failed",
        artifacts=[],
        pricing=RunPricing(estimated_cost=0.05, actual_cost=None),
        idempotency_key="run-4",
        error={"code": "ProviderRejected", "message": "safety"},
    )
    payload = result.to_dict()
    _assert_common(payload)
    assert payload["status"] == "failed"
    assert payload["jobId"] == "wfr_fail"
    assert payload["error"]["code"] == "ProviderRejected"


def test_fixture_max_cost_pre_admission() -> None:
    err = TypedRunError(
        code="EstimateExceedsMaxCost",
        message="estimate exceeds maxCost",
        details={"estimatedCost": 0.05, "maxCostUsd": 0.01},
        http_status=402,
    )
    payload = err.to_dict()
    assert payload["error"] is True
    assert payload["code"] == "EstimateExceedsMaxCost"
    assert "jobId" not in payload


def test_fixture_funding_required() -> None:
    err = TypedRunError(
        code="FundingRequired",
        message="connect a provider",
        details={"managedWalletTopUpLive": False, "options": ["trial", "byok"]},
        http_status=402,
    )
    payload = err.to_dict()
    assert payload["code"] == "FundingRequired"
    assert payload["details"]["managedWalletTopUpLive"] is False
    assert "byok" in payload["details"]["options"]


def test_fixture_artifact_persist_failure_keeps_recovery() -> None:
    result = RunResult(
        capability="image.generate.v1",
        job_id="wfr_ok",
        status="succeeded",
        artifacts=[
            RunArtifact(
                artifact_id="art_1",
                media_type="image/png",
                sha256="abc",
                remote_ref="/v1/jobs/wfr_ok/artifacts/art_1",
                local_path=None,
                verified=False,
            )
        ],
        pricing=RunPricing(estimated_cost=0.05, actual_cost=0.05),
        receipt={"receiptId": "rcpt_ok"},
        idempotency_key="run-5",
        error={"code": "ArtifactPersistFailed", "message": "SHA mismatch"},
        diagnostics={"recovery": {"jobId": "wfr_ok", "cli": "python -m hydracept jobs recover wfr_ok"}},
    )
    payload = result.to_dict()
    _assert_common(payload)
    assert payload["jobId"] == "wfr_ok"
    assert payload["diagnostics"]["recovery"]["jobId"] == "wfr_ok"
    assert payload["error"]["code"] == "ArtifactPersistFailed"
