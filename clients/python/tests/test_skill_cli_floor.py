"""Skill CLI floor: public skills teach `python -m hydracept run` as the generate primitive."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_skill_mentions_run_cli_floor() -> None:
    paths = [
        ROOT / "clients" / "python" / "hydracept" / "data" / "agents" / "skills" / "hydracept" / "SKILL.md",
        ROOT / "public" / "agents" / "source" / "skills" / "hydracept" / "SKILL.md",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "python -m hydracept run" in text, path
        assert "python -m hydracept doctor --fix" in text or "hydracept run" in text
