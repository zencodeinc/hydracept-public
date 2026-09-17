"""Quote/run coercion parity invariant."""

from __future__ import annotations

from typing import Any

from click.testing import CliRunner
from hydracept.cli import entrypoint
from hydracept.cli.main import app as typer_app
from hydracept.cli.workspace import ResolvedWorkspace


def _command(*path: str) -> Any:
    from typer.main import get_command

    command = get_command(typer_app)
    for segment in path:
        command = command.commands[segment]
    return command


def _options(command: Any) -> set[str]:
    return {
        option
        for param in getattr(command, "params", [])
        for option in (getattr(param, "opts", None) or [])
    }


def test_run_and_quote_share_ergonomic_input_options() -> None:
    run_opts = _options(_command("run"))
    quote_opts = _options(_command("capabilities", "quote"))
    for option in ("--prompt", "--target-locale", "--input-file", "--input"):
        assert option in run_opts, option
        assert option in quote_opts, option


def test_quote_applies_same_translate_coercion_as_run(monkeypatch) -> None:
    from hydracept.cli import main as cli_main

    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def quote_capability(self, key: str, body: dict) -> dict:
            captured["key"] = key
            captured["payload"] = body
            return {"pricing": {"quote": {"customerTotal": {"amountMicros": 0}}}}

    monkeypatch.setattr(
        cli_main,
        "_execution_workspace",
        lambda *args, **kwargs: ResolvedWorkspace(
            api_url="https://api.hydracept.com",
            token="hapt_test",
            project_id="cpr_a",
            environment="development",
        ),
    )
    monkeypatch.setattr(cli_main, "HydraceptClient", FakeClient)

    result = CliRunner().invoke(
        entrypoint.app,
        [
            "capabilities",
            "quote",
            "text.translate.v1",
            "--prompt",
            "Hello",
            "--target-locale",
            "es",
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured["key"] == "text.translate.v1"
    assert captured["payload"]["targetLocale"] == "es"
    assert captured["payload"]["items"] == [{"id": "1", "text": "Hello"}]
    assert "prompt" not in captured["payload"]


def test_quote_missing_locale_reports_value_recovery(monkeypatch) -> None:
    from hydracept.cli import main as cli_main

    monkeypatch.setattr(
        cli_main,
        "_execution_workspace",
        lambda *args, **kwargs: ResolvedWorkspace(
            api_url="https://api.hydracept.com",
            token="hapt_test",
            project_id="cpr_a",
            environment="development",
        ),
    )
    result = CliRunner().invoke(
        entrypoint.app,
        ["capabilities", "quote", "text.translate.v1", "--prompt", "Hello"],
    )
    assert result.exit_code != 0
    assert "targetLocale" in result.output
    assert "--target-locale" in result.output
