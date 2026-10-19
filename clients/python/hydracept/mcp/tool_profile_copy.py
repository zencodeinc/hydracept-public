"""Profile-aware MCP server instructions and tool-description cross-references."""

from __future__ import annotations

import re
from typing import Any

from hydracept.mcp.tool_documentation import TOOL_DESCRIPTIONS
from hydracept.mcp.tool_profiles import (
    COMPACT_DEFAULT_TOOL_NAMES,
    MCP_TOOL_PROFILE_COMPACT,
    MCP_TOOL_PROFILE_FULL,
    normalize_mcp_tool_profile,
)
from hydracept.mcp.tool_surface_names import (
    MCP_CANONICAL_TO_FULL_LIST_NAME,
    MCP_FULL_LIST_TO_CANONICAL,
    listed_name_for_profile,
)

_HOSTED_FULL_AT = "POST /mcp/full"
_STDIO_FULL_AT = "HYDRACEPT_MCP_TOOL_PROFILE=full"

# Tool names that may appear in canonical documentation text.
_DOC_TOOL_TOKENS: tuple[str, ...] = tuple(
    sorted(
        {
            *TOOL_DESCRIPTIONS.keys(),
            *MCP_CANONICAL_TO_FULL_LIST_NAME.values(),
            *MCP_CANONICAL_TO_FULL_LIST_NAME.keys(),
        },
        key=len,
        reverse=True,
    )
)

_TOOL_REF_RE = re.compile(
    r"(?<![a-z0-9_])(?:hydracept_[a-z0-9_]+|resolve_capability|request_capability_quote|"
    r"get_capability_request_quote)(?![a-z0-9_])"
)


def _canonical_for_token(token: str) -> str:
    return MCP_FULL_LIST_TO_CANONICAL.get(token, token)


def reference_name_for_profile(
    canonical: str,
    *,
    profile: str,
    listed_on_surface: set[str],
    full_surface_at: str = _HOSTED_FULL_AT,
) -> str:
    """How to refer to ``canonical`` from instructions/descriptions on ``profile``."""
    normalized = normalize_mcp_tool_profile(profile)
    listed = listed_name_for_profile(canonical, normalized)
    if listed in listed_on_surface:
        return listed
    full_name = listed_name_for_profile(canonical, MCP_TOOL_PROFILE_FULL)
    return f"{full_name} ({full_surface_at})"


def _dedupe_surface_label(text: str, label: str) -> str:
    """Collapse only back-to-back copies of the same surface label."""
    token = f"({label})"
    return re.sub(rf"({re.escape(token)})(?:\s*{re.escape(token)})+", r"\1", text)


def project_text_for_profile(
    text: str,
    *,
    profile: str,
    listed_on_surface: set[str],
    full_surface_at: str = _HOSTED_FULL_AT,
) -> str:
    if not text:
        return text
    result = text
    for token in _DOC_TOOL_TOKENS:
        if token not in result:
            continue
        canonical = _canonical_for_token(token)
        replacement = reference_name_for_profile(
            canonical,
            profile=profile,
            listed_on_surface=listed_on_surface,
            full_surface_at=full_surface_at,
        )
        pattern = re.compile(
            r"(?<![a-z0-9_])"
            + re.escape(token)
            + r"(?![a-z0-9_])(?!\s*\(\s*POST /mcp/full\s*\))"
        )
        result = pattern.sub(replacement, result)
    return _dedupe_surface_label(result, full_surface_at)


def _listed_tool_name(canonical: str, profile: str) -> str:
    return listed_name_for_profile(canonical, normalize_mcp_tool_profile(profile))


