"""Stable Hydracept client identification for HTTP APIs."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

HYDRACEPT_CLIENT_HEADER = "X-Hydracept-Client"


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
