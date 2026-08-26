"""Prefer the in-repo hydracept package over a separately installed wheel."""

from __future__ import annotations

import sys
from pathlib import Path

_CLIENTS_PYTHON = str(Path(__file__).resolve().parents[1])
if _CLIENTS_PYTHON not in sys.path:
    sys.path.insert(0, _CLIENTS_PYTHON)
