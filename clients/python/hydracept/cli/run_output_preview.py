"""Human-readable previews for non-artifact run results."""

from __future__ import annotations

from typing import Any


def human_run_preview(payload: dict[str, Any]) -> str | None:
    capability = str(payload.get("capability") or "")
    typed = payload.get("typedOutput")
    if not isinstance(typed, dict):
        output = payload.get("output")
        typed = output if isinstance(output, dict) else None
    if not isinstance(typed, dict):
        return None
    if capability == "text.translate.v1":
        items = typed.get("items")
        if not isinstance(items, list) or not items:
            return None
        lines: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            translation = item.get("translation")
            if not isinstance(translation, str) or not translation.strip():
                continue
            item_id = str(item.get("id") or "").strip()
            lines.append(f"{item_id}: {translation}" if item_id else translation.strip())
        return "\n".join(lines) if lines else None
    text = typed.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return None
