"""HydraceptClient must tolerate missing credentials for keyless discovery."""

from __future__ import annotations

import httpx

from hydracept.client import DEFAULT_BASE_URL, HydraceptClient


def test_capabilities_without_token_uses_no_authorization_header() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("Authorization", "")
        return httpx.Response(200, json={"capabilities": []})

    transport = httpx.MockTransport(handler)
    with HydraceptClient(token="", transport=transport) as client:
        assert client.base_url == DEFAULT_BASE_URL
        payload = client.capabilities()
    assert payload["capabilities"] == []
    assert captured["authorization"] == ""


def test_default_base_url() -> None:
    with HydraceptClient(token="", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))) as client:
        assert client.base_url == "https://api.hydracept.com"
