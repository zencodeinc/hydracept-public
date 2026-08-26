"""Stable machine fingerprint for bootstrap trust."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

_MACHINE_DIR = Path.home() / ".hydracept"
_MACHINE_FILE = _MACHINE_DIR / "machine.json"


def _ensure_install_id() -> str:
    _MACHINE_DIR.mkdir(parents=True, exist_ok=True)
    if _MACHINE_FILE.exists():
        try:
            payload = json.loads(_MACHINE_FILE.read_text(encoding="utf-8"))
            install_id = str(payload.get("installId") or "").strip()
            if install_id:
                return install_id
        except (OSError, json.JSONDecodeError):
            pass
    install_id = str(uuid.uuid4())
    _MACHINE_FILE.write_text(
        json.dumps({"schemaVersion": 1, "installId": install_id}, indent=2) + "\n",
        encoding="utf-8",
    )
    return install_id


def machine_fingerprint() -> str:
    install_id = _ensure_install_id()
    hostname = (os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "unknown").strip()
    user = (os.environ.get("USERNAME") or os.environ.get("USER") or "unknown").strip()
    material = f"{user}\0{hostname}\0{install_id}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
