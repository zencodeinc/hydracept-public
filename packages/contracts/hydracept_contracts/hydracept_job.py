"""Unified public job and receipt contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_serializer, model_validator

from hydracept_contracts.digests import normalize_sha256_digest
from hydracept_contracts.job_wait import job_retry_guidance
from hydracept_contracts.pricing import CustomerSavings, HydraceptReceiptPricing
from hydracept_contracts.routing_policy import RoutingSelection


class HydraceptJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELING = "canceling"
    CANCELED = "canceled"
    NEEDS_ATTENTION = "needs_attention"

    @classmethod
    def waiting_values(cls) -> tuple[str, ...]:
        return (cls.QUEUED.value, cls.RUNNING.value, cls.CANCELING.value)

    @classmethod
    def terminal_values(cls) -> tuple[str, ...]:
        return (
            cls.SUCCEEDED.value,
            cls.FAILED.value,
            cls.CANCELED.value,
            cls.AWAITING_APPROVAL.value,
            cls.NEEDS_ATTENTION.value,
        )

    @classmethod
    def human_gate_values(cls) -> tuple[str, ...]:
        return (cls.AWAITING_APPROVAL.value, cls.NEEDS_ATTENTION.value)


class HydraceptJobDiagnostics(BaseModel):
    backend_kind: str = Field(alias="backendKind")
    backend_state: str = Field(alias="backendState")
    backend_id: str = Field(alias="backendId")

    model_config = {"populate_by_name": True}


class HydraceptVariantSet(BaseModel):
    schema_version: str = Field(default="hydracept.variant-set.v1", alias="schemaVersion")
    requested_count: int = Field(alias="requestedCount")
    completed_count: int = Field(alias="completedCount")
    failed_count: int = Field(alias="failedCount")
    selected_artifact_id: str | None = Field(default=None, alias="selectedArtifactId")

    model_config = {"populate_by_name": True}


class HydraceptJobArtifactRef(BaseModel):
    artifact_id: str = Field(alias="artifactId")
    media_type: str = Field(alias="mediaType")
    kind: str
    download_path: str | None = Field(default=None, alias="downloadPath")
    sha256: str | None = None
    byte_length: int | None = Field(default=None, alias="byteLength")
    variant_index: int | None = Field(default=None, alias="variantIndex")
    slot_status: str | None = Field(default=None, alias="slotStatus")
    selected: bool | None = None
    label: str | None = None
    filename: str | None = None
    slice_cell_id: str | None = Field(default=None, alias="sliceCellId")

    model_config = {"populate_by_name": True}

    @field_validator("sha256", mode="before")
    @classmethod
    def _public_sha256(cls, value: object) -> str | None:
        """Emit hex only; artifact store keys may be advertised as sha256:<hex>."""
        if value is None:
            return None
        digest = normalize_sha256_digest(str(value))
        return digest or None

    @model_serializer(mode="wrap")
    def _omit_unselected_flag(self, serializer):
        data = serializer(self)
        if data.get("selected") is None:
            data.pop("selected", None)
        return data


class HydraceptJob(BaseModel):
    job_id: str = Field(alias="jobId")
    capability_key: str = Field(alias="capabilityKey")
    status: HydraceptJobStatus
    project_id: str | None = Field(default=None, alias="projectId")
    product_id: str | None = Field(default=None, alias="productId")
    created_at: datetime | None = Field(default=None, alias="createdAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    estimated_cost: float | None = Field(default=None, alias="estimatedCost")
    actual_cost: float | None = Field(default=None, alias="actualCost")
    currency: str = "USD"
    artifacts: list[HydraceptJobArtifactRef] = Field(default_factory=list)
    variant_set: HydraceptVariantSet | None = Field(default=None, alias="variantSet")
    receipt_id: str | None = Field(default=None, alias="receiptId")
    primary_artifact_id: str | None = Field(default=None, alias="primaryArtifactId")
    typed_output: Any | None = Field(default=None, alias="typedOutput")
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    error: dict[str, Any] | None = None
    diagnostics: HydraceptJobDiagnostics | None = None
    request_snapshot: dict[str, Any] | None = Field(
        default=None,
        alias="requestSnapshot",
        description="Canonical submitted request for Studio re-run (not receipt).",
    )
    next_action: str | None = Field(default=None, alias="nextAction")
    poll_after_seconds: int | None = Field(default=None, alias="pollAfterSeconds")
    retry: dict[str, Any] | None = None
    approval: dict[str, Any] | None = Field(
        default=None,
        description="Sanitized human-gate payload. Present only while the job awaits approval.",
    )

    model_config = {"populate_by_name": True}

    @field_validator("error", mode="before")
    @classmethod
    def normalize_error(cls, value: object) -> dict[str, Any] | None:
        """Keep one stable public error shape even when a backend has only a code.

        Job-list history intentionally exposes only ``errorCode``. Once a caller
        explicitly inspects one job, the public job contract guarantees both a
        machine-stable code and human-readable message.
        """
        if value is None:
            return None
        if isinstance(value, dict):
            normalized = dict(value)
            code = str(normalized.get("code") or "failed").strip() or "failed"
            raw_message = normalized.get("message")
            message = str(raw_message).strip() if raw_message is not None else ""
            if not message or message == code:
                message = f"Job failed with error code {code}."
            normalized["code"] = code
            normalized["message"] = message
            return normalized
        message = str(value).strip() or "Job failed."
        return {"code": "failed", "message": message}

    @model_validator(mode="after")
    def fill_wait_hints(self) -> HydraceptJob:
        if self.next_action and self.retry is not None:
            return self
        hints = job_retry_guidance(
            status=str(self.status),
            error_code=(self.error or {}).get("code") if isinstance(self.error, dict) else None,
        )
        if not self.next_action:
            self.next_action = str(hints["nextAction"])
        poll_after = hints.get("pollAfterSeconds")
        if self.poll_after_seconds is None:
            self.poll_after_seconds = int(poll_after) if poll_after is not None else None
        if self.retry is None:
            retry = hints.get("retry")
            self.retry = dict(retry) if isinstance(retry, dict) else None
        return self


class HydraceptJobResult(BaseModel):
    """First-class job result projection — typed output plus payload identity."""

    job_id: str = Field(alias="jobId")
    status: HydraceptJobStatus
    typed_output: Any | None = Field(default=None, alias="typedOutput")
    output_payload_ref: str | None = Field(default=None, alias="outputPayloadRef")
    payload_state: str | None = Field(default=None, alias="payloadState")
    artifacts: list[HydraceptJobArtifactRef] = Field(default_factory=list)
    error: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class HydraceptReceiptAdmission(BaseModel):
    admitted: bool
    rejection_code: str | None = Field(default=None, alias="rejectionCode")
    rejection_message: str | None = Field(default=None, alias="rejectionMessage")

    model_config = {"populate_by_name": True}


class HydraceptReceiptRoute(BaseModel):
    provider: str | None = None
    model: str | None = None
    route_bundle_version: str | None = Field(default=None, alias="routeBundleVersion")
    route_bundle_hash: str | None = Field(default=None, alias="routeBundleHash")

    model_config = {"populate_by_name": True}


class HydraceptReceiptTimestamps(BaseModel):
    created_at: datetime | None = Field(default=None, alias="createdAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")

    model_config = {"populate_by_name": True}


class HydraceptReceiptProvenance(BaseModel):
    bundle_version: str | None = Field(default=None, alias="bundleVersion")
    bundle_hash: str | None = Field(default=None, alias="bundleHash")
    policy_hash: str | None = Field(default=None, alias="policyHash")
    receipt_hash: str | None = Field(default=None, alias="receiptHash")

    model_config = {"populate_by_name": True}


class HydraceptReceipt(BaseModel):
    receipt_id: str = Field(alias="receiptId")
    job_id: str = Field(alias="jobId")
    capability_key: str = Field(alias="capabilityKey")
    principal_id: str | None = Field(default=None, alias="principalId")
    project_id: str | None = Field(default=None, alias="projectId")
    product_id: str | None = Field(default=None, alias="productId")
    environment: str | None = None
    admission: HydraceptReceiptAdmission | None = None
    route: HydraceptReceiptRoute | None = None
    estimated_cost: float | None = Field(
        default=None,
        alias="estimatedCost",
        description="Deprecated 0.2 shim of pricing.quote.customerTotal. Do not use internally.",
    )
    actual_cost: float | None = Field(
        default=None,
        alias="actualCost",
        description="Deprecated 0.2 shim of pricing.charge.customerCharge (amount owed). Do not use internally.",
    )
    currency: str = "USD"
    artifacts: list[HydraceptJobArtifactRef] = Field(default_factory=list)
    timestamps: HydraceptReceiptTimestamps | None = None
    status: HydraceptJobStatus | str
    provenance: HydraceptReceiptProvenance | None = None
    text: dict[str, Any] | None = None
    media: dict[str, Any] | None = None
    pricing: HydraceptReceiptPricing | None = None
    routing: RoutingSelection | None = None
    customer_savings: CustomerSavings | None = Field(default=None, alias="customerSavings")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _project_legacy_cost_floats(self) -> HydraceptReceipt:
        pricing = self.pricing
        if pricing is None:
            return self
        quote_total = pricing.quote.customer_total if pricing.quote else None
        charge_total = pricing.charge.customer_charge if pricing.charge else None
        self.estimated_cost = quote_total.as_usd_float() if quote_total is not None else None
        self.actual_cost = charge_total.as_usd_float() if charge_total is not None else None
        return self

    @model_serializer(mode="wrap")
    def _omit_duplicate_estimate_id(self, serializer):
        data = serializer(self)
        pricing = data.get("pricing")
        if (
            isinstance(pricing, dict)
            and pricing.get("quoteId")
            and pricing.get("estimateId") == pricing.get("quoteId")
        ):
            pricing = dict(pricing)
            pricing.pop("estimateId", None)
            data["pricing"] = pricing
        return data


_SHEET_PRIMARY_KINDS = frozenset(
    {
        "composite-sheet",
        "contact-preview",
        "sheet",
        "contact-sheet",
    }
)


def resolve_primary_artifact_id(
    artifacts: list[HydraceptJobArtifactRef],
    variant_set: HydraceptVariantSet | None = None,
) -> str | None:
    """Default usable output without choosing among peers.

    Genuine variant/user selection remains ``variantSet.selectedArtifactId`` /
    ``artifacts[].selected``. A single ordinary output is primary and does not
    set ``selected``.
    """
    if variant_set is not None and variant_set.selected_artifact_id:
        return variant_set.selected_artifact_id
    chosen = [item for item in artifacts if item.selected is True]
    if len(chosen) == 1:
        return chosen[0].artifact_id
    if variant_set is not None and variant_set.requested_count > 1 and not chosen:
        return None
    sheet_primaries = [
        item for item in artifacts if str(item.kind or "") in _SHEET_PRIMARY_KINDS
    ]
    if len(sheet_primaries) == 1:
        return sheet_primaries[0].artifact_id
    sliced = [item for item in artifacts if item.slice_cell_id]
    if len(sliced) > 1 and not sheet_primaries:
        return None
    outputs = [item for item in artifacts if item.artifact_id]
    if len(outputs) == 1:
        return outputs[0].artifact_id
    return None


_SEALED_RECEIPT_STATUSES = frozenset(
    {
        HydraceptJobStatus.SUCCEEDED.value,
        HydraceptJobStatus.FAILED.value,
        HydraceptJobStatus.CANCELED.value,
    }
)


def workflow_receipt_id_for_status(run_id: str, status: HydraceptJobStatus) -> str | None:
    """``rcpt_{run.id}`` only when a sealed receipt exists — not human-gate states."""
    if str(status) not in _SEALED_RECEIPT_STATUSES:
        return None
    return f"rcpt_{run_id}"


# Preferred public names (internal Forge* names retained for implementation modules).