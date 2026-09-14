from __future__ import annotations

from hydracept.cli.run_output_preview import human_run_preview
from hydracept.cli.structured_output_guard import empty_structured_output_error
from hydracept.run_result import RunResult


def test_human_run_preview_translate_items() -> None:
    preview = human_run_preview(
        {
            "capability": "text.translate.v1",
            "typedOutput": {
                "items": [{"id": "1", "translation": "Hola"}],
            },
        }
    )
    assert preview == "1: Hola"


def test_empty_structured_output_error_translate() -> None:
    err = empty_structured_output_error(
        "text.translate.v1",
        RunResult(
            capability="text.translate.v1",
            status="succeeded",
            typed_output={"items": []},
        ),
    )
    assert err is not None
    assert err.code == "EmptyStructuredOutput"
    assert "target-locale" in err.message
