"""Hydracept panel MCP App — one ui:// resource over existing execution primitives."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.apps import Apps

APP_URI = "ui://hydracept/app.html"
APP_MIME = "text/html;profile=mcp-app"
INTERACTION_SCHEMA_VERSION = "hydracept.interaction.v1"

_UI_DIR = Path(__file__).resolve().parent / "ui"
_APP_HTML = _UI_DIR / "app.html"


def load_app_html() -> str:
    if not _APP_HTML.is_file():
        raise FileNotFoundError(
            f"Hydracept panel HTML missing at {_APP_HTML}. "
            "Run python scripts/build_hydracept_panel.py"
        )
    return _APP_HTML.read_text(encoding="utf-8")


def create_apps() -> Apps:
    apps = Apps()
    apps.add_html_resource(
        APP_URI,
        load_app_html(),
        name="hydracept-panel",
        title="Hydracept panel",
        description="Schema-driven Hydracept control surface over existing jobs, receipts, and artifacts.",
        prefers_border=True,
    )
    return apps


def panel_interaction(surface: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schemaVersion": INTERACTION_SCHEMA_VERSION,
        "surface": surface,
    }
    if extra:
        payload.update(extra)
    return payload


def is_tool_failure_payload(result: Any) -> bool:
    """True only for MCP/tool failures, not job envelopes with error objects."""
    if not isinstance(result, dict):
        return False
    if result.get("isError") is True or result.get("is_error") is True:
        return True
    return result.get("error") is True


def attach_interaction(result: Any, surface: str | None) -> Any:
    if not isinstance(result, dict) or is_tool_failure_payload(result) or not surface:
        return result
    attached = dict(result)
    attached.setdefault("interaction", panel_interaction(surface))
    return attached


def surface_for_job(job: dict[str, Any] | None) -> str | None:
    from hydracept.mcp.surface_contract import is_visual_capability, is_visual_media_type, surface_for_job_status

    payload = job or {}
    nested = payload.get("job") if isinstance(payload.get("job"), dict) else payload
    status = str(payload.get("status") or payload.get("state") or nested.get("status") or nested.get("state") or "")
    capability_key = str(payload.get("capabilityKey") or nested.get("capabilityKey") or "")
    media_type = str(payload.get("mediaType") or nested.get("mediaType") or "")
    artifacts = nested.get("artifacts") if isinstance(nested.get("artifacts"), list) else payload.get("artifacts")
    if not media_type and isinstance(artifacts, list):
        for item in artifacts:
            if isinstance(item, dict) and (item.get("mediaType") or item.get("media_type")):
                media_type = str(item.get("mediaType") or item.get("media_type"))
                break
    visual = is_visual_capability(capability_key) or is_visual_media_type(media_type)
    return surface_for_job_status(status, visual=visual)
