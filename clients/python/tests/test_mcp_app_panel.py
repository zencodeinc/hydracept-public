from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock

from hydracept.mcp.panel import APP_URI, create_apps, load_app_html

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_apps_resource_is_single_hydracept_panel() -> None:
    apps = create_apps()
    bindings = list(apps.resources())
    uris = [str(binding.resource.uri) for binding in bindings]
    assert uris == [APP_URI]
    html = load_app_html()
    mime = bindings[0].resource.mime_type or ""
    assert "text/html" in mime
    assert "Hydracept panel" in html
    for needle in (
        'id="prompt"',
        'id="references"',
        'id="width"',
        'id="height"',
        'id="quality"',
        'id="variantCount"',
        'id="transparent"',
        'id="sheet-enabled"',
        'id="sheet-rows"',
        'id="sheet-cols"',
        'id="brand-logo"',
        "hydracept_ui_poll_job",
        "hydracept_ui_artifact_preview",
        "hydracept_ui_submit_job",
        "hydracept_ui_download_artifact",
        'id="size-preset"',
        'id="output-dir"',
        'id="lightbox"',
        "availableDisplayModes",
        "autoResize: false",
        "Use in chat",
        "Download to folder",
        'id="again-btn"',
        "Generate another",
        "referenceImages",
        "hydracept_ui_quote",
        "Full size",
        'id="variant-seg"',
        'id="reference-drop"',
        'id="surface-root"',
        "project.connect",
        "capability.launch",
        "connection.resolve",
        "authorization.preflight",
        "job.progress",
        "artifact.review",
        "change.promote",
        "renderInteractionContract",
        "image.generate.v1",
        "json-editor",
        "typedOutput",
        "hydracept_ui_quote",
        "hydracept_ui_run",
        "hydracept_ui_connect_project",
        "hydracept_ui_connection_recheck",
        "hydracept_ui_approve_job",
        "hydracept_ui_reject_job",
        "hydracept_ui_select_variant",
        "hydracept_ui_promote",
        "hydracept_ui_cancel_job",
        "This Hydracept surface is not supported",
        "normalizeIncoming",
        "paintIncoming",
        "isToolFailure",
        "porkbunAgreementVersion",
        "isPrimaryAction",
        "jobIdOf",
        "jobFromSurface",
        "isSecretField",
        "useReviewedArtifact",
        "hydracept_get_receipt",
        "cancel-job",
        "TERMINAL_JOB_STATES",
        "isBenignNonSurface",
        "cancel-job-btn",
        "openLinkPayload",
        "scheduleConnectWaitPoll",
        "renderConnectWaiting",
        "Didn't open?",
    ):
        assert needle in html
    assert "sheet-controls" in html
    assert "<textarea" in html
    assert "applyDocumentTheme" in html or "applyHostStyleVariables" in html
    assert "data:image/png;base64," in html
    assert "I've completed setup" not in html
    assert "state.app.openLink(url)" not in html


def test_image_launch_html_is_not_a_json_editor() -> None:
    html = load_app_html()
    assert "sheet-controls" in html
    assert "textarea" in html
    assert html.count("<textarea") == 1


def test_panel_ordered_sources_exist() -> None:
    ui = Path(__file__).resolve().parents[1] / "hydracept" / "mcp" / "ui"
    for name in ("panel-core.js", "render-contract.js", "plugin-image-generate.js", "panel.js", "shell.html"):
        assert (ui / name).is_file()
    core = (ui / "panel-core.js").read_text(encoding="utf-8")
    assert "normalizeIncoming" in core
    assert "paintIncoming" in core
    assert "isToolFailure" in core
    assert "This Hydracept surface is not supported" in core
    start = core.index("function capabilityKeyOf")
    end = core.index("function showNotice")
    assert "state.capabilityKey" not in core[start:end]
    assert "function jobIdOf" in core
    assert "function isSecretField" in core
    assert "await state.app.openLink(payload)" in core
    assert "state.app.openLink(url)" not in core
    assert "function openLinkPayload" in core
    render = (ui / "render-contract.js").read_text(encoding="utf-8")
    assert "isPrimaryAction" in render
    assert "hydracept_get_receipt" in render
    assert 'action.id === "refresh"' in render
    assert "useReviewedArtifact" in render
    assert "scheduleConnectWaitPoll" in render
    assert "I've completed setup" not in render
    assert "Approve in your browser" in render
    plugin = (ui / "plugin-image-generate.js").read_text(encoding="utf-8")
    assert "hydracept_ui_quote" in plugin
    assert "hydracept_quote_capability" not in plugin


