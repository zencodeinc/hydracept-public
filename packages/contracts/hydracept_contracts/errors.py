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
    QUEUE_TIMEOUT = "QueueTimeout"
    TRANSPORT_AMBIGUOUS = "TRANSPORT_AMBIGUOUS"
    CANCELLED = "Cancelled"
    PAYLOAD_UNAVAILABLE = "PayloadUnavailable"
    STRUCTURED_OUTPUT_INVALID = "StructuredOutputInvalid"
    STRUCTURED_OUTPUT_REPAIR_FAILED = "StructuredOutputRepairFailed"
    RETENTION_VIOLATION = "RetentionViolation"
    IDEMPOTENCY_CONFLICT = "IdempotencyConflict"
    ESTIMATE_UNAVAILABLE = "EstimateUnavailable"
    PROMPT_TOO_LONG = "PromptTooLong"
    # The provider spent the whole output budget on reasoning and returned no
    # visible output. Terminal: retrying with the same budget reproduces it.
    REASONING_BUDGET_EXHAUSTED = "ReasoningBudgetExhausted"
    ESTIMATE_EXCEEDS_MAX_COST = "EstimateExceedsMaxCost"
    FUNDING_REQUIRED = "FundingRequired"
    PROJECT_CREDENTIAL_MISMATCH = "ProjectCredentialMismatch"
    QUOTE_MISMATCH = "QUOTE_MISMATCH"
    ESTIMATE_MISMATCH = "ESTIMATE_MISMATCH"
    REESTIMATE_REQUIRED = "REESTIMATE_REQUIRED"
    COST_LIMIT_EXCEEDED = "COST_LIMIT_EXCEEDED"
    ROUTE_UNAVAILABLE = "ROUTE_UNAVAILABLE"
    ROUTE_CASCADE_EXHAUSTED = "ROUTE_CASCADE_EXHAUSTED"
    PRICING_INPUTS_REQUIRED = "PRICING_INPUTS_REQUIRED"
    INVALID_INPUT = "InvalidInput"
    UNSUPPORTED_TLD = "UnsupportedTld"
    CATALOG_UNAVAILABLE = "CatalogUnavailable"
    UNKNOWN_EXECUTION_FIELD = "UNKNOWN_EXECUTION_FIELD"
    CONFLICTING_EXECUTION_CONSTRAINT = "CONFLICTING_EXECUTION_CONSTRAINT"
    INTERNAL_FAILURE = "InternalFailure"


# Codes that clients may safely retry after backoff.
RETRYABLE_ERROR_CODES: frozenset[HydraceptErrorCode] = frozenset(
    {
        HydraceptErrorCode.RATE_LIMITED,
        HydraceptErrorCode.PROVIDER_UNAVAILABLE,
        HydraceptErrorCode.PROVIDER_TIMEOUT,
        HydraceptErrorCode.CATALOG_UNAVAILABLE,
        HydraceptErrorCode.INTERNAL_FAILURE,
    }
)


from hydracept_contracts.public_error import public_error_content


class HydraceptError(BaseModel):
    """Stable failure payload returned by runtime APIs."""

    code: HydraceptErrorCode
    message: str
    retryable: bool = False
    next_action: str | None = Field(default=None, alias="nextAction")
    retry_after_seconds: int | None = Field(default=None, alias="retryAfterSeconds")
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
        next_action: str | None = None,
        retry_after_seconds: int | None = None,
        status: int | None = None,
    ) -> HydraceptError:
        recovery = public_error_content(
            code=code.value,
            message=message,
            status=status,
            retryable=retryable,
            next_action=next_action,
            retry_after_seconds=retry_after_seconds,
        )
        return cls(
            code=code,
            message=message,
            retryable=bool(recovery.get("retryable", False)),
            next_action=recovery.get("nextAction"),
            retry_after_seconds=recovery.get("retryAfterSeconds"),
            execution_id=execution_id,
            receipt_id=receipt_id,
            correlation_id=correlation_id,
            details=details or {},
        )


# Preferred public names (internal Forge* names retained for implementation modules).
