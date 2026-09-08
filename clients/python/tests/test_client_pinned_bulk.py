"""HydraceptClient pinned bulk submit/poll against a mock HTTP transport."""

from __future__ import annotations

import httpx
import pytest

from hydracept import HydraceptClient


def _client(handler) -> HydraceptClient:
    return HydraceptClient(
        "https://api.test",
        "tok_test",
        transport=httpx.MockTransport(handler),
    )


def test_wait_pinned_bulk_polls_until_succeeded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hydracept.client.time.sleep", lambda _seconds: None)
    states = [
        {"bulkId": "pblk_1", "status": "accepted", "nextAction": "poll", "pollAfterSeconds": 4, "items": []},
        {"bulkId": "pblk_1", "status": "running", "nextAction": "poll", "pollAfterSeconds": 4, "items": []},
        {
            "bulkId": "pblk_1",
            "status": "partial",
            "nextAction": "stop",
            "items": [
                {"id": "a", "status": "succeeded"},
                {"id": "b", "status": "failed"},
            ],
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/inference/pinned/bulk/pblk_1"
        return httpx.Response(200, json=states.pop(0))

    with _client(handler) as client:
        done = client.wait_pinned_bulk("pblk_1", interval=0.01, timeout=5)
    assert done["status"] == "partial"
    assert [item["id"] for item in done["items"]] == ["a", "b"]


def test_create_pinned_inference_bulk_posts_items() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = request.read()
        return httpx.Response(200, json={"bulkId": "pblk_1", "status": "accepted"})

    with _client(handler) as client:
        payload = client.create_pinned_inference_bulk(
            {
                "pin": {"provider": "openai", "model": "gpt-5.6-sol", "api": "responses"},
                "concurrency": 8,
                "items": [{"id": "a", "input": "one"}],
            }
        )
    assert captured["path"] == "/v1/inference/pinned/bulk"
    assert payload["bulkId"] == "pblk_1"
