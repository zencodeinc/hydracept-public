"""Tests for 0.3.11 consumer-trust client modules."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from hydracept.cli.artifact_output import ArtifactOutputError, resolve_artifact_output
from hydracept.cli.installed_workspace import (
    InstalledWorkspaceStatus,
    validate_installed_workspace,
)
from hydracept.cli.init_resolver import run_init
from hydracept.cli.workspace_fingerprint import workspace_fingerprint


class _FakeResponse:
    def __init__(self, payload: dict | None = None, status_code: int = 200) -> None:
        self._payload = payload or {}
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload


def _write_installed_workspace(
    tmp_path: Path,
    *,
    project_id: str = "cpr_installed",
    api_key: str = "hydracept_installed_key",
) -> None:
    (tmp_path / ".hydracept").mkdir()
    (tmp_path / ".hydracept" / "project.json").write_text(
        json.dumps(
            {
                "schemaVersion": "hydracept.workspace.v1",
                "projectId": project_id,
                "environment": "development",
                "projectName": "Installed",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / ".hydracept" / "secrets.json").write_text(
        json.dumps({"apiKey": api_key, "kind": "api_key", "schemaVersion": 2}) + "\n",
        encoding="utf-8",
    )


def test_validate_installed_workspace_not_installed(tmp_path: Path) -> None:
    result = validate_installed_workspace(tmp_path)
    assert result.status == InstalledWorkspaceStatus.NOT_INSTALLED


def test_validate_installed_workspace_invalid_binding(tmp_path: Path) -> None:
    (tmp_path / ".hydracept").mkdir()
    (tmp_path / ".hydracept" / "project.json").write_text("{not-json", encoding="utf-8")
    result = validate_installed_workspace(tmp_path)
    assert result.status == InstalledWorkspaceStatus.INVALID_LOCAL_BINDING


def test_validate_installed_workspace_remote_valid(tmp_path: Path) -> None:
    _write_installed_workspace(tmp_path)

    def fake_get(url: str, **kwargs) -> _FakeResponse:
        if url.endswith("/v1/diagnostics/session"):
            return _FakeResponse(
                {
                    "projectId": "cpr_installed",
                    "tokenProjectId": "cpr_installed",
                    "principalId": "usr_1",
                }
            )
        if url.endswith("/v1/session/context"):
            return _FakeResponse({"project": {"id": "cpr_home"}})
        raise AssertionError(url)

    with patch("hydracept.cli.installed_workspace.httpx.get", side_effect=fake_get):
        result = validate_installed_workspace(tmp_path)

    assert result.status == InstalledWorkspaceStatus.INSTALLED_VALID
    assert result.project_id == "cpr_installed"
    assert result.token == "hydracept_installed_key"


def test_validate_installed_workspace_credential_invalid(tmp_path: Path) -> None:
    _write_installed_workspace(tmp_path)

    with patch(
        "hydracept.cli.installed_workspace.httpx.get",
        return_value=_FakeResponse(status_code=401),
    ):
        result = validate_installed_workspace(tmp_path)

    assert result.status == InstalledWorkspaceStatus.CREDENTIAL_INVALID


def test_validate_installed_workspace_network_failure(tmp_path: Path) -> None:
    _write_installed_workspace(tmp_path)

    with patch(
        "hydracept.cli.installed_workspace.httpx.get",
        side_effect=httpx.ConnectError("offline"),
    ):
        result = validate_installed_workspace(tmp_path)

    assert result.status == InstalledWorkspaceStatus.VALIDATION_UNAVAILABLE


def test_validate_installed_workspace_project_mismatch(tmp_path: Path) -> None:
    _write_installed_workspace(tmp_path)

    def fake_get(url: str, **kwargs) -> _FakeResponse:
        if url.endswith("/v1/diagnostics/session"):
            return _FakeResponse(
                {
                    "projectId": "cpr_other",
                    "tokenProjectId": "cpr_other",
                    "principalId": "usr_1",
                }
            )
        if url.endswith("/v1/session/context"):
            return _FakeResponse({"project": {"id": "cpr_home"}})
        raise AssertionError(url)

    with patch("hydracept.cli.installed_workspace.httpx.get", side_effect=fake_get):
        result = validate_installed_workspace(tmp_path)

    assert result.status == InstalledWorkspaceStatus.PROJECT_CREDENTIAL_MISMATCH


def test_workspace_fingerprint_is_opaque_and_stable(tmp_path: Path) -> None:
    binding = {"projectId": "cpr_abc", "projectName": "Demo"}
    first = workspace_fingerprint(tmp_path, binding)
    second = workspace_fingerprint(tmp_path, binding)
    assert first == second
    assert first.startswith("wsf_")
    assert str(tmp_path) not in first


def test_workspace_fingerprint_uses_folder_identity_without_project(tmp_path: Path) -> None:
    demo = tmp_path / "Hydratest22"
    demo.mkdir()
    fp = workspace_fingerprint(demo, {})
    assert fp.startswith("wsf_")


def test_resolve_artifact_output_defaults_to_job_directory(tmp_path: Path) -> None:
    dest = resolve_artifact_output(tmp_path, None, "sprite.png", 1, job_id="wfr_1")
    assert dest == (tmp_path / ".hydracept" / "output" / "wfr_1").resolve()


def test_finalize_single_artifact_path_appends_filename_to_job_directory(tmp_path: Path) -> None:
    from hydracept.cli.artifact_output import finalize_single_artifact_path

    base = resolve_artifact_output(tmp_path, None, "sprite.png", 1, job_id="wfr_1")
    dest = finalize_single_artifact_path(base, "sprite.png")
    assert dest == (tmp_path / ".hydracept" / "output" / "wfr_1" / "sprite.png").resolve()


def test_resolve_artifact_output_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(ArtifactOutputError) as exc:
        resolve_artifact_output(tmp_path, "../outside.png", "sprite.png", 1)
    assert exc.value.code == "ARTIFACT_OUTPUT_TRAVERSAL"


def test_resolve_artifact_output_single_file_target(tmp_path: Path) -> None:
    dest = resolve_artifact_output(tmp_path, "assets/out.png", "sprite.png", 1)
    assert dest == (tmp_path / "assets" / "out.png").resolve()


def test_resolve_artifact_output_rejects_file_target_for_many_artifacts(tmp_path: Path) -> None:
    with pytest.raises(ArtifactOutputError) as exc:
        resolve_artifact_output(tmp_path, "assets/out.png", "sprite.png", 2)
    assert exc.value.code == "ARTIFACT_OUTPUT_FILE_WITH_MULTIPLE_ARTIFACTS"


def test_run_init_installed_valid_skips_browser(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_installed_workspace(tmp_path)
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.setattr("hydracept.cli.init_resolver.load_session", lambda: None)

    def fake_get(url: str, **kwargs) -> _FakeResponse:
        if url.endswith("/v1/diagnostics/session"):
            return _FakeResponse(
                {
                    "projectId": "cpr_installed",
                    "tokenProjectId": "cpr_installed",
                    "principalId": "usr_1",
                }
            )
        if url.endswith("/v1/session/context"):
            return _FakeResponse({"project": {"id": "cpr_home"}})
        if "/v1/diagnostics/readiness" in url:
            return _FakeResponse({"providers": {}, "capabilities": {}})
        raise AssertionError(url)

    with patch("hydracept.cli.installed_workspace.httpx.get", side_effect=fake_get):
        with patch("hydracept.cli.init_resolver.httpx.get", side_effect=fake_get):
            with patch("hydracept.cli.init_resolver.build_doctor_report", return_value={}):
                with patch("hydracept.cli.init_resolver.doctor_exit_code", return_value=0):
                    with patch("hydracept.cli.init_resolver.run_configure"):
                        result = run_init(tmp_path, apply=True, yes=True, json_output=True)

    assert result.payload["status"] == "ready"
    assert result.payload["installation"]["action"] == "reused"


def test_run_init_validation_unavailable_is_retryable_not_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_installed_workspace(tmp_path)
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.setattr("hydracept.cli.init_resolver.load_session", lambda: None)

    with patch(
        "hydracept.cli.installed_workspace.httpx.get",
        side_effect=httpx.ConnectError("offline"),
    ):
        result = run_init(tmp_path, apply=True, yes=True, json_output=True)

    assert result.payload["status"] == "configuration_required"
    assert result.payload["reason"] == "validation_unavailable"
    assert result.payload.get("retryable") is True
