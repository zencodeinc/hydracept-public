"""hydracept.run-result.v1 — client façade contract shared by CLI, SDK, and MCP."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hydracept.receipt_cost import present_receipt

SCHEMA_VERSION = "hydracept.run-result.v1"


@dataclass
class RunArtifact:
    artifact_id: str
    media_type: str = "application/octet-stream"
    sha256: str | None = None
    byte_length: int | None = None
    remote_ref: str | None = None
    local_path: str | None = None
    verified: bool = False
    filename: str | None = None
    label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifactId": self.artifact_id,
            "mediaType": self.media_type,
            "sha256": self.sha256,
            "byteLength": self.byte_length,
            "remoteRef": self.remote_ref,
            "localPath": self.local_path,
            "verified": self.verified,
            "filename": self.filename,
            "label": self.label,
        }


@dataclass
class RunPricing:
    estimated_cost: float | None = None
    actual_cost: float | None = None
    currency: str = "USD"
    reserved_cost: float | None = None
    customer_total_micros: int | None = None
    provider_basis_micros: int | None = None
    estimated_provider_micros: int | None = None
    estimated_charge_micros: int | None = None
    financial_state: str | None = None
    mode: str | None = None
    provider_cost_micros: int | None = None
    managed_equivalent_micros: int | None = None
    estimated_provider_cost_micros: int | None = None
    service_fee_bps: int | None = None

    def charge_state(self) -> str:
        """Canonical post-execution charge state (single public vocabulary)."""
        from hydracept.receipt_cost import canonical_charge_state

        return canonical_charge_state(self.mode, self.customer_total_micros)

    def charge_expectation(self) -> str:
        """Canonical pre-execution charge expectation."""
        if (self.mode or "").strip().lower() == "byok":
            return "provider_billed_directly"
        if self.financial_state == "covered":
            return "covered"
        return "charged"

    def to_dict(self) -> dict[str, Any]:
        from hydracept.receipt_cost import format_pricing_summary, micros_to_usd

        owed = micros_to_usd(self.customer_total_micros)
        basis = micros_to_usd(self.provider_basis_micros)
        if basis is None:
            basis = micros_to_usd(self.provider_cost_micros)
        estimated_provider = micros_to_usd(self.estimated_provider_micros)
        if estimated_provider is None:
            estimated_provider = micros_to_usd(self.estimated_provider_cost_micros)
        estimated_charge = micros_to_usd(self.estimated_charge_micros)
        if estimated_charge is None:
            estimated_charge = self.estimated_cost
        state = self.charge_state()
        billing_mode = (self.mode or "").strip().lower() or None
        summary = format_pricing_summary(owed, state, estimated_charge)
        payload: dict[str, Any] = {
            "customerCharge": {
                "customerTotalMicros": self.customer_total_micros,
                "amountMicros": self.customer_total_micros,
                "currency": self.currency,
                "state": state,
            },
            "customerChargeUsd": owed,
            "chargeState": state,
            "billingMode": billing_mode,
            "chargeExpectation": self.charge_expectation(),
            "managedEquivalentChargeUsd": micros_to_usd(self.managed_equivalent_micros),
            "providerCostUsd": basis,
            "providerCostBasis": "upstream-price-basis",
            "estimatedCustomerChargeUsd": estimated_charge,
            "summary": summary,
            "mode": self.mode,
            "currency": self.currency,
            "reservedCost": self.reserved_cost,
            "note": (
                "customerChargeUsd is what this customer was charged (0 when Hydracept covers it); "
                "providerCostUsd is the upstream provider price basis the charge was computed from, "
                "not a retail or list price; estimatedCustomerChargeUsd is a quote, never a charge; "
                "managedEquivalentChargeUsd is provider cost + 6%, not a retail list price. "
                "Hydracept's own procurement cost is not a customer field (ADR-022)."
            ),
        }
        if estimated_provider is not None or estimated_charge is not None:
            payload["estimatedProviderCostUsd"] = estimated_provider
        if self.service_fee_bps is not None:
            payload["managedFeePercent"] = self.service_fee_bps / 100.0
        if owed is None and basis is None and self.actual_cost is not None:
            # A receipt-less job reported an actual cost that no explicit field
            # covers. Keep it under an unambiguous name instead of dropping it.
            payload["legacyActualCostUsd"] = self.actual_cost
        return payload


@dataclass
class RunResult:
    schema_version: str = SCHEMA_VERSION
    capability: str = ""
    job_id: str | None = None
    execution_id: str | None = None
    status: str = "unknown"
    output: Any = None
    typed_output: Any = None
    artifacts: list[RunArtifact] = field(default_factory=list)
    pricing: RunPricing = field(default_factory=RunPricing)
    receipt: dict[str, Any] | None = None
    idempotency_key: str | None = None
    error: dict[str, Any] | None = None
    diagnostics: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "capability": self.capability,
            "jobId": self.job_id,
            "executionId": self.execution_id or self.job_id,
            "status": self.status,
            "output": self.output,
            "typedOutput": self.typed_output,
            "artifacts": [item.to_dict() for item in self.artifacts],
            "pricing": self.pricing.to_dict(),
            "receipt": present_receipt(self.receipt) if isinstance(self.receipt, dict) else self.receipt,
            "idempotencyKey": self.idempotency_key,
            "error": self.error,
            "diagnostics": self.diagnostics,
        }


@dataclass
class TypedRunError:
    """Pre-admission failure: no execution, not a RunResult."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    http_status: int | None = None
    recovery: dict[str, Any] = field(default_factory=dict)
    error_class: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error": True,
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }
        if self.error_class:
            payload["errorClass"] = self.error_class
        if self.http_status is not None:
            payload["httpStatus"] = self.http_status
        if self.recovery:
            payload["recovery"] = self.recovery
            next_action = self.recovery.get("nextAction") or self.recovery.get("cli")
            if next_action:
                payload["nextAction"] = next_action
        return payload
