from __future__ import annotations

from hydracept.cli import init_resolver


def _applied(tmp_path):
    return init_resolver._BrowserBootstrapResult(
        api_key="hyd_test_key",
        project_id="cpr_test",
        environment="development",
        setup_grant="setup-test",
        binding={"projectId": "cpr_test", "environment": "development"},
    )


def test_new_bootstrap_session_tries_one_local_identity(monkeypatch, tmp_path) -> None:
    expected = _applied(tmp_path)
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(init_resolver, "load_bootstrap_session", lambda root: None)
    monkeypatch.setattr(
        init_resolver,
        "_create_bootstrap_session",
        lambda *args, **kwargs: ("bs_new", "https://api.hydracept.com/connect/bs_new", None),
    )
    monkeypatch.setattr(init_resolver, "unified_bootstrap_enabled", lambda: True)
    monkeypatch.setattr(init_resolver, "load_session", lambda: None)

    def fake_try(*args, **kwargs):
        calls.append(kwargs)
        return expected, [{"provider": "github", "account": "octocat", "source": "gh"}], {"outcome": "succeeded"}

    monkeypatch.setattr(init_resolver, "_try_local_identity_bootstrap", fake_try)

    result = init_resolver._bootstrap_interaction(
        "authentication",
        tmp_path,
        "https://api.hydracept.com",
        {"projectName": "demo"},
        wait=False,
        poll_seconds=1,
    )

    assert result is expected
    assert len(calls) == 1
    assert calls[0]["session_id"] == "bs_new"


