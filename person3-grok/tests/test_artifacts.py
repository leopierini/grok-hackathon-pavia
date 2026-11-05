"""Fixture artifact URIs resolve to the rehearsal JPEGs. No network."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from patrol.bridge.ground import resolve_roots
from patrol.vision_v2.artifacts import ArtifactError, resolve_artifact


def _frame(name: str) -> dict[str, object]:
    ground, _dog = resolve_roots(None)
    path = ground / "fixtures" / "ground" / "g14" / "accepted" / name
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_downward_and_front_fixtures_match_their_sha256() -> None:
    for name in ("downward.json", "front.json"):
        frame = _frame(name)
        image_ref = frame["image_ref"]
        digest = frame["sha256"]
        assert isinstance(image_ref, str)
        assert isinstance(digest, str)
        data = resolve_artifact(image_ref, digest)
        assert data.startswith(b"\xff\xd8\xff")
        assert hashlib.sha256(data).hexdigest() == digest


def test_missing_artifact_and_bad_hash_fail_closed() -> None:
    frame = _frame("downward.json")
    image_ref = str(frame["image_ref"])
    with pytest.raises(ArtifactError, match="artifact missing"):
        resolve_artifact(image_ref.replace("downward-001.jpg", "missing.jpg"), "a" * 64)
    with pytest.raises(ArtifactError, match="sha256 mismatch"):
        resolve_artifact(image_ref, "b" * 64)


def test_path_escape_is_rejected() -> None:
    with pytest.raises(ArtifactError, match="path escape"):
        resolve_artifact("artifact://demo-20261104-001/../../outside.jpg", "c" * 64)
    with pytest.raises(ArtifactError, match="not an artifact"):
        resolve_artifact(str(Path("/tmp/frame.jpg")), "d" * 64)
