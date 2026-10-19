"""CLI ergonomics for capability discovery."""

from __future__ import annotations

from typer.testing import CliRunner

from hydracept.cli.main import app


def test_capabilities_without_subcommand_prints_help() -> None:
    result = CliRunner().invoke(app, ["capabilities"])
    assert result.exit_code == 0
    assert "list" in result.stdout.lower()
    assert "Missing command" not in result.stdout
