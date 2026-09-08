from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hydracept.mcp.interaction_hydration import hydrate_interaction_surface


class _Client:
    def __init__(self) -> None:
        self.described: list[str] = []
        self.quoted: list[tuple[str, dict[str, Any]]] = []
        self.jobs: dict[str, dict[str, Any]] = {}
        self.mutated = False

    def describe_capability(self, key: str) -> dict[str, Any]:
        self.described.append(key)
        if key == "text.translate.v1":
            return {
                "key": key,
                "title": "Translation",
                "description": "Translate text",
                "inputSchema": {
                    "type": "object",
                    "required": ["text"],
                    "properties": {
                        "text": {"type": "string"},
                        "glossary": {"type": "object"},
                    },
                },
                "uiSchema": {"glossary": {"widget": "json"}},
                "executionModes": ["invoke"],
                "estimateAvailable": True,
                "pricing": {"billable": True},
                "workspaceRunnable": {"runnable": True, "connectUrl": "https://studio.example/connections?x=1"},
                "approvalRequirements": {"requiresHumanApproval": False},
            }
        if key == "domain.register.v1":
            return {
                "key": key,
                "approvalRequirements": {
                    "requiresHumanApproval": True,
                    "irreversibleEffects": ["creates_registered_domain"],
                },
                "workspaceRunnable": {
                    "runnable": False,
                    "connectUrl": "https://studio.example/connections?exact=1",
                    "status": "missing",
                },
            }
        return {"key": key, "inputSchema": {"type": "object", "properties": {}}}

    def quote_capability(self, key: str, body: dict[str, Any]) -> dict[str, Any]:
        self.quoted.append((key, body))
        return {
            "pricing": {
                "quote": {"customerTotal": {"display": "$1.29", "amountMicros": 1_290_000}}
            }
        }

    def get_job(self, job_id: str) -> dict[str, Any]:
        return dict(self.jobs[job_id])


def test_connect_hydration_does_not_fill_identity_from_binding(tmp_path: Path, monkeypatch: Any) -> None:
    from hydracept.cli import project as project_mod
    from hydracept.cli.workspace_fingerprint import workspace_fingerprint

    writes: list[Any] = []
    monkeypatch.setattr(project_mod, "write_project_binding", lambda *a, **k: writes.append(a))
    (tmp_path / ".hydracept").mkdir()
    binding = {
        "schemaVersion": "hydracept.workspace.v1",
        "projectId": "cpr_1",
        "environment": "staging",
        "projectName": "Arena",
    }
    (tmp_path / ".hydracept" / "project.json").write_text(
        json.dumps(binding) + "\n",
        encoding="utf-8",
    )
    fingerprint = workspace_fingerprint(tmp_path, binding)
    surface = hydrate_interaction_surface(
        "project.connect",
        {
            "projectId": "cpr_1",
            "displayName": "Arena",
            "environment": "staging",
            "fingerprint": fingerprint,
        },
        project_root=tmp_path,
        client=_Client(),
    )
    fields = {field["name"]: field for field in surface["fields"]}
    assert fields["projectId"]["value"] == "cpr_1"
    assert fields["displayName"]["value"] == "Arena"
    assert fields["environment"]["value"] == "staging"
    assert not writes


def test_connect_hydration_rejects_workspace_fingerprint_mismatch(tmp_path: Path) -> None:
    (tmp_path / ".hydracept").mkdir()
    binding = {
        "schemaVersion": "hydracept.workspace.v1",
        "projectId": "cpr_1",
        "environment": "development",
        "projectName": "Arena",
    }
    (tmp_path / ".hydracept" / "project.json").write_text(
        json.dumps(binding) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="WORKSPACE_CONTEXT_MISMATCH"):
        hydrate_interaction_surface(
            "project.connect",
            {"fingerprint": "wsf_deadbeef"},
            project_root=tmp_path,
            client=_Client(),
        )


def test_launch_hydrates_descriptor_and_ui_schema() -> None:
    client = _Client()
    surface = hydrate_interaction_surface(
        "capability.launch",
        {"capabilityKey": "text.translate.v1"},
        client=client,
    )
    assert client.described == ["text.translate.v1"]
    assert surface["data"]["inputSchema"]["properties"]["glossary"]["type"] == "object"
    assert surface["data"]["uiSchema"]["glossary"]["widget"] == "json"
    assert surface["data"]["executionModes"] == ["invoke"]
    assert surface["data"]["workspaceRunnable"]["runnable"] is True


def test_connection_uses_exact_connect_url() -> None:
    client = _Client()
    surface = hydrate_interaction_surface(
        "connection.resolve",
        {"capabilityKey": "domain.register.v1"},
        client=client,
    )
    assert surface["data"]["connectUrl"] == "https://studio.example/connections?exact=1"
    assert surface["data"]["acceptsSecrets"] is False


def test_preflight_quote_does_not_invent_human_approval() -> None:
    client = _Client()
    surface = hydrate_interaction_surface(
        "authorization.preflight",
        {"capabilityKey": "text.translate.v1", "request": {"input": {"text": "hi"}}},
        client=client,
    )
    assert surface["risk"]["needsAuthorization"] is False
    assert surface["actions"][0]["id"] == "continue"
    assert client.quoted


