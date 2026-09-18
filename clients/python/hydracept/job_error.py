"""Public job failure taxonomy for the Python client (hydracept 0.4).

One failure must read the same way in the job payload, the SDK, and the CLI. The
authority lives in ``hydracept_contracts.hydracept_job`` (``JOB_ERROR_TAXONOMY``), but
this package ships as a separate distribution and cannot import it. The mapping is
therefore mirrored here and pinned by
``clients/python/tests/test_job_error_taxonomy_parity.py``: if either side moves, CI
fails instead of the two surfaces drifting apart.

``resolution`` is human next-step guidance, not a restatement of the code. When a code
has no meaningful resolution, the payload says so explicitly rather than inventing
advice.
"""

from __future__ import annotations

from typing import Any

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


def _resolved(resolution: str) -> dict[str, Any]:
    return {"resolution": resolution, "retryable": False, "terminal": True}


def _transient(resolution: str) -> dict[str, Any]:
    return {"resolution": resolution, "retryable": True, "terminal": False}


def _undecided(resolution: str) -> dict[str, Any]:
    return {"resolution": resolution, "retryable": False, "terminal": False}


# Keep byte-identical to hydracept_contracts.hydracept_job.JOB_ERROR_TAXONOMY.
JOB_ERROR_TAXONOMY: dict[str, dict[str, Any]] = {
    "AuthenticationFailed": _resolved(
        "The API token was missing, expired, or invalid. Re-authenticate and retry with a fresh token."
    ),
    "AuthorizationFailed": _resolved(
        "This principal is not permitted to perform the operation. Use a principal with the "
        "required scope, or have a project owner grant access, then retry."
    ),
    "CapabilityNotAllowed": _resolved(
        "The capability is disabled for this product or environment. Enable it in the "
        "product's capability policy, or call an allowed capability."
    ),
    "PolicyRejected": _resolved(
        "A workspace or operations policy rejected the request. Read the message for the "
        "rule that matched, adjust the request to satisfy it, then submit with a new idempotencyKey."
    ),
    "BudgetExceeded": _resolved(
        "The request would exceed the available budget. Reduce the request scope or cost, "
        "add funds, then submit with a new idempotencyKey."
    ),
    "Paused": _resolved(
        "Paid generation is paused by operations. Wait for it to resume or contact the "
        "operator; do not retry."
    ),
    "RateLimited": _transient(
        "The provider rate-limited the request. Wait for the Retry-After interval, then "
        "retry the same request."
    ),
    "ProviderUnavailable": _transient(
        "The provider is temporarily unavailable. Wait and retry; the platform may reseal "
        "to an alternate route."
    ),
    "ProviderRejected": _resolved(
        "The provider rejected the request as invalid or unsupported. Change the prompt, "
        "parameters, or model, then submit with a new idempotencyKey."
    ),
    "ProviderTimeout": _transient(
        "The provider did not respond in time. Retry after a short wait; the platform may "
        "reseal to an alternate route."
    ),
    "ExecutionTimeout": _resolved(
        "The execution exceeded its wall-clock budget. Reduce the work or raise the "
        "timeout, then submit with a new idempotencyKey."
    ),
    "QueueTimeout": _resolved(
        "The job waited too long for a worker slot. Submit a new job with a new "
        "idempotencyKey; check capacity if this recurs."
    ),
    "TRANSPORT_AMBIGUOUS": _undecided(
        "The request outcome is unknown and may have been received. Do not resubmit "
        "blindly; inspect the job and receipt (and the provider) to determine whether it "
        "ran before retrying."
    ),
    "Cancelled": _resolved(
        "The job was canceled before it completed. Submit a new job with a new "
        "idempotencyKey if the output is still needed."
    ),
    "PayloadUnavailable": _resolved(
        "The stored input or output payload is no longer available. Re-submit the request, "
        "re-uploading the input artifact if needed."
    ),
    "StructuredOutputInvalid": _resolved(
        "The model returned output that did not match the required schema. Adjust the "
        "prompt or output schema, then retry."
    ),
    "StructuredOutputRepairFailed": _resolved(
        "Automatic repair of the model's output failed. Adjust the prompt or output "
        "schema, then retry."
    ),
    "RetentionViolation": _resolved(
        "The request conflicts with the resource's retention policy. Adjust the request or "
        "the policy, then retry."
    ),
    "IdempotencyConflict": _resolved(
        "The idempotencyKey was already used with a different payload. Submit with a new "
        "idempotencyKey."
    ),
    "EstimateUnavailable": _resolved(
        "A cost estimate could not be produced. Retry once; if it persists, simplify the "
        "request or contact the operator."
    ),
    "PromptTooLong": _resolved(
        "The prompt exceeds the model's input limit. Shorten the prompt or choose a model "
        "with a larger context."
    ),
    "ReasoningBudgetExhausted": _resolved(
        "The model spent its whole output budget on reasoning and returned no visible "
        "output. Raise the output budget or simplify the prompt, then retry."
    ),
    "EstimateExceedsMaxCost": _resolved(
        "The quoted cost is above the authorized maximum. Raise the authorization or "
        "reduce the request scope, then submit with a new idempotencyKey."
    ),
    "FundingRequired": _resolved(
        "The account has insufficient funds. Add a payment method or credits, then retry."
    ),
    "ProjectCredentialMismatch": _resolved(
        "The stored provider credential does not belong to this project. Reconnect the "
        "provider with credentials for this project, then retry."
    ),
    "QUOTE_MISMATCH": _resolved(
        "The quote is stale or does not match the server's pricing. Omit quoteId/estimateId "
        "and submit with a new idempotencyKey to reseal pricing."
    ),
    "ESTIMATE_MISMATCH": _resolved(
        "The estimate is stale or does not match the server's pricing. Request a fresh "
        "estimate and submit with a new idempotencyKey."
    ),
    "REESTIMATE_REQUIRED": _resolved(
        "Pricing inputs changed and a new estimate is required. Request a fresh estimate, "
        "then submit with a new idempotencyKey."
    ),
    "COST_LIMIT_EXCEEDED": _resolved(
        "The request exceeds a configured cost limit. Raise the limit or reduce the "
        "request scope, then retry."
    ),
    "ROUTE_UNAVAILABLE": _resolved(
        "The sealed route is no longer routable. Do not retry this job or reuse its "
        "idempotencyKey; submit a new job with a new key and, if the same capability is "
        "still required, pin an alternate provider from error.recovery.alternates."
    ),
    "ROUTE_CASCADE_EXHAUSTED": _resolved(
        "Every sealed route candidate failed. Submit a new job with a new idempotencyKey; "
        "adjust the model or provider preference, or wait if the last failure was transient."
    ),
    "PRICING_INPUTS_REQUIRED": _resolved(
        "Pricing needs more input before it can quote. Supply the missing inputs, then "
        "submit with a new idempotencyKey."
    ),
    "InvalidInput": _resolved(
        "The request failed validation. Fix the fields named in the message, then submit "
        "with a new idempotencyKey."
    ),
    "UnsupportedTld": _resolved(
        "The domain extension is not supported. Choose a supported TLD and submit again."
    ),
    "CatalogUnavailable": _transient(
        "The model or provider catalog could not be loaded. Retry after a short wait."
    ),
    "UNKNOWN_EXECUTION_FIELD": _resolved(
        "The request contained an execution field the server does not recognize. Remove or "
        "correct it, then retry."
    ),
    "CONFLICTING_EXECUTION_CONSTRAINT": _resolved(
        "The request combined execution constraints that cannot both hold. Relax one of "
        "them, then retry."
    ),
    "InternalFailure": _transient(
        "An internal error occurred. Retry after a short wait; if it persists, contact the "
        "operator with the job id."
    ),
    "failed": _resolved(GENERIC_FAILED_ERROR_RESOLUTION),
    "needs_attention": _resolved(NEEDS_ATTENTION_ERROR_RESOLUTION),
}

