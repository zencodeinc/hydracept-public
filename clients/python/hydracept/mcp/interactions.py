"""IDE-native Hydracept interaction contracts and MCP elicitation adapter."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal, Mapping

from mcp.server.mcpserver.context import Context
from mcp_types import ElicitRequest, ElicitRequestFormParams, ElicitResult, InputRequiredResult
from mcp_types.version import is_version_at_least

from hydracept.mcp.presentation import (
    authorization_from_context,
    presentation_for_host,
)

INTERACTION_SCHEMA_VERSION = "hydracept.interaction.v1"
_INPUT_REQUIRED_PROTOCOL = "2026-07-28"

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

_SECRET_MARKERS = (
    "secret",
    "apikey",
    "password",
    "credential",
    "privatekey",
    "accesskey",
)
_TOKEN_PREFIXES = (
    "access",
    "api",
    "auth",
    "bearer",
    "id",
    "provider",
    "refresh",
    "secret",
    "session",
)
_TERMINAL_STATES = {
    "succeeded",
    "completed",
    "failed",
    "failed_terminal",
    "canceled",
    "cancelled",
    "blocked_budget",
    "blocked_provider",
    "needs_attention",
}


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(by_alias=True)
        if isinstance(dumped, Mapping):
            return dumped
    return {}


def _read(value: Any, *names: str, default: Any = None) -> Any:
    data = _mapping(value)
    for name in names:
        if name in data and data[name] is not None:
            return data[name]
        if hasattr(value, name):
            attribute = getattr(value, name)
            if attribute is not None:
                return attribute
    return default


def is_secret_field(name: str) -> bool:
    """True for credential-bearing field names, but not normal token-count inputs."""
    normalized = "".join(ch for ch in name.lower() if ch.isalnum())
    if any(marker in normalized for marker in _SECRET_MARKERS):
        return True
    if normalized == "token":
        return True
    if not normalized.endswith("token"):
        return False
    stem = normalized[:-5]
    return any(stem.endswith(prefix) for prefix in _TOKEN_PREFIXES)


def _field(
    name: str,
    label: str,
    *,
    kind: str = "string",
    value: Any = None,
    required: bool = False,
    read_only: bool = False,
    options: list[Any] | None = None,
) -> dict[str, Any]:
    field: dict[str, Any] = {
        "name": name,
        "label": label,
        "kind": kind,
        "required": required,
        "readOnly": read_only,
    }
    if value is not None:
        field["value"] = value
    if options:
        field["options"] = options
    return field


def _action(
    action_id: str,
    label: str,
    intent: str,
    *,
    primary: bool = False,
) -> dict[str, Any]:
    return {
        "id": action_id,
        "label": label,
        "intent": intent,
        "primary": primary,
        "style": "primary" if primary else "secondary",
    }


def _surface(
    surface_id: SurfaceId,
    title: str,
    description: str,
    *,
    fields: list[dict[str, Any]] | None = None,
    actions: list[dict[str, Any]] | None = None,
    risk: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    fallback: list[str],
) -> dict[str, Any]:
    safe_fields = [
        field
        for field in fields or []
        if not is_secret_field(str(field.get("name") or ""))
    ]
    return {
        "schemaVersion": INTERACTION_SCHEMA_VERSION,
        "surface": surface_id,
        "title": title,
        "description": description,
        "fields": safe_fields,
        "actions": actions or [],
        "risk": risk or {},
        "data": data or {},
        "fallback": {
            "summary": fallback[0],
            "nextActions": fallback[1:],
        },
    }


def _approval_requirements(capability: Any) -> dict[str, Any]:
    approval = _mapping(
        _read(capability, "approvalRequirements", "approval_requirements", default={})
    )
    return {
        "requiresHumanApproval": bool(
            _read(
                approval,
                "requiresHumanApproval",
                "requires_human_approval",
                default=False,
            )
        ),
        "requiredSecretScopes": list(
            _read(
                approval,
                "requiredSecretScopes",
                "required_secret_scopes",
                default=[],
            )
            or []
        ),
        "requiredAssetApprovals": list(
            _read(
                approval,
                "requiredAssetApprovals",
                "required_asset_approvals",
                default=[],
            )
            or []
        ),
        "maxEstimatedCostCents": _read(
            approval,
            "maxEstimatedCostCents",
            "max_estimated_cost_cents",
        ),
        "dataSensitivity": _read(approval, "dataSensitivity", "data_sensitivity"),
        "irreversibleEffects": list(
            _read(
                approval,
                "irreversibleEffects",
                "irreversible_effects",
                default=[],
            )
            or []
        ),
        "expectedOutputDelivery": _read(
            approval,
            "expectedOutputDelivery",
            "expected_output_delivery",
        ),
    }


def project_connect_surface(context: Mapping[str, Any]) -> dict[str, Any]:
    known_name = str(context.get("displayName") or context.get("suggestedName") or "").strip()
    action_url = str(context.get("actionUrl") or context.get("connectUrl") or "")
    if not action_url:
        action = context.get("action")
        if isinstance(action, Mapping):
            action_url = str(action.get("url") or "")
    bootstrap = str(context.get("status") or "") == "interaction_required" or bool(action_url)
    name_locked = bootstrap and bool(known_name)
    fields = [
        _field(
            "projectId",
            "Project ID",
            value=context.get("projectId") or "",
            read_only=True,
        ),
        _field(
            "displayName",
            "Project name",
            value=known_name,
            required=not name_locked,
            read_only=name_locked,
        ),
        _field(
            "environment",
            "Environment",
            kind="select",
            value=context.get("environment") or "development",
            required=not name_locked,
            read_only=name_locked,
            options=list(
                context.get("environments")
                or ["development", "staging", "production"]
            ),
        ),
    ]
    if context.get("accountName"):
        fields.insert(
            1,
            _field(
                "accountName",
                "Account",
                value=context["accountName"],
                read_only=True,
            ),
        )
    if context.get("detectedRoot"):
        fields.append(
            _field(
                "detectedRoot",
                "Repository",
                value=context["detectedRoot"],
                read_only=True,
            )
        )
    description = (
        "Approve this workspace in your browser. Hydracept already has the project name."
        if name_locked
        else "Confirm project name and environment without leaving the agent flow."
    )
    return _surface(
        "project.connect",
        "Connect this project",
        description,
        fields=fields,
        actions=[
            _action("connect", "Connect project", "apply", primary=True),
            _action("cancel", "Cancel", "cancel"),
        ],
        data={
            "authority": "existing_init_apply_doctor",
            "stableIdentityField": "projectId",
            "status": context.get("status"),
            "action": deepcopy(context["action"])
            if isinstance(context.get("action"), Mapping)
            else None,
            "actionUrl": action_url or context.get("actionUrl") or context.get("connectUrl"),
            "displayName": known_name or None,
            "autoConnect": name_locked,
        },
        fallback=[
            "Use the existing init/apply/doctor path.",
            "python -m hydracept init --apply --yes --json",
            "python -m hydracept doctor",
        ],
    )


def capability_launch_surface(context: Mapping[str, Any]) -> dict[str, Any]:
    capability = context.get("capability") or context
    capability_key = str(
        _read(capability, "key", default=context.get("capabilityKey") or "")
    )
    schema = _mapping(
        _read(
            capability,
            "inputSchema",
            "input_schema",
            "requestSchema",
            "request_schema",
            default={},
        )
    )
    required = set(schema.get("required") or [])
    defaults = _mapping(context.get("defaults"))
    fields: list[dict[str, Any]] = []
    excluded_fields: list[str] = []

    for name, raw_schema in _mapping(schema.get("properties")).items():
        field_name = str(name)
        if is_secret_field(field_name):
            excluded_fields.append(field_name)
            continue
        field_schema = _mapping(raw_schema)
        field_type = str(field_schema.get("type") or "string")
        options = list(field_schema.get("enum") or []) or None
        fields.append(
            _field(
                field_name,
                str(field_schema.get("title") or field_name),
                kind="select" if options else field_type,
                value=defaults.get(field_name, field_schema.get("default")),
                required=field_name in required,
                options=options,
            )
        )

    return _surface(
        "capability.launch",
        str(
            _read(
                capability,
                "displayName",
                "name",
                default=capability_key or "Run capability",
            )
        ),
        str(_read(capability, "description", default="Provide capability inputs.")),
        fields=fields,
        actions=[
            _action("run", "Run", "submit", primary=True),
            _action("cancel", "Cancel", "cancel"),
        ],
        risk=_approval_requirements(capability),
        data={
            "capabilityKey": capability_key,
            "inputSchema": deepcopy(dict(schema)),
            "uiSchema": deepcopy(
                dict(
                    _mapping(
                        _read(capability, "uiSchema", "ui_schema", default={})
                    )
                )
            ),
            "executionModes": list(
                _read(capability, "executionModes", "execution_modes", default=[]) or []
            ),
            "estimateAvailable": bool(
                _read(capability, "estimateAvailable", "estimate_available", default=False)
            ),
            "pricing": deepcopy(_mapping(_read(capability, "pricing", default={})) or {}),
            "workspaceRunnable": deepcopy(
                _mapping(_read(capability, "workspaceRunnable", "workspace_runnable", default={}))
                or {}
            ),
            "approvalRequirements": deepcopy(
                _mapping(
                    _read(
                        capability,
                        "approvalRequirements",
                        "approval_requirements",
                        default={},
                    )
                )
                or {}
            ),
            "excludedInteractiveFields": excluded_fields,
        },
        fallback=[
            "Build a normal Hydracept run/invoke request from the catalogue schema.",
            f"python -m hydracept capabilities describe {capability_key}",
        ],
    )


def connection_resolve_surface(context: Mapping[str, Any]) -> dict[str, Any]:
    scopes = list(context.get("requiredSecretScopes") or [])
    fields = [
        _field(
            "capabilityKey",
            "Capability",
            value=context.get("capabilityKey") or "",
            read_only=True,
        ),
        _field(
            "provider",
            "Provider",
            value=context.get("provider") or "",
            read_only=True,
        ),
        _field(
            "requiredScopes",
            "Required connection scopes",
            kind="array",
            value=scopes,
            read_only=True,
        ),
        _field(
            "status",
            "Connection status",
            value=context.get("status") or "missing",
            read_only=True,
        ),
    ]
    return _surface(
        "connection.resolve",
        "Connect a provider",
        "Resolve an authenticated connection without collecting provider secrets in MCP.",
        fields=fields,
        actions=[
            _action("connect", "Connect provider", "authorize", primary=True),
            _action("recheck", "Recheck", "recheck"),
            _action("cancel", "Cancel", "cancel"),
        ],
        risk={"requiredSecretScopes": scopes},
        data={
            "acceptsSecrets": False,
            "capabilityKey": context.get("capabilityKey") or "",
            "actionUrl": context.get("connectUrl") or context.get("actionUrl"),
            "connectUrl": context.get("connectUrl") or context.get("actionUrl"),
        },
        fallback=[
            "Use authenticated setup/Studio, then recheck.",
            "Do not paste provider secrets into agent chat or MCP arguments.",
        ],
    )


def authorization_preflight_surface(context: Mapping[str, Any]) -> dict[str, Any]:
    capability = context.get("capability") or context
    capability_key = str(
        _read(capability, "key", default=context.get("capabilityKey") or "")
    )
    risk = _approval_requirements(capability)
    estimated_cents = context.get(
        "estimatedCostCents",
        context.get("estimated_cost_cents"),
    )
    cost_display = (
        context.get("estimatedCostDisplay")
        or context.get("costDisplay")
        or context.get("displayCost")
    )
    currency = context.get("currency")

    if estimated_cents is not None:
        risk["estimatedCostCents"] = estimated_cents
    if cost_display:
        risk["estimatedCostDisplay"] = str(cost_display)
    if currency:
        risk["currency"] = currency

    fields = [
        _field(
            "capabilityKey",
            "Capability",
            value=capability_key,
            read_only=True,
        )
    ]
    if cost_display:
        fields.append(
            _field(
                "estimatedCostDisplay",
                "Estimated maximum cost",
                value=str(cost_display),
                read_only=True,
            )
        )
    elif estimated_cents is not None:
        fields.append(
            _field(
                "estimatedCostCents",
                "Estimated maximum cost (cents)",
                kind="integer",
                value=estimated_cents,
                read_only=True,
            )
        )
    if risk["requiredSecretScopes"]:
        fields.append(
            _field(
                "requiredScopes",
                "Required connections",
                kind="array",
                value=risk["requiredSecretScopes"],
                read_only=True,
            )
        )
    if risk["irreversibleEffects"]:
        fields.append(
            _field(
                "irreversibleEffects",
                "Irreversible effects",
                kind="array",
                value=risk["irreversibleEffects"],
                read_only=True,
            )
        )
    if risk.get("dataSensitivity"):
        fields.append(
            _field(
                "dataSensitivity",
                "Sensitivity",
                value=risk["dataSensitivity"],
                read_only=True,
            )
        )
    if risk.get("requiredAssetApprovals"):
        fields.append(
            _field(
                "requiredAssetApprovals",
                "Asset approvals",
                kind="array",
                value=risk["requiredAssetApprovals"],
                read_only=True,
            )
        )

    policy_requires = bool(
        risk["requiresHumanApproval"]
        or risk["irreversibleEffects"]
        or risk["requiredAssetApprovals"]
        or context.get("requiresAuthorization")
        or context.get("approval")
    )
    ceiling = risk.get("maxEstimatedCostCents")
    estimated = estimated_cents
    if ceiling is not None and estimated is not None:
        try:
            if int(estimated) > int(ceiling):
                policy_requires = True
        except (TypeError, ValueError):
            pass
    authorization = authorization_from_context(context, policy_requires=policy_requires)
    confirmation_required = bool(authorization.get("confirmationRequired"))
    primary_action = _action(
        "authorize" if confirmation_required else "continue",
        "Authorize" if confirmation_required else "Continue",
        "authorize" if confirmation_required else "continue",
        primary=True,
    )
    actions = [primary_action]
    if context.get("approval"):
        actions.append(_action("reject", "Reject", "reject"))
    actions.append(_action("cancel", "Cancel", "cancel"))
    contract = _surface(
        "authorization.preflight",
        "Review before execution",
        "Price is always visible. Execution is blocked only when approval policy or irreversible effects require it.",
        fields=fields,
        actions=actions,
        risk={
            **risk,
            "costAuthorizationPolicy": "show_price_block_on_policy",
            "needsAuthorization": confirmation_required,
            "confirmationRequired": confirmation_required,
        },
        data={
            "capabilityKey": capability_key,
            "approval": deepcopy(context.get("approval")) if context.get("approval") else None,
            "request": deepcopy(context.get("request")) if isinstance(context.get("request"), Mapping) else None,
            "jobId": context.get("jobId"),
            "authorization": authorization,
        },
        fallback=[
            "Keep approval separate from execution.",
            "quote or estimate",
            "explicit human approval when policy requires it",
            "existing execution tool",
        ],
    )
    contract["authorization"] = authorization
    return contract


def job_progress_surface(context: Mapping[str, Any]) -> dict[str, Any]:
    job = context.get("job") or context
    state = str(_read(job, "status", "state", "businessState", default="unknown"))
    fields = [
        _field(
            "jobId",
            "Job",
            value=_read(job, "jobId", "id", default=""),
            read_only=True,
        ),
        _field("status", "Status", value=state, read_only=True),
    ]
    capability_key = _read(job, "capabilityKey", "capability_key")
    if capability_key:
        fields.insert(
            1,
            _field(
                "capabilityKey",
                "Capability",
                value=capability_key,
                read_only=True,
            ),
        )

    terminal = state.lower() in _TERMINAL_STATES
    job_id = _read(job, "jobId", "id", default="") or context.get("jobId") or ""
    actions = [
        _action("refresh", "Refresh", "recheck", primary=not terminal),
        (
            _action("receipt", "View receipt", "inspect", primary=True)
            if terminal
            else _action("close", "Stop watching", "stop")
        ),
    ]
    if not terminal:
        actions.append(_action("cancel-job", "Cancel job", "cancel-job"))
    return _surface(
        "job.progress",
        "Hydracept job",
        "Keep execution state and artifacts visible while the agent continues.",
        fields=fields,
        actions=actions,
        data={
            "jobId": job_id,
            "capabilityKey": capability_key,
            "status": state,
            "nextAction": _read(job, "nextAction", "next_action"),
            "pollAfterSeconds": _read(job, "pollAfterSeconds", "poll_after_seconds"),
            "artifacts": list(_read(job, "artifacts", default=[]) or []),
            "error": _read(job, "error"),
            "receiptId": _read(job, "receiptId", "receipt_id"),
        },
        fallback=[
            "Follow the existing job lifecycle.",
            "hydracept_job_status",
            "hydracept_get_receipt when terminal",
        ],
    )


def artifact_review_surface(context: Mapping[str, Any]) -> dict[str, Any]:
    artifacts = []
    for raw_artifact in context.get("artifacts") or []:
        artifact = _mapping(raw_artifact)
        artifact_id = artifact.get("artifactId") or artifact.get("id")
        artifacts.append(
            {
                "id": artifact_id,
                "artifactId": artifact_id,
                "filename": artifact.get("filename") or artifact.get("label") or artifact_id,
                "label": (
                    artifact.get("label")
                    or artifact.get("filename")
                    or artifact_id
                ),
                "kind": artifact.get("kind") or artifact.get("type"),
                "mediaType": artifact.get("mediaType") or artifact.get("media_type"),
                "previewUri": (
                    artifact.get("previewUri")
                    or artifact.get("url")
                    or artifact.get("uri")
                ),
                "metadata": deepcopy(artifact.get("metadata") or {}),
            }
        )

    artifact_ids = [artifact["id"] for artifact in artifacts if artifact.get("id")]
    typed_output = context.get("typedOutput") or context.get("output")
    fields = (
        [
            _field(
                "selectedArtifactId",
                "Selected artifact",
                kind="select",
                options=artifact_ids,
                required=True,
            )
        ]
        if artifact_ids and (
            len(artifact_ids) > 1
            or bool(context.get("reviewRequired") or context.get("requiresAssetApproval"))
        )
        else []
    )
    authority = context.get("reviewAuthority")
    executable_review = isinstance(authority, Mapping) and bool(
        authority.get("executable") or authority.get("approve")
    )
    review_gate = bool(context.get("reviewRequired") or context.get("requiresAssetApproval"))
    if executable_review:
        actions = [
            _action("approve", "Approve", "approve", primary=True),
            _action("reject", "Reject", "reject"),
            _action("cancel", "Cancel", "cancel"),
        ]
        description = "Compare outputs before approval; approval does not promote them."
        fallback = [
            "Inspect then explicitly approve or reject.",
            "download/inspect artifact",
            "promote separately if needed",
        ]
    elif len(artifact_ids) > 1:
        actions = [
            _action("select", "Select", "select", primary=True),
            _action("download", "Download", "download"),
            _action("cancel", "Cancel", "cancel"),
        ]
        description = "Choose among peer outputs. Selection is not an approval gate."
        fallback = [
            "Select one artifact, then download.",
            "hydracept_download_artifact(job_id, artifact_id=)",
        ]
    else:
        actions = [
            _action("use", "Use", "use", primary=True),
            _action("download", "Download", "download"),
            _action("cancel", "Cancel", "cancel"),
        ]
        description = "Use or download the primary output. This is not an approval gate."
        fallback = [
            "Download via primaryArtifactId.",
            "hydracept_download_artifact(job_id)",
            "promote separately if a repository change is requested",
        ]
    return _surface(
        "artifact.review",
        "Review generated artifacts",
        description,
        fields=fields,
        actions=actions,
        data={
            "artifacts": artifacts,
            "reviewRequired": review_gate,
            "typedOutput": typed_output,
            "reviewAuthority": deepcopy(authority) if isinstance(authority, Mapping) else None,
            "capabilityKey": context.get("capabilityKey")
            or _read(context.get("job") or context, "capabilityKey", "capability_key"),
            "jobId": context.get("jobId")
            or _read(context.get("job") or context, "jobId", "id"),
        },
        fallback=fallback,
    )


def change_promote_surface(context: Mapping[str, Any]) -> dict[str, Any]:
    paths = list(context.get("surfacePaths") or context.get("paths") or [])
    fields = [
        _field(
            "projectId",
            "Project",
            value=context.get("projectId") or "",
            read_only=True,
        ),
        _field(
            "validationStatus",
            "Validation",
            value=context.get("validationStatus") or "unknown",
            read_only=True,
        ),
    ]
    if paths:
        fields.append(
            _field(
                "surfacePath",
                "Surface definition",
                kind="select" if len(paths) > 1 else "string",
                value=paths[0],
                required=True,
                read_only=len(paths) <= 1,
                options=paths if len(paths) > 1 else None,
            )
        )
    return _surface(
        "change.promote",
        "Promote approved changes",
        "Review destination and validation before the project-local agent writes changes.",
        fields=fields,
        actions=[
            _action("promote", "Promote", "apply", primary=True),
            _action("cancel", "Cancel", "cancel"),
        ],
        data={
            "changes": list(context.get("changes") or context.get("files") or []),
            "surfacePaths": paths,
            "authority": "project-local-agent",
            "centralServiceWritesRepository": False,
            "promoteEnabled": bool(context.get("promoteEnabled", True)),
        },
        fallback=[
            "Use existing project-local promotion/apply.",
            "validate",
            "explicit approval",
            "project-local promote/apply",
        ],
    )


_BUILDERS = {
    "project.connect": project_connect_surface,
    "capability.launch": capability_launch_surface,
    "connection.resolve": connection_resolve_surface,
    "authorization.preflight": authorization_preflight_surface,
    "job.progress": job_progress_surface,
    "artifact.review": artifact_review_surface,
    "change.promote": change_promote_surface,
}


def build_interaction_surface(
    surface: str,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        builder = _BUILDERS[surface]
    except KeyError as exc:
        raise ValueError(f"surface must be one of: {', '.join(SURFACE_IDS)}") from exc
    return builder(context or {})


def named_bootstrap_connect(surface: Mapping[str, Any]) -> bool:
    """True when init already chose a project name and only browser approval remains."""
    if str(surface.get("surface") or "") != "project.connect":
        return False
    data = _mapping(surface.get("data"))
    if data.get("autoConnect") is True:
        return True
    name = str(data.get("displayName") or "").strip()
    if not name:
        for field in surface.get("fields") or []:
            if str(field.get("name") or "") == "displayName":
                name = str(field.get("value") or "").strip()
                break
    url = str(data.get("actionUrl") or data.get("connectUrl") or "")
    action = data.get("action")
    if not url and isinstance(action, Mapping):
        url = str(action.get("url") or "")
    return bool(name) and bool(url.strip())


def elicitation_schema(surface: Mapping[str, Any]) -> dict[str, Any]:
    """Build the shallow MCP form schema for a semantic interaction surface."""
    properties: dict[str, Any] = {}
    required: list[str] = []

    for field in surface.get("fields") or []:
        name = str(field.get("name") or "")
        if not name or field.get("readOnly") or is_secret_field(name):
            continue

        kind = str(field.get("kind") or "string")
        field_type = {
            "integer": "integer",
            "number": "number",
            "boolean": "boolean",
            "array": "array",
        }.get(kind, "string")
        field_schema: dict[str, Any] = {
            "type": field_type,
            "title": field.get("label") or name,
        }
        if kind == "array":
            field_schema["items"] = {"type": "string"}
        elif field.get("options"):
            field_schema["enum"] = field["options"]
        if field.get("value") is not None and kind != "object":
            field_schema["default"] = field["value"]
        if kind == "object":
            field_schema["description"] = "JSON object"

        properties[name] = field_schema
        if field.get("required"):
            required.append(name)

    decisions = [
        str(action["id"])
        for action in surface.get("actions") or []
        if action.get("id")
    ]
    if decisions:
        properties["decision"] = {
            "type": "string",
            "title": "Action",
            "enum": decisions,
            "default": decisions[0],
        }
        required.append("decision")

    result: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    return result


def surface_prompt(surface: Mapping[str, Any]) -> str:
    risk = _mapping(surface.get("risk"))
    parts = [
        str(surface.get("title") or "Hydracept action"),
        str(surface.get("description") or ""),
    ]
    if risk.get("irreversibleEffects"):
        parts.append(
            "Irreversible effects: "
            + ", ".join(map(str, risk["irreversibleEffects"]))
        )
    if risk.get("estimatedCostDisplay"):
        parts.append(f"Estimated maximum cost: {risk['estimatedCostDisplay']}.")
    elif risk.get("estimatedCostCents") is not None:
        parts.append(f"Estimated maximum cost: {risk['estimatedCostCents']} cents.")
    if risk.get("dataSensitivity"):
        parts.append(f"Sensitivity: {risk['dataSensitivity']}.")
    if risk.get("requiredAssetApprovals"):
        parts.append(
            "Asset approvals: "
            + ", ".join(map(str, risk["requiredAssetApprovals"]))
        )
    if risk.get("requiredSecretScopes"):
        parts.append(
            "Required authenticated connections: "
            + ", ".join(map(str, risk["requiredSecretScopes"]))
        )
    if surface.get("surface") == "connection.resolve":
        parts.append("Do not enter provider secrets here.")
    return "\n\n".join(part for part in parts if part)


def _next_action(surface: str, decision: str) -> str:
    if decision in {"cancel", "close", "stop_watching"}:
        return "stop"
    return {
        ("project.connect", "connect"): "continue_existing_init_apply",
        ("capability.launch", "run"): "submit_existing_capability_execution",
        ("connection.resolve", "connect"): "open_authenticated_connection_flow",
        ("connection.resolve", "recheck"): "recheck_connection",
        ("authorization.preflight", "authorize"): "continue_existing_execution",
        ("authorization.preflight", "continue"): "continue_existing_execution",
        ("artifact.review", "approve"): "record_artifact_approval",
        ("artifact.review", "reject"): "record_artifact_rejection",
        ("artifact.review", "use"): "present_artifact_to_agent",
        ("artifact.review", "download"): "download_primary_artifact",
        ("artifact.review", "select"): "select_artifact",
        ("change.promote", "promote"): "continue_project_local_promotion",
        ("job.progress", "refresh"): "poll_existing_job",
        ("job.progress", "receipt"): "inspect_receipt",
        ("job.progress", "cancel-job"): "cancel_existing_job",
        ("job.progress", "close"): "stop",
    }.get((surface, decision), "return_to_agent")


def _supports_input_required_form(ctx: Context) -> bool:
    protocol_version = getattr(ctx, "protocol_version", None)
    if not protocol_version or not is_version_at_least(
        protocol_version,
        _INPUT_REQUIRED_PROTOCOL,
    ):
        return False

    capabilities = getattr(ctx, "client_capabilities", None)
    elicitation = getattr(capabilities, "elicitation", None)
    if elicitation is None:
        return False

    # Before elicitation modes existed, a bare elicitation capability meant form support.
    return getattr(elicitation, "form", None) is not None or getattr(
        elicitation,
        "url",
        None,
    ) is None


def _client_advertises_apps(ctx: Context) -> bool:
    from mcp.server.apps import APP_MIME_TYPE, EXTENSION_ID, client_supports_apps

    try:
        return bool(client_supports_apps(ctx))
    except Exception:  # noqa: BLE001 — tests and incomplete host contexts
        capabilities = getattr(ctx, "client_capabilities", None)
        if capabilities is None:
            session = getattr(ctx, "session", None)
            capabilities = getattr(session, "client_capabilities", None) if session is not None else None
        extensions = getattr(capabilities, "extensions", None) or {}
        if not isinstance(extensions, dict):
            return False
        settings = extensions.get(EXTENSION_ID)
        if not isinstance(settings, dict):
            return False
        mime_types = settings.get("mimeTypes")
        return isinstance(mime_types, (list, tuple)) and APP_MIME_TYPE in mime_types


def register_interaction_tools(server: Any, apps: Any | None = None) -> None:
    """Register the presentation layer without adding a second authority path."""
    from hydracept.mcp.interaction_hydration import hydrate_interaction_surface
    from hydracept.mcp.panel import APP_URI

    decorator = apps.tool(resource_uri=APP_URI) if apps is not None else server.tool()

    def _hydrate(surface: str, context: Mapping[str, Any] | None) -> dict[str, Any]:
        project_root = None
        client = None
        try:
            from hydracept.mcp.server import _client, _project_root

            project_root = _project_root()
            client = _client
        except Exception:  # noqa: BLE001
            project_root = None
            client = None
        try:
            return hydrate_interaction_surface(
                surface,
                context,
                project_root=project_root,
                client=client,
            )
        except Exception:  # noqa: BLE001
            return build_interaction_surface(surface, context)

    @decorator
    async def hydracept_interaction_surface(
        ctx: Context,
        surface: SurfaceId,
        context: dict[str, Any] | None = None,
        interactive: bool = True,
    ) -> dict[str, Any] | InputRequiredResult:
        """Present one human-facing Hydracept interaction; never pass secrets in context."""
        contract = _hydrate(surface, context)
        authorization = contract.get("authorization") if isinstance(contract.get("authorization"), dict) else None
        confirmation_required = None
        if isinstance(authorization, dict) and "confirmationRequired" in authorization:
            confirmation_required = bool(authorization["confirmationRequired"])
        apps = _client_advertises_apps(ctx)
        form = _supports_input_required_form(ctx)
        presentation = presentation_for_host(
            surface,
            apps_supported=apps,
            form_supported=form,
            interactive=interactive,
            confirmation_required=confirmation_required,
            context=context,
            authorization=authorization,
        )
        contract = {**contract, "presentation": presentation}

        if apps:
            contract["_meta"] = {
                "presentation": presentation,
                "agentAction": presentation.get("agentAction"),
            }
            return contract

        if (
            not interactive
            or surface == "job.progress"
            or named_bootstrap_connect(contract)
            or not form
        ):
            return contract

        responses = ctx.input_responses or {}
        if "interaction" in responses:
            response = responses["interaction"]
            if not isinstance(response, ElicitResult) or response.action != "accept":
                return {
                    **contract,
                    "resolved": True,
                    "resolution": {"decision": "cancel", "values": {}},
                    "nextAction": "stop",
                }

            values = dict(response.content or {})
            decision = str(values.pop("decision", "continue"))
            allowed = {
                str(action["id"])
                for action in contract["actions"]
                if action.get("id")
            }
            if decision not in allowed:
                allowed_text = ", ".join(sorted(allowed))
                raise ValueError(f"decision must be one of: {allowed_text}")

            return {
                **contract,
                "resolved": True,
                "resolution": {"decision": decision, "values": values},
                "nextAction": _next_action(surface, decision),
            }

        return InputRequiredResult(
            input_requests={
                "interaction": ElicitRequest(
                    params=ElicitRequestFormParams(
                        message=surface_prompt(contract),
                        requested_schema=elicitation_schema(contract),
                    )
                )
            },
            _meta={
                "presentation": presentation,
                "surface": surface,
                "schemaVersion": INTERACTION_SCHEMA_VERSION,
            },
        )
