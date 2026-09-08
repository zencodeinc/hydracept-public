"""Production chroma-key identity for leftover-plate detection.

Hydracept keys backgrounds to one of three hex plates. A leftover plate pixel
is near that keyed RGB — not merely a saturated secondary hue.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_CHROMA_KEY = "#ff00ff"
ALLOWED_CHROMA_KEYS = frozenset({"#ff00ff", "#00ffff", "#00ff00"})
# Leftover plate stays close to the keyed RGB. (220, 20, 220) vs #ff00ff is 35.
# Royal blue (2, 203, 254) vs #00ffff is 52 and is a subject, not cyan plate.
KEY_MATCH_MAX_CHEBYSHEV = 40


def normalize_chroma_key_hex(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return DEFAULT_CHROMA_KEY
    if not raw.startswith("#"):
        raw = f"#{raw}"
    key = raw.lower()
    if key not in ALLOWED_CHROMA_KEYS:
        raise ValueError(f"unsupported chroma key {value!r}")
    return key


def hex_to_rgb(key_hex: str) -> tuple[int, int, int]:
    key = normalize_chroma_key_hex(key_hex)
    return (int(key[1:3], 16), int(key[3:5], 16), int(key[5:7], 16))


@dataclass(frozen=True)
class ChromaPlateKey:
    hex: str
    red: int
    green: int
    blue: int
    max_chebyshev: int = KEY_MATCH_MAX_CHEBYSHEV

    @classmethod
    def from_hex(cls, value: str | None = None) -> ChromaPlateKey:
        key = normalize_chroma_key_hex(value)
        red, green, blue = hex_to_rgb(key)
        return cls(hex=key, red=red, green=green, blue=blue)

    def matches(self, red: int, green: int, blue: int) -> bool:
        distance = max(
            abs(red - self.red),
            abs(green - self.green),
            abs(blue - self.blue),
        )
        return distance <= self.max_chebyshev
