"""Canonical MCP tool descriptions and JSON Schema parameter documentation.

Applied at server assembly via ``enrich_tool_list_metadata`` so hosted ``tools/list``
and stdio ``tools/list`` match this authority. Keep ``clients/python/hydracept/mcp/tool_parameter_docs.py``
in sync (public wheel copy).
"""

from __future__ import annotations

from typing import Any

from hydracept.mcp.tool_profiles import (
    COMPACT_DEFAULT_TOOL_NAMES,
    MCP_TOOL_PROFILE_COMPACT,
    MCP_TOOL_PROFILE_FULL,
)

# ---------------------------------------------------------------------------
# Compact profile (hosted POST /mcp and stdio default)
# ---------------------------------------------------------------------------

TOOL_DESCRIPTIONS: dict[str, str] = {
    "hydracept_resolve_capability": (
        "Match the user's goal to a capability key using natural language. "
        "Use when the key is unknown; use hydracept_capabilities when you already have a key or need the catalog. "
        "Keyless. No charge. Read-only."
    ),
    "hydracept_capabilities": (
        "Browse or fetch capability descriptors (keys, modes, schemas). "
        "Use hydracept_resolve_capability when routing from intent alone. "
        "List/resolve is keyless; a bearer key may add project-scoped fields. No charge. Read-only."
    ),
    "hydracept_quote_capability": (
        "Preview what a run would cost — does not execute, create a job, or charge the wallet. "
        "Use before spending when the user asks about price; use hydracept_run or hydracept_submit_job only to execute. "
        "Not the same as hydracept_request_capability_quote on the full profile (human-paid capability commission). "
        "Requires bearer API key. No charge for the quote itself."
    ),
    "hydracept_run": (
        "Run a capability (paid). Use when the user wants execution — not for quotes (hydracept_quote_capability), "
        "status (hydracept_job_status), or receipts (hydracept_get_receipt). "
        "Default wait=true waits until the job finishes; use hydracept_submit_job when this call must return immediately. "
        "Picks invoke vs durable job from the capability descriptor. "
        "Requires bearer key. Settles at actual provider cost plus any managed service fee; no per-call minimum. "
        "May create jobs, artifacts, and provider usage."
    ),
    "hydracept_submit_job": (
        "Start a capability job and return its id immediately (paid). "
        "Use when execution is required but this MCP call must not block — not for quotes or status checks. "
        "Prefer hydracept_run when waiting is acceptable. Poll with hydracept_job_status. "
        "Same billing as hydracept_run. Requires bearer key."
    ),
    "hydracept_job_status": (
        "Read one job's current status. "
        "Use after hydracept_submit_job or hydracept_run with wait=false; use hydracept_get_receipt after success. "
        "If the job id is unknown, use hydracept_jobs_find first. "
        "Requires bearer key. No charge."
    ),
    "hydracept_jobs_find": (
        "Find a prior job in the bound project when you do not have its id. "
        "intent is recent, failed, or reusable. The list never includes prompt text. "
        "Use after context loss, for failure triage, or to recover a job to cancel. "
        "Requires bearer key. No charge. Read-only."
    ),
    "hydracept_cancel_job": (
        "Request cancellation of one job. Use only when the user explicitly asks to cancel the job itself; "
        "stopping a local polling loop is not a cancellation. "
        "Returns whether the request was accepted, whether the job is already terminal, and the next action. "
        "Never promise that upstream provider work stopped or that already-incurred cost is refunded. "
        "Safe to retry: a terminal job reports its terminal state. Requires bearer key."
    ),
    "hydracept_get_receipt": (
        "Read billing and provenance for a finished job. Does not run capabilities or spend money. "
        "Use after terminal success; use hydracept_job_status while still running. "
        "Hosted MCP accepts job_id only. Requires bearer key. No charge."
    ),
    "hydracept_download_artifact": (
        "Fetch artifact metadata (and SHA-256 on hosted MCP) for a succeeded job output. "
        "Stdio may also write bytes when output_path is set. Requires bearer key. No charge on hosted."
    ),
    "hydracept_workspace_status": (
        "Check workspace/session authentication and readiness, plus common setup errors. "
        "Use when setup, auth, or project binding is in doubt; use hydracept_job_status for a specific execution. "
        "Does not execute capabilities or spend money. "
        "Hosted requires bearer (WORKSPACE_KEY_REQUIRED when missing); stdio checks local project binding. "
        "Not a substitute for hydracept_capabilities."
    ),
}

