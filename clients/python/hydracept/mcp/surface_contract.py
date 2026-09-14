"""Public-client copy of the interaction-surface lifecycle.

Keep in sync with packages/contracts/hydracept_contracts/interaction_surfaces.py.
The published hydracept wheel cannot import hydracept_contracts.

Surfaces are states of one App at ``ui://hydracept/app.html``, not independent
widgets. Agents should follow structured ``presentation`` fields rather than
reconstructing this lifecycle from prose.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping

APP_URI = "ui://hydracept/app.html"
INTERACTION_SCHEMA_VERSION = "hydracept.interaction.v1"
INTERACTION_TOOL = "hydracept_interaction_surface"

SurfaceId = Literal[
    "project.connect",
    "capability.launch",
    "connection.resolve",
    "authorization.preflight",
    "job.progress",
    "artifact.review",
    "change.promote",
]

SURFACE_IDS: tuple[SurfaceId, ...] = (
    "project.connect",
    "capability.launch",
    "connection.resolve",
    "authorization.preflight",
    "job.progress",
    "artifact.review",
    "change.promote",
)

PresentationStatus = Literal[
    "mounted",
    "already_mounted",
    "transitioned",
    "fallback",
    "unsupported",
    "failed",
    "mount_requested",
]

AgentAction = Literal["present_and_yield", "present", "continue", "none"]

PRESENTATION_STATUSES: tuple[PresentationStatus, ...] = (
    "mounted",
    "already_mounted",
    "transitioned",
    "fallback",
    "unsupported",
    "failed",
    "mount_requested",
)

AGENT_ACTIONS: tuple[AgentAction, ...] = (
    "present_and_yield",
    "present",
    "continue",
    "none",
)

STATE_OWNERS: dict[str, SurfaceId] = {
    "project_cannot_be_resolved": "project.connect",
    "provider_connection_required": "connection.resolve",
    "paid_execution_awaiting_visibility": "authorization.preflight",
    "job_queued_or_running": "job.progress",
    "reviewable_artifact_produced": "artifact.review",
    "capability_input_needed": "capability.launch",
    "repository_change_requested": "change.promote",
}

INTERACTION_SURFACES: dict[str, dict[str, Any]] = {
    "project.connect": {
        "trigger": "project_resolution_requires_human",
        "blocking": True,
        "agentAction": "present_and_yield",
        "owns": "project_cannot_be_resolved",
        "next": {"workspace_ready": "authorization.preflight"},
    },
    "capability.launch": {
        "trigger": "capability_input_or_tuning_available",
        "blocking": False,
        "agentAction": "present",
        "owns": "capability_input_needed",
        "next": {"launch_submitted": "authorization.preflight"},
    },
    "connection.resolve": {
        "trigger": "provider_connection_required",
        "blocking": True,
        "agentAction": "present_and_yield",
        "owns": "provider_connection_required",
        "next": {"connection_ready": "authorization.preflight"},
    },
    "authorization.preflight": {
        "trigger": "paid_or_irreversible_execution",
        "blocking": "policy_dependent",
        "agentAction": "policy_dependent",
        "owns": "paid_execution_awaiting_visibility",
        "next": {"authorization_accepted": "job.progress"},
    },
    "job.progress": {
        "trigger": "job_submitted",
        "blocking": False,
        "agentAction": "present",
        "owns": "job_queued_or_running",
        "next": {"reviewable_artifact_succeeded": "artifact.review"},
    },
    "artifact.review": {
        "trigger": "reviewable_artifact_available",
        "blocking": False,
        "agentAction": "present",
        "owns": "reviewable_artifact_produced",
        "next": {"promotion_requested": "change.promote"},
    },
    "change.promote": {
        "trigger": "repository_change_requested",
        "blocking": True,
        "agentAction": "present_and_yield",
        "owns": "repository_change_requested",
        "next": {},
    },
}

_VISUAL_PREFIXES = (
    "image.",
    "video.",
    "model3d.",
    "mesh.",
    "3d.",
    "sheet.",
)
_VISUAL_MEDIA_PREFIXES = ("image/", "video/", "model/")
_REVIEWABLE_PREFIXES = _VISUAL_PREFIXES + ("audio.",)
_REVIEWABLE_MEDIA_PREFIXES = _VISUAL_MEDIA_PREFIXES + ("audio/",)
_TERMINAL_SUCCESS = frozenset({"succeeded", "completed"})
_RUNNING = frozenset({"queued", "submitted", "running", "processing", "canceling"})


def surface_catalog(*, compact: bool = False) -> dict[str, Any]:
    if compact:
        return {
            "appUri": APP_URI,
            "schemaVersion": INTERACTION_SCHEMA_VERSION,
            "tool": INTERACTION_TOOL,
            "oneApp": True,
            "surfaces": {
                key: {
                    "trigger": value["trigger"],
                    "blocking": value["blocking"],
                }
                for key, value in INTERACTION_SURFACES.items()
            },
            "stateOwners": dict(STATE_OWNERS),
        }
    return {
        "appUri": APP_URI,
        "schemaVersion": INTERACTION_SCHEMA_VERSION,
        "tool": INTERACTION_TOOL,
        "oneApp": True,
        "surfaces": dict(INTERACTION_SURFACES),
        "stateOwners": dict(STATE_OWNERS),
        "agentActions": {
            "present_and_yield": (
                "Present the requested Hydracept surface. Do not perform unrelated "
                "tool calls afterward in the same turn. Do not bury the surface "
                "under an assessment. Yield control to the user/application."
            ),
            "present": (
                "Present or keep the Hydracept App visible. Further agent work in "
                "the same turn is allowed only when it does not replace the App."
            ),
            "continue": "No presentation change is required.",
            "none": "No agent presentation action.",
        },
        "presentationStatuses": list(PRESENTATION_STATUSES),
    }


def is_visual_capability(capability_key: str | None) -> bool:
    """Compatibility helper for callers that specifically need visual media."""
    key = str(capability_key or "").strip().lower()
    return bool(key) and key.startswith(_VISUAL_PREFIXES)


def is_visual_media_type(media_type: str | None) -> bool:
    """Compatibility helper for callers that specifically need visual media."""
    value = str(media_type or "").strip().lower()
    return bool(value) and value.startswith(_VISUAL_MEDIA_PREFIXES)


def is_reviewable_capability(capability_key: str | None) -> bool:
    """Whether successful output should transition into artifact.review."""
    key = str(capability_key or "").strip().lower()
    return bool(key) and key.startswith(_REVIEWABLE_PREFIXES)


def is_reviewable_media_type(media_type: str | None) -> bool:
    """Whether an artifact media type belongs on the review surface."""
    value = str(media_type or "").strip().lower()
    return bool(value) and value.startswith(_REVIEWABLE_MEDIA_PREFIXES)


def surface_for_job_status(
    status: str | None,
    *,
    visual: bool = False,
    reviewable: bool | None = None,
) -> SurfaceId:
    """Return lifecycle ownership; presentation may still be explicitly no-op.

    ``visual`` remains a backwards-compatible alias. New callers should pass
    ``reviewable`` because audio artifacts are reviewable too.
    """
    normalized = str(status or "").strip().lower()
    should_review = bool(visual if reviewable is None else reviewable)
    if normalized in _TERMINAL_SUCCESS:
        return "artifact.review" if should_review else "job.progress"
    if normalized == "awaiting_approval":
        return "authorization.preflight"
    if normalized in _RUNNING or not normalized:
        return "job.progress"
    if normalized in {"failed", "failed_terminal", "canceled", "cancelled", "needs_attention"}:
        return "job.progress"
    return "job.progress"


def next_presentation(surface: str, when: str) -> dict[str, str] | None:
    catalog = INTERACTION_SURFACES.get(surface) or {}
    nxt = catalog.get("next") or {}
    target = nxt.get(when)
    if not target:
        return None
    return {"surface": str(target), "when": when}


def default_agent_action(surface: str, *, confirmation_required: bool | None = None) -> AgentAction:
    catalog = INTERACTION_SURFACES.get(surface) or {}
    raw = catalog.get("agentAction")
    if raw == "policy_dependent":
        if confirmation_required is None:
            return "present_and_yield"
        return "present_and_yield" if confirmation_required else "present"
    if raw in AGENT_ACTIONS:
        return raw  # type: ignore[return-value]
    blocking = catalog.get("blocking")
    return "present_and_yield" if blocking is True else "present"


def default_blocking(surface: str, *, confirmation_required: bool | None = None) -> bool:
    catalog = INTERACTION_SURFACES.get(surface) or {}
    blocking = catalog.get("blocking")
    if blocking == "policy_dependent":
        return True if confirmation_required is None else bool(confirmation_required)
    return bool(blocking)


def authorization_contract(
    *,
    confirmation_required: bool,
    status: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    resolved_status = status or (
        "confirmation_required" if confirmation_required else "not_required"
    )
    payload: dict[str, Any] = {
        "status": resolved_status,
        "confirmationRequired": bool(confirmation_required),
    }
    if reason:
        payload["reason"] = reason
    return payload


_POSITIVE_HOST_CONFIRMATIONS = frozenset({"acked", "acknowledged", "observed", "confirmed"})


def presentation_contract(
    *,
    surface: str,
    status: PresentationStatus,
    agent_action: AgentAction | None = None,
    blocking: bool | None = None,
    preferred: bool = True,
    reason: str | None = None,
    fallback: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
    next_presentation_meta: Mapping[str, Any] | None = None,
    authorization: Mapping[str, Any] | None = None,
    surface_session_id: str | None = None,
    host_confirmation: str | None = None,
    requested: str | None = None,
) -> dict[str, Any]:
    confirmation_required = None
    if authorization and "confirmationRequired" in authorization:
        confirmation_required = bool(authorization["confirmationRequired"])
    resolved_action = agent_action or default_agent_action(
        surface, confirmation_required=confirmation_required
    )
    resolved_blocking = (
        default_blocking(surface, confirmation_required=confirmation_required)
        if blocking is None
        else blocking
    )
    resolved_status = status
    resolved_confirmation = host_confirmation
    if resolved_status in {"mounted", "already_mounted"}:
        if resolved_confirmation not in _POSITIVE_HOST_CONFIRMATIONS:
            resolved_status = "mount_requested"
            resolved_confirmation = resolved_confirmation or "unobserved"
    elif resolved_status == "mount_requested" and not resolved_confirmation:
        resolved_confirmation = "unobserved"
    payload: dict[str, Any] = {
        "requested": requested or surface,
        "surface": surface,
        "appUri": APP_URI,
        "uri": APP_URI,
        "status": resolved_status,
        "preferred": bool(preferred),
        "blocking": bool(resolved_blocking),
        "agentAction": resolved_action,
        "tool": INTERACTION_TOOL,
    }
    if reason:
        payload["reason"] = reason
    if fallback:
        payload["fallback"] = dict(fallback)
    if context:
        payload["context"] = dict(context)
    if next_presentation_meta:
        payload["next"] = dict(next_presentation_meta)
    if authorization:
        payload["authorization"] = dict(authorization)
    if surface_session_id:
        payload["surfaceSessionId"] = surface_session_id
    if resolved_confirmation:
        payload["hostConfirmation"] = resolved_confirmation
    return payload