def test_preflight_domain_job_uses_server_approval() -> None:
    client = _Client()
    client.jobs["job_d"] = {
        "jobId": "job_d",
        "capabilityKey": "domain.register.v1",
        "status": "awaiting_approval",
        "approval": {
            "kind": "external_domain_purchase",
            "quote": {"domain": "example.com", "firstYearPriceUsd": 10.37},
            "requiredFields": ["domain"],
        },
    }
    surface = hydrate_interaction_surface(
        "authorization.preflight",
        {"jobId": "job_d"},
        client=client,
    )
    assert surface["data"]["approval"]["kind"] == "external_domain_purchase"
    assert surface["data"]["approval"]["quote"]["domain"] == "example.com"
    assert surface["actions"][0]["id"] == "authorize"


def test_progress_and_review_job_id_only() -> None:
    client = _Client()
    client.jobs["job_r"] = {
        "jobId": "job_r",
        "capabilityKey": "text.translate.v1",
        "status": "succeeded",
        "typedOutput": {"text": "bonjour"},
        "artifacts": [],
    }
    progress = hydrate_interaction_surface("job.progress", {"jobId": "job_r"}, client=client)
    review = hydrate_interaction_surface("artifact.review", {"jobId": "job_r"}, client=client)
    assert progress["data"]["jobId"] == "job_r"
    assert progress["data"]["capabilityKey"] == "text.translate.v1"
    assert progress["data"]["status"] == "succeeded"
    assert progress["actions"][1]["id"] == "receipt"
    assert review["data"]["typedOutput"] == {"text": "bonjour"}
    assert review["data"]["jobId"] == "job_r"
    assert review["data"]["capabilityKey"] == "text.translate.v1"


def test_review_variants_do_not_advertise_domain_approve() -> None:
    client = _Client()
    client.jobs["job_v"] = {
        "jobId": "job_v",
        "status": "succeeded",
        "artifacts": [
            {"artifactId": "a", "filename": "a.png"},
            {"artifactId": "b", "filename": "b.png"},
        ],
        "variantSet": {"requestedCount": 2, "completedCount": 2, "failedCount": 0},
    }
    review = hydrate_interaction_surface("artifact.review", {"jobId": "job_v"}, client=client)
    assert review["actions"][0]["id"] == "select"
    assert all(action["id"] != "approve" for action in review["actions"])


def test_promote_enumerates_paths_and_does_not_materialize_writes(tmp_path: Path) -> None:
    folder = tmp_path / "tools" / "hydracept" / "surfaces"
    folder.mkdir(parents=True)
    (folder / "hero.json").write_text("{}", encoding="utf-8")
    surface = hydrate_interaction_surface(
        "change.promote",
        {"changes": ["Assets/hero.png"]},
        project_root=tmp_path,
    )
    assert surface["data"]["surfacePaths"] == ["tools/hydracept/surfaces/hero.json"]
    assert surface["data"]["changes"] == ["Assets/hero.png"]
    assert surface["data"]["authority"] == "project-local-agent"
    assert surface["data"]["promoteEnabled"] is True
    fields = {field["name"]: field for field in surface["fields"]}
    assert fields["surfacePath"]["value"] == "tools/hydracept/surfaces/hero.json"
    assert fields["surfacePath"]["readOnly"] is True


def test_promote_disabled_without_local_workspace() -> None:
    surface = hydrate_interaction_surface("change.promote", {}, project_root=None)
    assert surface["data"]["promoteEnabled"] is False
    assert surface["data"]["centralServiceWritesRepository"] is False


def test_failed_job_error_object_still_hydrates() -> None:
    from hydracept.mcp.interaction_hydration import attach_hydrated_interaction

    attached = attach_hydrated_interaction(
        {
            "jobId": "job_fail",
            "status": "failed",
            "capabilityKey": "text.translate.v1",
            "error": {"code": "provider_error", "message": "upstream failed"},
        },
        "job.progress",
    )
    assert attached["surface"] == "job.progress"
    assert attached["interaction"]["surface"] == "job.progress"
    assert attached["error"]["message"] == "upstream failed"


def test_boolean_tool_error_skips_hydration() -> None:
    from hydracept.mcp.interaction_hydration import attach_hydrated_interaction
    from hydracept.mcp.panel import attach_interaction

    payload = {"isError": True, "error": True, "message": "tool failed"}
    assert attach_hydrated_interaction(payload, "job.progress") is payload
    assert attach_interaction(payload, "job.progress") is payload
    assert "interaction" not in payload


def test_connect_interaction_required_preserves_exact_url(tmp_path: Path) -> None:
    from hydracept.mcp.interaction_hydration import attach_hydrated_interaction

    url = "https://api.hydracept.com/connect?bootstrapSessionId=sess_exact&token=verbatim"
    attached = attach_hydrated_interaction(
        {
            "status": "interaction_required",
            "reason": "authentication",
            "detail": "Open the connect URL",
            "action": {"type": "open_url", "url": url},
        },
        "project.connect",
        project_root=tmp_path,
        client=None,
    )
    assert attached["status"] == "interaction_required"
    assert attached["action"]["url"] == url
    assert attached["interaction"]["data"]["action"]["url"] == url
    assert attached["interaction"]["data"]["actionUrl"] == url
    assert attached["surface"] == "project.connect"
