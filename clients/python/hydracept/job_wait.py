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
    payload = {
        "jobId": job_id,
        "state": status,
        "nextAction": hints["nextAction"],
        "statusView": {"jobId": job_id, "status": status, "nextAction": hints["nextAction"]},
        "job": job,
    }
    if hints.get("pollAfterSeconds") is not None:
        payload["pollAfterSeconds"] = hints["pollAfterSeconds"]
        payload["statusView"]["pollAfterSeconds"] = hints["pollAfterSeconds"]
    return payload
