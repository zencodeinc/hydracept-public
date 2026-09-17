from __future__ import annotations

from types import SimpleNamespace

from hydracept.history import find_project_jobs, inspect_job, list_project_jobs


class FakeClient:
    def __init__(self) -> None:
        self.workspace = SimpleNamespace(project_id="cpr_test")
        self.paths: list[str] = []

    def _get(self, path: str):
        self.paths.append(path)
        return {"items": [{"jobId": "wfr_1", "status": "failed"}], "nextCursor": None}

    def get_job(self, job_id: str):
        assert job_id == "wfr_1"
        return {
            "jobId": job_id,
            "capabilityKey": "image.generate.v1",
            "status": "succeeded",
            "receiptId": "rcpt_wfr_1",
            "requestSnapshot": {"input": {"prompt": "make an icon"}, "idempotencyKey": "old"},
            "variantSet": {"selectedArtifactId": "art_selected"},
            "artifacts": [
                {"artifactId": "art_other", "kind": "output"},
                {"artifactId": "art_selected", "kind": "output", "selected": True},
            ],
        }

    def get_job_receipt(self, job_id: str):
        assert job_id == "wfr_1"
        return {
            "receiptId": "rcpt_wfr_1",
            "jobId": job_id,
            "status": "succeeded",
            "pricing": {
                "charge": {"customerCharge": {"amountMicros": 12500, "currency": "USD"}}
            },
            "route": {"provider": "example", "model": "model"},
            "artifacts": [{"artifactId": "art_selected"}],
        }


def test_list_project_jobs_uses_workspace_project_and_filters() -> None:
    client = FakeClient()
    payload = list_project_jobs(
        client,
        outcome="reusable",
        capability_key="image.generate.v1",
        selected=True,
        limit=7,
    )
    assert payload["items"]
    path = client.paths[-1]
    assert path.startswith("/v1/projects/cpr_test/jobs?")
    assert "outcome=reusable" in path
    assert "capabilityKey=image.generate.v1" in path
    assert "selected=true" in path
    assert "limit=7" in path


def test_find_project_jobs_adds_agent_next_action() -> None:
    client = FakeClient()
    payload = find_project_jobs(client, intent="failed")
    assert payload["nextAction"] == "inspect"
    assert "outcome=failed" in client.paths[-1]


def test_inspect_job_prefers_explicit_selected_artifact_and_preserves_snapshot() -> None:
    client = FakeClient()
    payload = inspect_job(client, "wfr_1")
    assert payload["nextAction"] == "reuse_selected"
    assert payload["reuseCandidateArtifactId"] == "art_selected"
    assert payload["reuseCandidateSelected"] is True
    assert payload["requestSnapshot"]["input"]["prompt"] == "make an icon"
    assert payload["receipt"]["costUsd"] == 0.0125
