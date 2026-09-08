"""Init bootstrap session reuse and JSON wait contract tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from hydracept.cli.bootstrap_session_store import load_bootstrap_session
from hydracept.cli.exit_codes import AUTH, SUCCESS
from hydracept.cli.init_resolver import CANONICAL_INIT_COMMAND, VERBATIM_URL_INSTRUCTION, run_init


@pytest.fixture(autouse=True)
def _disable_ambient_local_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests cover session reuse, not GitHub auto-auth (see test_init_local_identity)."""
    monkeypatch.setattr(
        "hydracept.cli.init_resolver._try_local_identity_bootstrap",
        lambda *args, **kwargs: (None, [], {}),
    )


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")


def _session_payload(session_id: str) -> dict:
    return {
        "sessionId": session_id,
        "connectUrl": f"https://app.hydracept.com/connect/{session_id}?token=opaque-token",
        "expiresAt": "2030-01-01T00:00:00+00:00",
    }


def _assert_interaction_contract(payload: dict, session_id: str) -> None:
    expected_url = f"https://app.hydracept.com/connect/{session_id}?token=opaque-token"
    assert payload["status"] == "interaction_required"
    assert payload["type"] == "interaction_required"
    assert payload["kind"] == "activation"
    assert payload["blocking"] is True
    assert payload["code"] == payload["reason"]
    assert payload["recommendedAction"] == "present_project_connect"
    assert payload["instruction"] == VERBATIM_URL_INSTRUCTION
    assert "action.url verbatim" in payload["agentInstruction"]
    assert "Do not ask the human to name the project" in payload["agentInstruction"]
    assert "final tool call" in payload["agentInstruction"]
    assert "Do not start --wait" in payload["agentInstruction"]
    assert payload["bootstrapSessionId"] == session_id
    assert payload["expiresAt"] == "2030-01-01T00:00:00+00:00"
    assert payload["action"]["url"] == expected_url
    assert payload["action"]["sessionId"] == session_id
    assert payload["action"]["waitCommandJson"] == CANONICAL_INIT_COMMAND
    assert payload["bootstrapSession"] == {
        "sessionId": session_id,
        "activationUrl": expected_url,
        "expiresAt": "2030-01-01T00:00:00+00:00",
    }
    assert payload["afterCompletion"] == {
        "kind": "run_command",
        "command": CANONICAL_INIT_COMMAND,
    }
    assert payload["agentControl"] == {
        "mustStop": True,
        "resumeAfter": "human_activation_complete",
        "doNotPollBeforeResume": True,
    }
    interaction = payload["interaction"]
    assert interaction["schemaVersion"] == "hydracept.interaction.v1"
    assert interaction["surface"] == "project.connect"
    assert interaction["tool"] == "hydracept_interaction_surface"
    assert interaction["appUri"] == "ui://hydracept/app.html"
    assert interaction["context"]["actionUrl"] == expected_url


def test_init_interaction_is_self_contained_for_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.setattr("hydracept.cli.init_resolver.load_session", lambda: None)

    with patch(
        "hydracept.cli.init_resolver.httpx.post",
        return_value=FakeResponse(_session_payload("bs_agent")),
    ):
        result = run_init(tmp_path, apply=True, yes=True, json_output=True)

    _assert_interaction_contract(result.payload, "bs_agent")
    stored = load_bootstrap_session(tmp_path)
    assert stored.get("sessionId") == "bs_agent"
    assert stored.get("connectUrl") == result.payload["action"]["url"]


def test_init_accepts_server_activation_url_alias_verbatim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.setattr("hydracept.cli.init_resolver.load_session", lambda: None)
    exact_url = "https://app.hydracept.com/a/opaque?state=x%2Fy&sig=abc123"

    with patch(
        "hydracept.cli.init_resolver.httpx.post",
        return_value=FakeResponse(
            {
                "sessionId": "bs_alias",
                "activationUrl": exact_url,
                "expiresAt": "2030-01-01T00:00:00+00:00",
            }
        ),
    ):
        result = run_init(tmp_path, apply=True, yes=True, json_output=True)

    assert result.payload["action"]["url"] == exact_url
    assert result.payload["bootstrapSession"]["activationUrl"] == exact_url
    assert "connect/bs_alias" not in result.payload["action"]["url"]


def test_init_reuses_pending_bootstrap_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.setattr("hydracept.cli.init_resolver.load_session", lambda: None)
    post_calls = 0

    def fake_post(url: str, **kwargs) -> FakeResponse:
        nonlocal post_calls
        post_calls += 1
        return FakeResponse(_session_payload("bs_reuse"))

    def fake_get(url: str, **kwargs) -> FakeResponse:
        return FakeResponse(
            {
                "sessionId": "bs_reuse",
                "status": "pending",
                "connectUrl": _session_payload("bs_reuse")["connectUrl"],
                "expiresAt": "2030-01-01T00:00:00+00:00",
            }
        )

    with patch("hydracept.cli.init_resolver.httpx.post", side_effect=fake_post):
        with patch("hydracept.cli.init_resolver.httpx.get", side_effect=fake_get):
            first = run_init(tmp_path, apply=True, yes=True, json_output=True)
            second = run_init(tmp_path, apply=True, yes=True, json_output=True)

    _assert_interaction_contract(first.payload, "bs_reuse")
    _assert_interaction_contract(second.payload, "bs_reuse")
    assert post_calls == 1