def mcp_server_instructions(profile: str, *, surface: str = "hosted") -> str:
    """Server ``instructions`` for hosted or stdio MCP at ``profile``."""
    normalized = normalize_mcp_tool_profile(profile)
    resolve = _listed_tool_name("hydracept_resolve_capability", normalized)
    quote = _listed_tool_name("hydracept_quote_capability", normalized)
    run = _listed_tool_name("hydracept_run", normalized)
    job_status = _listed_tool_name("hydracept_job_status", normalized)
    download = _listed_tool_name("hydracept_download_artifact", normalized)
    receipt = _listed_tool_name("hydracept_get_receipt", normalized)
    submit = _listed_tool_name("hydracept_submit_job", normalized)
    invoke = _listed_tool_name("hydracept_invoke", normalized)
    jobs_find = _listed_tool_name("hydracept_jobs_find", normalized)
    cancel_job = _listed_tool_name("hydracept_cancel_job", normalized)

    common = (
        "Hydracept executes external capabilities for agents. "
        f"Pass the user's words to {resolve}. Do not ask for a capability key and do not pick a key from memory. "
        f"Then optionally {quote}, then {run} on the resolved key. "
        f"Call {job_status} only when the result says to poll. "
        f"If you no longer have the job id, call {jobs_find}. "
        f"Call {cancel_job} only when the user asks to cancel the job itself; stopping a polling loop is not a cancellation. "
        f"Call {download} and {receipt} when the job produced them. "
    )
    full_at = _STDIO_FULL_AT if surface == "stdio" else _HOSTED_FULL_AT
    if normalized == MCP_TOOL_PROFILE_COMPACT:
        compact_listed = set(COMPACT_DEFAULT_TOOL_NAMES)
        invoke_ref = reference_name_for_profile(
            "hydracept_invoke",
            profile=normalized,
            listed_on_surface=compact_listed,
            full_surface_at=full_at,
        )
        specialist = (
            f"Specialists such as {invoke_ref}, pinned inference, and provenance tools are not listed here; "
            f"use {full_at} for the full specialist tools/list. "
        )
    else:
        specialist = (
            f"Specialists stay listed: {submit} returns immediately; "
            f"{invoke} is for synchronous read-only calls; "
            "pinned tools are exact model pins; "
            "provenance tools run after a receipt. "
        )
    hosted_tail = (
        "One capability call is enough; do not assume repeated usage is required. "
    )
    if surface == "hosted":
        hosted_tail += (
            "Authenticate with a Hydracept API key bearer token. "
            "Project apply/sync/watch require stdio MCP in the project checkout; "
            "this host does not execute local project commands."
        )
        return common + specialist + hosted_tail
    stdio_tail = (
        "hydracept_ui_* tools are the panel, not the agent. "
        "Hydracept public capability jobs, pinned execution, and project surfaces. "
        "Credentials resolve from workspace only. "
        "One capability call is enough — do not assume repeated usage is required. "
        "hydracept_run composes init when needed and waits for terminal completion by default; "
        "pass wait=false when an immediate durable-job continuation is preferred. "
    )
    if normalized == MCP_TOOL_PROFILE_COMPACT:
        stdio_tail += (
            "Other project tools (status/apply/sync/watch) and the interaction App are on "
            "full-profile stdio MCP only (unset HYDRACEPT_MCP_TOOL_PROFILE or set full). "
        )
    else:
        stdio_tail += (
            "Project surface tools require cwd to be the project checkout. "
            f"{submit} and {job_status} return immediately. "
            f"If nextAction is poll, wait pollAfterSeconds and call {job_status} again. "
            "Do not call hydracept_ui_* tools; those are for the Hydracept panel iframe only. "
            "For PNG transparency, never infer alpha correctness from a host image preview or vision description; "
            "trust transparencyReport or python -m hydracept verify <path.png> --json. "
            "A Hydracept App (ui://hydracept/app.html) is the visual control surface for "
            "seven semantic states: project.connect, capability.launch, "
            "connection.resolve, authorization.preflight, job.progress, artifact.review, "
            "and change.promote. "
            "When Hydracept returns presentation.agentAction=present_and_yield, present "
            "that surface and perform no subsequent unrelated tool calls or prose in the "
            "same turn. If presentation.status is mount_requested, present the App. "
            "If presentation.status is mounted or already_mounted, do not replace it "
            "with a text fallback. If presentation.status is fallback or unsupported, "
            "use the supplied fallback. "
            "Defer long assessments across blocking Hydracept interactions. "
            "When a human decision or structured input is needed, call "
            "hydracept_interaction_surface instead of synthesizing a browser or CLI flow. "
            "App-only hydracept_ui_* wrappers adapt user actions to existing primitives; they are not "
            "a second execution, pricing, or repository plane. Generic artifact review does "
            "not approve or reject jobs. Domain human gates use authorization.preflight. "
            "Promotion stays project-local. Hydracept cloud does not write repositories. "
        )
    stdio_tail += (
        "In a git checkout, use stdio MCP after `python -m hydracept init`. "
        "Hosted MCP with an API key is for clients with no checkout."
    )
    return common + specialist + stdio_tail