_JOB_ERROR_CODE_INDEX: dict[str, str] = {code.lower(): code for code in JOB_ERROR_TAXONOMY}


def job_error_guidance(code: str | None) -> dict[str, Any] | None:
    """Known taxonomy row for a code, or ``None`` so the caller does not invent advice."""
    key = str(code or "").strip()
    if not key:
        return None
    entry = JOB_ERROR_TAXONOMY.get(key)
    if entry is None:
        entry = JOB_ERROR_TAXONOMY.get(_JOB_ERROR_CODE_INDEX.get(key.lower(), ""))
    return dict(entry) if entry is not None else None


def project_job_error(error: Any) -> dict[str, Any] | None:
    """Return the public failure projection for a job payload ``error`` field.

    A server-provided ``resolution``/``retryable``/``terminal`` always wins, so the SDK
    reads exactly what the job payload carries. Only a locally constructed error with no
    server projection falls back to the mirrored taxonomy.
    """
    if error is None:
        return None
    if isinstance(error, str):
        message = error.strip() or "Job failed."
        return _project(code="failed", message=message, extra=None)
    if not isinstance(error, dict):
        return None
    code = str(error.get("code") or "failed").strip() or "failed"
    raw_message = error.get("message")
    message = str(raw_message).strip() if raw_message is not None else ""
    if not message or message == code:
        message = f"Job failed with error code {code}."
    return _project(code=code, message=message, extra=error)


def _project(*, code: str, message: str, extra: dict[str, Any] | None) -> dict[str, Any]:
    projected: dict[str, Any] = dict(extra or {})
    guidance = job_error_guidance(code)
    projected["code"] = code
    projected["message"] = message
    if guidance is None:
        projected.setdefault("retryable", False)
        projected.setdefault("resolution", UNKNOWN_JOB_ERROR_RESOLUTION)
        projected.setdefault("terminal", True)
        return projected
    projected.setdefault("retryable", guidance["retryable"])
    projected.setdefault("resolution", guidance["resolution"])
    projected.setdefault("terminal", guidance["terminal"])
    return projected


def attach_error_projection(payload: dict[str, Any]) -> dict[str, Any]:
    """Add resolution/terminal to a tool-result payload for a known code.

    Unknown codes are left untouched: the client never invents guidance for a failure it
    does not have a taxonomy row for.
    """
    guidance = job_error_guidance(str(payload.get("code") or ""))
    if guidance is None:
        return payload
    if "retryable" not in payload:
        payload["retryable"] = guidance["retryable"]
    payload.setdefault("resolution", guidance["resolution"])
    payload.setdefault("terminal", guidance["terminal"])
    return payload


__all__ = [
    "GENERIC_FAILED_ERROR_RESOLUTION",
    "JOB_ERROR_TAXONOMY",
    "NEEDS_ATTENTION_ERROR_RESOLUTION",
    "UNKNOWN_JOB_ERROR_RESOLUTION",
    "attach_error_projection",
    "job_error_guidance",
    "project_job_error",
]
