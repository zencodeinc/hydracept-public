"""Map convenience --prompt shapes into capability-specific input bodies.

Validation failures carry value-level recovery metadata so the next action
addresses the actual invalid value instead of generic capability discovery.
"""

from __future__ import annotations

import difflib
import re
from typing import Any

_LOCALE_PROMPT_PREFIX = re.compile(r"^([a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})?):(.+)$")

_CONTEXT_KEYS = frozenset(
    {"context", "execution", "idempotencyKey", "projectId", "environment"}
)

# Job-envelope keys a caller may legitimately pass alongside the capability input.
# ``input`` is handled separately by :func:`_unwrap_input_envelope`.
_ENVELOPE_KEYS = _CONTEXT_KEYS | frozenset(
    {"input", "quoteId", "estimateId", "capabilityKey", "capability"}
)

_DOMAIN_SEARCH_INPUT_FIELDS = frozenset({"domain", "prompt"})
_TRANSLATE_INPUT_FIELDS = frozenset(
    {"prompt", "targetLocale", "sourceLocale", "items", "glossary", "preserveTerms"}
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
    body = _unwrap_input_envelope(dict(payload))
    if key == "text.translate.v1":
        coerced = _coerce_translate_input(dict(body))
    elif key == "domain.search.v1":
        coerced = _coerce_domain_search_input(dict(body))
    else:
        coerced = dict(body)
    return _validate_required_inputs(key, coerced)


def _unwrap_input_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    """Treat ``{"input": {...}}`` as the capability input, never as a stray field.

    Agents wrap capability fields the way the job API does. Validating the wrapper
    instead of the inner object reports a capability-schema error ("domain is
    required") for what is really an envelope mistake, which sends the caller
    debugging the wrong layer.
    """
    if "input" not in payload:
        return payload
    # A caller that also supplied job-envelope keys handed us a complete job body;
    # leave it intact so the existing envelope path (and its server-side
    # validation) keeps working.
    if any(name in _ENVELOPE_KEYS and name != "input" for name in payload):
        return payload
    inner = payload.get("input")
    if not isinstance(inner, dict) or not inner:
        raise InputValidationError(
            "INPUT_ENVELOPE_INVALID",
            "The 'input' field must be a non-empty object of capability input fields.",
            field="input",
            expected="non-empty object",
            recovery={
                "nextAction": (
                    "Pass capability fields directly (for example prompt/domain), or wrap "
                    'them as {"input": {...}}.'
                ),
                "cli": "python -m hydracept run <capability> --input-file request.json --json",
                "field": "input",
            },
        )
    # Keep any non-envelope siblings so no supplied field is silently discarded.
    merged = dict(inner)
    for name, value in payload.items():
        if name != "input":
            merged[name] = value
    return merged


def _reject_unknown_input_fields(
    capability: str,
    payload: dict[str, Any],
    allowed: frozenset[str],
) -> None:
    """Fail on a field the capability cannot accept, naming the allowed set.

    Without this, an unknown field is ignored until the API reports a missing
    required field, which hides the real mistake.
    """
    unknown = sorted(
        name for name in payload if name not in allowed and name not in _ENVELOPE_KEYS
    )
    if not unknown:
        return
    field = unknown[0]
    nearest = difflib.get_close_matches(field, sorted(allowed), n=1, cutoff=0.4)
    suggestion = f" Did you mean '{nearest[0]}'?" if nearest else ""
    allowed_list = ", ".join(sorted(allowed))
    next_action = (
        f"python -m hydracept run {capability} --prompt \"...\" --json"
        if "prompt" in allowed
        else f"python -m hydracept run {capability} --input-file request.json --json"
    )
    raise InputValidationError(
        "UNKNOWN_INPUT_FIELD",
        f"Unknown input field '{field}' for {capability}.{suggestion} "
        f"Allowed fields: {allowed_list}.",
        field=field,
        expected=f"one of: {allowed_list}",
        recovery={
            "nextAction": next_action,
            "cli": next_action,
            "field": field,
            "allowedFields": sorted(allowed),
            "unknownFields": unknown,
        },
    )


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
    _reject_unknown_input_fields(
        "domain.search.v1", payload, _DOMAIN_SEARCH_INPUT_FIELDS - {"prompt"}
    )
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
    _reject_unknown_input_fields(
        "text.translate.v1", payload, _TRANSLATE_INPUT_FIELDS - {"prompt"}
    )
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


def parse_set_values(values: list[str] | tuple[str, ...]) -> dict[str, Any]:
    """Parse repeated ``--set key=value`` flags into capability input fields.

    Values are JSON when they parse as JSON (numbers, booleans, arrays, objects)
    and a plain string otherwise, so ``--set width=816`` supplies an integer while
    ``--set prompt=hello`` stays a string. This is the generic escape hatch for
    simple schema properties that are not worth a dedicated CLI flag.
    """
    import json as _json

    parsed: dict[str, Any] = {}
    for raw in values:
        text = str(raw or "").strip()
        key, separator, raw_value = text.partition("=")
        key = key.strip()
        if not separator or not key:
            raise InputValidationError(
                "INVALID_SET",
                f"--set expects key=value, got {text!r}.",
                field="--set",
                expected="key=value",
                recovery={
                    "nextAction": 'python -m hydracept run <capability> --set width=816 --json',
                    "cli": '--set width=816',
                    "field": "set",
                },
            )
        value_text = raw_value.strip()
        try:
            value: Any = _json.loads(value_text)
        except _json.JSONDecodeError:
            value = value_text
        parsed[key] = value
    return parsed


__all__ = ["InputValidationError", "coerce_capability_input", "parse_set_values"]
