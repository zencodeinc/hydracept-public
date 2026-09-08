"""Agent stdio line-buffering for piped coding-agent shells."""

from __future__ import annotations

import io
import sys

import pytest

from hydracept.stdio import configure_agent_stdio


def test_configure_agent_stdio_enables_line_buffering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout_buffer = io.BytesIO()
    monkeypatch.setattr(
        sys,
        "stdout",
        io.TextIOWrapper(stdout_buffer, encoding="utf-8", errors="strict", line_buffering=False),
    )
    monkeypatch.setattr("hydracept.stdio._CONFIGURED", False)
    configure_agent_stdio()
    assert sys.stdout.line_buffering is True
