from __future__ import annotations

from typing import Any

from hydracept.mcp import interactions


def _field_names(surface: dict[str, Any]) -> set[str]:
    return {field["name"] for field in surface["fields"]}


def test_exactly_seven_stable_surfaces() -> None:
    assert interactions.SURFACE_IDS == (
        "project.connect",
        "capability.launch",
        "connection.resolve",
        "authorization.preflight",
        "job.progress",
        "artifact.review",
        "change.promote",
    )


def test_project_connect_keeps_identity_stable_but_name_editable() -> None:
    surface = interactions.project_connect_surface(
        {
            "projectId": "cpr_123",
            "displayName": "Old Name",
            "environment": "development",
            "detectedRoot": "/repo",
        }
    )
    fields = {field["name"]: field for field in surface["fields"]}
    assert fields["projectId"]["readOnly"] is True
    assert fields["displayName"]["readOnly"] is False
    assert fields["displayName"]["required"] is True
    assert fields["environment"]["options"] == ["development", "staging", "production"]
    assert surface["data"]["stableIdentityField"] == "projectId"
    assert surface["data"].get("autoConnect") is not True


def test_project_connect_locks_known_name_during_bootstrap() -> None:
    surface = interactions.project_connect_surface(
        {
            "displayName": "Hydratest20",
            "environment": "development",
            "status": "interaction_required",
            "actionUrl": "https://api.hydracept.com/connect/bs_test",
        }
    )
    fields = {field["name"]: field for field in surface["fields"]}
    assert fields["displayName"]["value"] == "Hydratest20"
    assert fields["displayName"]["readOnly"] is True
    assert fields["displayName"]["required"] is False
    assert fields["environment"]["readOnly"] is True
    assert surface["data"]["autoConnect"] is True
    assert "already has the project name" in surface["description"]
    schema = interactions.elicitation_schema(surface)
    assert "displayName" not in schema.get("properties", {})
    assert interactions.named_bootstrap_connect(surface) is True


def test_capability_launch_filters_credentials_but_keeps_token_counts() -> None:
    surface = interactions.capability_launch_surface(
        {
            "capability": {
                "key": "text.general.fast.v1",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "messages": {"type": "array"},
                        "maxOutputTokens": {"type": "integer"},
                        "apiKey": {"type": "string"},
                        "access_token": {"type": "string"},
                        "password": {"type": "string"},
                    },
                },
            }
        }
    )
    assert _field_names(surface) == {"messages", "maxOutputTokens"}
    assert surface["data"]["excludedInteractiveFields"] == [
        "apiKey",
        "access_token",
        "password",
    ]


def test_connection_surface_never_accepts_secrets() -> None:
    surface = interactions.connection_resolve_surface(
        {
            "capabilityKey": "image.generate.v1",
            "provider": "openai",
            "requiredSecretScopes": ["account.openai"],
        }
    )
    assert surface["data"]["acceptsSecrets"] is False
    assert all(field["readOnly"] for field in surface["fields"])
    assert "Do not paste provider secrets" in " ".join(surface["fallback"]["nextActions"])


def test_domain_registration_preflight_exposes_irreversible_effect() -> None:
    surface = interactions.authorization_preflight_surface(
        {
            "capability": {
                "key": "domain.register.v1",
                "approvalRequirements": {
                    "requiresHumanApproval": True,
                    "requiredSecretScopes": ["account.domain_registrar"],
                    "irreversibleEffects": ["creates_registered_domain"],
                },
            },
            "estimatedCostCents": 1299,
            "currency": "USD",
        }
    )
    assert surface["risk"]["requiresHumanApproval"] is True
    assert surface["risk"]["irreversibleEffects"] == ["creates_registered_domain"]
    assert surface["risk"]["estimatedCostCents"] == 1299
    assert surface["actions"][0]["id"] == "authorize"
    assert surface["actions"][0]["intent"] == "authorize"


