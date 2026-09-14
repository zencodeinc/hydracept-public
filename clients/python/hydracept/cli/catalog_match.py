"""Client-side capability matching when the live resolver returns no requestable match."""

from __future__ import annotations

import re
from typing import Any

import httpx

_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "me",
    "of",
    "one",
    "or",
    "the",
    "this",
    "to",
    "with",
}

_MODALITY_HINTS = (
    ("image.", ("image", "icon", "png", "sprite", "pixel", "art", "picture", "photo", "transparent", "illustration", "texture", "portrait")),
    ("audio.", ("audio", "sfx", "sound", "ogg", "wav", "music", "voice")),
    ("video.", ("video", "clip", "mp4", "animation")),
    ("text.", ("text", "translate", "prompt", "copy", "write")),
    ("domain.", ("domain", "dns", "tld")),
)


def intent_tokens(intent: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", (intent or "").lower())
        if token not in _STOPWORDS and len(token) > 1
    }


def score_capability(intent: str, item: dict[str, Any]) -> int:
    tokens = intent_tokens(intent)
    if not tokens:
        return 0
    key = str(item.get("key") or item.get("capabilityKey") or "")
    blob = " ".join(
        [
            key,
            str(item.get("title") or ""),
            str(item.get("summary") or ""),
            str(item.get("description") or ""),
            " ".join(str(tag) for tag in (item.get("tags") or []) if tag),
        ]
    ).lower()
    overlap = sum(1 for token in tokens if token in blob or token in key.lower())
    lowered = (intent or "").lower()
    for prefix, hints in _MODALITY_HINTS:
        if key.startswith(prefix) and any(hint in lowered for hint in hints):
            overlap += 4
            break
    if "generate" in tokens and "edit" not in tokens:
        if ".generate." in key:
            overlap += 3
        elif ".edit." in key:
            overlap -= 2
    elif "edit" in tokens and "generate" not in tokens:
        if ".edit." in key:
            overlap += 3
        elif ".generate." in key:
            overlap -= 2
    return overlap


def prefer_intent_matches(intent: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep resolver results, but surface the user's explicit generate/edit verb first."""
    if not items:
        return items
    lowered = (intent or "").lower()
    wants_generate = "generate" in lowered and "edit" not in lowered
    wants_edit = "edit" in lowered and "generate" not in lowered
    if not wants_generate and not wants_edit:
        return list(items)
    needle = ".generate." if wants_generate else ".edit."
    preferred: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            rest.append(item)
            continue
        key = str(item.get("key") or item.get("capabilityKey") or "")
        (preferred if needle in key else rest).append(item)
    return preferred + rest if preferred else list(items)


def catalog_matches(
    intent: str,
    *,
    api: str,
    headers: dict[str, str] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    response = httpx.get(
        f"{api.rstrip('/')}/v1/capabilities",
        headers=headers or {},
        params={"view": "summary"},
        timeout=30.0,
    )
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("capabilities") or payload.get("items") or payload.get("results") or []
    else:
        items = []
    ranked: list[tuple[int, dict[str, Any]]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        score = score_capability(intent, item)
        if score:
            ranked.append((score, item))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in ranked[:limit]]
