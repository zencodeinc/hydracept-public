"""Unified public job and receipt contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping, TypedDict

from pydantic import BaseModel, Field, field_validator, model_serializer, model_validator

from hydracept_contracts.digests import normalize_sha256_digest
from hydracept_contracts.errors import HydraceptErrorCode, RETRYABLE_ERROR_CODES
from hydracept_contracts.job_wait import job_retry_guidance
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

    @classmethod
    def waiting_values(cls) -> tuple[str, ...]:
        return (cls.QUEUED.value, cls.RUNNING.value, cls.CANCELING.value)

    @classmethod
    def terminal_values(cls) -> tuple[str, ...]:
        return (
            cls.SUCCEEDED.value,
            cls.FAILED.value,
            cls.CANCELED.value,
            cls.AWAITING_APPROVAL.value,
            cls.NEEDS_ATTENTION.value,
        )

    @classmethod
    def human_gate_values(cls) -> tuple[str, ...]:
        return (cls.AWAITING_APPROVAL.value, cls.NEEDS_ATTENTION.value)


class HydraceptJobProgress(BaseModel):
    """Where a durable job has reached, as reported by the activity that owns the work.

    ``updatedAt`` is required whenever progress is present, so a reader can always tell
    how fresh the projection is. ``percent`` and ``etaSeconds`` are optional on purpose:
    they are present only when the authority (a provider that reports them) can compute
    them. The contract forbids fabricating either one (ADR-035), so an unknown value is
    omitted rather than defaulted to ``0``.
    """

    phase: str
    step: str
    percent: float | None = None
    eta_seconds: int | None = Field(default=None, alias="etaSeconds")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = {"populate_by_name": True}


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

    @model_serializer(mode="wrap")
    def _omit_unselected_flag(self, serializer):
        data = serializer(self)
        if data.get("selected") is None:
            data.pop("selected", None)
        return data


@dataclass(frozen=True)
class JobErrorGuidance:
    """One row of the public failure taxonomy.

    ``resolution`` is human next-step guidance, not a restatement of the code.
    ``retryable`` means the same operation may succeed if tried again; ``terminal`` means
    the outcome is decided and the caller should stop. They are independent: an ambiguous
    transport failure is neither retryable nor terminal until its outcome is determined.
    """

    resolution: str
    retryable: bool
    terminal: bool


def _resolved(resolution: str) -> JobErrorGuidance:
    return JobErrorGuidance(resolution=resolution, retryable=False, terminal=True)


def _transient(resolution: str) -> JobErrorGuidance:
    return JobErrorGuidance(resolution=resolution, retryable=True, terminal=False)


def _undecided(resolution: str) -> JobErrorGuidance:
    return JobErrorGuidance(resolution=resolution, retryable=False, terminal=False)


# Explicitly state when no actionable advice is recorded, rather than inventing some.
UNKNOWN_JOB_ERROR_RESOLUTION = (
    "No specific resolution is recorded for this error code. Read message, diagnostics, "
    "and requestSnapshot; if the cause is unclear, contact the operator with the job id."
)
GENERIC_FAILED_ERROR_RESOLUTION = (
    "No specific resolution is recorded for the generic 'failed' code. Read message, "
    "diagnostics, and requestSnapshot; retry only if the message names a transient cause."
)
NEEDS_ATTENTION_ERROR_RESOLUTION = (
    "The job finished partially or needs a human decision. Inspect the artifacts and "
    "message, select a candidate if a selection is required, then resubmit only if the "
    "output is unusable."
)

# Single authority mapping an existing error code to a human-actionable resolution.
# The job payload, the Python SDK, and the CLI all read this shape; the client mirrors
# it because it ships separately (pinned by a parity test).
JOB_ERROR_TAXONOMY: Mapping[str, JobErrorGuidance] = {
    HydraceptErrorCode.AUTHENTICATION_FAILED.value: _resolved(
        "The API token was missing, expired, or invalid. Re-authenticate and retry with a fresh token."
    ),
    HydraceptErrorCode.AUTHORIZATION_FAILED.value: _resolved(
        "This principal is not permitted to perform the operation. Use a principal with the "
        "required scope, or have a project owner grant access, then retry."
    ),
    HydraceptErrorCode.CAPABILITY_NOT_ALLOWED.value: _resolved(
        "The capability is disabled for this product or environment. Enable it in the "
        "product's capability policy, or call an allowed capability."
    ),
    HydraceptErrorCode.POLICY_REJECTED.value: _resolved(
        "A workspace or operations policy rejected the request. Read the message for the "
        "rule that matched, adjust the request to satisfy it, then submit with a new idempotencyKey."
    ),
    HydraceptErrorCode.BUDGET_EXCEEDED.value: _resolved(
        "The request would exceed the available budget. Reduce the request scope or cost, "
        "add funds, then submit with a new idempotencyKey."
    ),
    HydraceptErrorCode.PAUSED.value: _resolved(
        "Paid generation is paused by operations. Wait for it to resume or contact the "
        "operator; do not retry."
    ),
    HydraceptErrorCode.RATE_LIMITED.value: _transient(
        "The provider rate-limited the request. Wait for the Retry-After interval, then "
        "retry the same request."
    ),
    HydraceptErrorCode.PROVIDER_UNAVAILABLE.value: _transient(
        "The provider is temporarily unavailable. Wait and retry; the platform may reseal "
        "to an alternate route."
    ),
    HydraceptErrorCode.PROVIDER_REJECTED.value: _resolved(
        "The provider rejected the request as invalid or unsupported. Change the prompt, "
        "parameters, or model, then submit with a new idempotencyKey."
    ),
    HydraceptErrorCode.PROVIDER_TIMEOUT.value: _transient(
        "The provider did not respond in time. Retry after a short wait; the platform may "
        "reseal to an alternate route."
    ),
    HydraceptErrorCode.EXECUTION_TIMEOUT.value: _resolved(
        "The execution exceeded its wall-clock budget. Reduce the work or raise the "
        "timeout, then submit with a new idempotencyKey."
    ),
    HydraceptErrorCode.QUEUE_TIMEOUT.value: _resolved(
        "The job waited too long for a worker slot. Submit a new job with a new "
        "idempotencyKey; check capacity if this recurs."
    ),
    HydraceptErrorCode.TRANSPORT_AMBIGUOUS.value: _undecided(
        "The request outcome is unknown and may have been received. Do not resubmit "
        "blindly; inspect the job and receipt (and the provider) to determine whether it "
        "ran before retrying."
    ),
    HydraceptErrorCode.CANCELLED.value: _resolved(
        "The job was canceled before it completed. Submit a new job with a new "
        "idempotencyKey if the output is still needed."
    ),
    HydraceptErrorCode.PAYLOAD_UNAVAILABLE.value: _resolved(
        "The stored input or output payload is no longer available. Re-submit the request, "
        "re-uploading the input artifact if needed."
    ),
    HydraceptErrorCode.STRUCTURED_OUTPUT_INVALID.value: _resolved(
        "The model returned output that did not match the required schema. Adjust the "
        "prompt or output schema, then retry."
    ),
    HydraceptErrorCode.STRUCTURED_OUTPUT_REPAIR_FAILED.value: _resolved(
        "Automatic repair of the model's output failed. Adjust the prompt or output "
        "schema, then retry."
    ),
    HydraceptErrorCode.OUTPUT_LIMIT_REACHED.value: _resolved(
        "The model's response was cut off at the output limit before it finished, so it "
        "could not be validated. Retry with a new idempotencyKey; if it recurs, reduce the "
        "requested output size or split the work."
    ),
    HydraceptErrorCode.RETENTION_VIOLATION.value: _resolved(
        "The request conflicts with the resource's retention policy. Adjust the request or "
        "the policy, then retry."
    ),
    HydraceptErrorCode.IDEMPOTENCY_CONFLICT.value: _resolved(
        "The idempotencyKey was already used with a different payload. Submit with a new "
        "idempotencyKey."
    ),
    HydraceptErrorCode.ESTIMATE_UNAVAILABLE.value: _resolved(
        "A cost estimate could not be produced. Retry once; if it persists, simplify the "
        "request or contact the operator."
    ),
    HydraceptErrorCode.PROMPT_TOO_LONG.value: _resolved(
        "The prompt exceeds the model's input limit. Shorten the prompt or choose a model "
        "with a larger context."
    ),
    HydraceptErrorCode.REASONING_BUDGET_EXHAUSTED.value: _resolved(
        "The model spent its whole output budget on reasoning and returned no visible "
        "output. Raise the output budget or simplify the prompt, then retry."
    ),
    HydraceptErrorCode.ESTIMATE_EXCEEDS_MAX_COST.value: _resolved(
        "The quoted cost is above the authorized maximum. Raise the authorization or "
        "reduce the request scope, then submit with a new idempotencyKey."
    ),
    HydraceptErrorCode.FUNDING_REQUIRED.value: _resolved(
        "The account has insufficient funds. Add a payment method or credits, then retry."
    ),
    HydraceptErrorCode.PROJECT_CREDENTIAL_MISMATCH.value: _resolved(
        "The stored provider credential does not belong to this project. Reconnect the "
        "provider with credentials for this project, then retry."
    ),
    HydraceptErrorCode.QUOTE_MISMATCH.value: _resolved(
        "The quote is stale or does not match the server's pricing. Omit quoteId/estimateId "
        "and submit with a new idempotencyKey to reseal pricing."
    ),
    HydraceptErrorCode.ESTIMATE_MISMATCH.value: _resolved(
        "The estimate is stale or does not match the server's pricing. Request a fresh "
        "estimate and submit with a new idempotencyKey."
    ),
    HydraceptErrorCode.REESTIMATE_REQUIRED.value: _resolved(
        "Pricing inputs changed and a new estimate is required. Request a fresh estimate, "
        "then submit with a new idempotencyKey."
    ),
    HydraceptErrorCode.COST_LIMIT_EXCEEDED.value: _resolved(
        "The request exceeds a configured cost limit. Raise the limit or reduce the "
        "request scope, then retry."
    ),
    HydraceptErrorCode.ROUTE_UNAVAILABLE.value: _resolved(
        "The sealed route is no longer routable. Do not retry this job or reuse its "
        "idempotencyKey; submit a new job with a new key and, if the same capability is "
        "still required, pin an alternate provider from error.recovery.alternates."
    ),
    HydraceptErrorCode.ROUTE_CASCADE_EXHAUSTED.value: _resolved(
        "Every sealed route candidate failed. Submit a new job with a new idempotencyKey; "
        "adjust the model or provider preference, or wait if the last failure was transient."
    ),
    HydraceptErrorCode.PRICING_INPUTS_REQUIRED.value: _resolved(
        "Pricing needs more input before it can quote. Supply the missing inputs, then "
        "submit with a new idempotencyKey."
    ),
    HydraceptErrorCode.INVALID_INPUT.value: _resolved(
        "The request failed validation. Fix the fields named in the message, then submit "
        "with a new idempotencyKey."
    ),
    HydraceptErrorCode.UNSUPPORTED_TLD.value: _resolved(
        "The domain extension is not supported. Choose a supported TLD and submit again."
    ),
    HydraceptErrorCode.CATALOG_UNAVAILABLE.value: _transient(
        "The model or provider catalog could not be loaded. Retry after a short wait."
    ),
    HydraceptErrorCode.UNKNOWN_EXECUTION_FIELD.value: _resolved(
        "The request contained an execution field the server does not recognize. Remove or "
        "correct it, then retry."
    ),
    HydraceptErrorCode.CONFLICTING_EXECUTION_CONSTRAINT.value: _resolved(
        "The request combined execution constraints that cannot both hold. Relax one of "
        "them, then retry."
    ),
    HydraceptErrorCode.INTERNAL_FAILURE.value: _transient(
        "An internal error occurred. Retry after a short wait; if it persists, contact the "
        "operator with the job id."
    ),
    # Generic codes that carry no specific cause.
    "failed": _resolved(GENERIC_FAILED_ERROR_RESOLUTION),
    "needs_attention": _resolved(NEEDS_ATTENTION_ERROR_RESOLUTION),
}

_JOB_ERROR_CODE_INDEX: dict[str, str] = {code.lower(): code for code in JOB_ERROR_TAXONOMY}


class HydraceptJobError(TypedDict):
    """The public failure projection. ``HydraceptJob.error`` always reads this shape."""

    code: str
    message: str
    retryable: bool
    resolution: str
    terminal: bool


def job_error_guidance(code: str | None) -> JobErrorGuidance:
    """Resolve one error code to the taxonomy row, case-insensitively.

    Unknown codes get the explicit no-guidance row instead of invented advice.
    """
    key = str(code or "").strip() or "failed"
    entry = JOB_ERROR_TAXONOMY.get(key)
    if entry is None:
        entry = JOB_ERROR_TAXONOMY.get(_JOB_ERROR_CODE_INDEX.get(key.lower(), ""))
    return entry or JobErrorGuidance(
        resolution=UNKNOWN_JOB_ERROR_RESOLUTION, retryable=False, terminal=True
    )


def project_job_error(
    *,
    code: str | None,
    message: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the typed public error projection from one existing error code.

    ``extra`` preserves richer producer payloads (for example route recovery alternates).
    """
    resolved_code = str(code or "failed").strip() or "failed"
    guidance = job_error_guidance(resolved_code)
    projected: dict[str, Any] = dict(extra or {})
    projected["code"] = resolved_code
    projected["message"] = message
    projected["retryable"] = guidance.retryable
    projected["resolution"] = guidance.resolution
    projected["terminal"] = guidance.terminal
    return projected


