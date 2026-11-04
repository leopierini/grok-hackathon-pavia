"""Hash agreement, placeholder bytes, and the published example hash."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from patrol.ground.extensions.g14.scenarios import _flip_bit
from patrol.ground.extensions.g14.store import fixture_store
from patrol.ground.kernel.paths import repo_root
from tests.ground.g14.helpers import load_frame, load_json, run


def test_downward_example_hash_matches_its_bytes(tmp_path: Path) -> None:
    frame = load_frame("downward")
    path = fixture_store() / "demo-20261104-001" / "drone" / "downward-001.jpg"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert frame["sha256"] == digest
    assert frame["width_px"] == 320
    assert frame["height_px"] == 240

    async def body() -> None:
        result, built = await run(tmp_path, frame, source="drone")
        assert result.status == "ok"
        assert result.error is None
        assert result.data["sha256"] == digest
        assert result.data["image_ref"] == frame["image_ref"]
        assert result.data["captured_at"] == frame["captured_at"]
        assert "bytes" not in result.data
        assert path.is_file()
        assert built.evidence.trace == ["evidence.validate"]
        assert built.adapters.devices.calls == []

    asyncio.run(body())


def test_one_flipped_hash_bit_is_rejected(tmp_path: Path) -> None:
    frame = load_frame("downward")
    frame["sha256"] = _flip_bit(str(frame["sha256"]))

    async def body() -> None:
        result, built = await run(tmp_path, frame)
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert result.error.detail == "hash_mismatch"
        assert result.data["accepted"] is False
        assert built.evidence.trace == []
        assert built.adapters.devices.calls == []

    asyncio.run(body())


def test_published_contract_hash_does_not_match_the_synthetic_bytes(tmp_path: Path) -> None:
    published = load_json("published/drone-observation.json")
    payload = published["payload"]
    assert isinstance(payload, dict)
    raw = payload["frame"]
    assert isinstance(raw, dict)
    frame = {str(key): value for key, value in raw.items()}
    path = fixture_store() / "demo-20261104-001" / "drone" / "downward-001.jpg"
    assert frame["sha256"] != hashlib.sha256(path.read_bytes()).hexdigest()

    async def body() -> None:
        result, _built = await run(tmp_path, frame)
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.detail == "hash_mismatch"

    asyncio.run(body())


def test_uppercase_and_short_hashes_are_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        upper = load_frame("downward")
        upper["sha256"] = str(upper["sha256"]).upper()
        rejected, _built = await run(tmp_path, upper)
        assert rejected.error is not None
        assert rejected.error.code == "invalid_input"
        short = load_frame("front")
        short["sha256"] = "ab" * 31
        again, _built = await run(tmp_path, short)
        assert again.error is not None
        assert again.error.detail == "invalid_frame"

    asyncio.run(body())


def test_vision_example_is_not_emitted(tmp_path: Path) -> None:
    example = (
        repo_root() / "fixtures" / "ground" / "g14" / "published" / "drone-vision-request.json"
    )
    text = example.read_text(encoding="utf-8")
    assert '"kind": "vision.request"' in text

    async def body() -> None:
        result, built = await run(tmp_path, load_frame("downward"))
        assert result.events[0].kind == "frame_validated"
        assert all(event.kind != "vision.request" for event in result.events)
        assert "vision.request" not in str(result.data)
        assert built.adapters.devices.calls == []
        assert built.state.trace == []

    asyncio.run(body())
