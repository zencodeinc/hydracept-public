"""Detect succeeded runs with empty structured payloads."""

from __future__ import annotations

from typing import Any

from hydracept.run_result import RunResult, TypedRunError


def empty_structured_output_error(capability: str, result: RunResult) -> TypedRunError | None:
    key = str(capability or "").strip()
    typed = result.typed_output if isinstance(result.typed_output, dict) else None
    if typed is None:
        output = result.output
        typed = output if isinstance(output, dict) else None
    if not isinstance(typed, dict):
        return None
    if key == "text.translate.v1":
        items = typed.get("items")
        if isinstance(items, list) and not items:
            return TypedRunError(
                code="EmptyStructuredOutput",
                message=(
                    "text.translate.v1 returned no translation items. "
                    "Use --target-locale es --prompt \"...\" or --input-file request.json."
                ),
                details={"typedOutput": typed},
                recovery={
                    "nextAction": (
                        'python -m hydracept run text.translate.v1 --target-locale es --prompt "..." --json'
                    )
                },
            )
    return None
