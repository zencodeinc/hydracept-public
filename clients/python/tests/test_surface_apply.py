"""Idempotent hydracept surface apply against the public panel-definitions API."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from hydracept.cli.session_client import SessionClientError
from hydracept.cli.surface_cmd import apply_project_surfaces, apply_surface, project_tools_fingerprint
from hydracept.cli.surface_definition import SurfaceDefinitionError


@pytest.fixture(autouse=True)
def _bound_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "hydracept.cli.surface_cmd.resolve_bound_project_id",
        lambda *args, **kwargs: "cpr_test",
    )


def _definition_file(tmp_path: Path) -> Path:
    path = tmp_path / "combat-balance.json"
    path.write_text(
        json.dumps(
            {
                "key": "combat-balance",
                "displayName": "Combat balance",
                "actions": [
                    {
                        "key": "validate",
                        "label": "Validate",
                        "handler": {"kind": "projectCommand", "command": "validate"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _view(*, origin: str = "project", version: int = 1) -> dict[str, Any]:
    return {
        "id": "pd_combat",
        "key": "combat-balance",
        "displayName": "Combat balance",
        "origin": origin,
        "currentVersion": {"version": version, "actions": []},
    }


class _FakeClient:
    def __init__(self, handler: Any) -> None:
        self._handler = handler

    def get(self, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
        return self._handler("GET", url, None)

    def post(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        return self._handler("POST", url, json)

    def patch(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        return self._handler("PATCH", url, json)


def _response(method: str, url: str, status: int, payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        status,
        json=payload,
        request=httpx.Request(method, url),
    )


def test_apply_creates_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HYDRACEPT_API_KEY", "hapt_test")
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def handler(method: str, url: str, body: dict[str, Any] | None) -> httpx.Response:
        calls.append((method, url, body))
        if method == "GET":
            return _response(method, url, 200, {"definitions": []})
        assert method == "POST"
        assert body is not None
        assert body["origin"] == "project"
        assert body["key"] == "combat-balance"
        assert body["projectId"] == "cpr_test"
        return _response(method, url, 200, _view(version=1))

    result = apply_surface(
        _definition_file(tmp_path),
        api="https://api.example.com",
        project_root=tmp_path,
        token=None,
        http_client=_FakeClient(handler),
    )
    assert result["status"] == "created"
    assert result["id"] == "pd_combat"
    assert result["version"] == 1
    assert result["origin"] == "project"
    assert calls[0][0] == "GET"
    assert calls[1][0] == "POST"


def test_apply_patches_existing_project_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HYDRACEPT_API_KEY", "hapt_test")

    def handler(method: str, url: str, body: dict[str, Any] | None) -> httpx.Response:
        if method == "GET":
            return _response(method, url, 200, {"definitions": [_view(version=1)]})
        assert method == "PATCH"
        assert "pd_combat" in url
        assert body is not None
        assert body["origin"] == "project"
        return _response(method, url, 200, _view(version=2))

    result = apply_surface(
        _definition_file(tmp_path),
        api="https://api.example.com",
        project_root=tmp_path,
        token=None,
        http_client=_FakeClient(handler),
    )
    assert result["status"] == "updated"
    assert result["version"] == 2


def test_apply_refuses_hydracept_owned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HYDRACEPT_API_KEY", "hapt_test")

    def handler(method: str, url: str, body: dict[str, Any] | None) -> httpx.Response:
        assert method == "GET"
        return _response(
            method, url, 200, {"definitions": [_view(origin="hydracept")]}
        )

    with pytest.raises(SurfaceDefinitionError, match="Hydracept-owned"):
        apply_surface(
            _definition_file(tmp_path),
            api="https://api.example.com",
            project_root=tmp_path,
            token=None,
            http_client=_FakeClient(handler),
        )


def test_apply_requires_credential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.delenv("HYDRACEPT_TOKEN", raising=False)
    with pytest.raises(SessionClientError) as exc:
        apply_surface(
            _definition_file(tmp_path),
            api="https://api.example.com",
            project_root=tmp_path,
            token=None,
        )
    assert exc.value.status_code == 401


def test_apply_project_surfaces_applies_json_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HYDRACEPT_API_KEY", "hapt_test")
    surfaces = tmp_path / "tools" / "hydracept" / "surfaces"
    surfaces.mkdir(parents=True)
    (surfaces / "word-trace-workbench.json").write_text(
        json.dumps(
            {
                "key": "knights-of-lex.word-trace-workbench",
                "displayName": "Word Trace Workbench",
                "actions": [
                    {
                        "key": "preview",
                        "label": "Preview",
                        "handler": {"kind": "projectCommand", "command": "preview"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    created: list[dict[str, Any]] = []

    def handler(method: str, url: str, body: dict[str, Any] | None) -> httpx.Response:
        if method == "GET":
            return _response(method, url, 200, {"definitions": []})
        created.append(body or {})
        return _response(
            method,
            url,
            201,
            {
                "id": "pd_1",
                "key": "knights-of-lex.word-trace-workbench",
                "displayName": "Word Trace Workbench",
                "origin": "project",
                "currentVersion": {"version": 1, "actions": []},
            },
        )

    results = apply_project_surfaces(
        api="https://api.example.com",
        project_root=tmp_path,
        token=None,
        http_client=_FakeClient(handler),
    )
    assert results[0]["status"] == "created"
    assert results[0]["key"] == "knights-of-lex.word-trace-workbench"
    assert created[0]["origin"] == "project"
    assert created[0]["projectId"] == "cpr_test"


def test_project_tools_fingerprint_changes_when_surface_json_changes(tmp_path: Path) -> None:
    surfaces = tmp_path / "tools" / "hydracept" / "surfaces"
    surfaces.mkdir(parents=True)
    target = surfaces / "tool.json"
    target.write_text("{}", encoding="utf-8")
    first = project_tools_fingerprint(tmp_path)
    target.write_text('{"key":"x"}', encoding="utf-8")
    assert project_tools_fingerprint(tmp_path) != first


def test_apply_does_not_publish_operations_policy() -> None:
    import inspect

    from hydracept.cli import surface_cmd, surface_definition

    apply_src = inspect.getsource(surface_cmd)
    definition_src = inspect.getsource(surface_definition)
    assert "/v1/projects/" not in apply_src
    assert "operationsPolicy" not in apply_src
    assert "operationsPolicy" not in definition_src
    assert "create_project_operation" not in apply_src