def test_ui_poll_uses_job_status_projection(monkeypatch) -> None:
    from hydracept.mcp.server import hydracept_ui_poll_job

    class _Client:
        def get_job(self, job_id: str) -> dict:
            return {
                "jobId": job_id,
                "status": "running",
                "receiptId": None,
                "primaryArtifactId": None,
            }

    monkeypatch.setattr("hydracept.mcp.server._client", lambda: _Client())
    result = hydracept_ui_poll_job("wfr_1")
    assert result["jobId"] == "wfr_1"
    assert result["state"] == "running"
    assert result["nextAction"] == "poll"


def test_ui_preview_returns_fixture_png(monkeypatch) -> None:
    from hydracept.mcp.server import hydracept_ui_artifact_preview

    monkeypatch.setattr(
        "hydracept.mcp.server._artifact_bytes",
        lambda job_id, artifact_id: (_PNG, "image/png"),
    )
    result = hydracept_ui_artifact_preview(jobId="wfr_1", artifactId="art_1")
    assert result["mediaType"] == "image/png"
    assert result["byteLength"] == len(_PNG)
    assert base64.b64decode(result["bytesBase64"]) == _PNG


def test_ui_preview_infers_artifact_when_omitted(monkeypatch) -> None:
    from hydracept.mcp.server import hydracept_ui_artifact_preview

    class _Client:
        def get_job(self, job_id: str) -> dict:
            return {
                "jobId": job_id,
                "artifacts": [{"artifactId": "art_inferred", "selected": True}],
            }

    monkeypatch.setattr("hydracept.mcp.server._client", lambda: _Client())
    monkeypatch.setattr(
        "hydracept.mcp.server._artifact_bytes",
        lambda job_id, artifact_id: (_PNG, "image/png") if artifact_id == "art_inferred" else (_PNG, "text/plain"),
    )
    result = hydracept_ui_artifact_preview(jobId="wfr_1")
    assert result["artifactId"] == "art_inferred"
    assert result["mediaType"] == "image/png"


