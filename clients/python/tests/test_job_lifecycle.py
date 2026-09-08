"""Job status classification and wait contract."""

from __future__ import annotations

import io

from hydracept.job_lifecycle import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_WAIT_TIMEOUT_SECONDS,
    classify_job,
    classify_status,
    job_wait_contract,
)
from hydracept.job_progress import JobProgress, emit_progress


def test_classify_known_statuses() -> None:
    queued = classify_status("queued")
    assert queued.waiting is True
    assert queued.terminal is False
    assert queued.next_action == "poll"

    succeeded = classify_status("SUCCEEDED")
    assert succeeded.succeeded is True
    assert succeeded.terminal is True
    assert succeeded.next_action == "download_artifacts"

    approval = classify_status("awaiting_approval")
    assert approval.human_gate is True
    assert approval.terminal is True
    assert approval.waiting is False
    assert approval.next_action == "present_approval"

    attention = classify_status("needs_attention")
    assert attention.next_action == "inspect_error"

    failed = classify_status("failed")
    assert failed.next_action == "stop"

    canceled = classify_status("cancelled")
    assert canceled.status == "canceled"
    assert canceled.terminal is True
    assert canceled.next_action == "stop"


def test_unknown_status_keeps_polling() -> None:
    view = classify_status("paused")
    assert view.waiting is True
    assert view.terminal is False
    assert view.next_action == "poll"


def test_classify_job_reads_current_status() -> None:
    view = classify_job({"currentStatus": "running"})
    assert view.status == "running"
    assert view.next_action == "poll"


def test_job_wait_contract_matches_client_defaults() -> None:
    contract = job_wait_contract()
    assert contract["intervalSeconds"] == DEFAULT_POLL_INTERVAL_SECONDS
    assert contract["timeoutSeconds"] == DEFAULT_WAIT_TIMEOUT_SECONDS
    assert contract["unknownStatusKeepsPolling"] is True
    assert set(contract["waiting"]) == {"queued", "running", "canceling"}
    assert set(contract["terminal"]) == {
        "succeeded",
        "failed",
        "canceled",
        "awaiting_approval",
        "needs_attention",
    }
    assert set(contract["nextActions"]) == {
        "poll",
        "download_artifacts",
        "present_approval",
        "inspect_error",
        "stop",
    }


def test_emit_progress_flushes_json_line() -> None:
    stream = io.StringIO()
    progress = JobProgress.from_job(
        {"jobId": "job_1", "status": "queued"},
        job_id="job_1",
        elapsed_seconds=1.25,
        attempt=1,
    )
    emit_progress(progress, stream)
    line = stream.getvalue()
    assert line.endswith("\n")
    assert '"status":"queued"' in line
    assert '"nextAction":"poll"' in line
