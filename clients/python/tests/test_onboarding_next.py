"""Tests for onboarding next-step copy."""

from __future__ import annotations

from pathlib import Path

from hydracept.cli.onboarding_next import credential_setup_next_steps, no_credential_detail


def test_no_credential_detail_points_to_init() -> None:
    detail = no_credential_detail(Path("/tmp/nowhere"))
    assert "python -m hydracept init" in detail
    assert "hydracept.com/start" in detail


def test_credential_steps_suggest_init(tmp_path: Path) -> None:
    steps = credential_setup_next_steps(tmp_path)
    assert steps[0] == "python -m hydracept init"
    assert any("--token" in step for step in steps)
