"""Bootstrap session persistence tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hydracept.cli.bootstrap_session_store import (
    bootstrap_session_expired,
    bootstrap_session_path,
    clear_bootstrap_session,
    load_bootstrap_session,
    save_bootstrap_session,
    stored_bootstrap_session_matches_api,
)


def test_save_and_load_bootstrap_session(tmp_path: Path) -> None:
    save_bootstrap_session(
        tmp_path,
        session_id="bs_test",
        connect_url="https://api.hydracept.com/connect/bs_test",
        api_url="https://api.hydracept.com",
        expires_at="2030-01-01T00:00:00+00:00",
    )
    stored = load_bootstrap_session(tmp_path)
    assert stored["sessionId"] == "bs_test"
    assert stored_bootstrap_session_matches_api(stored, "https://api.hydracept.com")


def test_bootstrap_session_expired(tmp_path: Path) -> None:
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    save_bootstrap_session(
        tmp_path,
        session_id="bs_old",
        connect_url="https://api.hydracept.com/connect/bs_old",
        api_url="https://api.hydracept.com",
        expires_at=past,
    )
    stored = load_bootstrap_session(tmp_path)
    assert bootstrap_session_expired(stored)
    clear_bootstrap_session(tmp_path)
    assert not bootstrap_session_path(tmp_path).is_file()


def test_concurrent_clear_does_not_raise_when_file_already_gone(tmp_path: Path) -> None:
    save_bootstrap_session(
        tmp_path,
        session_id="bs_race",
        connect_url="https://api.hydracept.com/connect/bs_race",
        api_url="https://api.hydracept.com",
    )

    def clear() -> None:
        clear_bootstrap_session(tmp_path)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(clear), pool.submit(clear)]
        for future in futures:
            future.result()

    assert not bootstrap_session_path(tmp_path).is_file()
