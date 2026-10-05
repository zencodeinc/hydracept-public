from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from hydracept.cli.main import app


runner = CliRunner()


def test_init_apply_yes_without_adopt_does_not_upload(tmp_path: Path) -> None:
    with (
        patch("hydracept.cli.main.unified_bootstrap_enabled", return_value=True),
        patch("hydracept.cli.main.run_init") as run_init,
    ):
        run_init.return_value = MagicMock(exit_code=0, payload={"status": "ready", "providers": {}})
        result = runner.invoke(app, ["init", "--project-root", str(tmp_path), "--apply", "--yes"])
        assert result.exit_code == 0
        kwargs = run_init.call_args.kwargs
        assert kwargs.get("no_adopt") is False
        assert kwargs.get("adopt_providers") is None


def test_init_no_adopt_flag(tmp_path: Path) -> None:
    with (
        patch("hydracept.cli.main.unified_bootstrap_enabled", return_value=True),
        patch("hydracept.cli.main.run_init") as run_init,
    ):
        run_init.return_value = MagicMock(exit_code=0, payload={"status": "ready"})
        runner.invoke(app, ["init", "--project-root", str(tmp_path), "--apply", "--yes", "--no-adopt"])
        assert run_init.call_args.kwargs.get("adopt_providers") == frozenset()


def test_init_adopt_keys_and_no_adopt_errors(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["init", "--project-root", str(tmp_path), "--apply", "--yes", "--adopt-keys", "--no-adopt"],
    )
    assert result.exit_code != 0
    assert "adopt" in result.output.lower() or "no-adopt" in result.output.lower()


def test_init_bare_adopt_keys(tmp_path: Path) -> None:
    with (
        patch("hydracept.cli.main.unified_bootstrap_enabled", return_value=True),
        patch("hydracept.cli.main.run_init") as run_init,
    ):
        run_init.return_value = MagicMock(exit_code=0, payload={"status": "ready"})
        # Non-TTY environments (CI, CliRunner) must use --adopt-key-providers; same adopt set as --adopt-keys.
        runner.invoke(
            app,
            [
                "init",
                "--project-root",
                str(tmp_path),
                "--apply",
                "--yes",
                "--adopt-key-providers",
                "*",
            ],
        )
        assert run_init.call_args.kwargs.get("adopt_providers") == frozenset({"*"})
