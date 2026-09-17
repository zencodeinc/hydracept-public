"""The API owns capability-descriptor projection; clients must not re-derive it."""

from __future__ import annotations

import pytest


def test_client_no_longer_ships_a_second_projection() -> None:
    """One-sided authority: the projection lives only in the API."""
    with pytest.raises(ImportError):
        import hydracept.capability_descriptor  # noqa: F401

    with pytest.raises(ImportError):
        import hydracept.cli.describe_contract  # noqa: F401


class _Response:
    is_success = True
    status_code = 200
    reason_phrase = "OK"
    content = b"{}"

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.request = None

    def json(self) -> dict:
        return self._payload


_SERVER_PAYLOAD = {
    "key": "image.generate.v1",
    "execution": {"mode": "job"},
    "canvasFloor": {"minPixels": 655360, "minimumSquare": "816x816"},
    "nextAction": {"cli": 'python -m hydracept run image.generate.v1 --prompt "..." --json'},
    "serverProjectionMarker": "untouched",
}


def test_mcp_describe_returns_the_server_projection_verbatim(monkeypatch) -> None:
    from hydracept.mcp import server

    monkeypatch.setattr(server, "_project_root", lambda: None)
    monkeypatch.setattr(server, "resolve_workspace", lambda *a, **k: None)
    monkeypatch.setattr(server, "_anonymous_api_url", lambda: "https://api.example")
    monkeypatch.setattr(server.httpx, "get", lambda *a, **k: _Response(dict(_SERVER_PAYLOAD)))

    described = server.hydracept_capabilities(key="image.generate.v1")

    assert described == _SERVER_PAYLOAD
