"""MCP runtime presentation: only incompatible/unreachable are warning-shaped."""

from __future__ import annotations

import json

from hydracept.cli.mcp_bind import McpBindResult
from hydracept.mcp.runtime_binding import RuntimeBindingStatus


def _bind(**overrides) -> McpBindResult:
    base = {
        "bound": True,
        "transport": "stdio",
        "project_config": (),
        "reload_required": False,
    }
    base.update(overrides)
    return McpBindResult(**base)


def test_verified_runtime_is_current_and_quiet() -> None:
    state = _bind(runtime=RuntimeBindingStatus(True, "verified")).runtime_state()
    assert state["state"] == "current"
    assert state["severity"] == "info"
    assert state["warning"] is False


def test_stale_config_is_reload_available_not_a_warning(tmp_path) -> None:
    from hydracept.cli.mcp_bind import inspect_workspace_mcp, stdio_args

    (tmp_path / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "hydracept": {
                        "command": "python",
                        "args": stdio_args(tmp_path),
                        "env": {"HYDRACEPT_MCP_GENERATION": "stale-generation-000"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    binding = inspect_workspace_mcp(tmp_path)
    assert binding.bound is False
    assert binding.config_stale is True
    state = binding.runtime_state()
    assert state["state"] == "reload_available"
    assert state["severity"] == "info"
    assert state["warning"] is False
    assert "reload available" in state["message"]


def test_workspace_mismatch_is_incompatible_and_warns() -> None:
    state = _bind(
        reload_required=True,
        runtime=RuntimeBindingStatus(False, "workspace_mismatch"),
    ).runtime_state()
    assert state["state"] == "incompatible"
    assert state["severity"] == "warning"
    assert state["warning"] is True


def test_missing_runtime_is_not_started() -> None:
    state = _bind(runtime=RuntimeBindingStatus(False, "missing")).runtime_state()
    assert state["state"] == "not_started"
    assert state["warning"] is False


def test_pid_reuse_is_reload_available() -> None:
    state = _bind(
        reload_required=True,
        runtime=RuntimeBindingStatus(False, "pid_reused"),
    ).runtime_state()
    assert state["state"] == "reload_available"
    assert state["warning"] is False


def test_to_dict_exposes_canonical_runtime_fields() -> None:
    payload = _bind(runtime=RuntimeBindingStatus(True, "verified")).to_dict()
    assert payload["runtimeState"] == "current"
    assert payload["runtimeStateSeverity"] == "info"
    assert payload["runtimeStateMessage"] == "MCP runtime: functional"


def test_consumer_versions_exposes_presentation_state(tmp_path) -> None:
    from hydracept.cli.consumer_versions import consumer_versions

    versions = consumer_versions(tmp_path)
    assert versions["mcpRuntimeState"] == "unbound"
    assert versions["mcpRuntimeStatePresentation"] == "not_started"
    assert versions["mcpRuntimeSeverity"] == "info"