def test_init_reuses_approved_bootstrap_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.setattr("hydracept.cli.init_resolver.load_session", lambda: None)

    def fake_get(url: str, **kwargs) -> FakeResponse:
        if "/v1/bootstrap/sessions/bs_done" in url:
            return FakeResponse(
                {
                    "sessionId": "bs_done",
                    "status": "approved",
                    "projectId": "cpr_test",
                    "environment": "development",
                    "installationApiKey": "hydracept_reuse_key",
                    "connectUrl": _session_payload("bs_done")["connectUrl"],
                    "expiresAt": "2030-01-01T00:00:00+00:00",
                }
            )
        if "/v1/diagnostics/" in url:
            return FakeResponse({"providers": {}, "capabilities": {}})
        raise AssertionError(f"unexpected get {url}")

    from hydracept.cli.bootstrap_session_store import save_bootstrap_session

    save_bootstrap_session(
        tmp_path,
        session_id="bs_done",
        connect_url=_session_payload("bs_done")["connectUrl"],
        api_url="https://api.hydracept.com",
        expires_at="2030-01-01T00:00:00+00:00",
    )

    post_calls = 0

    def counting_post(url: str, **kwargs) -> FakeResponse:
        nonlocal post_calls
        post_calls += 1
        return FakeResponse(_session_payload("unexpected"))

    with patch("hydracept.cli.init_resolver.httpx.post", side_effect=counting_post):
        with patch("hydracept.cli.init_resolver.httpx.get", side_effect=fake_get):
            with patch("hydracept.cli.init_resolver.build_doctor_report", return_value={}):
                with patch("hydracept.cli.init_resolver.doctor_exit_code", return_value=0):
                    with patch("hydracept.cli.init_resolver.run_configure"):
                        result = run_init(
                            tmp_path,
                            apply=True,
                            yes=True,
                            json_output=True,
                            wait=True,
                            poll_seconds=5,
                        )

    assert result.payload["status"] == "ready"
    assert post_calls == 0


