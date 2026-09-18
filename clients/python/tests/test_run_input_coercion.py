from __future__ import annotations

import pytest

from hydracept.cli.run_input_coercion import (
    InputValidationError,
    coerce_capability_input,
    parse_set_values,
)


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


def test_input_envelope_is_treated_as_capability_input() -> None:
    payload = coerce_capability_input("domain.search.v1", {"input": {"domain": "example.com"}})
    assert payload == {"domain": "example.com"}


def test_translate_envelope_builds_items() -> None:
    payload = coerce_capability_input(
        "text.translate.v1", {"input": {"prompt": "Hello", "targetLocale": "es"}}
    )
    assert payload == {"targetLocale": "es", "items": [{"id": "1", "text": "Hello"}]}


def test_input_envelope_unknown_field_names_the_allowed_set() -> None:
    with pytest.raises(InputValidationError) as caught:
        coerce_capability_input("domain.search.v1", {"input": {"query": "example.com"}})
    assert caught.value.code == "UNKNOWN_INPUT_FIELD"
    assert "'query'" in caught.value.message
    assert "domain" in caught.value.message
    assert caught.value.recovery["allowedFields"] == ["domain"]


def test_unknown_top_level_field_is_not_silently_ignored() -> None:
    with pytest.raises(InputValidationError) as caught:
        coerce_capability_input("domain.search.v1", {"query": "example.com"})
    assert caught.value.code == "UNKNOWN_INPUT_FIELD"
    assert caught.value.field == "query"


def test_full_job_envelope_is_preserved() -> None:
    body = {"input": {"domain": "example.com"}, "context": {"projectId": "p"}}
    assert coerce_capability_input("domain.search.v1", body) == body


def test_non_object_input_envelope_is_rejected() -> None:
    with pytest.raises(InputValidationError) as caught:
        coerce_capability_input("text.translate.v1", {"input": "Hello"})
    assert caught.value.code == "INPUT_ENVELOPE_INVALID"


def test_quote_accepts_the_same_ergonomic_flags_as_run(monkeypatch, tmp_path) -> None:
    """`quote` must not reject the coercion flags `run` accepts."""
    from click.testing import CliRunner

    from hydracept.cli import entrypoint
    from hydracept.cli import main as cli_main

    captured: dict = {}

    class _FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def quote_capability(self, key: str, payload: dict) -> dict:
            captured["key"] = key
            captured["payload"] = payload
            return {"pricing": {"quote": {}}}

    class _FakeWorkspace:
        api_url = "https://api.example"
        token = "tok"

    monkeypatch.setattr(
        cli_main, "_execution_workspace", lambda *a, **k: _FakeWorkspace(), raising=False
    )
    monkeypatch.setattr(cli_main, "HydraceptClient", _FakeClient)
    monkeypatch.setattr(cli_main, "merge_workspace_job_context", lambda payload, *a, **k: payload)

    result = CliRunner().invoke(
        entrypoint.app,
        [
            "capabilities",
            "quote",
            "text.translate.v1",
            "--prompt",
            "Hello",
            "--target-locale",
            "es",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["key"] == "text.translate.v1"
    assert captured["payload"]["targetLocale"] == "es"
    assert captured["payload"]["items"] == [{"id": "1", "text": "Hello"}]


def test_quote_rejects_a_translate_prompt_without_locale_with_a_concrete_recovery(
    monkeypatch,
) -> None:
    from click.testing import CliRunner

    from hydracept.cli import entrypoint
    from hydracept.cli import main as cli_main

    class _FakeWorkspace:
        api_url = "https://api.example"
        token = "tok"

    monkeypatch.setattr(
        cli_main, "_execution_workspace", lambda *a, **k: _FakeWorkspace(), raising=False
    )

    result = CliRunner().invoke(
        entrypoint.app,
        ["capabilities", "quote", "text.translate.v1", "--prompt", "Hello", "--json"],
    )

    assert result.exit_code != 0
    assert "targetLocale" in result.output
    assert "--target-locale" in result.output


def test_domain_search_prompt_maps_to_domain() -> None:
    payload = coerce_capability_input(
        "domain.search.v1",
        {"prompt": "hydracept.com"},
    )
    assert payload == {"domain": "hydracept.com"}


def test_domain_search_structured_domain_wins_over_prompt() -> None:
    payload = coerce_capability_input(
        "domain.search.v1",
        {"prompt": "ignored.example", "domain": "hydracept.com"},
    )
    assert payload == {"domain": "hydracept.com"}


def test_domain_search_rejects_empty_prompt() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        coerce_capability_input("domain.search.v1", {"prompt": "  "})


def test_parse_set_values_coerces_json_scalars() -> None:
    assert parse_set_values(["width=816", "height=816", "flag=true", "prompt=hello"]) == {
        "width": 816,
        "height": 816,
        "flag": True,
        "prompt": "hello",
    }


def test_parse_set_values_requires_key_value() -> None:
    with pytest.raises(InputValidationError) as caught:
        parse_set_values(["width"])
    assert caught.value.code == "INVALID_SET"
    assert caught.value.field == "--set"


def test_run_accepts_generic_set_values(monkeypatch) -> None:
    """`--set` is the generic escape hatch for simple schema properties like dimensions."""
    from click.testing import CliRunner

    from hydracept.cli import entrypoint
    from hydracept.cli.run_facade import RunOutcome, RunResult

    captured: dict = {}

    def fake_execute_run(root, capability, body, **kwargs):
        captured["capability"] = capability
        captured["body"] = body
        return RunOutcome(
            result=RunResult(capability=capability, job_id="job_1", status="succeeded")
        )

    monkeypatch.setattr("hydracept.cli.run_facade.execute_run", fake_execute_run)

    result = CliRunner().invoke(
        entrypoint.app,
        [
            "run",
            "image.generate.v1",
            "--prompt",
            "icon",
            "--set",
            "width=816",
            "--set",
            "height=816",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["capability"] == "image.generate.v1"
    assert captured["body"]["prompt"] == "icon"
    assert captured["body"]["width"] == 816
    assert captured["body"]["height"] == 816
