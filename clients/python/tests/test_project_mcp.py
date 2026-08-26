"""Stdio MCP project-surface tools wrap the public CLI; they do not execute on the API host."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from hydracept.cli.project_service import ProjectUpServiceStatus
from hydracept.cli.session_client import SessionClientError
from hydracept.cli.surface_definition import SurfaceDefinitionError
from hydracept.mcp.icons import HYDRACEPT_LOGO_URL
from hydracept.mcp.project_mcp import STDIO_PROJECT_TOOL_NAMES, ProjectMcpService
from hydracept.mcp.server import server


def test_stdio_mcp_advertises_stylized_h_icon() -> None:
    assert server.icons
    assert any(icon.src == HYDRACEPT_LOGO_URL for icon in server.icons)


def _bind_workspace(root: Path) -> None:
    hydra = root / ".hydracept"
    hydra.mkdir(parents=True)
    (hydra / "config.json").write_text(
        json.dumps({"apiBaseUrl": "https://api.example.com", "projectId": "cpr_studio"}),
        encoding="utf-8",
    )


def _surface_file(root: Path, *, name: str = "combat-balance.json") -> Path:
    surfaces = root / "tools" / "hydracept" / "surfaces"
    surfaces.mkdir(parents=True)
    path = surfaces / name
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


class _FakeClient:
    def __init__(self, handler: Any) -> None:
        self._handler = handler
        self.urls: list[str] = []

    def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        self.urls.append(url)
        return self._handler("GET", url, None, params)

    def post(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        self.urls.append(url)
        return self._handler("POST", url, json, None)

    def patch(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        self.urls.append(url)
        return self._handler("PATCH", url, json, None)


def _response(method: str, url: str, status: int, payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(status, json=payload, request=httpx.Request(method, url))


def test_stdio_server_registers_project_tools() -> None:
    names = [tool.name for tool in server._tool_manager.list_tools()]
    for expected in STDIO_PROJECT_TOOL_NAMES:
        assert expected in names
    assert "hydracept_submit_job" in names
    assert "hydracept_invoke" in names
    for expected in (
        "hydracept_pinned_run",
        "hydracept_pinned_get",
        "hydracept_manifest_create",
        "hydracept_manifest_verify",
        "hydracept_lockfile_emit",
        "hydracept_verify_lockfile",
    ):
        assert expected in names


def test_apply_does_not_call_execute_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HYDRACEPT_API_KEY", "hapt_test")
    _bind_workspace(tmp_path)
    _surface_file(tmp_path)

    def handler(
        method: str,
        url: str,
        body: dict[str, Any] | None,
        params: dict[str, str] | None,
    ) -> httpx.Response:
        if method == "GET":
            return _response(method, url, 200, {"definitions": []})
        return _response(
            method,
            url,
            200,
            {
                "id": "pd_combat",
                "key": "combat-balance",
                "displayName": "Combat balance",
                "origin": "project",
                "currentVersion": {"version": 1, "actions": []},
            },
        )

    client = _FakeClient(handler)
    result = ProjectMcpService(tmp_path, http_client=client).apply_surfaces()
    assert result["applied"][0]["status"] == "created"
    assert all("execute-local" not in url for url in client.urls)
    assert any("/v1/panel-definitions" in url for url in client.urls)


def test_apply_requires_bound_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HYDRACEPT_API_KEY", "hapt_test")

    def _no_session() -> dict[str, Any]:
        raise SessionClientError("no session", status_code=401)

    monkeypatch.setattr(
        "hydracept.cli.project_agent.fetch_session_context",
        _no_session,
    )
    hydra = tmp_path / ".hydracept"
    hydra.mkdir(parents=True)
    (hydra / "config.json").write_text(
        json.dumps({"apiBaseUrl": "https://api.example.com"}),
        encoding="utf-8",
    )
    _surface_file(tmp_path)

    with pytest.raises(SurfaceDefinitionError, match="No Hydracept project id"):
        ProjectMcpService(tmp_path).apply_surfaces()


def test_apply_missing_file_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HYDRACEPT_API_KEY", "hapt_test")
    _bind_workspace(tmp_path)
    with pytest.raises(SurfaceDefinitionError, match="not found"):
        ProjectMcpService(tmp_path).apply_surfaces("tools/hydracept/surfaces/missing.json")


def test_request_operation_requires_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HYDRACEPT_API_KEY", "hapt_test")
    _bind_workspace(tmp_path)
    with pytest.raises(SessionClientError, match="command is required"):
        ProjectMcpService(tmp_path).request_operation("  ")


def test_request_operation_posts_public_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HYDRACEPT_API_KEY", "hapt_test")
    _bind_workspace(tmp_path)
    posted: dict[str, Any] = {}

    def handler(
        method: str,
        url: str,
        body: dict[str, Any] | None,
        params: dict[str, str] | None,
    ) -> httpx.Response:
        assert method == "POST"
        assert url.endswith("/v1/projects/cpr_studio/operations")
        assert "execute-local" not in url
        posted.update(body or {})
        return _response(method, url, 200, {"id": "pop_1", "status": "requested"})

    result = ProjectMcpService(tmp_path, http_client=_FakeClient(handler)).request_operation(
        "preview",
        action_key="preview-word",
        input={"seed": "1"},
    )
    assert result["id"] == "pop_1"
    assert posted["command"] == "preview"
    assert posted["actionKey"] == "preview-word"
    assert posted["input"] == {"seed": "1"}


def test_watch_once_defers_when_persistent_watcher_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HYDRACEPT_API_KEY", "hapt_test")
    _bind_workspace(tmp_path)
    monkeypatch.setattr("hydracept.mcp.project_mcp.watcher_running", lambda _root: True)
    result = ProjectMcpService(tmp_path).watch_once()
    assert result["deferred"] is True
    assert "already running" in result["reason"]


def test_sync_does_not_call_execute_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HYDRACEPT_API_KEY", "hapt_test")
    _bind_workspace(tmp_path)
    hydra = tmp_path / "tools" / "hydracept"
    hydra.mkdir(parents=True)
    (hydra / "project.yaml").write_text(
        "\n".join(
            [
                "schemaVersion: hydracept.project.v1",
                "projectId: knights-of-lex",
                "displayName: Knights of Lex",
                "adapter:",
                "  protocolVersion: 1",
                "  entrypoint: tools/hydracept",
                "repository:",
                "    allowedWriteRoots: []",
                "    dirtyTreePolicy: reject-conflicting",
                "validation:",
                "  commands: []",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (hydra / "manifest.json").write_text(
        json.dumps(
            {
                "operations": {
                    "preview": {
                        "command": "preview",
                        "allowlisted": True,
                        "argv": ["python", "-c", "pass"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    def handler(
        method: str,
        url: str,
        body: dict[str, Any] | None,
        params: dict[str, str] | None,
    ) -> httpx.Response:
        assert method == "POST"
        assert url.endswith("/v1/projects/cpr_studio/syncs")
        assert "execute-local" not in url
        assert body is not None
        assert body["operationsPolicy"] == {"allowlisted": ["preview"]}
        return _response(
            method,
            url,
            200,
            {
                "id": "syn_1",
                "projectId": "cpr_studio",
                "status": "accepted",
                "discoveredAssetCount": 0,
                "repositoryRevision": "local",
                "manifestHash": body["manifestHash"],
                "operationsPolicyHash": "sha256:x",
            },
        )

    client = _FakeClient(handler)
    result = ProjectMcpService(tmp_path, http_client=client).sync()
    assert result["allowlisted"] == ["preview"]
    assert all("execute-local" not in url for url in client.urls)


def test_install_up_uses_workspace_not_tool_args(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HYDRACEPT_API_KEY", "hapt_test")
    _bind_workspace(tmp_path)
    captured: dict[str, Any] = {}

    def fake_install(
        *,
        api: str,
        project_root: Path,
        token: str | None,
        project: str | None,
    ) -> ProjectUpServiceStatus:
        captured.update(
            {"api": api, "project": project, "token": token, "root": str(project_root)}
        )
        return ProjectUpServiceStatus(
            name="HydraceptProjectUp-test",
            installed=True,
            running=False,
            detail="ok",
        )

    monkeypatch.setattr("hydracept.mcp.project_mcp.install_project_up", fake_install)
    result = ProjectMcpService(tmp_path).install_up()
    assert result["installed"] is True
    assert captured["api"] == "https://api.example.com"
    assert captured["project"] == "cpr_studio"
    assert captured["token"] == "hapt_test"
