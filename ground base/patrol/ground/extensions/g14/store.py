"""Resolve artifact:// references inside this task's fixture store.

A Windows path, a UNC path, or a relative sender path is not an artifact.
Bytes stay in the store; callers receive the artifact reference only.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from patrol.ground.kernel.paths import repo_root

_PREFIX = "artifact://"
_PLACEHOLDERS = (
    "placeholder.jpg",
    "demo-20261104-001/drone/downward-001.jpg",
    "demo-20261104-001/dog/front-001.jpg",
)


def fixture_store() -> Path:
    return repo_root() / "fixtures" / "ground" / "g14" / "store"


def placeholder_digests() -> frozenset[str]:
    """Hashes of the bundled synthetic images. A real capture cannot reuse them."""

    found: set[str] = set()
    root = fixture_store()
    for relative in _PLACEHOLDERS:
        path = root.joinpath(*relative.split("/"))
        if path.is_file():
            found.add(hashlib.sha256(path.read_bytes()).hexdigest())
    return frozenset(found)


def resolve_artifact(image_ref: str, store_root: Path) -> tuple[Path | None, str]:
    """Return the store path, or a stable rejection token."""

    if not isinstance(image_ref, str) or not image_ref or image_ref != image_ref.strip():
        return None, "not_artifact"
    if image_ref.startswith(("\\\\", "//")) or _is_windows_path(image_ref):
        return None, "not_artifact"
    if not image_ref.startswith(_PREFIX):
        return None, "not_artifact"
    remainder = image_ref[len(_PREFIX) :]
    if (
        not remainder
        or remainder.startswith("/")
        or "\\" in remainder
        or ":" in remainder
        or remainder.startswith(".")
    ):
        return None, "not_artifact"
    parts = remainder.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None, "path_escape"
    root = Path(store_root)
    if not root.is_absolute():
        return None, "not_artifact"
    try:
        base = root.resolve()
    except OSError:
        return None, "artifact_missing"
    target = base.joinpath(*parts)
    try:
        resolved = target.resolve()
    except OSError:
        return None, "artifact_missing"
    try:
        resolved.relative_to(base)
    except ValueError:
        return None, "path_escape"
    return resolved, ""


def _is_windows_path(value: str) -> bool:
    if len(value) >= 3 and value[0].isalpha() and value[1] == ":" and value[2] in {"\\", "/"}:
        return True
    return False
