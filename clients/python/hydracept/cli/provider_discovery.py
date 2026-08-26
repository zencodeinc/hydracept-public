"""Allowlisted local provider credential discovery for bootstrap."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from hydracept.cli.dotenv import parse_dotenv_file

ProviderSourceKind = Literal["environment", "env_file"]

PROVIDER_ENV_ALLOWLIST: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY", "HYDRACEPT_OPENAI_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY", "HYDRACEPT_ANTHROPIC_API_KEY"),
    "elevenlabs": ("ELEVENLABS_API_KEY", "HYDRACEPT_ELEVENLABS_API_KEY"),
    "meshy": ("MESHY_API_KEY", "HYDRACEPT_MESHY_API_KEY"),
}

DEFAULT_ENV_FILES = (".env.local", ".env")


@dataclass(frozen=True)
class DiscoveredProviderCredential:
    provider: str
    env_var: str
    source: ProviderSourceKind
    source_path: str
    secret: str


def _lookup_in_mapping(provider: str, mapping: dict[str, str]) -> DiscoveredProviderCredential | None:
    for env_var in PROVIDER_ENV_ALLOWLIST.get(provider, ()):
        value = (mapping.get(env_var) or "").strip()
        if value:
            return DiscoveredProviderCredential(
                provider=provider,
                env_var=env_var,
                source="environment",
                source_path="",
                secret=value,
            )
    return None


def discover_provider(
    provider: str,
    project_root: Path,
    *,
    extra_env_file: Path | None = None,
) -> DiscoveredProviderCredential | None:
    provider = provider.strip().lower()
    if provider not in PROVIDER_ENV_ALLOWLIST:
        return None

    found = _lookup_in_mapping(provider, dict(os.environ))
    if found is not None:
        return found

    files = list(DEFAULT_ENV_FILES)
    if extra_env_file is not None:
        files.append(extra_env_file.name)

    for name in files:
        path = project_root / name if not Path(name).is_absolute() else Path(name)
        mapping = parse_dotenv_file(path)
        for env_var in PROVIDER_ENV_ALLOWLIST.get(provider, ()):
            value = (mapping.get(env_var) or "").strip()
            if value:
                return DiscoveredProviderCredential(
                    provider=provider,
                    env_var=env_var,
                    source="env_file",
                    source_path=str(path),
                    secret=value,
                )
    return None


def discover_provider_labels(project_root: Path) -> list[str]:
    labels: list[str] = []
    for provider in PROVIDER_ENV_ALLOWLIST:
        if discover_provider(provider, project_root) is not None:
            labels.append(provider)
    return labels
