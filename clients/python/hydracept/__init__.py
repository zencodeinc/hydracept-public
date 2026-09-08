"""Hydracept Python client — public API surface."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path

from hydracept.artifact_naming import DownloadedArtifact
from hydracept.client import HydraceptClient, iter_invocation_events
from hydracept.http_timeout import http_timeout
from hydracept.job_lifecycle import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_WAIT_TIMEOUT_SECONDS,
    JobNotSucceeded,
    JobStatusView,
    JobWaitTimeout,
    classify_job,
    classify_status,
    job_wait_contract,
)
from hydracept.job_progress import JobProgress
from hydracept.workspace import HydraceptWorkspace

_http_timeout = http_timeout


def _package_version() -> str:
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if pyproject.is_file():
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("version ="):
                value = stripped.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    try:
        return package_version("hydracept")
    except PackageNotFoundError:
        return "0.0.0+local"


__version__ = _package_version()

__all__ = [
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "DEFAULT_WAIT_TIMEOUT_SECONDS",
    "DownloadedArtifact",
    "HydraceptClient",
    "HydraceptWorkspace",
    "JobNotSucceeded",
    "JobProgress",
    "JobStatusView",
    "JobWaitTimeout",
    "__version__",
    "classify_job",
    "classify_status",
    "http_timeout",
    "iter_invocation_events",
    "job_wait_contract",
]
