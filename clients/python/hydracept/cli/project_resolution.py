"""Resolve a Hydracept project from local workspace context.

Matching is conservative: exact repository identity or unique exact name.
Creation is aggressive when the workspace identity is clear and the org is unique.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from hydracept.cli.local_project_context import LocalProjectContext

ResolutionValue = Literal[
    "existing_binding",
    "repository_match",
    "workspace_match",
    "created_from_repository",
    "created_from_workspace",
    "explicit_selection",
]
ResolutionState = Literal["resolved", "ambiguous", "unavailable"]


def project_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return (slug[:64] if slug else "project")


def _norm(value: str | None) -> str:
    return str(value or "").strip().lower()


def _repo_key(owner: str | None, name: str | None) -> str:
    if not owner or not name:
        return ""
    return f"github:{owner.strip().lower()}/{name.strip().lower()}"


def repository_key(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    provider = _norm(str(payload.get("provider") or "github"))
    owner = str(payload.get("owner") or payload.get("repositoryOwner") or "").strip()
    name = str(payload.get("name") or payload.get("repositoryName") or "").strip()
    if provider != "github" or not owner or not name:
        return ""
    return _repo_key(owner, name)


@dataclass(frozen=True)
class AccessibleProject:
    id: str
    organization_id: str
    organization_slug: str = ""
    organization_name: str = ""
    slug: str = ""
    display_name: str = ""
    repository: dict[str, Any] | None = None

    @property
    def repo_key(self) -> str:
        return repository_key(self.repository)


@dataclass
class ProjectResolution:
    state: ResolutionState
    resolution: ResolutionValue | None = None
    project_id: str | None = None
    display_name: str | None = None
    environment: str = "development"
    organization_id: str | None = None
    created: bool = False
    reason: str | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"state": self.state}
        if self.resolution:
            payload["resolution"] = self.resolution
        if self.project_id:
            payload["projectId"] = self.project_id
        if self.display_name:
            payload["displayName"] = self.display_name
        payload["environment"] = self.environment
        if self.organization_id:
            payload["organizationId"] = self.organization_id
        payload["created"] = self.created
        if self.reason:
            payload["reason"] = self.reason
        if self.candidates:
            payload["candidates"] = list(self.candidates)
        return payload


def _candidate(project: AccessibleProject, why: str) -> dict[str, Any]:
    return {
        "id": project.id,
        "displayName": project.display_name,
        "slug": project.slug,
        "organizationId": project.organization_id,
        "organizationName": project.organization_name,
        "match": why,
    }


def _unique(projects: list[AccessibleProject]) -> AccessibleProject | None:
    ids = {item.id for item in projects}
    if len(ids) != 1:
        return None
    return projects[0]


def _name_matches(project: AccessibleProject, name: str) -> bool:
    needle = _norm(name)
    if not needle:
        return False
    return _norm(project.display_name) == needle or _norm(project.slug) == project_slug(name)


def _name_hits(
    projects: list[AccessibleProject],
    name: str,
    *,
    local_repo: str = "",
) -> list[AccessibleProject]:
    hits: list[AccessibleProject] = []
    for item in projects:
        if not _name_matches(item, name):
            continue
        if local_repo and item.repo_key and item.repo_key != local_repo:
            continue
        hits.append(item)
    return hits


def _org_matches_owner(project: AccessibleProject, owner: str) -> bool:
    needle = _norm(owner)
    if not needle:
        return False
    return _norm(project.organization_slug) == needle or _norm(project.organization_name) == needle


def _restrict_hits_to_known_owner(
    hits: list[AccessibleProject],
    context: LocalProjectContext,
) -> list[AccessibleProject]:
    owner = context.repository_owner.value
    if not owner:
        return hits
    owner_hits = [item for item in hits if _org_matches_owner(item, str(owner))]
    return owner_hits if owner_hits else []


def choose_default_organization(
    organizations: list[dict[str, Any]],
    context: LocalProjectContext,
    *,
    preferred_organization_id: str | None = None,
) -> tuple[str | None, str | None]:
    """Return (organization_id, ambiguity_reason)."""
    if not organizations:
        return None, None
    if len(organizations) == 1:
        return str(organizations[0].get("id") or ""), None
    owner = context.repository_owner.value
    if owner:
        matches = [
            org
            for org in organizations
            if _norm(str(org.get("slug") or "")) == _norm(owner)
            or _norm(str(org.get("displayName") or "")) == _norm(owner)
        ]
        if len(matches) == 1:
            return str(matches[0].get("id") or ""), None
    preferred = str(preferred_organization_id or "").strip()
    if preferred:
        matches = [org for org in organizations if str(org.get("id") or "") == preferred]
        if len(matches) == 1:
            return preferred, None
    return None, "multiple_organizations"


def resolve_existing_project(
    context: LocalProjectContext,
    projects: list[AccessibleProject],
) -> ProjectResolution:
    environment = "development"
    local_repo = repository_key(context.repository_payload())
    if local_repo:
        repo_hits = [item for item in projects if item.repo_key == local_repo]
        unique = _unique(repo_hits)
        if unique is not None:
            return ProjectResolution(
                state="resolved",
                resolution="repository_match",
                project_id=unique.id,
                display_name=unique.display_name,
                environment=environment,
                organization_id=unique.organization_id,
            )
        if len({item.id for item in repo_hits}) > 1:
            return ProjectResolution(
                state="ambiguous",
                reason="multiple_matching_projects",
                environment=environment,
                candidates=[_candidate(item, "repository") for item in repo_hits],
            )

    repo_name = context.repository_name.value or ""
    if repo_name:
        name_hits = _restrict_hits_to_known_owner(
            _name_hits(projects, repo_name, local_repo=local_repo),
            context,
        )
        unique = _unique(name_hits)
        if unique is not None:
            return ProjectResolution(
                state="resolved",
                resolution="repository_match",
                project_id=unique.id,
                display_name=unique.display_name,
                environment=environment,
                organization_id=unique.organization_id,
            )
        if len({item.id for item in name_hits}) > 1:
            return ProjectResolution(
                state="ambiguous",
                reason="multiple_matching_projects",
                environment=environment,
                candidates=[_candidate(item, "repository_name") for item in name_hits],
            )

    workspace_name = context.inferred_name
    if workspace_name and context.display_name.confidence in {"high", "medium"}:
        name_hits = _restrict_hits_to_known_owner(
            _name_hits(projects, workspace_name, local_repo=local_repo),
            context,
        )
        unique = _unique(name_hits)
        if unique is not None:
            # Folder-only match is allowed only when it is exact and unique.
            resolution: ResolutionValue = (
                "repository_match"
                if context.has_github_repository
                else "workspace_match"
            )
            return ProjectResolution(
                state="resolved",
                resolution=resolution,
                project_id=unique.id,
                display_name=unique.display_name,
                environment=environment,
                organization_id=unique.organization_id,
            )
        if len({item.id for item in name_hits}) > 1:
            return ProjectResolution(
                state="ambiguous",
                reason="multiple_matching_projects",
                environment=environment,
                candidates=[_candidate(item, "workspace_name") for item in name_hits],
            )

    return ProjectResolution(state="unavailable", reason="no_match", environment=environment)


def resolve_creation_target(
    context: LocalProjectContext,
    organizations: list[dict[str, Any]],
    *,
    preferred_organization_id: str | None = None,
) -> ProjectResolution:
    if not context.inferred_name:
        return ProjectResolution(
            state="ambiguous",
            reason="workspace_identity_unknown",
            environment="development",
        )
    org_id, reason = choose_default_organization(
        organizations,
        context,
        preferred_organization_id=preferred_organization_id,
    )
    if not organizations:
        created_resolution: ResolutionValue = (
            "created_from_repository"
            if context.has_github_repository
            else "created_from_workspace"
        )
        return ProjectResolution(
            state="resolved",
            resolution=created_resolution,
            display_name=context.inferred_name,
            environment="development",
            created=True,
        )
    if reason == "multiple_organizations" or not org_id:
        return ProjectResolution(
            state="ambiguous",
            reason="multiple_organizations",
            environment="development",
            candidates=[
                {
                    "id": str(org.get("id") or ""),
                    "displayName": str(org.get("displayName") or org.get("slug") or ""),
                    "match": "organization",
                }
                for org in organizations
            ],
        )
    created_resolution = (
        "created_from_repository"
        if context.has_github_repository
        else "created_from_workspace"
    )
    return ProjectResolution(
        state="resolved",
        resolution=created_resolution,
        display_name=context.inferred_name,
        environment="development",
        organization_id=org_id,
        created=True,
    )


def resolve_project_from_catalog(
    context: LocalProjectContext,
    *,
    projects: list[AccessibleProject],
    organizations: list[dict[str, Any]],
    preferred_organization_id: str | None = None,
) -> ProjectResolution:
    matched = resolve_existing_project(context, projects)
    if matched.state != "unavailable":
        return matched
    return resolve_creation_target(
        context,
        organizations,
        preferred_organization_id=preferred_organization_id,
    )


def project_from_api_row(
    row: dict[str, Any],
    *,
    organization_id: str,
    organization_slug: str = "",
    organization_name: str = "",
) -> AccessibleProject | None:
    project_id = str(row.get("id") or "").strip()
    if not project_id:
        return None
    repository = row.get("repository")
    return AccessibleProject(
        id=project_id,
        organization_id=str(row.get("organizationId") or organization_id),
        organization_slug=organization_slug,
        organization_name=organization_name or str(row.get("organizationName") or ""),
        slug=str(row.get("slug") or ""),
        display_name=str(row.get("displayName") or row.get("slug") or project_id),
        repository=repository if isinstance(repository, dict) else None,
    )


def load_accessible_catalog() -> tuple[list[dict[str, Any]], list[AccessibleProject]]:
    from hydracept.cli.session_client import list_organization_projects, list_organizations

    organizations = list_organizations()
    projects: list[AccessibleProject] = []
    for org in organizations:
        org_id = str(org.get("id") or "").strip()
        if not org_id:
            continue
        slug = str(org.get("slug") or "")
        name = str(org.get("displayName") or slug)
        for row in list_organization_projects(org_id):
            parsed = project_from_api_row(
                row,
                organization_id=org_id,
                organization_slug=slug,
                organization_name=name,
            )
            if parsed is not None:
                projects.append(parsed)
    return organizations, projects


def find_explicit_project(
    selector: str,
    projects: list[AccessibleProject],
) -> ProjectResolution:
    needle = selector.strip()
    if not needle:
        return ProjectResolution(
            state="ambiguous",
            reason="explicit_project_missing",
            environment="development",
        )
    hits = [
        item
        for item in projects
        if item.id == needle
        or _norm(item.slug) == _norm(needle)
        or _norm(item.display_name) == _norm(needle)
    ]
    unique = _unique(hits)
    if unique is not None:
        return ProjectResolution(
            state="resolved",
            resolution="explicit_selection",
            project_id=unique.id,
            display_name=unique.display_name,
            environment="development",
            organization_id=unique.organization_id,
        )
    if hits:
        return ProjectResolution(
            state="ambiguous",
            reason="multiple_matching_projects",
            environment="development",
            candidates=[_candidate(item, "explicit") for item in hits],
        )
    return ProjectResolution(
        state="unavailable",
        reason="project_not_found",
        environment="development",
    )


def _created_payload_to_resolution(
    payload: dict[str, Any],
    planned: ProjectResolution,
) -> ProjectResolution:
    project_id = str(
        payload.get("id")
        or payload.get("projectId")
        or (payload.get("principal") or {}).get("projectId")
        or ""
    ).strip()
    display_name = str(
        payload.get("displayName") or planned.display_name or ""
    ).strip() or planned.display_name
    environment = str(payload.get("environment") or planned.environment or "development")
    created = bool(payload.get("created", planned.created))
    resolution = planned.resolution
    if not created and resolution in {"created_from_repository", "created_from_workspace"}:
        resolution = (
            "repository_match" if resolution == "created_from_repository" else "workspace_match"
        )
    return ProjectResolution(
        state="resolved",
        resolution=resolution,
        project_id=project_id or None,
        display_name=display_name,
        environment=environment or "development",
        organization_id=str(payload.get("organizationId") or planned.organization_id or "") or None,
        created=created,
    )


def apply_automatic_project(
    context: LocalProjectContext,
    *,
    organizations: list[dict[str, Any]] | None = None,
    projects: list[AccessibleProject] | None = None,
    environment: str = "development",
    preferred_organization_id: str | None = None,
) -> ProjectResolution:
    from hydracept.cli.session_client import (
        SessionClientError,
        bootstrap_onboarding_project,
        create_organization_project,
    )

    if organizations is None or projects is None:
        organizations, projects = load_accessible_catalog()
    env = (environment or "development").strip() or "development"
    planned = resolve_project_from_catalog(
        context,
        projects=projects,
        organizations=organizations,
        preferred_organization_id=preferred_organization_id,
    )
    planned.environment = env
    if planned.state != "resolved" or not planned.created:
        return planned
    repository = context.repository_payload()
    display_name = planned.display_name or context.inferred_name
    if planned.organization_id:
        created = create_organization_project(
            planned.organization_id,
            display_name=display_name,
            environment=env,
            repository=repository,
        )
        return _created_payload_to_resolution(created, planned)
    try:
        created = bootstrap_onboarding_project(
            display_name=display_name,
            repository=repository,
            environment=env,
        )
    except SessionClientError as exc:
        if exc.status_code != 409:
            raise
        organizations, projects = load_accessible_catalog()
        retry = resolve_project_from_catalog(
            context,
            projects=projects,
            organizations=organizations,
            preferred_organization_id=preferred_organization_id,
        )
        retry.environment = env
        if retry.state == "resolved" and retry.created and retry.organization_id:
            created = create_organization_project(
                retry.organization_id,
                display_name=display_name,
                environment=env,
                repository=repository,
            )
            return _created_payload_to_resolution(created, retry)
        return retry
    return _created_payload_to_resolution(created, planned)
