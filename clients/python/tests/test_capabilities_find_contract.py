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
            "resolution": "matched",
            "requirementsSatisfied": True,
            "matches": [
                {
                    "key": "text.translate.v1",
                    "title": "Translate text",
                    "description": "large descriptor field should not be echoed",
                    "readySummary": "Ready now · managed execution",
                    "accessDecision": {
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
                    "confidence": 0.99,
                }
            ],
        }


def test_capabilities_find_accepts_json_and_returns_compact_server_matches(monkeypatch) -> None:
    captured: dict = {}

    def _post(url: str, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return _Response()

    monkeypatch.setattr(entrypoint.httpx, "post", _post)
    monkeypatch.setattr(
        entrypoint,
        "_workspace_headers",
        lambda api: {"Authorization": "Bearer workspace-token"},
    )

    result = CliRunner().invoke(
        entrypoint.app,
        ["capabilities", "find", "translate this", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["query"] == "translate this"
    assert payload["resolution"] == "matched"
    assert payload["requirementsSatisfied"] is True
    assert payload["count"] == 1
    assert payload["candidates"] == [
        {
            "key": "text.translate.v1",
            "title": "Translate text",
            "runnable": True,
            "status": "managed",
            "readySummary": "Ready now · managed execution",
            "confidence": 0.99,
            "billingMode": "managed",
            "pricing": {
                "mode": "managed",
                "estimateRequired": True,
                "pricingContext": "retail",
            },
        }
    ]
    assert "description" not in result.output
    assert captured["json"] == {"intent": "translate this", "requirements": {}}
    assert captured["headers"] == {"Authorization": "Bearer workspace-token"}
    assert captured["url"].endswith("/v1/capabilities/resolve")


def test_capabilities_find_preserves_server_relevance_order(monkeypatch) -> None:
    class RankedResponse(_Response):
        def json(self) -> dict:
            return {
                "resolution": "matched",
                "requirementsSatisfied": True,
                "matches": [
                    {
                        "key": "text.general.fast.v1",
                        "title": "Fast text",
                        "readySummary": "Provider setup required",
                        "accessDecision": {
                            "runnable": False,
                            "status": "missing_provider",
                            "requiredAction": {"kind": "connect_provider"},
                        },
                    },
                    {
                        "key": "text.reasoning.high.v1",
                        "title": "Reasoning text",
                        "readySummary": "Ready now · managed execution",
                        "accessDecision": {
                            "runnable": True,
                            "status": "managed",
                            "billingMode": "managed",
                        },
                    },
                ],
            }

    monkeypatch.setattr(entrypoint.httpx, "post", lambda *args, **kwargs: RankedResponse())
    monkeypatch.setattr(entrypoint, "_workspace_headers", lambda api: {})
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


def test_capabilities_find_limits_after_server_order_without_reranking(monkeypatch) -> None:
    class ManyResponse(_Response):
        def json(self) -> dict:
            return {
                "resolution": "matched",
                "requirementsSatisfied": True,
                "matches": [
                    {
                        "key": f"text.test.{index}.v1",
                        "title": f"Candidate {index}",
                        "accessDecision": {"runnable": index % 2 == 1, "status": "test"},
                    }
                    for index in range(7)
                ],
            }

    monkeypatch.setattr(entrypoint.httpx, "post", lambda *args, **kwargs: ManyResponse())
    monkeypatch.setattr(entrypoint, "_workspace_headers", lambda api: {})
    result = CliRunner().invoke(
        entrypoint.app,
        ["capabilities", "find", "anything", "--json"],
    )
    assert result.exit_code == 0, result.output
    candidates = json.loads(result.output)["candidates"]
    assert [item["key"] for item in candidates] == [
        "text.test.0.v1",
        "text.test.1.v1",
        "text.test.2.v1",
        "text.test.3.v1",
        "text.test.4.v1",
    ]


def test_capabilities_find_api_failure_is_one_json_error_without_traceback(monkeypatch) -> None:
    request = httpx.Request("POST", "https://api.hydracept.com/v1/capabilities/resolve")
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
    monkeypatch.setattr(entrypoint.httpx, "post", lambda *args, **kwargs: response)
    monkeypatch.setattr(entrypoint, "_workspace_headers", lambda api: {})

    result = CliRunner().invoke(
        entrypoint.app,
        ["capabilities", "find", "audio", "--json"],
    )
    assert result.exit_code == 1
    assert "Traceback" not in result.output
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["error"] is True
    assert payload["httpStatus"] == 403
    assert payload["code"] == "CapabilityNotAllowed"


def test_capabilities_find_falls_back_to_catalog_on_no_match(monkeypatch) -> None:
    class MissResponse(_Response):
        def json(self) -> dict:
            return {"resolution": "no_match_requestable", "matches": []}

    monkeypatch.setattr(entrypoint.httpx, "post", lambda *args, **kwargs: MissResponse())
    monkeypatch.setattr(entrypoint, "_workspace_headers", lambda api: {})
    monkeypatch.setattr(
        "hydracept.cli.catalog_match.catalog_matches",
        lambda intent, api, headers=None, limit=5: [
            {
                "key": "image.generate.v1",
                "title": "Generate image",
                "accessDecision": {"runnable": True, "status": "managed", "billingMode": "managed"},
            }
        ],
    )
    result = CliRunner().invoke(
        entrypoint.app,
        ["capabilities", "find", "transparent potion inventory icon", "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["resolution"] == "matched"
    assert payload["matchSource"] == "catalog_fallback"
    assert payload["candidates"][0]["key"] == "image.generate.v1"
    assert "--prompt" in payload["execution"]


def test_catalog_match_prefers_image_capability_for_icon_intent() -> None:
    from hydracept.cli.catalog_match import score_capability

    image = score_capability(
        "transparent potion inventory icon",
        {"key": "image.generate.v1", "title": "Generate image"},
    )
    domain = score_capability(
        "transparent potion inventory icon",
        {"key": "domain.search.v1", "title": "Search domains"},
    )
    assert image > domain


def test_catalog_match_prefers_generate_over_edit() -> None:
    from hydracept.cli.catalog_match import prefer_intent_matches, score_capability

    generate = score_capability(
        "generate one transparent inventory icon",
        {"key": "image.generate.v1", "title": "Generate image"},
    )
    edit = score_capability(
        "generate one transparent inventory icon",
        {"key": "image.edit.v1", "title": "Edit image"},
    )
    assert generate > edit
    ordered = prefer_intent_matches(
        "generate a transparent potion",
        [
            {"key": "image.edit.v1"},
            {"key": "image.generate.v1"},
        ],
    )
    assert [item["key"] for item in ordered] == ["image.generate.v1", "image.edit.v1"]


def test_domain_search_execution_hint_uses_prompt_shortcut(monkeypatch) -> None:
    class DomainResponse(_Response):
        def json(self) -> dict:
            return {
                "resolution": "matched",
                "requirementsSatisfied": True,
                "matches": [
                    {
                        "key": "domain.search.v1",
                        "title": "Search domains",
                        "accessDecision": {"runnable": True, "status": "managed"},
                    }
                ],
            }

    monkeypatch.setattr(entrypoint.httpx, "post", lambda *args, **kwargs: DomainResponse())
    monkeypatch.setattr(entrypoint, "_workspace_headers", lambda api: {})
    result = CliRunner().invoke(
        entrypoint.app,
        ["capabilities", "find", "check a domain", "--json"],
    )
    assert result.exit_code == 0, result.output
    assert '--prompt \\"example.com\\"' in result.output
