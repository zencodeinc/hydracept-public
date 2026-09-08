"""Client-side wait hints so MCP tools match the agent job contract."""

from __future__ import annotations

from typing import Any

JOB_POLL_SECONDS = 4
_POLL_STATUSES = frozenset({"queued", "running", "canceling"})
_STOP_STATUSES = frozenset({"failed", "canceled"})


def job_wait_hints(status: str | None) -> dict[str, Any]:
    normalized = str(status or "").strip().lower()
    if normalized == "succeeded":
        return {"nextAction": "download_artifacts"}
    if normalized == "awaiting_approval":
        return {"nextAction": "present_approval"}
    if normalized == "needs_attention":
        return {"nextAction": "inspect_error"}
    if normalized in _STOP_STATUSES:
        return {"nextAction": "stop"}
    return {"nextAction": "poll", "pollAfterSeconds": JOB_POLL_SECONDS}


def infer_receipt_id(job: dict[str, Any]) -> str | None:
    explicit = str(job.get("receiptId") or "").strip()
    if explicit:
        return explicit
    status = str(job.get("status") or job.get("currentStatus") or "").strip().lower()
    job_id = str(job.get("jobId") or job.get("id") or "")
    if status in {"succeeded", "failed", "canceled"} and job_id.startswith("wfr_"):
        return f"rcpt_{job_id}"
    return None


def infer_primary_artifact_id(job: dict[str, Any]) -> str | None:
    explicit = str(job.get("primaryArtifactId") or "").strip()
    if explicit:
        return explicit
    variant = job.get("variantSet") if isinstance(job.get("variantSet"), dict) else {}
    selected = str(variant.get("selectedArtifactId") or "").strip()
    if selected:
        return selected
    artifacts = job.get("artifacts") if isinstance(job.get("artifacts"), list) else []
    chosen = [
        str(item.get("artifactId") or "").strip()
        for item in artifacts
        if isinstance(item, dict) and item.get("selected") is True and item.get("artifactId")
    ]
    if len(chosen) == 1:
        return chosen[0]
    ids = [
        str(item.get("artifactId") or "").strip()
        for item in artifacts
        if isinstance(item, dict) and item.get("artifactId")
    ]
    if len(ids) == 1:
        return ids[0]
    return None


def infer_preview_artifact_id(job: dict[str, Any]) -> str | None:
    primary = infer_primary_artifact_id(job)
    if primary:
        return primary
    artifacts = job.get("artifacts") if isinstance(job.get("artifacts"), list) else []
    ranked: list[tuple[int, str]] = []
    for item in artifacts:
        if not isinstance(item, dict) or not item.get("artifactId"):
            continue
        if str(item.get("slotStatus") or "").lower() not in {"", "succeeded"}:
            continue
        index = item.get("variantIndex")
        rank = int(index) if isinstance(index, int) else 10_000
        ranked.append((rank, str(item.get("artifactId")).strip()))
    ranked.sort(key=lambda pair: pair[0])
    return ranked[0][1] if ranked else None


def decorate_job_tool_result(job: dict[str, Any]) -> dict[str, Any]:
    job_id = str(job.get("jobId") or job.get("id") or "")
    status = str(job.get("status") or job.get("currentStatus") or "")
    hints = job_wait_hints(status)
    if job.get("nextAction"):
        hints["nextAction"] = job["nextAction"]
        if job.get("pollAfterSeconds") is not None:
            hints["pollAfterSeconds"] = job["pollAfterSeconds"]
        elif hints["nextAction"] != "poll":
            hints.pop("pollAfterSeconds", None)
    waiting = hints["nextAction"] == "poll"
    receipt_id = infer_receipt_id(job)
    primary = infer_primary_artifact_id(job)
    preview = infer_preview_artifact_id(job)
    payload = {
        "jobId": job_id,
        "state": status,
        "waiting": waiting,
        "terminal": not waiting,
        "nextAction": hints["nextAction"],
        "receiptId": receipt_id,
        "primaryArtifactId": primary,
        "previewArtifactId": preview,
        "projectId": job.get("projectId"),
        "statusView": {
            "jobId": job_id,
            "status": status,
            "nextAction": hints["nextAction"],
            "waiting": waiting,
            "terminal": not waiting,
            "receiptId": receipt_id,
            "primaryArtifactId": primary,
            "previewArtifactId": preview,
        },
        "job": job,
    }
    if hints.get("pollAfterSeconds") is not None:
        payload["pollAfterSeconds"] = hints["pollAfterSeconds"]
        payload["statusView"]["pollAfterSeconds"] = hints["pollAfterSeconds"]
    else:
        payload["pollAfterSeconds"] = 0
        payload["statusView"]["pollAfterSeconds"] = 0
    error = job.get("error")
    if isinstance(error, dict) and isinstance(error.get("recovery"), dict):
        payload["recovery"] = error["recovery"]
        payload["statusView"]["recovery"] = error["recovery"]
    return payload
