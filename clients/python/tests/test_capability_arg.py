from __future__ import annotations

import pytest

from hydracept.mcp.capability_arg import resolve_capability_key


def test_resolve_capability_key_prefers_first_provided_alias() -> None:
    assert resolve_capability_key(capability="image.generate.v1") == "image.generate.v1"
    assert resolve_capability_key(capabilityKey="text.general.fast.v1") == "text.general.fast.v1"


def test_resolve_capability_key_rejects_conflicts() -> None:
    with pytest.raises(ValueError, match="Conflicting"):
        resolve_capability_key(capability="a", capability_key="b")


def test_resolve_capability_key_requires_value() -> None:
    with pytest.raises(ValueError, match="Missing capability key"):
        resolve_capability_key()
