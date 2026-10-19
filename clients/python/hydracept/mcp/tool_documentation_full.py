"""Public-client copy of hydracept_contracts.mcp_tool_documentation_full.

Keep in sync with packages/contracts. The published wheel cannot import hydracept_contracts.
"""

from __future__ import annotations

from hydracept.history import JOB_INSPECT_DESCRIPTION

FULL_PROFILE_TOOL_DESCRIPTIONS: dict[str, str] = {
    "hydracept_invoke": (
        "POST /v1/capabilities/{key}/invoke: synchronous capability call (no job poll loop). "
        "Use only when the capability descriptor lists invoke_sync; use hydracept_run for job-based "
        "execution and hydracept_pinned_run for exact model pins. "
        "Auth: bearer required. Cost: billed like invoke admission. Side effects: may create invoke audit records."
    ),
    "hydracept_request_capability_quote": (
        "POST /v1/capability-requests then submit: human-paid commission quote for a missing capability. "
        "Not retail execution pricing (see hydracept_quote_capability). quoteId from this flow must not "
        "be used as execution.quoteId on jobs. "
        "Auth: bearer required. Cost: none to the agent (humans pay commission). Side effects: creates request rows."
    ),
    "hydracept_get_capability_request_quote": (
        "GET /v1/capability-requests/{id}/quote: read commission quote for an existing request. "
        "Use after hydracept_request_capability_quote; not for retail hydracept_quote_capability. "
        "Auth: bearer required. Cost: none. Side effects: none."
    ),
    "hydracept_job_inspect": JOB_INSPECT_DESCRIPTION
    + " Auth: bearer required. Cost: none. Side effects: none.",
    "hydracept_pinned_run": (
        "POST /v1/inference/pinned: one exact provider/model pin with scientific receipt. "
        "Use for pinned inference experiments; use hydracept_run for registry capability keys. "
        "Optional processing=deferred for 50% Flex pricing when supported; no Flex→Standard fallback; "
        "capacity 429s may retry inside the admission deadline. "
        "Auth: bearer required. Cost: paid — hold at worst-case then settle at actual cost. "
        "Side effects: creates pinned receipt."
    ),
    "hydracept_pinned_get": (
        "GET /v1/inference/pinned/{receipt_id}: fetch pinned run receipt. "
        "Use after hydracept_pinned_run; use hydracept_get_receipt for capability jobs. "
        "Auth: bearer required. Cost: none. Side effects: none."
    ),
    "hydracept_pinned_bulk": (
        "POST /v1/inference/pinned/bulk: concurrent pinned items (one execution each). "
        "Use for batch pins; use hydracept_pinned_run for a single pin. "
        "Auth: bearer required. Cost: billed per item. Side effects: creates bulk run state."
    ),
    "hydracept_pinned_bulk_get": (
        "GET /v1/inference/pinned/bulk/{bulk_id}: poll bulk pinned run aggregate. "
        "Use when hydracept_pinned_bulk returns nextAction poll. "
        "Auth: bearer required. Cost: none. Side effects: none."
    ),
    "hydracept_manifest_create": (
        "POST /v1/provenance/manifests: hash pinned inference receipts into a manifest id. "
        "Use after hydracept_pinned_run; capability job receipts are not accepted. "
        "Verify with hydracept_manifest_verify. "
        "Auth: bearer required. Cost: none. Side effects: creates manifest record."
    ),
    "hydracept_manifest_verify": (
        "POST /v1/provenance/manifests/{manifest_id}/verify: check manifest members. "
        "Read-only verification. Use after hydracept_manifest_create. "
        "Auth: bearer required. Cost: none. Side effects: none."
    ),
    "hydracept_lockfile_emit": (
        "GET /v1/provenance/lockfile?receipt_id=: emit lockfile JSON for a pinned inference receipt. "
        "Use after hydracept_pinned_run / hydracept_pinned_get; verify with hydracept_verify_lockfile. "
        "Auth: bearer required. Cost: none. Side effects: none."
    ),
    "hydracept_verify_lockfile": (
        "POST /v1/provenance/lockfile/verify: validate lockfile document. "
        "Use after hydracept_lockfile_emit or for CI replay. "
        "Auth: bearer required. Cost: none. Side effects: none."
    ),
    "hydracept_smoke": (
        "Runs one REAL paid image.generate.v1 job (trial credit if eligible, otherwise wallet-billed like "
        "hydracept_run) — not a dry run or quote. Use only when the user explicitly wants a managed-trial smoke "
        "execution; never for price checks (hydracept_quote_capability) or catalog questions. "
        "Auth: bearer required. Cost: paid image generation. Side effects: creates job/receipt and provider usage."
    ),
    "hydracept_project_request_operation": (
        "POST /v1/projects/{projectId}/operations: enqueue allowlisted project operation for local execution. "
        "Hosted MCP does not run argv; stdio watch_once/up executes. "
        "Auth: bearer required. Side effects: creates operation record."
    ),
    "hydracept_project_get_operation": (
        "GET /v1/projects/{projectId}/operations/{id}: poll operation status. "
        "Use after hydracept_project_request_operation. "
        "Auth: bearer required. Cost: none. Side effects: none."
    ),
    "hydracept_model_adapters": (
        "GET adapter catalog: registered LoRAs, aliases, defaults, routing readiness for the bound project. "
        "Use before hydracept_use_lora or adapter mutation tools. "
        "Auth: bearer required. Cost: none. Side effects: none."
    ),
    "hydracept_register_model_adapter": (
        "POST /v1/model-adapters: register LoRA source for the project. "
        "Auth: bearer required. Cost: none. Side effects: mutates project adapter registry."
    ),
    "hydracept_revalidate_model_adapter": (
        "POST revalidate adapter source metadata. Auth: bearer required. Side effects: updates adapter record."
    ),
    "hydracept_create_adapter_alias": (
        "POST /v1/adapter-aliases: create semantic alias pointing at adapter/weight. "
        "Auth: bearer required. Side effects: mutates alias map."
    ),
    "hydracept_promote_adapter_alias": (
        "POST /v1/adapter-aliases/{alias}/promotions: new immutable alias version. "
        "Auth: bearer required. Side effects: mutates alias history."
    ),
    "hydracept_bind_adapter_alias": (
        "POST recipe binding for alias version. Auth: bearer required. Side effects: persists binding."
    ),
    "hydracept_set_adapter_default": (
        "POST project default alias for image.generate.v1 route. Auth: bearer required. Side effects: mutates default."
    ),
    "hydracept_clear_adapter_default": (
        "DELETE/clear project adapter default override. Auth: bearer required. Side effects: mutates default."
    ),
    "hydracept_prepare_adapter_selection": (
        "Build generation patch from selected adapters list. Read-only composition helper. "
        "Auth: bearer required. Cost: none. Side effects: none."
    ),
    "hydracept_preview_lora_source": (
        "Preview Hugging Face or registry LoRA source before register. "
        "Auth: bearer required. Cost: none. Side effects: none."
    ),
    "hydracept_suggest_lora": (
        "Suggest project alias or registered LoRA from query string. "
        "Auth: bearer required. Cost: none. Side effects: none."
    ),
    "hydracept_use_lora": (
        "Resolve query to adapter selection for image.generate.v1. "
        "Auth: bearer required. Cost: none. Side effects: none (selection only)."
    ),
    # Stdio-only
    "hydracept_interaction_surface": (
        "Present Hydracept App UI resource (stdio). Use when init/onboarding returns present_and_yield. "
        "Auth: workspace session. Side effects: UI presentation only."
    ),
    "hydracept_project_status": (
        "Read login-persistent project up status from local checkout (stdio, cwd=project). Side effects: none."
    ),
    "hydracept_project_sync": (
        "Sync operations allowlist from tools/hydracept/manifest.json (stdio). Side effects: rewrites allowlist file."
    ),
    "hydracept_project_up_install": (
        "Run project up --install locally (stdio). Side effects: local install argv."
    ),
    "hydracept_project_watch_once": (
        "Execute pending project operations once (stdio). Side effects: local argv execution."
    ),
    "hydracept_surface_apply": (
        "Apply surface JSON to project checkout (stdio). Does not grant allowlist by itself."
    ),
    "hydracept_ui_approve_job": (
        "Panel POST /v1/jobs/{id}/approve (stdio App). Same API as human approval gate."
    ),
    "hydracept_ui_artifact_preview": (
        "Panel bounded artifact preview (stdio App). Read-only media preview."
    ),
    "hydracept_ui_cancel_job": (
        "Panel POST /v1/jobs/{id}/cancel. Side effects: cancels job when policy allows."
    ),
    "hydracept_ui_connect_project": (
        "Panel init/connect flow (stdio App). Does not replace python -m hydracept init binding writes."
    ),
    "hydracept_ui_connection_recheck": (
        "Panel read-only connection/runnability recheck. No secret arguments."
    ),
    "hydracept_ui_download_artifact": (
        "Panel save artifact into workspace (stdio App)."
    ),
    "hydracept_ui_poll_job": (
        "Panel poll job once; same API projection as hydracept_job_status."
    ),
    "hydracept_ui_promote": (
        "Panel apply_surfaces(path) locally; cloud never writes git checkout."
    ),
    "hydracept_ui_quote": (
        "Panel quote adapter; same primitive as hydracept_quote_capability."
    ),
    "hydracept_ui_reject_job": (
        "Panel POST /v1/jobs/{id}/reject."
    ),
    "hydracept_ui_run": (
        "Panel run adapter choosing invoke vs jobs from descriptor executionModes."
    ),
    "hydracept_ui_select_variant": (
        "Panel POST /v1/jobs/{id}/variants/select."
    ),
    "hydracept_ui_submit_job": (
        "Panel submit job; same execution as hydracept_submit_job."
    ),
    "hydracept_billing_status": (
        "GET /v1/billing/managed: Managed continuation status (trial, Managed, BYOK). "
        "Auth: bearer required. Cost: none. Side effects: none."
    ),
    "hydracept_billing_setup_managed": (
        "POST /v1/billing/managed/setup-session: Stripe-hosted Managed setup URL. "
        "Auth: bearer required. Cost: none. Side effects: creates setup session."
    ),
    "hydracept_billing_update_managed": (
        "PATCH /v1/billing/managed: enable/disable Managed or change monthly limit. "
        "Limit increases require confirm_limit_usd. Auth: bearer required. Side effects: billing state."
    ),
}

