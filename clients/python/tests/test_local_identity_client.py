from __future__ import annotations

import pytest

from hydracept.cli.identity import client
from hydracept.cli.identity.adapters import LocalIdentityHint, LocalIdentityProof
from hydracept.cli.session_store import DEFAULT_APP_BASE_URL, HumanSession
from hydracept.cli.workspace import DEFAULT_API


class _Response:
    def __init__(self, body: object, *, status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code
        self.is_error = status_code >= 400
        self.request = object()

    def json(self):
        return self._body


def _hint() -> LocalIdentityHint:
    return LocalIdentityHint(provider="github", account="octocat", source="gh")


def _proof() -> LocalIdentityProof:
    return LocalIdentityProof(
        provider="github",
        proof_type="oauth_access_token",
        secret="gho_super_secret",
    )


def _assertion_body() -> dict[str, object]:
    return {
        "schemaVersion": "hydracept.identity.session.v1",
        "identity": {"provider": "github", "account": "octocat"},
        "principalId": "usr_test",
        "sessionToken": "session-secret",
        "csrfToken": "csrf-secret",
        "projectId": "cpr_test",
        "environment": "development",
        "projectSelectionRequired": False,
    }


def test_assertion_pins_official_app_origin_and_delays_persistence(monkeypatch) -> None:
    client._TRANSIENT_SESSIONS.clear()
    monkeypatch.setenv("HYDRACEPT_APP_URL", "https://attacker.invalid")
    seen_urls: list[str] = []
    saved: list[HumanSession] = []

    def fake_post(url, **kwargs):
        seen_urls.append(url)
        return _Response(_assertion_body())

    monkeypatch.setattr(client.httpx, "post", fake_post)
    monkeypatch.setattr(client, "save_session", saved.append)

    body = client.assert_local_identity(
        hint=_hint(),
        proof=_proof(),
        bootstrap_session_id="bs_test",
    )

    assert body["principalId"] == "usr_test"
    assert seen_urls == [f"{DEFAULT_APP_BASE_URL}/v1/auth/identity-assertions"]
    assert saved == []
    assert client._TRANSIENT_SESSIONS["bs_test"].principal_id == "usr_test"


def test_assertion_rejects_wrong_response_provider(monkeypatch) -> None:
    client._TRANSIENT_SESSIONS.clear()
    body = _assertion_body()
    body["identity"] = {"provider": "google", "account": "person@example.com"}
    monkeypatch.setattr(client.httpx, "post", lambda *args, **kwargs: _Response(body))

    with pytest.raises(ValueError, match="different provider"):
        client.assert_local_identity(
            hint=_hint(),
            proof=_proof(),
            bootstrap_session_id="bs_test",
        )

    assert "bs_test" not in client._TRANSIENT_SESSIONS


def test_completion_refuses_custom_api_without_exporting_session(monkeypatch) -> None:
    client._TRANSIENT_SESSIONS.clear()
    client._TRANSIENT_SESSIONS["bs_test"] = HumanSession(
        session_token="session-secret",
        csrf_token="csrf-secret",
        principal_id="usr_test",
    )

    def should_not_post(*args, **kwargs):
        raise AssertionError("human session must not be sent to a custom API origin")

    monkeypatch.setattr(client.httpx, "post", should_not_post)

    with pytest.raises(RuntimeError, match="official Hydracept API"):
        client.complete_bootstrap_with_session(
            api_url="https://attacker.invalid",
            bootstrap_session_id="bs_test",
            project_id="cpr_test",
            environment="development",
        )

    assert "bs_test" not in client._TRANSIENT_SESSIONS


def test_completion_persists_session_only_after_approved_response(monkeypatch) -> None:
    client._TRANSIENT_SESSIONS.clear()
    transient = HumanSession(
        session_token="session-secret",
        csrf_token="csrf-secret",
        principal_id="usr_test",
    )
    client._TRANSIENT_SESSIONS["bs_test"] = transient
    saved: list[HumanSession] = []
    monkeypatch.setattr(
        client.httpx,
        "post",
        lambda *args, **kwargs: _Response(
            {
                "sessionId": "bs_test",
                "status": "approved",
                "projectId": "cpr_test",
                "environment": "development",
            }
        ),
    )
    monkeypatch.setattr(client, "save_session", saved.append)

    body = client.complete_bootstrap_with_session(
        api_url=DEFAULT_API,
        bootstrap_session_id="bs_test",
        project_id="cpr_test",
        environment="development",
    )

    assert body["status"] == "approved"
    assert saved == [transient]
    assert "bs_test" not in client._TRANSIENT_SESSIONS
