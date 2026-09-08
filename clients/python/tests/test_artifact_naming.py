"""Artifact filename and label matching."""

from __future__ import annotations

from hydracept.artifact_naming import find_artifact, suggested_filename


ANVIL = {
    "artifactId": "art_1",
    "mediaType": "image/png",
    "kind": "output",
    "label": "anvil",
    "filename": "anvil.png",
    "sliceCellId": "anvil",
}


def test_suggested_filename_prefers_explicit_name() -> None:
    assert suggested_filename(ANVIL, index=0) == "anvil.png"
    nested = dict(ANVIL, filename="icons/anvil.png")
    assert suggested_filename(nested, index=0) == "anvil.png"


def test_suggested_filename_from_label() -> None:
    item = {"label": "Iron Anvil", "mediaType": "image/png"}
    assert suggested_filename(item, index=3) == "iron-anvil.png"


def test_find_artifact_matches_label_filename_and_slice() -> None:
    artifacts = [ANVIL]
    assert find_artifact(artifacts, label="anvil") is ANVIL
    assert find_artifact(artifacts, label="anvil.png") is ANVIL
    assert find_artifact(artifacts, artifact_id="art_1") is ANVIL
    assert find_artifact(artifacts, label="missing") is None
