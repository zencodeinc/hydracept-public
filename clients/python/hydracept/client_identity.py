"""Stable Hydracept client identification for HTTP APIs."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

HYDRACEPT_CLIENT_HEADER = "X-Hydracept-Client"
HYDRACEPT_CLIENT_COMPONENT_ENV = "HYDRACEPT_CLIENT_COMPONENT"
_ALLOWED_CLIENT_COMPONENTS = frozenset(
    {
        "cli",
        "sdk",
        "python-sdk",
        "typescript-sdk",
        "csharp-sdk",
        "mcp",
        "plugin",
        "browser",
    }
)


def resolve_hydracept_client_component(*, default: str = "sdk") -> str:
    import os

    raw = os.environ.get(HYDRACEPT_CLIENT_COMPONENT_ENV, "").strip().lower()
    if raw in _ALLOWED_CLIENT_COMPONENTS:
        return raw
    normalized = default.strip().lower()
    if normalized in _ALLOWED_CLIENT_COMPONENTS:
        return normalized
    return "sdk"


def hydracept_client_version() -> str:
    try:
        return version("hydracept")
    except PackageNotFoundError:
        return "0.0.0+source"


def hydracept_client_headers(*, component: str = "sdk") -> dict[str, str]:
    ver = hydracept_client_version()
    agent = f"hydracept/{ver} {component}".strip()
    return {
        HYDRACEPT_CLIENT_HEADER: agent,
        "User-Agent": agent,
    }
