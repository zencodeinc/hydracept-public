"""Public project-agent loop: sync authority, watch and execute locally."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

from hydracept.cli.project_agent import (
    ProjectAgentError,
    _parse_tool_stdout,
    build_sync_payload,
    operations_policy_from_manifest,
    run_named_operation,
)
from hydracept.cli.project_cmd import _sync_project, _watch_once


def _write_project(root: Path, *, allowlisted: bool = True) -> Path:
    hydra = root / "tools" / "hydracept"
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
                "  allowedWriteRoots:",
                "    - content/images",
                "  dirtyTreePolicy: reject-conflicting",
                "validation:",
                "  commands: []",
                "",
            ]
        ),
        encoding="utf-8",
    )
    helper = root / "preview.py"
    helper.write_text(
        "import json\n"
        "print(json.dumps({"
        '"status": "succeeded",'
        '"message": "Preview ROB",'
        '"details": {"statusFields": [{"label": "Word", "value": "ROB"}]}'
        "}))\n",
        encoding="utf-8",
    )
    (hydra / "manifest.json").write_text(
        json.dumps(
            {
                "operations": {
                    "preview": {
                        "command": "preview",
                        "allowlisted": allowlisted,
                        "argv": [sys.executable, str(helper)],
                    },
                    "findPlayableWord": {
                        "command": "findPlayableWord",
                        "allowlisted": False,
                        "argv": [sys.executable, str(helper)],
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return root


class _FakeClient:
    def __init__(self, handler: Any) -> None:
        self._handler = handler

    def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        return self._handler("GET", url, None, params)

    def post(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        return self._handler("POST", url, json, None)


def _response(method: str, url: str, status: int, payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(status, json=payload, request=httpx.Request(method, url))


def test_sync_payload_binds_hydracept_project_and_strips_argv(tmp_path: Path) -> None:
    root = _write_project(tmp_path)
    payload = build_sync_payload(root, hydracept_project_id="cpr_studio")
    assert payload["manifest"]["projectId"] == "cpr_studio"
    assert payload["localProjectSlug"] == "knights-of-lex"
    assert payload["operationsPolicy"] == {"allowlisted": ["preview"]}
    assert "argv" not in json.dumps(payload["operationsPolicy"])
    assert payload["assets"] == []


def test_missing_manifest_syncs_empty_allowlist(tmp_path: Path) -> None:
    hydra = tmp_path / "tools" / "hydracept"
    hydra.mkdir(parents=True)
    (hydra / "project.yaml").write_text(
        "\n".join(
            [
                "schemaVersion: hydracept.project.v1",
                "projectId: demo",
                "displayName: Demo",
                "adapter:",
                "  protocolVersion: 1",
                "  entrypoint: tools/hydracept",
                "repository:",
                "  allowedWriteRoots: []",
                "  dirtyTreePolicy: reject-conflicting",
                "",
            ]
        ),
        encoding="utf-8",
    )
    assert operations_policy_from_manifest(tmp_path) == {"allowlisted": []}


def test_local_agent_refuses_non_allowlisted(tmp_path: Path) -> None:
    root = _write_project(tmp_path)
    with pytest.raises(ProjectAgentError, match="does not implement"):
        run_named_operation(root, "findPlayableWord", {})


def test_local_agent_runs_allowlisted_argv(tmp_path: Path) -> None:
    root = _write_project(tmp_path)
    payload = run_named_operation(root, "preview", {})
    assert payload["status"] == "succeeded"
    assert payload["message"] == "Preview ROB"
    assert payload["statusFields"][0]["value"] == "ROB"


def test_sync_posts_bound_project_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HYDRACEPT_API_KEY", "hapt_test")
    root = _write_project(tmp_path)
    posted: dict[str, Any] = {}

    def handler(
        method: str,
        url: str,
        body: dict[str, Any] | None,
        params: dict[str, str] | None,
    ) -> httpx.Response:
        assert method == "POST"
        assert url.endswith("/v1/projects/cpr_studio/syncs")
        assert body is not None
        posted.update(body)
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

    result = _sync_project(
        api="https://api.example.com",
        project_root=root,
        token=None,
        project="cpr_studio",
        http_client=_FakeClient(handler),
    )
    assert result["projectId"] == "cpr_studio"
    assert result["allowlisted"] == ["preview"]
    assert posted["manifest"]["projectId"] == "cpr_studio"
    assert posted["operationsPolicy"] == {"allowlisted": ["preview"]}


def test_watch_reports_allowlisted_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HYDRACEPT_API_KEY", "hapt_test")
    root = _write_project(tmp_path)
    reports: list[dict[str, Any]] = []

    def handler(
        method: str,
        url: str,
        body: dict[str, Any] | None,
        params: dict[str, str] | None,
    ) -> httpx.Response:
        if method == "GET":
            assert params == {"status": "requested"}
            return _response(
                method,
                url,
                200,
                {
                    "items": [
                        {
                            "id": "pop_1",
                            "projectId": "cpr_studio",
                            "command": "preview",
                            "status": "requested",
                            "input": {},
                        }
                    ],
                    "total": 1,
                },
            )
        if url.endswith("/agent-heartbeat"):
            return _response(method, url, 200, {"connected": True})
        assert method == "POST"
        assert url.endswith("/operations/pop_1/report")
        assert body is not None
        reports.append(body)
        return _response(
            method,
            url,
            200,
            {"id": "pop_1", "status": "reported", "result": body},
        )

    result = _watch_once(
        api="https://api.example.com",
        project_root=root,
        token=None,
        project="cpr_studio",
        http_client=_FakeClient(handler),
    )
    assert result[0]["status"] == "succeeded"
    assert reports[0]["kind"] == "preview"
    assert reports[0]["statusFields"][0]["value"] == "ROB"
    assert reports[0]["metrics"]["statusFields"][0]["label"] == "Word"


def test_parse_kol_shaped_stdout_keeps_status_fields() -> None:
    stdout = json.dumps(
        {
            "status": [{"label": "Word", "value": "ROB"}, {"label": "HP", "value": "12"}],
            "lastResult": {
                "status": "succeeded",
                "message": "Preview ROB (RNG unchanged)",
                "details": {
                    "statusFields": [
                        {"label": "Word", "value": "ROB"},
                        {"label": "HP", "value": "12"},
                    ],
                    "status": [
                        {"label": "Word", "value": "ROB"},
                        {"label": "HP", "value": "12"},
                    ],
                },
            },
        }
    )
    payload = _parse_tool_stdout(stdout)
    assert payload["status"] == "succeeded"
    assert payload["message"] == "Preview ROB (RNG unchanged)"
    assert payload["statusFields"][0]["value"] == "ROB"
    assert payload["statusFields"][1]["label"] == "HP"
