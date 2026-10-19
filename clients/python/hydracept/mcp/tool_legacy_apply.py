"""Public-client copy of hydracept_contracts.mcp_tool_legacy_apply."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver.server import MCPServer

from hydracept.mcp.tool_legacy_aliases import MCP_TOOL_LEGACY_CALL_ALIASES
from hydracept.mcp.tool_profiles import (
    MCP_TOOL_PROFILE_COMPACT,
    MCP_TOOL_PROFILE_FULL,
    normalize_mcp_tool_profile,
    resolve_mcp_tool_profile,
)
from hydracept.mcp.tool_surface_names import full_surface_canonical_call_aliases


def _call_aliases_for_profile(profile: str) -> dict[str, str]:
    normalized = normalize_mcp_tool_profile(profile)
    if normalized == MCP_TOOL_PROFILE_FULL:
        return full_surface_canonical_call_aliases()
    if normalized == MCP_TOOL_PROFILE_COMPACT:
        return dict(MCP_TOOL_LEGACY_CALL_ALIASES)
    raise ValueError(f"unknown MCP profile {profile!r}")


def install_mcp_tool_legacy_call_aliases(
    server: MCPServer,
    *,
    profile: str | None = None,
) -> None:
    resolved = normalize_mcp_tool_profile(profile if profile is not None else resolve_mcp_tool_profile())
    aliases = _call_aliases_for_profile(resolved)
    if not aliases:
        return
    manager = server._tool_manager
    original = manager.call_tool

    async def call_tool_with_aliases(
        name: str,
        arguments: dict[str, Any],
        context: Any,
        convert_result: bool = False,
    ) -> Any:
        canonical = aliases.get(name, name)
        return await original(canonical, arguments, context, convert_result=convert_result)

    manager.call_tool = call_tool_with_aliases  # type: ignore[method-assign]
