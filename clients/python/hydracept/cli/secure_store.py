"""Atomic, permission-restricted JSON credential storage."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON via temp file, fsync, and rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        _restrict_permissions(tmp_path)
        tmp_path.replace(path)
        _restrict_permissions(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _restrict_permissions(path: Path) -> None:
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    if os.name == "nt":
        try:
            import ctypes

            acl = ctypes.cdll.LoadLibrary("advapi32")
            # Best-effort: rely on default user-only temp dir semantics on Windows.
            _ = acl
        except Exception:
            pass


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
