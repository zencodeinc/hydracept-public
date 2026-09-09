"""Load consumer JSON files written by Windows/PowerShell editors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def decode_consumer_json_bytes(raw: bytes) -> str:
    """Decode UTF-8/UTF-16 JSON, including PowerShell BOM encodings."""
    if raw.startswith(b"\xff\xfe\x00\x00") or raw.startswith(b"\x00\x00\xfe\xff"):
        return raw.decode("utf-32")
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def read_json_file(path: Path) -> Any:
    return json.loads(decode_consumer_json_bytes(path.read_bytes()))
