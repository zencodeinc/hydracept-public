from __future__ import annotations

import pytest

from hydracept.cli.run_input_coercion import coerce_capability_input


def test_translate_prompt_with_target_locale_builds_items() -> None:
    payload = coerce_capability_input(
        "text.translate.v1",
        {"prompt": "Hello", "targetLocale": "es"},
    )
    assert payload == {
        "targetLocale": "es",
        "items": [{"id": "1", "text": "Hello"}],
    }


def test_translate_prompt_parses_locale_prefix() -> None:
    payload = coerce_capability_input(
        "text.translate.v1",
        {"prompt": "fr:Bonjour le monde"},
    )
    assert payload["targetLocale"] == "fr"
    assert payload["items"] == [{"id": "1", "text": "Bonjour le monde"}]


def test_translate_prompt_without_locale_raises() -> None:
    with pytest.raises(ValueError, match="targetLocale"):
        coerce_capability_input("text.translate.v1", {"prompt": "Hello"})


def test_translate_keeps_existing_items() -> None:
    payload = coerce_capability_input(
        "text.translate.v1",
        {
            "prompt": "ignored",
            "targetLocale": "es",
            "items": [{"id": "a", "text": "Keep me"}],
        },
    )
    assert payload["items"] == [{"id": "a", "text": "Keep me"}]
    assert payload["prompt"] == "ignored"


def test_image_prompt_unchanged() -> None:
    payload = coerce_capability_input("image.generate.v1", {"prompt": "icon"})
    assert payload == {"prompt": "icon"}
