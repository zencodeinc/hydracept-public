from __future__ import annotations

import subprocess

from hydracept.cli.identity.adapters import (
    GitHubIdentityAdapter,
    GoogleIdentityAdapter,
    LocalIdentityHint,
    detect_local_identities,
    ordered_local_identity_hints,
)


def test_github_detection_ignores_environment_tokens(monkeypatch) -> None:
    seen_envs: list[dict[str, str]] = []
    monkeypatch.setenv("GH_TOKEN", "ambient-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "actions-secret")
    monkeypatch.setattr("hydracept.cli.identity.adapters.shutil.which", lambda name: "gh")

    def fake_run(args, **kwargs):
        seen_envs.append(kwargs["env"])
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout='{"login":"octocat"}\n',
            stderr="",
        )

    monkeypatch.setattr("hydracept.cli.identity.adapters.subprocess.run", fake_run)
    hint = GitHubIdentityAdapter().detect()

    assert hint is not None
    assert hint.provider == "github"
    assert hint.account == "octocat"
    assert "GH_TOKEN" not in seen_envs[0]
    assert "GITHUB_TOKEN" not in seen_envs[0]


def test_github_detection_accepts_plain_login_output(monkeypatch) -> None:
    monkeypatch.setattr("hydracept.cli.identity.adapters.shutil.which", lambda name: "gh")
    monkeypatch.setattr(
        "hydracept.cli.identity.adapters.subprocess.run",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args=args, returncode=0, stdout="octocat\n", stderr=""
        ),
    )

    hint = GitHubIdentityAdapter().detect()

    assert hint is not None
    assert hint.account == "octocat"


def test_github_proof_is_not_represented(monkeypatch) -> None:
    monkeypatch.setattr("hydracept.cli.identity.adapters.shutil.which", lambda name: "gh")

    def fake_run(args, **kwargs):
        output = '{"login":"octocat"}' if "api" in args else "gho_super_secret"
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=output, stderr="")

    monkeypatch.setattr("hydracept.cli.identity.adapters.subprocess.run", fake_run)
    adapter = GitHubIdentityAdapter()
    hint = adapter.detect()
    assert hint is not None
    proof = adapter.issue_proof(hint)

    assert "gho_super_secret" not in repr(proof)
    assert proof.to_wire() == {"type": "oauth_access_token", "accessToken": "gho_super_secret"}


def test_google_detection_ignores_environment_tokens_and_service_accounts(monkeypatch) -> None:
    seen_envs: list[dict[str, str]] = []
    monkeypatch.setenv("CLOUDSDK_AUTH_ACCESS_TOKEN", "ambient-secret")
    monkeypatch.setenv("CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT", "sa@example.iam.gserviceaccount.com")
    monkeypatch.setattr("hydracept.cli.identity.adapters.shutil.which", lambda name: "gcloud")

    def fake_run(args, **kwargs):
        seen_envs.append(kwargs["env"])
        stdout = (
            "sa@example.iam.gserviceaccount.com\n"
            if "list" in args
            else "dev@example.com\n"
        )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("hydracept.cli.identity.adapters.subprocess.run", fake_run)
    hint = GoogleIdentityAdapter().detect()

    assert hint is not None
    assert hint.provider == "google"
    assert hint.account == "dev@example.com"
    assert hint.source == "gcloud"
    assert "CLOUDSDK_AUTH_ACCESS_TOKEN" not in seen_envs[0]
    assert "CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT" not in seen_envs[0]


def test_google_detection_skips_only_service_account(monkeypatch) -> None:
    monkeypatch.setattr("hydracept.cli.identity.adapters.shutil.which", lambda name: "gcloud")
    monkeypatch.setattr(
        "hydracept.cli.identity.adapters.subprocess.run",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="bot@project.iam.gserviceaccount.com\n",
            stderr="",
        ),
    )

    assert GoogleIdentityAdapter().detect() is None


def test_google_proof_is_not_represented(monkeypatch) -> None:
    monkeypatch.setattr("hydracept.cli.identity.adapters.shutil.which", lambda name: "gcloud")

    def fake_run(args, **kwargs):
        output = "dev@example.com\n" if "list" in args else "ya29.super_secret"
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=output, stderr="")

    monkeypatch.setattr("hydracept.cli.identity.adapters.subprocess.run", fake_run)
    adapter = GoogleIdentityAdapter()
    hint = adapter.detect()
    assert hint is not None
    proof = adapter.issue_proof(hint)

    assert "ya29.super_secret" not in repr(proof)
    assert proof.to_wire() == {"type": "oauth_access_token", "accessToken": "ya29.super_secret"}


def test_registry_probes_github_then_gcloud(monkeypatch) -> None:
    executables: list[str] = []

    def fake_which(name: str):
        executables.append(name)
        return name

    def fake_run(args, **kwargs):
        stdout = '{"login":"octocat"}' if args and args[0] == "gh" else "dev@example.com\n"
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr("hydracept.cli.identity.adapters.shutil.which", fake_which)
    monkeypatch.setattr("hydracept.cli.identity.adapters.subprocess.run", fake_run)

    hints = detect_local_identities()

    assert [hint.provider for hint in hints] == ["github", "google"]
    assert [hint.account for hint in hints] == ["octocat", "dev@example.com"]
    assert executables == ["gh", "gcloud"]


def test_ordered_hints_prefer_github_then_google() -> None:
    google = LocalIdentityHint(provider="google", account="dev@example.com", source="gcloud")
    github = LocalIdentityHint(provider="github", account="octocat", source="gh")

    assert ordered_local_identity_hints([google, github]) == [github, google]
    assert ordered_local_identity_hints([google, github], requested_provider="google") == [google]
    assert ordered_local_identity_hints([google, github], requested_provider="unknown") == []
