"""Every contract example lands in the category its kind requires."""

from __future__ import annotations

from patrol.ground.extensions.g29.classify import LOG_SCHEMA, LOGS_STATUS
from patrol.ground.extensions.g29.implementation import LogFeature
from tests.ground.g29.conftest import load_example, request, run

EXPECTED = {
    "ai-to-dog-proposal.json": "approval",
    "ai-to-drone-proposal.json": "approval",
    "dog-ack-accepted.json": "acknowledgement",
    "dog-ack-completed.json": "acknowledgement",
    "dog-ack-running.json": "acknowledgement",
    "dog-capabilities.json": "session",
    "dog-command-rejected.json": "acknowledgement",
    "dog-navigation-candidates.json": "observation",
    "dog-observation.json": "observation",
    "dog-vision-decision.json": "vision",
    "dog-vision-request.json": "vision",
    "drone-ack-accepted.json": "acknowledgement",
    "drone-ack-completed.json": "acknowledgement",
    "drone-ack-running.json": "acknowledgement",
    "drone-capabilities.json": "session",
    "drone-landing-unknown.json": "acknowledgement",
    "drone-observation.json": "observation",
    "drone-vision-decision.json": "vision",
    "drone-vision-request.json": "vision",
    "event-demo_goal_reached.json": "completion",
    "event-dog_dispatched.json": "command",
    "event-drone_target_acquired.json": "observation",
    "event-landing_unverified.json": "safety",
    "ground-to-dog-command.json": "command",
    "ground-to-dog-halt.json": "command",
    "ground-to-drone-command.json": "command",
    "ground-to-drone-hover.json": "command",
    "ground-to-drone-land.json": "command",
    "pi-capabilities.json": "session",
    "pi-heartbeat.json": "session",
    "pi-rssi-window.json": "observation",
    "proximity-evidence.json": "completion",
}


def test_every_example_kind_has_one_category(feature: LogFeature) -> None:
    async def body() -> None:
        seen: dict[str, str] = {}
        for name, category in EXPECTED.items():
            envelope = load_example(name)
            result = await feature.execute(request("accept", {"envelope": envelope}))
            assert result.status == "ok", name
            assert result.error is None
            assert result.data["category"] == category
            assert result.data["published"] is False
            assert result.data["writer_state"] == "queued"
            assert result.data["log_schema"] == LOG_SCHEMA
            assert result.data["logs_requirements_status"] == LOGS_STATUS
            kind = envelope["kind"]
            assert isinstance(kind, str)
            if kind == "mission.event":
                continue
            previous = seen.get(kind)
            if previous is None:
                seen[kind] = category
            else:
                assert previous == category
        assert len(feature.records) == len(EXPECTED)

    run(body)


def test_known_zero_pose_is_kept(feature: LogFeature) -> None:
    async def body() -> None:
        result = await feature.execute(
            request("accept", {"envelope": load_example("dog-observation.json")})
        )
        record = result.data["record"]
        assert isinstance(record, dict)
        summary = record["summary"]
        assert isinstance(summary, dict)
        pose = summary["pose"]
        assert isinstance(pose, dict)
        assert pose["x_m"] == 0
        assert pose["y_m"] == 0
        assert pose["z_m"] == 0

    run(body)


def test_future_team_field_does_not_drop_core_ids(feature: LogFeature) -> None:
    async def body() -> None:
        envelope = load_example("pi-heartbeat.json")
        payload = envelope["payload"]
        assert isinstance(payload, dict)
        payload["team_field"] = "later-requirement"
        result = await feature.execute(request("accept", {"envelope": envelope}))
        record = result.data["record"]
        assert isinstance(record, dict)
        summary = record["summary"]
        assert isinstance(summary, dict)
        assert summary["team_field"] == "later-requirement"
        assert record["message_id"] == envelope["message_id"]
        assert record["mission_id"] == envelope["mission_id"]
        assert record["epoch"] == envelope["epoch"]
        assert record["log_schema"] == "proposed-1"

    run(body)
