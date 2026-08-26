"""Tests for configure/bootstrap (ADR-019)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from hydracept.cli.bootstrap import ConfigureError, run_configure, write_secrets


def test_configure_fast_path_skips_bootstrap_free(tmp_path: Path) -> None:
    write_secrets(tmp_path, {"apiKey": "existing-key", "kind": "service_principal"})
    session = {
        "needsOnboarding": False,
        "project": {"id": "cpr_1", "displayName": "Demo"},
        "environment": {"slug": "development"},
        "organization": {"id": "org_1"},
    }

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return session

    with patch("hydracept.cli.bootstrap.httpx.get", return_value=FakeResponse()):
        result = run_configure(tmp_path, token="existing-key")
    assert result.bootstrap_called is False
    assert (tmp_path / ".hydracept" / "config.json").is_file()


def test_configure_requires_credential(tmp_path: Path) -> None:
    with pytest.raises(ConfigureError):
        run_configure(tmp_path)
