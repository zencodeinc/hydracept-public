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


def test_cli_version_json_flag() -> None:
    import json

    result = subprocess.run(
        [sys.executable, "-m", "hydracept", "--version", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(CLIENTS_PYTHON),
        },
    )
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["version"] == hydracept.__version__
    assert payload["packagePath"]
    assert payload["distribution"]["source"] in {
        "installed-package",
        "editable-install",
        "source-checkout",
        "unknown",
    }


def test_consumer_version_report_includes_workspace_versions(tmp_path: Path) -> None:
    from hydracept.cli.consumer_versions import consumer_version_report

    (tmp_path / ".hydracept").mkdir()
    payload = consumer_version_report(tmp_path)
    assert payload["version"] == hydracept.__version__
    assert "consumer" in payload
    assert payload["consumer"]["installedClient"] == hydracept.__version__


def test_cli_version_command_json() -> None:
    import json

    result = subprocess.run(
        [sys.executable, "-m", "hydracept", "version", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(CLIENTS_PYTHON),
        },
    )
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["version"] == hydracept.__version__
