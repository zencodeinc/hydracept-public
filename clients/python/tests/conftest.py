"""Prefer the in-repo hydracept package; enforce hermetic tests (no prod network)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_CLIENTS_PYTHON = str(Path(__file__).resolve().parents[1])
if _CLIENTS_PYTHON not in sys.path:
    sys.path.insert(0, _CLIENTS_PYTHON)

# clients/python/tests/conftest.py -> parents[3] is the repository root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_API_TESTS = _REPO_ROOT / "apps" / "api" / "tests"
_GUARD = _API_TESTS / "network_guard_bootstrap.py"
if not _GUARD.is_file():
    raise ImportError(
        "HYDRACEPT_TESTS_SOCKET_GUARD requires "
        f"{_GUARD}; refusing to run clients/python tests without it"
    )
if str(_API_TESTS) not in sys.path:
    sys.path.insert(0, str(_API_TESTS))

os.environ["HYDRACEPT_TESTS_SOCKET_GUARD"] = "1"

from network_guard_bootstrap import install_socket_guard  # noqa: E402

install_socket_guard()
if not getattr(__import__("socket").socket.connect, "__hydracept_guard__", False):
    raise RuntimeError("socket guard failed to install; refusing to continue")
