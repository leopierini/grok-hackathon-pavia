"""The placeholder model id is copied through and never replaced."""

from __future__ import annotations

from pathlib import Path

from patrol.ground.extensions.g15.schedule import PLACEHOLDER_MODEL
from tests.ground.g15.support import (
    assert_placeholder,
    call,
    opened,
    payload,
    payload_of,
    run,
    settings,
)


def test_placeholder_model_id_is_not_rewritten(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        result = await call(port, payload(built, "drone-downward-001"))
        assert_placeholder(result)
        assert payload_of(result)["model_id"] == PLACEHOLDER_MODEL
        assert "grok-" not in str(payload_of(result)["model_id"])
        assert payload_of(result)["prompt_version"] == "patrol-demo-v2.0"

    run(body)


def test_a_configured_model_id_is_copied_as_resolved(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        configured = "configured-image-model"
        result = await call(
            port,
            payload(built, "drone-downward-001", settings=settings(model_id=configured)),
        )
        assert result.data["model_unresolved"] is False
        assert payload_of(result)["model_id"] == configured

    run(body)


def test_missing_model_id_is_not_invented(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        raw = settings()
        del raw["model_id"]
        result = await call(port, payload(built, "drone-downward-001", settings=raw))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "invalid_input"
        assert result.data["message"] is None

    run(body)


def test_criminal_intent_text_is_not_forwarded(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        result = await call(
            port,
            payload(built, "drone-downward-001", target_description="Infer criminal intent"),
        )
        assert result.status == "blocked"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert result.data["message"] is None

    run(body)


def test_string_booleans_and_a_second_in_flight_slot_are_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = opened(tmp_path)
        flagged = settings()
        scene = flagged["scene_context"]
        assert isinstance(scene, dict)
        scene["staged_demo"] = "true"
        text = await call(port, payload(built, "drone-downward-001", settings=flagged))
        assert text.status == "failed"
        crowded = await call(
            port,
            payload(built, "drone-downward-001", settings=settings(max_in_flight=2)),
        )
        assert crowded.status == "blocked"
        assert crowded.error is not None
        assert crowded.error.code == "rejected"

    run(body)
