"""Tests for init JSON contract (ADR-028)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hydracept.cli.init_resolver import INIT_SCHEMA_VERSION, run_init


@pytest.fixture(autouse=True)
def _isolate_init_from_ambient_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.delenv("HYDRACEPT_TOKEN", raising=False)
    monkeypatch.setattr("hydracept.cli.init_resolver.load_session", lambda: None)
    monkeypatch.setattr(
        "hydracept.cli.init_resolver._try_local_identity_bootstrap",
        lambda *args, **kwargs: (None, [], {}),
    )


def test_init_requires_apply_json() -> None:
    result = run_init(Path.cwd(), apply=False, json_output=True)
    assert result.exit_code == 2
    assert result.payload["status"] == "interaction_required"
    assert result.payload.get("reason") == "apply_required"
    assert result.payload.get("stage") == "local_binding"


def test_init_interaction_required_without_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.setattr("hydracept.cli.init_resolver.load_session", lambda: None)
    result = run_init(tmp_path, apply=True, yes=True, json_output=True)
    assert result.exit_code == 0
    assert result.payload["status"] == "interaction_required"
    assert result.payload.get("stage") == "authentication"
    assert result.payload["identity"]["status"] == "pending"
    assert result.payload["project"]["status"] == "pending"
    assert result.payload["action"]["type"] == "open_url"
    assert result.payload.get("detail")
    assert result.payload["recommendedAction"] == "present_project_connect"
    assert result.payload["agentControl"] == {
        "mustStop": True,
        "resumeAfter": "human_activation_complete",
        "doNotPollBeforeResume": True,
    }
    assert result.payload["interaction"]["schemaVersion"] == "hydracept.interaction.v1"
    assert result.payload["interaction"]["surface"] == "project.connect"
    assert result.payload["interaction"]["tool"] == "hydracept_interaction_surface"
    assert result.payload["interaction"]["appUri"] == "ui://hydracept/app.html"
    assert result.payload["interaction"]["context"]["actionUrl"] == result.payload["action"]["url"]
    assert result.payload["presentation"]["agentAction"] == "present_and_yield"
    assert result.payload["presentation"]["status"] == "mount_requested"
    assert result.payload["presentation"]["surface"] == "project.connect"
    instruction = str(result.payload.get("agentInstruction") or "")
    assert "final tool call" in instruction
    assert "Do not start --wait" in instruction
    assert "action.url" in instruction
    assert "apiKey" not in json.dumps(result.payload)


def test_init_ci_missing_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    result = run_init(tmp_path, apply=True, yes=True, json_output=True, ci_mode=True)
    assert result.payload["status"] == "configuration_required"
    assert result.payload["reason"] == "missing_api_key"
    assert result.payload.get("stage") == "authentication"
