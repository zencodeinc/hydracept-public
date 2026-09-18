"""Job status groupings, wait policy, and poll classification for agents."""

from __future__ import annotations

from dataclasses import dataclass

# Keep in sync with hydracept_contracts.HydraceptJobStatus.
WAITING_STATUSES = frozenset({"queued", "running", "canceling"})
SUCCESS_STATUSES = frozenset({"succeeded"})
HUMAN_GATE_STATUSES = frozenset({"awaiting_approval", "needs_attention"})
FAILURE_STATUSES = frozenset({"failed", "canceled"})
TERMINAL_STATUSES = SUCCESS_STATUSES | HUMAN_GATE_STATUSES | FAILURE_STATUSES
DEFAULT_POLL_INTERVAL_SECONDS = 4.0
DEFAULT_WAIT_TIMEOUT_SECONDS = 600.0


def normalize_job_status(value: object) -> str:
    status = str(value or "").strip().lower()
    if status == "cancelled":
        return "canceled"
    return status


def status_from_job(job: dict[str, object]) -> str:
    return normalize_job_status(job.get("status") or job.get("currentStatus"))


def job_id_from_payload(payload: dict[str, object]) -> str:
    return str(payload.get("jobId") or payload.get("id") or "").strip()


@dataclass(frozen=True)
class JobStatusView:
    status: str
    waiting: bool
    terminal: bool
    human_gate: bool
    succeeded: bool
    next_action: str

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "waiting": self.waiting,
            "terminal": self.terminal,
            "humanGate": self.human_gate,
            "succeeded": self.succeeded,
            "nextAction": self.next_action,
        }


def classify_status(status: object) -> JobStatusView:
    normalized = normalize_job_status(status)
    terminal = normalized in TERMINAL_STATUSES
    # Unknown / future statuses keep polling until timeout. Only known terminals stop.
    waiting = not terminal
    succeeded = normalized in SUCCESS_STATUSES
    human_gate = normalized in HUMAN_GATE_STATUSES
    if waiting:
        next_action = "poll"
    elif succeeded:
        next_action = "download_artifacts"
    elif normalized == "awaiting_approval":
        next_action = "present_approval"
    elif normalized == "needs_attention":
        next_action = "inspect_error"
    else:
        next_action = "stop"
    return JobStatusView(
        status=normalized or "unknown",
        waiting=waiting,
        terminal=terminal,
        human_gate=human_gate,
        succeeded=succeeded,
        next_action=next_action,
    )


def classify_job(job: dict[str, object]) -> JobStatusView:
    return classify_status(status_from_job(job))


def job_wait_contract() -> dict[str, object]:
    return {
        "intervalSeconds": DEFAULT_POLL_INTERVAL_SECONDS,
        "timeoutSeconds": DEFAULT_WAIT_TIMEOUT_SECONDS,
        "unknownStatusKeepsPolling": True,
        "waiting": sorted(WAITING_STATUSES),
        "terminal": sorted(TERMINAL_STATUSES),
        "humanGate": sorted(HUMAN_GATE_STATUSES),
        "success": sorted(SUCCESS_STATUSES),
        "failure": sorted(FAILURE_STATUSES),
        "nextActions": {
            "poll": "Job is still running — call get_job / hydracept_job_status again after intervalSeconds.",
            "download_artifacts": "Job succeeded — download by artifact.label or artifact.filename.",
            "present_approval": "Stop polling. Show the approval URL or quote to the human.",
            "inspect_error": "Stop polling. Read job.error.resolution and job.error.recovery before any resubmit. Do not retry a sealed route that is not routable.",
            "stop": "Terminal failure or cancel. Do not poll again. Read job.error.resolution before resubmitting.",
        },
    }


class JobWaitTimeout(Exception):
    def __init__(self, job_id: str, status: str, elapsed_seconds: float) -> None:
        self.job_id = job_id
        self.status = status
        self.elapsed_seconds = elapsed_seconds
        super().__init__(
            f"Timed out after {elapsed_seconds:.0f}s waiting for job {job_id} (last status={status}). "
            f"Poll GET /v1/jobs/{job_id} or hydracept_job_status."
        )


class JobNotSucceeded(Exception):
    def __init__(self, job_id: str, status: str, job: dict[str, object]) -> None:
        self.job_id = job_id
        self.status = status
        self.job = job
        super().__init__(f"Job {job_id} ended with status={status}")
