from __future__ import annotations

from hydracept.cli.describe_contract import describe_use_contract


def test_describe_omits_fake_default_for_variable_work() -> None:
    payload = describe_use_contract(
        {
            "key": "text.general.fast.v1",
            "executionModes": ["invoke_sync"],
            "estimateAvailable": True,
            "pricing": {"pricingUnit": "per_million_tokens", "catalogUsd": 0.05},
            "billingModes": {
                "managed": {"available": True},
                "byok": {"available": True},
            },
        }
    )
    assert payload["pricing"]["estimateAvailable"] is True
    assert payload["pricing"]["requiresInput"] is True
    assert "defaultEstimate" not in payload["pricing"]
    assert payload["nextAction"]["cli"] == (
        "python -m hydracept run text.general.fast.v1 --input-file request.json --json"
    )
    assert "use" not in payload


def test_describe_allows_default_for_fixed_image_unit() -> None:
    payload = describe_use_contract(
        {
            "key": "image.generate.v1",
            "executionModes": ["job_async"],
            "estimateAvailable": True,
            "pricing": {"pricingUnit": "per_image", "defaultEstimate": 0.05},
            "billingModes": {
                "managed": {"available": True},
                "byok": {"available": True},
            },
        }
    )
    assert payload["pricing"]["defaultEstimate"] == 0.05
    assert payload["execution"]["mode"] == "job"


def test_describe_keeps_quote_metadata_and_surfaces_example_input() -> None:
    payload = describe_use_contract(
        {
            "key": "text.structured.extraction.v1",
            "executionModes": ["invoke_sync", "job_async"],
            "estimateAvailable": True,
            "pricing": {
                "pricingUnit": "per_million_tokens",
                "catalogUsd": 0.05,
                "quoteEndpoint": "/v1/capabilities/text.structured.extraction.v1/quote",
                "quote": {"supported": True, "requirements": ["/input/document"]},
            },
            "features": {
                "minimalInput": {
                    "document": "Invoice 42",
                    "schema": {"type": "object", "properties": {"id": {"type": "string"}}},
                }
            },
            "inputSchema": {
                "properties": {
                    "schema": {
                        "type": "object",
                        "description": "JSON Schema describing the extracted object.",
                    }
                }
            },
        }
    )
    assert payload["pricing"]["quoteEndpoint"].endswith("/quote")
    assert "catalogUsd" not in payload["pricing"]
    assert payload["nextAction"]["exampleInput"]["document"] == "Invoice 42"
    assert payload["nextAction"]["exampleInput"]["schema"]["type"] == "object"
    assert "JSON Schema" in payload["inputSchema"]["properties"]["schema"]["description"]

