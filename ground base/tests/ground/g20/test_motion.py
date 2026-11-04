"""This feature never proposes a dog motion method."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from tests.ground.g20.support import calls_of, feature, payload, request, run


def _blob(result_data: object, events: object) -> str:
    return json.dumps({"data": result_data, "events": events}, default=str)


def test_example_proposes_no_motion_method(tmp_path: Path) -> None:
    async def body() -> None:
        built, port = feature(tmp_path)
        result = await port.execute(request(payload()))
        assert result.data["commands"] == ()
        assert result.data["motion_proposed"] is False
        blob = _blob(result.data, [event.payload for event in result.events])
        assert "move_local" not in blob
        assert calls_of(built) == []

    run(body)


def test_blocked_observation_proposes_no_forward_step(tmp_path: Path) -> None:
    async def body() -> None:
        from tests.ground.g20.support import as_object, candidates

        message = candidates()
        body_map = as_object(message["payload"], "payload")
        body_map["candidates"] = []
        body_map["blocked"] = True
        built, port = feature(tmp_path)
        result = await port.execute(request(payload(candidate_message=message)))
        assert result.data["commands"] == ()
        assert result.data["candidate_ids"] == ()
        blob = _blob(result.data, [event.payload for event in result.events])
        assert "move_local" not in blob
        assert "candidate-forward-01" not in blob
        assert calls_of(built) == []

    run(body)


def test_frame_handle_is_not_opened(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload()))
        frame = result.data["frame"]
        assert isinstance(frame, Mapping)
        image_ref = frame["image_ref"]
        assert isinstance(image_ref, str)
        assert image_ref.startswith("artifact://")
        assert not Path(str(frame["image_ref"])).exists()

    run(body)


def test_device_mismatch_is_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        from tests.ground.g20.support import as_object, candidates

        message = candidates()
        as_object(message["payload"], "payload")["device_id"] = "dog-02"
        built, port = feature(tmp_path)
        result = await port.execute(request(payload(candidate_message=message)))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "contract_mismatch"
        assert result.data["commands"] == ()
        assert calls_of(built) == []

    run(body)
