"""Structured job progress for wait/watch loops."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, TextIO

from hydracept.job_lifecycle import JobStatusView, classify_job


@dataclass(frozen=True)
class JobProgress:
    job_id: str
    status: str
    elapsed_seconds: float
    attempt: int
    waiting: bool
    terminal: bool
    human_gate: bool
    succeeded: bool
    next_action: str
    job: dict[str, Any]

    @classmethod
    def from_job(cls, job: dict[str, Any], *, job_id: str, elapsed_seconds: float, attempt: int) -> JobProgress:
        view: JobStatusView = classify_job(job)
        return cls(
            job_id=job_id,
            status=view.status,
            elapsed_seconds=elapsed_seconds,
            attempt=attempt,
            waiting=view.waiting,
            terminal=view.terminal,
            human_gate=view.human_gate,
            succeeded=view.succeeded,
            next_action=view.next_action,
            job=job,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "jobId": self.job_id,
            "status": self.status,
            "elapsedSeconds": round(self.elapsed_seconds, 3),
            "attempt": self.attempt,
            "waiting": self.waiting,
            "terminal": self.terminal,
            "humanGate": self.human_gate,
            "succeeded": self.succeeded,
            "nextAction": self.next_action,
        }

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), separators=(",", ":"))


def emit_progress(progress: JobProgress, stream: TextIO | None) -> None:
    """Write one JSON progress line and flush. Used so piped agent shells see waits immediately."""
    if stream is None:
        return
    stream.write(progress.as_json() + "\n")
    stream.flush()
