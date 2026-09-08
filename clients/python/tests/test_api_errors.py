from hydracept.errors import HydraceptApiError, parse_error_fields, raise_api_status
from hydracept.job_wait import decorate_job_tool_result
import httpx


def test_parse_error_fields_from_detail_object() -> None:
    code, message = parse_error_fields(
        {"detail": {"code": "QUOTE_MISMATCH", "message": "omit quoteId"}}
    )
    assert code == "QUOTE_MISMATCH"
    assert "omit" in message


def test_raise_api_status_includes_code() -> None:
    request = httpx.Request("POST", "https://api.hydracept.com/v1/jobs")
    response = httpx.Response(
        409,
        request=request,
        json={"detail": {"code": "QUOTE_MISMATCH", "message": "omit quoteId"}},
    )
    try:
        raise_api_status(response)
    except HydraceptApiError as exc:
        assert exc.code == "QUOTE_MISMATCH"
        assert "QUOTE_MISMATCH" in str(exc)
        tool = exc.as_tool_result()
        assert tool["error"] is True
        assert tool["httpStatus"] == 409
    else:
        raise AssertionError("expected HydraceptApiError")


def test_decorate_job_tool_result_poll() -> None:
    payload = decorate_job_tool_result({"jobId": "job_1", "status": "queued"})
    assert payload["nextAction"] == "poll"
    assert payload["statusView"]["pollAfterSeconds"] == 4


def test_decorate_job_tool_result_surfaces_route_recovery() -> None:
    payload = decorate_job_tool_result(
        {
            "jobId": "fex_1",
            "status": "failed",
            "error": {
                "code": "ROUTE_UNAVAILABLE",
                "message": "Sealed route openai-text:gpt-5.6-luna:text.translate.v1 is not routable",
                "recovery": {
                    "nextAction": "do_not_retry_same_route",
                    "retrySameRoute": False,
                },
            },
        }
    )
    assert payload["nextAction"] == "stop"
    assert payload["recovery"]["retrySameRoute"] is False
