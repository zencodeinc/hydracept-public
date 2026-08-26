"""Local validation for project surface definitions (public CLI).

Does not import hydracept_api. Authorship is not execution authority:
named project commands may be declared here and still 422 until the
project agent allowlists them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SURFACE_APPLY_SCHEMA_VERSION = "hydracept.cli.surface-apply.v1"

_DEFINITION_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,127}$")
_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,127}$")
_SHELLISH = re.compile(r"[;|&`$<>\\\n]|://")
_INPUT_TYPES = frozenset({"string", "number", "boolean", "string[]"})
_HANDLER_KINDS = frozenset({"projectCommand", "capability", "navigation"})


class SurfaceDefinitionError(ValueError):
    """Invalid surface definition or apply policy violation."""


def load_surface_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SurfaceDefinitionError(f"Surface file not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SurfaceDefinitionError(f"Surface file is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SurfaceDefinitionError("Surface file must be a JSON object")
    return payload


def apply_body_from_definition(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and return the public PanelDefinitionCreate/Patch body.

    Always sets origin=project. Does not grant execution of named commands.
    """
    key = _require_token(raw.get("key"), field="key", pattern=_DEFINITION_KEY)
    display_name = _require_text(raw.get("displayName"), field="displayName", max_length=255)
    actions = raw.get("actions")
    if not isinstance(actions, list) or not actions:
        raise SurfaceDefinitionError("actions must be a non-empty array")
    normalized_actions = [_normalize_action(item, index) for index, item in enumerate(actions)]
    _reject_duplicate_keys(
        [str(item["key"]) for item in normalized_actions],
        field="actions.key",
    )

    body: dict[str, Any] = {
        "key": key,
        "displayName": display_name,
        "origin": "project",
        "actions": normalized_actions,
    }
    allowed = raw.get("allowedOrigins")
    if allowed is not None:
        if not isinstance(allowed, list) or any(not isinstance(item, str) for item in allowed):
            raise SurfaceDefinitionError("allowedOrigins must be an array of strings")
        body["allowedOrigins"] = allowed
    if raw.get("presentation") is not None:
        if not isinstance(raw["presentation"], dict):
            raise SurfaceDefinitionError("presentation must be an object")
        body["presentation"] = raw["presentation"]
    if raw.get("policy") is not None:
        if not isinstance(raw["policy"], dict):
            raise SurfaceDefinitionError("policy must be an object")
        body["policy"] = raw["policy"]
    capability_key = raw.get("capabilityKey")
    if capability_key is not None:
        if not isinstance(capability_key, str) or not capability_key.strip():
            raise SurfaceDefinitionError("capabilityKey must be a non-empty string when set")
        body["capabilityKey"] = capability_key.strip()
        version = raw.get("capabilityVersion")
        if isinstance(version, str) and version.strip():
            body["capabilityVersion"] = version.strip()
    return body


def _normalize_action(raw: Any, index: int) -> dict[str, Any]:
    prefix = f"actions[{index}]"
    if not isinstance(raw, dict):
        raise SurfaceDefinitionError(f"{prefix} must be an object")
    key = _require_token(raw.get("key"), field=f"{prefix}.key", pattern=_TOKEN)
    label = _require_text(raw.get("label"), field=f"{prefix}.label", max_length=255)
    handler = _normalize_handler(raw.get("handler"), prefix=f"{prefix}.handler")
    action: dict[str, Any] = {"key": key, "label": label, "handler": handler}
    inputs = raw.get("inputs")
    if inputs is None:
        return action
    if not isinstance(inputs, list):
        raise SurfaceDefinitionError(f"{prefix}.inputs must be an array")
    normalized_inputs = [
        _normalize_input(item, f"{prefix}.inputs[{input_index}]")
        for input_index, item in enumerate(inputs)
    ]
    _reject_duplicate_keys(
        [str(item["key"]) for item in normalized_inputs],
        field=f"{prefix}.inputs.key",
    )
    action["inputs"] = normalized_inputs
    return action


def _normalize_handler(raw: Any, *, prefix: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SurfaceDefinitionError(f"{prefix} must be an object")
    kind = raw.get("kind")
    if kind not in _HANDLER_KINDS:
        raise SurfaceDefinitionError(
            f"{prefix}.kind must be projectCommand, capability, or navigation"
        )
    if kind == "projectCommand":
        command = raw.get("command")
        if not isinstance(command, str) or not command.strip():
            raise SurfaceDefinitionError(f"{prefix}.command is required")
        trimmed = command.strip()
        if _SHELLISH.search(trimmed) or not _TOKEN.fullmatch(trimmed):
            raise SurfaceDefinitionError(
                f"{prefix}.command is not a named project operation "
                f"(no shell, paths, or whitespace): {trimmed!r}"
            )
        return {"kind": "projectCommand", "command": trimmed}
    if kind == "capability":
        capability = raw.get("capability")
        if not isinstance(capability, str) or not capability.strip():
            raise SurfaceDefinitionError(f"{prefix}.capability is required")
        return {"kind": "capability", "capability": capability.strip()}
    href = raw.get("href")
    if not isinstance(href, str) or not href.strip():
        raise SurfaceDefinitionError(f"{prefix}.href is required")
    trimmed = href.strip()
    if not trimmed.startswith("/") or trimmed.startswith("//") or "://" in trimmed:
        raise SurfaceDefinitionError(f"{prefix}.href must be an in-app path")
    return {"kind": "navigation", "href": trimmed}


def _normalize_input(raw: Any, prefix: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SurfaceDefinitionError(f"{prefix} must be an object")
    key = _require_token(raw.get("key"), field=f"{prefix}.key", pattern=_TOKEN)
    label = _require_text(raw.get("label"), field=f"{prefix}.label", max_length=255)
    value_type = raw.get("valueType", "string")
    if value_type not in _INPUT_TYPES:
        raise SurfaceDefinitionError(
            f"{prefix}.valueType must be string, number, boolean, or string[]"
        )
    return {"key": key, "label": label, "valueType": value_type}


def _require_token(value: Any, *, field: str, pattern: re.Pattern[str]) -> str:
    text = _require_text(value, field=field, max_length=128)
    if not pattern.fullmatch(text):
        raise SurfaceDefinitionError(f"{field} is not a valid identifier: {text!r}")
    return text


def _require_text(value: Any, *, field: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SurfaceDefinitionError(f"{field} is required")
    trimmed = value.strip()
    if len(trimmed) > max_length:
        raise SurfaceDefinitionError(f"{field} exceeds {max_length} characters")
    return trimmed


def _reject_duplicate_keys(keys: list[str], *, field: str) -> None:
    seen: set[str] = set()
    for key in keys:
        if key in seen:
            raise SurfaceDefinitionError(f"duplicate {field}: {key}")
        seen.add(key)
