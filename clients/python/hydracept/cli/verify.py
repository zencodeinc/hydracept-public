"""hydracept verify — lockfile and run-manifest checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

LOCKFILE_KIND = "hydracept.lock"
MANIFEST_KIND = "hydracept.run-manifest"
DEFAULT_LOCKFILE = Path("hydracept.lock")


def load_document(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} is not a mapping")
    return raw


def is_manifest(path: Path, document: dict[str, Any]) -> bool:
    kind = str(document.get("kind") or "")
    if kind == MANIFEST_KIND:
        return True
    if kind == LOCKFILE_KIND:
        return False
    name = path.name.lower()
    return "manifest" in name or name.endswith(".manifest.json") or name.endswith(".manifest.yaml")


def structural_lockfile_checks(document: dict[str, Any]) -> list[dict[str, Any]]:
    inference = document.get("inference") if isinstance(document.get("inference"), dict) else {}
    semantics = document.get("semantics") if isinstance(document.get("semantics"), dict) else {}
    provider = str(inference.get("provider") or "")
    model = str(inference.get("model") or "")
    api = str(inference.get("api") or "")
    protocol = str(inference.get("protocol") or "rip-v1")
    return [
        {
            "name": "model_pin",
            "passed": bool(provider and model and api),
            "detail": f"{provider}/{model}/{api}" if provider else "provider/model/api required",
        },
        {
            "name": "native_api",
            "passed": provider == "openai" and api == "responses",
            "detail": f"{provider}/{api}" if api else "native API missing",
        },
        {
            "name": "semantics_pinned",
            "passed": bool(semantics.get("stateless", True))
            and not bool(semantics.get("fallback", False))
            and not bool(semantics.get("rewriting", False)),
            "detail": "stateless, no fallback, no rewrite",
        },
        {
            "name": "protocol",
            "passed": protocol == "rip-v1",
            "detail": protocol,
        },
    ]


def structural_manifest_checks(document: dict[str, Any]) -> list[dict[str, Any]]:
    receipts = document.get("receipts") or []
    ids = [
        str(item.get("receipt_id") or item.get("receiptId") or "")
        for item in receipts
        if isinstance(item, dict)
    ]
    unique = len(ids) == len(set(ids)) and all(ids)
    fallbacks = [
        str(item.get("receipt_id") or item.get("receiptId"))
        for item in receipts
        if isinstance(item, dict) and item.get("fallback")
    ]
    totals = document.get("totals") if isinstance(document.get("totals"), dict) else {}
    return [
        {
            "name": "receipt_ids_unique",
            "passed": unique,
            "detail": f"{len(ids)} receipts" if unique else "duplicate or empty receipt set",
        },
        {
            "name": "no_fallback",
            "passed": not fallbacks,
            "detail": "0 fallbacks" if not fallbacks else f"fallback on {fallbacks}",
        },
        {
            "name": "totals",
            "passed": True,
            "detail": (
                f"{totals.get('receipts', len(ids))} receipts · "
                f"{totals.get('fallbacks', len(fallbacks))} fallbacks · "
                f"{totals.get('provider_retries', totals.get('providerRetries', 0))} provider retries · "
                f"${(int(totals.get('cost_micros') or totals.get('costMicros') or 0) / 1_000_000):.2f} provider spend"
            ),
        },
    ]


def format_checks(checks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for check in checks:
        mark = "✓" if check.get("passed") else "✗"
        name = str(check.get("name") or "check").replace("_", " ")
        detail = check.get("detail")
        suffix = f"  {detail}" if detail else ""
        lines.append(f"{mark} {name}{suffix}")
    return "\n".join(lines)


def all_passed(checks: list[dict[str, Any]]) -> bool:
    return all(bool(check.get("passed")) for check in checks)
