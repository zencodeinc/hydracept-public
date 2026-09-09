"""Workspace verification targets must never masquerade as access authority."""

from __future__ import annotations

import json

from hydracept.cli.project import (
    DEFAULT_VERIFICATION_CAPABILITIES,
    capability_profile,
    load_project_binding,
    verification_capabilities,
    write_project_binding,
)


def test_legacy_capability_profile_is_read_for_compatibility() -> None:
    binding = {"capabilityProfile": ["text.summarize.v1"]}
    assert verification_capabilities(binding) == ["text.summarize.v1"]
    assert capability_profile(binding) == ["text.summarize.v1"]


def test_new_verification_field_wins_over_legacy_name() -> None:
    binding = {
        "verificationCapabilities": ["text.translate.v1"],
        "capabilityProfile": ["image.generate.v1"],
    }
    assert verification_capabilities(binding) == ["text.translate.v1"]


def test_project_binding_writes_unambiguous_verification_field(tmp_path) -> None:
    write_project_binding(
        tmp_path,
        {
            "projectId": "cpr_test",
            "environment": "development",
            "capabilityProfile": ["image.generate.v1"],
        },
    )
    payload = json.loads((tmp_path / ".hydracept" / "project.json").read_text(encoding="utf-8"))
    assert payload["verificationCapabilities"] == ["image.generate.v1"]
    assert "capabilityProfile" not in payload
    assert load_project_binding(tmp_path)["verificationCapabilities"] == ["image.generate.v1"]


def test_default_is_explicitly_a_verification_default() -> None:
    assert verification_capabilities({}) == DEFAULT_VERIFICATION_CAPABILITIES