def test_reused_pending_session_retries_local_identity(monkeypatch, tmp_path) -> None:
    expected = _applied(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(init_resolver, "load_bootstrap_session", lambda root: {"sessionId": "bs_existing"})
    monkeypatch.setattr(
        init_resolver,
        "_create_bootstrap_session",
        lambda *args, **kwargs: (
            "bs_existing",
            "https://api.hydracept.com/connect/bs_existing",
            None,
        ),
    )
    monkeypatch.setattr(init_resolver, "unified_bootstrap_enabled", lambda: True)
    monkeypatch.setattr(init_resolver, "load_session", lambda: None)

    def fake_try(*args, **kwargs):
        calls.append(str(kwargs.get("session_id") or ""))
        return expected, [{"provider": "github", "account": "octocat", "source": "gh"}], {"outcome": "succeeded"}

    monkeypatch.setattr(init_resolver, "_try_local_identity_bootstrap", fake_try)

    result = init_resolver._bootstrap_interaction(
        "authentication",
        tmp_path,
        "https://api.hydracept.com",
        {},
        wait=False,
        poll_seconds=1,
    )

    assert result is expected
    assert calls == ["bs_existing"]


def test_explicit_provider_can_complete_reused_session(monkeypatch, tmp_path) -> None:
    expected = _applied(tmp_path)
    seen: list[str | None] = []
    monkeypatch.setattr(init_resolver, "load_bootstrap_session", lambda root: {"sessionId": "bs_existing"})
    monkeypatch.setattr(
        init_resolver,
        "_create_bootstrap_session",
        lambda *args, **kwargs: (
            "bs_existing",
            "https://api.hydracept.com/connect/bs_existing",
            None,
        ),
    )
    monkeypatch.setattr(init_resolver, "unified_bootstrap_enabled", lambda: True)
    monkeypatch.setattr(init_resolver, "load_session", lambda: None)

    def fake_try(*args, **kwargs):
        seen.append(kwargs.get("requested_provider"))
        return expected, [{"provider": "github", "account": "octocat", "source": "gh"}], {"outcome": "succeeded"}

    monkeypatch.setattr(init_resolver, "_try_local_identity_bootstrap", fake_try)

    result = init_resolver._bootstrap_interaction(
        "authentication",
        tmp_path,
        "https://api.hydracept.com",
        {},
        wait=False,
        poll_seconds=1,
        identity_provider="github",
    )

    assert result is expected
    assert seen == ["github"]


def test_try_local_identity_falls_through_to_google(monkeypatch, tmp_path) -> None:
    from hydracept.cli.identity.adapters import LocalIdentityHint, LocalIdentityProof

    expected = _applied(tmp_path)
    github = LocalIdentityHint(provider="github", account="octocat", source="gh")
    google = LocalIdentityHint(provider="google", account="dev@example.com", source="gcloud")
    issued: list[str] = []

    monkeypatch.setattr(
        "hydracept.cli.identity.detect_local_identities",
        lambda: [github, google],
    )

    def fake_issue(hint):
        issued.append(hint.provider)
        if hint.provider == "github":
            raise RuntimeError("github unavailable")
        return LocalIdentityProof(
            provider="google",
            proof_type="oauth_access_token",
            secret="ya29.secret",
        )

    def fake_assert(*, hint, proof, bootstrap_session_id):
        assert hint.provider == "google"
        assert bootstrap_session_id == "bs_test"
        return {"projectId": "cpr_test", "environment": "development"}

    monkeypatch.setattr("hydracept.cli.identity.issue_local_identity_proof", fake_issue)
    monkeypatch.setattr("hydracept.cli.identity.assert_local_identity", fake_assert)
    monkeypatch.setattr(
        "hydracept.cli.identity.complete_bootstrap_with_session",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        init_resolver,
        "_fetch_bootstrap_session",
        lambda *args, **kwargs: {
            "status": "approved",
            "projectId": "cpr_test",
            "environment": "development",
        },
    )
    monkeypatch.setattr(init_resolver, "_apply_browser_bootstrap", lambda *args, **kwargs: expected)

    result, candidates, local_identity = init_resolver._try_local_identity_bootstrap(
        tmp_path,
        "https://api.hydracept.com",
        {"environment": "development"},
        session_id="bs_test",
    )

    assert result is expected
    assert local_identity["outcome"] == "succeeded"
    assert issued == ["github", "google"]
    assert [item["provider"] for item in candidates] == ["github", "google"]


def test_ci_without_key_never_enters_identity_bootstrap(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)

    def should_not_run(*args, **kwargs):
        raise AssertionError("CI must not touch local human identity")

    monkeypatch.setattr(init_resolver, "_bootstrap_interaction", should_not_run)
    result = init_resolver.run_init(tmp_path, apply=True, yes=True, ci_mode=True, json_output=True)

    assert result.payload["status"] == "configuration_required"
    assert result.payload["reason"] == "missing_api_key"


def test_expired_session_retries_local_identity(monkeypatch, tmp_path) -> None:
    from hydracept.cli.session_client import SessionClientError
    from hydracept.cli.session_store import HumanSession

    expected = _applied(tmp_path)
    state = {"live": True}
    calls: list[str] = []
    monkeypatch.setattr(init_resolver, "load_bootstrap_session", lambda root: None)
    monkeypatch.setattr(
        init_resolver,
        "_create_bootstrap_session",
        lambda *args, **kwargs: ("bs_stale", "https://api.hydracept.com/connect/bs_stale", None),
    )
    monkeypatch.setattr(init_resolver, "unified_bootstrap_enabled", lambda: True)
    monkeypatch.setattr(
        init_resolver,
        "load_session",
        lambda: HumanSession(session_token="s", csrf_token="c", principal_id="usr_1")
        if state["live"]
        else None,
    )

    def fake_fetch():
        raise SessionClientError("expired", status_code=401)

    def fake_clear():
        state["live"] = False

    monkeypatch.setattr(init_resolver, "fetch_session_context", fake_fetch)
    monkeypatch.setattr(init_resolver, "clear_session", fake_clear)

    def fake_try(*args, **kwargs):
        calls.append(str(kwargs.get("session_id") or ""))
        return expected, [{"provider": "github", "account": "octocat", "source": "gh"}], {"outcome": "succeeded"}

    monkeypatch.setattr(init_resolver, "_try_local_identity_bootstrap", fake_try)

    result = init_resolver._bootstrap_interaction(
        "authentication",
        tmp_path,
        "https://api.hydracept.com",
        {"projectName": "Hydratest22"},
        wait=False,
        poll_seconds=1,
    )

    assert result is expected
    assert calls == ["bs_stale"]
    assert state["live"] is False
