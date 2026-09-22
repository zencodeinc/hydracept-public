"""MCP tools accept `input` as an alias for `body` without silently discarding either."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from hydracept.mcp.server import (
    _capability_body,
    hydracept_invoke,
    hydracept_run,
    hydracept_submit_job,
)


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


def test_estimate_capability_forwards_input_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_quote(key: str, body: Any = None, **kwargs: Any) -> dict[str, Any]:
        captured["call"] = (key, body, kwargs)
        return {"pricing": {}}

    monkeypatch.setattr("hydracept.mcp.server.hydracept_quote_capability", fake_quote)

    from hydracept.mcp.server import estimate_capability

    estimate_capability(capability_key="domain.search.v1", input={"domain": "example.com"})

    assert captured["call"] == (
        "domain.search.v1",
        None,
        {"input": {"domain": "example.com"}},
    )


def test_hydracept_submit_job_accepts_input_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_submit(key: str, body: dict, idempotency_key: str) -> dict[str, Any]:
        captured["call"] = (key, body, idempotency_key)
        return {"status": "queued", "jobId": "job_1"}

    monkeypatch.setattr("hydracept.mcp.server._submit_job_payload", fake_submit)

    result = hydracept_submit_job(capability_key="image.generate.v1", input={"prompt": "icon"})

    assert captured["call"][0] == "image.generate.v1"
    assert captured["call"][1] == {"prompt": "icon"}
    assert result.get("isError") is not True


def test_hydracept_submit_job_rejects_body_and_input(monkeypatch: pytest.MonkeyPatch) -> None:
    result = hydracept_submit_job(
        capability_key="image.generate.v1",
        body={"prompt": "a"},
        input={"prompt": "b"},
    )

    assert result.is_error is True
    payload = result.structured_content or {}
    assert payload["code"] == "INVALID_ARGUMENT"
    assert "not both" in payload["message"]


def test_hydracept_run_terminal_success_is_slim(monkeypatch: pytest.MonkeyPatch) -> None:
    from hydracept.cli.run_facade import RunOutcome, RunResult

    captured: dict[str, Any] = {}
    _patch_workspace(
        monkeypatch,
        captured,
        RunOutcome(
            result=RunResult(
                capability="text.translate.v1", job_id="job_1", status="succeeded"
            )
        ),
    )

    result = hydracept_run(
        capability_key="text.translate.v1",
        input={"targetLocale": "es", "items": [{"id": "1", "text": "hi"}]},
    )

    assert result.get("isError") is not True
    assert "interaction" not in result
    assert "presentation" not in result
    assert result.get("nextAction") == "stop"
