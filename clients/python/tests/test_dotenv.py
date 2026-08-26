"""Tests for parse-only dotenv."""

from __future__ import annotations

from pathlib import Path

from hydracept.cli.dotenv import parse_dotenv_file


def test_parse_dotenv_quoted_values(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text('OPENAI_API_KEY="sk-test"\n# comment\nFOO=bar\n', encoding="utf-8")
    values = parse_dotenv_file(env)
    assert values["OPENAI_API_KEY"] == "sk-test"
    assert values["FOO"] == "bar"
    assert "comment" not in values
