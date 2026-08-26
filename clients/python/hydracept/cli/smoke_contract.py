"""Image smoke contract: identity + receipt SHA-256 + downloaded bytes + pricing + PNG alpha."""

from __future__ import annotations

import hashlib
from typing import Any

from hydracept.png_alpha import PngTransparencyError, inspect_png_transparency


class SmokeContractError(ValueError):
    """Raised when a smoke job fails the public image contract."""


def artifact_sha256(item: dict[str, Any]) -> str:
    digest = item.get("sha256") or item.get("sha256Hex")
    if isinstance(digest, str) and digest:
        return digest.lower()
    nested = item.get("digest") or item.get("content") or {}
    if isinstance(nested, dict):
        value = nested.get("sha256") or nested.get("sha256Hex")
        if isinstance(value, str) and value:
            return value.lower()
    return ""


def pricing_charge_present(receipt: dict[str, Any] | None) -> bool:
    if not receipt:
        return False
    pricing = receipt.get("pricing") or {}
    charge = pricing.get("charge") or {}
    customer = charge.get("customerCharge") or {}
    return customer.get("amountMicros") is not None or customer.get("amountMinor") is not None


def receipt_artifact_item(receipt: dict[str, Any], artifact_id: str) -> dict[str, Any] | None:
    artifacts = receipt.get("artifacts") or []
    if not isinstance(artifacts, list):
        return None
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        ident = str(item.get("id") or item.get("artifactId") or "")
        if ident == artifact_id:
            return item
    return None


def evaluate_image_smoke_contract(
    receipt: dict[str, Any] | None,
    *,
    artifact_id: str,
    data: bytes,
    verify_transparency: bool = True,
) -> dict[str, bool]:
    """Prove download integrity, pricing.charge, and PNG transparency.

    Receipt artifact identity, receipt SHA-256, and SHA-256(downloaded bytes)
    must all agree. A missing receipt hash is a failure.
    """
    if not receipt:
        raise SmokeContractError("missing receipt")
    if not artifact_id:
        raise SmokeContractError("missing artifact identity")
    item = receipt_artifact_item(receipt, artifact_id)
    if item is None:
        raise SmokeContractError(f"receipt missing artifact {artifact_id}")
    expected_sha = artifact_sha256(item)
    if not expected_sha:
        raise SmokeContractError("receipt missing SHA-256 for artifact")
    actual_sha = hashlib.sha256(data).hexdigest()
    if expected_sha != actual_sha:
        raise SmokeContractError(
            f"Download integrity failed: receipt SHA-256 {expected_sha} != downloaded {actual_sha}"
        )
    if not pricing_charge_present(receipt):
        raise SmokeContractError("Receipt missing pricing.charge.customerCharge")
    transparency_ok = False
    if verify_transparency:
        try:
            inspect_png_transparency(data)
            transparency_ok = True
        except PngTransparencyError as exc:
            raise SmokeContractError(f"Transparency contract failed: {exc}") from exc
    return {
        "sha256_ok": True,
        "pricing_ok": True,
        "transparency_ok": transparency_ok or (not verify_transparency),
    }
