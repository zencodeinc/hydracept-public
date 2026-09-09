"""Attach and interpret Hydracept presentation envelopes."""

from __future__ import annotations

from typing import Any, Mapping
from uuid import uuid4

from hydracept.mcp.surface_contract import (
    APP_URI,
    INTERACTION_SCHEMA_VERSION,
    INTERACTION_TOOL,
    AgentAction,
    PresentationStatus,
    authorization_contract,
    default_agent_action,
    default_blocking,
    is_visual_capability,
    is_visual_media_type,
    next_presentation,
    presentation_contract,
    surface_for_job_status,
)

__all__ = [
    "APP_URI",
    "INTERACTION_SCHEMA_VERSION",
    "INTERACTION_TOOL",
    "attach_presentation",
    "authorization_from_context",
    "job_presentation",
    "presentation_for_host",
    "smoke_presentation",
]

_TERMINAL_SUCCESS = frozenset({"succeeded", "completed"})


def _new_surface_session_id(existing: str | None = None) -> str:
    value = str(existing or "").strip()
    if value.startswith("uis_"):
        return value
    return f"uis_{uuid4().hex[:16]}"


def presentation_for_host(
    surface: str,
    *,
    apps_supported: bool,
    form_supported: bool = False,
    interactive: bool = True,
    confirmation_required: bool | None = None,
    context: Mapping[str, Any] | None = None,
    authorization: Mapping[str, Any] | None = None,
    already_mounted: bool = False,
    transitioned: bool = False,
    status: PresentationStatus | None = None,
) -> dict[str, Any]:
    """Distinguish App mount from structured fallback. Never infer from form schema."""
    ctx = dict(context or {})
    session_id = _new_surface_session_id(str(ctx.get("surfaceSessionId") or "") or None)
    nxt = None
    if surface == "authorization.preflight":
        nxt = next_presentation(surface, "authorization_accepted")
    elif surface == "project.connect":
        nxt = next_presentation(surface, "workspace_ready")

    if not interactive and not apps_supported:
        resolved_status: PresentationStatus = "fallback"
        reason = "interactive_disabled"
        fallback: dict[str, Any] | None = {"kind": "structured_form"}
    elif apps_supported:
        if status:
            resolved_status = status
        elif transitioned:
            resolved_status = "transitioned"
        elif already_mounted:
            resolved_status = "already_mounted"
        else:
            resolved_status = "mounted"
        reason = None
        fallback = None
    elif surface == "job.progress":
        resolved_status = "fallback"
        reason = "host_does_not_support_apps"
        fallback = {"kind": "structured_contract"}
    elif form_supported:
        resolved_status = "fallback"
        reason = "host_does_not_support_apps"
        fallback = {"kind": "structured_form"}
    else:
        resolved_status = "fallback"
        reason = "host_does_not_support_apps"
        fallback = {"kind": "structured_contract"}

    agent_action: AgentAction = default_agent_action(
        surface, confirmation_required=confirmation_required
    )
    return presentation_contract(
        surface=surface,
        status=resolved_status,
        agent_action=agent_action,
        blocking=default_blocking(surface, confirmation_required=confirmation_required),
        reason=reason,
        fallback=fallback,
        context=ctx or None,
        next_presentation_meta=nxt,
        authorization=authorization,
        surface_session_id=session_id,
        host_confirmation=(
            "unobserved"
            if resolved_status in {"mounted", "already_mounted", "transitioned"}
            else None
        ),
    )


def authorization_from_context(context: Mapping[str, Any], *, policy_requires: bool) -> dict[str, Any]:
    """Separate preflight visibility from a confirmation click."""
    if policy_requires:
        return authorization_contract(
            confirmation_required=True,
            status="confirmation_required",
            reason="policy_requires_confirmation",
        )
    user_intent = bool(
        context.get("userIntentAuthorized")
        or context.get("alreadyAuthorizedByUserIntent")
        or context.get("userRequestedExecution")
        or context.get("smoke")
        or context.get("explicitUserRequest")
    )
    return authorization_contract(
        confirmation_required=False,
        status="already_authorized_by_user_intent" if user_intent else "not_required",
        reason="user_requested_execution" if user_intent else "policy_does_not_require_confirmation",
    )


