"""MCP isError results must keep a structured envelope, not a generic ToolError string."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from mcp_types import CallToolResult

from hydracept.errors import RunAdmissionError
from hydracept.mcp.server import McpToolError, _as_error_result, _tool_call, server


def test_tool_call_returns_structured_is_error() -> None:
    def _boom() -> dict:
        raise McpToolError({"code": "FundingRequired", "message": "Connect a provider"})

    result = _tool_call(_boom)
    assert isinstance(result, CallToolResult)
    assert result.is_error is True
    assert result.structured_content["code"] == "FundingRequired"
    assert result.structured_content["isError"] is True
    text = result.content[0].text
    assert "FundingRequired" in text
    assert "Error executing tool" not in text


def test_as_error_result_json_is_parseable() -> None:
    result = _as_error_result({"code": "EstimateExceedsMaxCost", "message": "too expensive"})
    assert result.is_error is True
    assert result.structured_content["error"] is True
    assert result.structured_content["code"] == "EstimateExceedsMaxCost"


def test_stdio_quote_preserves_admission_structured_content() -> None:
    async def _call() -> CallToolResult:
        with patch(
            "hydracept.mcp.server._execution_workspace",
            side_effect=RunAdmissionError(
                {
                    "error": True,
                    "code": "ProjectCredentialMismatch",
                    "message": "checkout and credential must match",
                }
            ),
        ):
            return await server.call_tool(
                "hydracept_quote_capability",
                {"capability_key": "image.generate.v1"},
            )

    result = asyncio.run(_call())
    assert result.is_error is True
    assert result.structured_content is not None
    assert result.structured_content["code"] == "ProjectCredentialMismatch"
    assert "Error executing tool" not in result.content[0].text


def test_smoke_download_failure_is_structured_error() -> None:
    from hydracept.cli.smoke_runner import SmokeResult

    smoke = SmokeResult(
        job_id="wfr_1",
        status="succeeded",
        receipt={},
        artifact_ids=["art_1"],
        sha256_ok=True,
        transparency_ok=True,
        pricing_ok=True,
    )

    async def _call() -> CallToolResult:
        with patch("hydracept.mcp.server.run_smoke", return_value=smoke), patch(
            "hydracept.mcp.server._download_artifact",
            side_effect=ValueError("artifact_id is required"),
        ):
            return await server.call_tool("hydracept_smoke", {})

    result = asyncio.run(_call())
    assert result.is_error is True
    assert result.structured_content["code"] == "INVALID_ARGUMENT"
    assert "Error executing tool" not in result.content[0].text
