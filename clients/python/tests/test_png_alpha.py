"""PNG transparency contract — leftover plate is a background field of the keyed color."""

from __future__ import annotations

import struct
import zlib

import pytest

from hydracept.chroma_plate_key import ChromaPlateKey
from hydracept.png_alpha import PngTransparencyError, inspect_png_transparency


def _rgba_png(width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    assert len(pixels) == width * height
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        row = bytearray()
        for x in range(width):
            r, g, b, a = pixels[y * width + x]
            row.extend((r, g, b, a))
        raw.extend(row)
    compressed = zlib.compress(bytes(raw), level=9)
    ihdr = struct.pack(">I", 13) + b"IHDR" + header + struct.pack(">I", zlib.crc32(b"IHDR" + header) & 0xFFFFFFFF)
    idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(
        ">I", zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF
    )
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


def _filled(width: int, height: int, fill: tuple[int, int, int, int]) -> list[tuple[int, int, int, int]]:
    return [fill] * (width * height)


def _with_transparent_border(
    width: int,
    height: int,
    interior: tuple[int, int, int, int],
    *,
    border: int = 2,
) -> list[tuple[int, int, int, int]]:
    pixels: list[tuple[int, int, int, int]] = []
    for y in range(height):
        for x in range(width):
            on_border = x < border or y < border or x >= width - border or y >= height - border
            pixels.append((0, 0, 0, 0) if on_border else interior)
    return pixels


def test_interior_magenta_plate_fails() -> None:
    png = _rgba_png(32, 32, _with_transparent_border(32, 32, (220, 20, 220, 255)))
    with pytest.raises(PngTransparencyError, match="leftover chroma plate connected to canvas"):
        inspect_png_transparency(png)


def test_border_only_magenta_plate_fails() -> None:
    width = height = 32
    pixels = [
        (220, 20, 220, 255) if (x < 2 or y < 2) else (0, 0, 0, 0)
        for y in range(height)
        for x in range(width)
    ]
    with pytest.raises(PngTransparencyError, match="leftover chroma plate connected to canvas"):
        inspect_png_transparency(_rgba_png(width, height, pixels))


def test_arbitrary_rgb_under_zero_alpha_is_ignored() -> None:
    width = height = 32
    pixels: list[tuple[int, int, int, int]] = []
    for y in range(height):
        for x in range(width):
            inside = 10 <= x < 22 and 10 <= y < 22
            if inside:
                pixels.append((80, 120, 200, 255))
            else:
                pixels.append((0, 255, 0, 0) if (x + y) % 2 else (255, 0, 255, 0))
    result = inspect_png_transparency(_rgba_png(width, height, pixels))
    assert result.has_alpha_channel is True
    assert result.transparent_pixel_ratio == pytest.approx((width * height - 12 * 12) / (width * height))
    assert result.visible_chroma_pixel_count == 0
    assert result.visible_chroma_ratio == 0.0
    assert result.opaque_background is False


def test_alpha_channel_with_every_alpha_255_fails_transparency_requirement() -> None:
    width = height = 8
    pixels = [(60, 80, 100, 255)] * (width * height)
    with pytest.raises(PngTransparencyError, match="every pixel is fully opaque"):
        inspect_png_transparency(_rgba_png(width, height, pixels))


def test_blue_subject_on_transparent_canvas_is_not_a_plate() -> None:
    """wfr_ma2ju573zg3c — isolated blue slime is the subject, not leftover cyan."""
    assert ChromaPlateKey.from_hex("#00ffff").matches(2, 203, 254) is False
    assert ChromaPlateKey.from_hex("#ff00ff").matches(220, 20, 220) is True
    png = _rgba_png(32, 32, _with_transparent_border(32, 32, (2, 203, 254, 255), border=4))
    result = inspect_png_transparency(png)
    assert result.visible_chroma_pixel_count == 0
    assert result.chroma_key == "#ff00ff"


def test_cyan_plate_fails_when_that_key_was_used() -> None:
    png = _rgba_png(32, 32, _with_transparent_border(32, 32, (8, 248, 252, 255)))
    with pytest.raises(PngTransparencyError, match="keyed to #00ffff"):
        inspect_png_transparency(png, key_color="#00ffff")
    result = inspect_png_transparency(png)
    assert result.visible_chroma_pixel_count == 0


def test_magenta_fill_behind_dark_outline_is_subject() -> None:
    """Histogram of keyed RGB would fail; border flood-fill must stop at the outline."""
    width = height = 24
    pixels = _filled(width, height, (0, 0, 0, 0))
    for y in range(4, 20):
        for x in range(4, 20):
            edge = x in {4, 19} or y in {4, 19}
            pixels[y * width + x] = (10, 10, 10, 255) if edge else (220, 20, 220, 255)
    result = inspect_png_transparency(_rgba_png(width, height, pixels))
    assert result.visible_chroma_pixel_count == 0


def test_opaque_non_key_corners_fail_isolation() -> None:
    width = height = 16
    pixels = [(40, 180, 40, 255)] * (width * height)
    for y in range(4, 12):
        for x in range(4, 12):
            pixels[y * width + x] = (80, 120, 200, 255)
    pixels[5 * width + 5] = (80, 120, 200, 200)
    with pytest.raises(PngTransparencyError, match="opaque canvas corners"):
        inspect_png_transparency(_rgba_png(width, height, pixels))


def test_clean_transparent_edge_passes() -> None:
    width = height = 16
    pixels: list[tuple[int, int, int, int]] = []
    for y in range(height):
        for x in range(width):
            distance = min(x, y, width - 1 - x, height - 1 - y)
            if distance < 3:
                pixels.append((11, 222, 33, 0))
            elif distance == 3:
                pixels.append((80, 120, 200, 96))
            else:
                pixels.append((80, 120, 200, 255))
    result = inspect_png_transparency(_rgba_png(width, height, pixels))
    assert result.transparent_pixel_ratio > 0
    assert result.visible_chroma_ratio == 0.0
