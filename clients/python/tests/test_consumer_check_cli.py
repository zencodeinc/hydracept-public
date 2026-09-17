"""Consumer-check CLI regression coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from hydracept.cli.main import app
from hydracept.consumer_boundary import scan, scan_path

runner = CliRunner()


def _provider_host() -> str:
    # Split so this test file itself never contains a forbidden literal.
    return "api." + "openai.com"


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


@pytest.mark.parametrize(
    "excluded_dir",
    [
        ".hydracept",
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".next",
        ".turbo",
        "coverage",
        "out",
        "obj",
        "bin",
    ],
)
def test_excluded_directories_are_not_reported(tmp_path: Path, excluded_dir: str) -> None:
    host = _provider_host()
    scratch = tmp_path / excluded_dir
    scratch.mkdir()
    (scratch / "generated.py").write_text(f"URL = 'https://{host}/v1'\n", encoding="utf-8")

    assert scan(tmp_path) == []


def test_excluded_hydracept_state_passes_scan_path(tmp_path: Path) -> None:
    host = _provider_host()
    state = tmp_path / ".hydracept"
    state.mkdir()
    (state / "agent-context.json").write_text(
        json.dumps({"endpoint": f"https://{host}/v1"}) + "\n",
        encoding="utf-8",
    )

    code, detail = scan_path(tmp_path, strict=True)

    assert code == 0, detail


def test_excluded_directory_does_not_hide_authored_sibling(tmp_path: Path) -> None:
    host = _provider_host()
    scratch = tmp_path / "node_modules"
    scratch.mkdir()
    (scratch / "dep.py").write_text(f"URL = 'https://{host}/v1'\n", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(f"URL = 'https://{host}/v1'\n", encoding="utf-8")

    assert scan(tmp_path) == [f"src/app.py: direct provider host {host} [code] (line 1)"]


def test_authored_source_violation_is_still_reported_with_location(tmp_path: Path) -> None:
    host = _provider_host()
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.ts").write_text(f'const url = "https://{host}/v1";\n', encoding="utf-8")

    code, detail = scan_path(tmp_path)

    assert code == 1
    assert f"src/foo.ts: direct provider host {host}" in detail


def test_excluded_ancestor_directory_name_does_not_hide_source(tmp_path: Path) -> None:
    host = _provider_host()
    root = tmp_path / "bin" / "product"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text(f"URL = 'https://{host}/v1'\n", encoding="utf-8")

    assert scan(root) == [f"src/app.py: direct provider host {host} [code] (line 1)"]


def test_github_workflows_are_not_excluded(tmp_path: Path) -> None:
    host = _provider_host()
    workflow = tmp_path / ".github" / "workflows"
    workflow.mkdir(parents=True)
    (workflow / "ci.yml").write_text(f"env:\n  URL: https://{host}/v1\n", encoding="utf-8")

    code, detail = scan_path(tmp_path, strict=True)

    assert code == 1
    assert f".github/workflows/ci.yml: direct provider host {host}" in detail


def test_classification_separates_documentation_from_code(tmp_path: Path) -> None:
    host = _provider_host()
    (tmp_path / "README.md").write_text(f"Talk to https://{host}/v1\n", encoding="utf-8")
    (tmp_path / "app.py").write_text(f"URL = 'https://{host}/v1'\n", encoding="utf-8")
    (tmp_path / "client.py").write_text(f"# see https://{host}/v1\n", encoding="utf-8")

    detail = "\n".join(scan(tmp_path, strict=True))

    assert f"README.md: direct provider host {host} [documentation]" in detail
    assert f"app.py: direct provider host {host} [code]" in detail
    assert f"client.py: direct provider host {host} [documentation]" in detail


def test_mixed_comment_and_code_match_is_classified_code(tmp_path: Path) -> None:
    host = _provider_host()
    (tmp_path / "mixed.py").write_text(
        f"# see https://{host}/v1\nURL = 'https://{host}/v1'\n",
        encoding="utf-8",
    )

    # Classified as code, and reported at the code line rather than the comment
    # so the actionable reference is the one a reviewer sees.
    assert scan(tmp_path) == [f"mixed.py: direct provider host {host} [code] (line 2)"]


def test_multi_line_probe_is_never_silently_dropped(tmp_path: Path) -> None:
    """A probe that only matches across lines must still produce a violation."""
    import re

    from hydracept import consumer_boundary

    host = _provider_host()
    (tmp_path / "wrapped.py").write_text(f"URL = 'https://{host}\n/v1'\n", encoding="utf-8")

    original = consumer_boundary._CHECKS
    try:
        consumer_boundary._CHECKS = [
            ("cross-line host", re.compile(rf"{re.escape(host)}\s*/v1"), True)
        ]
        violations = consumer_boundary.scan(tmp_path)
    finally:
        consumer_boundary._CHECKS = original

    assert violations == ["wrapped.py: cross-line host [code] (line 1)"]
