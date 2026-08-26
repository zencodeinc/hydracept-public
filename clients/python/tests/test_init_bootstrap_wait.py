"""Init bootstrap session reuse and JSON wait contract tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from hydracept.cli.bootstrap_session_store import load_bootstrap_session
from hydracept.cli.exit_codes import AUTH, SUCCESS
from hydracept.cli.init_resolver import run_init


def test_init_interaction_includes_bootstrap_session_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.setattr("hydracept.cli.init_resolver.load_session", lambda: None)

    class FakeResponse:
        def __init__(self, payload: dict, status_code: int = 200) -> None:
            self._payload = payload
            self.status_code = status_code

        def json(self) -> dict:
            return self._payload

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"status {self.status_code}")

    def fake_post(url: str, **kwargs) -> FakeResponse:
        return FakeResponse(
            {
                "sessionId": "bs_agent",
                "connectUrl": "https://api.hydracept.com/connect/bs_agent",
                "expiresAt": "2030-01-01T00:00:00+00:00",
            }
        )

    with patch("hydracept.cli.init_resolver.httpx.post", side_effect=fake_post):
        result = run_init(tmp_path, apply=True, yes=True, json_output=True)

    assert result.payload["status"] == "interaction_required"
    assert result.payload["bootstrapSessionId"] == "bs_agent"
    assert "waitCommandJson" in result.payload["action"]
    stored = load_bootstrap_session(tmp_path)
    assert stored.get("sessionId") == "bs_agent"


def test_init_reuses_pending_bootstrap_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.setattr("hydracept.cli.init_resolver.load_session", lambda: None)
    post_calls = 0

    class FakeResponse:
        def __init__(self, payload: dict, status_code: int = 200) -> None:
            self._payload = payload
            self.status_code = status_code

        def json(self) -> dict:
            return self._payload

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"status {self.status_code}")

    def fake_post(url: str, **kwargs) -> FakeResponse:
        nonlocal post_calls
        post_calls += 1
        return FakeResponse(
            {
                "sessionId": "bs_reuse",
                "connectUrl": "https://api.hydracept.com/connect/bs_reuse",
                "expiresAt": "2030-01-01T00:00:00+00:00",
            }
        )

    def fake_get(url: str, **kwargs) -> FakeResponse:
        return FakeResponse({"sessionId": "bs_reuse", "status": "pending"})

    with patch("hydracept.cli.init_resolver.httpx.post", side_effect=fake_post):
        with patch("hydracept.cli.init_resolver.httpx.get", side_effect=fake_get):
            first = run_init(tmp_path, apply=True, yes=True, json_output=True)
            second = run_init(tmp_path, apply=True, yes=True, json_output=True)

    assert first.payload["bootstrapSessionId"] == "bs_reuse"
    assert second.payload["bootstrapSessionId"] == "bs_reuse"
    assert post_calls == 1


def test_init_reuses_approved_bootstrap_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.setattr("hydracept.cli.init_resolver.load_session", lambda: None)

    class FakeResponse:
        def __init__(self, payload: dict, status_code: int = 200) -> None:
            self._payload = payload
            self.status_code = status_code

        def json(self) -> dict:
            return self._payload

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"status {self.status_code}")

    save_payload = {
        "sessionId": "bs_done",
        "connectUrl": "https://api.hydracept.com/connect/bs_done",
        "expiresAt": "2030-01-01T00:00:00+00:00",
    }

    def fake_post(url: str, **kwargs) -> FakeResponse:
        return FakeResponse(save_payload)

    def fake_get(url: str, **kwargs) -> FakeResponse:
        if "/v1/bootstrap/sessions/bs_done" in url:
            return FakeResponse(
                {
                    "sessionId": "bs_done",
                    "status": "approved",
                    "projectId": "cpr_test",
                    "environment": "development",
                    "installationApiKey": "hydracept_reuse_key",
                }
            )
        if "/v1/diagnostics/" in url:
            return FakeResponse({"providers": {}, "capabilities": {}})
        raise AssertionError(f"unexpected get {url}")

    from hydracept.cli.bootstrap_session_store import save_bootstrap_session

    save_bootstrap_session(
        tmp_path,
        session_id="bs_done",
        connect_url="https://api.hydracept.com/connect/bs_done",
        api_url="https://api.hydracept.com",
        expires_at="2030-01-01T00:00:00+00:00",
    )

    post_calls = 0

    def counting_post(url: str, **kwargs) -> FakeResponse:
        nonlocal post_calls
        post_calls += 1
        return fake_post(url, **kwargs)

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


def test_init_json_wait_applies_approved_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.setattr("hydracept.cli.init_resolver.load_session", lambda: None)

    class FakeResponse:
        def __init__(self, payload: dict, status_code: int = 200) -> None:
            self._payload = payload
            self.status_code = status_code

        def json(self) -> dict:
            return self._payload

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"status {self.status_code}")

    def fake_post(url: str, **kwargs) -> FakeResponse:
        if url.endswith("/v1/bootstrap/sessions"):
            return FakeResponse(
                {
                    "sessionId": "bs_ready",
                    "connectUrl": "https://api.hydracept.com/connect/bs_ready",
                    "expiresAt": "2030-01-01T00:00:00+00:00",
                }
            )
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
    binding_path = tmp_path / ".hydracept" / "project.json"
    assert binding_path.is_file()


def test_init_wait_timeout_exits_auth_and_emits_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    monkeypatch.setattr("hydracept.cli.init_resolver.load_session", lambda: None)
    clock = {"now": 1_000.0}

    class FakeResponse:
        def __init__(self, payload: dict, status_code: int = 200) -> None:
            self._payload = payload
            self.status_code = status_code

        def json(self) -> dict:
            return self._payload

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError(f"status {self.status_code}")

    def fake_post(url: str, **kwargs) -> FakeResponse:
        return FakeResponse(
            {
                "sessionId": "bs_timeout",
                "connectUrl": "https://api.hydracept.com/connect/bs_timeout",
                "expiresAt": "2030-01-01T00:00:00+00:00",
            }
        )

    def fake_get(url: str, **kwargs) -> FakeResponse:
        return FakeResponse({"sessionId": "bs_timeout", "status": "pending"})

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

    assert result.exit_code == AUTH
    assert result.exit_code != SUCCESS
    assert result.payload["status"] == "interaction_required"
    assert result.payload["reason"] == "bootstrap_wait_timeout"
    err = capsys.readouterr().err
    assert '"status": "waiting"' in err
    assert "https://api.hydracept.com/connect/bs_timeout" in err