def test_preflight_exposes_sensitivity_and_asset_approvals() -> None:
    surface = interactions.authorization_preflight_surface(
        {
            "capability": {
                "key": "domain.register.v1",
                "approvalRequirements": {
                    "requiresHumanApproval": True,
                    "dataSensitivity": "account",
                    "requiredAssetApprovals": ["registrant_contact"],
                    "irreversibleEffects": ["creates_registered_domain"],
                },
            }
        }
    )
    fields = {field["name"]: field for field in surface["fields"]}
    assert fields["dataSensitivity"]["value"] == "account"
    assert fields["requiredAssetApprovals"]["value"] == ["registrant_contact"]
    prompt = interactions.surface_prompt(surface)
    assert "Sensitivity: account" in prompt
    assert "registrant_contact" in prompt


def test_preflight_prefers_user_facing_cost_display() -> None:
    surface = interactions.authorization_preflight_surface(
        {
            "capabilityKey": "image.generate.v1",
            "estimatedCostCents": 47,
            "estimatedCostDisplay": "CA$0.64",
            "currency": "CAD",
        }
    )
    fields = {field["name"]: field for field in surface["fields"]}
    assert fields["estimatedCostDisplay"]["value"] == "CA$0.64"
    assert "estimatedCostCents" not in fields
    assert "CA$0.64" in interactions.surface_prompt(surface)


def test_native_elicitation_schema_is_shallow_and_secret_safe() -> None:
    surface = interactions.capability_launch_surface(
        {
            "capability": {
                "key": "example.v1",
                "inputSchema": {
                    "type": "object",
                    "required": ["prompt"],
                    "properties": {
                        "prompt": {"type": "string"},
                        "options": {"type": "object"},
                        "tags": {"type": "array"},
                        "sessionToken": {"type": "string"},
                    },
                },
            }
        }
    )
    schema = interactions.elicitation_schema(surface)
    assert schema["properties"]["options"]["type"] == "string"
    assert schema["properties"]["tags"]["items"] == {"type": "string"}
    assert "sessionToken" not in schema["properties"]
    assert schema["properties"]["decision"]["enum"] == ["run", "cancel"]
    assert "prompt" in schema["required"]


def test_progress_is_structured_and_non_authoritative() -> None:
    surface = interactions.job_progress_surface(
        {
            "jobId": "job_123",
            "capabilityKey": "image.generate.v1",
            "status": "running",
            "nextAction": "poll",
            "pollAfterSeconds": 2,
        }
    )
    assert surface["data"]["nextAction"] == "poll"
    assert surface["data"]["pollAfterSeconds"] == 2
    assert surface["fallback"]["nextActions"][0] == "hydracept_job_status"
    assert surface["data"]["jobId"] == "job_123"
    assert surface["data"]["capabilityKey"] == "image.generate.v1"
    assert surface["data"]["status"] == "running"
    assert surface["actions"][1]["id"] == "close"
    assert surface["actions"][1]["label"] == "Stop watching"
    assert surface["actions"][2]["id"] == "cancel-job"
    assert surface["actions"][0]["primary"] is True
    assert surface["actions"][0]["style"] == "primary"


def test_canceled_and_needs_attention_are_terminal_on_progress() -> None:
    canceled = interactions.job_progress_surface(
        {"jobId": "job_x", "status": "canceled", "capabilityKey": "text.translate.v1"}
    )
    attention = interactions.job_progress_surface(
        {"jobId": "job_n", "status": "needs_attention"}
    )
    assert canceled["actions"][1]["id"] == "receipt"
    assert all(action["id"] != "cancel-job" for action in canceled["actions"])
    assert attention["actions"][1]["id"] == "receipt"
    assert interactions._next_action("job.progress", "refresh") == "poll_existing_job"
    assert interactions._next_action("job.progress", "receipt") == "inspect_receipt"
    assert interactions._next_action("job.progress", "cancel-job") == "cancel_existing_job"
    assert interactions._next_action("artifact.review", "use") == "present_artifact_to_agent"
    assert interactions._next_action("artifact.review", "download") == "download_primary_artifact"


