"""HydraceptClient watch/wait/download against a mock HTTP transport."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from hydracept import HydraceptClient, JobWaitTimeout
from hydracept.client import BoundWorkspace


def _client(handler) -> HydraceptClient:
    workspace = BoundWorkspace(
        api_url="https://api.test",
        project_id="prj_1",
        environment="development",
    )
    return HydraceptClient(
        "https://api.test",
        "tok_test",
        workspace=workspace,
        transport=httpx.MockTransport(handler),
    )


def test_watch_job_polls_until_succeeded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hydracept.client.time.sleep", lambda _seconds: None)
    states = [
        {"jobId": "job_1", "status": "queued"},
        {"jobId": "job_1", "status": "running"},
        {
            "jobId": "job_1",
            "status": "succeeded",
            "artifacts": [
                {
                    "artifactId": "art_1",
                    "label": "anvil",
                    "filename": "anvil.png",
                    "mediaType": "image/png",
                }
            ],
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/jobs/job_1"
        return httpx.Response(200, json=states.pop(0))

    with _client(handler) as client:
        progress = list(client.watch_job("job_1", interval=0.01, timeout=5))
    assert [item.status for item in progress] == ["queued", "running", "succeeded"]
    assert progress[-1].next_action == "download_artifacts"
    assert progress[-1].terminal is True


def test_wait_for_job_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hydracept.client.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("hydracept.client.time.monotonic", lambda: 100.0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jobId": "job_1", "status": "running"})

    with _client(handler) as client:
        with pytest.raises(JobWaitTimeout):
            client.wait_for_job("job_1", interval=1, timeout=1)


def test_submit_injects_workspace_context() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"jobId": "job_1", "status": "queued"})

    with _client(handler) as client:
        client.submit_capability_job("image.generate.v1", {"input": {"prompt": "x"}})
    body = json.loads(captured["body"])
    assert body["context"]["projectId"] == "prj_1"
    assert body["context"]["productId"] == "prj_1"
    assert body["context"]["environment"] == "development"
    assert body["input"]["prompt"] == "x"


def test_download_job_artifacts_uses_label(tmp_path: Path) -> None:
    job = {
        "jobId": "job_1",
        "status": "succeeded",
        "artifacts": [
            {
                "artifactId": "art_1",
                "label": "anvil",
                "filename": "props/anvil.png",
                "mediaType": "image/png",
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1/jobs/job_1":
            return httpx.Response(200, json=job)
        if request.url.path.endswith("/artifacts/art_1"):
            return httpx.Response(200, content=b"png-bytes", headers={"content-type": "image/png"})
        return httpx.Response(404)

    dest = tmp_path / "out"
    with _client(handler) as client:
        downloaded = client.download_job_artifacts("job_1", dest)
    assert len(downloaded) == 1
    assert downloaded[0].label == "anvil"
    assert downloaded[0].filename == "anvil.png"
    assert downloaded[0].path.read_bytes() == b"png-bytes"
    assert downloaded[0].sha256
