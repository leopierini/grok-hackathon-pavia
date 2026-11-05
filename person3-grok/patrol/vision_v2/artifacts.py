"""Resolve ``artifact://`` rehearsal frames to JPEG bytes.

This does not import Ground's ``patrol`` package. The store is the g14 fixture
directory under ``ground base``. A missing file or a hash mismatch raises
``ArtifactError``. No socket is opened.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from patrol.bridge.ground import resolve_roots

_PREFIX = "artifact://"
_JPEG = b"\xff\xd8\xff"


class ArtifactError(Exception):
    """The request named an image this tree cannot hand to a model."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def resolve_artifact(
    image_ref: str,
    expected_sha256: str,
    *,
    team_repo: str | Path | None = None,
) -> bytes:
    """Return JPEG bytes whose SHA-256 matches ``expected_sha256``."""

    if not isinstance(expected_sha256, str) or len(expected_sha256.strip()) != 64:
        raise ArtifactError("invalid_input", "frame sha256 must be 64 hex characters")
    path = _artifact_path(image_ref, team_repo)
    if not path.is_file():
        raise ArtifactError("unavailable", f"artifact missing: {image_ref}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ArtifactError("io_fault", f"artifact unreadable: {image_ref}") from exc
    if not data.startswith(_JPEG):
        raise ArtifactError("rejected", f"artifact is not a JPEG: {image_ref}")
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256.strip().lower():
        raise ArtifactError("validation_failed", f"sha256 mismatch: {image_ref}")
    return data


def _artifact_path(image_ref: str, team_repo: str | Path | None) -> Path:
    if not isinstance(image_ref, str) or not image_ref.startswith(_PREFIX):
        raise ArtifactError("rejected", f"not an artifact URI: {image_ref}")
    remainder = image_ref[len(_PREFIX) :]
    if (
        not remainder
        or remainder.startswith("/")
        or "\\" in remainder
        or ":" in remainder
        or remainder.startswith(".")
    ):
        raise ArtifactError("rejected", f"not an artifact URI: {image_ref}")
    parts = remainder.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ArtifactError("rejected", f"artifact path escape: {image_ref}")
    ground, _dog = resolve_roots(team_repo)
    store = (ground / "fixtures" / "ground" / "g14" / "store").resolve()
    target = store.joinpath(*parts).resolve()
    try:
        target.relative_to(store)
    except ValueError as exc:
        raise ArtifactError("rejected", f"artifact path escape: {image_ref}") from exc
    return target
