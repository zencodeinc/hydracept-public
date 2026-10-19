"""Public-client copy of hydracept_contracts.mcp_tool_profiles.

Keep in sync with packages/contracts/hydracept_contracts/mcp_tool_profiles.py.
The published hydracept wheel cannot import hydracept_contracts.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Final

MCP_TOOL_PROFILE_ENV: Final = "HYDRACEPT_MCP_TOOL_PROFILE"
MCP_TOOL_PROFILE_COMPACT: Final = "compact"
MCP_TOOL_PROFILE_FULL: Final = "full"
DEFAULT_MCP_TOOL_PROFILE: Final = MCP_TOOL_PROFILE_FULL

COMPACT_DEFAULT_TOOL_NAMES: Final[tuple[str, ...]] = (
    "hydracept_resolve_capability",
    "hydracept_capabilities",
    "hydracept_quote_capability",
    "hydracept_run",
    "hydracept_submit_job",
    "hydracept_job_status",
    "hydracept_jobs_find",
    "hydracept_cancel_job",
    "hydracept_get_receipt",
    "hydracept_download_artifact",
    "hydracept_workspace_status",
)

_COMPACT_SET = frozenset(COMPACT_DEFAULT_TOOL_NAMES)


def normalize_mcp_tool_profile(raw: str | None) -> str:
    value = str(raw or "").strip().lower()
    if not value:
        return DEFAULT_MCP_TOOL_PROFILE
    if value in {MCP_TOOL_PROFILE_COMPACT, MCP_TOOL_PROFILE_FULL}:
        return value
    raise ValueError(
        f"Invalid {MCP_TOOL_PROFILE_ENV}={raw!r}; "
        f"use {MCP_TOOL_PROFILE_COMPACT!r} or {MCP_TOOL_PROFILE_FULL!r}"
    )


def resolve_mcp_tool_profile(*, environ: Mapping[str, str] | None = None) -> str:
    env = os.environ if environ is None else environ
    return normalize_mcp_tool_profile(env.get(MCP_TOOL_PROFILE_ENV))


def filter_tool_names_for_profile(
    registered_names: tuple[str, ...] | list[str],
    profile: str,
) -> tuple[str, ...]:
    normalized = normalize_mcp_tool_profile(profile)
    names = tuple(sorted(set(str(name) for name in registered_names if str(name).strip())))
    if normalized == MCP_TOOL_PROFILE_FULL:
        return names
    return tuple(name for name in names if name in _COMPACT_SET)


def compact_tool_names_on_surface(surface_names: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return filter_tool_names_for_profile(surface_names, MCP_TOOL_PROFILE_COMPACT)
