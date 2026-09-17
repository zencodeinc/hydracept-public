"""Map convenience --prompt shapes into capability-specific input bodies.

Validation failures carry value-level recovery metadata so the next action
addresses the actual invalid value instead of generic capability discovery.
"""

from __future__ import annotations

import re
from typing import Any

_LOCALE_PROMPT_PREFIX = re.compile(r"^([a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})?):(.+)$")

_CONTEXT_KEYS = frozenset(
    {"context", "execution", "idempotencyKey", "projectId", "environment"}
)

# Capabilities whose ergonomic one-shot shape is a single prompt.
_PROMPT_CAPABILITIES = frozenset(
    {
        "image.generate.v1",
        "audio.generate.v1",
        "video.generate.v1",
    }
)

_SUPPLY_PROMPT = (
    "Supply a non-empty --prompt or use --input-file request.json."
)


class InputValidationError(ValueError):
    """Value-level validation failure with recovery metadata."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        field: str = "",
        expected: str = "",
        recovery: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.expected = expected
        self.recovery = recovery or {}

    def to_payload(self) -> dict[str, Any]:
        """Structured CLI/MCP error envelope for this validation failure."""
        details: dict[str, Any] = {"errorClass": "INVALID_INPUT"}
        if self.field:
            details["field"] = self.field
        if self.expected:
            details["expected"] = self.expected
        payload: dict[str, Any] = {
            "error": True,
            "code": "InvalidInput",
            "errorClass": "INVALID_INPUT",
            "message": self.message,
            "details": details,
        }
        if self.recovery:
            payload["recovery"] = self.recovery
            next_action = self.recovery.get("nextAction") or self.recovery.get("cli")
            if next_action:
                payload["nextAction"] = next_action
        return payload


def coerce_capability_input(capability: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize CLI/MCP convenience fields before admission."""
    key = str(capability or "").strip()
    if key == "text.translate.v1":
        coerced = _coerce_translate_input(dict(payload))
    elif key == "domain.search.v1":
        coerced = _coerce_domain_search_input(dict(payload))
    else:
        coerced = dict(payload)
    return _validate_required_inputs(key, coerced)


def _validate_required_inputs(key: str, payload: dict[str, Any]) -> dict[str, Any]:
    if key not in _PROMPT_CAPABILITIES:
        return payload
    meaningful = {name: value for name, value in payload.items() if name not in _CONTEXT_KEYS}
    if meaningful:
        return payload
    raise InputValidationError(
        "INPUT_REQUIRED",
        f"{key} requires input; prompt is required.",
        field="prompt",
        expected="non-empty string",
        recovery={
            "nextAction": _SUPPLY_PROMPT,
            "cli": _SUPPLY_PROMPT,
            "field": "prompt",
        },
    )


def _coerce_domain_search_input(payload: dict[str, Any]) -> dict[str, Any]:
    """Treat a lone prompt as the domain, while preserving structured bodies."""
    prompt = payload.pop("prompt", None)
    if prompt is None:
        return payload
    prompt_text = str(prompt).strip()
    if not prompt_text:
        raise InputValidationError(
            "INPUT_EMPTY",
            "domain.search.v1 --prompt must not be empty.",
            field="prompt",
            expected="non-empty string",
            recovery={
                "nextAction": "Supply a non-empty --prompt or pass a domain field.",
                "cli": "Supply a non-empty --prompt or pass a domain field.",
                "field": "prompt",
            },
        )
    payload.setdefault("domain", prompt_text)
    return payload


def _coerce_translate_input(payload: dict[str, Any]) -> dict[str, Any]:
    prompt = payload.pop("prompt", None)
    if prompt is None:
        return payload
    prompt_text = str(prompt).strip()
    if not prompt_text:
        raise InputValidationError(
            "INPUT_EMPTY",
            "prompt is required for text.translate.v1.",
            field="prompt",
            expected="non-empty string",
            recovery={"nextAction": _SUPPLY_PROMPT, "cli": _SUPPLY_PROMPT, "field": "prompt"},
        )

    items = payload.get("items")
    if isinstance(items, list) and items:
        payload["prompt"] = prompt_text
        return payload

    target_locale = str(payload.get("targetLocale") or "").strip()
    text = prompt_text
    if not target_locale:
        match = _LOCALE_PROMPT_PREFIX.match(prompt_text)
        if match:
            target_locale = match.group(1)
            text = match.group(2).strip()
    if not target_locale:
        next_action = (
            'python -m hydracept run text.translate.v1 --target-locale es '
            '--prompt "Hello" --json'
        )
        raise InputValidationError(
            "INPUT_REQUIRED",
            "text.translate.v1 requires targetLocale.",
            field="targetLocale",
            expected="BCP 47 locale",
            recovery={
                "nextAction": next_action,
                "cli": next_action,
                "field": "targetLocale",
                "example": 'python -m hydracept run text.translate.v1 --target-locale es --prompt "Hello" --json',
            },
        )
    if not text:
        raise InputValidationError(
            "INPUT_EMPTY",
            "text.translate.v1 requires non-empty text to translate.",
            field="items[0].text",
            expected="non-empty string",
            recovery={"nextAction": _SUPPLY_PROMPT, "cli": _SUPPLY_PROMPT},
        )

    payload["targetLocale"] = target_locale
    payload["items"] = [{"id": "1", "text": text}]
    return payload


__all__ = ["InputValidationError", "coerce_capability_input"]