def enrich_tool_list_metadata_for_profile(
    tools: list[Any], *, profile: str, surface: str = "hosted"
) -> None:
    """Apply canonical descriptions with profile-correct tool cross-references."""
    from hydracept.mcp.tool_documentation import (
        PARAMETER_DESCRIPTIONS,
        enrich_tool_list_metadata,
    )

    enrich_tool_list_metadata(tools)
    listed_on_surface = {str(getattr(t, "name", "") or "") for t in tools if getattr(t, "name", None)}
    normalized = normalize_mcp_tool_profile(profile)
    full_at = _STDIO_FULL_AT if surface == "stdio" else _HOSTED_FULL_AT
    for tool in tools:
        name = str(getattr(tool, "name", "") or "")
        if not name:
            continue
        doc_key = MCP_FULL_LIST_TO_CANONICAL.get(name, name)
        raw = TOOL_DESCRIPTIONS.get(doc_key)
        if raw:
            tool.description = project_text_for_profile(
                raw, profile=normalized, listed_on_surface=listed_on_surface, full_surface_at=full_at
            )
        param_docs = PARAMETER_DESCRIPTIONS.get(doc_key)
        if not param_docs:
            continue
        schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
        if not isinstance(schema, dict):
            continue
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            continue
        for param_name, param_desc in param_docs.items():
            prop = properties.get(param_name)
            if isinstance(prop, dict) and param_desc:
                prop["description"] = project_text_for_profile(
                    param_desc,
                    profile=normalized,
                    listed_on_surface=listed_on_surface,
                    full_surface_at=full_at,
                )


def expected_tool_description(
    doc_key: str,
    *,
    profile: str,
    listed_on_surface: set[str],
    surface: str = "hosted",
) -> str:
    raw = TOOL_DESCRIPTIONS.get(doc_key, "")
    full_at = _STDIO_FULL_AT if surface == "stdio" else _HOSTED_FULL_AT
    return project_text_for_profile(
        raw, profile=profile, listed_on_surface=listed_on_surface, full_surface_at=full_at
    )


def tool_references_in_text(text: str) -> set[str]:
    return set(_TOOL_REF_RE.findall(text or ""))


def find_invalid_compact_doc_claims(text: str) -> list[str]:
    """Tool names claimed on /mcp/compact that compact does not list, plus a compact stdio default."""
    invalid: list[str] = []
    if re.search(r"stdio\s+defaults\s+to\s+(?:\*\*)?compact\b", text or "", flags=re.IGNORECASE):
        invalid.append("stdio-defaults-to-compact")
    compact = set(COMPACT_DEFAULT_TOOL_NAMES)
    for match in re.finditer(r"/mcp/compact", text or ""):
        left = max(
            (
                text.rfind(mark_text, 0, match.start())
                for mark_text in (".", ";", "\n", " or ", "(or ")
            ),
            default=-1,
        )
        right_at = [
            pos
            for pos in (
                text.find(".", match.end()),
                text.find(";", match.end()),
                text.find("\n", match.end()),
                text.find(" or ", match.end()),
            )
            if pos != -1
        ]
        right = min(right_at) if right_at else len(text)
        clause = text[left + 1 : right]
        if re.search(r"\b(?:not|never|without)\b", clause, flags=re.IGNORECASE):
            continue
        for token in sorted(tool_references_in_text(clause)):
            if token.endswith("_") and "hydracept_ui_*" in clause:
                continue
            if token not in compact:
                invalid.append(token)
    return invalid


def find_invalid_tool_references(text: str, *, listed_on_surface: set[str]) -> list[str]:
    """Tool names in ``text`` that are not listed and not explicitly routed to full."""
    invalid: list[str] = []
    for token in sorted(tool_references_in_text(text)):
        if token.endswith("_") and "hydracept_ui_*" in (text or ""):
            continue
        if token in listed_on_surface:
            continue
        if re.search(
            re.escape(token) + r"\s*\(\s*(?:POST /mcp/full|HYDRACEPT_MCP_TOOL_PROFILE=full)\s*\)",
            text or "",
        ):
            continue
        compact_label = re.search(re.escape(token) + r"\s*\(\s*/mcp/compact\s*\)", text or "")
        if compact_label and token in COMPACT_DEFAULT_TOOL_NAMES:
            continue
        if compact_label:
            invalid.append(token)
            continue
        invalid.append(token)
    return invalid
