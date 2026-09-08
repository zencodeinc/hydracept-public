from __future__ import annotations

import json

from click.testing import CliRunner

from hydracept.cli import entrypoint


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "capabilities": [
                {
                    "key": "text.translate.v1",
                    "title": "Translate text",
                    "description": "large descriptor field should not be echoed",
                    "readySummary": "Ready now · managed execution",
                    "workspaceRunnable": {
                        "runnable": True,
                        "status": "managed",
                        "billingMode": "managed",
                    },
                    "pricing": {
                        "mode": "managed",
                        "estimateRequired": True,
                        "pricingContext": "retail",
                        "largeInternalSchema": {"ignored": True},
                    },
                }
            ]
        }


def test_capabilities_find_accepts_json_and_returns_compact_candidates(monkeypatch) -> None:
    captured: dict = {}

    def _get(url: str, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return _Response()

    monkeypatch.setattr(entrypoint.httpx, "get", _get)
    monkeypatch.setattr(
        entrypoint,
        "_find_headers",
        lambda api: {"Authorization": "Bearer workspace-token"},
    )

    result = CliRunner().invoke(
        entrypoint.app,
        ["capabilities", "find", "translate this", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["query"] == "translate this"
    assert payload["count"] == 1
    assert payload["candidates"] == [
        {
            "key": "text.translate.v1",
            "title": "Translate text",
            "runnable": True,
            "status": "managed",
            "readySummary": "Ready now · managed execution",
            "billingMode": "managed",
            "pricing": {
                "mode": "managed",
                "estimateRequired": True,
                "pricingContext": "retail",
            },
        }
    ]
    assert "description" not in result.output
    assert captured["params"] == {"q": "translate this"}
    assert captured["headers"] == {"Authorization": "Bearer workspace-token"}
