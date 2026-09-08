"""Resolve the chroma key used for a job from a sealed receipt."""

from __future__ import annotations

from typing import Any

from hydracept.chroma_plate_key import DEFAULT_CHROMA_KEY, normalize_chroma_key_hex


def chroma_key_from_receipt(receipt: dict[str, Any] | None) -> str:
    if not isinstance(receipt, dict):
        return DEFAULT_CHROMA_KEY
    candidates: list[Any] = []
    media = receipt.get("media") if isinstance(receipt.get("media"), dict) else {}
    matte = receipt.get("matte") if isinstance(receipt.get("matte"), dict) else {}
    metadata = receipt.get("metadata") if isinstance(receipt.get("metadata"), dict) else {}
    media_matte = media.get("matte") if isinstance(media.get("matte"), dict) else {}
    candidates.extend(
        (
            media_matte.get("chromaKeyColor"),
            media_matte.get("keyColor"),
            matte.get("chromaKeyColor"),
            matte.get("keyColor"),
            metadata.get("chromaKeyColor"),
            metadata.get("keyColor"),
        )
    )
    for artifact in receipt.get("artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        art_meta = artifact.get("metadata") if isinstance(artifact.get("metadata"), dict) else {}
        art_matte = artifact.get("matte") if isinstance(artifact.get("matte"), dict) else {}
        candidates.extend(
            (
                art_meta.get("chromaKeyColor"),
                art_matte.get("chromaKeyColor"),
            )
        )
    for value in candidates:
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            return normalize_chroma_key_hex(value)
        except ValueError:
            continue
    return DEFAULT_CHROMA_KEY
