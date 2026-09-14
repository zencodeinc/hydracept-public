"""High-value regressions from the 0.3.12 blind-consumer audit.

These tests deliberately span CLI/MCP boundaries. They protect the consumer
truth contract rather than individual implementation helpers.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from click.testing import CliRunner

from hydracept.cli import entrypoint
from hydracept.cli.mcp_bind import bind_workspace_mcp, inspect_workspace_mcp
from hydracept.cli.run_facade import _as_float, parse_json_body
from hydracept.mcp.runtime_binding import attest_runtime_binding
from hydracept.mcp.server import _sanitize_public_payload
from hydracept.mcp.workspace_locator import resolve_mcp_workspace


def _write_project(root: Path, project_id: str) -> None:
    state = root / ".hydracept"
    state.mkdir(parents=True, exist_ok=True)
    (state / "project.json").write_text(
        json.dumps({"projectId": project_id}) + "\n",
        encoding="utf-8",
    )


def test_dirty_ide_runtime_for_repo_a_cannot_verify_repo_b(tmp_path: Path) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    _write_project(repo_a, "cpr_a")
    _write_project(repo_b, "cpr_b")

    bound_a = bind_workspace_mcp(repo_a)
    attest_runtime_binding(
        repo_a,
        source="dirty-ide-test",
        env={"HYDRACEPT_MCP_GENERATION": bound_a.generation},
    )
    assert inspect_workspace_mcp(repo_a).runtime is not None
    assert inspect_workspace_mcp(repo_a).runtime.verified

    bound_b = bind_workspace_mcp(repo_b)
    inspected_b = inspect_workspace_mcp(repo_b)
    assert bound_b.reload_required is True
    assert inspected_b.reload_required is True
    assert inspected_b.runtime is not None
    assert inspected_b.runtime.status == "missing"
    assert inspected_b.runtime.verified is False


def test_explicit_repo_b_workspace_beats_stale_repo_a_environment(tmp_path: Path) -> None:
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    _write_project(repo_a, "cpr_a")
    _write_project(repo_b, "cpr_b")

    resolved = resolve_mcp_workspace(
        repo_b,
        cwd=repo_a,
        env={"HYDRACEPT_WORKSPACE": str(repo_a)},
    )
    assert resolved == repo_b.resolve()


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (403, "CapabilityNotAllowed"),
        (422, "InvalidRequest"),
        (400, "EstimateExceedsMaxCost"),
    ],
)
def test_cli_operational_failures_are_one_json_document_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    code: str,
) -> None:
    request = httpx.Request("POST", "https://api.hydracept.com/v1/capabilities/resolve")
    response = httpx.Response(
        status,
        request=request,
        json={"detail": {"code": code, "message": f"consumer failure: {code}"}},
    )
    monkeypatch.setattr(entrypoint.httpx, "post", lambda *args, **kwargs: response)
    monkeypatch.setattr(entrypoint, "_workspace_headers", lambda api: {})

    result = CliRunner().invoke(
        entrypoint.app,
        ["capabilities", "find", "consumer probe", "--json"],
    )

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["error"] is True
    assert payload["httpStatus"] == status
    assert payload["code"] == code


def test_structured_input_file_avoids_shell_json_quoting(tmp_path: Path) -> None:
    body = tmp_path / "extract.json"
    expected = {
        "document": "Ada Lovelace wrote notes on the Analytical Engine.",
        "schema": {
            "type": "object",
            "properties": {"person": {"type": "string"}},
            "required": ["person"],
        },
    }
    body.write_text(json.dumps(expected), encoding="utf-8")
    assert parse_json_body(None, body_file=body) == expected


def test_internal_money_sentinels_never_reach_public_run_or_mcp_payloads() -> None:
    sentinel = 999_999_930.0
    assert _as_float(sentinel) is None
    sanitized = _sanitize_public_payload(
        {
            "estimatedCost": sentinel,
            "nested": {
                "customerChargeUsd": sentinel,
                "ordinaryCount": 999_999_930,
            },
        }
    )
    assert sanitized["estimatedCost"] is None
    assert sanitized["nested"]["customerChargeUsd"] is None
    # Sanitization is semantic, not a blanket giant-number scrubber.
    assert sanitized["nested"]["ordinaryCount"] == 999_999_930
