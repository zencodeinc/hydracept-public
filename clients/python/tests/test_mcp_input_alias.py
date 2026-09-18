"""MCP tools accept `input` as an alias for `body` without silently discarding either."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hydracept.mcp.server import _capability_body, hydracept_invoke, hydracept_run


def test_capability_body_prefers_body() -> None:
    assert _capability_body({"prompt": "x"}, None) == {"prompt": "x"}


def test_capability_body_uses_input_alias() -> None:
    assert _capability_body(None, {"prompt": "x"}) == {"prompt": "x"}


def test_capability_body_empty_is_empty() -> None:
    assert _capability_body(None, None) == {}
    assert _capability_body(None, {}) == {}


def test_capability_body_non_dict_input_is_ignored() -> None:
    assert _capability_body({"prompt": "x"}, False) == {"prompt": "x"}  # type: ignore[arg-type]


def test_capability_body_rejects_both() -> None:
    with pytest.raises(ValueError, match="not both"):
        _capability_body({"prompt": "x"}, {"prompt": "y"})


def _patch_workspace(monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any], outcome: Any) -> None:
    class _Client:
        def invoke_capability(self, key: str, payload: dict) -> dict:
            captured["invoked"] = (key, payload)
            return {"status": "succeeded"}

    monkeypatch.setattr("hydracept.mcp.server._project_root", lambda: Path("."))
    monkeypatch.setattr(
        "hydracept.mcp.server._execution_workspace",
        lambda: type("W", (), {"api_url": "https://api.example", "token": "tok"})(),
    )
    monkeypatch.setattr(
        "hydracept.mcp.server.merge_workspace_job_context",
        lambda body, workspace: dict(body or {}),
    )
    monkeypatch.setattr("hydracept.mcp.server.HydraceptClient", lambda *a, **k: _Client())

    def fake_execute_run(root, capability, body, **kwargs):
        captured["executed"] = (capability, body)
        return outcome

    monkeypatch.setattr("hydracept.cli.run_facade.execute_run", fake_execute_run)


def test_hydracept_run_accepts_input_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    from hydracept.cli.run_facade import RunOutcome, RunResult

    captured: dict[str, Any] = {}
    _patch_workspace(
        monkeypatch,
        captured,
        RunOutcome(result=RunResult(capability="image.generate.v1", job_id="job_1", status="succeeded")),
    )

    result = hydracept_run(capability_key="image.generate.v1", input={"prompt": "icon"})

    assert captured["executed"] == ("image.generate.v1", {"prompt": "icon"})
    assert result.get("isError") is not True


def test_hydracept_run_rejects_body_and_input_together(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _patch_workspace(monkeypatch, captured, None)

    result = hydracept_run(
        capability_key="image.generate.v1",
        body={"prompt": "a"},
        input={"prompt": "b"},
    )

    assert result.is_error is True
    payload = result.structured_content or {}
    assert payload["code"] == "INVALID_ARGUMENT"
    assert "not both" in payload["message"]


def test_mcp_invoke_accepts_input_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _patch_workspace(monkeypatch, captured, None)

    hydracept_invoke(capability_key="domain.search.v1", input={"domain": "example.com"})

    assert captured["invoked"] == ("domain.search.v1", {"domain": "example.com"})
