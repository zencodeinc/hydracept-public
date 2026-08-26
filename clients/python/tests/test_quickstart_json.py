"""Tests for quickstart JSON contract (ADR-019)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from hydracept.cli.bootstrap import ConfigureError
from hydracept.cli.quickstart import QUICKSTART_SCHEMA_VERSION, run_quickstart


def test_quickstart_missing_token_json() -> None:
    result = run_quickstart(Path.cwd(), token=None, json_output=True)
    assert result.exit_code == 2
    assert result.payload["schemaVersion"] == QUICKSTART_SCHEMA_VERSION
    assert result.payload["error"] == "credential_required"
    assert result.payload["status"] == "unconfigured"
    assert "nextActions" in result.payload
    assert "apiKey" not in result.payload


def test_quickstart_empty_token_json() -> None:
    result = run_quickstart(Path.cwd(), token="", json_output=True)
    assert result.exit_code == 2
    assert result.payload["error"] == "empty_token"
    assert result.payload["steps"]["login"]["detail"] == "Empty --token"


def test_quickstart_login_writes_secrets_without_configure(tmp_path: Path) -> None:
    with patch(
        "hydracept.cli.quickstart.run_configure",
        side_effect=ConfigureError("fail"),
    ):
        result = run_quickstart(tmp_path, token="hapt_test", json_output=True)
    assert result.payload["steps"]["login"]["status"] == "succeeded"
    assert (tmp_path / ".hydracept" / "secrets.json").is_file()
    assert "hapt_test" not in json.dumps(result.payload)
