from __future__ import annotations

import httpx

from hydracept.client import HydraceptClient


def test_invoke_populates_camel_case_only_from_snake_case() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["json"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"status": "Succeeded"})

    transport = httpx.MockTransport(handler)
    client = HydraceptClient(base_url="http://test", token="k", transport=transport)
    client.invoke_capability("text.general.fast.v1", {"idempotency_key": "snake-key", "input": {"prompt": "x"}})
    sent = captured["json"]
    assert sent["idempotencyKey"] == "snake-key"
    assert "idempotency_key" not in sent
