"""Lane E: a consumer can author a project surface from the public CLI contract."""

from __future__ import annotations

from hydracept.cli.main import app
from hydracept.cli.surface_definition import apply_body_from_definition


def test_fresh_agent_can_author_actions_only_surface_from_public_contract() -> None:
    authored = {
        "key": "project-validator",
        "displayName": "Project validator",
        "origin": "hydracept",
        "actions": [
            {
                "key": "validate",
                "label": "Validate",
                "handler": {"kind": "projectCommand", "command": "validate"},
            }
        ],
    }
    body = apply_body_from_definition(authored)
    assert body["origin"] == "project"
    assert body["actions"][0]["handler"]["command"] == "validate"
    assert "capabilityKey" not in body


def test_public_cli_exposes_sync_and_watch() -> None:
    from hydracept.cli.project_cmd import project_app

    group_names = {getattr(group, "name", "") for group in app.registered_groups}
    assert "project" in group_names
    command_names = {getattr(command, "name", "") for command in project_app.registered_commands}
    assert command_names >= {"sync", "watch", "up"}
