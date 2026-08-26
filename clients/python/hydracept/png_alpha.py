"""PNG transparency checks without occupancy percentages."""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass


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


def inspect_png_transparency(data: bytes) -> PngTransparency:
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
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1
    for y in range(height):
        row = reconstituted[y * stride : (y + 1) * stride]
        for x in range(width):
            alpha = row[x * bytes_per_pixel + alpha_index]
            if bit_depth == 16:
                alpha = int.from_bytes(
                    row[x * bytes_per_pixel + (channels - 1) * 2 : x * bytes_per_pixel + channels * 2],
                    "big",
                )
                opaque = 65535
            else:
                opaque = 255
            if alpha < opaque:
                below_255 = True
            if alpha > 0:
                above_0 = True
            if alpha > 0:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if not below_255:
        raise PngTransparencyError("no pixel with alpha < 255")
    if not above_0:
        raise PngTransparencyError("no pixel with alpha > 0")
    bbox = max_x >= min_x and max_y >= min_y
    if not bbox:
        raise PngTransparencyError("opaque bounding box is empty")
    return PngTransparency(
        width=width,
        height=height,
        has_alpha_channel=True,
        has_alpha_below_255=below_255,
        has_alpha_above_0=above_0,
        opaque_bbox_nonempty=bbox,
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
