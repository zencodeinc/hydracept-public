"""Map convenience --prompt shapes into capability-specific input bodies."""

from __future__ import annotations

import re
from typing import Any

_LOCALE_PROMPT_PREFIX = re.compile(r"^([a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})?):(.+)$")


def coerce_capability_input(capability: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize CLI/MCP convenience fields before admission."""
    key = str(capability or "").strip()
    if key == "text.translate.v1":
        return _coerce_translate_input(dict(payload))
    return dict(payload)


def _coerce_translate_input(payload: dict[str, Any]) -> dict[str, Any]:
    prompt = payload.pop("prompt", None)
    if prompt is None:
        return payload
    prompt_text = str(prompt).strip()
    if not prompt_text:
        raise ValueError("text.translate.v1 --prompt must not be empty.")

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
        raise ValueError(
            "text.translate.v1 requires targetLocale. "
            'Use --target-locale es --prompt "Hello" or --prompt "es:Hello".'
        )
    if not text:
        raise ValueError("text.translate.v1 requires non-empty text to translate.")

    payload["targetLocale"] = target_locale
    payload["items"] = [{"id": "1", "text": text}]
    return payload
