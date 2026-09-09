"""Capability input overflow contract.

Hydracept never silently truncates semantic user input to satisfy a provider
limit. Callers discover the effective limit and overflow policy on the
capability descriptor; admission rejects overflow before quote, reservation,
or provider submission.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_serializer

from hydracept_contracts.errors import HydraceptErrorCode

TTS_DEFAULT_CHARACTER_LIMIT = 10_000
TTS_MODEL_CHARACTER_LIMITS: dict[str, int] = {
    "eleven_multilingual_v2": 10_000,
    "eleven_turbo_v2_5": 40_000,
    "eleven_flash_v2_5": 40_000,
}
# Downstream OpenAI Images prompt caps (gpt-image-1 / gpt-image-2).
IMAGE_DEFAULT_CHARACTER_LIMIT = 32_000
IMAGE_MODEL_CHARACTER_LIMITS: dict[str, int] = {
    "gpt-image-2": 32_000,
    "gpt-image-1": 32_000,
}
MESH_TEXTURE_PROMPT_MAX = 800
SFX_PROMPT_CHARACTER_LIMIT = 450
# Downstream ElevenLabs /v1/music prompt cap (music_v1).
MUSIC_PROMPT_CHARACTER_LIMIT = 4_100
MUSIC_PROVIDER_CHARACTER_LIMIT = MUSIC_PROMPT_CHARACTER_LIMIT


class OverflowPolicy(StrEnum):
    """What Hydracept does when a field exceeds its measured maximum."""

    REJECT = "reject"
    CHUNK = "chunk"
    PRUNE = "prune"


class ConstraintMeasurement(StrEnum):
    CHARACTERS = "characters"
    TOKENS = "tokens"


class ModelFieldConstraint(BaseModel):
    """Per-model overlay on a field constraint."""

    max: int | None = None
    overflow: OverflowPolicy | None = None

    model_config = {"populate_by_name": True}


class FieldInputConstraint(BaseModel):
    """Normative limit for one capability input field."""

    measurement: ConstraintMeasurement = ConstraintMeasurement.CHARACTERS
    max: int | None = None
    overflow: OverflowPolicy = OverflowPolicy.REJECT
    semantic: bool = True
    by_model: dict[str, ModelFieldConstraint] = Field(default_factory=dict, alias="byModel")

    model_config = {"populate_by_name": True}

    @model_serializer(mode="wrap")
    def _omit_empty(self, serializer):  # noqa: ANN001
        data = serializer(self)
        if not data.get("byModel"):
            data.pop("byModel", None)
        if data.get("max") is None:
            data.pop("max", None)
        return data

    def resolve(self, model_id: str | None) -> tuple[int | None, OverflowPolicy]:
        """Return (max, overflow) for the selected model, else the field default."""
        if model_id and model_id in self.by_model:
            overlay = self.by_model[model_id]
            maximum = overlay.max if overlay.max is not None else self.max
            overflow = overlay.overflow if overlay.overflow is not None else self.overflow
            return maximum, overflow
        return self.max, self.overflow


class PromptTooLongError(ValueError):
    """Semantic input exceeded a character (or token) contract."""

    def __init__(
        self,
        *,
        field: str,
        actual: int,
        maximum: int,
        capability_key: str | None = None,
        provider: str | None = None,
        measurement: ConstraintMeasurement = ConstraintMeasurement.CHARACTERS,
        overflow: OverflowPolicy = OverflowPolicy.REJECT,
        model_id: str | None = None,
    ) -> None:
        self.field = field
        self.actual = actual
        self.maximum = maximum
        self.capability_key = capability_key
        self.provider = provider
        self.measurement = measurement
        self.overflow = overflow
        self.model_id = model_id
        unit = "characters" if measurement == ConstraintMeasurement.CHARACTERS else "tokens"
        scope = capability_key or "this capability"
        super().__init__(
            f"Prompt is {actual} {unit}; {scope} accepts at most {maximum}."
        )

    def to_detail(self) -> dict[str, Any]:
        detail: dict[str, Any] = {
            "code": HydraceptErrorCode.PROMPT_TOO_LONG.value,
            "message": str(self),
            "field": self.field,
            "retryable": False,
            "overflow": self.overflow.value,
            "measurement": self.measurement.value,
        }
        if self.measurement == ConstraintMeasurement.CHARACTERS:
            detail["actualCharacters"] = self.actual
            detail["maxCharacters"] = self.maximum
        else:
            detail["actualTokens"] = self.actual
            detail["maxTokens"] = self.maximum
        if self.capability_key:
            detail["capabilityKey"] = self.capability_key
        if self.provider:
            detail["provider"] = self.provider
        if self.model_id:
            detail["modelId"] = self.model_id
        return detail


def constraints_from_schema(schema: dict[str, Any] | None) -> dict[str, FieldInputConstraint]:
    """Derive character/reject constraints from JSON Schema string maxLength."""
    if not schema:
        return {}
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return {}
    out: dict[str, FieldInputConstraint] = {}
    for name, spec in properties.items():
        if not isinstance(spec, dict):
            continue
        if spec.get("type") == "string" and isinstance(spec.get("maxLength"), int):
            out[str(name)] = FieldInputConstraint(
                measurement=ConstraintMeasurement.CHARACTERS,
                max=int(spec["maxLength"]),
                overflow=OverflowPolicy.REJECT,
            )
    return out


def merge_constraints(
    base: dict[str, FieldInputConstraint],
    overlay: dict[str, FieldInputConstraint] | None,
) -> dict[str, FieldInputConstraint]:
    merged = dict(base)
    if overlay:
        merged.update(overlay)
    return merged


def lookup_input_strings(input_data: dict[str, Any] | None, field: str) -> list[tuple[str, str]]:
    """Return (json-pointer-ish field, string value) for a constraint field path."""
    if not input_data:
        return []
    if field == "messages":
        found: list[tuple[str, str]] = []
        messages = input_data.get("messages")
        if not isinstance(messages, list):
            return found
        for index, message in enumerate(messages):
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                found.append((f"input.messages[{index}].content", message["content"]))
        return found
    current: Any = input_data
    for part in field.split("."):
        if not isinstance(current, dict):
            return []
        current = current.get(part)
    if isinstance(current, str):
        return [(f"input.{field}", current)]
    return []


def selected_model_id(input_data: dict[str, Any] | None) -> str | None:
    if not input_data:
        return None
    for key in ("modelId", "model"):
        value = input_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def enforce_input_constraints(
    constraints: dict[str, FieldInputConstraint] | None,
    input_data: dict[str, Any] | None,
    *,
    capability_key: str | None = None,
    provider: str | None = None,
    model_id: str | None = None,
) -> None:
    """Reject semantic overflow. Chunk/prune are recorded on the descriptor;
    until orchestration implements them, overflow still fails closed at `max`.
    """
    if not constraints:
        return
    resolved_model = model_id or selected_model_id(input_data)
    for field, constraint in constraints.items():
        maximum, overflow = constraint.resolve(resolved_model)
        if maximum is None:
            continue
        if constraint.measurement != ConstraintMeasurement.CHARACTERS:
            # Token-budget admission is not yet measured at the HTTP boundary.
            continue
        if overflow == OverflowPolicy.PRUNE and not constraint.semantic:
            continue
        for pointer, value in lookup_input_strings(input_data, field):
            actual = len(value)
            if actual > maximum:
                raise PromptTooLongError(
                    field=pointer,
                    actual=actual,
                    maximum=maximum,
                    capability_key=capability_key,
                    provider=provider,
                    measurement=constraint.measurement,
                    overflow=overflow,
                    model_id=resolved_model,
                )
