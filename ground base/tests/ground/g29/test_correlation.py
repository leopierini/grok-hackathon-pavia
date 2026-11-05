"""Required correlation ids, and distinct goal versus landing names."""

from __future__ import annotations

from patrol.ground.extensions.g29.implementation import LogFeature
from patrol.ground.kernel.contracts import BaseServices
from tests.ground.g29.conftest import journal_count, load_example, request, run


def test_command_and_vision_ids_are_copied(feature: LogFeature) -> None:
    async def body() -> None:
        command = await feature.execute(
            request("accept", {"envelope": load_example("ground-to-dog-command.json")})
        )
        record = command.data["record"]
        assert isinstance(record, dict)
        assert record["command_id"] == "cmd-dog-001"
        assert record["proposal_id"] == "proposal-dog-001"
        assert record["track_id"] == "target-001"
        assert record["beacon_epoch"] == 3
        assert record["map_epoch"] == 1
        assert record["message_id"] == "msg-ground-to-dog-command"
        assert record["source"] == "ground"
        assert record["destination"] == "dog"
        vision = await feature.execute(
            request("accept", {"envelope": load_example("drone-vision-decision.json")})
        )
        seen = vision.data["record"]
        assert isinstance(seen, dict)
        assert seen["request_id"] == "vision-drone-001"
        assert seen["frame_id"] == "drone-downward-001"
        observation = await feature.execute(
            request("accept", {"envelope": load_example("drone-observation.json")})
        )
        pose = observation.data["record"]
        assert isinstance(pose, dict)
        assert pose["frame_id"] == "drone-downward-001"
        assert pose["camera_epoch"] == 1
        assert pose["beacon_epoch"] == 3

    run(body)


def test_command_without_command_id_is_rejected(
    feature: LogFeature,
    services: BaseServices,
) -> None:
    async def body() -> None:
        envelope = load_example("ground-to-dog-command.json")
        payload = envelope["payload"]
        assert isinstance(payload, dict)
        del payload["command_id"]
        envelope["message_id"] = "msg-no-command"
        result = await feature.execute(request("accept", {"envelope": envelope}))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert result.error.detail == "command record is missing command_id"
        assert result.data["published"] is False
        assert feature.records == []
        assert journal_count(services) == 0

    run(body)


def test_ack_without_command_id_is_rejected(feature: LogFeature) -> None:
    async def body() -> None:
        envelope = load_example("dog-ack-accepted.json")
        payload = envelope["payload"]
        assert isinstance(payload, dict)
        del payload["command_id"]
        envelope["message_id"] = "msg-ack-no-command"
        result = await feature.execute(request("accept", {"envelope": envelope}))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "rejected"
        assert feature.records == []

    run(body)


def test_vision_decision_without_frame_id_is_rejected(feature: LogFeature) -> None:
    async def body() -> None:
        envelope = load_example("drone-vision-decision.json")
        payload = envelope["payload"]
        assert isinstance(payload, dict)
        del payload["frame_id"]
        envelope["message_id"] = "msg-vision-no-frame"
        result = await feature.execute(request("accept", {"envelope": envelope}))
        assert result.status == "failed"
        assert result.error is not None
        assert "frame_id" in result.error.detail
        assert feature.records == []

    run(body)


def test_vision_request_without_request_id_is_rejected(feature: LogFeature) -> None:
    async def body() -> None:
        envelope = load_example("drone-vision-request.json")
        payload = envelope["payload"]
        assert isinstance(payload, dict)
        del payload["request_id"]
        envelope["message_id"] = "msg-vision-no-request"
        result = await feature.execute(request("accept", {"envelope": envelope}))
        assert result.status == "failed"
        assert result.error is not None
        assert "request_id" in result.error.detail

    run(body)


def test_goal_and_landing_stay_distinct(feature: LogFeature) -> None:
    async def body() -> None:
        goal = await feature.execute(
            request("accept", {"envelope": load_example("event-demo_goal_reached.json")})
        )
        landing = await feature.execute(
            request("accept", {"envelope": load_example("event-landing_unverified.json")})
        )
        unknown = await feature.execute(
            request("accept", {"envelope": load_example("drone-landing-unknown.json")})
        )
        goal_record = goal.data["record"]
        landing_record = landing.data["record"]
        unknown_record = unknown.data["record"]
        assert isinstance(goal_record, dict)
        assert isinstance(landing_record, dict)
        assert isinstance(unknown_record, dict)
        assert goal_record["event_name"] == "demo_goal_reached"
        assert goal_record["category"] == "completion"
        assert landing_record["event_name"] == "landing_unverified"
        assert landing_record["category"] == "safety"
        assert goal_record["event_name"] != landing_record["event_name"]
        assert unknown_record["event_name"] == "landing_not_verified"
        assert unknown_record["category"] == "acknowledgement"
        assert unknown_record["command_id"] == "cmd-drone-land-001"
        assert len(feature.records) == 3

    run(body)


def test_string_simulated_flag_is_rejected(feature: LogFeature) -> None:
    async def body() -> None:
        envelope = load_example("pi-heartbeat.json")
        envelope["simulated"] = "true"
        envelope["message_id"] = "msg-string-bool"
        result = await feature.execute(request("accept", {"envelope": envelope}))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "invalid_input"
        assert feature.records == []

    run(body)
