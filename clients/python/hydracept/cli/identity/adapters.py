"""First-party local identity detection and proof issuance.

Detection returns non-secret account hints. Proof issuance is intentionally a
separate operation so ordinary panel hydration and polling can never expose a
foreign credential to MCP or the model.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Protocol

_GITHUB_ENV_CREDENTIALS = {
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GH_ENTERPRISE_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN",
}
_GOOGLE_ENV_CREDENTIALS = {
    "CLOUDSDK_AUTH_ACCESS_TOKEN",
    "CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT",
    "GOOGLE_OAUTH_ACCESS_TOKEN",
}
_PREFERRED_PROVIDERS = ("github", "google")


@dataclass(frozen=True)
class LocalIdentityHint:
    provider: str
    account: str
    source: str

    def to_public_dict(self) -> dict[str, str]:
        return {"provider": self.provider, "account": self.account, "source": self.source}


@dataclass(frozen=True, repr=False)
class LocalIdentityProof:
    provider: str
    proof_type: str
    secret: str

    def __repr__(self) -> str:
        return (
            f"LocalIdentityProof(provider={self.provider!r}, "
            f"proof_type={self.proof_type!r}, secret=<redacted>)"
        )

    def to_wire(self) -> dict[str, str]:
        if self.proof_type == "oauth_access_token":
            return {"type": self.proof_type, "accessToken": self.secret}
        raise ValueError(f"Unsupported local identity proof type: {self.proof_type}")


class LocalIdentityAdapter(Protocol):
    provider_id: str

    def detect(self) -> LocalIdentityHint | None: ...

    def issue_proof(self, hint: LocalIdentityHint) -> LocalIdentityProof: ...


def _without_env(names: set[str]) -> dict[str, str]:
    env = dict(os.environ)
    for name in names:
        env.pop(name, None)
    return env


def _run_cli(args: list[str], *, env: dict[str, str], timeout: float = 12.0) -> str:
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        return ""
    return (completed.stdout or "").strip()


def _github_login(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        if "\n" in text or " " in text:
            return ""
        return text
    if not isinstance(payload, dict):
        return ""
    login = str(payload.get("login") or "").strip()
    if not login or "\n" in login:
        return ""
    return login


def _human_google_account(raw: str) -> str:
    accounts = [line.strip() for line in (raw or "").splitlines() if line.strip()]
    humans = [
        account
        for account in accounts
        if account not in {"(unset)", "None"}
        and not account.endswith(".gserviceaccount.com")
    ]
    if len(humans) != 1:
        return ""
    return humans[0]


class GitHubIdentityAdapter:
    provider_id = "github"

    def detect(self) -> LocalIdentityHint | None:
        executable = shutil.which("gh")
        if not executable:
            return None
        account = _github_login(
            _run_cli(
                [executable, "api", "--hostname", "github.com", "user"],
                env=_without_env(_GITHUB_ENV_CREDENTIALS),
            )
        )
        if not account:
            return None
        return LocalIdentityHint(provider=self.provider_id, account=account, source="gh")

    def issue_proof(self, hint: LocalIdentityHint) -> LocalIdentityProof:
        if hint.provider != self.provider_id:
            raise ValueError("GitHub adapter received a different provider")
        executable = shutil.which("gh")
        if not executable:
            raise RuntimeError("GitHub CLI is no longer available")
        token = _run_cli(
            [executable, "auth", "token", "--hostname", "github.com"],
            env=_without_env(_GITHUB_ENV_CREDENTIALS),
        )
        if not token:
            raise RuntimeError("GitHub CLI has no usable github.com login")
        return LocalIdentityProof(
            provider=self.provider_id,
            proof_type="oauth_access_token",
            secret=token,
        )


class GoogleIdentityAdapter:
    """Active `gcloud` user account — the local counterpart of browser Google OAuth.

    The access token is used only against Google identity endpoints, the same way
    `gh auth token` is used only against GitHub identity endpoints. Service
    accounts and impersonation are not human developer identity.
    """

    provider_id = "google"

    def detect(self) -> LocalIdentityHint | None:
        executable = shutil.which("gcloud")
        if not executable:
            return None
        env = _without_env(_GOOGLE_ENV_CREDENTIALS)
        account = _human_google_account(
            _run_cli(
                [
                    executable,
                    "auth",
                    "list",
                    "--filter=status:ACTIVE",
                    "--format=value(account)",
                ],
                env=env,
            )
        )
        if not account:
            account = _human_google_account(
                _run_cli([executable, "config", "get-value", "account"], env=env)
            )
        if not account:
            return None
        return LocalIdentityHint(provider=self.provider_id, account=account, source="gcloud")

    def issue_proof(self, hint: LocalIdentityHint) -> LocalIdentityProof:
        if hint.provider != self.provider_id:
            raise ValueError("Google adapter received a different provider")
        executable = shutil.which("gcloud")
        if not executable:
            raise RuntimeError("Google Cloud CLI is no longer available")
        token = _run_cli(
            [
                executable,
                "auth",
                "print-access-token",
                f"--account={hint.account}",
                "--quiet",
            ],
            env=_without_env(_GOOGLE_ENV_CREDENTIALS),
        )
        if not token or " " in token or "\n" in token:
            raise RuntimeError("Google Cloud CLI has no usable user login")
        return LocalIdentityProof(
            provider=self.provider_id,
            proof_type="oauth_access_token",
            secret=token,
        )


# First-party registry only. Do not auto-load plugin entry points for identity.
_ADAPTERS: tuple[LocalIdentityAdapter, ...] = (
    GitHubIdentityAdapter(),
    GoogleIdentityAdapter(),
)


def detect_local_identities() -> list[LocalIdentityHint]:
    """Return only safe account hints; detection never acquires a proof."""
    hints: list[LocalIdentityHint] = []
    for adapter in _ADAPTERS:
        try:
            hint = adapter.detect()
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            hint = None
        if hint is not None:
            hints.append(hint)
    return hints


def ordered_local_identity_hints(
    hints: list[LocalIdentityHint],
    requested_provider: str | None = None,
) -> list[LocalIdentityHint]:
    """Pick GitHub then Google when both CLIs are logged in.

    Two supported local logins are not browser-OAuth ambiguity. An explicit
    provider request still has to match exactly one detected account.
    """
    requested = str(requested_provider or "").strip().lower()
    if requested:
        matches = [hint for hint in hints if hint.provider == requested]
        return matches if len(matches) == 1 else []
    ordered: list[LocalIdentityHint] = []
    remaining = list(hints)
    for provider in _PREFERRED_PROVIDERS:
        for hint in remaining:
            if hint.provider == provider:
                ordered.append(hint)
        remaining = [hint for hint in remaining if hint.provider != provider]
    ordered.extend(remaining)
    return ordered


def issue_local_identity_proof(hint: LocalIdentityHint) -> LocalIdentityProof:
    """Acquire a proof for an already-selected hint; never log or return it via MCP."""
    for adapter in _ADAPTERS:
        if adapter.provider_id == hint.provider:
            return adapter.issue_proof(hint)
    raise ValueError(f"No first-party local identity adapter for {hint.provider}")
