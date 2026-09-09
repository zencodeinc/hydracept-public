from __future__ import annotations

import json

import httpx
from click.testing import CliRunner

from hydracept.cli import entrypoint


class _Response:
    is_success = True
    content = b"{}"

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


def test_capabilities_find_preserves_server_relevance_order(monkeypatch) -> None:
    class RankedResponse(_Response):
        def json(self) -> dict:
            return {
                "capabilities": [
                    {
                        "key": "text.general.fast.v1",
                        "title": "Fast text",
                        "readySummary": "Provider setup required",
                        "workspaceRunnable": {
                            "runnable": False,
                            "status": "missing_provider",
                            "requiredAction": {"kind": "connect_provider"},
                        },
                    },
                    {
                        "key": "text.reasoning.high.v1",
                        "title": "Reasoning text",
                        "readySummary": "Ready now · managed execution",
                        "workspaceRunnable": {
                            "runnable": True,
                            "status": "managed",
                            "billingMode": "managed",
                        },
                    },
                ]
            }

    monkeypatch.setattr(entrypoint.httpx, "get", lambda *args, **kwargs: RankedResponse())
    result = CliRunner().invoke(
        entrypoint.app,
        ["capabilities", "find", "cheap summary", "--json"],
    )
    assert result.exit_code == 0, result.output
    candidates = json.loads(result.output)["candidates"]
    # The API owns task relevance; the CLI exposes readiness without turning it
    # into a second ranking algorithm.
    assert [item["key"] for item in candidates] == [
        "text.general.fast.v1",
        "text.reasoning.high.v1",
    ]
    assert candidates[0]["requiredAction"] == {"kind": "connect_provider"}


def test_capabilities_find_api_failure_is_one_json_error_without_traceback(monkeypatch) -> None:
    request = httpx.Request("GET", "https://api.hydracept.com/v1/capabilities")
    response = httpx.Response(
        403,
        request=request,
        json={
            "detail": {
                "code": "CapabilityNotAllowed",
                "message": "capability is disabled for this workspace",
            }
        },
    )
    monkeypatch.setattr(entrypoint.httpx, "get", lambda *args, **kwargs: response)

    result = CliRunner().invoke(
        entrypoint.app,
        ["capabilities", "find", "audio", "--json"],
    )
    assert result.exit_code == 1
    assert "Traceback" not in result.output
    payload = json.loads(result.output)
    assert payload["error"] is True
    assert payload["httpStatus"] == 403
    assert payload["code"] == "CapabilityNotAllowed"
