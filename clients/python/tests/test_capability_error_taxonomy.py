"""Error identity invariant: a typo is never reported as a workspace problem."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
from hydracept.capability_errors import (
    AUTH_REQUIRED,
    BUDGET_EXCEEDED,
    CAPABILITY_NOT_CONFIGURED,
    UNKNOWN_CAPABILITY,
    WORKSPACE_CAPABILITY_DISABLED,
    classify_capability_error,
    suggest_capability_keys,
    unknown_capability_payload,
)
from hydracept.cli.run_facade import _map_api_error, execute_run
from hydracept.cli.workspace import ResolvedWorkspace
from hydracept.errors import HydraceptApiError


def _api_error(status: int, code: str, message: str = "boom") -> HydraceptApiError:
    request = httpx.Request("GET", "https://api.hydracept.com/v1/capabilities/image.nope.v9")
    response = httpx.Response(
        status, request=request, json={"detail": {"code": code, "message": message}}
    )
    return HydraceptApiError(
        f"{status} {code}: {message}",
        request=request,
        response=response,
        payload={"detail": {"code": code, "message": message}},
        code=code,
    )


def test_404_wins_over_disabled_language() -> None:
    assert (
        classify_capability_error(
            status=404, code="CapabilityDisabled", message="capability disabled for workspace"
        )
        == UNKNOWN_CAPABILITY
    )


def test_workspace_disabled_is_distinct_from_unknown() -> None:
    assert (
        classify_capability_error(
            status=200, code="CapabilityDisabled", message="disabled by workspace policy"
        )
        == WORKSPACE_CAPABILITY_DISABLED
    )


def test_auth_and_budget_and_not_configured_classification() -> None:
    assert classify_capability_error(status=401, code="whatever") == AUTH_REQUIRED
    assert classify_capability_error(status=402, code="EstimateExceedsMaxCost") == BUDGET_EXCEEDED
    assert (
        classify_capability_error(status=409, code="CONNECTION_REQUIRED")
        == CAPABILITY_NOT_CONFIGURED
    )


def test_suggestions_rank_same_family_first() -> None:
    catalog = {
        "capabilities": [
            {"key": "image.generate.v1"},
            {"key": "image.edit.v1"},
            {"key": "audio.generate.v1"},
        ]
    }
    suggestions = suggest_capability_keys("image.genrate.v1", catalog)
    assert suggestions
    assert suggestions[0].startswith("image.")
    assert "image.generate.v1" in suggestions


def test_unknown_capability_payload_never_points_at_connections() -> None:
    payload = unknown_capability_payload("image.nope.v9", [{"key": "image.generate.v1"}])
    assert payload["code"] == UNKNOWN_CAPABILITY
    assert payload["unknownCapability"] == "image.nope.v9"
    assert "image.generate.v1" in payload["suggestions"]
    assert "connections" not in str(payload).lower()


def test_map_api_error_promotes_unknown_capability_with_suggestions() -> None:
    mapped = _map_api_error(
        _api_error(404, "NOT_FOUND", "unknown capability"),
        capability="image.nope.v9",
        catalog=[{"key": "image.generate.v1"}],
    )
    assert mapped.code == UNKNOWN_CAPABILITY
    assert mapped.error_class == UNKNOWN_CAPABILITY
    assert mapped.details["unknownCapability"] == "image.nope.v9"
    assert mapped.details["suggestions"] == ["image.generate.v1"]


def test_map_api_error_disabled_is_not_unknown() -> None:
    mapped = _map_api_error(
        _api_error(403, "CapabilityDisabled", "disabled for this workspace"),
        capability="image.generate.v1",
    )
    assert mapped.code == "CapabilityDisabled"
    assert mapped.error_class == WORKSPACE_CAPABILITY_DISABLED
    assert "connections" not in str(mapped.recovery).lower()


def test_run_fails_fast_on_unknown_capability_with_suggestions(tmp_path: Path) -> None:
    class FakeClient:
        def describe_capability(self, key: str) -> dict:
            raise _api_error(404, "NOT_FOUND", f"unknown capability {key}")

        def capabilities(self) -> dict:
            return {"capabilities": [{"key": "image.generate.v1"}]}

    with patch(
        "hydracept.cli.run_facade.require_execution_context",
        return_value=(
            ResolvedWorkspace(
                api_url="https://api.hydracept.com",
                token="hapt_test",
                project_id="cpr_a",
                environment="development",
            ),
            None,
        ),
    ), patch("hydracept.cli.run_facade.HydraceptClient", return_value=FakeClient()):
        outcome = execute_run(
            tmp_path,
            "image.nope.v9",
            {"prompt": "icon"},
            wait=False,
            refresh_context=False,
        )
    assert outcome.exit_code == 1
    assert outcome.error is not None
    assert outcome.error.code == UNKNOWN_CAPABILITY
    assert outcome.error.details["suggestions"] == ["image.generate.v1"]


def _detail_string_error(status: int, detail: str) -> HydraceptApiError:
    request = httpx.Request("GET", "https://api.hydracept.com/v1/jobs/job_bogus")
    response = httpx.Response(status, request=request, json={"detail": detail})
    return HydraceptApiError(
        f"{status} {detail}",
        request=request,
        response=response,
        payload={"detail": detail},
        code="",
    )


def test_job_scoped_404_keeps_not_found_identity() -> None:
    assert (
        classify_capability_error(status=404, code="", message="Not found", scope="job") is None
    )
    mapped = _map_api_error(_detail_string_error(404, "Not found"), capability="", scope="job")
    assert mapped.code != UNKNOWN_CAPABILITY
    assert "unknownCapability" not in mapped.details


def test_capability_scoped_404_is_still_unknown_capability() -> None:
    assert (
        classify_capability_error(status=404, code="", message="Not found")
        == UNKNOWN_CAPABILITY
    )
    mapped = _map_api_error(
        _detail_string_error(404, "Not found"),
        capability="image.nope.v9",
        catalog=[{"key": "image.generate.v1"}],
    )
    assert mapped.code == UNKNOWN_CAPABILITY
    assert mapped.details["unknownCapability"] == "image.nope.v9"
