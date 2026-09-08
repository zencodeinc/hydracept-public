"""CLI opportunistic run composes existing init."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from hydracept.cli.run_capability import (
    RunCapabilityError,
    build_run_input,
    ensure_workspace_for_run,
    run_capability,
)
from hydracept.cli.workspace import ResolvedWorkspace, WorkspaceState


def test_build_run_input_prompt_and_json() -> None:
    payload = build_run_input(
        prompt="blue slime",
        input_json='{"requestTransparentOutput": true, "width": 1024}',
    )
    assert payload["prompt"] == "blue slime"
    assert payload["requestTransparentOutput"] is True
    assert payload["width"] == 1024


def test_ensure_workspace_returns_ready_without_init(monkeypatch, tmp_path: Path) -> None:
    ready = ResolvedWorkspace(
        api_url="https://api.hydracept.com",
        token="tok",
        project_id="cpr_test",
        environment="development",
    )
    monkeypatch.setattr(
        "hydracept.cli.run_capability.resolve_workspace",
        lambda *args, **kwargs: ready,
    )
    monkeypatch.setattr(
        "hydracept.cli.run_capability.workspace_state",
        lambda resolved: WorkspaceState.READY,
    )
    called = {"init": False}

    def _init(*args, **kwargs):
        called["init"] = True
        return SimpleNamespace(payload={"status": "ready"}, exit_code=0)

    monkeypatch.setattr("hydracept.cli.run_capability.run_init", _init)
    workspace, payload = ensure_workspace_for_run(tmp_path)
    assert workspace is ready
    assert payload is None
    assert called["init"] is False


def test_ensure_workspace_composes_init_when_unbound(monkeypatch, tmp_path: Path) -> None:
    ready = ResolvedWorkspace(
        api_url="https://api.hydracept.com",
        token="tok",
        project_id="cpr_test",
        environment="development",
    )
    states = {"n": 0}

    def _resolve(*args, **kwargs):
        states["n"] += 1
        if states["n"] == 1:
            return None
        return ready

    monkeypatch.setattr("hydracept.cli.run_capability.resolve_workspace", _resolve)
    monkeypatch.setattr(
        "hydracept.cli.run_capability.workspace_state",
        lambda resolved: WorkspaceState.READY,
    )
    monkeypatch.setattr(
        "hydracept.cli.run_capability.run_init",
        lambda *args, **kwargs: SimpleNamespace(payload={"status": "ready"}, exit_code=0),
    )
    workspace, payload = ensure_workspace_for_run(tmp_path)
    assert workspace is ready
    assert payload["bootstrapComposed"] is True


def test_ensure_workspace_surfaces_interaction_required(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("hydracept.cli.run_capability.resolve_workspace", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "hydracept.cli.run_capability.run_init",
        lambda *args, **kwargs: SimpleNamespace(
            payload={
                "status": "interaction_required",
                "action": {"url": "https://hydracept.com/connect/abc"},
            },
            exit_code=0,
        ),
    )
    workspace, payload = ensure_workspace_for_run(tmp_path)
    assert workspace is None
    assert payload["status"] == "interaction_required"
    assert payload["bootstrapComposed"] is True
    assert "hydracept.com/connect" in payload["action"]["url"]


def test_run_capability_requires_input(tmp_path: Path) -> None:
    try:
        run_capability(tmp_path, "image.generate.v1")
    except RunCapabilityError as exc:
        assert "prompt" in str(exc).lower()
    else:
        raise AssertionError("expected RunCapabilityError")


def test_funding_required_payload_from_http_error() -> None:
    from hydracept.cli.run_capability import _http_boundary_payload

    class _Resp:
        status_code = 402

        def json(self):
            return {
                "code": "funding_required",
                "message": "x",
                "details": {
                    "status": "funding_required",
                    "fundingOptions": ["managed", "byok"],
                    "legacyCode": "billing_managed_usage_exhausted",
                },
            }

    class _Exc(Exception):
        response = _Resp()

    payload = _http_boundary_payload(_Exc())
    assert payload is not None
    assert payload["status"] == "funding_required"
    assert payload["fundingOptions"] == ["managed", "byok"]
    assert "managed funding" in payload["message"].lower()
