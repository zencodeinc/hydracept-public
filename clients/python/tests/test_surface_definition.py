"""Local validation for hydracept surface apply."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hydracept.cli.surface_definition import (
    SurfaceDefinitionError,
    apply_body_from_definition,
    load_surface_file,
)


def _valid(**overrides: object) -> dict:
    body: dict = {
        "key": "scrapfall.event-encounter-walker",
        "displayName": "Event encounter walker",
        "origin": "hydracept",
        "actions": [
            {
                "key": "validate",
                "label": "Validate",
                "handler": {"kind": "projectCommand", "command": "validate"},
            },
            {
                "key": "hydrateNode",
                "label": "Hydrate",
                "handler": {"kind": "projectCommand", "command": "hydrateNode"},
                "inputs": [
                    {"key": "eventKey", "label": "Event key", "valueType": "string"},
                    {"key": "seed", "label": "Seed", "valueType": "number"},
                ],
            },
        ],
    }
    body.update(overrides)
    return body


def test_forces_origin_project_and_keeps_named_ops() -> None:
    body = apply_body_from_definition(_valid())
    assert body["origin"] == "project"
    assert body["actions"][1]["handler"]["command"] == "hydrateNode"
    assert body["actions"][1]["inputs"][1]["valueType"] == "number"


def test_rejects_shell_command() -> None:
    raw = _valid(
        actions=[
            {
                "key": "shell",
                "label": "Shell",
                "handler": {"kind": "projectCommand", "command": "validate; id"},
            }
        ]
    )
    with pytest.raises(SurfaceDefinitionError, match="named project operation"):
        apply_body_from_definition(raw)


def test_rejects_external_navigation() -> None:
    raw = _valid(
        actions=[
            {
                "key": "docs",
                "label": "Docs",
                "handler": {"kind": "navigation", "href": "https://evil.example"},
            }
        ]
    )
    with pytest.raises(SurfaceDefinitionError, match="in-app path"):
        apply_body_from_definition(raw)


def test_rejects_empty_actions() -> None:
    with pytest.raises(SurfaceDefinitionError, match="non-empty"):
        apply_body_from_definition(_valid(actions=[]))


def test_rejects_duplicate_action_keys() -> None:
    raw = _valid(
        actions=[
            {
                "key": "validate",
                "label": "A",
                "handler": {"kind": "projectCommand", "command": "validate"},
            },
            {
                "key": "validate",
                "label": "B",
                "handler": {"kind": "projectCommand", "command": "validate"},
            },
        ]
    )
    with pytest.raises(SurfaceDefinitionError, match="duplicate"):
        apply_body_from_definition(raw)


def test_load_surface_file(tmp_path: Path) -> None:
    path = tmp_path / "walker.json"
    path.write_text(json.dumps(_valid()), encoding="utf-8")
    loaded = load_surface_file(path)
    assert loaded["key"] == "scrapfall.event-encounter-walker"


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SurfaceDefinitionError, match="not found"):
        load_surface_file(tmp_path / "missing.json")


def test_beastwright_catalog_surface_is_valid_apply_json() -> None:
    root = Path(__file__).resolve().parents[3]
    path = (
        root
        / "fixtures"
        / "projects"
        / "beastwright"
        / "tools"
        / "hydracept"
        / "surfaces"
        / "catalog-inspect.json"
    )
    body = apply_body_from_definition(load_surface_file(path))
    assert body["origin"] == "project"
    assert body["key"] == "catalog-inspect"
    assert body["actions"][0]["handler"]["command"] == "inspectCatalog"
