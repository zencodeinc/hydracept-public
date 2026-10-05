"""Init must not upload provider keys without explicit opt-in."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from hydracept.cli.init_resolver import _discover_and_maybe_adopt_providers


def test_discover_without_adopt_providers_does_not_upload(tmp_path: Path) -> None:
    discovered_secret = MagicMock(secret="sk-fake", source=".env.local")

    with (
        patch(
            "hydracept.cli.provider_discovery.discover_provider",
            return_value=discovered_secret,
        ),
        patch("hydracept.cli.init_resolver.adopt_provider_secret") as adopt,
    ):
        discovered, adopted = _discover_and_maybe_adopt_providers(
            tmp_path,
            missing=["openai"],
            adopt_providers=None,
            project_id="prj_x",
            environment="development",
            env_file=None,
            setup_grant=None,
            yes=True,
        )

    adopt.assert_not_called()
    assert len(discovered) == 1
    assert discovered[0]["uploaded"] is False
    assert adopted == []


def test_adopt_when_provider_listed(tmp_path: Path) -> None:
    discovered_secret = MagicMock(secret="sk-fake", source=".env.local")

    with (
        patch(
            "hydracept.cli.provider_discovery.discover_provider",
            return_value=discovered_secret,
        ),
        patch(
            "hydracept.cli.init_resolver.adopt_provider_secret",
            return_value={"result": "connected"},
        ) as adopt,
    ):
        _discovered, adopted = _discover_and_maybe_adopt_providers(
            tmp_path,
            missing=["openai"],
            adopt_providers=frozenset({"openai"}),
            project_id="prj_x",
            environment="development",
            env_file=None,
            setup_grant=None,
            yes=True,
        )

    adopt.assert_called_once()
    assert adopted[0]["provider"] == "openai"
    assert adopted[0]["uploaded"] is True
