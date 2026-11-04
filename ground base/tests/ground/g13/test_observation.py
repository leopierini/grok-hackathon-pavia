"""The example drone observation is stored with its own height reference."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.kernel.contracts import FeatureResult
from tests.ground.g13.support import feature, load, request_for


def _run(path: Path, request: object) -> tuple[object, FeatureResult]:
    services, provider = feature(path)

    async def body() -> FeatureResult:
        return await provider.execute(request)  # type: ignore[arg-type]

    return services, asyncio.run(body())


def _observation(result: FeatureResult) -> Mapping[str, object]:
    body = result.data["observation"]
    assert isinstance(body, Mapping)
    return body


def test_example_keeps_floor_height_and_both_clocks(tmp_path: Path) -> None:
    services, result = _run(
        tmp_path,
        request_for(load("drone-observation.json"), load("drone-capabilities.json")),
    )
    assert result.status == "ok"
    assert result.error is None
    body = _observation(result)
    assert body["flight_state"] == "airborne"
    assert body["height_estimate_m"] == 4.0
    assert body["height_reference"] == "floor_agl"
    assert body["floor_agl_claim"] is True
    assert body["battery_percent"] == 74
    assert body["pose"] is None
    assert body["active_command_id"] is None
    assert body["command_completed"] is False
    assert body["beacon_policy"] == "deferred"
    assert body["sent_at"] == "2026-11-04T13:00:10.000Z"
    assert body["received_utc"] == "2026-01-01T00:00:00+00:00"
    assert body["received_monotonic"] == 0.0
    assert body["sent_at"] != body["received_utc"]
    beacon = body["beacon"]
    assert isinstance(beacon, Mapping)
    assert beacon["beacon_epoch"] == 3
    assert beacon["bssid"] == "02:00:00:00:00:01"
    assert beacon["hold_state"] == "stable"
    frame = body["frame"]
    assert isinstance(frame, Mapping)
    assert frame["camera_id"] == "downward"
    assert frame["camera_epoch"] == 1
    assert frame["width_px"] == 320
    assert frame["height_px"] == 240
    journal = result.data["journal"]
    assert isinstance(journal, Mapping)
    assert journal["kind"] == "drone.observation"
    assert journal["message_id"] == "msg-drone-observation"
    assert journal["mission_id"] == "demo-20261104-001"
    assert journal["epoch"] == 1
    assert journal["beacon_epoch"] == 3
    assert journal["frame_id"] == "drone-downward-001"
    assert journal["camera_epoch"] == 1
    assert journal["command_id"] is None
    assert result.events[0].kind == "decision_received"
    assert result.events[0].payload["height_reference"] == "floor_agl"
    assert result.data["state_writes"] == 0
    assert result.data["command_methods"] == ()
    assert getattr(services.state, "trace", []) == []
    assert getattr(services.journal, "records", []) == []
    devices = getattr(services.adapters, "devices", None)
    assert getattr(devices, "calls", ["missing"]) == []


def test_unknown_reference_is_not_a_floor_profile(tmp_path: Path) -> None:
    envelope = load("drone-observation.json")
    payload = envelope["payload"]
    assert isinstance(payload, dict)
    payload["height_reference"] = "unknown"
    _, result = _run(tmp_path, request_for(envelope, load("drone-capabilities.json")))
    body = _observation(result)
    assert result.status == "ok"
    assert body["height_estimate_m"] == 4.0
    assert body["height_reference"] == "unknown"
    assert body["floor_agl_claim"] is False


def test_takeoff_relative_number_stays_takeoff_relative(tmp_path: Path) -> None:
    envelope = load("drone-observation.json")
    payload = envelope["payload"]
    assert isinstance(payload, dict)
    payload["height_reference"] = "takeoff_relative"
    _, result = _run(tmp_path, request_for(envelope, load("drone-capabilities.json")))
    body = _observation(result)
    assert body["height_estimate_m"] == 4.0
    assert body["height_reference"] == "takeoff_relative"
    assert body["floor_agl_claim"] is False


def test_floor_label_cannot_upgrade_a_takeoff_relative_height(tmp_path: Path) -> None:
    envelope = load("drone-observation.json")
    payload = envelope["payload"]
    assert isinstance(payload, dict)
    payload["height_reference"] = "takeoff_relative"
    _, result = _run(
        tmp_path,
        request_for(
            envelope,
            load("drone-capabilities.json"),
            height_label="floor_agl",
        ),
    )
    assert result.status == "blocked"
    assert result.error is not None
    assert result.error.code == "rejected"
    assert "floor_agl" in result.error.detail
    assert result.events == ()
    assert "observation" not in result.data


def test_matching_floor_label_is_accepted(tmp_path: Path) -> None:
    _, result = _run(
        tmp_path,
        request_for(
            load("drone-observation.json"),
            load("drone-capabilities.json"),
            height_label="floor_agl",
        ),
    )
    assert result.status == "ok"
    assert _observation(result)["floor_agl_claim"] is True


def test_null_pose_battery_and_frame_stay_null(tmp_path: Path) -> None:
    envelope = load("drone-observation.json")
    payload = envelope["payload"]
    assert isinstance(payload, dict)
    payload["pose"] = None
    payload["battery_percent"] = None
    payload["frame"] = None
    _, result = _run(tmp_path, request_for(envelope, load("drone-capabilities.json")))
    body = _observation(result)
    assert result.status == "ok"
    assert body["pose"] is None
    assert body["battery_percent"] is None
    assert body["frame"] is None
    assert body["frame_id"] is None
    assert body["camera_epoch"] is None
    assert body["map_epoch"] is None
    assert result.data["journal"]["frame_id"] is None  # type: ignore[index]


def test_unknown_flight_state_survives_an_attached_frame(tmp_path: Path) -> None:
    envelope = load("drone-observation.json")
    payload = envelope["payload"]
    assert isinstance(payload, dict)
    payload["flight_state"] = "unknown"
    _, result = _run(tmp_path, request_for(envelope, load("drone-capabilities.json")))
    assert _observation(result)["flight_state"] == "unknown"
    assert _observation(result)["frame"] is not None


def test_reported_pose_is_copied_without_added_axes(tmp_path: Path) -> None:
    envelope = load("drone-observation.json")
    payload = envelope["payload"]
    assert isinstance(payload, dict)
    payload["pose"] = {
        "frame_id": "drone/base_link",
        "map_id": None,
        "map_epoch": 0,
        "x_m": 1.5,
        "y_m": -2.0,
        "z_m": 4.0,
        "yaw_rad": 0.25,
        "observed_at": "2026-11-04T13:00:10.000Z",
        "valid": True,
    }
    _, result = _run(tmp_path, request_for(envelope, load("drone-capabilities.json")))
    pose = _observation(result)["pose"]
    assert isinstance(pose, Mapping)
    assert set(pose) == {
        "frame_id",
        "map_id",
        "map_epoch",
        "x_m",
        "y_m",
        "z_m",
        "yaw_rad",
        "observed_at",
        "valid",
    }
    assert pose["x_m"] == 1.5
    assert pose["map_id"] is None
    assert _observation(result)["map_epoch"] == 0


def test_active_command_is_not_completion(tmp_path: Path) -> None:
    envelope = load("drone-observation.json")
    payload = envelope["payload"]
    assert isinstance(payload, dict)
    payload["active_command_id"] = "cmd-drone-001"
    services, result = _run(tmp_path, request_for(envelope, load("drone-capabilities.json")))
    body = _observation(result)
    assert body["active_command_id"] == "cmd-drone-001"
    assert body["command_completed"] is False
    assert result.data["journal"]["command_id"] == "cmd-drone-001"  # type: ignore[index]
    devices = getattr(services.adapters, "devices", None)
    assert getattr(devices, "calls", ["missing"]) == []


def test_sender_time_is_not_replaced_by_local_receive_time(tmp_path: Path) -> None:
    _, result = _run(
        tmp_path,
        request_for(
            load("drone-observation.json"),
            load("drone-capabilities.json"),
            received_monotonic=12.5,
        ),
    )
    body = _observation(result)
    assert body["sent_at"] == "2026-11-04T13:00:10.000Z"
    assert body["received_monotonic"] == 12.5
    assert body["received_utc"] == "2026-01-01T00:00:00+00:00"


def test_fixture_copy_matches_the_contract_example() -> None:
    root = Path(__file__).resolve().parents[3]
    examples = root / "contracts" / "examples"
    copied = root / "fixtures" / "ground" / "g13"
    assert (copied / "drone-observation.json").read_bytes() == (
        examples / "drone-observation.json"
    ).read_bytes()
    assert (copied / "drone-capabilities.json").read_bytes() == (
        examples / "drone-capabilities.json"
    ).read_bytes()
    unused = copy.deepcopy(load("drone-observation.json"))
    assert unused["kind"] == "drone.observation"
