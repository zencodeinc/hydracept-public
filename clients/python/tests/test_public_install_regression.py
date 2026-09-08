"""Public-install first-success fixture pair (review 26 Aug).

1. Settled managed image receipt + canonical API dump → persist PNG, exit 0.
2. Successful PNG bytes + malformed receipt → persist PNG + jobId, exit 7.

CLI 0.3.1 smoke reads only pricing.charge.customerCharge — do not add actualCharge.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hydracept.cli.exit_codes import SMOKE_FAILED
from hydracept.cli.smoke_contract import pricing_charge_present
from hydracept.cli.smoke_runner import SmokeError, run_smoke
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


def _cli_031_pricing_charge_present(receipt: dict | None) -> bool:
    """Frozen 0.3.1 predicate. Do not accept actualCharge here."""
    if not receipt:
        return False
    pricing = receipt.get("pricing") or {}
    charge = pricing.get("charge") or {}
    customer = charge.get("customerCharge") or {}
    return customer.get("amountMicros") is not None or customer.get("amountMinor") is not None


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


def _canonical_settled_receipt(artifact_id: str) -> dict:
    digest = hashlib.sha256(PNG_BYTES).hexdigest()
    settled = {"amountMicros": 50000, "amountMinor": 5, "currency": "USD"}
    dumped = {
        "receiptId": "rcpt_ok",
        "jobId": "wfr_ok",
        "capabilityKey": "image.generate.v1",
        "status": "succeeded",
        "actualCost": 0.05,
        "pricing": {
            "mode": "managed",
            "actualCharge": settled,
            "charge": {"customerCharge": settled},
        },
        "artifacts": [{"id": artifact_id, "sha256": digest}],
    }
    assert _cli_031_pricing_charge_present(dumped)
    assert pricing_charge_present(dumped)
    return dumped


def test_settled_managed_receipt_persists_png_and_passes_031_contract(tmp_path: Path) -> None:
    dumped = _canonical_settled_receipt("art_ok")

    class FakeClient:
        def submit_capability_job(self, key: str, body: dict) -> dict:
            return {"jobId": "wfr_ok"}

        def get_job(self, job_id: str) -> dict:
            return {"status": "succeeded"}

        def download_job_artifact(self, job_id: str, artifact_id: str) -> bytes:
            return PNG_BYTES

        def get_job_receipt(self, job_id: str) -> dict:
            return dumped

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

    saved = tmp_path / ".hydracept" / "output" / "art_ok.png"
    assert result.job_id == "wfr_ok"
    assert result.pricing_ok
    assert saved.is_file()
    assert saved.read_bytes() == PNG_BYTES


def test_malformed_receipt_keeps_png_and_job_id_exit_7(tmp_path: Path) -> None:
    malformed = {
        "receiptId": "rcpt_bad",
        "artifacts": [{"id": "art_kept", "sha256": hashlib.sha256(PNG_BYTES).hexdigest()}],
        "pricing": {"actualCharge": {"amountMicros": 50000, "currency": "USD"}},
    }
    assert _cli_031_pricing_charge_present(malformed) is False

    class FakeClient:
        def submit_capability_job(self, key: str, body: dict) -> dict:
            return {"jobId": "wfr_malformed"}

        def get_job(self, job_id: str) -> dict:
            return {"status": "succeeded"}

        def download_job_artifact(self, job_id: str, artifact_id: str) -> bytes:
            return PNG_BYTES

        def get_job_receipt(self, job_id: str) -> dict:
            return malformed

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
    assert exc.exit_code == SMOKE_FAILED
    assert exc.status == "contract_failed"
    assert exc.execution_status == "succeeded"
    payload = exc.to_json()
    assert payload["jobId"] == "wfr_malformed"
    assert payload["status"] == "contract_failed"
    assert payload["execution"]["status"] == "succeeded"
    assert payload["validation"]["status"] == "failed"
    assert payload["validation"]["code"] == "receipt_pricing_validation_failed"
    assert payload["exitCode"] == 7
    saved = tmp_path / ".hydracept" / "output" / "art_kept.png"
    assert saved.is_file()
    assert saved.read_bytes() == PNG_BYTES
