"""End-to-end interaction presentation contract."""

from __future__ import annotations

import asyncio
from typing import Any

from hydracept.mcp import interactions
from hydracept.mcp.presentation import presentation_for_host
from hydracept.mcp.interaction_hydration import attach_hydrated_interaction


def _apps_ctx() -> Any:
    from types import SimpleNamespace

    from mcp.server.apps import APP_MIME_TYPE, EXTENSION_ID

    return SimpleNamespace(
        client_capabilities=SimpleNamespace(
            extensions={EXTENSION_ID: {"mimeTypes": [APP_MIME_TYPE]}},
            elicitation=SimpleNamespace(form=True, url=None),
        ),
        protocol_version="2026-07-28",
        input_responses={},
    )


def _plain_ctx() -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(
        client_capabilities=SimpleNamespace(extensions={}, elicitation=None),
        protocol_version="2025-01-01",
        input_responses={},
    )


def _server() -> Any:
    class FakeServer:
        def __init__(self) -> None:
            self.tools: dict[str, Any] = {}

        def tool(self):
            def register(fn):
                self.tools[fn.__name__] = fn
                return fn

            return register

    server = FakeServer()
    interactions.register_interaction_tools(server)
    return server


def test_apps_host_returns_mounted_presentation() -> None:
    result = asyncio.run(
        _server().tools["hydracept_interaction_surface"](
            _apps_ctx(),
            "project.connect",
            {"projectId": "cpr_1", "displayName": "Arena"},
            True,
        )
    )
    presentation = result["presentation"]
    assert presentation["status"] == "mounted"
    assert presentation["appUri"] == "ui://hydracept/app.html"
    assert presentation["agentAction"] == "present_and_yield"
    assert presentation["blocking"] is True
    assert "fallback" not in presentation


def test_unsupported_host_returns_explicit_fallback() -> None:
    result = asyncio.run(
        _server().tools["hydracept_interaction_surface"](
            _plain_ctx(),
            "project.connect",
            {"projectId": "cpr_1"},
            True,
        )
    )
    presentation = result["presentation"]
    assert presentation["status"] == "fallback"
    assert presentation["reason"] == "host_does_not_support_apps"
    assert presentation["fallback"]["kind"] == "structured_contract"
    assert result["fields"]


def test_smoke_user_intent_does_not_require_confirmation() -> None:
    surface = interactions.authorization_preflight_surface(
        {
            "capabilityKey": "image.generate.v1",
            "estimatedCostDisplay": "~$0.05",
            "userRequestedExecution": True,
            "smoke": True,
        }
    )
    assert surface["authorization"]["confirmationRequired"] is False
    assert surface["authorization"]["status"] == "already_authorized_by_user_intent"
    assert surface["actions"][0]["id"] == "continue"


def test_policy_cost_and_irreversible_require_confirmation() -> None:
    surface = interactions.authorization_preflight_surface(
        {
            "capability": {
                "key": "domain.register.v1",
                "approvalRequirements": {
                    "requiresHumanApproval": True,
                    "irreversibleEffects": ["creates_registered_domain"],
                    "maxEstimatedCostCents": 100,
                },
            },
            "estimatedCostCents": 1299,
            "userRequestedExecution": True,
        }
    )
    assert surface["authorization"]["confirmationRequired"] is True
    assert surface["actions"][0]["id"] == "authorize"


def test_job_result_attaches_artifact_review_presentation() -> None:
    attached = attach_hydrated_interaction(
        {
            "jobId": "job_ok",
            "status": "succeeded",
            "capabilityKey": "image.generate.v1",
            "artifacts": [{"artifactId": "art_1", "mediaType": "image/png"}],
        }
    )
    assert attached["surface"] == "artifact.review"
    assert attached["presentation"]["surface"] == "artifact.review"
    assert attached["presentation"]["status"] == "mount_requested"
    assert attached["presentation"]["preferred"] is True
    assert attached["presentation"].get("hostConfirmation") is None
    assert attached["presentation"]["context"]["artifactId"] == "art_1"


def test_awaiting_approval_job_owns_blocking_preflight() -> None:
    attached = attach_hydrated_interaction(
        {
            "jobId": "job_wait",
            "status": "awaiting_approval",
            "capabilityKey": "domain.register.v1",
        }
    )
    assert attached["surface"] == "authorization.preflight"
    assert attached["presentation"]["surface"] == "authorization.preflight"
    assert attached["presentation"]["blocking"] is True
    assert attached["presentation"]["agentAction"] == "present_and_yield"


def test_present_and_yield_is_structured_not_prose_only() -> None:
    payload = presentation_for_host(
        "project.connect",
        apps_supported=True,
        confirmation_required=True,
    )
    assert payload["agentAction"] == "present_and_yield"
    assert payload["status"] == "mounted"


def test_init_style_presentation_does_not_claim_mount() -> None:
    payload = presentation_for_host(
        "project.connect",
        apps_supported=True,
        confirmation_required=True,
        status="mount_requested",
    )
    assert payload["status"] == "mount_requested"
    assert payload["agentAction"] == "present_and_yield"
    assert payload.get("hostConfirmation") is None


def test_stale_progress_interaction_advances_to_artifact_review() -> None:
    attached = attach_hydrated_interaction(
        {
            "jobId": "job_ok",
            "status": "succeeded",
            "capabilityKey": "image.generate.v1",
            "artifacts": [{"artifactId": "art_1", "mediaType": "image/png"}],
            "interaction": {
                "schemaVersion": "hydracept.interaction.v1",
                "surface": "job.progress",
                "title": "Hydracept job",
                "actions": [{"id": "refresh"}],
            },
        }
    )
    assert attached["surface"] == "artifact.review"
    assert attached["presentation"]["surface"] == "artifact.review"
