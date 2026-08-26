"""Tests for global session store."""

from __future__ import annotations

from pathlib import Path

from hydracept.cli.session_store import HumanSession, load_session, save_session


def test_save_and_load_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("hydracept.cli.session_store.global_hydracept_dir", lambda: tmp_path)
    session = HumanSession(
        session_token="sess",
        csrf_token="csrf",
        principal_id="usr_test",
    )
    save_session(session)
    loaded = load_session()
    assert loaded is not None
    assert loaded.session_token == "sess"
    assert loaded.principal_id == "usr_test"


def test_keys_configure_does_not_touch_session(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("hydracept.cli.session_store.global_hydracept_dir", lambda: home / ".hydracept")
    save_session(
        HumanSession(session_token="a", csrf_token="b", principal_id="usr_1"),
    )
    from hydracept.cli.bootstrap import write_secrets

    repo = tmp_path / "repo"
    write_secrets(repo, {"apiKey": "hydracept_test", "kind": "api_key"})
    loaded = load_session()
    assert loaded is not None
    assert loaded.session_token == "a"