def test_connection_and_review_put_identity_in_data() -> None:
    connection = interactions.connection_resolve_surface(
        {"capabilityKey": "domain.register.v1", "connectUrl": "https://studio.example/c"}
    )
    review = interactions.artifact_review_surface(
        {
            "jobId": "job_r",
            "capabilityKey": "image.generate.v1",
            "artifacts": [{"artifactId": "art_1", "filename": "hero.png", "mediaType": "image/png"}],
        }
    )
    assert connection["data"]["capabilityKey"] == "domain.register.v1"
    assert review["data"]["jobId"] == "job_r"
    assert review["data"]["capabilityKey"] == "image.generate.v1"
    assert review["data"]["artifacts"][0]["artifactId"] == "art_1"
    assert review["actions"][0]["primary"] is True


def test_promote_exposes_selectable_surface_path() -> None:
    surface = interactions.change_promote_surface(
        {
            "projectId": "cpr_1",
            "surfacePaths": [
                "tools/hydracept/surfaces/hero.json",
                "tools/hydracept/surfaces/icon.json",
            ],
            "promoteEnabled": True,
        }
    )
    fields = {field["name"]: field for field in surface["fields"]}
    assert fields["surfacePath"]["value"] == "tools/hydracept/surfaces/hero.json"
    assert fields["surfacePath"]["options"] == [
        "tools/hydracept/surfaces/hero.json",
        "tools/hydracept/surfaces/icon.json",
    ]
    assert fields["surfacePath"]["readOnly"] is False


def test_cost_alone_does_not_require_authorization() -> None:
    surface = interactions.authorization_preflight_surface(
        {
            "capabilityKey": "image.generate.v1",
            "estimatedCostDisplay": "$0.01",
            "estimatedCostCents": 1,
        }
    )
    assert surface["actions"][0]["id"] == "continue"
    assert surface["risk"]["costAuthorizationPolicy"] == "show_price_block_on_policy"
    assert surface["risk"]["needsAuthorization"] is False


def test_artifact_review_and_promotion_remain_separate_gates() -> None:
    review = interactions.artifact_review_surface(
        {
            "artifacts": [{"artifactId": "art_1", "filename": "hero.png"}],
            "reviewRequired": True,
        }
    )
    ordinary = interactions.artifact_review_surface(
        {"artifacts": [{"artifactId": "art_1", "filename": "hero.png"}]}
    )
    variants = interactions.artifact_review_surface(
        {
            "artifacts": [
                {"artifactId": "art_a", "filename": "a.png"},
                {"artifactId": "art_b", "filename": "b.png"},
            ]
        }
    )
    promote = interactions.change_promote_surface(
        {
            "projectId": "cpr_123",
            "validationStatus": "passed",
            "changes": ["Assets/hero.png"],
        }
    )
    assert review["actions"][0]["intent"] == "use"
    assert all(action["intent"] != "approve" for action in review["actions"])
    executable = interactions.artifact_review_surface(
        {
            "artifacts": [{"artifactId": "art_1", "filename": "hero.png"}],
            "reviewRequired": True,
            "reviewAuthority": {"executable": True, "approve": "/v1/jobs/x/approve"},
        }
    )
    assert executable["actions"][0]["intent"] == "approve"
    assert ordinary["actions"][0]["id"] == "use"
    assert variants["actions"][0]["id"] == "select"
    assert all(action["intent"] != "apply" for action in review["actions"])
    assert promote["data"]["authority"] == "project-local-agent"
    assert promote["data"]["centralServiceWritesRepository"] is False


def test_every_surface_has_structured_fallback() -> None:
    for surface_id in interactions.SURFACE_IDS:
        surface = interactions.build_interaction_surface(surface_id, {})
        assert surface["schemaVersion"] == "hydracept.interaction.v1"
        assert surface["fallback"]["summary"]
        assert surface["fallback"]["nextActions"]


def test_registration_adds_single_interaction_tool() -> None:
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
    assert set(server.tools) == {"hydracept_interaction_surface"}


