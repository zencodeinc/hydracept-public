"""Capability façade request bodies and execution constraint contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from hydracept_contracts.execution import DataClassification, ExecutionMode, RetentionPolicy


class ExecutionPreferenceAlpha(StrEnum):
    AUTOMATIC = "automatic"


_ALPHA_EXECUTION_PREFERENCES = frozenset({ExecutionPreferenceAlpha.AUTOMATIC.value})
_ALPHA_CONSTRAINT_KEYS = frozenset({"maxCostUsd", "providerPin"})
_REJECTED_EXECUTION_PREFERENCES = frozenset(
    {"fastest", "cheapest", "maximum_quality", "maximum_quality"}
)
_REJECTED_CONSTRAINT_KEYS = frozenset({"maxLatencyMs"})


class ExecutionConstraints(BaseModel):
    max_cost_usd: float | None = Field(default=None, alias="maxCostUsd", gt=0)
    provider_pin: str | None = Field(default=None, alias="providerPin")

    model_config = {"populate_by_name": True, "extra": "forbid"}


class CapabilityExecutionOptions(BaseModel):
    execution_preference: str = Field(default="automatic", alias="executionPreference")
    billing_mode: str | None = Field(default=None, alias="billingMode")
    credential_source: str | None = Field(default=None, alias="credentialSource")
    quote_id: str | None = Field(default=None, alias="quoteId")
    estimate_id: str | None = Field(
        default=None,
        alias="estimateId",
        description="Inbound alias of quoteId. Internals consume quoteId / pricing.quote.",
    )
    maximum_charge: dict | None = Field(default=None, alias="maximumCharge")
    execution_constraints: ExecutionConstraints | None = Field(
        default=None, alias="executionConstraints"
    )

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_alpha_contract(self) -> CapabilityExecutionOptions:
        if self.quote_id and not self.estimate_id:
            self.estimate_id = self.quote_id
        elif self.estimate_id and not self.quote_id:
            self.quote_id = self.estimate_id
        pref = (self.execution_preference or "automatic").strip()
        if pref in _REJECTED_EXECUTION_PREFERENCES:
            raise ValueError(f"executionPreference '{pref}' is not supported in this API version")
        if pref not in _ALPHA_EXECUTION_PREFERENCES:
            raise ValueError(f"unsupported executionPreference '{pref}'")
        if self.execution_constraints is not None:
            extra = set(self.execution_constraints.model_dump(by_alias=True).keys())
            allowed = _ALPHA_CONSTRAINT_KEYS
            rejected = extra & _REJECTED_CONSTRAINT_KEYS
            if rejected:
                raise ValueError(
                    f"executionConstraints {sorted(rejected)} not supported in this API version"
                )
            unknown = extra - allowed
            if unknown:
                raise ValueError(f"unknown executionConstraints keys: {sorted(unknown)}")
        return self


class CapabilityContext(BaseModel):
    product_id: str = Field(default="", alias="productId")
    environment: str = Field(default="development")
    project_id: str | None = Field(default=None, alias="projectId")
    data_classification: DataClassification = Field(
        default=DataClassification.INTERNAL, alias="dataClassification"
    )
    retention_requirement: RetentionPolicy = Field(
        default=RetentionPolicy.TRANSIENT, alias="retentionRequirement"
    )

    model_config = {"populate_by_name": True}


_INVOKE_ENVELOPE_KEYS = frozenset(
    {
        "context",
        "input",
        "execution",
        "idempotencyKey",
        "idempotency_key",
        "correlationId",
        "correlation_id",
        "taskKind",
        "task_kind",
        "executionMode",
        "execution_mode",
    }
)


def wrap_bare_capability_input(data: Any) -> Any:
    """Accept `{ prompt: "..." }` / `{ start: 0 }` as `{ input: { ... } }`."""
    if not isinstance(data, dict) or "input" in data:
        return data
    extra = {key: value for key, value in data.items() if key not in _INVOKE_ENVELOPE_KEYS}
    if not extra:
        return data
    wrapped = {key: value for key, value in data.items() if key in _INVOKE_ENVELOPE_KEYS}
    wrapped["input"] = extra
    return wrapped


def mint_job_idempotency_key() -> str:
    return f"job-{uuid4().hex}"


class CapabilityInvokeRequest(BaseModel):
    context: CapabilityContext = Field(default_factory=CapabilityContext)
    input: dict[str, Any] = Field(default_factory=dict)
    execution: CapabilityExecutionOptions = Field(default_factory=CapabilityExecutionOptions)
    idempotency_key: str | None = Field(default=None, alias="idempotencyKey")
    correlation_id: str | None = Field(default=None, alias="correlationId")
    task_kind: str | None = Field(default=None, alias="taskKind")
    execution_mode: ExecutionMode | None = Field(default=None, alias="executionMode")

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def coerce_agent_invoke_body(cls, data: Any) -> Any:
        return wrap_bare_capability_input(data)


class CapabilityJobRequest(BaseModel):
    context: CapabilityContext = Field(default_factory=CapabilityContext)
    input: dict[str, Any] = Field(default_factory=dict)
    execution: CapabilityExecutionOptions = Field(default_factory=CapabilityExecutionOptions)
    idempotency_key: str = Field(default_factory=mint_job_idempotency_key, alias="idempotencyKey")
    correlation_id: str | None = Field(default=None, alias="correlationId")
    task_kind: str | None = Field(default=None, alias="taskKind")

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def wrap_input_and_mint_idempotency(cls, data: Any) -> Any:
        wrapped = wrap_bare_capability_input(data)
        if not isinstance(wrapped, dict):
            return wrapped
        key = str(wrapped.get("idempotencyKey") or wrapped.get("idempotency_key") or "").strip()
        if not key:
            wrapped["idempotencyKey"] = mint_job_idempotency_key()
            wrapped.pop("idempotency_key", None)
        return wrapped
