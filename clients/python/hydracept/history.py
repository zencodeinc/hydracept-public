"""Public Python helpers for project job discovery and inspection."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode


def history_query_for_intent(intent: str) -> dict[str, str]:
    normalized = (intent or "recent").strip().lower()
    if normalized == "recent":
        return {}
    if normalized == "failed":
        return {"outcome": "failed"}
    if normalized == "reusable":
        return {"outcome": "reusable"}
    raise ValueError("intent must be recent, failed, or reusable")


def history_find_result(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    items = result.get("items")
    result["nextAction"] = "inspect" if isinstance(items, list) and items else "none"
    return result


def _receipt_summary(receipt: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(receipt, dict) or not receipt:
        return None
    pricing = receipt.get("pricing") or {}
    charge = (pricing.get("charge") or {}).get("customerCharge") or {}
    quote = (pricing.get("quote") or {}).get("customerTotal") or {}
    micros = charge.get("amountMicros")
    if micros is None:
        micros = quote.get("amountMicros")
    cost_usd = None
    if micros is not None:
        try:
            cost_usd = int(micros) / 1_000_000
        except (TypeError, ValueError):
            cost_usd = None
    return {
        "receiptId": receipt.get("receiptId") or receipt.get("id"),
        "jobId": receipt.get("jobId"),
        "status": receipt.get("status"),
        "pricing": pricing or None,
        "costUsd": cost_usd,
        "route": receipt.get("route") or receipt.get("routing"),
        "artifacts": receipt.get("artifacts") or [],
        "provenance": receipt.get("provenance"),
    }


def _reuse_candidate(job: dict[str, Any]) -> tuple[str | None, bool]:
    variant_set = job.get("variantSet")
    if isinstance(variant_set, dict):
        selected = str(variant_set.get("selectedArtifactId") or "").strip()
        if selected:
            return selected, True

    artifacts = job.get("artifacts")
    if isinstance(artifacts, list):
        for item in artifacts:
            if not isinstance(item, dict) or item.get("selected") is not True:
                continue
            artifact_id = str(item.get("artifactId") or item.get("id") or "").strip()
            if artifact_id:
                return artifact_id, True

    primary = str(job.get("primaryArtifactId") or "").strip()
    if primary:
        return primary, False

    if isinstance(artifacts, list):
        for item in artifacts:
            if not isinstance(item, dict):
                continue
            artifact_id = str(item.get("artifactId") or item.get("id") or "").strip()
            if artifact_id:
                return artifact_id, False
    return None, False


def inspect_job_bundle(
    job: dict[str, Any],
    receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = str(job.get("status") or "").strip().lower()
    artifact_id, explicitly_selected = _reuse_candidate(job)
    error = job.get("error") if isinstance(job.get("error"), dict) else None

    if status in {"failed", "needs_attention"}:
        next_action = "inspect_error"
    elif artifact_id and explicitly_selected:
        next_action = "reuse_selected"
    elif artifact_id:
        next_action = "download_artifacts"
    else:
        next_action = "stop"

    return {
        "jobId": job.get("jobId") or job.get("id"),
        "capabilityKey": job.get("capabilityKey"),
        "status": job.get("status"),
        "error": error,
        "diagnostics": job.get("diagnostics"),
        "receipt": _receipt_summary(receipt),
        "requestSnapshot": job.get("requestSnapshot"),
        "artifacts": job.get("artifacts") or [],
        "selectedArtifactId": (
            (job.get("variantSet") or {}).get("selectedArtifactId")
            if isinstance(job.get("variantSet"), dict)
            else None
        ),
        "reuseCandidateArtifactId": artifact_id,
        "reuseCandidateSelected": explicitly_selected,
        "jobNextAction": job.get("nextAction"),
        "pollAfterSeconds": job.get("pollAfterSeconds"),
        "nextAction": next_action,
    }


def _bound_project_id(client: Any, project_id: str | None) -> str:
    explicit = str(project_id or "").strip()
    if explicit:
        return explicit
    workspace = getattr(client, "workspace", None)
    bound = str(getattr(workspace, "project_id", "") or "").strip()
    if not bound:
        raise ValueError("project_id is required when the client is not workspace-bound")
    return bound


def list_project_jobs(
    client: Any,
    project_id: str | None = None,
    *,
    limit: int = 25,
    cursor: str | None = None,
    status: str | None = None,
    capability_key: str | None = None,
    outcome: str | None = None,
    selected: bool | None = None,
) -> dict[str, Any]:
    """List prompt-free project job metadata through the public history route."""
    bound = _bound_project_id(client, project_id)
    params: dict[str, str] = {"limit": str(max(1, min(int(limit), 100)))}
    if cursor:
        params["cursor"] = cursor
    if status:
        params["status"] = status
    if capability_key:
        params["capabilityKey"] = capability_key
    if outcome:
        if outcome not in {"failed", "reusable"}:
            raise ValueError("outcome must be failed or reusable")
        params["outcome"] = outcome
    if selected is not None:
        params["selected"] = "true" if selected else "false"
    return client._get(  # noqa: SLF001 — helper is part of the same client package
        f"/v1/projects/{bound}/jobs?{urlencode(params)}"
    )


def find_project_jobs(
    client: Any,
    *,
    intent: str = "recent",
    project_id: str | None = None,
    capability_key: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Agent-oriented recent/failed/reusable discovery wrapper."""
    query = history_query_for_intent(intent)
    return history_find_result(
        list_project_jobs(
            client,
            project_id,
            limit=limit,
            capability_key=capability_key,
            outcome=query.get("outcome"),
        )
    )


def inspect_job(client: Any, job_id: str) -> dict[str, Any]:
    """Compose existing job and sealed receipt reads into one diagnosis bundle."""
    jid = job_id.strip()
    if not jid:
        raise ValueError("job_id is required")
    job = client.get_job(jid)
    receipt = None
    if job.get("receiptId"):
        try:
            receipt = client.get_job_receipt(jid)
        except Exception:  # noqa: BLE001 — inspection remains useful before receipt availability
            receipt = None
    return inspect_job_bundle(job, receipt)
