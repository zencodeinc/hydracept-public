"""Capability façade request bodies and execution constraint contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from hydracept_contracts.capability_invoke_envelope import CapabilityInvocationEnvelope
from hydracept_contracts.execution import DataClassification, ExecutionMode, RetentionPolicy
from hydracept_contracts.execution_contract_error import (
    EXECUTION_CONSTRAINT_FIELDS,
    ExecutionContractError,
)


class ExecutionPreferenceAlpha(StrEnum):
    AUTOMATIC = "automatic"


_ALPHA_EXECUTION_PREFERENCES = frozenset({ExecutionPreferenceAlpha.AUTOMATIC.value})
_ALPHA_CONSTRAINT_KEYS = frozenset(EXECUTION_CONSTRAINT_FIELDS)
_REJECTED_EXECUTION_PREFERENCES = frozenset(
    {"fastest", "cheapest", "maximum_quality", "maximum_quality"}
)
_REJECTED_CONSTRAINT_KEYS = frozenset({"maxLatencyMs"})
_FOLD_CONSTRAINT_KEYS = (
    ("preferredModel", "preferred_model"),
    ("autoSelect", "auto_select"),
    ("providerPin", "provider_pin"),
    ("maxCostUsd", "max_cost_usd"),
    ("maxDurationSeconds", "max_duration_seconds"),
    ("timeoutSeconds", "timeout_seconds"),
)
_FOLD_EXECUTION_OPTION_KEYS = (
    ("billingMode", "billing_mode"),
    ("credentialSource", "credential_source"),
    ("quoteId", "quote_id"),
    ("estimateId", "estimate_id"),
    ("maximumCharge", "maximum_charge"),
)


class ExecutionConstraints(BaseModel):
    max_cost_usd: float | None = Field(default=None, alias="maxCostUsd", gt=0)
    provider_pin: str | None = Field(default=None, alias="providerPin")
    preferred_model: str | None = Field(default=None, alias="preferredModel")
    auto_select: bool = Field(
        default=False,
        alias="autoSelect",
        description=(
            "Opt in to smart fallback when preferredModel is physically unavailable. "
            "Ignored when preferredModel is omitted."
        ),
    )
    budget_enforcement: str | None = Field(
        default=None,
        alias="budgetEnforcement",
        description="warn (admit over ceiling) or prevent (HTTP 402). Setting maxCostUsd without this is prevent.",
    )
    max_duration_seconds: int | None = Field(
        default=None,
        alias="maxDurationSeconds",
        ge=5,
        le=7200,
        description=(
            "Provider execution deadline in seconds after the job starts running. "
            "Does not include queue wait. timeoutSeconds is accepted as an alias."
        ),
    )

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="before")
    @classmethod
    def _fold_timeout_alias(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        timeout = payload.pop("timeoutSeconds", None)
        if timeout is None:
            timeout = payload.pop("timeout_seconds", None)
        if timeout is None:
            return payload
        existing = payload.get("maxDurationSeconds", payload.get("max_duration_seconds"))
        if existing is not None and existing != timeout:
            raise ValueError("conflicting timeoutSeconds and maxDurationSeconds")
        payload["maxDurationSeconds"] = timeout
        return payload

    @field_validator("budget_enforcement")
    @classmethod
    def _budget_enforcement_values(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        text = str(value).strip().lower()
        if text not in {"off", "warn", "prevent"}:
            raise ValueError(f"unsupported budgetEnforcement '{value}'")
        return text


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

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="after")
    def validate_alpha_contract(self) -> "CapabilityExecutionOptions":
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
    # Authenticated execution binds environment from the principal/home workspace.
    # An empty contract default preserves "unspecified" until that authority runs.
    environment: str = Field(default="")
    project_id: str | None = Field(default=None, alias="projectId")
    data_classification: DataClassification = Field(
        default=DataClassification.INTERNAL, alias="dataClassification"
    )
    retention_requirement: RetentionPolicy = Field(
        default=RetentionPolicy.TRANSIENT, alias="retentionRequirement"
    )

    model_config = {"populate_by_name": True, "extra": "forbid"}


def capability_envelope_keys(model: type[BaseModel]) -> frozenset[str]:
    keys: set[str] = set()
    for name, field in model.model_fields.items():
        keys.add(name)
        if field.alias:
            keys.add(str(field.alias))
    return frozenset(keys)


def _ensure_execution_dict(remaining: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    execution = remaining.get("execution")
    if execution is None:
        return remaining, {}
    if not isinstance(execution, dict):
        return remaining, execution
    return remaining, dict(execution)


def _fold_execution_options(data: dict[str, Any]) -> dict[str, Any]:
    """Lift legacy top-level execution options into ``execution`` for every surface."""
    remaining = dict(data)
    execution_raw = remaining.get("execution")
    if execution_raw is None:
        execution: dict[str, Any] = {}
    elif isinstance(execution_raw, dict):
        execution = dict(execution_raw)
    else:
        return remaining
    for alias, snake in _FOLD_EXECUTION_OPTION_KEYS:
        present = alias if alias in remaining else snake if snake in remaining else None
        if present is None:
            continue
        value = remaining.pop(present)
        existing = execution.get(alias)
        if existing is not None and existing != value:
            raise ValueError(f"conflicting {alias} between top-level shim and execution")
        execution[alias] = value
    if execution:
        remaining["execution"] = execution
    return remaining


def _fold_routing_constraints(data: dict[str, Any]) -> dict[str, Any]:
    """Lift top-level routing pins onto execution.executionConstraints."""
    folded: dict[str, Any] = {}
    remaining = dict(data)
    for alias, snake in _FOLD_CONSTRAINT_KEYS:
        if alias in remaining:
            folded[alias] = remaining.pop(alias)
        elif snake in remaining:
            folded[alias] = remaining.pop(snake)
    if not folded:
        return remaining
    execution = remaining.get("execution")
    if not isinstance(execution, dict):
        execution = {}
        remaining["execution"] = execution
    else:
        execution = dict(execution)
        remaining["execution"] = execution
    constraints = execution.get("executionConstraints")
    if not isinstance(constraints, dict):
        constraints = {}
        execution["executionConstraints"] = constraints
    else:
        constraints = dict(constraints)
        execution["executionConstraints"] = constraints
    for key, value in folded.items():
        if key in constraints and constraints[key] != value:
            raise ExecutionContractError.conflicting_constraint(key)
        constraints.setdefault(key, value)
    return remaining


def _fold_legacy_quote_shims(data: dict[str, Any]) -> dict[str, Any]:
    """Fold quote-only ``options``/``model`` shims into canonical ``input``."""
    remaining = dict(data)
    input_data = remaining.get("input")
    if input_data is None:
        input_data = {}
    elif not isinstance(input_data, dict):
        return remaining
    else:
        input_data = dict(input_data)

    options = remaining.pop("options", None)
    if isinstance(options, dict):
        for key, value in options.items():
            if key in input_data and input_data[key] != value:
                raise ValueError(f"conflicting quote option/input field '{key}'")
            input_data.setdefault(key, value)
    elif options is not None:
        raise ValueError("quote options must be an object")

    if "model" in remaining:
        model = remaining.pop("model")
        if "model" in input_data and input_data["model"] != model:
            raise ValueError("conflicting model between quote shim and input")
        input_data["model"] = model

    if input_data:
        remaining["input"] = input_data
    return remaining


def normalize_capability_request_body(
    data: Any,
    *,
    model: type[BaseModel] | None = None,
    legacy_quote_shims: bool = False,
) -> Any:
    """Canonicalize every public capability body before closed validation."""
    if not isinstance(data, dict):
        return data
    normalized = _fold_execution_options(dict(data))
    if legacy_quote_shims:
        normalized = _fold_legacy_quote_shims(normalized)
    normalized = _fold_routing_constraints(normalized)
    if "input" in normalized:
        return normalized
    envelope = capability_envelope_keys(model) if model is not None else frozenset()
    capability_fields = {key: value for key, value in normalized.items() if key not in envelope}
    if not capability_fields:
        return normalized
    wrapped = {key: value for key, value in normalized.items() if key in envelope}
    wrapped["input"] = capability_fields
    return wrapped


def wrap_bare_capability_input(data: Any, *, model: type[BaseModel] | None = None) -> Any:
    """Backward-compatible alias for the canonical request normalizer."""
    return normalize_capability_request_body(data, model=model)


def mint_job_idempotency_key() -> str:
    return f"job-{uuid4().hex}"


class CapabilityInvokeRequest(CapabilityInvocationEnvelope):
    context: CapabilityContext = Field(default_factory=CapabilityContext)
    input: dict[str, Any] = Field(default_factory=dict)
    execution: CapabilityExecutionOptions = Field(default_factory=CapabilityExecutionOptions)
    idempotency_key: str | None = Field(default=None, alias="idempotencyKey")
    correlation_id: str | None = Field(default=None, alias="correlationId")
    task_kind: str | None = Field(default=None, alias="taskKind")
    execution_mode: ExecutionMode | None = Field(default=None, alias="executionMode")

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="before")
    @classmethod
    def coerce_agent_invoke_body(cls, data: Any) -> Any:
        return normalize_capability_request_body(data, model=cls)


class CapabilityJobRequest(CapabilityInvocationEnvelope):
    context: CapabilityContext = Field(default_factory=CapabilityContext)
    input: dict[str, Any] = Field(default_factory=dict)
    execution: CapabilityExecutionOptions = Field(default_factory=CapabilityExecutionOptions)
    idempotency_key: str = Field(default_factory=mint_job_idempotency_key, alias="idempotencyKey")
    correlation_id: str | None = Field(default=None, alias="correlationId")
    task_kind: str | None = Field(default=None, alias="taskKind")

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="before")
    @classmethod
    def wrap_input_and_mint_idempotency(cls, data: Any) -> Any:
        wrapped = normalize_capability_request_body(data, model=cls)
        if not isinstance(wrapped, dict):
            return wrapped
        key = str(wrapped.get("idempotencyKey") or wrapped.get("idempotency_key") or "").strip()
        if not key:
            wrapped["idempotencyKey"] = mint_job_idempotency_key()
            wrapped.pop("idempotency_key", None)
        return wrapped