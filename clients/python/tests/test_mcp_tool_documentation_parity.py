"""Published MCP documentation copy must match hydracept_contracts authority."""

from __future__ import annotations

from hydracept.mcp import tool_documentation as client_doc
from hydracept_contracts import mcp_tool_documentation as contract_doc


def test_tool_descriptions_match_contracts() -> None:
    assert client_doc.TOOL_DESCRIPTIONS == contract_doc.TOOL_DESCRIPTIONS


def test_parameter_descriptions_match_contracts() -> None:
    assert client_doc.PARAMETER_DESCRIPTIONS == contract_doc.PARAMETER_DESCRIPTIONS
