"""`version --json` exposes the same consumer provenance facts as doctor."""

from __future__ import annotations

import json

from click.testing import CliRunner

from hydracept.cli import entrypoint

_FACTS = {
    "installedClient": "0.4.2",
    "mcpBindingVersion": "gen_provenance",
    "mcpRuntimeState": "ready",
    "apiRevision": "routes.v23",
    "apiRevisionState": "fetched",
    "agentPack": "0.1.1",
}


def _report() -> dict:
    return {
        "version": "0.4.2",
        "packagePath": "x",
        "distribution": {"source": "source-checkout"},
        "consumer": dict(_FACTS),
    }


def test_version_json_mirrors_consumer_provenance(monkeypatch) -> None:
    monkeypatch.setattr(
        "hydracept.cli.consumer_versions.consumer_version_report",
        lambda root: _report(),
    )

    result = CliRunner().invoke(entrypoint.app, ["version", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["apiRevision"] == "routes.v23"
    assert payload["apiRevisionState"] == "fetched"
    assert payload["agentPack"] == "0.1.1"
    assert payload["consumer"]["mcpBindingVersion"] == "gen_provenance"


def test_version_json_reports_not_fetched_without_a_session(monkeypatch) -> None:
    report = _report()
    report["consumer"] = {
        "installedClient": "0.4.2",
        "mcpBindingVersion": "gen_provenance",
        "apiRevision": None,
        "apiRevisionState": "not_fetched",
        "agentPack": "0.1.1",
    }
    monkeypatch.setattr(
        "hydracept.cli.consumer_versions.consumer_version_report",
        lambda root: report,
    )

    result = CliRunner().invoke(entrypoint.app, ["version", "--json"])

    payload = json.loads(result.output)
    assert payload["apiRevision"] is None
    assert payload["apiRevisionState"] == "not_fetched"
    assert payload["agentPack"] == "0.1.1"


def test_version_refresh_uses_the_live_session_revision(monkeypatch) -> None:
    monkeypatch.setattr(
        "hydracept.cli.consumer_versions.consumer_version_report",
        lambda root: {
            "version": "0.4.2",
            "packagePath": "x",
            "distribution": {"source": "source-checkout"},
            "consumer": {**_FACTS, "apiRevision": None, "apiRevisionState": "not_fetched"},
        },
    )
    monkeypatch.setattr(
        "hydracept.cli.agent_status.build_agent_status",
        lambda root, refresh=False: {"versions": {**_FACTS, "apiRevision": "routes.v24"}},
    )

    result = CliRunner().invoke(entrypoint.app, ["version", "--refresh", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["apiRevision"] == "routes.v24"
    assert payload["apiRevisionState"] == "fetched"


def test_version_refresh_failure_still_prints_version(monkeypatch) -> None:
    monkeypatch.setattr(
        "hydracept.cli.consumer_versions.consumer_version_report",
        lambda root: _report(),
    )

    def _boom(root, refresh=False):
        raise RuntimeError("network down")

    monkeypatch.setattr("hydracept.cli.agent_status.build_agent_status", _boom)

    result = CliRunner().invoke(entrypoint.app, ["version", "--refresh", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["version"] == "0.4.2"
    assert payload["refreshError"] == "network down"