PARAMETER_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "hydracept_resolve_capability": {
        "intent": (
            "Required string: user goal in natural language (passed verbatim to the resolver)."
        ),
        "requirements": (
            "Optional object matching CapabilityResolutionRequest.requirements (e.g. modality tags). "
            "Default {}. runnableNow requires an authenticated project workspace on the API."
        ),
    },
    "hydracept_capabilities": {
        "key": (
            "Optional capability key for GET /v1/capabilities/{key}. When set, query is ignored."
        ),
        "query": (
            "Optional search string when key is empty. Hosted: always POST /v1/capabilities/resolve "
            "(keyless). Stdio: resolve when authenticated, else list filtering."
        ),
    },
    "hydracept_quote_capability": {
        "capability_key": "Required capability registry key unless only legacy aliases are passed.",
        "capability": "Legacy alias of capability_key (stdio).",
        "capabilityKey": "Legacy alias of capability_key (stdio).",
        "body": "Invocation payload object validated against the capability schema.",
        "input": "Alias for body; do not pass both.",
    },
    "hydracept_run": {
        "capability_key": "Required capability registry key for POST .../jobs.",
        "capability": "Legacy alias of capability_key (stdio).",
        "capabilityKey": "Legacy alias of capability_key (stdio).",
        "body": "Required capability input object (schema fields). Merged with session project context when bound.",
        "input": "Alias for body; do not pass both.",
        "out": "Stdio only: filesystem path to persist a primary artifact locally.",
        "wait": (
            "Boolean, default true. When true, poll until succeeded/failed/canceled or timeout. "
            "When false, return job id and poll with hydracept_job_status."
        ),
        "timeout": (
            "Seconds to poll when wait=true; omit to poll until terminal with no tool-side limit "
            "(the MCP client request timeout may end the call first). On timeout, status may stay "
            "running — call hydracept_job_status."
        ),
        "max_cost": (
            "Optional number (USD): sets execution.executionConstraints.maxCostUsd before submit."
        ),
        "idempotency_key": (
            "Optional string; server generates run-{uuid} when empty. Reuse for safe retries."
        ),
    },
    "hydracept_submit_job": {
        "capability_key": "Required capability registry key.",
        "capability": "Legacy alias of capability_key (stdio).",
        "capabilityKey": "Legacy alias of capability_key (stdio).",
        "body": "Capability input object; merged with session project context when bound.",
        "input": "Alias for body.",
        "idempotency_key": "Optional string; server generates job-{uuid} when empty.",
    },
    "hydracept_job_status": {
        "job_id": "Required job id from hydracept_run or hydracept_submit_job.",
        "jobId": "CamelCase alias of job_id (stdio).",
    },
    "hydracept_jobs_find": {
        "intent": "Optional search scope: recent (default), failed, or reusable.",
        "capability_key": "Optional capability key to narrow the search.",
        "limit": "Optional maximum number of matching jobs (1-100, default 10).",
        "project_id": "Hosted only: bound project id; omit to use the session-bound project.",
    },
    "hydracept_cancel_job": {
        "job_id": "Required job id to cancel. Use hydracept_jobs_find if the id is unknown.",
        "jobId": "CamelCase alias of job_id (stdio).",
    },
    "hydracept_get_receipt": {
        "job_id": (
            "Job or execution id for GET /v1/jobs/{jobId}/receipt. Required on hosted MCP."
        ),
        "receipt_id": (
            "Stdio: receipt id from a prior result when job_id is omitted. Ignored on hosted MCP."
        ),
        "jobId": "CamelCase alias of job_id (stdio).",
        "receiptId": "CamelCase alias of receipt_id (stdio).",
    },
    "hydracept_download_artifact": {
        "job_id": "Required owning job id (scopes the artifact download URL).",
        "artifact_id": "Required artifact id from job artifacts or run result.",
        "output_path": "Stdio: workspace-relative path to write bytes; ignored on hosted MCP.",
        "out": "Stdio alias for output_path.",
        "outputPath": "CamelCase alias of output_path (stdio).",
        "label": "Stdio: optional artifact label when multiple artifacts exist.",
    },
    "hydracept_workspace_status": {
        "refresh": (
            "Stdio: when true, also verify session over the network. Ignored on hosted MCP."
        ),
    },
}

