"""Shared artifact output target resolution for CLI and MCP."""

from __future__ import annotations

from pathlib import Path

_FILE_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".ogg",
        ".glb",
        ".gltf",
        ".wav",
        ".mp3",
        ".json",
        ".txt",
    }
)


class ArtifactOutputError(ValueError):
    """Typed failure when an artifact output target is invalid."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _looks_like_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    return bool(suffix and suffix in _FILE_SUFFIXES)


def _resolve_within_project(project_root: Path, requested: Path) -> Path:
    root = project_root.resolve()
    if requested.is_absolute():
        return requested
    candidate = (root / requested).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise ArtifactOutputError(
            "ARTIFACT_OUTPUT_TRAVERSAL",
            f"Artifact output {requested} escapes the project root.",
        ) from None
    return candidate


def resolve_artifact_output(
    project_root: Path,
    requested_path: str | Path | None,
    artifact_filename: str,
    artifact_count: int = 1,
    *,
    job_id: str | None = None,
) -> Path:
    """Resolve where an artifact (or artifact set) should be written."""
    root = Path(project_root)
    filename = Path(str(artifact_filename or "artifact.bin")).name
    count = max(1, int(artifact_count or 1))
    requested = str(requested_path or "").strip()

    if not requested:
        if not str(job_id or "").strip():
            raise ArtifactOutputError(
                "ARTIFACT_OUTPUT_JOB_REQUIRED",
                "job_id is required when no output path is provided.",
            )
        return (root / ".hydracept" / "output" / str(job_id).strip()).resolve()

    target = _resolve_within_project(root, Path(requested))
    if count > 1 and _looks_like_file(target):
        raise ArtifactOutputError(
            "ARTIFACT_OUTPUT_FILE_WITH_MULTIPLE_ARTIFACTS",
            "A file output path cannot be used when multiple artifacts are being saved.",
        )
    if _looks_like_file(target):
        return target
    if target.suffix and not target.exists():
        # Preserve explicit extension-bearing relative paths as file targets.
        return target
    return target / filename


def is_file_output_target(path: Path) -> bool:
    """True when ``path`` is a concrete file destination rather than a directory."""
    if path.exists() and path.is_dir():
        return False
    return _looks_like_file(path) or bool(path.suffix)


def finalize_single_artifact_path(resolved: Path, artifact_filename: str) -> Path:
    """Turn a resolved directory or file target into a concrete single-artifact file path."""
    filename = Path(str(artifact_filename or "artifact.bin")).name
    if is_file_output_target(resolved):
        return resolved
    return resolved / filename
