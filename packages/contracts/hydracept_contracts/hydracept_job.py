"""Unified public job and receipt contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


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
    variant_index: int | None = Field(default=None, alias="variantIndex")
    slot_status: str | None = Field(default=None, alias="slotStatus")
    selected: bool | None = None

    model_config = {"populate_by_name": True}


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
    environment: str | None = None
    admission: HydraceptReceiptAdmission | None = None
    route: HydraceptReceiptRoute | None = None
    estimated_cost: float = Field(default=0.0, alias="estimatedCost")
    actual_cost: float = Field(default=0.0, alias="actualCost")
    currency: str = "USD"
    artifacts: list[HydraceptJobArtifactRef] = Field(default_factory=list)
    timestamps: HydraceptReceiptTimestamps | None = None
    status: HydraceptJobStatus | str
    provenance: HydraceptReceiptProvenance | None = None
    text: dict[str, Any] | None = None
    media: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


# Preferred public names (internal Forge* names retained for implementation modules).
