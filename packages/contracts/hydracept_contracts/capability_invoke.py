"""Capability façade request bodies and execution constraint contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

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
    execution_constraints: ExecutionConstraints | None = Field(
        default=None, alias="executionConstraints"
    )

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_alpha_contract(self) -> CapabilityExecutionOptions:
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
    product_id: str = Field(alias="productId")
    environment: str
    project_id: str | None = Field(default=None, alias="projectId")
    data_classification: DataClassification = Field(
        default=DataClassification.INTERNAL, alias="dataClassification"
    )
    retention_requirement: RetentionPolicy = Field(
        default=RetentionPolicy.TRANSIENT, alias="retentionRequirement"
    )

    model_config = {"populate_by_name": True}


class CapabilityInvokeRequest(BaseModel):
    context: CapabilityContext
    input: dict[str, Any] = Field(default_factory=dict)
    execution: CapabilityExecutionOptions = Field(default_factory=CapabilityExecutionOptions)
    idempotency_key: str | None = Field(default=None, alias="idempotencyKey")
    correlation_id: str | None = Field(default=None, alias="correlationId")
    task_kind: str | None = Field(default=None, alias="taskKind")
    execution_mode: ExecutionMode | None = Field(default=None, alias="executionMode")

    model_config = {"populate_by_name": True}


class CapabilityJobRequest(BaseModel):
    context: CapabilityContext
    input: dict[str, Any] = Field(default_factory=dict)
    execution: CapabilityExecutionOptions = Field(default_factory=CapabilityExecutionOptions)
    idempotency_key: str = Field(alias="idempotencyKey")
    correlation_id: str | None = Field(default=None, alias="correlationId")
    task_kind: str | None = Field(default=None, alias="taskKind")

    model_config = {"populate_by_name": True}