def attach_presentation(payload: dict[str, Any], presentation: Mapping[str, Any]) -> dict[str, Any]:
    attached = dict(payload)
    attached["presentation"] = dict(presentation)
    return attached


def job_presentation(
    payload: Mapping[str, Any],
    *,
    apps_supported: bool | None = None,
) -> dict[str, Any]:
    """Present active work and visual review; typed terminal output is a no-op."""
    job = payload.get("job") if isinstance(payload.get("job"), Mapping) else payload
    status = str(payload.get("status") or payload.get("state") or job.get("status") or "")
    normalized_status = status.strip().lower()
    capability_key = str(
        payload.get("capabilityKey")
        or job.get("capabilityKey")
        or ""
    )
    artifacts = job.get("artifacts") if isinstance(job.get("artifacts"), list) else payload.get("artifacts")
    media_type = None
    artifact_id = str(payload.get("primaryArtifactId") or payload.get("artifactId") or "")
    if isinstance(artifacts, list):
        for item in artifacts:
            if not isinstance(item, Mapping):
                continue
            artifact_id = artifact_id or str(item.get("artifactId") or item.get("id") or "")
            media_type = item.get("mediaType") or item.get("media_type")
            if media_type:
                break
    visual = is_visual_capability(capability_key) or is_visual_media_type(
        str(media_type or payload.get("mediaType") or "")
    )
    surface = surface_for_job_status(status, visual=visual)

    context: dict[str, Any] = {
        "jobId": str(payload.get("jobId") or job.get("jobId") or job.get("id") or ""),
        "projectId": str(payload.get("projectId") or job.get("projectId") or ""),
        "environment": str(payload.get("environment") or job.get("environment") or ""),
        "capabilityKey": capability_key,
    }
    if artifact_id:
        context["artifactId"] = artifact_id
    if media_type:
        context["mediaType"] = str(media_type)

    if normalized_status in _TERMINAL_SUCCESS and not visual:
        return presentation_contract(
            surface="job.progress",
            status="unsupported",
            preferred=False,
            blocking=False,
            agent_action="none",
            reason="typed_result_requires_no_review_surface",
            context=context,
        )

    confirmation_required = True if surface == "authorization.preflight" else None
    status_name: PresentationStatus
    if apps_supported is True:
        status_name = "mounted"
    elif apps_supported is False:
        status_name = "fallback"
    else:
        status_name = "mount_requested"
    return presentation_contract(
        surface=surface,
        status=status_name,
        preferred=True,
        blocking=default_blocking(surface, confirmation_required=confirmation_required),
        agent_action=default_agent_action(surface, confirmation_required=confirmation_required),
        context=context,
        next_presentation_meta=(
            next_presentation("job.progress", "visual_artifact_succeeded")
            if surface == "job.progress" and visual
            else None
        ),
        reason=None if apps_supported is not False else "host_does_not_support_apps",
        fallback={"kind": "structured_contract"} if apps_supported is False else None,
        host_confirmation="unobserved" if apps_supported is True else None,
    )


def smoke_presentation(
    *,
    job_id: str,
    artifact_id: str | None,
    media_type: str | None = "image/png",
    capability_key: str = "image.generate.v1",
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "jobId": job_id,
        "capabilityKey": capability_key,
    }
    if artifact_id:
        context["artifactId"] = artifact_id
    if media_type:
        context["mediaType"] = media_type
    return presentation_contract(
        surface="artifact.review",
        status="mount_requested",
        preferred=True,
        blocking=False,
        agent_action="present",
        context=context,
    )
