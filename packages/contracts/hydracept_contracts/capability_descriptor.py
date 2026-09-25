"""Public capability descriptor contracts (semantic + presentation split)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from hydracept_contracts.input_constraints import FieldInputConstraint


class CapabilityModality(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    MESH = "mesh"
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


class CapabilityQuoteBlock(BaseModel):
    """Serializable quote support. ``requires_input`` is a request error, not this flag."""

    supported: bool = False
    requirements: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class CapabilityPricingBlock(BaseModel):
    billable: bool = True
    quote: CapabilityQuoteBlock = Field(default_factory=CapabilityQuoteBlock)

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
    capability_pricing: CapabilityPricingBlock | None = Field(
        default=None, alias="capabilityPricing"
    )
    execution_preference: ExecutionPreferenceSupport = Field(
        default_factory=ExecutionPreferenceSupport,
        alias="executionPreference",
    )
    route_provider: str | None = Field(default=None, alias="routeProvider")
    route_model: str | None = Field(default=None, alias="routeModel")
    action_risk: ActionRisk | None = Field(default=None, alias="actionRisk")
    minimum_approval: MinimumApproval | None = Field(default=None, alias="minimumApproval")
    quote_ttl_seconds: int | None = Field(default=None, alias="quoteTtlSeconds")
    features: dict[str, Any] = Field(default_factory=dict)
    input_media_types: list[str] = Field(default_factory=list, alias="inputMediaTypes")
    credential_sources: list[str] | None = Field(default=None, alias="credentialSources")
    default_credential_source: str | None = Field(default=None, alias="defaultCredentialSource")
    family: str | None = None
    category: str | None = None
    constraints: dict[str, Any] | None = None
    input_constraints: dict[str, FieldInputConstraint] = Field(
        default_factory=dict,
        alias="inputConstraints",
    )
    # Canonical natural-language discovery metadata. Runtime/readiness strings
    # are deliberately excluded from intent ranking.
    intent_examples: list[str] = Field(default_factory=list, alias="intentExamples")
    task_tags: list[str] = Field(default_factory=list, alias="taskTags")
    synonyms: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


def taxonomy_for_capability(key: str, modality: CapabilityModality) -> tuple[str, str]:
    """Stable family/category so consumers do not reconstruct taxonomy from prefixes."""
    normalized = str(key or "").strip().lower()
    if normalized.startswith(("domain.", "dns.", "web.domain.")):
        return "domain", "infrastructure"
    if "translat" in normalized:
        return "text", "translation"
    if normalized.startswith(("math.", "compute.")) or ".math." in normalized:
        return "math", "analysis"
    if normalized.startswith(("research.", "analysis.", "inference.")):
        return "research", "analysis"
    if normalized.startswith(("convert.", "file.", "productivity.")):
        return "productivity", "conversion"
    by_modality = {
        CapabilityModality.IMAGE: ("image", "generation"),
        CapabilityModality.AUDIO: ("audio", "generation"),
        CapabilityModality.VIDEO: ("video", "generation"),
        CapabilityModality.MESH: ("geometry", "generation"),
        CapabilityModality.TEXT: ("text", "generation"),
        CapabilityModality.EMBEDDING: ("text", "analysis"),
        CapabilityModality.MODERATION: ("text", "analysis"),
        CapabilityModality.INFRASTRUCTURE: ("domain", "infrastructure"),
    }
    return by_modality.get(modality, ("productivity", "other"))


class CapabilityListItem(BaseModel):
    key: str
    title: str
    modality: CapabilityModality
    family: str | None = None
    category: str | None = None
    execution_modes: list[CapabilityExecutionMode] = Field(alias="executionModes")
    descriptor_available: bool = Field(default=True, alias="descriptorAvailable")

    model_config = {"populate_by_name": True}
