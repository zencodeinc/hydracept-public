"""Package version is part of the public Python SDK surface."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import hydracept

CLIENTS_PYTHON = Path(__file__).resolve().parents[1]
REPO_ROOT = CLIENTS_PYTHON.parents[1]
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+")


def test_module_exposes_version() -> None:
    assert isinstance(hydracept.__version__, str)
    assert _VERSION_RE.match(hydracept.__version__)


def test_version_matches_pyproject() -> None:
    pyproject = (CLIENTS_PYTHON / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
    assert match is not None
    assert hydracept.__version__ == match.group(1)


def test_cli_version_flag() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "hydracept", "--version"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(CLIENTS_PYTHON),
        },
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip() == hydracept.__version__
