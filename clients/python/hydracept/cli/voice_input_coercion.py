"""Client-side voice job input normalization (no server SDK dependency)."""

from __future__ import annotations

import re
from typing import Any

from hydracept.cli.run_input_coercion import InputValidationError

# Must match server managed default in hydracept_provider_sdk.elevenlabs.default_voice.
_MANAGED_DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
_VOICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{10,40}$")


def coerce_voice_generate_input(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload or {})
    normalized.pop("voiceIdSource", None)
    raw_voice = str(normalized.get("voiceId") or "").strip()
    if raw_voice:
        if not _VOICE_ID_PATTERN.fullmatch(raw_voice):
            raise InputValidationError(
                "InvalidVoiceId",
                "voiceId must be 10–40 alphanumeric characters.",
                field="voiceId",
                expected="10–40 alphanumeric characters",
            )
        normalized["voiceId"] = raw_voice
    else:
        normalized["voiceId"] = _MANAGED_DEFAULT_VOICE_ID
    return normalized
