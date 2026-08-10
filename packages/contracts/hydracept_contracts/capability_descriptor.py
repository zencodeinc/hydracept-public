"""Public capability descriptor contracts (semantic + presentation split)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CapabilityModality(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    EMBEDDING = "embedding"
    MODERATION = "moderation"
    INFRASTRUCTURE = "infrastructure"


class ActionRisk(StrEnum):
    READ_ONLY = "read_only"
    REVERSIBLE_WRITE = "reversible_write"
    DESTRUCTIVE_WRITE = "destructive_write"
    FINANCIAL_IRREVERSIBLE = "financial_irreversible"


class MinimumApproval(StrEnum):
    NEVER = "never"
    ALWAYS = "always"
    POLICY = "policy"


class CapabilityExecutionMode(StrEnum):
    INVOKE_SYNC = "invoke_sync"
    INVOKE_STREAM = "invoke_stream"
    JOB_ASYNC = "job_async"


class ExecutionPreferenceSupport(BaseModel):
    supported: list[str] = Field(default_factory=lambda: ["automatic"])
    constraints: dict[str, bool] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class CapabilityDescriptor(BaseModel):
    key: str
    title: str
    description: str = ""
    modality: CapabilityModality
    input_schema: dict[str, Any] = Field(alias="inputSchema")
    output_schema: dict[str, Any] = Field(default_factory=dict, alias="outputSchema")
    ui_schema: dict[str, Any] = Field(default_factory=dict, alias="uiSchema")
    execution_modes: list[CapabilityExecutionMode] = Field(alias="executionModes")
    idempotency_required: bool = Field(default=False, alias="idempotencyRequired")
    estimate_available: bool = Field(default=False, alias="estimateAvailable")
    execution_preference: ExecutionPreferenceSupport = Field(
        default_factory=ExecutionPreferenceSupport,
        alias="executionPreference",
    )
    route_provider: str | None = Field(default=None, alias="routeProvider")
    route_model: str | None = Field(default=None, alias="routeModel")
    action_risk: ActionRisk | None = Field(default=None, alias="actionRisk")
    minimum_approval: MinimumApproval | None = Field(default=None, alias="minimumApproval")
    quote_ttl_seconds: int | None = Field(default=None, alias="quoteTtlSeconds")

    model_config = {"populate_by_name": True}


class CapabilityListItem(BaseModel):
    key: str
    title: str
    modality: CapabilityModality
    execution_modes: list[CapabilityExecutionMode] = Field(alias="executionModes")
    descriptor_available: bool = Field(default=True, alias="descriptorAvailable")

    model_config = {"populate_by_name": True}
