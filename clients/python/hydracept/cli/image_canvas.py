"""Client-side image canvas floor matching live image.generate.v1 admission."""

from __future__ import annotations

from typing import Any

MIN_PIXELS = 655_360
MIN_SQUARE = 816


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return None
    return resolved if resolved > 0 else None


def canvas_size(payload: dict[str, Any] | None) -> tuple[int, int] | None:
    blobs: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        blobs.append(payload)
        nested = payload.get("input")
        if isinstance(nested, dict):
            blobs.append(nested)
    for blob in blobs:
        width = _as_int(blob.get("width"))
        height = _as_int(blob.get("height"))
        if width is not None and height is not None:
            return width, height
    return None


def preflight_image_canvas(capability: str, payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return an error document if this canvas would fail admission."""
    if not str(capability or "").startswith("image."):
        return None
    size = canvas_size(payload)
    if size is None:
        return None
    width, height = size
    if width * height >= MIN_PIXELS:
        return None
    key = str(capability).strip() or "image.generate.v1"
    return {
        "error": True,
        "code": "InvalidInput",
        "message": (
            f"total pixels must be >= {MIN_PIXELS}. {width}×{height} is {width * height} pixels. "
            f"Minimum square is {MIN_SQUARE}×{MIN_SQUARE}."
        ),
        "nextAction": (
            f"python -m hydracept run {key} --prompt \"...\" --json "
            f"(omit width/height, or use {MIN_SQUARE}x{MIN_SQUARE})"
        ),
        "recovery": {
            "minimumSquare": f"{MIN_SQUARE}x{MIN_SQUARE}",
            "minPixels": MIN_PIXELS,
            "requested": f"{width}x{height}",
        },
    }
