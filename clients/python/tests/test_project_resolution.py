"""Automatic project resolution from workspace identity."""

from __future__ import annotations

from pathlib import Path

from hydracept.cli.local_project_context import ContextField, LocalProjectContext
from hydracept.cli.project_resolution import AccessibleProject, resolve_project_from_catalog


def _context(*, name: str, owner: str | None = None, repo: str | None = None) -> LocalProjectContext:
    empty = ContextField(None, "low", "none")
    return LocalProjectContext(
        workspace_root=ContextField("/tmp/game", "high", "cli:cwd"),
        display_name=ContextField(name, "high", "git:repository-name"),
        git_root=ContextField("/tmp/game", "high", "git"),
        git_remote=empty,
        repository_provider=ContextField("github", "high", "git") if owner else empty,
        repository_owner=ContextField(owner, "high", "git") if owner else empty,
        repository_name=ContextField(repo or name, "high", "git") if owner else empty,
        ide=empty,
    )


def test_parse_github_remote() -> None:
    from hydracept.cli.local_project_context import parse_github_remote as parse

    assert parse("git@github.com:acme/hydra.git") == ("acme", "hydra")
    assert parse("https://github.com/acme/hydra.git") == ("acme", "hydra")


def test_unique_workspace_name_binds_existing_project() -> None:
    projects = [
        AccessibleProject(
            id="cpr_one",
            organization_id="org_1",
            slug="hydra",
            display_name="hydra",
        )
    ]
    resolved = resolve_project_from_catalog(
        _context(name="hydra"),
        projects=projects,
        organizations=[{"id": "org_1", "slug": "acme", "displayName": "Acme"}],
    )
    assert resolved.state == "resolved"
    assert resolved.project_id == "cpr_one"
    assert resolved.created is False


def test_duplicate_names_are_ambiguous() -> None:
    projects = [
        AccessibleProject(id="cpr_a", organization_id="org_1", slug="hydra", display_name="hydra"),
        AccessibleProject(id="cpr_b", organization_id="org_2", slug="hydra", display_name="hydra"),
    ]
    resolved = resolve_project_from_catalog(
        _context(name="hydra"),
        projects=projects,
        organizations=[
            {"id": "org_1", "slug": "a", "displayName": "A"},
            {"id": "org_2", "slug": "b", "displayName": "B"},
        ],
    )
    assert resolved.state == "ambiguous"
    assert resolved.reason == "multiple_matching_projects"


def test_unique_org_creates_from_workspace() -> None:
    resolved = resolve_project_from_catalog(
        _context(name="New Game"),
        projects=[],
        organizations=[{"id": "org_1", "slug": "acme", "displayName": "Acme"}],
    )
    assert resolved.state == "resolved"
    assert resolved.created is True
    assert resolved.organization_id == "org_1"
    assert resolved.display_name == "New Game"


def test_multiple_orgs_without_match_are_ambiguous() -> None:
    resolved = resolve_project_from_catalog(
        _context(name="New Game"),
        projects=[],
        organizations=[
            {"id": "org_1", "slug": "a", "displayName": "A"},
            {"id": "org_2", "slug": "b", "displayName": "B"},
        ],
    )
    assert resolved.state == "ambiguous"
    assert resolved.reason == "multiple_organizations"


def test_home_org_creates_when_multiple_orgs() -> None:
    resolved = resolve_project_from_catalog(
        _context(name="Hydratest22"),
        projects=[],
        organizations=[
            {"id": "org_1", "slug": "a", "displayName": "A"},
            {"id": "org_2", "slug": "b", "displayName": "B"},
        ],
        preferred_organization_id="org_1",
    )
    assert resolved.state == "resolved"
    assert resolved.created is True
    assert resolved.organization_id == "org_1"


def test_corrupt_binding_is_not_treated_as_unbound(tmp_path: Path) -> None:
    from hydracept.cli.project import load_project_binding, project_path

    path = project_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{not-json", encoding="utf-8")
    binding = load_project_binding(tmp_path)
    assert binding.get("corruptLocalBinding") is True
    assert not binding.get("projectId")


def test_bootstrap_conflict_rebinds_existing_project() -> None:
    from unittest.mock import patch

    from hydracept.cli.project_resolution import apply_automatic_project
    from hydracept.cli.session_client import SessionClientError

    existing = AccessibleProject(
        id="cpr_existing",
        organization_id="org_1",
        slug="new-game",
        display_name="New Game",
    )
    catalogs = [
        ([], []),
        ([{"id": "org_1", "slug": "acme", "displayName": "Acme"}], [existing]),
    ]

    def _catalog() -> tuple[list[dict], list[AccessibleProject]]:
        return catalogs.pop(0)

    with patch("hydracept.cli.project_resolution.load_accessible_catalog", side_effect=_catalog):
        with patch("hydracept.cli.session_client.create_organization_project") as create:
            with patch(
                "hydracept.cli.session_client.bootstrap_onboarding_project",
                side_effect=SessionClientError("conflict", status_code=409),
            ) as bootstrap:
                resolved = apply_automatic_project(_context(name="New Game"))
    assert resolved.project_id == "cpr_existing"
    assert resolved.created is False
    create.assert_not_called()
    bootstrap.assert_called_once()
