"""Use-contract overlay for `capabilities describe` — no fake numerical defaults."""

from __future__ import annotations

from typing import Any

_VARIABLE_HINTS = ("token", "per_million", "audio", "video", "duration")
_FAKE_PRICE_KEYS = ("catalogUsd", "defaultEstimate")


def describe_use_contract(descriptor: dict[str, Any]) -> dict[str, Any]:
    payload = dict(descriptor)
    key = str(payload.get("key") or "")
    modes = payload.get("executionModes") or []
    mode = "job"
    if isinstance(modes, list) and any(str(m).startswith("invoke") for m in modes) and not any(
        "job" in str(m) for m in modes
    ):
        mode = "invoke"
    estimate_available = bool(payload.get("estimateAvailable"))
    pricing_in = payload.get("pricing") if isinstance(payload.get("pricing"), dict) else {}
    quote = pricing_in.get("quote") if isinstance(pricing_in.get("quote"), dict) else {}
    unit = str(
        pricing_in.get("pricingUnit")
        or quote.get("pricingUnit")
        or ""
    ).lower()
    requires_input = True
    if unit in {"per_image", "fixed"}:
        requires_input = False
    default_estimate = None
    if estimate_available and not requires_input:
        for candidate in (
            pricing_in.get("defaultEstimate"),
            pricing_in.get("catalogUsd"),
            (pricing_in.get("managed") or {}).get("usd")
            if isinstance(pricing_in.get("managed"), dict)
            else None,
        ):
            if isinstance(candidate, (int, float)):
                default_estimate = float(candidate)
                break
    if any(hint in unit for hint in _VARIABLE_HINTS):
        default_estimate = None
        requires_input = True
    billing = payload.get("billingModes") if isinstance(payload.get("billingModes"), dict) else {}
    managed = bool((billing.get("managed") or {}).get("available")) if isinstance(billing.get("managed"), dict) else bool(
        pricing_in.get("managed")
    )
    byok = bool((billing.get("byok") or {}).get("available")) if isinstance(billing.get("byok"), dict) else True
    pricing_out = {
        name: value
        for name, value in pricing_in.items()
        if name not in _FAKE_PRICE_KEYS
    }
    pricing_out["estimateAvailable"] = estimate_available
    pricing_out["requiresInput"] = requires_input
    pricing_out["managed"] = managed
    pricing_out["byok"] = byok
    if default_estimate is not None:
        pricing_out["defaultEstimate"] = default_estimate
    execution_in = payload.get("execution") if isinstance(payload.get("execution"), dict) else {}
    execution_out = dict(execution_in)
    execution_out["mode"] = mode
    payload["execution"] = execution_out
    payload["pricing"] = pricing_out
    cli = f"python -m hydracept run {key}"
    if requires_input:
        cli = f"python -m hydracept run {key} --input-file request.json --json"
    next_action: dict[str, Any] = {
        "cli": cli,
        "sdk": "workspace.run",
        "mcp": "hydracept_run",
    }
    example_input = _example_input(payload)
    if example_input is not None:
        next_action["exampleInput"] = example_input
        next_action["inputFile"] = "request.json"
        next_action["note"] = (
            "Write exampleInput to request.json. schema/responseSchema values are "
            "inlined JSON Schema objects, not file paths. Prefer --input-file on PowerShell."
        )
    payload["nextAction"] = next_action
    return payload


def _example_input(payload: dict[str, Any]) -> dict[str, Any] | None:
    features = payload.get("features") if isinstance(payload.get("features"), dict) else {}
    minimal = features.get("minimalInput")
    if isinstance(minimal, dict) and minimal:
        return dict(minimal)
    schema = payload.get("inputSchema") if isinstance(payload.get("inputSchema"), dict) else {}
    examples = schema.get("examples")
    if isinstance(examples, list) and examples and isinstance(examples[0], dict):
        return dict(examples[0])
    return None
