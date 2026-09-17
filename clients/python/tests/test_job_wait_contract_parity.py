"""The public wait contract has one authority; this pins the client's projection to it.

``hydracept_contracts.job_wait`` owns the wait interval and timeout. The Python client
ships as a separate distribution and therefore cannot import that package, so it carries
its own constants. This test — not a "keep in sync" comment — is what makes the
duplication safe: if either side moves, CI fails.
"""

from __future__ import annotations

from hydracept.job_lifecycle import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_WAIT_TIMEOUT_SECONDS,
    job_wait_contract,
)
from hydracept_contracts.job_wait import (
    JOB_POLL_SECONDS,
    JOB_WAIT_TIMEOUT_SECONDS,
    job_wait_hints,
)


def test_client_poll_interval_matches_the_authority() -> None:
    assert DEFAULT_POLL_INTERVAL_SECONDS == JOB_POLL_SECONDS


def test_client_wait_timeout_matches_the_authority() -> None:
    assert DEFAULT_WAIT_TIMEOUT_SECONDS == JOB_WAIT_TIMEOUT_SECONDS


def test_client_wait_contract_projects_the_authority() -> None:
    contract = job_wait_contract()
    assert contract["intervalSeconds"] == JOB_POLL_SECONDS
    assert contract["timeoutSeconds"] == JOB_WAIT_TIMEOUT_SECONDS


def test_authority_still_publishes_poll_after_seconds() -> None:
    # Guards the value the client and agent-context both project.
    hints = job_wait_hints("running")
    assert hints["nextAction"] == "poll"
    assert hints["pollAfterSeconds"] == JOB_POLL_SECONDS
