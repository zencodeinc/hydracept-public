from __future__ import annotations

import httpx

from hydracept.http_retry import post_json_with_retry, request_with_retry


def test_request_with_retry_reuses_idempotent_post_body() -> None:
    attempts = {"n": 0}
    idem = {"key": "stable-idem"}

    def send() -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(503, json={"code": "Unavailable"})
        return httpx.Response(200, json={"ok": True})

    response = request_with_retry(send, max_attempts=5, base_delay_seconds=0)
    assert response.status_code == 200
    assert attempts["n"] == 3


def test_post_json_with_retry_on_transport() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.headers.get("Idempotency-Key", ""))
        if len(calls) < 2:
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(200, json={"status": "Succeeded"})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://test")
    body = {"idempotencyKey": "idem-123", "input": {"prompt": "hi"}}
    payload = post_json_with_retry(client, "/v1/capabilities/k/invoke", body, max_attempts=4)
    assert payload["status"] == "Succeeded"
    assert calls == ["idem-123", "idem-123"]
