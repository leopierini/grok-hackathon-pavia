"""Serve evidence only from allowlisted artifact roots."""

from __future__ import annotations

from pathlib import Path

MAX_BYTES = 2_000_000
_JPEG = b"\xff\xd8\xff"


class ArtifactError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


def resolve_jpeg(artifact_id: str, roots: tuple[Path, ...]) -> Path:
    relative = _relative(artifact_id)
    for root in roots:
        base = root.resolve()
        candidate = (base / relative).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            continue
        if not candidate.is_file():
            continue
        if candidate.stat().st_size > MAX_BYTES:
            raise ArtifactError("rejected", "evidence file exceeds the size limit")
        with candidate.open("rb") as handle:
            header = handle.read(3)
        if header != _JPEG:
            raise ArtifactError("rejected", "evidence is not a JPEG")
        return candidate
    raise ArtifactError("not_found", "evidence id is not in an allowlisted artifact root")


def _relative(artifact_id: str) -> Path:
    if not isinstance(artifact_id, str) or not artifact_id or len(artifact_id) > 240:
        raise ArtifactError("invalid_input", "evidence id is missing or too long")
    text = artifact_id
    if text.startswith("artifact://"):
        text = text[len("artifact://") :]
    if text.startswith("/") or "\\" in text or ":" in text or ".." in text.split("/"):
        raise ArtifactError("rejected", "evidence id escapes the artifact root")
    parts = tuple(part for part in text.split("/") if part)
    if not parts or any(part in {".", ".."} for part in parts):
        raise ArtifactError("rejected", "evidence id escapes the artifact root")
    return Path(*parts)
