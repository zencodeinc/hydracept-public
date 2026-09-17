"""Executable contradiction check for the CLI surface advertised to agents (ADR-034)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hydracept.cli.agent_surface import advertised_commands, command_accepts
from hydracept.cli.exit_codes import USAGE
from hydracept.cli.init_resolver import run_init


def test_init_apply_yes_json_is_accepted() -> None:
    assert command_accepts(["init"], ["--apply", "--yes", "--json"]) is True


def test_init_ci_json_flags_are_registered() -> None:
    """Measured result: `--ci` is a real declared option on `init`.

    This is the drift the ADR calls out, but it is a *resolver* rejection, not a phantom
    flag: `main.py::init_cmd` declares `--ci`, and `init_resolver.run_init` refuses the
    invocation unless `--apply` is present. A checker built only on flag existence sees
    `True` here, so it must add resolver acceptance to catch `init --ci --json`.
    """
    assert command_accepts(["init"], ["--ci", "--json"]) is True
    assert "--ci" in advertised_commands()["init"]


def test_init_ci_json_is_rejected_by_the_resolver_without_apply(tmp_path: Path) -> None:
    result = run_init(tmp_path, apply=False, yes=False, json_output=True, ci_mode=True)

    assert result.exit_code == USAGE
    assert result.payload["status"] == "interaction_required"
    assert result.payload["reason"] == "apply_required"


def test_init_apply_clears_the_apply_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.delenv("HYDRACEPT_TOKEN", raising=False)
    result = run_init(tmp_path, apply=True, yes=True, json_output=True, ci_mode=True)

    assert result.payload.get("reason") != "apply_required"
    assert result.payload["reason"] == "missing_api_key"


def test_unknown_command_path_returns_false() -> None:
    assert command_accepts(["not-a-command"], ["--json"]) is False
    assert command_accepts(["init", "bogus"], ["--json"]) is False
    assert command_accepts([], ["--json"]) is False


def test_known_command_rejects_unknown_flag() -> None:
    assert command_accepts(["init"], ["--json", "--not-a-flag"]) is False
    assert command_accepts(["mcp"], ["--json"]) is False


def test_advertised_commands_includes_init_and_mcp_serve() -> None:
    registry = advertised_commands()

    assert "init" in registry
    assert "--apply" in registry["init"]
    assert "--yes" in registry["init"]
    assert "--json" in registry["init"]

    assert "mcp serve" in registry
    assert "--workspace" in registry["mcp serve"]


def test_nested_typer_groups_are_walked() -> None:
    assert command_accepts(["integrations", "install", "unity"], ["--project-root", "--version"])
    assert command_accepts(["jobs", "submit"], ["--watch"])
    assert command_accepts(["panels", "session", "create"], ["--max-jobs"])


def test_option_forms_include_negated_secondary_opts() -> None:
    assert command_accepts(["login"], ["--open", "--no-open"])
    assert command_accepts(["context"], ["--json", "--no-json"])
    assert command_accepts(["jobs", "recover"], ["--wait", "--no-wait"])


def test_positional_arguments_are_not_advertised_as_flags() -> None:
    registry = advertised_commands()

    assert "capability" not in registry["run"]
    assert "key" not in registry["quote"]
    assert "body" not in registry["quote"]
    assert "capabilities quote" in registry


def test_registry_copy_does_not_mutate_the_authority() -> None:
    registry = advertised_commands()
    registry["init"] = ()

    assert advertised_commands()["init"] != ()
