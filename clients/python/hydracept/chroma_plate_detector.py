"""Detect leftover chroma plate as a background field, not as subject hue.

A leftover plate is keyed-RGB pixels reachable from the canvas border by walking
through hidden (low-alpha) pixels and other keyed pixels. Subject pixels — even
saturated blue or green — are not walkable, so a blue slime on a punched-out
background is not a cyan plate.
"""

from __future__ import annotations

from collections import deque

from hydracept.chroma_plate_key import ChromaPlateKey
from hydracept.chroma_plate_measurement import ChromaPlateMeasurement

_HIDDEN = 0
_KEY = 1
_SUBJECT = 2


class ChromaPlateDetector:
    def __init__(
        self,
        key: ChromaPlateKey,
        *,
        visible_alpha_threshold: int = 16,
    ) -> None:
        self._key = key
        self._visible_alpha = visible_alpha_threshold

    def measure(
        self,
        reconstituted: bytes | bytearray,
        *,
        width: int,
        height: int,
        bytes_per_pixel: int,
        stride: int,
    ) -> ChromaPlateMeasurement:
        kind = bytearray(width * height)
        visible = 0
        opaque_corners = 0
        for y in range(height):
            row_off = y * stride
            for x in range(width):
                pix = row_off + x * bytes_per_pixel
                red = reconstituted[pix]
                green = reconstituted[pix + 1]
                blue = reconstituted[pix + 2]
                alpha = reconstituted[pix + 3]
                index = y * width + x
                if alpha < self._visible_alpha:
                    kind[index] = _HIDDEN
                    continue
                visible += 1
                if x in {0, width - 1} and y in {0, height - 1}:
                    opaque_corners += 1
                if self._key.matches(red, green, blue):
                    kind[index] = _KEY
                else:
                    kind[index] = _SUBJECT

        leftover = self._border_connected_key_count(kind, width, height)
        ratio = leftover / max(1, visible)
        return ChromaPlateMeasurement(
            visible_count=visible,
            leftover_plate_count=leftover,
            leftover_plate_ratio=ratio,
            opaque_corner_count=opaque_corners,
            key_hex=self._key.hex,
        )

    def _border_connected_key_count(
        self,
        kind: bytearray,
        width: int,
        height: int,
    ) -> int:
        seen = bytearray(width * height)
        queue: deque[int] = deque()

        def try_enqueue(x: int, y: int) -> None:
            if x < 0 or y < 0 or x >= width or y >= height:
                return
            index = y * width + x
            if seen[index] or kind[index] == _SUBJECT:
                return
            seen[index] = 1
            queue.append(index)

        for x in range(width):
            try_enqueue(x, 0)
            try_enqueue(x, height - 1)
        for y in range(height):
            try_enqueue(0, y)
            try_enqueue(width - 1, y)

        leftover = 0
        while queue:
            index = queue.popleft()
            if kind[index] == _KEY:
                leftover += 1
            y, x = divmod(index, width)
            try_enqueue(x - 1, y)
            try_enqueue(x + 1, y)
            try_enqueue(x, y - 1)
            try_enqueue(x, y + 1)
        return leftover
