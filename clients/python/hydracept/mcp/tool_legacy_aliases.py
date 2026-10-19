"""Public-client copy of hydracept_contracts.mcp_tool_legacy_aliases."""

from __future__ import annotations

from typing import Final

MCP_TOOL_LEGACY_CALL_ALIASES: Final[dict[str, str]] = {
    "resolve_capability": "hydracept_resolve_capability",
    "request_capability_quote": "hydracept_request_capability_quote",
    "get_capability_request_quote": "hydracept_get_capability_request_quote",
    "hydracept_status": "hydracept_workspace_status",
}

MCP_TOOL_LEGACY_CALL_ALIAS_NAMES: Final[tuple[str, ...]] = tuple(
    sorted(MCP_TOOL_LEGACY_CALL_ALIASES.keys())
)
