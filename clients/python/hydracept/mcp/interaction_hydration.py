"""Read-only hydration of thin agent context into hydracept.interaction.v1 builders.

Does not charge, submit, approve, connect credentials, or write the repository.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from hydracept.mcp.interactions import SURFACE_IDS, build_interaction_surface
from hydracept.mcp.panel import INTERACTION_SCHEMA_VERSION, is_tool_failure_payload, surface_for_job
from hydracept.mcp.presentation import attach_presentation, job_presentation

_SURFACES = frozenset(SURFACE_IDS)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(by_alias=True)
        if isinstance(dumped, Mapping):
            return dict(dumped)
    return {}


def _resolve_client(client: Any) -> Any | None:
    if client is None:
        return None
    if callable(client) and not hasattr(client, "describe_capability"):
        try:
            return client()
        except Exception:  # noqa: BLE001
            return None
    return client


def _resolve_root(project_root: Path | str | None) -> Path | None:
    if project_root is None:
        return None
    return Path(project_root)


def _load_binding(project_root: Path | None) -> dict[str, Any]:
    if project_root is None:
        return {}
    from hydracept.cli.project import load_project_binding

    try:
        return dict(load_project_binding(project_root) or {})
    except Exception:  # noqa: BLE001
        return {}


def _suggested_name(project_root: Path | None, binding: Mapping[str, Any]) -> str:
    from hydracept.cli.project import resolve_suggested_project_name

    if project_root is None:
        return str(binding.get("projectName") or binding.get("displayName") or "")
    try:
        return resolve_suggested_project_name(project_root, dict(binding))
    except Exception:  # noqa: BLE001
        return str(binding.get("projectName") or "")


def _dump_job(job: Any) -> dict[str, Any]:
    payload = _mapping(job)
    if payload:
        return payload
    return {}


def _describe(client: Any, capability_key: str) -> dict[str, Any]:
    if client is None or not capability_key:
        return {}
    try:
        return _mapping(client.describe_capability(capability_key))
    except Exception:  # noqa: BLE001
        return {}


def _quote(client: Any, capability_key: str, body: Mapping[str, Any] | None) -> dict[str, Any]:
    if client is None or not capability_key or not hasattr(client, "quote_capability"):
        return {}
    try:
        return _mapping(client.quote_capability(capability_key, dict(body or {})))
    except Exception:  # noqa: BLE001
        return {}


def _get_job(client: Any, job_id: str) -> dict[str, Any]:
    if client is None or not job_id:
        return {}
    try:
        return _dump_job(client.get_job(job_id))
    except Exception:  # noqa: BLE001
        return {}


def _workspace_runnable(descriptor: Mapping[str, Any]) -> dict[str, Any]:
    return _mapping(descriptor.get("workspaceRunnable") or descriptor.get("workspace_runnable"))


def _connections_fallback(project_root: Path | None, binding: Mapping[str, Any]) -> str:
    from hydracept.cli.funding import connections_url

    api = str(binding.get("apiOrigin") or binding.get("apiBaseUrl") or "https://api.hydracept.com")
    project_id = str(binding.get("projectId") or "")
    environment = str(binding.get("environment") or "development")
    try:
        return connections_url(api, project_id, environment)
    except Exception:  # noqa: BLE001
        return ""


def _surface_definition_paths(project_root: Path | None) -> list[str]:
    if project_root is None:
        return []
    folder = Path(project_root) / "tools" / "hydracept" / "surfaces"
    if not folder.is_dir():
        return []
    return [str(path.relative_to(project_root)).replace("\\", "/") for path in sorted(folder.glob("*.json"))]


def _cost_from_quote(quote: Mapping[str, Any]) -> dict[str, Any]:
    pricing = _mapping(quote.get("pricing"))
    charge = _mapping(_mapping(pricing.get("charge")).get("customerCharge"))
    total = _mapping(_mapping(pricing.get("quote")).get("customerTotal")) or _mapping(
        quote.get("expectedCharge")
    )
    display = charge.get("display") or total.get("display") or quote.get("estimatedCostDisplay")
    cents = quote.get("estimatedCostCents")
    micros = charge.get("amountMicros")
    if micros is None:
        micros = total.get("amountMicros")
    if cents is None and micros is not None:
        try:
            cents = int(round(int(micros) / 10_000))
        except (TypeError, ValueError):
            cents = None
    out: dict[str, Any] = {}
    if display:
        out["estimatedCostDisplay"] = str(display)
    if cents is not None:
        out["estimatedCostCents"] = cents
    if quote.get("currency"):
        out["currency"] = quote["currency"]
    return out


def _hydrate_connect(context: dict[str, Any], *, project_root: Path | None) -> dict[str, Any]:
    hydrated = dict(context)
    expected_fp = str(
        hydrated.get("fingerprint")
        or hydrated.get("workspaceFingerprint")
        or _mapping(hydrated.get("workspace")).get("fingerprint")
        or ""
    ).strip()
    if project_root is not None and expected_fp:
        from hydracept.cli.workspace_fingerprint import workspace_fingerprint

        local_fp = workspace_fingerprint(project_root, _load_binding(project_root))
        if local_fp != expected_fp:
            raise ValueError("WORKSPACE_CONTEXT_MISMATCH")
    if project_root is not None:
        hydrated.setdefault("detectedRoot", str(Path(project_root).resolve()))
    return hydrated


def _hydrate_launch(context: dict[str, Any], *, client: Any) -> dict[str, Any]:
    hydrated = dict(context)
    capability = _mapping(hydrated.get("capability"))
    key = str(capability.get("key") or hydrated.get("capabilityKey") or "")
    if key and not capability.get("inputSchema") and not capability.get("input_schema"):
        capability = _describe(client, key) or capability
    if capability:
        hydrated["capability"] = capability
        hydrated.setdefault("capabilityKey", str(capability.get("key") or key))
    return hydrated


def _hydrate_connection(
    context: dict[str, Any],
    *,
    client: Any,
    project_root: Path | None,
) -> dict[str, Any]:
    hydrated = dict(context)
    key = str(hydrated.get("capabilityKey") or _mapping(hydrated.get("capability")).get("key") or "")
    descriptor = _mapping(hydrated.get("capability")) or _describe(client, key)
    runnable = _workspace_runnable(descriptor)
    connect_url = (
        hydrated.get("connectUrl")
        or hydrated.get("actionUrl")
        or runnable.get("connectUrl")
        or runnable.get("actionUrl")
    )
    if not connect_url:
        connect_url = _connections_fallback(project_root, _load_binding(project_root))
    hydrated["connectUrl"] = connect_url
    hydrated["actionUrl"] = connect_url
    hydrated.setdefault("capabilityKey", key)
    hydrated.setdefault("status", runnable.get("status") or ("ready" if runnable.get("runnable") else "missing"))
    if descriptor.get("title"):
        hydrated.setdefault("provider", descriptor.get("title"))
    scopes = hydrated.get("requiredSecretScopes") or runnable.get("requiredScopes") or []
    hydrated["requiredSecretScopes"] = list(scopes)
    return hydrated


def _hydrate_preflight(context: dict[str, Any], *, client: Any) -> dict[str, Any]:
    hydrated = dict(context)
    job_id = str(hydrated.get("jobId") or "")
    if job_id:
        job = _get_job(client, job_id)
        if job:
            hydrated.setdefault("capabilityKey", job.get("capabilityKey"))
            if job.get("approval"):
                hydrated["approval"] = job["approval"]
            hydrated.setdefault("status", job.get("status"))
            return hydrated
    capability = _mapping(hydrated.get("capability"))
    key = str(capability.get("key") or hydrated.get("capabilityKey") or "")
    if key and not capability.get("approvalRequirements"):
        capability = _describe(client, key) or capability
    if capability:
        hydrated["capability"] = capability
        hydrated.setdefault("capabilityKey", str(capability.get("key") or key))
    request = hydrated.get("request") if isinstance(hydrated.get("request"), Mapping) else None
    body = request or hydrated.get("body")
    if isinstance(body, Mapping) and key and "estimatedCostDisplay" not in hydrated:
        quote = _quote(client, key, body if "input" in body else {"input": dict(body)})
        hydrated.update(_cost_from_quote(quote))
        if quote:
            hydrated.setdefault("quote", quote)
    return hydrated


def _hydrate_job_surface(context: dict[str, Any], *, client: Any) -> dict[str, Any]:
    hydrated = dict(context)
    job_id = str(hydrated.get("jobId") or "")
    job = hydrated.get("job") if isinstance(hydrated.get("job"), Mapping) else None
    if job_id and not job:
        job = _get_job(client, job_id)
    if job:
        hydrated.update({k: v for k, v in job.items() if k not in hydrated or hydrated[k] in (None, "", [], {})})
        hydrated.setdefault("jobId", job.get("jobId") or job_id)
        hydrated.setdefault("capabilityKey", job.get("capabilityKey"))
        hydrated.setdefault("status", job.get("status"))
        hydrated.setdefault("artifacts", job.get("artifacts") or [])
        hydrated.setdefault("typedOutput", job.get("typedOutput") or job.get("output"))
        if job.get("variantSet"):
            hydrated.setdefault("variantSet", job["variantSet"])
    return hydrated


def _hydrate_promote(context: dict[str, Any], *, project_root: Path | None) -> dict[str, Any]:
    hydrated = dict(context)
    binding = _load_binding(project_root)
    hydrated.setdefault("projectId", binding.get("projectId") or "")
    paths = list(hydrated.get("surfacePaths") or hydrated.get("paths") or [])
    if not paths:
        paths = _surface_definition_paths(project_root)
    hydrated["surfacePaths"] = paths
    hydrated["promoteEnabled"] = bool(project_root and paths)
    hydrated.setdefault("changes", list(context.get("changes") or []))
    return hydrated


_HYDRATORS = {
    "project.connect": lambda ctx, **kw: _hydrate_connect(ctx, project_root=kw.get("project_root")),
    "capability.launch": lambda ctx, **kw: _hydrate_launch(ctx, client=kw.get("client")),
    "connection.resolve": lambda ctx, **kw: _hydrate_connection(
        ctx, client=kw.get("client"), project_root=kw.get("project_root")
    ),
    "authorization.preflight": lambda ctx, **kw: _hydrate_preflight(ctx, client=kw.get("client")),
    "job.progress": lambda ctx, **kw: _hydrate_job_surface(ctx, client=kw.get("client")),
    "artifact.review": lambda ctx, **kw: _hydrate_job_surface(ctx, client=kw.get("client")),
    "change.promote": lambda ctx, **kw: _hydrate_promote(ctx, project_root=kw.get("project_root")),
}


def hydrate_interaction_surface(
    surface: str,
    context: Mapping[str, Any] | None = None,
    *,
    project_root: Path | str | None = None,
    client: Any = None,
) -> dict[str, Any]:
    """Convert thin agent context into a full hydracept.interaction.v1 contract."""
    if surface not in _SURFACES:
        raise ValueError(f"surface must be one of: {', '.join(SURFACE_IDS)}")
    raw = dict(context or {})
    resolved_client = _resolve_client(client)
    root = _resolve_root(project_root)
    hydrated = _HYDRATORS[surface](raw, project_root=root, client=resolved_client)
    return build_interaction_surface(surface, hydrated)


def attach_hydrated_interaction(
    result: Any,
    surface: str | None = None,
    context: Mapping[str, Any] | None = None,
    *,
    project_root: Path | str | None = None,
    client: Any = None,
) -> Any:
    """Attach a full interaction contract to an App wrapper result."""
    from hydracept.mcp.presentation import presentation_for_host

    if not isinstance(result, dict) or is_tool_failure_payload(result):
        return result
    attached = dict(result)
    if str(attached.get("status") or "") == "interaction_required":
        action = attached.get("action") if isinstance(attached.get("action"), Mapping) else {}
        try:
            contract = hydrate_interaction_surface(
                "project.connect",
                dict(context or {}),
                project_root=project_root,
                client=None,
            )
        except Exception:  # noqa: BLE001
            contract = {
                "schemaVersion": INTERACTION_SCHEMA_VERSION,
                "surface": "project.connect",
            }
        data = dict(contract.get("data") or {})
        data["status"] = "interaction_required"
        data["action"] = dict(action)
        data["actionUrl"] = action.get("url")
        contract["data"] = data
        presentation = attached.get("presentation")
        if not isinstance(presentation, Mapping):
            presentation = presentation_for_host(
                "project.connect",
                apps_supported=True,
                confirmation_required=True,
                status="mount_requested",
                context={"actionUrl": action.get("url")},
            )
        contract["presentation"] = dict(presentation)
        attached["interaction"] = contract
        attached["surface"] = "project.connect"
        return attach_presentation(attached, presentation)

    existing = attached.get("interaction")
    if isinstance(existing, Mapping) and existing.get("schemaVersion") == INTERACTION_SCHEMA_VERSION:
        if existing.get("title") or existing.get("actions"):
            implied = surface_for_job(attached)
            existing_surface = str(existing.get("surface") or "")
            if not (existing_surface == "job.progress" and implied == "artifact.review"):
                attached["surface"] = existing.get("surface") or attached.get("surface")
                if not attached.get("presentation"):
                    attached = attach_presentation(attached, job_presentation(attached))
                return attached
    resolved_surface = surface
    if not resolved_surface:
        implied = surface_for_job(attached)
        existing_surface = existing.get("surface") if isinstance(existing, Mapping) else None
        if existing_surface == "job.progress" and implied == "artifact.review":
            resolved_surface = implied
        else:
            resolved_surface = existing_surface or implied
    ctx = dict(context or {})
    ctx.setdefault("jobId", attached.get("jobId"))
    ctx.setdefault("capabilityKey", attached.get("capabilityKey"))
    if attached.get("artifacts"):
        ctx.setdefault("artifacts", attached["artifacts"])
    try:
        contract = hydrate_interaction_surface(
            str(resolved_surface),
            ctx,
            project_root=project_root,
            client=client,
        )
    except Exception:  # noqa: BLE001
        contract = {
            "schemaVersion": INTERACTION_SCHEMA_VERSION,
            "surface": resolved_surface,
        }
    presentation = attached.get("presentation")
    if not isinstance(presentation, Mapping):
        presentation = job_presentation(attached)
    contract = dict(contract)
    contract["presentation"] = dict(presentation)
    attached["interaction"] = contract
    attached["surface"] = contract.get("surface") or resolved_surface
    return attach_presentation(attached, presentation)

