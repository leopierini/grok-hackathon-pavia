"""Shared fixtures for dog-navigation tests."""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import cast

from patrol.ground.extensions.g20.implementation import NavigationFeature, create
from patrol.ground.extensions.g20.policy import SLOT
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest, FeatureResult, Ticket
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services

CANDIDATE = "candidate-forward-01"


def services(tmp_path: Path) -> BaseServices:
    return build_test_services(output_dir=tmp_path)


def feature(tmp_path: Path) -> tuple[BaseServices, NavigationFeature]:
    built = services(tmp_path)
    return built, create(built)


def fixture(name: str) -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g20" / name
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AssertionError(f"{name} is not an object")
    return cast(dict[str, object], copy.deepcopy(loaded))


def observation() -> dict[str, object]:
    return fixture("dog-observation.json")


def candidates() -> dict[str, object]:
    return fixture("dog-navigation-candidates.json")


def capabilities() -> dict[str, object]:
    return fixture("dog-capabilities.json")


def payload(
    *,
    observation_message: dict[str, object] | None = None,
    candidate_message: dict[str, object] | None = None,
    capability_message: dict[str, object] | None = None,
    map_epoch: int = 1,
    dog_transport: str = "ethernet",
) -> dict[str, object]:
    return {
        "observation": observation() if observation_message is None else observation_message,
        "candidates": candidates() if candidate_message is None else candidate_message,
        "capabilities": capabilities() if capability_message is None else capability_message,
        "map_epoch": map_epoch,
        "profile": {"dog_transport": dog_transport, "profile_identity": f"{dog_transport}-test"},
    }


def request(body: Mapping[str, object], ticket: Ticket | None = None) -> FeatureRequest:
    return FeatureRequest("guard", SLOT, ticket, body)


def run(test: Callable[[], Awaitable[None]]) -> None:
    asyncio.run(test())


def data_of(result: FeatureResult) -> Mapping[str, object]:
    return result.data


def calls_of(built: BaseServices) -> list[str]:
    devices = getattr(built.adapters, "devices", None)
    found = getattr(devices, "calls", None)
    if not isinstance(found, list):
        raise AssertionError("device call trace is missing")
    return found


def as_object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AssertionError(f"{label} is not an object")
    return cast(dict[str, object], value)


def readiness_of(result: FeatureResult) -> Mapping[str, object]:
    readiness = result.data["readiness"]
    if not isinstance(readiness, Mapping):
        raise AssertionError("readiness record is missing")
    return readiness


def ids_of(result: FeatureResult) -> tuple[object, ...]:
    found = result.data["candidate_ids"]
    if not isinstance(found, tuple):
        raise AssertionError("candidate ids are not a tuple")
    return found


def first_candidate(message: dict[str, object]) -> dict[str, object]:
    body = as_object(message["payload"], "payload")
    rows = body["candidates"]
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise AssertionError("candidate missing")
    return cast(dict[str, object], rows[0])


def forbid_target_range(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {
                "target_range",
                "target_range_m",
                "range_m",
                "person_range_m",
                "target_distance_m",
                "distance_m",
            }:
                raise AssertionError(f"target range leaked in {key}")
            forbid_target_range(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            forbid_target_range(item)
