"""Public-client copy of hydracept_contracts.mcp_tool_surface_names."""

from __future__ import annotations

from typing import Final

from mcp.server.mcpserver.server import MCPServer

from hydracept.mcp.tool_profiles import (
    MCP_TOOL_PROFILE_FULL,
    normalize_mcp_tool_profile,
)

MCP_CANONICAL_TO_FULL_LIST_NAME: Final[dict[str, str]] = {
    "hydracept_resolve_capability": "resolve_capability",
    "hydracept_request_capability_quote": "request_capability_quote",
    "hydracept_get_capability_request_quote": "get_capability_request_quote",
    "hydracept_workspace_status": "hydracept_status",
}

MCP_FULL_LIST_TO_CANONICAL: Final[dict[str, str]] = {
    legacy: canonical for canonical, legacy in MCP_CANONICAL_TO_FULL_LIST_NAME.items()
}


def listed_name_for_profile(registered_name: str, profile: str) -> str:
    normalized = normalize_mcp_tool_profile(profile)
    if normalized == MCP_TOOL_PROFILE_FULL:
        return MCP_CANONICAL_TO_FULL_LIST_NAME.get(registered_name, registered_name)
    return registered_name


def project_listed_tool_names(names: tuple[str, ...] | list[str], profile: str) -> tuple[str, ...]:
    normalized = normalize_mcp_tool_profile(profile)
    projected = [listed_name_for_profile(str(name), normalized) for name in names]
    return tuple(sorted(set(projected)))


def apply_full_surface_list_name_renames(server: MCPServer) -> None:
    tools_map = getattr(server._tool_manager, "_tools", None)
    if not isinstance(tools_map, dict):
        raise RuntimeError("MCP tool manager has no _tools map")
    for canonical, legacy in MCP_CANONICAL_TO_FULL_LIST_NAME.items():
        entry = tools_map.pop(canonical, None)
        if entry is None:
            continue
        if hasattr(entry, "name"):
            entry.name = legacy
        tools_map[legacy] = entry


def full_surface_canonical_call_aliases() -> dict[str, str]:
    return dict(MCP_CANONICAL_TO_FULL_LIST_NAME)