def test_download_by_job_uses_primary(tmp_path: Path, monkeypatch) -> None:
    from hydracept.mcp.server import _download_artifact

    workspace = MagicMock(api_url="https://api.example", token="tok")
    monkeypatch.setattr("hydracept.mcp.server.require_ready_workspace", lambda root: workspace)
    monkeypatch.setattr("hydracept.mcp.server._project_root", lambda: tmp_path)

    class _Client:
        def get_job(self, job_id: str) -> dict:
            return {
                "jobId": job_id,
                "primaryArtifactId": "art_1",
                "artifacts": [{"artifactId": "art_1", "filename": "hero.png"}],
            }

    monkeypatch.setattr("hydracept.mcp.server._client", lambda: _Client())

    class _Stream:
        headers = {"content-type": "image/png"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_bytes(self):
            yield _PNG

    monkeypatch.setattr("hydracept.mcp.server.httpx.stream", lambda *a, **k: _Stream())
    monkeypatch.setattr("hydracept.mcp.server.raise_api_status", lambda response: None)
    result = _download_artifact("wfr_1", "", "", "")
    assert result["artifactId"] == "art_1"
    assert Path(result["path"]).name == "hero.png"
    assert Path(result["path"]).read_bytes() == _PNG


def test_download_without_primary_requires_selection(monkeypatch, tmp_path: Path) -> None:
    from hydracept.mcp.server import McpToolError, _download_artifact

    workspace = MagicMock(api_url="https://api.example", token="tok")
    monkeypatch.setattr("hydracept.mcp.server.require_ready_workspace", lambda root: workspace)
    monkeypatch.setattr("hydracept.mcp.server._project_root", lambda: tmp_path)

    class _Client:
        def get_job(self, job_id: str) -> dict:
            return {
                "jobId": job_id,
                "primaryArtifactId": None,
                "artifacts": [
                    {"artifactId": "art_a", "filename": "a.png"},
                    {"artifactId": "art_b", "filename": "b.png"},
                ],
            }

    monkeypatch.setattr("hydracept.mcp.server._client", lambda: _Client())
    try:
        _download_artifact("wfr_sheet", "", "", "")
        raise AssertionError("expected ARTIFACT_SELECTION_REQUIRED")
    except McpToolError as exc:
        assert exc.payload["code"] == "ARTIFACT_SELECTION_REQUIRED"
        assert exc.payload["nextAction"] == "select_artifact"


def test_download_infers_single_artifact_without_primary_field(tmp_path: Path, monkeypatch) -> None:
    from hydracept.mcp.server import _download_artifact

    workspace = MagicMock(api_url="https://api.example", token="tok")
    monkeypatch.setattr("hydracept.mcp.server.require_ready_workspace", lambda root: workspace)
    monkeypatch.setattr("hydracept.mcp.server._project_root", lambda: tmp_path)

    class _Client:
        def get_job(self, job_id: str) -> dict:
            return {
                "jobId": job_id,
                "primaryArtifactId": None,
                "artifacts": [{"artifactId": "art_only", "filename": "hero.png", "selected": True}],
            }

    monkeypatch.setattr("hydracept.mcp.server._client", lambda: _Client())

    class _Stream:
        headers = {"content-type": "image/png"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_bytes(self):
            yield _PNG

    monkeypatch.setattr("hydracept.mcp.server.httpx.stream", lambda *a, **k: _Stream())
    monkeypatch.setattr("hydracept.mcp.server.raise_api_status", lambda response: None)
    result = _download_artifact("wfr_1", "", "", "")
    assert result["artifactId"] == "art_only"
    assert Path(result["path"]).name == "hero.png"


def test_download_relative_output_dir(tmp_path: Path, monkeypatch) -> None:
    from hydracept.mcp.server import _download_artifact

    workspace = MagicMock(api_url="https://api.example", token="tok")
    monkeypatch.setattr("hydracept.mcp.server.require_ready_workspace", lambda root: workspace)
    monkeypatch.setattr("hydracept.mcp.server._project_root", lambda: tmp_path)

    class _Client:
        def get_job(self, job_id: str) -> dict:
            return {
                "jobId": job_id,
                "primaryArtifactId": "art_1",
                "artifacts": [{"artifactId": "art_1", "filename": "hero.png"}],
            }

    monkeypatch.setattr("hydracept.mcp.server._client", lambda: _Client())

    class _Stream:
        headers = {"content-type": "image/png"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_bytes(self):
            yield _PNG

    monkeypatch.setattr("hydracept.mcp.server.httpx.stream", lambda *a, **k: _Stream())
    monkeypatch.setattr("hydracept.mcp.server.raise_api_status", lambda response: None)
    result = _download_artifact("wfr_1", "art_1", "", "exports/out")
    target = Path(result["path"])
    assert target == tmp_path / "exports" / "out" / "hero.png"
    assert target.read_bytes() == _PNG


def test_panel_tools_are_callable_without_app_visibility() -> None:
    from hydracept.mcp.server import apps, server

    visibility = {}
    for binding, _uri in apps._tools:
        name = getattr(binding.fn, "__name__", "")
        visibility[name] = (binding.meta or {}).get("ui", {}).get("visibility")
    assert "hydracept_ui_submit_job" not in visibility
    assert "hydracept_ui_download_artifact" not in visibility
    assert "hydracept_ui_poll_job" not in visibility
    assert "hydracept_ui_artifact_preview" not in visibility
    assert "hydracept_ui_run" not in visibility
    assert visibility.get("hydracept_submit_job") is None
    tools = {tool.name: tool for tool in server._tool_manager.list_tools()}
    for name in (
        "hydracept_ui_submit_job",
        "hydracept_ui_run",
        "hydracept_ui_quote",
        "hydracept_ui_connect_project",
        "hydracept_ui_promote",
        "hydracept_ui_connection_recheck",
        "hydracept_ui_approve_job",
        "hydracept_ui_cancel_job",
    ):
        meta = tools[name].meta or {}
        assert meta.get("ui", {}).get("visibility") == ["app"]


def test_connect_promote_connection_wrappers_have_no_secret_arguments() -> None:
    import inspect

    from hydracept.mcp import server as server_mod

    secret_markers = ("secret", "apikey", "password", "token", "privatekey", "credential")
    for name in (
        "hydracept_ui_connect_project",
        "hydracept_ui_promote",
        "hydracept_ui_connection_recheck",
    ):
        params = inspect.signature(getattr(server_mod, name)).parameters
        joined = " ".join(params).lower()
        assert not any(marker in joined for marker in secret_markers)


def test_ui_run_dispatches_through_run_facade(monkeypatch) -> None:
    from hydracept.cli.run_facade import RunOutcome
    from hydracept.mcp.server import hydracept_ui_run
    from hydracept.run_result import RunResult

    captured: dict[str, object] = {}

    def fake_execute_run(root, capability, body, **kwargs):
        captured.update({"capability": capability, "body": body, **kwargs})
        return RunOutcome(
            result=RunResult(capability=capability, job_id="job_1", status="queued"),
            exit_code=0,
        )

    monkeypatch.setattr("hydracept.cli.run_facade.execute_run", fake_execute_run)
    monkeypatch.setattr("hydracept.mcp.server._project_root", lambda: Path("."))
    monkeypatch.setattr(
        "hydracept.mcp.interaction_hydration.attach_hydrated_interaction",
        lambda result, *a, **k: result,
    )
    result = hydracept_ui_run("text.translate.v1", {"input": {"text": "hi"}}, None, "")
    assert captured["capability"] == "text.translate.v1"
    assert captured["wait"] is False
    assert captured["persist"] is False
    assert result["jobId"] == "job_1"


def test_run_and_submit_attach_full_interaction(monkeypatch) -> None:
    from hydracept.cli.run_facade import RunOutcome
    from hydracept.mcp.server import hydracept_run, hydracept_ui_submit_job
    from hydracept.run_result import RunResult

    class _Client:
        def get_job(self, job_id: str) -> dict:
            return {
                "jobId": job_id,
                "status": "running",
                "capabilityKey": "text.translate.v1",
                "pollAfterSeconds": 4,
            }

        def submit_capability_job(self, capability_key: str, payload: dict) -> dict:
            return {
                "jobId": "job_submit",
                "status": "queued",
                "capabilityKey": capability_key,
            }

        def describe_capability(self, key: str) -> dict:
            return {"key": key}

    monkeypatch.setattr("hydracept.mcp.server._client", lambda: _Client())
    monkeypatch.setattr("hydracept.mcp.server._project_root", lambda: Path("."))
    monkeypatch.setattr(
        "hydracept.mcp.server._execution_workspace",
        lambda: type("W", (), {"api_url": "https://api.example", "token": "tok"})(),
    )
    monkeypatch.setattr(
        "hydracept.mcp.server.merge_workspace_job_context",
        lambda body, workspace: dict(body or {}),
    )
    monkeypatch.setattr(
        "hydracept.mcp.server.HydraceptClient",
        lambda *a, **k: _Client(),
    )

    def fake_execute_run(root, capability, body, **kwargs):
        return RunOutcome(
            result=RunResult(capability=capability, job_id="job_run", status="running"),
            exit_code=0,
        )

    monkeypatch.setattr("hydracept.cli.run_facade.execute_run", fake_execute_run)
    run_result = hydracept_run("text.translate.v1", {"input": {"text": "hi"}}, False, None, None, "", "")
    assert run_result["interaction"]["schemaVersion"] == "hydracept.interaction.v1"
    assert run_result["interaction"]["surface"] == "job.progress"
    assert run_result["interaction"]["title"]
    assert run_result["interaction"]["data"]["jobId"] == "job_run"

    submitted = hydracept_ui_submit_job("text.translate.v1", {"input": {"text": "hi"}}, "")
    assert submitted["interaction"]["schemaVersion"] == "hydracept.interaction.v1"
    assert submitted["interaction"]["data"]["jobId"] == "job_submit"


def test_ui_connect_forwards_environment(monkeypatch, tmp_path: Path) -> None:
    from hydracept.cli.init_resolver import InitResult
    from hydracept.mcp.server import hydracept_ui_connect_project

    captured: dict[str, object] = {}

    def fake_init(root, **kwargs):
        captured.update(kwargs)
        return InitResult(exit_code=0, payload={"status": "ready"})

    monkeypatch.setattr("hydracept.cli.init_resolver.run_init", fake_init)
    monkeypatch.setattr("hydracept.mcp.server._project_root", lambda: tmp_path)
    monkeypatch.setattr(
        "hydracept.mcp.interaction_hydration.attach_hydrated_interaction",
        lambda result, *a, **k: result,
    )
    hydracept_ui_connect_project(displayName="Arena", environment="staging")
    assert captured["project_name"] == "Arena"
    assert captured["environment"] == "staging"
    assert captured["wait"] is False
    assert captured["apply"] is True


def test_ui_approve_and_reject_and_variant(monkeypatch) -> None:
    from hydracept.mcp.server import (
        hydracept_ui_approve_job,
        hydracept_ui_reject_job,
        hydracept_ui_select_variant,
    )

    calls: list[tuple[str, object]] = []

    class _Client:
        def approve_job(self, job_id, body=None):
            calls.append(("approve", job_id, body))
            return {"jobId": job_id, "status": "running"}

        def reject_job(self, job_id):
            calls.append(("reject", job_id))
            return {"jobId": job_id, "status": "canceled"}

        def select_job_variant(self, job_id, artifact_id):
            calls.append(("select", job_id, artifact_id))
            return {"jobId": job_id, "primaryArtifactId": artifact_id}

        def get_job(self, job_id):
            return {"jobId": job_id, "status": "succeeded"}

    monkeypatch.setattr("hydracept.mcp.server._client", lambda: _Client())
    monkeypatch.setattr("hydracept.mcp.server._project_root", lambda: Path("."))
    monkeypatch.setattr(
        "hydracept.mcp.interaction_hydration.attach_hydrated_interaction",
        lambda result, *a, **k: result,
    )
    hydracept_ui_approve_job("job_a", {"domain": "example.com", "agreementVersion": "4.1"})
    hydracept_ui_reject_job("job_b")
    hydracept_ui_select_variant("job_c", "art_1")
    assert calls[0][0] == "approve"
    assert calls[0][1] == "job_a"
    assert calls[0][2]["domain"] == "example.com"
    assert calls[0][2]["porkbunAgreementVersion"] == "4.1"
    assert calls[0][2]["agreeToPorkbunRegistrationAgreement"] is True
    assert "agreementVersion" not in calls[0][2]
    assert calls[1] == ("reject", "job_b")
    assert calls[2] == ("select", "job_c", "art_1")


def test_normalize_job_approve_body_maps_prompt_keys() -> None:
    from hydracept.mcp.server import _normalize_job_approve_body

    body = _normalize_job_approve_body(
        {
            "quote": {"domain": "example.com", "firstYearPriceUsd": 10.99},
            "prompt": {"agreementVersion": "4.1", "title": "Register example.com"},
            "require": ["human_approval"],
        }
    )
    assert body == {
        "domain": "example.com",
        "firstYearPriceUsd": 10.99,
        "porkbunAgreementVersion": "4.1",
        "agreeToPorkbunRegistrationAgreement": True,
    }


def test_ui_promote_path_only(monkeypatch, tmp_path: Path) -> None:
    from hydracept.mcp.server import hydracept_ui_promote

    captured: list[str] = []

    class _Service:
        def __init__(self, root):
            self.root = root

        def apply_surfaces(self, path=""):
            captured.append(path)
            return {"applied": [path]}

    monkeypatch.setattr("hydracept.mcp.server._project_root", lambda: tmp_path)
    monkeypatch.setattr("hydracept.mcp.project_mcp.ProjectMcpService", _Service)
    result = hydracept_ui_promote("tools/hydracept/surfaces/hero.json")
    assert captured == ["tools/hydracept/surfaces/hero.json"]
    assert "does not write this repository" in result["note"]


def test_stop_watching_is_not_cancel() -> None:
    html = load_app_html()
    assert "Stop watching" in html
    assert "hydracept_ui_cancel_job" in html
    assert "does not cancel" in html
    assert 'id="cancel-job-btn"' in html
