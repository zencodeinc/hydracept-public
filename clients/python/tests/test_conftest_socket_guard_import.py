"""clients/python tests install the socket guard without apps/api/tests on PYTHONPATH."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]


def test_conftest_imports_guard_when_pythonpath_is_only_the_client() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_REPO / "clients" / "python")
    env["HYDRACEPT_TESTS_SOCKET_GUARD"] = "1"
    conftest = _REPO / "clients" / "python" / "tests" / "conftest.py"
    script = (
        "import importlib.util, socket\n"
        "from pathlib import Path\n"
        f"path = Path({str(conftest)!r})\n"
        "spec = importlib.util.spec_from_file_location('client_conftest_probe', path)\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "assert spec.loader is not None\n"
        "spec.loader.exec_module(mod)\n"
        "assert getattr(socket.socket.connect, '__hydracept_guard__', False)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(_REPO),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
