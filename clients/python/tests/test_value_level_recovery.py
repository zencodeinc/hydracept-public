"""Error recovery must point at the invalid value, not generic discovery."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from hydracept.cli.run_facade import execute_run
from hydracept.cli.run_input_coercion import InputValidationError, coerce_capability_input
from hydracept.cli.workspace import ResolvedWorkspace


def _workspace() -> ResolvedWorkspace:
    return ResolvedWorkspace(
        api_url="https://api.hydracept.com",
        token="hapt_test",
        project_id="cpr_a",
        environment="development",
    )


def test_missing_prompt_recovery_names_prompt() -> None:
    with pytest.raises(InputValidationError) as excinfo:
        coerce_capability_input("image.generate.v1", {})
    error = excinfo.value
    payload = error.to_payload()
    assert error.field == "prompt"
    assert payload["details"]["field"] == "prompt"
    assert "--prompt" in payload["nextAction"]
    assert "capabilities describe" not in payload["nextAction"]


def test_translate_missing_locale_recovery_is_specific() -> None:
    with pytest.raises(InputValidationError) as excinfo:
        coerce_capability_input("text.translate.v1", {"prompt": "Hello"})
    error = excinfo.value
    payload = error.to_payload()
    assert error.field == "targetLocale"
    assert "--target-locale es" in payload["nextAction"]
    assert payload["errorClass"] == "INVALID_INPUT"


def test_execute_run_maps_validation_error_to_value_recovery(tmp_path: Path) -> None:
    with patch(
        "hydracept.cli.run_facade.require_execution_context",
        return_value=(_workspace(), None),
    ):
        outcome = execute_run(
            tmp_path,
            "image.generate.v1",
            {},
            wait=False,
            refresh_context=False,
        )
    assert outcome.exit_code == 1
    assert outcome.error is not None
    assert outcome.error.code == "InvalidInput"
    assert outcome.error.details["field"] == "prompt"
    assert outcome.error.error_class == "INVALID_INPUT"
    assert "--prompt" in (outcome.error.recovery.get("nextAction") or "")
