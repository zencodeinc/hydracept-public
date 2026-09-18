"""Public HTTP errors that keep the Hydracept JSON body visible to agents."""

from __future__ import annotations

from typing import Any

import httpx


def _detail_payload(payload: Any) -> Any:
    if isinstance(payload, dict) and "detail" in payload:
        return payload["detail"]
    return payload


def parse_error_fields(payload: Any) -> tuple[str, str]:
    detail = _detail_payload(payload)
    if isinstance(detail, dict):
        code = str(detail.get("code") or "").strip()
        message = str(detail.get("message") or "").strip()
        return code, message
    if isinstance(detail, str) and detail.strip():
        return "", detail.strip()
    return "", ""


def recovery_fields_from_payload(payload: Any) -> dict[str, Any]:
    blob = payload
    if isinstance(payload, dict) and isinstance(payload.get("detail"), dict):
        blob = payload["detail"]
    if not isinstance(blob, dict):
        return {}
    recovered: dict[str, Any] = {}
    if "retryable" in blob:
        recovered["retryable"] = bool(blob.get("retryable"))
    next_action = blob.get("nextAction") or blob.get("next_action")
    if next_action:
        recovered["nextAction"] = str(next_action)
    retry_after = blob.get("retryAfterSeconds", blob.get("retry_after_seconds"))
    if retry_after is not None:
        try:
            recovered["retryAfterSeconds"] = int(retry_after)
        except (TypeError, ValueError):
            pass
    return recovered


class HydraceptApiError(httpx.HTTPStatusError):
    """HTTP error that includes Hydracept `code` / `detail` in the message."""

    def __init__(
        self,
        message: str,
        *,
        request: httpx.Request,
        response: httpx.Response,
        payload: Any = None,
        code: str = "",
    ) -> None:
        super().__init__(message, request=request, response=response)
        self.payload = payload
        self.code = code

    def as_tool_result(self) -> dict[str, Any]:
        payload = {
            "error": True,
            "httpStatus": self.response.status_code,
            "code": self.code or "HTTP_ERROR",
            "message": str(self),
            "body": self.payload,
        }
        payload.update(recovery_fields_from_payload(self.payload))
        if "retryable" not in payload and self.response.status_code in {429, 500, 502, 503, 504}:
            payload["retryable"] = True
            payload.setdefault("nextAction", "retry_after_backoff")
            payload.setdefault("retryAfterSeconds", 2)
        # One failure taxonomy across the job payload, the SDK, and the CLI. Only known
        # codes are enriched; an unknown code keeps its raw payload.
        from hydracept.job_error import attach_error_projection

        return attach_error_projection(payload)


class RunAdmissionError(Exception):
    """Pre-admission `run` failure — no execution occurred."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.code = str(payload.get("code") or "RunAdmissionError")
        super().__init__(str(payload.get("message") or self.code))

    def as_tool_result(self) -> dict[str, Any]:
        return dict(self.payload)


def raise_api_status(response: httpx.Response) -> None:
    if response.is_success:
        return
    payload: Any
    try:
        payload = response.json() if response.content else {}
    except Exception:  # noqa: BLE001
        payload = {"raw": (response.text or "")[:4000]}
    code, message = parse_error_fields(payload)
    if not message:
        message = response.reason_phrase or "request failed"
    label = code or "HTTP_ERROR"
    raise HydraceptApiError(
        f"{response.status_code} {label}: {message}",
        request=response.request,
        response=response,
        payload=payload,
        code=code,
    )
