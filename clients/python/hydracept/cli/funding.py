"""Funding façade — how this workspace can fund execution."""

from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from hydracept.cli.workspace import (
    CliOverrides,
    auth_headers,
    require_ready_workspace,
)

STUDIO_CONNECTIONS_PATH = "/connections"


def connections_url(api_url: str, project_id: str, environment: str) -> str:
    """Studio connections URL owned by this helper. Callers must pass it through verbatim."""
    origin = "https://studio.hydracept.com"
    if "localhost" in api_url or "127.0.0.1" in api_url:
        origin = api_url.rstrip("/").replace("/v1", "")
        if origin.endswith(":8080") or ":8" in origin:
            origin = "http://localhost:4200"
    query = f"?projectId={quote(project_id)}&environment={quote(environment)}"
    return f"{origin}{STUDIO_CONNECTIONS_PATH}{query}"


def _managed_credit_from_diagnostics(body: dict[str, Any]) -> tuple[float | None, str]:
    """Read aggregate managed credit without presenting it as the trial grant.

    New servers expose ``managedCreditRemaining``. Older servers exposed the same
    aggregate ledger balance under ``managedTrialRemaining``; retain that fallback
    but mark its provenance so agents cannot infer that it is the original grant.
    """
    if body.get("managedCreditRemaining") is not None:
        return float(body["managedCreditRemaining"]), "managedCreditRemaining"
    if body.get("managedTrialRemaining") is not None:
        return float(body["managedTrialRemaining"]), "managedTrialRemaining_legacy_alias"
    return None, "unavailable"


def funding_status(
    project_root: Path,
    *,
    overrides: CliOverrides | None = None,
) -> dict[str, Any]:
    workspace = require_ready_workspace(project_root, overrides=overrides)
    remaining: float | None = None
    remaining_source = "unavailable"
    byok = False
    with httpx.Client(timeout=20.0) as client:
        try:
            resp = client.get(
                f"{workspace.api_url}/v1/diagnostics/providers",
                headers=auth_headers(workspace.token),
            )
            if resp.status_code == 200:
                raw = resp.json()
                body = raw if isinstance(raw, dict) else {}
                remaining, remaining_source = _managed_credit_from_diagnostics(body)
                byok = bool(body.get("byokBound"))
        except (httpx.HTTPError, TypeError, ValueError):
            pass
    return {
        "schemaVersion": "hydracept.funding.v1",
        "options": ["managed_credit", "byok"],
        "managedWalletTopUpLive": False,
        "managedCreditRemainingUsd": remaining,
        "managedCreditSemantics": "aggregate_available_credit",
        "managedCreditSource": remaining_source,
        # Compatibility only. This value is aggregate available managed credit,
        # not proof of the original trial grant amount.
        "trialRemainingUsd": remaining,
        "trialRemainingUsdDeprecated": True,
        "byokConnected": byok,
        "setupCli": "python -m hydracept funding setup",
        "projectId": workspace.project_id,
        "environment": workspace.environment,
    }


def funding_setup(
    project_root: Path,
    *,
    overrides: CliOverrides | None = None,
    open_browser: bool = True,
) -> dict[str, Any]:
    """Same browser-handoff pattern as init: open existing connection-management flow."""
    workspace = require_ready_workspace(project_root, overrides=overrides)
    url = connections_url(workspace.api_url, workspace.project_id, workspace.environment)
    opened = False
    if open_browser:
        try:
            opened = bool(webbrowser.open(url))
        except Exception:  # noqa: BLE001
            opened = False
    return {
        "schemaVersion": "hydracept.funding.v1",
        "connectUrl": url,
        "openedBrowser": opened,
        "nextAction": "complete_provider_connect_in_browser",
        "note": "Never paste provider keys into chat or CLI args.",
        "alias": "python -m hydracept providers connect",
    }
