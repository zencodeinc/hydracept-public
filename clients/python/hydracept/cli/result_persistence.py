"""Universal `--out` persistence for run results.

Invariant: supplying an output path means bytes appear there on success, or the
run fails loudly with a typed error. There is no silent no-op.

Rendering rule:

* an explicit ``.json`` output path always receives the canonical result envelope;
* any other output path receives the rendered text when the result has a text
  rendering, and the canonical ``hydracept.run-result.v1`` JSON envelope otherwise.

The recorded ``persistedOutputKind`` always matches the bytes actually written.
"""

from __future__ import annotations

import json
from pathlib import Path

from hydracept.cli.artifact_output import finalize_single_artifact_path, resolve_artifact_output
from hydracept.cli.run_output_preview import human_run_preview
from hydracept.run_result import RunResult


def _text_rendering(result: RunResult) -> str | None:
    rendering = human_run_preview(result.to_dict())
    if rendering is None or not rendering.strip():
        return None
    return rendering.strip()


def preferred_output_kind(out: Path, result: RunResult) -> str:
    """Return ``"text"`` or ``"json"`` for an explicit output path.

    An explicit ``.json`` path always receives the envelope. Anything else
    receives the rendered text when the result has one, so the recorded kind can
    never disagree with the bytes written.
    """
    if Path(str(out)).suffix.lower() == ".json":
        return "json"
    return "text" if _text_rendering(result) is not None else "json"


def render_result_payload(result: RunResult, *, kind: str) -> bytes:
    if kind == "text":
        rendering = _text_rendering(result)
        if rendering is not None:
            return (rendering + "\n").encode("utf-8")
    return (json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def resolve_result_target(project_root: Path, out: Path, kind: str, result: RunResult) -> Path:
    filename = "result.txt" if kind == "text" else "result.json"
    resolved = resolve_artifact_output(
        project_root,
        out,
        filename,
        1,
        job_id=result.execution_id or result.idempotency_key or "result",
    )
    return finalize_single_artifact_path(resolved, filename)


def persist_run_result(project_root: Path, out: Path, result: RunResult) -> Path:
    """Write the run result to ``out`` and record it on ``result.diagnostics``."""
    kind = preferred_output_kind(out, result)
    target = resolve_result_target(project_root, out, kind, result)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(render_result_payload(result, kind=kind))
    result.diagnostics = {
        **(result.diagnostics or {}),
        "requestedOutputPath": str(out),
        "persistedOutputPath": str(target),
        "persistedOutputKind": kind,
    }
    return target


_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "canceled", "cancelled"})


def output_not_persisted_note(
    *,
    status: str,
    persist: bool = True,
    has_remote_artifacts: bool = False,
) -> str:
    """Explicit explanation when ``out`` was supplied but nothing was written."""
    if not persist:
        return "Persistence is disabled for this call; nothing was written to the requested output path."
    normalized = str(status or "").strip().lower()
    if normalized not in _TERMINAL_STATUSES:
        return (
            f"No file was written to the requested output path: the execution is not terminal "
            f"(status={status}). After it succeeds, run "
            "`python -m hydracept jobs recover <jobId> --out <path>`."
        )
    if normalized != "succeeded":
        return (
            f"No file was written to the requested output path: the execution did not succeed "
            f"(status={status})."
        )
    if has_remote_artifacts:
        return (
            "Remote artifacts were reported but none were persisted locally. Run "
            "`python -m hydracept jobs recover <jobId> --out <path>`."
        )
    return "No file was written to the requested output path."