# Phase B: full-profile extensions (import merges below)
from hydracept.mcp.tool_documentation_full import (  # noqa: E402
    FULL_PROFILE_PARAMETER_DESCRIPTIONS,
    FULL_PROFILE_TOOL_DESCRIPTIONS,
)

TOOL_DESCRIPTIONS.update(FULL_PROFILE_TOOL_DESCRIPTIONS)
PARAMETER_DESCRIPTIONS.update(FULL_PROFILE_PARAMETER_DESCRIPTIONS)

COMPACT_TOOL_DESCRIPTIONS_BEFORE_PHASE_B: dict[str, str] = {
    "hydracept_resolve_capability": (
        "Semantic router for capability choice. Pass the user's words as intent; "
        "do not ask for a capability key. Read-only and does not spend money. "
        "Use before hydracept_run when the key is unknown."
    ),
    "hydracept_capabilities": (
        "List, search, or describe capabilities (pass key for one descriptor, query for search). "
        "Read-only discovery; use hydracept_resolve_capability when the user intent is natural language."
    ),
    "hydracept_quote_capability": (
        "Price preview for a capability invocation (POST /v1/capabilities/{key}/quote). "
        "Does not reserve funds or execute. Optional before hydracept_run when cost visibility matters."
    ),
    "hydracept_run": (
        "Default execution path: run a capability and wait for terminal completion (hydracept.run-result.v1). "
        "Use hydracept_submit_job when the agent must return immediately and poll with hydracept_job_status. "
        "Use hydracept_invoke only for synchronous read-only specialist calls when run is unsuitable."
    ),
    "hydracept_submit_job": (
        "Submit a durable capability job and return immediately without waiting. "
        "Prefer hydracept_run when the agent can block until completion. "
        "After submit, poll with hydracept_job_status when nextAction is poll."
    ),
    "hydracept_job_status": (
        "Read job state once (GET /v1/jobs/{jobId}). "
        "Use when hydracept_run or hydracept_submit_job returned nextAction poll; "
        "use hydracept_get_receipt after terminal success for the sealed record."
    ),
    "hydracept_get_receipt": (
        "Fetch the sealed execution receipt by jobId/executionId or receiptId from a prior result. "
        "Read-only; use after terminal success when you need provenance or billing detail beyond the run envelope."
    ),
    "hydracept_download_artifact": (
        "Download or resolve artifact bytes/metadata for a job artifact id. "
        "Use after success when hydracept_run did not persist a local file (stdio saves under workspace)."
    ),
    "hydracept_workspace_status": (
        "Session and workspace readiness diagnostics for the authenticated principal. "
        "Read-only; call when credentials, project binding, or MCP setup may be wrong."
    ),
}


def _tool_input_schema(tool: Any) -> dict[str, Any] | None:
    for attr in ("parameters", "input_schema", "inputSchema"):
        schema = getattr(tool, attr, None)
        if isinstance(schema, dict):
            return schema
    return None


def enrich_tool_list_metadata(tools: list[Any]) -> None:
    """Apply canonical descriptions to listed MCP tools in place."""
    from hydracept.mcp.tool_surface_names import MCP_FULL_LIST_TO_CANONICAL

    for tool in tools:
        name = str(getattr(tool, "name", "") or "")
        if not name:
            continue
        doc_key = MCP_FULL_LIST_TO_CANONICAL.get(name, name)
        description = TOOL_DESCRIPTIONS.get(doc_key)
        if description:
            tool.description = description
        param_docs = PARAMETER_DESCRIPTIONS.get(doc_key)
        if not param_docs:
            continue
        schema = _tool_input_schema(tool)
        if not isinstance(schema, dict):
            continue
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            continue
        for param_name, param_desc in param_docs.items():
            prop = properties.get(param_name)
            if isinstance(prop, dict) and param_desc:
                prop["description"] = param_desc


