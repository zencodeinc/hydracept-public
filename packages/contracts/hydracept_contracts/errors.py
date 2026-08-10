"""Normalized Hydracept error taxonomy for runtime and durable APIs."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class HydraceptErrorCode(StrEnum):
    AUTHENTICATION_FAILED = "AuthenticationFailed"
    AUTHORIZATION_FAILED = "AuthorizationFailed"
    CAPABILITY_NOT_ALLOWED = "CapabilityNotAllowed"
    POLICY_REJECTED = "PolicyRejected"
    BUDGET_EXCEEDED = "BudgetExceeded"
    PAUSED = "Paused"
    RATE_LIMITED = "RateLimited"
    PROVIDER_UNAVAILABLE = "ProviderUnavailable"
    PROVIDER_REJECTED = "ProviderRejected"
    PROVIDER_TIMEOUT = "ProviderTimeout"
    EXECUTION_TIMEOUT = "ExecutionTimeout"
    CANCELLED = "Cancelled"
    PAYLOAD_UNAVAILABLE = "PayloadUnavailable"
    STRUCTURED_OUTPUT_INVALID = "StructuredOutputInvalid"
    STRUCTURED_OUTPUT_REPAIR_FAILED = "StructuredOutputRepairFailed"
    RETENTION_VIOLATION = "RetentionViolation"
    IDEMPOTENCY_CONFLICT = "IdempotencyConflict"
    ESTIMATE_UNAVAILABLE = "EstimateUnavailable"
    INTERNAL_FAILURE = "InternalFailure"


# Codes that clients may safely retry after backoff.
RETRYABLE_ERROR_CODES: frozenset[HydraceptErrorCode] = frozenset(
    {
        HydraceptErrorCode.RATE_LIMITED,
        HydraceptErrorCode.PROVIDER_UNAVAILABLE,
        HydraceptErrorCode.PROVIDER_TIMEOUT,
        HydraceptErrorCode.INTERNAL_FAILURE,
    }
)


class HydraceptError(BaseModel):
    """Stable failure payload returned by runtime APIs."""

    code: HydraceptErrorCode
    message: str
    retryable: bool = False
    execution_id: str | None = Field(default=None, alias="executionId")
    receipt_id: str | None = Field(default=None, alias="receiptId")
    correlation_id: str | None = Field(default=None, alias="correlationId")
    details: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    @classmethod
    def of(
        cls,
        code: HydraceptErrorCode,
        message: str,
        *,
        execution_id: str | None = None,
        receipt_id: str | None = None,
        correlation_id: str | None = None,
        details: dict[str, Any] | None = None,
        retryable: bool | None = None,
    ) -> HydraceptError:
        return cls(
            code=code,
            message=message,
            retryable=RETRYABLE_ERROR_CODES.__contains__(code)
            if retryable is None
            else retryable,
            execution_id=execution_id,
            receipt_id=receipt_id,
            correlation_id=correlation_id,
            details=details or {},
        )


# Preferred public names (internal Forge* names retained for implementation modules).
