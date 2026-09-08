"""MCP job status payload classifies nextAction without blocking."""

from __future__ import annotations

from hydracept.job_lifecycle import DEFAULT_POLL_INTERVAL_SECONDS
from hydracept.mcp.server import _status_payload


def test_status_payload_asks_agent_to_poll() -> None:
    payload = _status_payload("job_1", {"jobId": "job_1", "status": "queued"})
    assert payload["waiting"] is True
    assert payload["terminal"] is False
    assert payload["nextAction"] == "poll"
    assert payload["pollAfterSeconds"] == DEFAULT_POLL_INTERVAL_SECONDS
    assert payload["state"] == "queued"


def test_status_payload_stops_on_success() -> None:
    payload = _status_payload(
        "job_1",
        {
            "jobId": "job_1",
            "status": "succeeded",
            "receiptId": "rcpt_1",
            "primaryArtifactId": "art_1",
            "projectId": "cpr_1",
        },
    )
    assert payload["terminal"] is True
    assert payload["nextAction"] == "download_artifacts"
    assert payload["pollAfterSeconds"] == 0
    assert payload["receiptId"] == "rcpt_1"
    assert payload["primaryArtifactId"] == "art_1"
    assert payload["projectId"] == "cpr_1"


def test_status_payload_infers_primary_when_api_omits_it() -> None:
    payload = _status_payload(
        "wfr_live",
        {
            "jobId": "wfr_live",
            "status": "succeeded",
            "artifacts": [
                {"artifactId": "art_only", "selected": True, "filename": "hero.png"},
            ],
            "variantSet": {"selectedArtifactId": "art_only"},
        },
    )
    assert payload["primaryArtifactId"] == "art_only"
    assert payload["receiptId"] == "rcpt_wfr_live"


def test_status_payload_preview_picks_first_unselected_variant() -> None:
    payload = _status_payload(
        "wfr_two",
        {
            "jobId": "wfr_two",
            "status": "succeeded",
            "artifacts": [
                {"artifactId": "art_a", "variantIndex": 0, "slotStatus": "succeeded", "selected": None},
                {"artifactId": "art_b", "variantIndex": 1, "slotStatus": "succeeded", "selected": None},
            ],
            "variantSet": {"selectedArtifactId": None},
        },
    )
    assert payload["primaryArtifactId"] is None
    assert payload["previewArtifactId"] == "art_a"