class HydraceptJob(BaseModel):
    job_id: str = Field(alias="jobId")
    capability_key: str = Field(alias="capabilityKey")
    status: HydraceptJobStatus
    project_id: str | None = Field(default=None, alias="projectId")
    product_id: str | None = Field(default=None, alias="productId")
    created_at: datetime | None = Field(default=None, alias="createdAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    estimated_cost: float | None = Field(default=None, alias="estimatedCost")
    actual_cost: float | None = Field(default=None, alias="actualCost")
    currency: str = "USD"
    artifacts: list[HydraceptJobArtifactRef] = Field(default_factory=list)
    variant_set: HydraceptVariantSet | None = Field(default=None, alias="variantSet")
    receipt_id: str | None = Field(default=None, alias="receiptId")
    primary_artifact_id: str | None = Field(default=None, alias="primaryArtifactId")
    typed_output: Any | None = Field(default=None, alias="typedOutput")
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    error: dict[str, Any] | None = None
    progress: HydraceptJobProgress | None = Field(
        default=None,
        description="Latest projection of the job's job.progress events; absent until one exists.",
    )
    diagnostics: HydraceptJobDiagnostics | None = None
    request_snapshot: dict[str, Any] | None = Field(
        default=None,
        alias="requestSnapshot",
        description="Canonical submitted request for Studio re-run (not receipt).",
    )
    next_action: str | None = Field(default=None, alias="nextAction")
    poll_after_seconds: int | None = Field(default=None, alias="pollAfterSeconds")
    retry: dict[str, Any] | None = None
    approval: dict[str, Any] | None = Field(
        default=None,
        description="Sanitized human-gate payload. Present only while the job awaits approval.",
    )

    model_config = {"populate_by_name": True}

    @field_validator("error", mode="before")
    @classmethod
    def normalize_error(cls, value: object) -> dict[str, Any] | None:
        """Project every backend failure onto the one typed public error shape.

        Job-list history intentionally exposes only ``errorCode``. Once a caller
        explicitly inspects one job, the public job contract guarantees
        ``{code, message, retryable, resolution, terminal}`` (ADR-035), with any richer
        producer keys such as ``recovery`` preserved. ``resolution`` comes from the
        taxonomy in this module, so the same failure reads the same way everywhere.
        """
        if value is None:
            return None
        if isinstance(value, dict):
            normalized = dict(value)
            code = str(normalized.get("code") or "failed").strip() or "failed"
            raw_message = normalized.get("message")
            message = str(raw_message).strip() if raw_message is not None else ""
            if not message or message == code:
                message = f"Job failed with error code {code}."
            return project_job_error(code=code, message=message, extra=normalized)
        message = str(value).strip() or "Job failed."
        return project_job_error(code="failed", message=message)

    @model_validator(mode="after")
    def fill_wait_hints(self) -> HydraceptJob:
        if self.next_action and self.retry is not None:
            return self
        hints = job_retry_guidance(
            status=str(self.status),
            error_code=(self.error or {}).get("code") if isinstance(self.error, dict) else None,
        )
        if not self.next_action:
            self.next_action = str(hints["nextAction"])
        poll_after = hints.get("pollAfterSeconds")
        if self.poll_after_seconds is None:
            self.poll_after_seconds = int(poll_after) if poll_after is not None else None
        if self.retry is None:
            retry = hints.get("retry")
            self.retry = dict(retry) if isinstance(retry, dict) else None
        return self


class HydraceptJobResult(BaseModel):
    """First-class job result projection — typed output plus payload identity."""

    job_id: str = Field(alias="jobId")
    status: HydraceptJobStatus
    typed_output: Any | None = Field(default=None, alias="typedOutput")
    output_payload_ref: str | None = Field(default=None, alias="outputPayloadRef")
    payload_state: str | None = Field(default=None, alias="payloadState")
    artifacts: list[HydraceptJobArtifactRef] = Field(default_factory=list)
    error: dict[str, Any] | None = None

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
    # Execution-backend provenance. Present for provider-free local execution so
    # a receipt can state, without inferring from the route, that nothing was
    # model-backed or provider-backed and that the result is deterministic.
    execution: str | None = None
    engine: str | None = None
    provider_backed: bool | None = Field(default=None, alias="providerBacked")
    model_backed: bool | None = Field(default=None, alias="modelBacked")
    deterministic: bool | None = None

    model_config = {"populate_by_name": True}


class HydraceptReceipt(BaseModel):
    receipt_id: str = Field(alias="receiptId")
    job_id: str = Field(alias="jobId")
    capability_key: str = Field(alias="capabilityKey")
    principal_id: str | None = Field(default=None, alias="principalId")
    project_id: str | None = Field(default=None, alias="projectId")
    product_id: str | None = Field(default=None, alias="productId")
    environment: str | None = None
    admission: HydraceptReceiptAdmission | None = None
    route: HydraceptReceiptRoute | None = None
    estimated_cost: float | None = Field(
        default=None,
        alias="estimatedCost",
        description="Deprecated 0.2 shim of pricing.quote.customerTotal. Do not use internally.",
    )
    actual_cost: float | None = Field(
        default=None,
        alias="actualCost",
        description="Deprecated 0.2 shim of pricing.charge.customerCharge (amount owed). Do not use internally.",
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
        self.estimated_cost = quote_total.as_usd_float() if quote_total is not None else None
        self.actual_cost = charge_total.as_usd_float() if charge_total is not None else None
        return self

    @model_serializer(mode="wrap")
    def _omit_duplicate_estimate_id(self, serializer):
        data = serializer(self)
        pricing = data.get("pricing")
        if (
            isinstance(pricing, dict)
            and pricing.get("quoteId")
            and pricing.get("estimateId") == pricing.get("quoteId")
        ):
            pricing = dict(pricing)
            pricing.pop("estimateId", None)
            data["pricing"] = pricing
        return data


_SHEET_PRIMARY_KINDS = frozenset(
    {
        "composite-sheet",
        "contact-preview",
        "sheet",
        "contact-sheet",
    }
)


def resolve_primary_artifact_id(
    artifacts: list[HydraceptJobArtifactRef],
    variant_set: HydraceptVariantSet | None = None,
) -> str | None:
    """Default usable output without choosing among peers.

    Genuine variant/user selection remains ``variantSet.selectedArtifactId`` /
    ``artifacts[].selected``. A single ordinary output is primary and does not
    set ``selected``.
    """
    if variant_set is not None and variant_set.selected_artifact_id:
        return variant_set.selected_artifact_id
    chosen = [item for item in artifacts if item.selected is True]
    if len(chosen) == 1:
        return chosen[0].artifact_id
    if variant_set is not None and variant_set.requested_count > 1 and not chosen:
        return None
    sheet_primaries = [
        item for item in artifacts if str(item.kind or "") in _SHEET_PRIMARY_KINDS
    ]
    if len(sheet_primaries) == 1:
        return sheet_primaries[0].artifact_id
    sliced = [item for item in artifacts if item.slice_cell_id]
    if len(sliced) > 1 and not sheet_primaries:
        return None
    outputs = [item for item in artifacts if item.artifact_id]
    if len(outputs) == 1:
        return outputs[0].artifact_id
    return None


_SEALED_RECEIPT_STATUSES = frozenset(
    {
        HydraceptJobStatus.SUCCEEDED.value,
        HydraceptJobStatus.FAILED.value,
        HydraceptJobStatus.CANCELED.value,
    }
)


def workflow_receipt_id_for_status(run_id: str, status: HydraceptJobStatus) -> str | None:
    """``rcpt_{run.id}`` only when a sealed receipt exists — not human-gate states."""
    if str(status) not in _SEALED_RECEIPT_STATUSES:
        return None
    return f"rcpt_{run_id}"


# Preferred public names (internal Forge* names retained for implementation modules).