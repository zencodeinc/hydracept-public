"""Result of leftover chroma-plate measurement on a decoded RGBA buffer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChromaPlateMeasurement:
    visible_count: int
    leftover_plate_count: int
    leftover_plate_ratio: float
    opaque_corner_count: int
    key_hex: str