def _assert_tool_documented(
    tool: Any,
    *,
    profile: str | None = None,
    listed_on_surface: set[str] | None = None,
    surface: str = "hosted",
) -> None:
    from hydracept.mcp.tool_profile_copy import expected_tool_description
    from hydracept.mcp.tool_surface_names import MCP_FULL_LIST_TO_CANONICAL

    name = str(getattr(tool, "name", "") or "")
    doc_key = MCP_FULL_LIST_TO_CANONICAL.get(name, name)
    if doc_key not in TOOL_DESCRIPTIONS:
        raise AssertionError(f"{name}: missing TOOL_DESCRIPTIONS entry (doc_key={doc_key})")
    if not str(getattr(tool, "description", "") or "").strip():
        raise AssertionError(f"{name}: empty tool description after enrich")
    if profile is not None and listed_on_surface is not None:
        expected = expected_tool_description(
            doc_key, profile=profile, listed_on_surface=listed_on_surface, surface=surface
        )
    else:
        expected = TOOL_DESCRIPTIONS[doc_key]
    if tool.description != expected:
        raise AssertionError(f"{name}: description drift from TOOL_DESCRIPTIONS")
    schema = _tool_input_schema(tool)
    if not isinstance(schema, dict):
        raise AssertionError(f"{name}: missing input schema")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise AssertionError(f"{name}: schema.properties missing")
    param_docs = PARAMETER_DESCRIPTIONS.get(doc_key, {})
    for param_name, prop in properties.items():
        if not isinstance(prop, dict):
            continue
        if param_name not in param_docs:
            raise AssertionError(f"{name}.{param_name}: missing PARAMETER_DESCRIPTIONS entry")
        if not str(prop.get("description") or "").strip():
            raise AssertionError(f"{name}.{param_name}: empty description after enrich")


def assert_tools_documented_for_names(
    tools: list[Any],
    expected_names: tuple[str, ...],
    *,
    profile: str | None = None,
    surface: str = "hosted",
) -> None:
    by_name = {str(getattr(t, "name", "") or ""): t for t in tools}
    missing = [n for n in expected_names if n not in by_name]
    if missing:
        raise AssertionError(f"tools not registered: {missing}")
    listed = set(by_name.keys())
    for name in expected_names:
        _assert_tool_documented(
            by_name[name],
            profile=profile,
            listed_on_surface=listed if profile is not None else None,
            surface=surface,
        )


def assert_compact_tool_documentation(
    tools: list[Any], *, profile: str | None = None, surface: str = "hosted"
) -> None:
    assert_tools_documented_for_names(
        tools,
        COMPACT_DEFAULT_TOOL_NAMES,
        profile=profile or MCP_TOOL_PROFILE_COMPACT,
        surface=surface,
    )


def assert_full_profile_tool_documentation(
    tools: list[Any], *, profile: str | None = None, surface: str = "hosted"
) -> None:
    """All listed tools must be documented (hosted full or stdio full surfaces)."""
    from hydracept.mcp.tool_profiles import MCP_TOOL_PROFILE_FULL

    names = tuple(sorted({str(getattr(t, "name", "") or "") for t in tools if getattr(t, "name", None)}))
    assert_tools_documented_for_names(
        tools, names, profile=profile or MCP_TOOL_PROFILE_FULL, surface=surface
    )


def tool_views_from_mcp_list(tools: list[dict[str, Any]]) -> list[Any]:
    """Adapt JSON tools/list entries for documentation asserts."""
    from types import SimpleNamespace

    views: list[Any] = []
    for item in tools:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        schema = item.get("inputSchema") if isinstance(item.get("inputSchema"), dict) else {}
        views.append(
            SimpleNamespace(
                name=name,
                description=str(item.get("description") or ""),
                inputSchema=schema,
            )
        )
    return views
