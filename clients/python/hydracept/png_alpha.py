"""PNG transparency checks: real alpha plus leftover chroma-key plate fields."""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import Any

from hydracept.chroma_plate_detector import ChromaPlateDetector
from hydracept.chroma_plate_key import DEFAULT_CHROMA_KEY, ChromaPlateKey

_MAX_CHROMA_PLATE_RATIO = 0.25
_VISIBLE_ALPHA_THRESHOLD = 16
_OPAQUE_CORNER_FAILURE = 3

TRANSPARENCY_AGENT_NOTE = (
    "Image previews and vision tools may composite transparent PNG pixels onto a black or white matte. "
    "That matte is not background color in the file. Do not judge PNG transparency from preview appearance; "
    "trust the decoded alpha and chroma evidence in this report."
)


class PngTransparencyError(ValueError):
    """Raised when a PNG fails the non-flaky transparency contract."""


@dataclass(frozen=True)
class PngTransparency:
    width: int
    height: int
    has_alpha_channel: bool
    has_alpha_below_255: bool
    has_alpha_above_0: bool
    opaque_bbox_nonempty: bool
    chroma_plate_ratio: float = 0.0
    transparent_pixel_ratio: float = 0.0
    visible_pixel_count: int = 0
    visible_chroma_pixel_count: int = 0
    visible_chroma_ratio: float = 0.0
    opaque_background: bool = False
    chroma_key: str = DEFAULT_CHROMA_KEY
    opaque_corner_count: int = 0


def png_transparency_report(result: PngTransparency) -> dict[str, Any]:
    """Serialize the successful transparency contract as stable agent-facing evidence.

    The inspector verdict remains authoritative. Consumers must not replace it with a
    shortcut based on one or two individual metrics because connected chroma-plate
    detection is part of the contract too.
    """
    return {
        "schemaVersion": "hydracept.png-transparency.v1",
        "verdict": "valid_transparent_sprite",
        "hasAlphaChannel": result.has_alpha_channel,
        "hasAlphaBelow255": result.has_alpha_below_255,
        "hasVisiblePixels": result.has_alpha_above_0,
        "opaqueBoundingBoxNonempty": result.opaque_bbox_nonempty,
        "transparentPixelRatio": result.transparent_pixel_ratio,
        "opaqueCornerCount": result.opaque_corner_count,
        "chromaPlateRatio": result.chroma_plate_ratio,
        "visiblePixelCount": result.visible_pixel_count,
        "visibleChromaPixelCount": result.visible_chroma_pixel_count,
        "visibleChromaRatio": result.visible_chroma_ratio,
        "opaqueBackground": result.opaque_background,
        "chromaKey": result.chroma_key,
        "width": result.width,
        "height": result.height,
        "agentNote": TRANSPARENCY_AGENT_NOTE,
    }