_SESSION_SCOPE = (
    "Optional; when omitted inherits projectId/environment from authenticated MCP session."
)

FULL_PROFILE_PARAMETER_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "hydracept_invoke": {
        "capability_key": "Required capability key with invoke_sync in descriptor.",
        "capability": "Legacy alias of capability_key (stdio).",
        "capabilityKey": "Legacy alias of capability_key (stdio).",
        "body": "Invoke payload object.",
        "input": "Alias for body.",
    },
    "hydracept_request_capability_quote": {
        "body": "Capability request create payload (capabilityKey, intent, etc.).",
    },
    "hydracept_get_capability_request_quote": {
        "request_id": "Capability request uuid from request_capability_quote (full surfaces only; not on /mcp/compact).",
    },
    "hydracept_job_inspect": {"job_id": "Required job id from prior run or hydracept_jobs_find."},
    "hydracept_pinned_run": {
        "body": "Pinned inference request body (model pin, input, processing mode). Merged with session context.",
    },
    "hydracept_pinned_get": {"receipt_id": "Pinned receipt id from hydracept_pinned_run."},
    "hydracept_pinned_bulk": {"body": "Bulk pinned request envelope (items array)."},
    "hydracept_pinned_bulk_get": {"bulk_id": "Bulk id from hydracept_pinned_bulk response."},
    "hydracept_manifest_create": {
        "body": (
            "Object with receiptIds (required array of pinned receipt ids), optional label, pin, experimentHash."
        ),
    },
    "hydracept_manifest_verify": {"manifest_id": "Manifest id from hydracept_manifest_create."},
    "hydracept_lockfile_emit": {
        "receipt_id": "Pinned receipt id from hydracept_pinned_run or hydracept_pinned_get."
    },
    "hydracept_verify_lockfile": {"body": "Lockfile JSON object to verify."},
    "hydracept_smoke": {
        "capability": "Capability key for smoke (often image.generate.v1).",
        "capability_key": "Alias of capability (stdio).",
        "capabilityKey": "Legacy alias of capability (stdio).",
        "prompt": "Text prompt input for smoke invocation.",
        "poll_seconds": "Optional max seconds to poll job completion.",
        "output_path": "Stdio: optional local path to persist artifact bytes.",
    },
    "hydracept_project_request_operation": {
        "command": "Operation command string from project manifest allowlist.",
        "action_key": "Allowlisted action key.",
        "project_id": "Target project id;" + _SESSION_SCOPE,
        "input": "Operation input object.",
        "context": "Optional operation context object.",
    },
    "hydracept_project_get_operation": {
        "operation_id": "Operation id from hydracept_project_request_operation.",
        "project_id": "Project id;" + _SESSION_SCOPE,
    },
    "hydracept_model_adapters": {
        "project_id": _SESSION_SCOPE,
        "environment": "Environment name;" + _SESSION_SCOPE,
    },
    "hydracept_register_model_adapter": {
        "display_name": "Human-readable adapter label.",
        "source_kind": "Source enum (e.g. huggingface, upload).",
        "source_ref": "Source URI or repo id.",
        "base_model_family": "Base model family key for routing.",
        "source_revision": "Optional revision/sha.",
        "source_file_path": "Optional local file path (stdio).",
        "source_provider": "Optional provider id.",
        "recommended_weight": "Optional default LoRA weight (number).",
        "trigger_words": "Optional trigger word list.",
        "project_id": _SESSION_SCOPE,
        "environment": _SESSION_SCOPE,
    },
    "hydracept_revalidate_model_adapter": {"adapter_id": "Registered adapter id."},
    "hydracept_create_adapter_alias": {
        "alias": "Semantic alias string.",
        "adapter_id": "Target registered adapter id.",
        "weight": "LoRA weight number.",
        "project_id": _SESSION_SCOPE,
        "environment": _SESSION_SCOPE,
    },
    "hydracept_promote_adapter_alias": {
        "alias": "Existing alias name.",
        "adapter_id": "New adapter id target.",
        "weight": "New weight.",
        "project_id": _SESSION_SCOPE,
        "environment": _SESSION_SCOPE,
    },
    "hydracept_bind_adapter_alias": {
        "alias": "Alias to bind.",
        "version_id": "Optional specific alias version id.",
        "project_id": _SESSION_SCOPE,
        "environment": _SESSION_SCOPE,
    },
    "hydracept_set_adapter_default": {
        "alias": "Route-compatible alias to preselect.",
        "capability_key": "Capability route (e.g. image.generate.v1).",
        "project_id": _SESSION_SCOPE,
        "environment": _SESSION_SCOPE,
    },
    "hydracept_clear_adapter_default": {
        "capability_key": "Capability route to clear default for.",
        "project_id": _SESSION_SCOPE,
        "environment": _SESSION_SCOPE,
    },
    "hydracept_prepare_adapter_selection": {
        "adapters": "Array of adapter selection objects for generation patch.",
    },
    "hydracept_preview_lora_source": {
        "query": "HF repo id or URL to preview.",
        "project_id": _SESSION_SCOPE,
        "environment": _SESSION_SCOPE,
    },
    "hydracept_suggest_lora": {
        "query": "Alias, name, or search string.",
        "project_id": _SESSION_SCOPE,
        "environment": _SESSION_SCOPE,
    },
    "hydracept_use_lora": {
        "query": "Alias, adapter id, or HF link.",
        "file_path": "Optional local file path hint (stdio).",
        "base_model_family": "Optional base model family override.",
        "refresh": "Boolean: force metadata refresh.",
        "project_id": _SESSION_SCOPE,
        "environment": _SESSION_SCOPE,
    },
    "hydracept_interaction_surface": {
        "surface": "Surface id or JSON descriptor for App presentation (stdio).",
        "context": "Optional context object passed to the App iframe.",
        "interactive": "Boolean: allow user interaction in the surface.",
    },
    "hydracept_project_status": {},
    "hydracept_project_sync": {},
    "hydracept_project_up_install": {},
    "hydracept_project_watch_once": {},
    "hydracept_surface_apply": {"path": "Relative surface file or directory under project."},
    "hydracept_ui_approve_job": {
        "job_id": "Job awaiting approval.",
        "body": "Optional approval payload object for the panel API.",
    },
    "hydracept_ui_artifact_preview": {
        "job_id": "Owning job id (snake_case).",
        "jobId": "CamelCase alias of job_id.",
        "artifact_id": "Artifact to preview (snake_case).",
        "artifactId": "CamelCase alias of artifact_id.",
    },
    "hydracept_ui_cancel_job": {"job_id": "Job id to cancel."},
    "hydracept_ui_connect_project": {
        "displayName": "Human-readable project label for the connect flow.",
        "environment": "Target environment name.",
        "project_name": "Project slug or name to bind.",
    },
    "hydracept_ui_connection_recheck": {
        "capability_key": "Optional capability key to test runnability for.",
    },
    "hydracept_ui_download_artifact": {
        "job_id": "Job id (snake_case).",
        "jobId": "CamelCase alias of job_id.",
        "artifact_id": "Artifact id (snake_case).",
        "artifactId": "CamelCase alias of artifact_id.",
        "output_path": "Workspace path to write artifact bytes.",
    },
    "hydracept_ui_poll_job": {"job_id": "Job id to poll once."},
    "hydracept_ui_promote": {"path": "Project-relative surfaces path."},
    "hydracept_ui_quote": {"capability_key": "Capability key.", "body": "Quote body object."},
    "hydracept_ui_reject_job": {"job_id": "Job id to reject."},
    "hydracept_ui_run": {
        "capability_key": "Capability key.",
        "body": "Run body.",
        "max_cost": "Optional admission ceiling in USD.",
        "idempotency_key": "Optional idempotency key for the job.",
    },
    "hydracept_ui_select_variant": {
        "job_id": "Job id with pending variants.",
        "artifact_id": "Selected variant artifact id.",
    },
    "hydracept_ui_submit_job": {
        "capability_key": "Capability key.",
        "body": "Submit body.",
        "idempotency_key": "Optional idempotency key.",
    },
}
