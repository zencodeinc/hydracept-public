"""Public capability error taxonomy (hydracept 0.4).

Errors must distinguish semantically different states. In particular a typo must
never be reported as a workspace permission problem: capability existence is
resolved before workspace policy is applied.

Canonical codes::

    UNKNOWN_CAPABILITY
    CAPABILITY_UNAVAILABLE
    WORKSPACE_CAPABILITY_DISABLED
    CAPABILITY_NOT_CONFIGURED
    INVALID_INPUT
    AUTH_REQUIRED
    BUDGET_EXCEEDED
    PROVIDER_UNAVAILABLE
    TRANSPORT_AMBIGUOUS
"""

from __future__ import annotations

import difflib
from typing import Any

UNKNOWN_CAPABILITY = "UNKNOWN_CAPABILITY"
CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
WORKSPACE_CAPABILITY_DISABLED = "WORKSPACE_CAPABILITY_DISABLED"
CAPABILITY_NOT_CONFIGURED = "CAPABILITY_NOT_CONFIGURED"
INVALID_INPUT = "INVALID_INPUT"
AUTH_REQUIRED = "AUTH_REQUIRED"
BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
TRANSPORT_AMBIGUOUS = "TRANSPORT_AMBIGUOUS"

# Raw server codes that already name a taxonomy state.
_RAW_CODES: dict[str, str] = {
    "UNKNOWN_CAPABILITY": UNKNOWN_CAPABILITY,
    "NOT_FOUND": UNKNOWN_CAPABILITY,
    "CAPABILITY_NOT_FOUND": UNKNOWN_CAPABILITY,
    "CapabilityNotFound": UNKNOWN_CAPABILITY,
    "CAPABILITY_UNAVAILABLE": CAPABILITY_UNAVAILABLE,
    "CapabilityUnavailable": CAPABILITY_UNAVAILABLE,
    "SERVICE_UNAVAILABLE": CAPABILITY_UNAVAILABLE,
    "WORKSPACE_CAPABILITY_DISABLED": WORKSPACE_CAPABILITY_DISABLED,
    "CapabilityDisabled": WORKSPACE_CAPABILITY_DISABLED,
    "WORKSPACE_DISABLED": WORKSPACE_CAPABILITY_DISABLED,
    "CAPABILITY_NOT_CONFIGURED": CAPABILITY_NOT_CONFIGURED,
    "ProviderNotConfigured": CAPABILITY_NOT_CONFIGURED,
    "CONNECTION_REQUIRED": CAPABILITY_NOT_CONFIGURED,
    "MANAGED_INFERENCE_UNAVAILABLE": CAPABILITY_NOT_CONFIGURED,
    "INVALID_INPUT": INVALID_INPUT,
    "InvalidInput": INVALID_INPUT,
    "AUTH_REQUIRED": AUTH_REQUIRED,
    "UNAUTHENTICATED": AUTH_REQUIRED,
    "BUDGET_EXCEEDED": BUDGET_EXCEEDED,
    "EstimateExceedsMaxCost": BUDGET_EXCEEDED,
    "billing_managed_usage_exhausted": BUDGET_EXCEEDED,
    "PROVIDER_UNAVAILABLE": PROVIDER_UNAVAILABLE,
    "ProviderUnavailable": PROVIDER_UNAVAILABLE,
    "PROVIDER_REJECTED": PROVIDER_UNAVAILABLE,
    "TRANSPORT_AMBIGUOUS": TRANSPORT_AMBIGUOUS,
    "TRANSPORT_ERROR": TRANSPORT_AMBIGUOUS,
}

# Raw codes that mean "no such capability". Outside capability scope a 404 is
# just a missing resource, so these must not become UNKNOWN_CAPABILITY.
_NOT_FOUND_RAW_CODES = frozenset({"NOT_FOUND", "CAPABILITY_NOT_FOUND", "CapabilityNotFound"})

_DISABLED_HINTS = ("disabled", "not enabled", "workspace policy", "not allowed for this workspace")
_CONFIGURED_HINTS = ("not configured", "no provider", "connection required", "credential")


def classify_capability_error(
    *,
    status: int | None = None,
    code: str = "",
    message: str = "",
    scope: str = "capability",
) -> str | None:
    """Map a raw server/HTTP error onto a taxonomy code, or ``None`` to keep raw.

    ``scope`` names what the request addressed. Only capability-scoped lookups
    turn a 404 / ``NOT_FOUND`` into :data:`UNKNOWN_CAPABILITY`; a missing job or
    other resource keeps its own identity.
    """
    capability_scope = str(scope or "") == "capability"
    normalized = str(code or "").strip()
    if normalized in _RAW_CODES:
        resolved = _RAW_CODES[normalized]
        if not capability_scope and normalized in _NOT_FOUND_RAW_CODES:
            return None
        # Existence wins over workspace policy: a 404 is never "disabled".
        if resolved == WORKSPACE_CAPABILITY_DISABLED and status == 404:
            return UNKNOWN_CAPABILITY if capability_scope else None
        return resolved

    lowered = f"{normalized} {message}".lower()
    if status == 404:
        return UNKNOWN_CAPABILITY if capability_scope else None
    if status in {401, 403}:
        return AUTH_REQUIRED
    if status == 402:
        if any(hint in lowered for hint in _DISABLED_HINTS):
            return WORKSPACE_CAPABILITY_DISABLED
        return BUDGET_EXCEEDED
    if status in {502, 503, 504}:
        return CAPABILITY_UNAVAILABLE if "capab" in lowered else PROVIDER_UNAVAILABLE
    if any(hint in lowered for hint in _DISABLED_HINTS):
        return WORKSPACE_CAPABILITY_DISABLED
    if any(hint in lowered for hint in _CONFIGURED_HINTS):
        return CAPABILITY_NOT_CONFIGURED
    return None


