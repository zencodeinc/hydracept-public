"""Console I/O helpers for the public CLI."""

from __future__ import annotations

import io
import sys

import pytest

from hydracept.cli.console_io import cli_console, configure_stdio_utf8


def test_cli_console_prints_unicode() -> None:
    configure_stdio_utf8()
    console = cli_console()
    console.print("  → next step — done")


def test_configure_stdio_utf8_upgrades_cp1252_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout_buffer = io.BytesIO()
    monkeypatch.setattr(
        sys,
        "stdout",
        io.TextIOWrapper(stdout_buffer, encoding="cp1252", errors="strict", line_buffering=True),
    )
    monkeypatch.setattr("hydracept.cli.console_io._STDIO_CONFIGURED", False)
    configure_stdio_utf8()
    assert sys.stdout.encoding.lower().replace("-", "") == "utf8"
