"""External surface guards for the commission-quote read path (CLI + MCP + catalog)."""

from __future__ import annotations

from pathlib import Path


def test_client_get_capability_request_quote_hits_quote_route(monkeypatch) -> None:
    from hydracept.client import HydraceptClient

    calls: dict[str, str] = {}

    def fake_get(_self, path: str):
        calls["path"] = path
        return {"quoteId": "cq_1", "quoteKind": "commission"}

    monkeypatch.setattr(HydraceptClient, "_get", fake_get)
    client = HydraceptClient("https://api.example", "token")

    payload = client.get_capability_request_quote("cr_1")

    assert payload["quoteId"] == "cq_1"
    assert calls["path"] == "/v1/capability-requests/cr_1/quote"


def test_cli_registers_capability_request_quote_command() -> None:
    from hydracept.cli import main as cli_main

    names = {command.name for command in cli_main.capability_request_app.registered_commands}
    assert "quote" in names


def test_mcp_stdio_exposes_quote_read_tool() -> None:
    import pytest

    pytest.importorskip("mcp")
    from hydracept.mcp import server as mcp_server

    assert callable(getattr(mcp_server, "get_capability_request_quote", None))


def test_public_mcp_tool_catalog_lists_quote_read() -> None:
    catalog = (
        Path(__file__).resolve().parents[3]
        / "public"
        / "agents"
        / "source"
        / "mcp"
        / "tools.yaml"
    )
    text = catalog.read_text(encoding="utf-8")
    assert "name: get_capability_request_quote" in text
