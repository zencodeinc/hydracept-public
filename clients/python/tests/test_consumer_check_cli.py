"""Consumer-check CLI regression coverage."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from hydracept.cli.main import app
from hydracept.consumer_boundary import scan_path

runner = CliRunner()


def test_strict_scans_configuration_files(tmp_path: Path) -> None:
    provider_host = "api." + "openai.com"
    (tmp_path / "service.yaml").write_text(
        f"provider: https://{provider_host}/v1\n",
        encoding="utf-8",
    )

    standard_code, _ = scan_path(tmp_path, strict=False)
    strict_code, strict_detail = scan_path(tmp_path, strict=True)

    assert standard_code == 0
    assert strict_code == 1
    assert f"service.yaml: direct provider host {provider_host}" in strict_detail


def test_consumer_check_json_success(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("print('hydracept consumer')\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["consumer-check", "--path", str(tmp_path), "--strict", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schemaVersion"] == "hydracept.cli.consumer-check.v1"
    assert payload["passed"] is True
    assert payload["strict"] is True
    assert payload["path"] == str(tmp_path.resolve())


def test_consumer_check_json_failure(tmp_path: Path) -> None:
    provider_host = "api." + "anthropic.com"
    (tmp_path / "client.py").write_text(
        f"URL = 'https://{provider_host}/v1/messages'\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["consumer-check", "--path", str(tmp_path), "--strict", "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["passed"] is False
    assert payload["strict"] is True
    assert provider_host in payload["detail"]
