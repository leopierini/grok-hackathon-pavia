"""Stage allowlist and track-id rule."""

from __future__ import annotations

from pathlib import Path

from tests.ground.g15.support import call, opened, payload, payload_of, run


def test_drone_search_accepts_a_null_track(tmp_path: Path) -> None:
    async def body() -> None:
        _services, port = opened(tmp_path)
        result = await call(port, payload(_services, "drone-downward-001"))
        assert result.status == "ok"
        assert result.data["outcome"] == "emitted"
        assert payload_of(result)["stage"] == "drone_search"
        assert payload_of(result)["active_track_id"] is None
        assert result.error is None
        assert result.events == ()

    run(body)


def test_drone_search_copies_a_track_when_one_exists(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        body = payload(built, "drone-downward-001", active_track_id="target-001")
        result = await call(port, body)
        assert payload_of(result)["active_track_id"] == "target-001"

    run(body)


def test_tracking_stages_reject_a_missing_track(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        for stage, camera in (
            ("drone_track", "downward"),
            ("dog_acquire", "front"),
            ("dog_approach", "front"),
        ):
            result = await call(
                port,
                payload(built, f"{stage}-frame", stage=stage, camera=camera, active_track_id=None),
            )
            assert result.status == "blocked"
            assert result.error is not None
            assert result.error.code == "rejected"
            assert result.data["message"] is None

        accepted = await call(
            port,
            payload(
                built,
                "drone-track-001",
                stage="drone_track",
                camera="downward",
                active_track_id="target-001",
            ),
        )
        assert accepted.data["outcome"] == "emitted"
        assert payload_of(accepted)["active_track_id"] == "target-001"

    run(body)


def test_unknown_stage_and_non_boolean_track_are_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        unknown = await call(port, payload(built, "frame", stage="search"))
        assert unknown.status == "failed"
        assert unknown.error is not None
        assert unknown.error.code == "invalid_input"
        flagged = await call(port, payload(built, "frame", active_track_id=True))
        assert flagged.status == "failed"
        assert flagged.error is not None
        assert flagged.error.code == "invalid_input"

    run(body)


def test_camera_must_match_the_stage(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        result = await call(port, payload(built, "front-on-drone", camera="front"))
        assert result.status == "blocked"
        assert result.error is not None
        assert "downward" in result.error.detail

    run(body)
