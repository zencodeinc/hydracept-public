"""CLI JSON body: file path, inline object, --input."""

from __future__ import annotations

from pathlib import Path

import pytest

from hydracept.cli.run_facade import parse_json_body


def test_parse_json_body_file(tmp_path: Path) -> None:
    path = tmp_path / "body.json"
    path.write_text('{"prompt": "hi"}', encoding="utf-8")
    assert parse_json_body(str(path)) == {"prompt": "hi"}


def test_parse_json_body_inline() -> None:
    assert parse_json_body('{"prompt": "inline"}') == {"prompt": "inline"}


def test_parse_json_body_input_option() -> None:
    assert parse_json_body(None, input_json='{"n": 1}') == {"n": 1}


def test_parse_json_body_requires_json() -> None:
    with pytest.raises(ValueError):
        parse_json_body("not-json-and-not-a-file")


def test_smoke_sheet_accepts_json_option() -> None:
    import inspect

    from hydracept.cli.main import smoke_sheet_cmd

    assert "json_output" in inspect.signature(smoke_sheet_cmd).parameters
