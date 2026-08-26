"""Tests for session HTTP client error handling."""

from __future__ import annotations

import httpx

from hydracept.cli.session_client import _response_error_message


def test_response_error_message_extracts_detail() -> None:
    response = httpx.Response(
        404,
        json={"detail": "Project not found: cpr_bad"},
        request=httpx.Request("POST", "https://app.hydracept.com/v1/api-keys"),
    )
    assert _response_error_message(response) == "Project not found: cpr_bad"


def test_response_error_message_falls_back_to_text() -> None:
    response = httpx.Response(
        502,
        text="upstream error",
        request=httpx.Request("GET", "https://app.hydracept.com/healthz"),
    )
    assert _response_error_message(response) == "upstream error"
