"""agent-status payload must keep configured for doctor --local-only."""

from __future__ import annotations

from pathlib import Path

from hydracept import __version__ as hydracept_version
from hydracept.cli.agent_status import build_agent_status
from hydracept.cli.consumer_versions import consumer_versions
from hydracept.mcp.runtime_binding import attest_runtime_binding


def test_agent_status_keeps_configured_and_workspace_root(tmp_path: Path) -> None:
    payload = build_agent_status(tmp_path)
    assert payload["configured"] is False
    assert payload["ready"] is False
    assert payload["workspaceRoot"] == str(tmp_path.resolve())
    assert "--workspace" in payload["mcp"]["stdioCommand"]


def test_unresolved_status_includes_agent_pack_version() -> None:
    from hydracept.cli.agent_status import AGENT_PACK_VERSION
    from hydracept.mcp.server import _unresolved_status_payload

    payload = _unresolved_status_payload("workspace not set")
    assert payload["agentPackVersion"] == AGENT_PACK_VERSION
    assert payload["configured"] is False


def test_agent_status_flags_missing_agent_context_cache(tmp_path: Path) -> None:
    payload = build_agent_status(tmp_path)
    cache = payload["agentContextCache"]
    assert cache["present"] is False
    assert cache["stale"] is True


def test_agent_status_inspects_without_binding(tmp_path: Path) -> None:
    build_agent_status(tmp_path)
    assert not (tmp_path / ".cursor" / "mcp.json").exists()
    assert not (tmp_path / ".mcp.json").exists()


def test_agent_status_exposes_independent_versions(tmp_path: Path) -> None:
    payload = build_agent_status(tmp_path)
    assert payload["installedClientVersion"] == hydracept_version
    # runningMcp reports the configured binding generation (defaults to installed client).
    assert payload["runningMcpVersion"] == hydracept_version
    assert payload["versions"]["mcpRuntimeState"] == "unbound"
    assert payload["apiRevision"] is None
    assert payload["versions"]["apiRevisionState"] == "not_fetched"
    assert payload["versions"]["agentPack"] == "not_installed"


def test_attested_runtime_publishes_mcp_package_version(tmp_path: Path) -> None:
    attest_runtime_binding(tmp_path, source="test")
    versions = consumer_versions(tmp_path)
    assert versions["runningMcp"] == hydracept_version
    assert versions["installedClient"] == hydracept_version


def test_fetched_api_revision_is_explicit(tmp_path: Path) -> None:
    versions = consumer_versions(tmp_path, session={"routeBundleVersion": "routes.v23"})
    assert versions["apiRevision"] == "routes.v23"
    assert versions["apiRevisionState"] == "fetched"
