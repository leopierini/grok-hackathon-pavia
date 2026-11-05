"""Approved move_local matches the dog command schema and stays off the dog port."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from tests.ground.g23.support import (
    approve,
    calls_of,
    command_of,
    fixture,
    move_payload,
    opened,
    payload_of,
    run,
)


def test_manifest_registers_the_v2_slot() -> None:
    path = Path("patrol/ground/extensions/g23/manifest.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw == {
        "schema_version": "ground-task-v2",
        "task_id": "GROUND-23",
        "slot": "feature.v2_dog_command",
        "factory": "patrol.ground.extensions.g23.implementation:create",
        "scenario_factory": "patrol.ground.extensions.g23.scenarios:cases",
    }


def test_example_proposal_yields_command_keys(tmp_path: Path) -> None:
    async def body() -> None:
        services, feature = opened(tmp_path)
        result = await approve(feature, move_payload())
        command = command_of(result)
        example = fixture("command-example.json")
        body_payload = payload_of(command)
        example_payload = payload_of(example)
        motion = body_payload["motion"]
        example_motion = example_payload["motion"]
        assert isinstance(motion, dict)
        assert isinstance(example_motion, dict)
        assert set(command) == set(example)
        assert set(body_payload) == set(example_payload)
        assert set(motion) == set(example_motion)
        assert command["kind"] == "dog.command"
        assert command["source"] == "ground"
        assert command["destination"] == "dog"
        assert command["protocol_version"] == "2.0-draft"
        assert command["simulated"] is True
        assert command["correlation_id"] == "msg-ai-to-dog-proposal"
        assert body_payload["action"] == "move_local"
        assert body_payload["action"] != "approach"
        assert body_payload["proposal_id"] == "proposal-dog-001"
        assert body_payload["track_id"] == "target-001"
        assert body_payload["beacon_epoch"] == 3
        assert body_payload["lease_ms"] == 300
        assert body_payload["safety_snapshot_id"] == "safety-001"
        assert motion["frame_id"] == "dog/base_link"
        assert motion["candidate_id"] == "candidate-forward-01"
        assert motion["snapshot_id"] == "nav-001"
        assert motion["map_epoch"] == 1
        assert motion["linear_x_m_s"] == 0.1
        assert motion["linear_y_m_s"] == 0.0
        assert motion["angular_z_rad_s"] == 0.0
        assert motion["duration_ms"] == 300
        assert "direction_hint" not in command
        assert "direction_hint" not in body_payload
        assert "direction_hint" not in motion
        assert "altitude" not in json.dumps(command)
        assert "altitude_m" not in json.dumps(command)
        reason = body_payload["reason"]
        assert isinstance(reason, str)
        assert "recheck" in reason
        assert "Unitree" in reason
        assert "+x forward" in reason
        assert calls_of(services) == []
        records = getattr(services.journal, "records", None)
        assert records == []
        assert result.events[0].kind == "operation_started"
        assert result.data["dog_port_called"] is False
        assert result.data["slot"] == "feature.v2_dog_command"

    run(body)


def test_lease_expiry_is_the_lease_after_send(tmp_path: Path) -> None:
    async def body() -> None:
        _services, feature = opened(tmp_path)
        command = command_of(await approve(feature, move_payload()))
        assert command["sent_at"] == "2026-01-01T00:00:00.000Z"
        assert command["expires_at"] == "2026-01-01T00:00:00.300Z"

    run(body)


def test_homing_selection_without_proposal(tmp_path: Path) -> None:
    async def body() -> None:
        services, feature = opened(tmp_path)
        payload = move_payload(selection=fixture("selection.json"))
        del payload["proposal"]
        command = command_of(await approve(feature, payload))
        assert command["correlation_id"] is None
        assert payload_of(command)["proposal_id"] == "proposal-dog-001"
        assert payload_of(command)["action"] == "move_local"
        assert calls_of(services) == []

    run(body)


def test_stand_and_turn_stay_in_the_ground_frame(tmp_path: Path) -> None:
    async def body() -> None:
        services, feature = opened(tmp_path)
        stand = command_of(await approve(feature, move_payload(action="stand")))
        stand_motion = payload_of(stand)["motion"]
        assert isinstance(stand_motion, dict)
        assert payload_of(stand)["action"] == "stand"
        assert stand_motion["linear_x_m_s"] == 0.0
        assert stand_motion["angular_z_rad_s"] == 0.0
        turned = command_of(
            await approve(
                feature,
                move_payload(action="turn", angular_z_rad_s=0.4, linear_x_m_s=0.0),
            )
        )
        turn_motion = payload_of(turned)["motion"]
        assert isinstance(turn_motion, dict)
        assert payload_of(turned)["action"] == "turn"
        assert turn_motion["angular_z_rad_s"] == 0.4
        assert "linear_z_m_s" not in turn_motion
        assert calls_of(services) == []

    run(body)


def test_operator_up_down_and_left_are_ground_axes(tmp_path: Path) -> None:
    async def body() -> None:
        _services, up_feature = opened(tmp_path / "up")
        up = payload_of(command_of(await approve(up_feature, move_payload(operator_axis="up"))))
        up_motion = up["motion"]
        assert isinstance(up_motion, dict)
        assert up_motion["linear_x_m_s"] == 0.1
        assert "z_m" not in up_motion
        _services, down_feature = opened(tmp_path / "down")
        down = payload_of(
            command_of(await approve(down_feature, move_payload(operator_axis="down")))
        )
        down_motion = down["motion"]
        assert isinstance(down_motion, dict)
        assert down_motion["linear_x_m_s"] == -0.1
        _services, left_feature = opened(tmp_path / "left")
        left = payload_of(
            command_of(
                await approve(left_feature, move_payload(operator_axis="left", linear_y_m_s=0.2))
            )
        )
        left_motion = left["motion"]
        assert isinstance(left_motion, dict)
        assert left_motion["linear_y_m_s"] == 0.2

    run(body)


def test_no_robot_sdk_import() -> None:
    root = Path("patrol/ground/extensions/g23")
    banned = {"djitellopy", "unitree_webrtc_connect", "go2_webrtc_connect", "xai_sdk", "xai"}
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            for module in modules:
                assert module.split(".", 1)[0] not in banned
                # g17 is the drone-command factory. A land_on_dog proposal is handed
                # there instead of being rewritten into a dog walk.
                assert not module.startswith("patrol.ground.extensions.g") or module.startswith(
                    ("patrol.ground.extensions.g23", "patrol.ground.extensions.g17")
                )
