"""Unified public job and receipt contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from hydracept_contracts.digests import normalize_sha256_digest
from hydracept_contracts.job_wait import job_wait_hints
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


class HydraceptJob(BaseModel):
    job_id: str = Field(alias="jobId")
    capability_key: str = Field(alias="capabilityKey")
    status: HydraceptJobStatus
    created_at: datetime | None = Field(default=None, alias="createdAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    estimated_cost: float | None = Field(default=None, alias="estimatedCost")
    actual_cost: float | None = Field(default=None, alias="actualCost")
    currency: str = "USD"
    artifacts: list[HydraceptJobArtifactRef] = Field(default_factory=list)
    variant_set: HydraceptVariantSet | None = Field(default=None, alias="variantSet")
    receipt_id: str | None = Field(default=None, alias="receiptId")
    typed_output: Any | None = Field(default=None, alias="typedOutput")
    error: dict[str, Any] | None = None
    diagnostics: HydraceptJobDiagnostics | None = None
    request_snapshot: dict[str, Any] | None = Field(
        default=None,
        alias="requestSnapshot",
        description="Canonical submitted request for Studio re-run (not receipt).",
    )
    next_action: str | None = Field(default=None, alias="nextAction")
    poll_after_seconds: int | None = Field(default=None, alias="pollAfterSeconds")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def fill_wait_hints(self) -> HydraceptJob:
        if self.next_action:
            return self
        hints = job_wait_hints(str(self.status))
        self.next_action = str(hints["nextAction"])
        poll_after = hints.get("pollAfterSeconds")
        self.poll_after_seconds = int(poll_after) if poll_after is not None else None
        return self


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
    environment: str | None = None
    admission: HydraceptReceiptAdmission | None = None
    route: HydraceptReceiptRoute | None = None
    estimated_cost: float = Field(
        default=0.0,
        alias="estimatedCost",
        description="Deprecated 0.2 shim of pricing.quote.customerTotal. Do not use internally.",
    )
    actual_cost: float = Field(
        default=0.0,
        alias="actualCost",
        description="Deprecated 0.2 shim of pricing.charge.customerCharge. Do not use internally.",
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
        self.estimated_cost = quote_total.as_usd_float() if quote_total is not None else 0.0
        self.actual_cost = charge_total.as_usd_float() if charge_total is not None else 0.0
        return self


# Preferred public names (internal Forge* names retained for implementation modules).
