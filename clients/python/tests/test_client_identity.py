"""Hydracept client identity headers and MCP component env."""

from __future__ import annotations

import os

from hydracept.client_identity import (
    HYDRACEPT_CLIENT_COMPONENT_ENV,
    resolve_hydracept_client_component,
)


def test_resolve_client_component_allowlists_plugin(monkeypatch) -> None:
    monkeypatch.setenv(HYDRACEPT_CLIENT_COMPONENT_ENV, "plugin")
    assert resolve_hydracept_client_component(default="mcp") == "plugin"


def test_resolve_client_component_rejects_unknown(monkeypatch) -> None:
    monkeypatch.delenv(HYDRACEPT_CLIENT_COMPONENT_ENV, raising=False)
    monkeypatch.setenv(HYDRACEPT_CLIENT_COMPONENT_ENV, "not-a-real-component")
    assert resolve_hydracept_client_component(default="mcp") == "mcp"
