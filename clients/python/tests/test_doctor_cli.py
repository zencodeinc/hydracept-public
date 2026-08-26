"""CLI integration tests for hydracept doctor (encoding + subprocess smoke)."""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path
from typing import TextIO

import pytest

from hydracept.cli.console_io import configure_stdio_utf8
from hydracept.cli.doctor import DoctorCheck, DoctorReport, _finish, run_doctor
from hydracept.cli.exit_codes import AUTH
from rich.console import Console

CLIENTS_PYTHON = Path(__file__).resolve().parents[1]
REPO_ROOT = CLIENTS_PYTHON.parents[1]


@pytest.fixture
def cp1252_stdio(monkeypatch: pytest.MonkeyPatch) -> TextIO:
    """Legacy Windows console: cp1252 cannot encode → (U+2192) or — (U+2014)."""
    stdout_buffer = io.BytesIO()
    stderr_buffer = io.BytesIO()
    stdout = io.TextIOWrapper(
        stdout_buffer,
        encoding="cp1252",
        errors="strict",
        line_buffering=True,
    )
    stderr = io.TextIOWrapper(
        stderr_buffer,
        encoding="cp1252",
        errors="strict",
        line_buffering=True,
    )
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setattr("hydracept.cli.console_io._STDIO_CONFIGURED", False)
    return stdout


def test_finish_raises_on_cp1252_without_utf8_reconfigure() -> None:
    stdout_buffer = io.BytesIO()
    stdout = io.TextIOWrapper(
        stdout_buffer,
        encoding="cp1252",
        errors="strict",
        line_buffering=True,
    )
    console = Console(file=stdout, force_terminal=False)
    report = DoctorReport()
    report.add(
        DoctorCheck(
            "local.credential",
            False,
            "No API credential — activate",
            next_action="python -m hydracept login",
        )
    )
    with pytest.raises(UnicodeEncodeError):
        _finish(report, console, json_output=False)


def test_finish_renders_unicode_next_steps_on_cp1252_stdout(
    cp1252_stdio: TextIO,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_stdio_utf8()
    console = Console()
    report = DoctorReport()
    report.add(
        DoctorCheck(
            "local.credential",
            False,
            "No workspace API credential",
            next_action="python -m hydracept login",
        )
    )
    code = _finish(report, console, json_output=False)
    assert code == AUTH
    out = capsys.readouterr().out
    assert "Next" in out
    assert "→" in out
    assert "—" in out


def test_run_doctor_without_credentials_on_cp1252_stdout(
    tmp_path: Path,
    cp1252_stdio: TextIO,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = run_doctor("https://api.hydracept.com", tmp_path, None, json_output=False)
    assert code == AUTH
    out = capsys.readouterr().out
    assert "Hydracept doctor" in out
    assert "→" in out


def test_run_doctor_json_on_cp1252_stdout(
    tmp_path: Path,
    cp1252_stdio: TextIO,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = run_doctor("https://api.hydracept.com", tmp_path, None, json_output=True)
    assert code == AUTH
    out = capsys.readouterr().out
    assert "nextActions" in out


def test_doctor_subprocess_smoke_from_wheel() -> None:
    """Mirrors scripts/smoke_public_packages.py — doctor must not crash on Unicode output."""
    result = subprocess.run(
        [sys.executable, "-m", "hydracept", "doctor"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={
            **dict(__import__("os").environ),
            "PYTHONPATH": str(CLIENTS_PYTHON),
        },
    )
    combined = (result.stdout or "") + (result.stderr or "")
    assert "UnicodeEncodeError" not in combined
    assert result.returncode in (0, AUTH, 6)
    if result.returncode == 1:
        assert "doctor" in combined.lower()