def test_init_applies_approved_session_without_wait(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.setattr("hydracept.cli.init_resolver.load_session", lambda: None)

    def fake_get(url: str, **kwargs) -> FakeResponse:
        if "/v1/bootstrap/sessions/bs_done" in url:
            return FakeResponse(
                {
                    "sessionId": "bs_done",
                    "status": "approved",
                    "projectId": "cpr_test",
                    "environment": "development",
                    "installationApiKey": "hydracept_reuse_key",
                    "connectUrl": _session_payload("bs_done")["connectUrl"],
                    "expiresAt": "2030-01-01T00:00:00+00:00",
                }
            )
        if "/v1/diagnostics/" in url:
            return FakeResponse({"providers": {}, "capabilities": {}})
        raise AssertionError(f"unexpected get {url}")

    from hydracept.cli.bootstrap_session_store import save_bootstrap_session

    save_bootstrap_session(
        tmp_path,
        session_id="bs_done",
        connect_url=_session_payload("bs_done")["connectUrl"],
        api_url="https://api.hydracept.com",
        expires_at="2030-01-01T00:00:00+00:00",
    )

    with patch("hydracept.cli.init_resolver.httpx.post") as post:
        with patch("hydracept.cli.init_resolver.httpx.get", side_effect=fake_get):
            with patch("hydracept.cli.init_resolver.build_doctor_report", return_value={}):
                with patch("hydracept.cli.init_resolver.doctor_exit_code", return_value=0):
                    with patch("hydracept.cli.init_resolver.run_configure"):
                        result = run_init(
                            tmp_path,
                            apply=True,
                            yes=True,
                            json_output=True,
                            wait=False,
                        )

    assert result.payload["status"] == "ready"
    post.assert_not_called()


def test_init_json_wait_applies_approved_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.setattr("hydracept.cli.init_resolver.load_session", lambda: None)

    def fake_post(url: str, **kwargs) -> FakeResponse:
        if url.endswith("/v1/bootstrap/sessions"):
            return FakeResponse(_session_payload("bs_ready"))
        raise AssertionError(f"unexpected post {url}")

    def fake_get(url: str, **kwargs) -> FakeResponse:
        if "/v1/bootstrap/sessions/bs_ready" in url:
            return FakeResponse(
                {
                    "sessionId": "bs_ready",
                    "status": "approved",
                    "projectId": "cpr_test",
                    "environment": "development",
                    "installationApiKey": "hydracept_test_install_key",
                    "setupGrant": "hsg_test_grant",
                }
            )
        if "/v1/diagnostics/" in url:
            return FakeResponse({"providers": {}, "capabilities": {}})
        raise AssertionError(f"unexpected get {url}")

    with patch("hydracept.cli.init_resolver.httpx.post", side_effect=fake_post):
        with patch("hydracept.cli.init_resolver.httpx.get", side_effect=fake_get):
            with patch("hydracept.cli.init_resolver.build_doctor_report", return_value={}):
                with patch("hydracept.cli.init_resolver.doctor_exit_code", return_value=0):
                    with patch("hydracept.cli.init_resolver.run_configure"):
                        result = run_init(
                            tmp_path,
                            apply=True,
                            yes=True,
                            json_output=True,
                            wait=True,
                            poll_seconds=5,
                        )

    assert result.payload["status"] == "ready"
    assert "apiKey" not in json.dumps(result.payload)
    assert (tmp_path / ".hydracept" / "project.json").is_file()


def test_init_wait_timeout_preserves_session_url_expiry_and_recovery_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.setattr("hydracept.cli.init_resolver.load_session", lambda: None)
    clock = {"now": 1_000.0}
    post_calls = 0

    def fake_post(url: str, **kwargs) -> FakeResponse:
        nonlocal post_calls
        post_calls += 1
        return FakeResponse(_session_payload("bs_timeout"))

    def fake_get(url: str, **kwargs) -> FakeResponse:
        return FakeResponse(
            {
                "sessionId": "bs_timeout",
                "status": "pending",
                "connectUrl": _session_payload("bs_timeout")["connectUrl"],
                "expiresAt": "2030-01-01T00:00:00+00:00",
            }
        )

    monkeypatch.setattr("hydracept.cli.init_resolver.time.time", lambda: clock["now"])
    monkeypatch.setattr(
        "hydracept.cli.init_resolver.time.sleep",
        lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
    )

    with patch("hydracept.cli.init_resolver.httpx.post", side_effect=fake_post):
        with patch("hydracept.cli.init_resolver.httpx.get", side_effect=fake_get):
            result = run_init(
                tmp_path,
                apply=True,
                yes=True,
                json_output=True,
                wait=True,
                poll_seconds=5,
            )
            retry = run_init(tmp_path, apply=True, yes=True, json_output=True)

    assert result.exit_code == AUTH
    assert result.exit_code != SUCCESS
    assert result.payload["reason"] == "bootstrap_wait_timeout"
    _assert_interaction_contract(result.payload, "bs_timeout")
    _assert_interaction_contract(retry.payload, "bs_timeout")
    assert post_calls == 1
    err = capsys.readouterr().err
    assert '"status": "waiting"' in err
    assert _session_payload("bs_timeout")["connectUrl"] in err


def test_concurrent_waiters_resolve_same_approved_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.setattr("hydracept.cli.init_resolver.load_session", lambda: None)
    from concurrent.futures import ThreadPoolExecutor

    def fake_post(url: str, **kwargs) -> FakeResponse:
        if url.endswith("/v1/bootstrap/sessions"):
            return FakeResponse(_session_payload("bs_shared"))
        raise AssertionError(f"unexpected post {url}")

    def fake_get(url: str, **kwargs) -> FakeResponse:
        if "/v1/bootstrap/sessions/bs_shared" in url:
            return FakeResponse(
                {
                    "sessionId": "bs_shared",
                    "status": "approved",
                    "projectId": "cpr_shared",
                    "environment": "development",
                    "installationApiKey": "hydracept_shared_key",
                    "connectUrl": _session_payload("bs_shared")["connectUrl"],
                }
            )
        if "/v1/diagnostics/" in url:
            return FakeResponse({"providers": {}, "capabilities": {}})
        raise AssertionError(f"unexpected get {url}")

    with patch("hydracept.cli.init_resolver.httpx.post", side_effect=fake_post):
        with patch("hydracept.cli.init_resolver.httpx.get", side_effect=fake_get):
            with patch("hydracept.cli.init_resolver.build_doctor_report", return_value={}):
                with patch("hydracept.cli.init_resolver.doctor_exit_code", return_value=0):
                    with patch(
                        "hydracept.cli.init_resolver.try_install_agent_pack",
                        return_value=(True, ""),
                    ):
                        with patch("hydracept.cli.init_resolver.run_configure"):
                            def wait() -> str:
                                result = run_init(
                                    tmp_path,
                                    apply=True,
                                    yes=True,
                                    json_output=True,
                                    wait=True,
                                    poll_seconds=5,
                                )
                                assert result.payload["status"] == "ready"
                                return str((result.payload.get("project") or {}).get("id") or "")

                            with ThreadPoolExecutor(max_workers=2) as pool:
                                futures = [pool.submit(wait), pool.submit(wait)]
                                first, second = futures[0].result(), futures[1].result()

    assert first == "cpr_shared"
    assert second == "cpr_shared"
    binding = (tmp_path / ".hydracept" / "project.json").read_text(encoding="utf-8")
    assert "cpr_shared" in binding
