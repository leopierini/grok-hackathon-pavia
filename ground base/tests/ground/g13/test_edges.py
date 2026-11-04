"""Rejections leave no observation event and no device command."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

from tests.ground.g13.support import feature, load, request_for


def _payload(envelope: dict[str, object]) -> dict[str, object]:
    payload = envelope["payload"]
    assert isinstance(payload, dict)
    return payload


def _run(path: Path, request: object) -> tuple[object, object]:
    services, provider = feature(path)

    async def body() -> object:
        return await provider.execute(request)  # type: ignore[arg-type]

    return services, asyncio.run(body())


def test_short_bssid_is_rejected_without_a_write(tmp_path: Path) -> None:
    envelope = load("drone-observation.json")
    beacon = _payload(envelope)["beacon"]
    assert isinstance(beacon, dict)
    beacon["bssid"] = "02:00:00:00:00"
    services, result = _run(tmp_path, request_for(envelope, load("drone-capabilities.json")))
    assert result.status == "failed"  # type: ignore[attr-defined]
    assert result.error.code == "invalid_input"  # type: ignore[attr-defined]
    assert "six octets" in result.error.detail  # type: ignore[attr-defined]
    assert result.events == ()  # type: ignore[attr-defined]
    assert "observation" not in result.data  # type: ignore[attr-defined]
    assert getattr(services.state, "trace", ["state.apply"]) == []


def test_dashed_and_seven_octet_bssids_are_rejected(tmp_path: Path) -> None:
    capability = load("drone-capabilities.json")
    for value in ("02-00-00-00-00-01", "02:00:00:00:00:01:02"):
        envelope = load("drone-observation.json")
        beacon = _payload(envelope)["beacon"]
        assert isinstance(beacon, dict)
        beacon["bssid"] = value
        _, result = _run(tmp_path, request_for(envelope, capability))
        assert result.status == "failed"  # type: ignore[attr-defined]
        assert result.events == ()  # type: ignore[attr-defined]


def test_uppercase_bssid_is_stored_in_canonical_form(tmp_path: Path) -> None:
    envelope = load("drone-observation.json")
    beacon = _payload(envelope)["beacon"]
    assert isinstance(beacon, dict)
    beacon["bssid"] = "02:00:00:00:00:0A"
    _, result = _run(tmp_path, request_for(envelope, load("drone-capabilities.json")))
    stored = result.data["observation"]["beacon"]  # type: ignore[attr-defined, index]
    assert isinstance(stored, Mapping)
    assert stored["bssid"] == "02:00:00:00:00:0a"


def test_foreign_device_is_rejected(tmp_path: Path) -> None:
    envelope = load("drone-observation.json")
    _payload(envelope)["device_id"] = "drone-02"
    services, result = _run(tmp_path, request_for(envelope, load("drone-capabilities.json")))
    assert result.status == "blocked"  # type: ignore[attr-defined]
    assert result.error.code == "rejected"  # type: ignore[attr-defined]
    assert result.events == ()  # type: ignore[attr-defined]
    devices = getattr(services.adapters, "devices", None)
    assert getattr(devices, "calls", ["missing"]) == []


def test_unvalidated_capability_does_not_arm(tmp_path: Path) -> None:
    capability = load("drone-capabilities.json")
    payload = capability["payload"]
    assert isinstance(payload, dict)
    payload["validated"] = False
    _, result = _run(tmp_path, request_for(load("drone-observation.json"), capability))
    assert result.status == "blocked"  # type: ignore[attr-defined]
    assert result.error.code == "rejected"  # type: ignore[attr-defined]
    assert result.events == ()  # type: ignore[attr-defined]


def test_string_validated_flag_does_not_arm(tmp_path: Path) -> None:
    capability = load("drone-capabilities.json")
    payload = capability["payload"]
    assert isinstance(payload, dict)
    payload["validated"] = "true"
    _, result = _run(tmp_path, request_for(load("drone-observation.json"), capability))
    assert result.status == "blocked"  # type: ignore[attr-defined]
    assert result.events == ()  # type: ignore[attr-defined]


def test_null_acceptance_reference_does_not_arm(tmp_path: Path) -> None:
    capability = load("drone-capabilities.json")
    payload = capability["payload"]
    assert isinstance(payload, dict)
    payload["acceptance_evidence_ref"] = None
    _, result = _run(tmp_path, request_for(load("drone-observation.json"), capability))
    assert result.error.code == "rejected"  # type: ignore[attr-defined]


def test_late_epoch_is_stale_and_not_committed(tmp_path: Path) -> None:
    services, result = _run(
        tmp_path,
        request_for(
            load("drone-observation.json"),
            load("drone-capabilities.json"),
            mission_epoch=2,
        ),
    )
    assert result.status == "blocked"  # type: ignore[attr-defined]
    assert result.error.code == "stale_ticket"  # type: ignore[attr-defined]
    assert result.error.recovery_required is True  # type: ignore[attr-defined]
    assert result.events == ()  # type: ignore[attr-defined]
    assert getattr(services.state, "trace", ["state.apply"]) == []


def test_ticket_from_the_previous_generation_is_stale(tmp_path: Path) -> None:
    services, provider = feature(tmp_path)
    ticket = services.kernel.authority.issue("demo-20261104-001", "drone.observation")
    services.kernel.authority.reset_generation("operator reset")
    envelope = load("drone-observation.json")
    envelope["epoch"] = 0
    request = request_for(
        envelope,
        load("drone-capabilities.json"),
        mission_epoch=0,
        ticket=ticket,
    )

    async def body() -> object:
        return await provider.execute(request)

    result = asyncio.run(body())
    assert result.status == "blocked"  # type: ignore[attr-defined]
    assert result.error.code == "stale_ticket"  # type: ignore[attr-defined]
    assert result.events == ()  # type: ignore[attr-defined]


def test_battery_outside_0_to_100_is_rejected(tmp_path: Path) -> None:
    capability = load("drone-capabilities.json")
    for value in (-1, 101, True, "74"):
        envelope = load("drone-observation.json")
        _payload(envelope)["battery_percent"] = value
        _, result = _run(tmp_path, request_for(envelope, capability))
        assert result.status == "failed"  # type: ignore[attr-defined]
        assert result.events == ()  # type: ignore[attr-defined]


def test_null_battery_is_kept(tmp_path: Path) -> None:
    envelope = load("drone-observation.json")
    _payload(envelope)["battery_percent"] = None
    _, result = _run(tmp_path, request_for(envelope, load("drone-capabilities.json")))
    assert result.data["observation"]["battery_percent"] is None  # type: ignore[attr-defined, index]


def test_floor_agl_without_a_height_is_rejected(tmp_path: Path) -> None:
    envelope = load("drone-observation.json")
    _payload(envelope)["height_estimate_m"] = None
    _, result = _run(tmp_path, request_for(envelope, load("drone-capabilities.json")))
    assert result.status == "failed"  # type: ignore[attr-defined]
    assert "floor_agl" in result.error.detail  # type: ignore[attr-defined]


def test_partial_pose_is_not_filled_in(tmp_path: Path) -> None:
    envelope = load("drone-observation.json")
    _payload(envelope)["pose"] = {"x_m": 1.0, "y_m": 2.0}
    _, result = _run(tmp_path, request_for(envelope, load("drone-capabilities.json")))
    assert result.status == "failed"  # type: ignore[attr-defined]
    assert "observation" not in result.data  # type: ignore[attr-defined]


def test_missing_beacon_window_is_rejected(tmp_path: Path) -> None:
    envelope = load("drone-observation.json")
    beacon = _payload(envelope)["beacon"]
    assert isinstance(beacon, dict)
    del beacon["hold_valid_until"]
    _, result = _run(tmp_path, request_for(envelope, load("drone-capabilities.json")))
    assert result.status == "failed"  # type: ignore[attr-defined]
    assert result.events == ()  # type: ignore[attr-defined]


def test_same_message_replays_once(tmp_path: Path) -> None:
    _, provider = feature(tmp_path)
    request = request_for(load("drone-observation.json"), load("drone-capabilities.json"))

    async def body() -> tuple[object, object]:
        first = await provider.execute(request)
        second = await provider.execute(request)
        return first, second

    first, second = asyncio.run(body())
    assert first.data["replayed"] is False  # type: ignore[attr-defined]
    assert len(first.events) == 1  # type: ignore[attr-defined]
    assert second.status == "ok"  # type: ignore[attr-defined]
    assert second.data["replayed"] is True  # type: ignore[attr-defined]
    assert second.events == ()  # type: ignore[attr-defined]
    assert second.data["observation"] == first.data["observation"]  # type: ignore[attr-defined]


def test_changed_replay_is_rejected(tmp_path: Path) -> None:
    _, provider = feature(tmp_path)
    original = request_for(load("drone-observation.json"), load("drone-capabilities.json"))
    changed_envelope = load("drone-observation.json")
    _payload(changed_envelope)["battery_percent"] = 70
    changed = request_for(changed_envelope, load("drone-capabilities.json"))

    async def body() -> object:
        await provider.execute(original)
        return await provider.execute(changed)

    result = asyncio.run(body())
    assert result.status == "blocked"  # type: ignore[attr-defined]
    assert result.error.code == "rejected"  # type: ignore[attr-defined]
    assert result.events == ()  # type: ignore[attr-defined]


def test_cancelled_session_stores_nothing(tmp_path: Path) -> None:
    services, provider = feature(tmp_path)
    services.kernel.authority.latch_cancel("operator halt")

    async def body() -> object:
        return await provider.execute(
            request_for(load("drone-observation.json"), load("drone-capabilities.json"))
        )

    result = asyncio.run(body())
    assert result.error.code == "cancelled"  # type: ignore[attr-defined]
    assert result.events == ()  # type: ignore[attr-defined]


def test_image_bytes_are_not_required(tmp_path: Path) -> None:
    envelope = load("drone-observation.json")
    frame = _payload(envelope)["frame"]
    assert isinstance(frame, dict)
    frame["image_ref"] = r"C:\sender-only\downward.jpg"
    _, result = _run(tmp_path, request_for(envelope, load("drone-capabilities.json")))
    stored = result.data["observation"]["frame"]  # type: ignore[attr-defined, index]
    assert isinstance(stored, Mapping)
    assert stored["image_ref"] == r"C:\sender-only\downward.jpg"
    assert result.status == "ok"  # type: ignore[attr-defined]