def inspect_png_transparency(
    data: bytes,
    *,
    key_color: str | None = None,
) -> PngTransparency:
    """Inspect an RGBA/GA PNG using rendered alpha semantics.

    RGB samples underneath alpha=0 (and near-transparent alpha below the documented
    visible threshold) are not rendered and therefore never participate in matte or
    chroma analysis. This is intentional: encoders are free to preserve arbitrary RGB
    in fully transparent pixels.

    Leftover chroma plate is a background field of the job's keyed color that is
    still connected to the canvas exterior through transparency. Subject pixels
    are not classified as plate merely because they are saturated blue or green.
    """
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise PngTransparencyError("not a PNG")
    offset = 8
    width = height = 0
    bit_depth = 0
    color_type = 0
    idat = bytearray()
    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        name = data[offset + 4 : offset + 8]
        start = offset + 8
        chunk = data[start : start + length]
        offset = start + length + 4
        if name == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", chunk[:10])
        elif name == b"IDAT":
            idat.extend(chunk)
        elif name == b"IEND":
            break
    if width <= 0 or height <= 0:
        raise PngTransparencyError("invalid IHDR")
    has_alpha_channel = color_type in {4, 6}
    if not has_alpha_channel:
        raise PngTransparencyError("PNG has no alpha channel")
    raw = zlib.decompress(bytes(idat))
    channels = 2 if color_type == 4 else 4
    bytes_per_pixel = max(1, (bit_depth * channels) // 8)
    stride = width * bytes_per_pixel
    prior = bytearray(stride)
    reconstituted = bytearray()
    cursor = 0
    for _row in range(height):
        if cursor >= len(raw):
            raise PngTransparencyError("truncated IDAT")
        filter_type = raw[cursor]
        cursor += 1
        scan = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        _paeth_unfilter(filter_type, scan, prior, bytes_per_pixel)
        reconstituted.extend(scan)
        prior = scan

    alpha_index = channels - 1
    below_255 = False
    above_0 = False
    transparent_pixels = 0
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1
    for y in range(height):
        row = reconstituted[y * stride : (y + 1) * stride]
        for x in range(width):
            if bit_depth == 16:
                alpha = int.from_bytes(
                    row[x * bytes_per_pixel + (channels - 1) * 2 : x * bytes_per_pixel + channels * 2],
                    "big",
                )
                opaque = 65535
            else:
                alpha = row[x * bytes_per_pixel + alpha_index]
                opaque = 255
            if alpha < opaque:
                below_255 = True
            if alpha > 0:
                above_0 = True
            if alpha == 0:
                transparent_pixels += 1
            if alpha > 0:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)

    total_pixels = max(1, width * height)
    transparent_ratio = transparent_pixels / total_pixels
    if not below_255:
        raise PngTransparencyError("alpha channel is present but every pixel is fully opaque")
    if not above_0:
        raise PngTransparencyError("no pixel with alpha > 0")
    bbox = max_x >= min_x and max_y >= min_y
    if not bbox:
        raise PngTransparencyError("visible bounding box is empty")

    plate_ratio = 0.0
    visible_pixels = 0
    leftover_plate = 0
    opaque_corners = 0
    key_hex = DEFAULT_CHROMA_KEY
    if bit_depth == 8 and color_type == 6:
        try:
            key = ChromaPlateKey.from_hex(key_color)
        except ValueError as exc:
            raise PngTransparencyError(str(exc)) from exc
        key_hex = key.hex
        measurement = ChromaPlateDetector(
            key,
            visible_alpha_threshold=_VISIBLE_ALPHA_THRESHOLD,
        ).measure(
            reconstituted,
            width=width,
            height=height,
            bytes_per_pixel=bytes_per_pixel,
            stride=stride,
        )
        visible_pixels = measurement.visible_count
        leftover_plate = measurement.leftover_plate_count
        plate_ratio = measurement.leftover_plate_ratio
        opaque_corners = measurement.opaque_corner_count
        if plate_ratio >= _MAX_CHROMA_PLATE_RATIO:
            raise PngTransparencyError(
                "leftover chroma plate connected to canvas "
                f"({plate_ratio:.0%} of visible pixels still keyed to {key_hex})"
            )
        if opaque_corners >= _OPAQUE_CORNER_FAILURE:
            raise PngTransparencyError(
                f"opaque canvas corners ({opaque_corners}/4) — expected an isolated transparent sprite"
            )

    return PngTransparency(
        width=width,
        height=height,
        has_alpha_channel=True,
        has_alpha_below_255=below_255,
        has_alpha_above_0=above_0,
        opaque_bbox_nonempty=bbox,
        chroma_plate_ratio=plate_ratio,
        transparent_pixel_ratio=transparent_ratio,
        visible_pixel_count=visible_pixels,
        visible_chroma_pixel_count=leftover_plate,
        visible_chroma_ratio=plate_ratio,
        opaque_background=not below_255,
        chroma_key=key_hex,
        opaque_corner_count=opaque_corners,
    )


def _paeth_predictor(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    pa = abs(estimate - left)
    pb = abs(estimate - up)
    pc = abs(estimate - up_left)
    if pa <= pb and pa <= pc:
        return left
    if pb <= pc:
        return up
    return up_left


def _paeth_unfilter(filter_type: int, scan: bytearray, prior: bytearray, bpp: int) -> None:
    if filter_type == 0:
        return
    for i, value in enumerate(scan):
        left = scan[i - bpp] if i >= bpp else 0
        up = prior[i]
        up_left = prior[i - bpp] if i >= bpp else 0
        if filter_type == 1:
            scan[i] = (value + left) & 255
        elif filter_type == 2:
            scan[i] = (value + up) & 255
        elif filter_type == 3:
            scan[i] = (value + ((left + up) // 2)) & 255
        elif filter_type == 4:
            scan[i] = (value + _paeth_predictor(left, up, up_left)) & 255
        else:
            raise PngTransparencyError(f"unsupported PNG filter {filter_type}")