def _catalog_keys(catalog: Any) -> list[str]:
    if isinstance(catalog, dict):
        items = catalog.get("capabilities") or catalog.get("items") or catalog.get("results") or []
    elif isinstance(catalog, list):
        items = catalog
    else:
        items = []
    keys: list[str] = []
    for item in items:
        if isinstance(item, str):
            keys.append(item)
        elif isinstance(item, dict):
            key = item.get("key") or item.get("capabilityKey")
            if key:
                keys.append(str(key))
    return keys


def suggest_capability_keys(
    unknown: str,
    catalog: Any = (),
    *,
    limit: int = 3,
) -> list[str]:
    """High-confidence nearest capability keys for a typo'd key."""
    key = str(unknown or "").strip().lower()
    if not key:
        return []
    candidates = [candidate for candidate in _catalog_keys(catalog) if candidate]
    scored: list[tuple[float, str]] = []
    prefix = key.split(".")[0]
    for candidate in candidates:
        lowered = candidate.lower()
        if lowered == key:
            continue
        ratio = difflib.SequenceMatcher(None, key, lowered).ratio()
        if lowered.startswith(f"{prefix}."):
            ratio += 0.15
        if ratio >= 0.6:
            scored.append((ratio, candidate))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    seen: set[str] = set()
    suggestions: list[str] = []
    for _, candidate in scored:
        if candidate in seen:
            continue
        seen.add(candidate)
        suggestions.append(candidate)
        if len(suggestions) >= limit:
            break
    return suggestions


def unknown_capability_payload(
    key: str,
    catalog: Any = (),
    *,
    limit: int = 3,
) -> dict[str, Any]:
    """Structured UNKNOWN_CAPABILITY error. Never points at Connections UI."""
    suggestions = suggest_capability_keys(key, catalog, limit=limit)
    payload: dict[str, Any] = {
        "error": True,
        "code": UNKNOWN_CAPABILITY,
        "message": f"Unknown capability key: {key}",
        "unknownCapability": key,
        "suggestions": suggestions,
    }
    next_action = f'python -m hydracept capabilities find "{key}" --json'
    if suggestions:
        next_action = f"python -m hydracept capabilities describe {suggestions[0]} --json"
    payload["recovery"] = {"nextAction": next_action, "cli": next_action}
    return payload


def fetch_suggestion_catalog(client: Any) -> list[dict[str, Any]]:
    """Best-effort summary catalog for suggestion ranking; never raises."""
    try:
        catalog = client.capabilities()
    except Exception:  # noqa: BLE001
        return []
    return catalog if isinstance(catalog, (list, dict)) else []


def fetch_catalog_summary(api: str, headers: dict[str, str] | None = None) -> Any:
    """Best-effort ``GET /v1/capabilities?view=summary`` for suggestion ranking."""
    try:
        import httpx

        response = httpx.get(
            f"{str(api).rstrip('/')}/v1/capabilities",
            headers=headers or {},
            params={"view": "summary"},
            timeout=30.0,
        )
        if response.status_code == 200:
            payload = response.json()
            if isinstance(payload, (list, dict)):
                return payload
    except Exception:  # noqa: BLE001
        return []
    return []


def error_payload_for_response(
    response: Any,
    *,
    key: str = "",
    catalog: Any = (),
) -> dict[str, Any] | None:
    """Return an UNKNOWN_CAPABILITY payload for a failed capability response."""
    status = getattr(response, "status_code", None)
    try:
        body = response.json() if getattr(response, "content", b"") else {}
    except Exception:  # noqa: BLE001
        body = {}
    detail = body.get("detail") if isinstance(body, dict) and isinstance(body.get("detail"), dict) else body
    code = str((detail or {}).get("code") or "") if isinstance(detail, dict) else ""
    message = str((detail or {}).get("message") or "") if isinstance(detail, dict) else ""
    if classify_capability_error(status=status, code=code, message=message) != UNKNOWN_CAPABILITY:
        return None
    return unknown_capability_payload(key, catalog)


__all__ = [
    "AUTH_REQUIRED",
    "BUDGET_EXCEEDED",
    "CAPABILITY_NOT_CONFIGURED",
    "CAPABILITY_UNAVAILABLE",
    "INVALID_INPUT",
    "PROVIDER_UNAVAILABLE",
    "TRANSPORT_AMBIGUOUS",
    "UNKNOWN_CAPABILITY",
    "WORKSPACE_CAPABILITY_DISABLED",
    "classify_capability_error",
    "error_payload_for_response",
    "fetch_catalog_summary",
    "fetch_suggestion_catalog",
    "suggest_capability_keys",
    "unknown_capability_payload",
]
