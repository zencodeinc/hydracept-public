"""The failure taxonomy has one authority; this pins the client's mirror to it.

``hydracept_contracts.hydracept_job`` owns the code-to-resolution mapping. The Python
client ships as a separate distribution and cannot import that package, so it carries a
mirror. This test - not a "keep in sync" comment - is what makes the duplication safe.
"""

from __future__ import annotations

import ast
from pathlib import Path

from hydracept.job_error import (
    JOB_ERROR_TAXONOMY as CLIENT_TAXONOMY,
    UNKNOWN_JOB_ERROR_RESOLUTION as CLIENT_UNKNOWN,
    attach_error_projection,
    job_error_guidance,
    project_job_error,
)
from hydracept_contracts.hydracept_job import (
    JOB_ERROR_TAXONOMY as AUTHORITY_TAXONOMY,
    UNKNOWN_JOB_ERROR_RESOLUTION,
    project_job_error as authority_project_job_error,
)


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _taxonomy_source_keys(path: Path, name: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        else:
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in targets):
            continue
        if not isinstance(value, ast.Dict):
            continue
        keys: list[str] = []
        for key in value.keys:
            if isinstance(key, ast.Attribute):
                keys.append(ast.unparse(key))
            elif isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys.append(key.value)
        return keys
    raise AssertionError(f"{name} literal not found in {path}")


def test_taxonomy_source_has_no_duplicate_keys() -> None:
    server = _taxonomy_source_keys(
        _REPO_ROOT / "packages/contracts/hydracept_contracts/hydracept_job.py",
        "JOB_ERROR_TAXONOMY",
    )
    client = _taxonomy_source_keys(
        _REPO_ROOT / "clients/python/hydracept/job_error.py",
        "JOB_ERROR_TAXONOMY",
    )
    assert server and client
    assert len(server) == len(set(server))
    assert len(client) == len(set(client))


def test_client_taxonomy_matches_the_authority_exactly() -> None:
    assert set(CLIENT_TAXONOMY) == set(AUTHORITY_TAXONOMY)
    for code, entry in AUTHORITY_TAXONOMY.items():
        client = CLIENT_TAXONOMY[code]
        assert client["resolution"] == entry.resolution, code
        assert client["retryable"] == entry.retryable, code
        assert client["terminal"] == entry.terminal, code


def test_client_unknown_resolution_matches_the_authority() -> None:
    assert CLIENT_UNKNOWN == UNKNOWN_JOB_ERROR_RESOLUTION


def test_client_projection_matches_the_authority_projection() -> None:
    for code in ("ProviderTimeout", "InvalidInput", "TRANSPORT_AMBIGUOUS", "failed"):
        error = {"code": code, "message": "boom"}
        assert project_job_error(error) == authority_project_job_error(
            code=code, message="boom", extra=error
        ), code


def test_unknown_code_is_not_given_invented_advice() -> None:
    assert job_error_guidance("NOT_A_REAL_CODE") is None
    projected = project_job_error({"code": "NOT_A_REAL_CODE", "message": "boom"})
    assert projected is not None
    assert projected["resolution"] == UNKNOWN_JOB_ERROR_RESOLUTION


def test_server_provided_resolution_wins() -> None:
    projected = project_job_error(
        {
            "code": "ProviderTimeout",
            "message": "timed out",
            "resolution": "server-authored guidance",
        }
    )
    assert projected is not None
    assert projected["resolution"] == "server-authored guidance"


def test_attach_error_projection_enriches_known_codes_only() -> None:
    known = attach_error_projection({"code": "RateLimited", "message": "slow"})
    assert known["retryable"] is True
    assert known["terminal"] is False
    assert "rate-limited" in known["resolution"]

    unknown = attach_error_projection({"code": "DATABASE_UNAVAILABLE", "message": "db"})
    assert "resolution" not in unknown
    assert "terminal" not in unknown
