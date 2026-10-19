"""Apply MCP tool discovery profiles to a built MCPServer (public client copy)."""

from __future__ import annotations

from mcp.server.mcpserver.server import MCPServer

from hydracept.mcp.tool_profiles import (
    MCP_TOOL_PROFILE_FULL,
    filter_tool_names_for_profile,
    normalize_mcp_tool_profile,
    resolve_mcp_tool_profile,
)


def apply_mcp_tool_profile(
    server: MCPServer,
    *,
    profile: str | None = None,
    registered_names: tuple[str, ...] | None = None,
) -> str:
    resolved = normalize_mcp_tool_profile(profile if profile is not None else resolve_mcp_tool_profile())
    if resolved == MCP_TOOL_PROFILE_FULL:
        return resolved
    tools_map = getattr(server._tool_manager, "_tools", None)
    if not isinstance(tools_map, dict):
        raise RuntimeError("MCP tool manager has no _tools map")
    if registered_names is None:
        registered_names = tuple(sorted(tools_map.keys()))
    allowed = set(filter_tool_names_for_profile(registered_names, resolved))
    for name in list(tools_map.keys()):
        if name not in allowed:
            tools_map.pop(name, None)
    return resolved
