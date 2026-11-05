"""Resolve ``artifact://`` rehearsal frames to JPEG bytes and check SHA-256.

The bytes stay inside the connector. Ground keeps the artifact reference.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from patrol.ground.extensions.g14.store import fixture_store, resolve_artifact
from patrol.ground.signal.errors import SignalError

_JPEG = b"\xff\xd8\xff"


def load_fixture_jpeg(
    image_ref: str,
    expected_sha256: str,
    store_root: Path | None = None,
) -> bytes:
    """Return JPEG bytes for one fixture reference, or raise ``SignalError``."""

    if not isinstance(expected_sha256, str) or len(expected_sha256.strip()) != 64:
        raise SignalError("invalid_input", "frame sha256 must be 64 hex characters")
    root = fixture_store() if store_root is None else store_root
    path, token = resolve_artifact(image_ref, root)
    if path is None:
        detail = "artifact URI could not be resolved" if token == "not_artifact" else token
        raise SignalError("rejected", f"{detail}: {image_ref}")
    if not path.is_file():
        raise SignalError("unavailable", f"artifact missing: {image_ref}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise SignalError("io_fault", f"artifact unreadable: {image_ref}") from exc
    if not data.startswith(_JPEG):
        raise SignalError("rejected", f"artifact is not a JPEG: {image_ref}")
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256.strip().lower():
        raise SignalError("validation_failed", f"sha256 mismatch: {image_ref}")
    return data
