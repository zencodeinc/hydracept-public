"""hydracept.run-result.v1 — client façade contract shared by CLI, SDK, and MCP."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "estimatedCost": self.estimated_cost,
            "actualCost": self.actual_cost,
            "currency": self.currency,
            "reservedCost": self.reserved_cost,
        }


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
            "receipt": self.receipt,
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

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error": True,
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }
        if self.http_status is not None:
            payload["httpStatus"] = self.http_status
        if self.recovery:
            payload["recovery"] = self.recovery
        return payload
