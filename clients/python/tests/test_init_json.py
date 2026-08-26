"""Tests for init JSON contract (ADR-028)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from hydracept.cli.init_resolver import INIT_SCHEMA_VERSION, run_init


def test_init_requires_apply_json() -> None:
    result = run_init(Path.cwd(), apply=False, json_output=True)
    assert result.exit_code == 2
    assert result.payload["status"] == "interaction_required"
    assert result.payload.get("reason") == "apply_required"


def test_init_interaction_required_without_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    result = run_init(tmp_path, apply=True, yes=True, json_output=True)
    assert result.exit_code == 0
    assert result.payload["status"] == "interaction_required"
    assert result.payload["action"]["type"] == "open_url"
    assert "apiKey" not in json.dumps(result.payload)


def test_init_ci_missing_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    result = run_init(tmp_path, apply=True, yes=True, json_output=True, ci_mode=True)
    assert result.payload["status"] == "configuration_required"
    assert result.payload["reason"] == "missing_api_key"
