"""Resolve MCP capability key arguments with common aliases."""

from __future__ import annotations


def resolve_capability_key(
    *,
    capability_key: str = "",
    capability: str = "",
    capabilityKey: str = "",
) -> str:
    pairs = (
        ("capability_key", capability_key),
        ("capability", capability),
        ("capabilityKey", capabilityKey),
    )
    provided = [(name, str(value).strip()) for name, value in pairs if str(value or "").strip()]
    if not provided:
        raise ValueError(
            "Missing capability key. Pass capability_key (aliases: capability, capabilityKey)."
        )
    values = {value for _, value in provided}
    if len(values) > 1:
        names = ", ".join(name for name, _ in provided)
        raise ValueError(f"Conflicting capability keys ({names}). Use one name consistently.")
    return next(iter(values))
