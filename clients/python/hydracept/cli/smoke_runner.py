"""Launch smoke job execution — persist evidence, then validate the public contract."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hydracept import HydraceptClient
from hydracept.cli.exit_codes import NOT_READY, SMOKE_FAILED
from hydracept.cli.smoke_contract import (
    SmokeContractError,
    evaluate_image_smoke_contract,
)
from hydracept.cli.workspace import (
    CliOverrides,
    WorkspaceNotReadyError,
    require_ready_workspace,
)

DEFAULT_SMOKE_CAPABILITY = "image.generate.v1"
DEFAULT_SMOKE_PROMPT = (
    "flat 2D game icon of a slime, no plate, no ground, no shadow, "
    "centered, simple silhouette, request transparent background"
)
SHEET_MIN_CELL_PX = 816
SHEET_EDGE_ALIGNMENT = 16
SHEET_SMOKE_ROWS = 2
SHEET_SMOKE_COLUMNS = 2
SHEET_SMOKE_POLL_SECONDS = 300


def sheet_minimum_canvas(*, rows: int, columns: int) -> tuple[int, int]:
    """Derive aligned canvas from min-cell × grid. Do not scatter 1632."""
    width = columns * SHEET_MIN_CELL_PX
    height = rows * SHEET_MIN_CELL_PX
    if width % SHEET_EDGE_ALIGNMENT:
        width += SHEET_EDGE_ALIGNMENT - (width % SHEET_EDGE_ALIGNMENT)
    if height % SHEET_EDGE_ALIGNMENT:
        height += SHEET_EDGE_ALIGNMENT - (height % SHEET_EDGE_ALIGNMENT)
    return width, height


def sheet_smoke_input(*, prompt: str) -> dict[str, Any]:
    width, height = sheet_minimum_canvas(rows=SHEET_SMOKE_ROWS, columns=SHEET_SMOKE_COLUMNS)
    if width < SHEET_SMOKE_COLUMNS * SHEET_MIN_CELL_PX:
        raise ValueError("sheet canvas width below min-cell × columns")
    if height < SHEET_SMOKE_ROWS * SHEET_MIN_CELL_PX:
        raise ValueError("sheet canvas height below min-cell × rows")
    if width % SHEET_EDGE_ALIGNMENT or height % SHEET_EDGE_ALIGNMENT:
        raise ValueError("sheet canvas edges must be multiples of 16")
    return {
        "prompt": prompt,
        "quality": "low",
        "width": width,
        "height": height,
        "requestTransparentOutput": True,
        "sheet": {
            "rows": SHEET_SMOKE_ROWS,
            "columns": SHEET_SMOKE_COLUMNS,
            "slice": True,
            "normalize": {"width": SHEET_MIN_CELL_PX, "height": SHEET_MIN_CELL_PX, "center": True},
        },
    }


@dataclass
class SmokeResult:
    job_id: str
    status: str
    receipt: dict[str, Any] | None
    artifact_ids: list[str]
    sha256_ok: bool = False
    transparency_ok: bool = False
    pricing_ok: bool = False
    downloads: list[Path] = field(default_factory=list)
    receipt_id: str = ""
    demo_path: Path | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "jobId": self.job_id,
            "receiptId": self.receipt_id or None,
            "artifactIds": self.artifact_ids,
            "downloads": [str(path) for path in self.downloads],
            "demoPath": str(self.demo_path) if self.demo_path else None,
            "sha256Ok": self.sha256_ok,
            "transparencyOk": self.transparency_ok,
            "pricingOk": self.pricing_ok,
            "exitCode": 0,
        }


class SmokeError(Exception):
    def __init__(
        self,
        message: str,
        exit_code: int = SMOKE_FAILED,
        *,
        job_id: str = "",
        downloads: list[Path] | None = None,
        artifact_ids: list[str] | None = None,
        receipt_id: str = "",
        demo_path: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.job_id = job_id
        self.downloads = list(downloads or [])
        self.artifact_ids = list(artifact_ids or [])
        self.receipt_id = receipt_id
        self.demo_path = demo_path

    def to_json(self) -> dict[str, Any]:
        return {
            "status": "failed",
            "detail": str(self),
            "jobId": self.job_id or None,
            "receiptId": self.receipt_id or None,
            "artifactIds": self.artifact_ids,
            "downloads": [str(path) for path in self.downloads],
            "demoPath": str(self.demo_path) if self.demo_path else None,
            "exitCode": self.exit_code,
        }


def _artifact_ids_from_receipt(receipt: dict[str, Any] | None) -> list[str]:
    if not receipt:
        return []
    artifacts = receipt.get("artifacts") or receipt.get("artifactIds") or []
    if isinstance(artifacts, list):
        ids: list[str] = []
        for item in artifacts:
            if isinstance(item, dict) and (item.get("id") or item.get("artifactId")):
                ids.append(str(item.get("id") or item.get("artifactId")))
            elif item:
                ids.append(str(item))
        return ids
    return []


def _write_demo_asset(project_root: Path, data: bytes) -> Path:
    demo = Path(project_root) / ".hydracept" / "demo" / "first-asset.png"
    demo.parent.mkdir(parents=True, exist_ok=True)
    demo.write_bytes(data)
    return demo


def _receipt_id(receipt: dict[str, Any] | None) -> str:
    if not receipt:
        return ""
    return str(receipt.get("receiptId") or receipt.get("id") or "")


def _sheet_cell_count(receipt: dict[str, Any] | None) -> int | None:
    if not receipt:
        return None
    media = receipt.get("media") if isinstance(receipt.get("media"), dict) else {}
    sheet = media.get("sheet") if isinstance(media, dict) else None
    if not isinstance(sheet, dict):
        sheet = receipt.get("sheet") if isinstance(receipt.get("sheet"), dict) else None
    if not isinstance(sheet, dict):
        return None
    cells = sheet.get("cells") or sheet.get("slices") or sheet.get("frames")
    if isinstance(cells, list):
        return len(cells)
    rows = sheet.get("rows")
    columns = sheet.get("columns") or sheet.get("cols")
    if isinstance(rows, int) and isinstance(columns, int) and rows > 0 and columns > 0:
        return rows * columns
    return None


def run_smoke(
    project_root: Path,
    *,
    api_url: str | None = None,
    token: str | None = None,
    capability: str = DEFAULT_SMOKE_CAPABILITY,
    prompt: str = DEFAULT_SMOKE_PROMPT,
    poll_seconds: int = 90,
    download_dir: Path | None = None,
    request_transparent: bool = True,
    verify_transparency: bool = True,
    extra_input: dict[str, Any] | None = None,
    min_artifacts: int = 1,
    require_sheet_cells: int | None = None,
) -> SmokeResult:
    try:
        workspace = require_ready_workspace(
            project_root,
            overrides=CliOverrides(token=token, api_url=api_url),
        )
    except WorkspaceNotReadyError as exc:
        raise SmokeError(str(exc), exit_code=NOT_READY) from exc

    client = HydraceptClient(workspace.api_url, workspace.token)
    idem = f"cli-smoke-{int(time.time())}"
    image_input: dict[str, Any] = {"prompt": prompt}
    if request_transparent:
        image_input["requestTransparentOutput"] = True
    if extra_input:
        image_input.update(extra_input)
        image_input.setdefault("prompt", prompt)
    job = client.submit_capability_job(
        capability,
        {
            "context": {
                "productId": workspace.project_id,
                "projectId": workspace.project_id,
                "environment": workspace.environment,
            },
            "input": image_input,
            "execution": {"executionPreference": "automatic"},
            "idempotencyKey": idem,
        },
    )
    job_id = str(job.get("jobId") or job.get("id") or "")
    if not job_id:
        raise SmokeError(f"No jobId in response: {job!r}")

    deadline = time.time() + max(5, poll_seconds)
    status = "unknown"
    while time.time() < deadline:
        current = client.get_job(job_id)
        status = str(current.get("status") or "unknown")
        if status in {"succeeded", "failed", "canceled"}:
            if status != "succeeded":
                raise SmokeError(
                    f"Smoke ended with status={status}: {current}",
                    job_id=job_id,
                )
            receipt: dict[str, Any] | None = None
            try:
                receipt = client.get_job_receipt(job_id)
            except Exception:  # noqa: BLE001
                receipt = None
            receipt_id = _receipt_id(receipt)
            artifact_ids = _artifact_ids_from_receipt(receipt) or _artifact_ids_from_receipt(current)
            if not artifact_ids:
                raise SmokeError(
                    "Receipt missing artifact identity",
                    job_id=job_id,
                    receipt_id=receipt_id,
                )
            target_dir = download_dir or (project_root / ".hydracept" / "output")
            target_dir.mkdir(parents=True, exist_ok=True)
            downloads: list[Path] = []
            first_data = b""
            for artifact_id in artifact_ids:
                data = client.download_job_artifact(job_id, artifact_id)
                if not first_data:
                    first_data = data
                path = target_dir / f"{artifact_id}.png"
                path.write_bytes(data)
                downloads.append(path)
            demo_path = _write_demo_asset(project_root, first_data) if first_data else None
            try:
                checks = evaluate_image_smoke_contract(
                    receipt,
                    artifact_id=artifact_ids[0],
                    data=first_data,
                    verify_transparency=verify_transparency,
                )
                if len(artifact_ids) < min_artifacts:
                    raise SmokeContractError(
                        f"expected>={min_artifacts} artifacts, got {len(artifact_ids)}"
                    )
                if require_sheet_cells is not None:
                    cells = _sheet_cell_count(receipt)
                    if cells is not None and cells < require_sheet_cells:
                        raise SmokeContractError(
                            f"sheet metadata describes {cells} cells, expected>={require_sheet_cells}"
                        )
                    if cells is None and len(artifact_ids) < require_sheet_cells:
                        raise SmokeContractError(
                            f"expected>={require_sheet_cells} sliced artifacts, got {len(artifact_ids)}"
                        )
            except SmokeContractError as exc:
                raise SmokeError(
                    str(exc),
                    job_id=job_id,
                    downloads=downloads,
                    artifact_ids=artifact_ids,
                    receipt_id=receipt_id,
                    demo_path=demo_path,
                ) from exc
            return SmokeResult(
                job_id=job_id,
                status=status,
                receipt=receipt,
                artifact_ids=artifact_ids,
                sha256_ok=checks["sha256_ok"],
                transparency_ok=checks["transparency_ok"],
                pricing_ok=checks["pricing_ok"],
                downloads=downloads,
                receipt_id=receipt_id,
                demo_path=demo_path,
            )
        time.sleep(3)

    raise SmokeError(
        f"Timed out while status={status} — poll with jobs get {job_id}",
        job_id=job_id,
    )


def run_sheet_smoke(
    project_root: Path,
    **kwargs: Any,
) -> SmokeResult:
    prompt = str(kwargs.pop("prompt", None) or DEFAULT_SMOKE_PROMPT)
    extra = sheet_smoke_input(prompt=prompt)
    kwargs.setdefault("capability", DEFAULT_SMOKE_CAPABILITY)
    kwargs.setdefault("verify_transparency", True)
    kwargs.setdefault("poll_seconds", SHEET_SMOKE_POLL_SECONDS)
    kwargs["prompt"] = prompt
    kwargs["extra_input"] = extra
    kwargs["request_transparent"] = True
    kwargs["min_artifacts"] = SHEET_SMOKE_ROWS * SHEET_SMOKE_COLUMNS
    kwargs["require_sheet_cells"] = SHEET_SMOKE_ROWS * SHEET_SMOKE_COLUMNS
    return run_smoke(project_root, **kwargs)
