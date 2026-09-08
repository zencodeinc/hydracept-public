"""Local workspace context and automatic Hydracept project resolution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from hydracept.cli.local_project_context import (
    ContextField,
    LocalProjectContext,
    parse_github_remote,
    resolve_local_project_context,
)
from hydracept.cli.project_resolution import (
    AccessibleProject,
    apply_automatic_project,
    find_explicit_project,
    resolve_project_from_catalog,
)
from hydracept.cli.session_store import HumanSession
from hydracept.cli.init_resolver import run_init
from hydracept.cli.project import write_project_binding


def _field(value: str | None, confidence: str = "high", provenance: str = "test") -> ContextField:
    return ContextField(value=value, confidence=confidence, provenance=provenance)  # type: ignore[arg-type]


def _context(
    *,
    name: str,
    owner: str | None = None,
    repo: str | None = None,
    root: str = "/tmp/MyGame",
) -> LocalProjectContext:
    has_repo = bool(owner and repo)
    return LocalProjectContext(
        workspace_root=_field(root),
        display_name=_field(name, "high" if has_repo else "medium", "git:repository-name" if has_repo else "workspace:basename"),
        git_root=_field(root if has_repo else None),
        git_remote=_field(f"https://github.com/{owner}/{repo}.git" if has_repo else None),
        repository_provider=_field("github" if has_repo else None),
        repository_owner=_field(owner),
        repository_name=_field(repo),
        ide=_field("cursor"),
    )


def _project(
    project_id: str,
    name: str,
    *,
    org_id: str = "org_1",
    org_slug: str = "zencodeinc",
    org_name: str = "Zencode",
    repository: dict | None = None,
) -> AccessibleProject:
    return AccessibleProject(
        id=project_id,
        organization_id=org_id,
        organization_slug=org_slug,
        organization_name=org_name,
        slug=name.lower(),
        display_name=name,
        repository=repository,
    )


def test_parse_github_remote_https_and_ssh() -> None:
    assert parse_github_remote("https://github.com/zencodeinc/Hydratest19.git") == (
        "zencodeinc",
        "Hydratest19",
    )
    assert parse_github_remote("git@github.com:zencodeinc/foo.git") == ("zencodeinc", "foo")
    assert parse_github_remote("ssh://git@github.com/zencodeinc/foo") == ("zencodeinc", "foo")
    assert parse_github_remote("https://github.com/zencodeinc/Hydratest19.git/") == (
        "zencodeinc",
        "Hydratest19",
    )
    assert parse_github_remote("https://gitlab.com/acme/foo.git") is None


def test_resolve_local_context_uses_folder_name(tmp_path: Path) -> None:
    workspace = tmp_path / "Hydratest19"
    workspace.mkdir()
    context = resolve_local_project_context(workspace)
    assert context.inferred_name == "Hydratest19"
    assert context.display_name.provenance == "workspace:basename"


def test_unique_repository_match() -> None:
    context = _context(name="foo", owner="zencodeinc", repo="foo")
    projects = [
        _project(
            "cpr_foo",
            "foo",
            repository={"provider": "github", "owner": "zencodeinc", "name": "foo"},
        )
    ]
    result = resolve_project_from_catalog(
        context,
        projects=projects,
        organizations=[{"id": "org_1", "slug": "zencodeinc", "displayName": "Zencode"}],
    )
    assert result.state == "resolved"
    assert result.resolution == "repository_match"
    assert result.project_id == "cpr_foo"
    assert result.created is False


def test_new_workspace_creates_project() -> None:
    context = _context(name="MyGame")
    result = resolve_project_from_catalog(
        context,
        projects=[],
        organizations=[{"id": "org_1", "slug": "personal", "displayName": "Personal"}],
    )
    assert result.state == "resolved"
    assert result.created is True
    assert result.resolution == "created_from_workspace"
    assert result.display_name == "MyGame"
    assert result.organization_id == "org_1"


def test_github_unavailable_still_creates_from_folder() -> None:
    context = _context(name="MyGame")
    assert not context.has_github_repository
    result = resolve_project_from_catalog(
        context,
        projects=[],
        organizations=[{"id": "org_1", "displayName": "Solo"}],
    )
    assert result.state == "resolved"
    assert result.created is True
    assert result.environment == "development"


def test_ambiguous_existing_projects() -> None:
    context = _context(name="foo", owner="zencodeinc", repo="foo")
    projects = [
        _project("cpr_a", "foo", org_id="org_1"),
        _project("cpr_b", "foo", org_id="org_2", org_slug="other", org_name="Other"),
    ]
    result = resolve_project_from_catalog(
        context,
        projects=projects,
        organizations=[
            {"id": "org_1", "slug": "zencodeinc", "displayName": "Zencode"},
            {"id": "org_2", "slug": "other", "displayName": "Other"},
        ],
    )
    # Owner matches org_1 uniquely among name hits.
    assert result.state == "resolved"
    assert result.project_id == "cpr_a"

    projects = [
        _project("cpr_a", "foo", org_id="org_1", org_slug="acme", org_name="Acme"),
        _project("cpr_b", "foo", org_id="org_2", org_slug="other", org_name="Other"),
    ]
    result = resolve_project_from_catalog(
        context,
        projects=projects,
        organizations=[
            {"id": "org_1", "slug": "acme", "displayName": "Acme"},
            {"id": "org_2", "slug": "other", "displayName": "Other"},
        ],
    )
    # GitHub owner is zencodeinc; neither existing name hit lives there, so do
    # not bind a foreign-org namesake. Creation still needs a unique org.
    assert result.state == "ambiguous"
    assert result.reason == "multiple_organizations"


def test_ambiguous_name_hits_in_owner_org() -> None:
    context = _context(name="foo", owner="zencodeinc", repo="foo")
    projects = [
        _project("cpr_a", "foo", org_id="org_1", org_slug="zencodeinc", org_name="Zencode"),
        _project("cpr_b", "foo", org_id="org_1", org_slug="zencodeinc", org_name="Zencode"),
    ]
    result = resolve_project_from_catalog(
        context,
        projects=projects,
        organizations=[{"id": "org_1", "slug": "zencodeinc", "displayName": "Zencode"}],
    )
    assert result.state == "ambiguous"
    assert result.reason == "multiple_matching_projects"
    assert len(result.candidates) == 2


def test_multiple_organizations_no_safe_default() -> None:
    context = _context(name="MyGame")
    result = resolve_project_from_catalog(
        context,
        projects=[],
        organizations=[
            {"id": "org_1", "slug": "one", "displayName": "One"},
            {"id": "org_2", "slug": "two", "displayName": "Two"},
        ],
    )
    assert result.state == "ambiguous"
    assert result.reason == "multiple_organizations"


def test_home_org_creates_when_multiple_organizations() -> None:
    context = _context(name="Hydratest22")
    result = resolve_project_from_catalog(
        context,
        projects=[],
        organizations=[
            {"id": "org_1", "slug": "one", "displayName": "One"},
            {"id": "org_2", "slug": "two", "displayName": "Two"},
        ],
        preferred_organization_id="org_2",
    )
    assert result.state == "resolved"
    assert result.created is True
    assert result.organization_id == "org_2"
    assert result.display_name == "Hydratest22"


def test_git_owner_wins_over_home_org() -> None:
    context = _context(name="New Game", owner="zencodeinc", repo="new-game")
    result = resolve_project_from_catalog(
        context,
        projects=[],
        organizations=[
            {"id": "org_1", "slug": "zencodeinc", "displayName": "Zencode"},
            {"id": "org_2", "slug": "personal", "displayName": "Personal"},
        ],
        preferred_organization_id="org_2",
    )
    assert result.state == "resolved"
    assert result.created is True
    assert result.organization_id == "org_1"


def test_name_match_ignores_project_with_different_repository() -> None:
    context = _context(name="foo", owner="zencodeinc", repo="foo")
    projects = [
        _project(
            "cpr_other",
            "foo",
            repository={"provider": "github", "owner": "acme", "name": "foo"},
        )
    ]
    result = resolve_project_from_catalog(
        context,
        projects=projects,
        organizations=[{"id": "org_1", "slug": "zencodeinc", "displayName": "Zencode"}],
    )
    assert result.state == "resolved"
    assert result.created is True
    assert result.resolution == "created_from_repository"


def test_name_match_does_not_bind_unique_project_in_wrong_org() -> None:
    context = _context(name="foo", owner="zencodeinc", repo="foo")
    projects = [_project("cpr_acme", "foo", org_id="org_acme", org_slug="acme", org_name="Acme")]
    result = resolve_project_from_catalog(
        context,
        projects=projects,
        organizations=[{"id": "org_1", "slug": "zencodeinc", "displayName": "Zencode"}],
    )
    assert result.created is True
    assert result.project_id != "cpr_acme"
    assert result.resolution == "created_from_repository"


def test_explicit_selector_wins() -> None:
    projects = [_project("cpr_a", "Alpha"), _project("cpr_b", "Beta")]
    result = find_explicit_project("Beta", projects)
    assert result.state == "resolved"
    assert result.resolution == "explicit_selection"
    assert result.project_id == "cpr_b"


def _ready_patches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "hydracept.cli.init_resolver._ensure_installation_credential",
        lambda *args, **kwargs: ("hk_test", "created"),
    )
    monkeypatch.setattr("hydracept.cli.init_resolver.run_configure", lambda *args, **kwargs: None)
    monkeypatch.setattr("hydracept.cli.init_resolver.build_doctor_report", lambda *args, **kwargs: {})
    monkeypatch.setattr("hydracept.cli.init_resolver.doctor_exit_code", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr("hydracept.cli.init_resolver._fetch_readiness", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        "hydracept.cli.init_resolver._attach_mcp",
        lambda project_root, payload: payload,
    )
    monkeypatch.setattr("hydracept.cli.local_project_context.github_cli_login", lambda: None)


def test_existing_binding_skips_interaction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_project_binding(
        tmp_path,
        {"projectId": "cpr_bound", "environment": "development", "projectName": "Hydratest19"},
    )
    monkeypatch.setattr(
        "hydracept.cli.init_resolver.load_session",
        lambda: HumanSession(session_token="s", csrf_token="c", principal_id="usr_1"),
    )
    monkeypatch.setattr(
        "hydracept.cli.init_resolver.fetch_session_context",
        lambda: {
            "identity": {"provider": "github", "account": "jklappstein", "authenticated": True},
            "needsOnboarding": False,
        },
    )
    monkeypatch.setattr(
        "hydracept.cli.project_resolution.load_accessible_catalog",
        lambda: ([{"id": "org_1"}], [_project("cpr_bound", "Hydratest19")]),
    )
    _ready_patches(monkeypatch)
    result = run_init(tmp_path, apply=True, yes=True, json_output=True)
    assert result.payload["status"] == "ready"
    assert result.payload["project"]["id"] == "cpr_bound"
    assert result.payload["project"]["resolution"] == "existing_binding"
    assert result.payload["identity"]["authenticated"] is True


def test_session_present_without_binding_still_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "Hydratest19"
    workspace.mkdir()
    monkeypatch.setattr(
        "hydracept.cli.init_resolver.load_session",
        lambda: HumanSession(session_token="s", csrf_token="c", principal_id="usr_1"),
    )
    monkeypatch.setattr(
        "hydracept.cli.init_resolver.fetch_session_context",
        lambda: {
            "identity": {"provider": "github", "account": "jklappstein", "authenticated": True},
            "needsOnboarding": False,
            "project": {"id": "cpr_other", "displayName": "Other"},
        },
    )
    created: list[str] = []

    def fake_apply(context: LocalProjectContext, **_kwargs):
        from hydracept.cli.project_resolution import ProjectResolution

        created.append(context.inferred_name)
        return ProjectResolution(
            state="resolved",
            resolution="created_from_workspace",
            project_id="cpr_new",
            display_name=context.inferred_name,
            environment="development",
            organization_id="org_1",
            created=True,
        )

    monkeypatch.setattr(
        "hydracept.cli.project_resolution.apply_automatic_project",
        fake_apply,
    )
    monkeypatch.setattr(
        "hydracept.cli.project_resolution.load_accessible_catalog",
        lambda: ([{"id": "org_1"}], []),
    )
    _ready_patches(monkeypatch)
    result = run_init(workspace, apply=True, yes=True, json_output=True)
    assert result.payload["status"] == "ready"
    assert result.payload["project"]["id"] == "cpr_new"
    assert result.payload["project"]["resolution"] == "created_from_workspace"
    assert result.payload["project"]["environment"] == "development"
    assert result.payload["identity"]["account"] == "jklappstein"
    assert created == ["Hydratest19"]


def test_session_home_org_is_used_for_new_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "Hydratest22"
    workspace.mkdir()
    seen: dict[str, str | None] = {}
    monkeypatch.setattr(
        "hydracept.cli.init_resolver.load_session",
        lambda: HumanSession(session_token="s", csrf_token="c", principal_id="usr_1"),
    )
    monkeypatch.setattr(
        "hydracept.cli.init_resolver.fetch_session_context",
        lambda: {
            "identity": {"provider": "github", "account": "jklappstein", "authenticated": True},
            "needsOnboarding": False,
            "organization": {"id": "org_home", "displayName": "Home"},
        },
    )

    def fake_apply(context: LocalProjectContext, **kwargs):
        from hydracept.cli.project_resolution import ProjectResolution

        seen["preferred"] = kwargs.get("preferred_organization_id")
        return ProjectResolution(
            state="resolved",
            resolution="created_from_workspace",
            project_id="cpr_new",
            display_name=context.inferred_name,
            environment="development",
            organization_id="org_home",
            created=True,
        )

    monkeypatch.setattr(
        "hydracept.cli.project_resolution.apply_automatic_project",
        fake_apply,
    )
    monkeypatch.setattr(
        "hydracept.cli.project_resolution.load_accessible_catalog",
        lambda: (
            [
                {"id": "org_home", "displayName": "Home"},
                {"id": "org_other", "displayName": "Other"},
            ],
            [],
        ),
    )
    _ready_patches(monkeypatch)
    result = run_init(workspace, apply=True, yes=True, json_output=True)
    assert result.payload["status"] == "ready"
    assert seen["preferred"] == "org_home"
    assert result.payload["project"]["id"] == "cpr_new"


def test_repeat_init_does_not_create_duplicate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    writes = {"create": 0}

    def fake_apply(context: LocalProjectContext, **_kwargs):
        from hydracept.cli.project_resolution import ProjectResolution

        writes["create"] += 1
        return ProjectResolution(
            state="resolved",
            resolution="created_from_workspace",
            project_id="cpr_same",
            display_name=context.inferred_name,
            environment="development",
            created=True,
        )

    monkeypatch.setattr(
        "hydracept.cli.init_resolver.load_session",
        lambda: HumanSession(session_token="s", csrf_token="c", principal_id="usr_1"),
    )
    monkeypatch.setattr(
        "hydracept.cli.init_resolver.fetch_session_context",
        lambda: {"identity": {"provider": "github", "account": "jklappstein", "authenticated": True}},
    )
    monkeypatch.setattr("hydracept.cli.project_resolution.apply_automatic_project", fake_apply)
    monkeypatch.setattr("hydracept.cli.project_resolution.load_accessible_catalog", lambda: ([{"id": "org_1"}], []))
    _ready_patches(monkeypatch)
    first = run_init(tmp_path, apply=True, yes=True, json_output=True)
    second = run_init(tmp_path, apply=True, yes=True, json_output=True)
    assert first.payload["project"]["id"] == second.payload["project"]["id"] == "cpr_same"
    assert second.payload["project"]["resolution"] == "existing_binding"
    assert writes["create"] == 1


def test_ambiguous_projects_return_interaction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from hydracept.cli.project_resolution import ProjectResolution

    monkeypatch.setattr(
        "hydracept.cli.init_resolver.load_session",
        lambda: HumanSession(session_token="s", csrf_token="c", principal_id="usr_1"),
    )
    monkeypatch.setattr(
        "hydracept.cli.init_resolver.fetch_session_context",
        lambda: {"identity": {"provider": "github", "account": "jklappstein", "authenticated": True}},
    )
    monkeypatch.setattr(
        "hydracept.cli.project_resolution.apply_automatic_project",
        lambda *_args, **_kwargs: ProjectResolution(
            state="ambiguous",
            reason="multiple_matching_projects",
            candidates=[{"id": "cpr_a"}, {"id": "cpr_b"}],
        ),
    )
    monkeypatch.setattr("hydracept.cli.project_resolution.load_accessible_catalog", lambda: ([], []))
    monkeypatch.setattr("hydracept.cli.local_project_context.github_cli_login", lambda: None)
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    with patch("hydracept.cli.init_resolver.httpx.post") as post:
        post.return_value.json.return_value = {
            "sessionId": "bs_pick",
            "connectUrl": "https://api.hydracept.com/connect/bs_pick",
            "expiresAt": "2030-01-01T00:00:00+00:00",
        }
        post.return_value.status_code = 200
        post.return_value.raise_for_status = lambda: None
        result = run_init(tmp_path, apply=True, yes=True, json_output=True)
    assert result.payload["status"] == "interaction_required"
    assert result.payload["reason"] == "project_selection"
    assert result.payload["identity"]["authenticated"] is True
    assert result.payload["identity"]["account"] == "jklappstein"
    assert result.payload["projectResolution"]["reason"] == "multiple_matching_projects"


def test_corrupt_binding_does_not_auto_create(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from hydracept.cli.project import project_path

    path = project_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    created: list[bool] = []

    def fake_apply(*_args, **_kwargs):
        created.append(True)
        raise AssertionError("corrupt binding must not auto-create")

    monkeypatch.setattr(
        "hydracept.cli.init_resolver.load_session",
        lambda: HumanSession(session_token="s", csrf_token="c", principal_id="usr_1"),
    )
    monkeypatch.setattr(
        "hydracept.cli.init_resolver.fetch_session_context",
        lambda: {"identity": {"provider": "github", "account": "jklappstein", "authenticated": True}},
    )
    monkeypatch.setattr("hydracept.cli.project_resolution.apply_automatic_project", fake_apply)
    monkeypatch.setattr("hydracept.cli.project_resolution.load_accessible_catalog", lambda: ([], []))
    monkeypatch.setattr("hydracept.cli.local_project_context.github_cli_login", lambda: None)
    monkeypatch.delenv("HYDRACEPT_API_KEY", raising=False)
    with patch("hydracept.cli.init_resolver.httpx.post") as post:
        post.return_value.json.return_value = {
            "sessionId": "bs_corrupt",
            "connectUrl": "https://api.hydracept.com/connect/bs_corrupt",
            "expiresAt": "2030-01-01T00:00:00+00:00",
        }
        post.return_value.status_code = 200
        post.return_value.raise_for_status = lambda: None
        result = run_init(tmp_path, apply=True, yes=True, json_output=True)
    assert result.payload["status"] == "configuration_required"
    assert result.payload["reason"] == "corrupt_local_binding"
    assert created == []


def test_explicit_project_overrides_inference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "hydracept.cli.init_resolver.load_session",
        lambda: HumanSession(session_token="s", csrf_token="c", principal_id="usr_1"),
    )
    monkeypatch.setattr(
        "hydracept.cli.init_resolver.fetch_session_context",
        lambda: {"identity": {"provider": "github", "account": "jklappstein", "authenticated": True}},
    )
    monkeypatch.setattr(
        "hydracept.cli.project_resolution.load_accessible_catalog",
        lambda: (
            [{"id": "org_1"}],
            [_project("cpr_chosen", "Chosen"), _project("cpr_other", "Other")],
        ),
    )
    _ready_patches(monkeypatch)
    result = run_init(
        tmp_path,
        apply=True,
        yes=True,
        json_output=True,
        explicit_project="Chosen",
    )
    assert result.payload["status"] == "ready"
    assert result.payload["project"]["id"] == "cpr_chosen"
    assert result.payload["project"]["resolution"] == "explicit_selection"


def test_explicit_environment_is_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_project_binding(
        tmp_path,
        {"projectId": "cpr_bound", "environment": "development", "projectName": "Hydratest19"},
    )
    monkeypatch.setattr(
        "hydracept.cli.init_resolver.load_session",
        lambda: HumanSession(session_token="s", csrf_token="c", principal_id="usr_1"),
    )
    monkeypatch.setattr(
        "hydracept.cli.init_resolver.fetch_session_context",
        lambda: {
            "identity": {"provider": "github", "account": "jklappstein", "authenticated": True},
        },
    )
    monkeypatch.setattr(
        "hydracept.cli.project_resolution.load_accessible_catalog",
        lambda: ([{"id": "org_1"}], [_project("cpr_bound", "Hydratest19")]),
    )
    _ready_patches(monkeypatch)
    result = run_init(
        tmp_path,
        apply=True,
        yes=True,
        json_output=True,
        explicit_environment="staging",
    )
    assert result.payload["status"] == "ready"
    assert result.payload["project"]["environment"] == "staging"


def test_create_failure_is_not_authentication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from hydracept.cli.session_client import SessionClientError

    def _raise_create(*_args, **_kwargs):
        raise SessionClientError("create failed", status_code=500)

    monkeypatch.setattr(
        "hydracept.cli.init_resolver.load_session",
        lambda: HumanSession(session_token="s", csrf_token="c", principal_id="usr_1"),
    )
    monkeypatch.setattr(
        "hydracept.cli.init_resolver.fetch_session_context",
        lambda: {"identity": {"provider": "github", "account": "jklappstein", "authenticated": True}},
    )
    monkeypatch.setattr(
        "hydracept.cli.project_resolution.load_accessible_catalog",
        lambda: ([{"id": "org_1"}], []),
    )
    monkeypatch.setattr(
        "hydracept.cli.project_resolution.apply_automatic_project",
        _raise_create,
    )
    monkeypatch.setattr("hydracept.cli.local_project_context.github_cli_login", lambda: None)
    result = run_init(tmp_path, apply=True, yes=True, json_output=True)
    assert result.payload["status"] == "configuration_required"
    assert result.payload["reason"] == "project_resolution_failed"
    assert result.payload["identity"]["authenticated"] is True
    assert result.payload.get("reason") != "authentication"


def test_apply_automatic_project_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    context = _context(name="MyGame")
    created = {"count": 0}

    def fake_create(org_id: str, **kwargs):
        created["count"] += 1
        return {
            "id": "cpr_game",
            "displayName": kwargs["display_name"],
            "organizationId": org_id,
            "created": created["count"] == 1,
            "environment": "development",
        }

    monkeypatch.setattr(
        "hydracept.cli.session_client.list_organizations",
        lambda: [{"id": "org_1", "slug": "solo", "displayName": "Solo"}],
    )
    monkeypatch.setattr(
        "hydracept.cli.session_client.list_organization_projects",
        lambda _org: []
        if created["count"] == 0
        else [{"id": "cpr_game", "displayName": "MyGame", "slug": "mygame", "organizationId": "org_1"}],
    )
    monkeypatch.setattr("hydracept.cli.session_client.create_organization_project", fake_create)
    first = apply_automatic_project(context)
    second = apply_automatic_project(context)
    assert first.project_id == second.project_id == "cpr_game"
    assert first.created is True
    assert second.created is False
    assert created["count"] == 1
