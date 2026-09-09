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
    """Read customer-visible managed credit with a marked legacy fallback."""
    if body.get("managedCreditRemaining") is not None:
        return float(body["managedCreditRemaining"]), "managedCreditRemaining"
    if body.get("managedTrialRemaining") is not None:
        return float(body["managedTrialRemaining"]), "managedTrialRemaining_legacy_alias"
    return None, "unavailable"


def _trial_credit_from_diagnostics(body: dict[str, Any]) -> float | None:
    value = body.get("managedTrialRemaining")
    if value is None:
        return None
    return float(value)


def _coverage_kind(source: str, available: bool | None) -> str:
    if not available:
        return "unavailable"
    return {
        "internal": "covered_by_hydracept",
        "managed_trial": "covered_by_trial",
        "wallet": "uses_customer_managed_credit",
        "unknown": "funded_source_sealed_at_admission",
    }.get(source, "managed_funding_available")


def funding_payload_from_diagnostics(
    body: dict[str, Any],
    *,
    project_id: str,
    environment: str,
) -> dict[str, Any]:
    """Project diagnostics into the public funding.v1 contract.

    Customer-visible managed credit, trial bucket, and execution-available
    funding are separate facts. Operator grants may fund execution without
    becoming a fake customer wallet or trial balance.
    """
    remaining, remaining_source = _managed_credit_from_diagnostics(body)
    remaining_semantics = str(
        body.get("managedCreditSemantics") or "aggregate_available_credit_legacy"
    )
    trial_remaining = _trial_credit_from_diagnostics(body)
    execution_funding_available: bool | None = None
    if body.get("managedExecutionFundingAvailable") is not None:
        execution_funding_available = bool(body.get("managedExecutionFundingAvailable"))
    sources = body.get("managedExecutionFundingSources")
    execution_funding_sources = (
        [str(source) for source in sources if str(source)] if isinstance(sources, list) else []
    )
    execution_funding_source = str(
        body.get("managedExecutionFundingSource")
        or ("unknown" if execution_funding_available else "unavailable")
    )
    execution_coverage = str(body.get("managedExecutionCoverage") or "")
    operator_funding_present = bool(body.get("managedOperatorFundingPresent"))
    byok = bool(body.get("byokBound"))
    if execution_funding_available is None and remaining is not None:
        execution_funding_available = remaining > 0
        execution_funding_source = "unknown" if execution_funding_available else "unavailable"

    if byok:
        next_action = None
    elif execution_funding_available:
        next_action = "python -m hydracept smoke"
    else:
        next_action = "python -m hydracept funding setup"

    return {
        "schemaVersion": "hydracept.funding.v1",
        "options": ["managed_credit", "byok"],
        "managedWalletTopUpLive": False,
        "managedCreditRemainingUsd": remaining,
        "managedCreditSemantics": remaining_semantics,
        "managedCreditSource": remaining_source,
        "managedExecutionFundingAvailable": execution_funding_available,
        "managedExecutionFundingSources": execution_funding_sources,
        "managedExecutionFundingSource": execution_funding_source,
        "managedExecutionCoverage": execution_coverage or None,
        "managedChargeExpectation": _coverage_kind(
            execution_funding_source,
            execution_funding_available,
        ),
        "managedOperatorFundingPresent": operator_funding_present,
        "trialRemainingUsd": trial_remaining,
        "trialRemainingSemantics": "active_trial_bucket_only",
        "byokConnected": byok,
        "setupCli": "python -m hydracept funding setup",
        "nextAction": next_action,
        "projectId": project_id,
        "environment": environment,
    }


def funding_status(
    project_root: Path,
    *,
    overrides: CliOverrides | None = None,
) -> dict[str, Any]:
    workspace = require_ready_workspace(project_root, overrides=overrides)
    body: dict[str, Any] = {}
    with httpx.Client(timeout=20.0) as client:
        try:
            resp = client.get(
                f"{workspace.api_url}/v1/diagnostics/providers",
                headers=auth_headers(workspace.token),
            )
            if resp.status_code == 200:
                raw = resp.json()
                if isinstance(raw, dict):
                    body = raw
        except (httpx.HTTPError, TypeError, ValueError):
            pass
    return funding_payload_from_diagnostics(
        body,
        project_id=str(workspace.project_id or ""),
        environment=str(workspace.environment or ""),
    )


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
