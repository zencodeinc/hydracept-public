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
    assert payload["nextAction"]["cli"] == "python -m hydracept run text.general.fast.v1"
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
