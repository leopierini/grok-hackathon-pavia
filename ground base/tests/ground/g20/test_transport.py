"""Dog transport must match the selected profile before readiness."""

from __future__ import annotations

from pathlib import Path

from patrol.ground.kernel.contracts import GroundSettings
from patrol.ground.kernel.settings import make_settings
from tests.ground.g20.support import (
    CANDIDATE,
    as_object,
    feature,
    ids_of,
    observation,
    payload,
    request,
    run,
)


def test_ethernet_observation_on_wifi_profile_is_not_ready(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        result = await port.execute(request(payload(dog_transport="wifi")))
        assert result.status == "ok"
        assert result.error is None
        assert result.data["ready"] is False
        assert result.data["ready_to_wait"] is False
        assert result.data["transport"] == "ethernet"
        assert result.data["profile_transport"] == "wifi"
        assert result.data["reason"] == "transport_mismatch"
        assert ids_of(result) == ()
        assert result.data["commands"] == ()

    run(body)


def test_wifi_observation_matches_wifi_profile(tmp_path: Path) -> None:
    async def body() -> None:
        message = observation()
        as_object(message["payload"], "payload")["transport"] = "wifi"
        _built, port = feature(tmp_path)
        result = await port.execute(
            request(payload(observation_message=message, dog_transport="wifi"))
        )
        assert result.status == "ok"
        assert result.data["ready"] is True
        assert result.data["transport"] == "wifi"
        assert ids_of(result) == (CANDIDATE,)

    run(body)


def test_ground_settings_transport_is_the_selected_profile(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        settings = make_settings(dog_transport="wifi")
        assert isinstance(settings, GroundSettings)
        body_map = payload()
        body_map.pop("profile")
        body_map["settings"] = settings
        result = await port.execute(request(body_map))
        assert result.status == "ok"
        assert result.data["ready"] is False
        assert result.data["profile_transport"] == "wifi"
        assert ids_of(result) == ()

    run(body)


def test_conflicting_profile_and_settings_are_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        _built, port = feature(tmp_path)
        body_map = payload(dog_transport="ethernet")
        body_map["settings"] = {"dog_transport": "wifi"}
        result = await port.execute(request(body_map))
        assert result.status == "failed"
        assert result.error is not None
        assert result.error.code == "invalid_input"
        assert ids_of(result) == ()

    run(body)
