"""Launch smoke job execution — persist evidence, then validate the public contract."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hydracept import HydraceptClient
from hydracept.cli.exit_codes import NOT_READY, SMOKE_FAILED
from hydracept.cli.receipt_validation import (
    CUSTOMER_CHARGE_PATH,
    ReceiptValidationError,
    terminal_customer_charge,
    validate_terminal_receipt_pricing,
)
from hydracept.cli.smoke_contract import SmokeContractError, evaluate_image_smoke_contract
from hydracept.cli.workspace import CliOverrides, WorkspaceNotReadyError, require_ready_workspace

DEFAULT_SMOKE_CAPABILITY = "image.generate.v1"
DEFAULT_SMOKE_PROMPT = (
    "flat 2D game icon of a slime, no plate, no ground, no shadow, "
    "centered, simple silhouette, request transparent background"
)
DEFAULT_SMOKE_POLL_SECONDS = 300
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


def _artifact_path(demo_path: Path | None, downloads: list[Path]) -> str | None:
    if demo_path is not None:
        return str(demo_path)
    return str(downloads[0]) if downloads else None


def _pricing_payload(receipt: dict[str, Any] | None) -> dict[str, Any]:
    charge = terminal_customer_charge(receipt)
    payload: dict[str, Any] = {"customerCharge": charge}
    display = format_customer_charge_display(charge, receipt)
    if display:
        payload["display"] = display
    return payload


def format_customer_charge_display(
    charge: dict[str, Any] | None,
    receipt: dict[str, Any] | None = None,
) -> dict[str, str] | None:
    """Display only funding facts explicitly evidenced by the receipt."""
    pricing = receipt.get("pricing") if isinstance(receipt, dict) else None
    funding = ""
    mode = ""
    if isinstance(pricing, dict):
        policy = pricing.get("policy") if isinstance(pricing.get("policy"), dict) else {}
        mode = str(pricing.get("mode") or policy.get("pricingMode") or "").lower()
        funding = str(
            pricing.get("fundingSource")
            or pricing.get("paidFrom")
            or policy.get("fundingSource")
            or ""
        ).lower()

    micros = charge.get("amountMicros") if isinstance(charge, dict) else None
    cost = f"${int(micros) / 1_000_000:.2f}" if micros is not None else "$0.00"
    paid_from = "unknown"
    if mode == "byok" or funding == "byok":
        paid_from = "BYOK"
    elif funding in {"wallet", "payg", "wallet_paid"}:
        paid_from = "wallet"
    elif funding in {"trial", "managed_trial", "trial_credit", "managed trial"}:
        paid_from = "managed trial"
    elif funding == "internal":
        paid_from = "internal"
    elif mode == "managed":
        paid_from = "managed"
    elif mode == "platform" or funding == "platform":
        paid_from = "platform"
    return {"cost": cost, "paidFrom": paid_from}


@dataclass
class SmokeResult:
    job_id: str
    status: str
    receipt: dict[str, Any] | None
    artifact_ids: list[str]
    sha256_ok: bool = False
    transparency_ok: bool = False
    transparency_report: dict[str, Any] | None = None
    pricing_ok: bool = False
    downloads: list[Path] = field(default_factory=list)
    receipt_id: str = ""
    demo_path: Path | None = None

    def to_json(self) -> dict[str, Any]:
        from hydracept.mcp.presentation import smoke_presentation

        artifact_path = _artifact_path(self.demo_path, self.downloads)
        artifact_id = self.artifact_ids[0] if self.artifact_ids else None
        media_type = "image/png"
        presentation = smoke_presentation(
            job_id=self.job_id,
            artifact_id=artifact_id,
            media_type=media_type,
        )
        payload = {
            "status": "ok",
            "execution": {
                "status": "succeeded",
                "jobId": self.job_id,
                "receiptId": self.receipt_id or None,
                "artifactPath": artifact_path,
            },
            "validation": {
                "status": "passed",
                "sha256Ok": self.sha256_ok,
                "transparencyOk": self.transparency_ok,
                "transparencyReport": self.transparency_report,
                "pricingOk": self.pricing_ok,
            },
            "pricing": _pricing_payload(self.receipt),
            "artifact": {
                "id": artifact_id,
                "mediaType": media_type,
                "path": artifact_path,
            }
            if artifact_id or artifact_path
            else None,
            "presentation": presentation,
            "jobId": self.job_id,
            "receiptId": self.receipt_id or None,
            "artifactIds": self.artifact_ids,
            "downloads": [str(path) for path in self.downloads],
            "demoPath": str(self.demo_path) if self.demo_path else None,
            "sha256Ok": self.sha256_ok,
            "transparencyOk": self.transparency_ok,
            "transparencyReport": self.transparency_report,
            "pricingOk": self.pricing_ok,
            "exitCode": 0,
        }
        return payload


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
        status: str = "failed",
        validation_error: str = "",
        validation_code: str = "",
        failing_path: str = "",
        suggested_action: str = "",
        execution_status: str = "failed",
        receipt: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.job_id = job_id
        self.downloads = list(downloads or [])
        self.artifact_ids = list(artifact_ids or [])
        self.receipt_id = receipt_id
        self.demo_path = demo_path
        self.status = status
        self.validation_error = validation_error
        self.validation_code = validation_code
        self.failing_path = failing_path
        self.suggested_action = suggested_action
        self.execution_status = execution_status
        self.receipt = receipt

    def to_json(self) -> dict[str, Any]:
        validation_status = "failed" if self.validation_error else "not_run"
        payload: dict[str, Any] = {
            "status": self.status,
            "execution": {
                "status": self.execution_status,
                "jobId": self.job_id or None,
                "receiptId": self.receipt_id or None,
                "artifactPath": _artifact_path(self.demo_path, self.downloads),
            },
            "validation": {
                "status": validation_status,
                "code": self.validation_code or None,
                "message": self.validation_error or None,
                "failingPath": self.failing_path or None,
            },
            "pricing": _pricing_payload(self.receipt),
            "detail": str(self),
            "jobId": self.job_id or None,
            "receiptId": self.receipt_id or None,
            "artifactIds": self.artifact_ids,
            "downloads": [str(path) for path in self.downloads],
            "demoPath": str(self.demo_path) if self.demo_path else None,
            "exitCode": self.exit_code,
        }
        if self.validation_error:
            payload["validationError"] = self.validation_error
        if self.failing_path:
            payload["failingPath"] = self.failing_path
        if self.suggested_action:
            payload["recommendedAction"] = {
                "kind": "inspect",
                "command": self.suggested_action,
            }
            payload["suggestedAction"] = self.suggested_action
        return payload


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


def _write_demo_asset(project_root: Path, data: bytes, *, name: str = "first-asset.png") -> Path:
    demo = Path(project_root) / ".hydracept" / "demo" / name
    demo.parent.mkdir(parents=True, exist_ok=True)
    demo.write_bytes(data)
    return demo


def _write_sheet_demos(project_root: Path, downloads: list[Path]) -> Path | None:
    demo_root = Path(project_root) / ".hydracept" / "demo"
    slices = demo_root / "sheet-slices"
    slices.mkdir(parents=True, exist_ok=True)
    first: Path | None = None
    for index, src in enumerate(downloads):
        dest = slices / src.name
        dest.write_bytes(src.read_bytes())
        if first is None:
            first = dest
            (demo_root / "first-sheet.png").write_bytes(src.read_bytes())
            first = demo_root / "first-sheet.png"
        del index
    return first


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


def _smoke_idempotency_key(*, kind: str) -> str:
    return f"cli-smoke-{kind}-{int(time.time())}-{uuid.uuid4().hex[:8]}"


def _validation_code(exc: SmokeContractError) -> str:
    text = str(exc).lower()
    if "transparency" in text or "chroma" in text or "alpha" in text:
        return "transparency_validation_failed"
    if "pricing" in text or CUSTOMER_CHARGE_PATH.lower() in text:
        return "receipt_pricing_validation_failed"
    if "sha-256" in text or "integrity" in text:
        return "artifact_integrity_validation_failed"
    return "smoke_contract_validation_failed"


def run_smoke(
    project_root: Path,
    *,
    api_url: str | None = None,
    token: str | None = None,
    capability: str = DEFAULT_SMOKE_CAPABILITY,
    prompt: str = DEFAULT_SMOKE_PROMPT,
    poll_seconds: int = DEFAULT_SMOKE_POLL_SECONDS,
    download_dir: Path | None = None,
    request_transparent: bool = True,
    verify_transparency: bool = True,
    extra_input: dict[str, Any] | None = None,
    min_artifacts: int = 1,
    require_sheet_cells: int | None = None,
    smoke_kind: str = "image",
) -> SmokeResult:
    try:
        workspace = require_ready_workspace(
            project_root,
            overrides=CliOverrides(token=token, api_url=api_url),
        )
    except WorkspaceNotReadyError as exc:
        raise SmokeError(str(exc), exit_code=NOT_READY, status="workspace_not_ready", execution_status="not_started") from exc

    client = HydraceptClient(workspace.api_url, workspace.token)
    idem = _smoke_idempotency_key(kind=smoke_kind)
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
        raise SmokeError(f"No jobId in response: {job!r}", status="execution_failed")

    deadline = time.time() + max(5, poll_seconds)
    status = "unknown"
    while time.time() < deadline:
        current = client.get_job(job_id)
        status = str(current.get("status") or "unknown")
        if status in {"succeeded", "failed", "canceled"}:
            if status != "succeeded":
                raise SmokeError(
                    f"Smoke execution ended with status={status}: {current}",
                    job_id=job_id,
                    status="execution_failed",
                    execution_status=status,
                )
            receipt: dict[str, Any] | None = None
            try:
                receipt = client.get_job_receipt(job_id)
            except Exception as exc:  # noqa: BLE001
                raise SmokeError(
                    f"Generation succeeded, but receipt retrieval failed: {exc}",
                    job_id=job_id,
                    status="contract_failed",
                    execution_status="succeeded",
                    validation_error="receipt retrieval failed",
                    validation_code="receipt_retrieval_failed",
                ) from exc
            receipt_id = _receipt_id(receipt)
            artifact_ids = _artifact_ids_from_receipt(receipt) or _artifact_ids_from_receipt(current)
            if not artifact_ids:
                raise SmokeError(
                    "Generation succeeded, but receipt/artifact validation failed: missing artifact identity",
                    job_id=job_id,
                    receipt_id=receipt_id,
                    status="contract_failed",
                    execution_status="succeeded",
                    validation_error="Receipt missing artifact identity",
                    validation_code="artifact_identity_missing",
                    receipt=receipt,
                )
            target_dir = download_dir or (project_root / ".hydracept" / "output")
            target_dir.mkdir(parents=True, exist_ok=True)
            downloads: list[Path] = []
            first_data = b""
            try:
                for artifact_id in artifact_ids:
                    data = client.download_job_artifact(job_id, artifact_id)
                    if not first_data:
                        first_data = data
                    path = target_dir / f"{artifact_id}.png"
                    path.write_bytes(data)
                    downloads.append(path)
            except Exception as exc:  # noqa: BLE001
                raise SmokeError(
                    f"Generation succeeded, but artifact retrieval failed: {exc}",
                    job_id=job_id,
                    downloads=downloads,
                    artifact_ids=artifact_ids,
                    receipt_id=receipt_id,
                    status="contract_failed",
                    execution_status="succeeded",
                    validation_error="artifact retrieval failed",
                    validation_code="artifact_retrieval_failed",
                    receipt=receipt,
                ) from exc
            demo_path = None
            if first_data:
                if require_sheet_cells is not None:
                    demo_path = _write_sheet_demos(project_root, downloads)
                else:
                    demo_path = _write_demo_asset(project_root, first_data)
            try:
                try:
                    validate_terminal_receipt_pricing(receipt)
                except ReceiptValidationError as exc:
                    raise SmokeContractError(str(exc)) from exc
                checks = evaluate_image_smoke_contract(
                    receipt,
                    artifact_id=artifact_ids[0],
                    data=first_data,
                    verify_transparency=verify_transparency,
                )
                if len(artifact_ids) < min_artifacts:
                    raise SmokeContractError(f"expected>={min_artifacts} artifacts, got {len(artifact_ids)}")
                if require_sheet_cells is not None:
                    cells = _sheet_cell_count(receipt)
                    if cells is not None and cells < require_sheet_cells:
                        raise SmokeContractError(f"sheet metadata describes {cells} cells, expected>={require_sheet_cells}")
                    if cells is None and len(artifact_ids) < require_sheet_cells:
                        raise SmokeContractError(f"expected>={require_sheet_cells} sliced artifacts, got {len(artifact_ids)}")
            except SmokeContractError as exc:
                missing_charge = CUSTOMER_CHARGE_PATH in str(exc)
                cause = exc.__cause__
                failing_path = (
                    cause.failing_path
                    if isinstance(cause, ReceiptValidationError)
                    else (CUSTOMER_CHARGE_PATH if missing_charge else "")
                )
                validation_code = _validation_code(exc)
                artifact_path = _artifact_path(demo_path, downloads)
                raise SmokeError(
                    "Generation succeeded. Smoke validation failed: " + str(exc),
                    job_id=job_id,
                    downloads=downloads,
                    artifact_ids=artifact_ids,
                    receipt_id=receipt_id,
                    demo_path=demo_path,
                    status="contract_failed",
                    execution_status="succeeded",
                    validation_error=str(exc),
                    validation_code=validation_code,
                    failing_path=failing_path,
                    suggested_action=(
                        f"python -m hydracept jobs receipt {job_id} --json"
                        if missing_charge
                        else (
                            f"python -m hydracept verify {artifact_path} --json"
                            if validation_code == "transparency_validation_failed" and artifact_path
                            else ""
                        )
                    ),
                    receipt=receipt,
                ) from exc
            return SmokeResult(
                job_id=job_id,
                status=status,
                receipt=receipt,
                artifact_ids=artifact_ids,
                sha256_ok=checks["sha256_ok"],
                transparency_ok=checks["transparency_ok"],
                transparency_report=checks.get("transparency_report"),
                pricing_ok=checks["pricing_ok"],
                downloads=downloads,
                receipt_id=receipt_id,
                demo_path=demo_path,
            )
        time.sleep(3)

    raise SmokeError(
        f"Local smoke wait ended while status={status}; remote job is still active",
        job_id=job_id,
        status="execution_pending",
        execution_status=status,
        suggested_action=f"python -m hydracept jobs get {job_id} --json",
    )


def run_sheet_smoke(project_root: Path, **kwargs: Any) -> SmokeResult:
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
    kwargs["smoke_kind"] = "sheet"
    return run_smoke(project_root, **kwargs)