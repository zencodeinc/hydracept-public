"""`keys verify` is a no-execution credential check with safe secret input."""

from __future__ import annotations

import json

import httpx
from typer.testing import CliRunner

from hydracept.cli import keys_cmd
from hydracept.errors import HydraceptApiError


class _FakeClient:
    last: "_FakeClient | None" = None

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url
        self.token = token
        self.closed = False
        _FakeClient.last = self

    def get_session_diagnostics(self) -> dict[str, object]:
        return {
            "principalId": "prn_fixture",
            "authMethod": "bearer",
            "scope": "product",
            "projectId": "cpr_fixture",
            "tokenProjectId": "cpr_fixture",
            "environment": "development",
            "credentialId": "tok_fixture",
            "scopes": ["capabilities:invoke", "jobs:read"],
            "expiresAt": None,
            "routeBundleVersion": "bundle_fixture",
            "routeBundleHash": "hash_fixture",
            "capabilitiesAlpha": 108,
        }

    def close(self) -> None:
        self.closed = True


def _patch_client(monkeypatch) -> None:
    _FakeClient.last = None
    monkeypatch.setattr(keys_cmd, "HydraceptClient", _FakeClient)


def test_keys_verify_reads_key_from_environment(monkeypatch) -> None:
    _patch_client(monkeypatch)
    monkeypatch.setenv("HYDRACEPT_API_KEY", "hydracept_fixture_key")

    result = CliRunner().invoke(keys_cmd.keys_app, ["verify", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["projectId"] == "cpr_fixture"
    assert _FakeClient.last is not None
    assert _FakeClient.last.token == "hydracept_fixture_key"
    assert _FakeClient.last.closed is True


def test_keys_verify_reads_key_from_stdin(monkeypatch) -> None:
    _patch_client(monkeypatch)
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)

    result = CliRunner().invoke(
        keys_cmd.keys_app,
        ["verify", "--json"],
        input="hydracept_stdin_key\n",
    )

    assert result.exit_code == 0, result.output
    assert _FakeClient.last is not None
    assert _FakeClient.last.token == "hydracept_stdin_key"


def test_keys_verify_without_a_key_is_an_auth_failure(monkeypatch) -> None:
    _patch_client(monkeypatch)
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)

    result = CliRunner().invoke(keys_cmd.keys_app, ["verify", "--json"], input="")

    assert result.exit_code == 3
    assert "No API key" in result.output


def test_keys_verify_rejects_a_revoked_key_as_auth_failure(monkeypatch) -> None:
    class _UnauthorizedClient(_FakeClient):
        def get_session_diagnostics(self) -> dict[str, object]:
            request = httpx.Request(
                "GET", "https://api.hydracept.com/v1/diagnostics/session"
            )
            response = httpx.Response(
                401,
                request=request,
                json={
                    "detail": {
                        "code": "AUTHORIZATION_FAILED",
                        "message": "Invalid or revoked API key",
                    }
                },
            )
            raise HydraceptApiError(
                "401 AUTHORIZATION_FAILED: Invalid or revoked API key",
                request=request,
                response=response,
                payload={},
                code="AUTHORIZATION_FAILED",
            )

    monkeypatch.setattr(keys_cmd, "HydraceptClient", _UnauthorizedClient)
    monkeypatch.setenv("HYDRACEPT_API_KEY", "hydracept_revoked_key")

    result = CliRunner().invoke(keys_cmd.keys_app, ["verify"])

    assert result.exit_code == 3
    assert "Invalid or revoked API key" in result.output


def test_keys_verify_does_not_accept_key_as_an_option(monkeypatch) -> None:
    _patch_client(monkeypatch)
    result = CliRunner().invoke(keys_cmd.keys_app, ["verify", "--help"])
    assert "--key" not in result.output
