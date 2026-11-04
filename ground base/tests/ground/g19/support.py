"""Shared fixtures for beacon-hold tests."""

from __future__ import annotations

import copy
import json
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import cast

from patrol.ground.extensions.g19.implementation import BeaconFeature, create
from patrol.ground.extensions.g19.policy import SLOT
from patrol.ground.kernel.clock import ManualClock
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest, FeatureResult, Ticket
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services

ARMED = "02:00:00:00:00:01"
HOLD_UNTIL = datetime.fromisoformat("2026-11-04T13:00:12+00:00")


def services(tmp_path: Path) -> BaseServices:
    return build_test_services(output_dir=tmp_path)


def feature(tmp_path: Path) -> tuple[BaseServices, BeaconFeature]:
    built = services(tmp_path)
    created = create(built)
    return built, created


def fixture(name: str) -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g19" / name
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AssertionError(f"{name} is not an object")
    return cast(dict[str, object], copy.deepcopy(loaded))


def observation() -> dict[str, object]:
    return fixture("drone-observation.json")


def window(window_id: str = "pi-window-1", epoch: int = 3) -> dict[str, object]:
    return {
        "window_id": window_id,
        "beacon_epoch": epoch,
        "bssid": ARMED,
        "rssi_dbm": -60,
        "median_rssi_dbm": -60,
    }


def payload(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "armed_bssid": ARMED,
        "observation": observation(),
        "windows": [window()],
    }
    body.update(overrides)
    return body


def request(body: Mapping[str, object], ticket: Ticket | None = None) -> FeatureRequest:
    return FeatureRequest("guard", SLOT, ticket, body)


def run(test: Callable[[], Awaitable[None]]) -> None:
    import asyncio

    asyncio.run(test())


def advance_to(built: BaseServices, moment: datetime) -> None:
    clock = built.kernel.clock
    if not isinstance(clock, ManualClock):
        raise AssertionError("expected the manual clock")
    delta = (moment - clock.utc_now()).total_seconds()
    if delta > 0:
        clock.advance(delta)


def beacon_of(message: dict[str, object]) -> dict[str, object]:
    inner = message["payload"]
    if not isinstance(inner, dict):
        raise AssertionError("payload missing")
    beacon = inner["beacon"]
    if not isinstance(beacon, dict):
        raise AssertionError("beacon missing")
    return cast(dict[str, object], beacon)


def data_of(result: FeatureResult) -> Mapping[str, object]:
    return result.data


def calls_of(built: BaseServices) -> list[str]:
    devices = getattr(built.adapters, "devices", None)
    found = getattr(devices, "calls", None)
    if not isinstance(found, list):
        raise AssertionError("device call trace is missing")
    return found