def test_source_skill_and_tools_yaml_advertise_interaction_surface() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    skill = (
        root / "public" / "agents" / "source" / "skills" / "hydracept" / "SKILL.md"
    ).read_text(encoding="utf-8")
    tools = (
        root / "public" / "agents" / "source" / "mcp" / "tools.yaml"
    ).read_text(encoding="utf-8")
    wheel = (
        root
        / "clients"
        / "python"
        / "hydracept"
        / "data"
        / "agents"
        / "skills"
        / "hydracept"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "hydracept_interaction_surface" in skill
    assert "hydracept_interaction_surface" in wheel
    assert "hydracept_interaction_surface" in tools
    for surface_id in interactions.SURFACE_IDS:
        assert surface_id in skill
        assert surface_id in wheel


def _apps_ctx(*, form: bool = True) -> Any:
    from types import SimpleNamespace

    from mcp.server.apps import APP_MIME_TYPE, EXTENSION_ID

    elicitation = SimpleNamespace(form=True, url=None) if form else None
    return SimpleNamespace(
        client_capabilities=SimpleNamespace(
            extensions={EXTENSION_ID: {"mimeTypes": [APP_MIME_TYPE]}},
            elicitation=elicitation,
        ),
        protocol_version="2026-07-28",
        input_responses={},
    )


def _form_ctx() -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(
        client_capabilities=SimpleNamespace(
            extensions={},
            elicitation=SimpleNamespace(form=True, url=None),
        ),
        protocol_version="2026-07-28",
        input_responses={},
    )


def test_apps_path_returns_full_contract_not_elicitation() -> None:
    import asyncio

    from mcp_types import InputRequiredResult

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
    result = asyncio.run(
        server.tools["hydracept_interaction_surface"](
            _apps_ctx(),
            "job.progress",
            {"jobId": "job_1", "status": "running"},
            True,
        )
    )
    assert not isinstance(result, InputRequiredResult)
    assert result["schemaVersion"] == "hydracept.interaction.v1"
    assert result["surface"] == "job.progress"
    assert result["presentation"]["status"] == "mounted"
    assert result["presentation"]["agentAction"] == "present"


def test_form_client_preserves_elicitation_for_blocking_surfaces() -> None:
    import asyncio

    from mcp_types import InputRequiredResult

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
    result = asyncio.run(
        server.tools["hydracept_interaction_surface"](
            _form_ctx(),
            "capability.launch",
            {"capabilityKey": "text.translate.v1"},
            True,
        )
    )
    assert isinstance(result, InputRequiredResult)
    meta = result.meta or {}
    assert meta["presentation"]["status"] == "fallback"
    assert meta["presentation"]["fallback"]["kind"] == "structured_form"
    assert meta["surface"] == "capability.launch"


def test_progress_remains_nonblocking_for_form_clients() -> None:
    import asyncio

    from mcp_types import InputRequiredResult

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
    result = asyncio.run(
        server.tools["hydracept_interaction_surface"](
            _form_ctx(),
            "job.progress",
            {"jobId": "job_1", "status": "running"},
            True,
        )
    )
    assert not isinstance(result, InputRequiredResult)
    assert result["surface"] == "job.progress"
    assert result["presentation"]["status"] == "fallback"
    assert result["presentation"]["reason"] == "host_does_not_support_apps"


def test_top_level_surface_survives_routing_payload() -> None:
    from hydracept.mcp.interaction_hydration import attach_hydrated_interaction

    attached = attach_hydrated_interaction(
        {"jobId": "job_1", "status": "running", "capabilityKey": "image.generate.v1"},
        "job.progress",
    )
    assert attached["surface"] == "job.progress"
    assert attached["interaction"]["schemaVersion"] == "hydracept.interaction.v1"
    assert attached["interaction"]["surface"] == "job.progress"


def test_capability_launch_retains_input_and_ui_schema() -> None:
    surface = interactions.capability_launch_surface(
        {
            "capability": {
                "key": "text.translate.v1",
                "inputSchema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}, "options": {"type": "object"}},
                },
                "uiSchema": {"options": {"widget": "json"}},
                "executionModes": ["invoke"],
            }
        }
    )
    assert surface["data"]["inputSchema"]["properties"]["text"]
    assert surface["data"]["uiSchema"]["options"]["widget"] == "json"
    assert surface["data"]["executionModes"] == ["invoke"]


def test_mcp_apps_helper_is_available_on_minimum_sdk() -> None:
    from importlib.metadata import version

    from mcp.server.apps import client_supports_apps

    parts = [int(part) for part in version("mcp").split(".")[:2]]
    assert parts >= [2, 1]
    assert callable(client_supports_apps)
