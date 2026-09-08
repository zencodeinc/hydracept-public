"""Use-contract overlay for `capabilities describe` — no fake numerical defaults."""

from __future__ import annotations

from typing import Any

_VARIABLE_HINTS = ("token", "per_million", "audio", "video", "duration")


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
    pricing_out: dict[str, Any] = {
        "estimateAvailable": estimate_available,
        "requiresInput": requires_input,
        "managed": managed,
        "byok": byok,
    }
    if default_estimate is not None:
        pricing_out["defaultEstimate"] = default_estimate
    payload["execution"] = {"mode": mode}
    payload["pricing"] = pricing_out
    payload["nextAction"] = {
        "cli": f"python -m hydracept run {key}",
        "sdk": "workspace.run",
        "mcp": "hydracept_run",
    }
    return payload
